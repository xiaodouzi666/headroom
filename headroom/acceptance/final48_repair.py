"""Pinned F3 repair pack: pure preparation and explicitly authorized sequential execution.

No profile, credential, budget database, workload or provider is opened by prepare/verify.
The fixed nine, two new s2 tiers and HF remain separate result groups.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import yaml

from headroom.acceptance.common import file_record, read_json, write_json
from headroom.acceptance.final48_tiers import prepare_s2_tiers, summarize_s2_tier
from headroom.api.security import open_regular
from headroom.budget import money
from headroom.evaluation import Scenario, load_manifest, resolve_policies, result_row, summarize
from headroom.orchestrator import FixRequest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "headroom.final48-repair.v1"
CAP = Decimal(4)
PER_RUN = Decimal("0.6")
MAX_BYTES = 64 * 1024 * 1024
CALIBRATION = "reports/s2-calibration-v2-20261025-c/audit.json"
SCENARIOS = (
    "s1_batch_too_big",
    "s2_capacity_v2",
    "s3_eval_no_grad_missing",
    "s4_loss_accumulation_graph",
    "s5_fragmentation_varlen",
    "s6_full_vocab_logits_fp32",
    "s7_frozen_params_optimizer_state",
    "s8_two_models_resident",
    "nanogpt",
)
CONTROLS = {
    "condition": "full_ultra",
    "search_mode": "until_target",
    "policy_name": "strict",
    "fixed_denominator": 9,
    "minimum_targets": 6,
    "max_rounds": 6,
    "max_steps": 20,
    "max_seconds_per_lab": 120,
    "wall_seconds_per_cell": 480,
    "seed": 1337,
    "per_run_budget_usd": "0.6",
    "scope_cap_usd": "4",
    "planned_cells": 12,
    "new_s2_tiers_replace_primary": False,
    "hf_in_primary": False,
    "request_policy": "final48-diagnosis-only-2000-v1",
}


class F3Refused(ValueError):
    """Stable refusal codes; never provider text, source contents or credentials."""


def require(condition, code):
    if not condition:
        raise F3Refused(code)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def inside(root, path):
    root = Path(root).resolve()
    path = Path(path)
    require(
        ".." not in path.parts and not any(p.lower().startswith(".env") for p in path.parts),
        "UNSAFE_INPUT_PATH",
    )
    absolute = path.absolute() if path.is_absolute() else (root / path).absolute()
    require(absolute.is_relative_to(root), "PATH_OUTSIDE_PROJECT")
    for part in (absolute, *absolute.parents):
        require(not part.is_symlink(), "SYMLINK_INPUT")
        if part == root:
            break
    return absolute


def _pin(pins, root, path, maximum=MAX_BYTES):
    absolute = inside(root, path)
    relative = str(absolute.relative_to(root))
    pins[relative] = file_record(absolute, maximum)
    return relative


def implementation_pins():
    paths = sorted((ROOT / "headroom").rglob("*.py"))
    paths += sorted((ROOT / "headroom/prompts").glob("*.md"))
    paths += sorted((ROOT / "scripts").glob("*.py"))
    paths += [ROOT / name for name in ("pyproject.toml", "uv.lock")]
    require(len(paths) <= 512, "IMPLEMENTATION_FILE_LIMIT")
    return {str(path.relative_to(ROOT)): file_record(path, MAX_BYTES) for path in paths}


def _request(case, root, policy):
    # Same R5 controls; the reviewed request policy is selected later by the bound profile.
    return FixRequest(
        script=str(root / case.script),
        source_root=str(root / case.source_root),
        script_args=list(case.script_args),
        source_profile=case.source_profile,
        target=case.target,
        policy=policy,
        numerical_reference=case.numerical_reference,
        allocator_conf=case.allocator_conf,
        reclaim_reduction_pct=case.reclaim_reduction_pct,
        search_mode="until_target",
        max_steps=20,
        max_rounds=6,
        max_seconds=120,
        seed=1337,
        budget_usd="0.6",
        daily_budget_usd="4",
        research_enabled=True,
    )


def _calibration(root, path, case, pins):
    relative = _pin(pins, root, path)
    audit = read_json(root / relative)
    require(
        audit.get("schema") == "headroom.s2-calibration-audit.v2" and audit.get("accepted") is True,
        "ACCEPTED_S2_CALIBRATION_REQUIRED",
    )
    require(
        not audit.get("errors")
        and len(audit.get("cases", [])) == 5
        and all(row.get("accepted") is True for row in audit["cases"]),
        "S2_CALIBRATION_INCOMPLETE",
    )
    plan_path = (root / relative).parent / "preregistration.json"
    _pin(pins, root, plan_path)
    plan = read_json(plan_path)
    require(
        plan.get("schema") == "headroom.s2-calibration.v2"
        and plan.get("required_steps") == 20
        and plan.get("fit_limit_bytes") == 22_000_000_000
        and plan.get("source_pins", {}).get("capacity_baseline", {}).get("sha256")
        == case.source_sha256,
        "S2_CALIBRATION_SOURCE_CHANGED",
    )
    require(
        audit.get("preregistration_sha256") == pins[str(plan_path.relative_to(root))]["sha256"],
        "S2_CALIBRATION_RECEIPT_CHANGED",
    )
    return {
        "receipt": relative,
        "accepted": True,
        "new_calibration_executed": False,
        "source_sha256": case.source_sha256,
        "historical_manifest_sha256": audit.get("manifest_sha256"),
    }


def prepare_f3(*, project_root=ROOT, calibration_path=CALIBRATION):
    """Return a deterministic reviewed pack. Never creates files or executes setup."""
    root = Path(project_root).resolve()
    pins = {}
    primary_path = _pin(pins, root, "eval/mvp_phase1_v2.yaml")
    extra_path = _pin(pins, root, "eval/scenario_set_v2.yaml")
    primary = load_manifest(root / primary_path, project_root=root)
    extra = load_manifest(root / extra_path, project_root=root)
    require(tuple(c.id for c in primary.scenarios) == SCENARIOS, "FIXED_NINE_CHANGED")
    hf = next((c for c in extra.scenarios if c.id == "hf_trainer"), None)
    require(
        hf is not None and hf.target == "fix-oom" and hf.group == "repository", "HF_CASE_REQUIRED"
    )
    strict = dict(resolve_policies(("strict",)))["strict"]
    require(
        strict.numerical_requirement == "legacy" and not strict.allow_numerics_change,
        "LEGACY_PRIMARY_POLICY_CHANGED",
    )
    require(
        all(c.reclaim_reduction_pct == 20 for c in primary.scenarios if c.target == "reclaim"),
        "FIXED_NINE_RECLAIM_CONTROL_CHANGED",
    )
    source_files = {}
    for case in [*primary.scenarios, hf]:
        source = inside(root, case.source_root)
        script = _pin(pins, root, case.script, 2 * 1024 * 1024)
        require(pins[script]["sha256"] == case.source_sha256, "SCENARIO_SOURCE_CHANGED")
        files = []
        for path in sorted(source.rglob("*.py")):
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            require(len(files) < 256, "TOO_MANY_SOURCE_FILES")
            relative = _pin(pins, root, path, 2 * 1024 * 1024)
            files.append(relative)
        require(case.script in files, "ENTRYPOINT_NOT_PINNED")
        source_files[case.id] = files
        if case.repository_manifest:
            _pin(pins, root, case.repository_manifest, 1024 * 1024)
    nano = next(c for c in primary.scenarios if c.id == "nanogpt")
    nano_manifest = yaml.safe_load((root / nano.repository_manifest).read_text())
    require(
        re.fullmatch(r"[a-f0-9]{40}", nano_manifest.get("ref", "")) is not None,
        "PINNED_NANOGPT_REVISION_REQUIRED",
    )
    git = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root / nano.source_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    require(
        git.returncode == 0 and git.stdout.strip() == nano_manifest["ref"],
        "NANOGPT_REVISION_CHANGED",
    )
    s2 = next(c for c in primary.scenarios if c.id == "s2_capacity_v2")
    calibration = _calibration(root, calibration_path, s2, pins)
    cells = []
    for case in primary.scenarios:
        cells.append(
            {
                "cell_id": "fixed9-" + case.id,
                "result_group": "fixed_nine",
                "scenario_id": case.id,
                "policy_name": "strict",
                "case": case.model_dump(),
                "request": _request(case, root, strict).model_dump(),
            }
        )
    for tier, request in prepare_s2_tiers(_request(s2, root, strict)).items():
        cells.append(
            {
                "cell_id": "s2-" + tier.replace("_", "-"),
                "result_group": "s2_tiers",
                "scenario_id": s2.id,
                "tier": tier,
                "policy_name": tier,
                "case": s2.model_dump(),
                "request": request.model_dump(),
            }
        )
    precision = dict(resolve_policies(("allow_precision",)))["allow_precision"]
    cells.append(
        {
            "cell_id": "hf-trainer",
            "result_group": "hf_trainer",
            "scenario_id": hf.id,
            "policy_name": "allow_precision",
            "case": hf.model_dump(),
            "request": _request(hf, root, precision).model_dump(),
        }
    )
    for cell in cells:
        cell["request_sha256"] = digest(cell["request"])
    prepared = {
        "schema": SCHEMA,
        "mode": "prepare",
        "project_root": str(root),
        "controls": copy.deepcopy(CONTROLS),
        "cells": cells,
        "input_pins": pins,
        "implementation_pins": implementation_pins(),
        "source_files": source_files,
        "calibration": calibration,
        "repository_identities": {
            "nanogpt": {"revision": git.stdout.strip(), "manifest": nano.repository_manifest}
        },
        "planned_cells": 12,
        "executed_cells": 0,
        "live_authorized": False,
        "allocation_status": "unresolved_until_explicit_execution",
        "profile_status": "unresolved_until_explicit_execution",
        "limitations": [
            "The fixed nine retains denominator 9 and threshold 6; extra tiers and HF never enter it.",
            "The 4 USD ceiling does not guarantee all twelve runs can be dispatched.",
            "Missing, pending or unknown charges stop subsequent dispatch; they are never zero.",
            "The historical s2 calibration is pinned evidence, not a new GPU calibration.",
            "Legacy strict and exact-loss20-v1 are different numerical requirements.",
            "Preparation grants no funding and creates no live repair result.",
        ],
    }
    prepared["preparation_sha256"] = digest(prepared)
    return prepared


def verify_preparation(path, *, expected_sha256):
    """Verify the explicitly reviewed digest and reconstruct all pins without side effects."""
    require(
        re.fullmatch(r"[a-f0-9]{64}", str(expected_sha256)) is not None,
        "REVIEWED_PREPARATION_SHA_REQUIRED",
    )
    document = read_json(path, max_bytes=MAX_BYTES)
    stored = document.pop("preparation_sha256", None)
    require(stored == expected_sha256 == digest(document), "PREPARATION_CHANGED")
    root = Path(document["project_root"]).resolve()
    inside(root, path)
    rebuilt = prepare_f3(project_root=root, calibration_path=document["calibration"]["receipt"])
    require(rebuilt["preparation_sha256"] == expected_sha256, "PREPARATION_INPUTS_CHANGED")
    return rebuilt


def bound_requests(prepared, *, profile_path, daily_limit_usd):
    """Pure request binding for allocation preparation; no profile/database is opened."""
    daily = money(daily_limit_usd)
    require(daily > 0, "INVALID_F3_DAILY_REQUEST_LIMIT")
    profile = inside(Path(prepared["project_root"]), profile_path)
    return {
        cell["cell_id"]: FixRequest.model_validate(
            {
                **cell["request"],
                "runtime_profile": str(profile),
                "daily_budget_usd": str(daily),
            }
        )
        for cell in prepared["cells"]
    }


def cell_request_pins(prepared, *, profile_path, daily_limit_usd):
    return {
        name: digest(request.model_dump(mode="json"))
        for name, request in bound_requests(
            prepared, profile_path=profile_path, daily_limit_usd=daily_limit_usd
        ).items()
    }


def _reference_for(job, document):
    locator = document.get("verification", {}).get("reference_run")
    if not locator:
        return None
    path = inside(job / "lab", locator)
    require(path.name and path.is_dir(), "REFERENCE_CAPTURE_UNAVAILABLE")
    value = read_json(path / "result.json", max_bytes=2 * 1024 * 1024)
    require(
        value.get("protocol") == "headroom.lab.v1" and value.get("run_id") == path.name,
        "REFERENCE_CAPTURE_IDENTITY_CHANGED",
    )
    return value


def _hf_check(root, job, cell, result, prepared):
    from headroom.acceptance.hf_configuration import check_hf_configuration

    source = inside(root, cell["case"]["source_root"])
    document = result.get("report") if isinstance(result.get("report"), dict) else {}
    kept = result.get("kept") or document.get("run", {}).get("kept") or {}
    candidate = kept.get("source")
    if not candidate:
        # Only an explicitly recorded actual candidate can be inspected.
        rounds = document.get("rounds", [])
        candidate = next(
            (
                row.get("candidate_dir")
                for row in reversed(rounds)
                if isinstance(row, dict) and row.get("candidate_dir")
            ),
            None,
        )
    if not candidate:
        return {
            "status": "unavailable",
            "accepted": False,
            "reason": "candidate_source_unavailable",
        }
    try:
        candidate = inside(job, candidate)
        require(candidate.is_dir(), "HF_CANDIDATE_UNAVAILABLE")
        before, after = {}, {}
        for relative in prepared["source_files"][cell["scenario_id"]]:
            path = inside(root, relative)
            with open_regular(source, str(path.relative_to(source)), 2 * 1024 * 1024) as stream:
                before[str(path.relative_to(source))] = stream.read().decode("utf-8")
        for path in sorted(candidate.rglob("*.py")):
            require(len(after) < 256, "HF_CANDIDATE_FILE_LIMIT")
            path = inside(candidate, path)
            with open_regular(
                candidate, str(path.relative_to(candidate)), 2 * 1024 * 1024
            ) as stream:
                after[str(path.relative_to(candidate))] = stream.read().decode("utf-8")
        return {
            "status": "checked",
            **check_hf_configuration(
                before,
                after,
                expected_source_sha256=cell["case"]["source_sha256"],
                max_changed_lines=15,
            ),
        }
    except (OSError, ValueError, TypeError, UnicodeError):
        return {
            "status": "unavailable",
            "accepted": False,
            "reason": "candidate_source_not_safely_readable",
        }


def _empty_row(cell, provenance):
    case = cell["case"]
    return {
        "cell_id": cell["cell_id"],
        "result_group": cell["result_group"],
        "scenario_id": cell["scenario_id"],
        "group": case["group"],
        "condition": "full_ultra",
        "policy_name": cell["policy_name"],
        "policy": cell["request"]["policy"],
        "status": "not_run",
        "provenance": provenance,
        "target_met": None,
        "cost_usd": None,
        "known_cost_usd": None,
        "run_id": None,
        "ground_truth": case.get("ground_truth"),
        "truth_status": case["truth_status"],
        "first_cause_matches": None,
        "first_cause": None,
        "reason": "not_dispatched",
    }


def _summaries(document):
    fixed = [row for row in document["rows"] if row["result_group"] == "fixed_nine"]
    targets = sum(
        row.get("target_met") is True and row.get("provenance") == "live" for row in fixed
    )
    document["fixed_nine"] = {
        "denominator": 9,
        "minimum_targets": 6,
        "target_met_count": targets,
        "offline_fixture_target_count": sum(
            row.get("target_met") is True and row.get("provenance") == "offline_fixture"
            for row in fixed
        ),
        "threshold_met": targets >= 6,
        "rows": fixed,
        "summary": summarize([row for row in fixed if row["status"] not in {"not_run", "running"}]),
    }
    document["s2_tiers"] = [row for row in document["rows"] if row["result_group"] == "s2_tiers"]
    document["hf_trainer"] = next(
        row for row in document["rows"] if row["result_group"] == "hf_trainer"
    )
    document["admitted_cells"] = sum(row["status"] != "not_run" for row in document["rows"])
    document["executed_cells"] = sum(
        row["status"] not in {"not_run", "running"} for row in document["rows"]
    )
    document["remaining_unrun_cells"] = sum(row["status"] == "not_run" for row in document["rows"])
    return document


def execute_f3(
    prepared_path,
    *,
    expected_sha256,
    allocation_receipt,
    profile_path,
    output_dir,
    execute=False,
    live_authorized=False,
    scope_limit_usd="4",
    _allocation=None,
    _supervisor=None,
):
    """Run exactly the prepared ordered cells, once, inside the receipt-bound F3 scope.

    The paired private injections are for offline fake-supervisor tests only; those
    results are always labelled offline_fixture and never count as live evidence.
    """
    require(execute is True and live_authorized is True, "EXPLICIT_LIVE_AUTHORIZATION_REQUIRED")
    require((_allocation is None) == (_supervisor is None), "PAIRED_OFFLINE_DEPENDENCIES_REQUIRED")
    offline = _allocation is not None
    if not offline:
        from headroom.acceptance import allocation as allocation_api
        from headroom.evaluation_worker import supervise_evaluation_run
    else:
        allocation_api, supervise_evaluation_run = _allocation, _supervisor
    from headroom.store.db import Store

    cap = money(scope_limit_usd)
    require(0 < cap <= CAP, "F3_SCOPE_CANNOT_EXCEED_FOUR_USD")
    prepared = verify_preparation(prepared_path, expected_sha256=expected_sha256)
    root = Path(prepared["project_root"])
    output = inside(root, output_dir)
    require(
        output.is_relative_to(root / "runs") and not output.exists(),
        "NEW_PRIVATE_EXECUTION_DIRECTORY_REQUIRED",
    )
    receipt = allocation_api.verify_receipt(allocation_receipt, project_root=root)
    require(str(inside(root, profile_path)) == receipt["profile_path"], "F3_PROFILE_MISMATCH")
    profile = read_json(inside(root, profile_path), max_bytes=1024 * 1024)
    require(
        profile.get("diagnosis_request_policy") == CONTROLS["request_policy"],
        "F3_DIAGNOSIS_REQUEST_POLICY_REQUIRED",
    )
    daily = money(receipt["amounts"]["daily_limit_usd"])
    requests = bound_requests(prepared, profile_path=profile_path, daily_limit_usd=str(daily))
    request_pins = {
        name: digest(request.model_dump(mode="json")) for name, request in requests.items()
    }
    parent = allocation_api.claim_f3_parent(
        allocation_receipt,
        project_root=root,
        preparation_sha256=expected_sha256,
        cell_requests=request_pins,
        scope_limit_usd=str(cap),
    )
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    provenance = "offline_fixture" if offline else "live"
    document = {
        "schema": SCHEMA,
        "mode": "execute",
        "provenance": provenance,
        "preparation_sha256": expected_sha256,
        "controls": copy.deepcopy(CONTROLS),
        "scope_cap_usd": str(cap),
        "status": "running",
        "stop_reason": None,
        "planned_cells": 12,
        "new_spending_scope_granted": False,
        "rows": [_empty_row(cell, provenance) for cell in prepared["cells"]],
        "scope_spent_usd": None,
        "all_costs_known": False,
        "historical_scores_modified": False,
        "report_path": str(output / "campaign.json"),
    }
    store = None
    finished = False

    def persist():
        write_json(output / "campaign.json", _summaries(document))

    persist()
    try:
        store = Store(output / "observations.db" if offline else root / "runs/headroom.db")
        for index, cell in enumerate(prepared["cells"]):
            # Changed source/code stops before any new admission or workload preparation.
            verify_preparation(prepared_path, expected_sha256=expected_sha256)
            account = allocation_api.f3_accounting(parent)
            document["accounting"] = account
            document["scope_spent_usd"] = account.get("scope_spent_usd")
            document["all_costs_known"] = account.get("all_costs_known") is True
            if (
                account.get("status") == "blocked"
                or not document["all_costs_known"]
                or account.get("scope_spent_usd") is None
            ):
                document["stop_reason"] = "unresolved_scope_cost"
                break
            spent = money(account["scope_spent_usd"])
            if spent < 0 or spent + PER_RUN > min(cap, money(account["scope_limit_usd"])):
                document["stop_reason"] = "insufficient_scope_for_next_full_run"
                break
            run_id = uuid4().hex
            request = requests[cell["cell_id"]]
            child = allocation_api.claim_f3_child(
                parent, cell_id=cell["cell_id"], request=request, run_id=run_id
            )
            document["rows"][index].update(
                status="running", run_id=run_id, request_sha256=request_pins[cell["cell_id"]]
            )
            persist()  # Durable intent before child preparation, research, GPU or model dispatch.
            started = time.monotonic()
            result = {}
            failure = None
            try:
                result = supervise_evaluation_run(
                    request,
                    store=store,
                    run_root=output / "jobs",
                    run_id=run_id,
                    condition="full_ultra",
                    audit_dir=output / ("condition-" + run_id),
                    started=started,
                    preparation={
                        "case": cell["case"],
                        "study_protocol": None,
                        "project_root": str(root),
                        "input_dir": str(output / ("input-" + run_id)),
                    },
                    wall_limit_seconds=480,
                    allocation_child_binding=child,
                )
            except Exception as error:  # noqa: BLE001 - retain uncertainty, never raw exception text
                failure = type(error).__name__
            timing = result.get("evaluation_timing", {})
            terminal = failure is None and result.get("status") in {
                "completed",
                "done",
                "failed",
                "needs_human",
                "budget_exceeded",
                "timeout",
                "cancelled",
                "rejected",
            }
            clean = timing.get("cleanup_verified") is True
            settlement = allocation_api.finish_f3_child(
                child, execution_terminal=terminal, cleanup_verified=clean
            )
            usage = store.usage(run_id) if store.get_run(run_id) is not None else None
            row = result_row(
                Scenario.model_validate(cell["case"]),
                "full_ultra",
                result,
                usage,
                provenance=provenance,
            )
            row.update(
                cell_id=cell["cell_id"],
                result_group=cell["result_group"],
                policy_name=cell["policy_name"],
                policy=request.policy.model_dump(),
                run_id=run_id,
                request_sha256=request_pins[cell["cell_id"]],
                wall_seconds=time.monotonic() - started,
                run_wall_limit_seconds=480,
                evaluation_timing=timing,
                settlement=settlement,
                cost_usd=settlement.get("actual_usd"),
                known_cost_usd=settlement.get("actual_usd"),
                cost_source="receipt_bound_scope_accounting",
                error_type=failure,
            )
            if failure:
                row["status"] = "error"
            safe_result = (
                terminal
                and clean
                and timing.get("within_wall_limit") is True
                and timing.get("cli", {}).get("verified") is True
                and settlement.get("status") == "settled"
                and settlement.get("actual_usd") is not None
                and money(settlement["actual_usd"]) <= PER_RUN
            )
            row["execution_certified"] = safe_result
            if not safe_result:
                row["target_met"] = False
            job = output / "jobs" / run_id
            if cell["result_group"] == "s2_tiers":
                try:
                    report = result.get("report", {})
                    row["tier_result"] = summarize_s2_tier(
                        cell["tier"],
                        request,
                        {
                            "run": report.get("run", {}),
                            "verification": report.get("verification", {}),
                        },
                        reference=_reference_for(job, report),
                    )
                    if not safe_result:
                        row["tier_result"]["tier_met"] = False
                except (OSError, ValueError, TypeError, KeyError):
                    row["tier_result"] = {
                        "tier": cell["tier"],
                        "tier_met": False,
                        "status": "evidence_unavailable",
                    }
            elif cell["result_group"] == "hf_trainer":
                row["configuration_check"] = _hf_check(root, job, cell, result, prepared)
                row["hf_requirement_met"] = (
                    row.get("target_met") is True
                    and row["configuration_check"].get("accepted") is True
                )
            document["rows"][index] = row
            account = allocation_api.f3_accounting(parent)
            document.update(
                accounting=account,
                scope_spent_usd=account.get("scope_spent_usd"),
                all_costs_known=account.get("all_costs_known") is True,
            )
            persist()
            if settlement.get("status") != "settled" or not safe_result:
                document["stop_reason"] = "child_execution_or_cost_unverified"
                break
        finished = document["stop_reason"] is None and all(
            row["status"] != "not_run" for row in document["rows"]
        )
        document["status"] = "finished" if finished else "partial"
        return document
    finally:
        if not finished and document["stop_reason"] is None:
            document["stop_reason"] = "interrupted_or_admission_refused"
            document["status"] = "partial"
        if store is not None:
            store.close()
        try:
            account = allocation_api.f3_accounting(parent)
            document.update(
                accounting=account,
                scope_spent_usd=account.get("scope_spent_usd"),
                all_costs_known=account.get("all_costs_known") is True,
            )
            allocation_api.finish_f3_parent(
                parent,
                status="completed"
                if finished
                else (
                    "stopped"
                    if document["stop_reason"] == "insufficient_scope_for_next_full_run"
                    else "blocked"
                ),
            )
        finally:
            persist()
