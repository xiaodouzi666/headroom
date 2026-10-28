"""Frozen nine-case, three-condition diagnosis-only F1 preparation and opt-in execution.

Preparation rebuilds evidence from preserved baseline captures; it does not open a
runtime, credential file or budget database. Live execution is never implicit.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import httpx

from headroom.acceptance.common import (
    acceptance_run,
    dispatch_summary,
    file_record,
    read_bytes,
    read_json,
    write_json,
)
from headroom.budget import BudgetExceeded, money
from headroom.config import SUPER_MODEL, ULTRA_MODEL
from headroom.diagnose import PROMPT_PATH, build_diagnosis_messages, validate_diagnosis
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.evaluation import restricted_evidence
from headroom.evidence import MAX_SNAPSHOT_BYTES, _main_source, _tokens, build_evidence
from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.lab.runner import read_capture, selected_capture_directory
from headroom.llm.client import LLMError
from headroom.llm.router import ResponseValidationError
from headroom.orchestrator import Policy
from headroom.runtime import PROJECT_ROOT

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
CONDITIONS = ("full_ultra", "traceback_ultra", "full_super")
# Exact vocabulary already defined by prompts/diagnose.md, not scenario answers.
CATEGORIES = (
    "params",
    "grads",
    "optimizer_state",
    "activations",
    "temporaries",
    "retained_graph",
    "cache",
    "fragmentation_candidate",
    "unknown",
)
DEFAULT_CAMPAIGN = "runs/evaluation/live/20261027T022818939585Z-151818b1/campaign.json"
SCHEMA = "headroom.final48-diagnosis-only.v1"
CAP = Decimal("1.50")
MAX_JSON = 64 * 1024 * 1024
GOAL = (
    "Identify the dominant GPU memory cause supported by the supplied evidence and explain "
    "it with evidence references. Return a diagnosis and proposed plan only. No patch or "
    "workload will be executed in this study. Missing information must remain explicit."
)


class F1Refused(ValueError):
    """Fixed refusal codes, without raw source or provider exception text."""


def require(condition, code):
    if not condition:
        raise F1Refused(code)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def inside(root, path):
    root, path = Path(root).resolve(), Path(path).absolute()
    require(not path.is_symlink(), "SYMLINK_INPUT")
    resolved = path.resolve()
    require(resolved.is_relative_to(root), "PATH_OUTSIDE_PROJECT")
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        require(not ancestor.is_symlink(), "SYMLINK_INPUT")
    require(not any(p.lower().startswith(".env") for p in path.parts), "CREDENTIAL_PATH_FORBIDDEN")
    return resolved


def pin(pins, root, path, limit=MAX_JSON):
    path = inside(root, path)
    relative = str(path.relative_to(root))
    pins[relative] = file_record(path, limit)
    return relative


def implementation_pins():
    root = Path(__file__).resolve().parents[2]
    names = (
        "headroom/acceptance/final48_ablation.py",
        "headroom/acceptance/common.py",
        "headroom/acceptance/allocation.py",
        "headroom/acceptance/feature_allocation.py",
        "headroom/diagnose.py",
        "headroom/diagnosis_protocol.py",
        "headroom/diagnosis_schema.py",
        "headroom/config.py",
        "headroom/orchestrator.py",
        "headroom/verify/numerical_requirement.py",
        "headroom/schemas.py",
        "headroom/solver_context.py",
        "headroom/evidence.py",
        "headroom/evidence_analysis.py",
        "headroom/evidence_blockers.py",
        "headroom/evaluation.py",
        "headroom/llm/router.py",
        "headroom/llm/client.py",
        "headroom/llm/request_audit.py",
        "headroom/store/db.py",
        "headroom/store/models.py",
        "headroom/api/security.py",
        "headroom/llm/admission.py",
        "headroom/llm/preflight.py",
        "headroom/llm/cost.py",
        "headroom/runtime.py",
        "headroom/budget.py",
        "headroom/ledger_path.py",
    )
    return {name: file_record(root / name, MAX_JSON) for name in names} | {
        "headroom/prompts/diagnose.md": file_record(PROMPT_PATH, MAX_JSON)
    }


def policy_metadata():
    policy = FINAL48_DIAGNOSIS_ONLY
    require(
        policy.max_completion_tokens == 2000 and policy.reasoning is False,
        "FINAL48_REQUEST_POLICY_CHANGED",
    )
    return {
        "id": policy.id,
        "max_completion_tokens": policy.max_completion_tokens,
        "reasoning": policy.reasoning,
        "max_supplements": 0,
        "max_http_retries": 0,
        "patch_calls": 0,
        "research_calls": 0,
        "gpu_executions": 0,
    }


def scoring_metadata():
    return {
        "id": "first-category-agreement-v1",
        "primary": "Strict JSON first root-cause category equals the authored manifest truth.",
        "strict_json": "No duplicate keys, nonfinite values, text extraction, JSON repair, or retries.",
        "category_contract": "The same RootCause.category enum in all three conditions.",
        "categories": list(CATEGORIES),
        "secondary": "Full Diagnosis and reference validation recorded separately; not required for primary category agreement.",
        "denominator_per_condition": 9,
        "unknown_truths": ["s5_fragmentation_varlen", "nanogpt"],
        "missing_or_invalid_first_category": None,
    }


def strict_first_category(text, schema):
    if not isinstance(text, str) or len(text.encode("utf-8")) > 256 * 1024:
        return None, "response_not_bounded_text", None

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise F1Refused("duplicate_json_keys")
            result[key] = value
        return result

    def reject_constant(_):
        raise F1Refused("nonfinite_json")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise F1Refused("nonfinite_json")
        return parsed

    try:
        document = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except F1Refused as error:
        return None, str(error), None
    except (ValueError, TypeError, RecursionError):
        return None, "invalid_json", None
    roots = document.get("root_causes") if type(document) is dict else None
    first = (
        roots[0].get("category")
        if type(roots) is list and roots and type(roots[0]) is dict
        else None
    )
    allowed = schema["$defs"]["RootCause"]["properties"]["category"]["enum"]
    allowed_refs = schema["$defs"]["RootCause"]["properties"]["evidence_refs"]["items"]["enum"]
    refs_valid = None
    if type(roots) is list and roots:
        refs_valid = all(
            type(root) is dict
            and type(root.get("evidence_refs")) is list
            and bool(root["evidence_refs"])
            and all(isinstance(ref, str) and ref in allowed_refs for ref in root["evidence_refs"])
            for root in roots
        )
    return (
        (first, "strict_json_category", refs_valid)
        if isinstance(first, str) and first in allowed
        else (None, "missing_or_invalid_first_category", refs_valid)
    )


def request_for(document, markdown):
    visible = copy.deepcopy(document)
    if "presentation" in visible:
        presentation = visible["presentation"]
        shown = set(presentation.get("peak_stack_ids", [])) | set(
            presentation.get("allocation_stack_ids", [])
        )
        catalog = visible["analysis"]["stack_catalog"]
        visible["analysis"]["stack_catalog"] = {
            key: value for key, value in catalog.items() if key in shown
        }
    visible["evidence_availability_catalog"] = build_evidence_availability_catalog(
        visible, markdown
    )
    policy = Policy().model_dump()
    messages = build_diagnosis_messages(
        markdown,
        goal=GOAL,
        policy=policy,
        required_saving_gb=None,
        evidence_availability_catalog=visible["evidence_availability_catalog"],
        request_policy=FINAL48_DIAGNOSIS_ONLY,
    )
    schema = build_diagnosis_schema(evidence=visible, policy=policy)
    schema["$defs"]["RootCause"]["properties"]["category"]["enum"] = list(CATEGORIES)
    return visible, messages, schema


def baseline_inputs(root, campaign_row, case, pins):
    job = inside(root, campaign_row["run_dir"])
    locator = job / "evidence/before/evidence.json"
    pin(pins, root, locator)
    baseline_id = read_json(locator, max_bytes=MAX_JSON)["run_id"]
    require(isinstance(baseline_id, str) and baseline_id.isalnum(), "INVALID_BASELINE_ID")
    capture = inside(root, job / "lab" / baseline_id)
    result = read_capture(capture / "result.json")
    manifest = read_json(capture / "manifest.json", max_bytes=MAX_JSON)
    require(result.get("run_id") == baseline_id, "BASELINE_RUN_ID_MISMATCH")
    require(
        result.get("capture_complete") is True and result.get("cleanup_verified") is True,
        "BASELINE_CAPTURE_INCOMPLETE",
    )
    require(result.get("status") == case["expected_baseline"], "BASELINE_STATUS_MISMATCH")
    require(
        manifest.get("device") == result.get("env", {}).get("device") == "cuda",
        "CUDA_CAPTURE_REQUIRED",
    )
    require(
        manifest.get("max_steps") == result.get("env", {}).get("max_steps") == 20,
        "BASELINE_UPDATE_CONFIGURATION_CHANGED",
    )
    command = manifest.get("command", [])
    expected_args = case.get("script_args", [])
    if case.get("group") == "repository":
        require(len(command) >= 2 and command[1] == "train.py", "REPOSITORY_ENTRYPOINT_CHANGED")
        args = command[2:]
        if case.get("source_profile") == "pinned_nanogpt":
            # Same recorded dataset relocation used by evaluation._prepare_case;
            # no target execution or new dataset is needed to verify this capture.
            expected_args = [
                "--dataset=headroom_synthetic" if a == "--dataset=/input" else a
                for a in expected_args
            ]
    else:
        args = command[command.index("--") + 1 :] if "--" in command else []
    require(args == expected_args, "BASELINE_ARGUMENTS_CHANGED")
    primary = _main_source(manifest)
    require(primary == "train.py", "ORIGINAL_TRAIN_SOURCE_REQUIRED")
    require(
        file_record(capture / "source" / primary, MAX_JSON)["sha256"] == case["source_sha256"],
        "BASELINE_SOURCE_CHANGED",
    )
    for name, recorded in manifest["source"]["files"].items():
        source = inside(root, capture / "source" / name)
        require(source.is_relative_to(capture / "source"), "SOURCE_ESCAPES_CAPTURE")
        pin(pins, root, source)
        require(
            file_record(source, MAX_JSON)["sha256"] == recorded["sha256"],
            "CAPTURE_SOURCE_HASH_MISMATCH",
        )
    artifacts = selected_capture_directory(capture, result, manifest)
    for path in (
        capture / "result.json",
        capture / "manifest.json",
        artifacts / "result.json",
        artifacts / "env.json",
    ):
        pin(pins, root, path)
    pin(pins, root, artifacts / "snapshot.json", MAX_SNAPSHOT_BYTES)
    inputs = {}
    for name in ("traceback", "memory_summary"):
        path = artifacts / (name + ".txt")
        pin(pins, root, path, 1024 * 1024)
        inputs[name] = read_bytes(path, 1024 * 1024).decode("utf-8")
        require(inputs[name].strip(), "MISSING_CAPTURED_TEXT_" + name.upper())
    return capture, inputs


def prepare_f1(campaign_path, output_dir, *, project_root=PROJECT_ROOT, evidence_budget=150000):
    root = Path(project_root).resolve()
    output = inside(root, output_dir)
    require(output.is_relative_to(root / "runs"), "PRIVATE_RUNS_DIRECTORY_REQUIRED")
    require(not output.exists(), "NEW_PREPARATION_DIRECTORY_REQUIRED")
    require(
        type(evidence_budget) is int and 1000 <= evidence_budget <= 150000,
        "INVALID_EVIDENCE_BUDGET",
    )
    source = inside(root, campaign_path)
    manifest_path = root / "eval/mvp_phase1_v2.yaml"
    cases = read_json(manifest_path, max_bytes=MAX_JSON)["scenarios"]
    require(tuple(c["id"] for c in cases) == SCENARIOS, "FIXED_NINE_SCENARIOS_REQUIRED")
    campaign = read_json(source, max_bytes=MAX_JSON)
    require(campaign.get("provenance") in {"live", "offline_fixture"}, "UNKNOWN_CAPTURE_PROVENANCE")
    if campaign.get("manifest_sha256") is not None:
        require(
            campaign["manifest_sha256"] == file_record(manifest_path, MAX_JSON)["sha256"],
            "CAMPAIGN_MANIFEST_CHANGED",
        )
    rows = campaign["rows"]
    require(tuple(r["scenario_id"] for r in rows) == SCENARIOS, "FIXED_NINE_BASELINES_REQUIRED")
    require(
        all(r.get("condition") == "full_ultra" for r in rows), "ORIGINAL_FULL_BASELINES_REQUIRED"
    )
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    pins = {}
    pin(pins, root, source)
    pin(pins, root, manifest_path)
    prepared = {
        "schema": SCHEMA,
        "mode": "prepare",
        "provenance": campaign["provenance"],
        "project_root": str(root),
        "source_campaign": str(source.relative_to(root)),
        "conditions": list(CONDITIONS),
        "scenario_ids": list(SCENARIOS),
        "fixed_denominator": 9,
        "planned_requests": 27,
        "executed_requests": 0,
        "campaign_cap_usd": str(CAP),
        "live_authorized": False,
        "inputs_ready": False,
        "request_policy": policy_metadata(),
        "scoring_policy": scoring_metadata(),
        "scoring_policy_sha256": digest(canonical(scoring_metadata())),
        "evidence_budget": evidence_budget,
        "input_pins": pins,
        "implementation_pins": implementation_pins(),
        "rows": [],
        "truths": {},
        "limitations": [
            "Preparation is not model execution, budget approval or a repair result.",
            "Local cl100k counts are approximations, not provider billable input counts.",
            "s5 and nanoGPT truth stays unknown; the denominator remains nine.",
            "Authored synthetic source comments and captured paths can suggest mechanisms; this is not a blinded benchmark.",
            "Paths and stack identifiers are preserved consistently; no ad-hoc renaming can break references.",
            "A new independent comparison, not a rerun or rescore of the historical repair campaign.",
        ],
    }
    for case_index, (case, original) in enumerate(zip(cases, rows, strict=True)):
        scenario = case["id"]
        known = case.get("truth_status") == "authored" and scenario not in {SCENARIOS[4], "nanogpt"}
        truth_path = root / (
            f"scenarios/{scenario}/README.md" if scenario != "nanogpt" else "repos/nanogpt.yaml"
        )
        truth = {
            "category": case.get("ground_truth") if known else None,
            "status": "authored" if known else "unverified",
            "source": str(manifest_path.relative_to(root)),
            "json_pointer": f"/scenarios/{case_index}/ground_truth",
            "status_pointer": f"/scenarios/{case_index}/truth_status",
            "notes_source": pin(pins, root, truth_path) if truth_path.exists() else None,
        }
        prepared["truths"][scenario] = truth
        try:
            capture, texts = baseline_inputs(root, original, case, pins)
            require(
                not output.is_relative_to(capture) and not capture.is_relative_to(output),
                "OUTPUT_OVERLAPS_CAPTURE",
            )
            built = build_evidence(
                capture, budget=evidence_budget, output_dir=output / scenario / "full"
            )
            full = read_json(built["evidence_json"], max_bytes=MAX_JSON)
            full_markdown = read_bytes(built["evidence_md"], MAX_JSON).decode("utf-8")
            # Fresh builder output contains measured evidence and source, never previous model labels.
            require(
                "annotation_delivery" not in full and "diagnosis" not in full,
                "MODEL_OUTPUT_IN_FRESH_EVIDENCE",
            )
            restricted_markdown, restricted = restricted_evidence({"evaluation_inputs": texts})
            for condition in CONDITIONS:
                is_full = condition != "traceback_ultra"
                markdown, document = (
                    (full_markdown, full) if is_full else (restricted_markdown, restricted)
                )
                visible, messages, schema = request_for(document, markdown)
                directory = output / scenario / condition
                directory.mkdir(parents=True, mode=0o700)
                payload = {
                    "evidence": visible,
                    "evidence_markdown": markdown,
                    "messages": messages,
                    "schema": schema,
                }
                request_path = directory / "request.json"
                write_json(request_path, payload)
                prepared["rows"].append(
                    {
                        "scenario_id": scenario,
                        "condition": condition,
                        "status": "ready",
                        "capture": str(capture.relative_to(root)),
                        "truth": truth,
                        "role": "patcher" if condition == "full_super" else "diagnose",
                        "expected_model": SUPER_MODEL if condition == "full_super" else ULTRA_MODEL,
                        "request_path": str(request_path.relative_to(output)),
                        "request_sha256": file_record(request_path, MAX_JSON)["sha256"],
                        "messages_sha256": digest(canonical(messages)),
                        "schema_sha256": digest(canonical(schema)),
                        "local_input_tokens_approx": _tokens(
                            json.dumps({"messages": messages, "schema": schema})
                        ),
                        "input_kind": "snapshot_and_source"
                        if is_full
                        else "traceback_and_memory_summary",
                    }
                )
        except (OSError, ValueError, TypeError, KeyError) as error:
            # Preserve the complete grid even if a baseline cannot support the experiment.
            prepared["rows"] = [r for r in prepared["rows"] if r["scenario_id"] != scenario]
            prepared["rows"].extend(
                {
                    "scenario_id": scenario,
                    "condition": condition,
                    "status": "not_ready",
                    "truth": truth,
                    "reason": str(error) if isinstance(error, F1Refused) else type(error).__name__,
                }
                for condition in CONDITIONS
            )
    prepared["inputs_ready"] = all(r["status"] == "ready" for r in prepared["rows"])
    prepared["ready_requests"] = sum(r["status"] == "ready" for r in prepared["rows"])
    prepared["preparation_sha256"] = digest(canonical(prepared))
    write_json(output / "preparation.json", prepared)
    for path in output.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    return prepared


def verify_preparation(path):
    path = Path(path).resolve()
    prepared = read_json(path, max_bytes=MAX_JSON)
    expected = prepared.pop("preparation_sha256", None)
    require(digest(canonical(prepared)) == expected, "PREPARATION_CHANGED")
    prepared["preparation_sha256"] = expected
    require(prepared["schema"] == SCHEMA and prepared["inputs_ready"] is True, "INPUTS_NOT_READY")
    require(prepared["request_policy"] == policy_metadata(), "REQUEST_POLICY_CHANGED")
    require(
        prepared["scoring_policy"] == scoring_metadata()
        and prepared["scoring_policy_sha256"] == digest(canonical(scoring_metadata())),
        "SCORING_POLICY_CHANGED",
    )
    require(
        prepared["implementation_pins"] == implementation_pins(), "REQUEST_IMPLEMENTATION_CHANGED"
    )
    require(
        prepared["planned_requests"] == 27 and prepared["executed_requests"] == 0,
        "REQUEST_COUNT_CHANGED",
    )
    require(
        [(r["scenario_id"], r["condition"]) for r in prepared["rows"]]
        == [(s, c) for s in SCENARIOS for c in CONDITIONS],
        "FIXED_GRID_CHANGED",
    )
    root = Path(prepared["project_root"])
    inside(root, path)
    require(path.is_relative_to(root / "runs"), "PRIVATE_RUNS_DIRECTORY_REQUIRED")
    for relative, record in prepared["input_pins"].items():
        require(
            file_record(inside(root, root / relative), MAX_SNAPSHOT_BYTES) == record,
            "ORIGINAL_INPUT_CHANGED",
        )
    for row in prepared["rows"]:
        request_path = inside(path.parent, path.parent / row["request_path"])
        require(
            file_record(request_path, MAX_JSON)["sha256"] == row["request_sha256"],
            "REQUEST_ARTIFACT_CHANGED",
        )
        payload = read_json(request_path, max_bytes=MAX_JSON)
        require(
            digest(canonical(payload["messages"])) == row["messages_sha256"], "MESSAGES_CHANGED"
        )
        require(digest(canonical(payload["schema"])) == row["schema_sha256"], "SCHEMA_CHANGED")
        require(
            row["role"] == ("patcher" if row["condition"] == "full_super" else "diagnose"),
            "MODEL_ROLE_CHANGED",
        )
        require(
            row["expected_model"]
            == (SUPER_MODEL if row["condition"] == "full_super" else ULTRA_MODEL),
            "EXACT_MODEL_REQUIRED",
        )
        _, rebuilt_messages, rebuilt_schema = request_for(
            payload["evidence"], payload["evidence_markdown"]
        )
        require(
            payload["messages"] == rebuilt_messages and payload["schema"] == rebuilt_schema,
            "REQUEST_CONSTRUCTION_CHANGED",
        )
        row["_payload"] = payload
    for index in range(0, 27, 3):
        ultra, _, super_row = prepared["rows"][index : index + 3]
        require(
            ultra["messages_sha256"] == super_row["messages_sha256"]
            and ultra["schema_sha256"] == super_row["schema_sha256"],
            "FULL_ARMS_INPUT_MISMATCH",
        )
    return prepared


def summarize(rows):
    summaries = []
    for condition in CONDITIONS:
        group = [r for r in rows if r["condition"] == condition]
        calls = [c for row in group for c in row.get("usage", [])]
        costs = [Decimal(str(c["cost_usd"])) for c in calls if c.get("cost_usd") is not None]
        token_counts = [c["prompt_tokens"] for c in calls if type(c.get("prompt_tokens")) is int]
        latencies = [r["elapsed_seconds"] for r in group if r.get("dispatched") is True]
        all_dispatched = len(calls) == 9 and all(r.get("dispatched") is True for r in group)
        summaries.append(
            {
                "condition": condition,
                "denominator": 9,
                "attempted": sum(r.get("dispatched") is True for r in group),
                "first_cause_matches": sum(r.get("first_cause_match") is True for r in group),
                "valid_correct_first_causes": sum(
                    r.get("valid_correct_first_cause") is True for r in group
                ),
                "unscored_truths": 2,
                "unknown_or_unexecuted": sum(r.get("first_cause_match") is None for r in group),
                "mean_provider_input_tokens": sum(token_counts) / 9
                if all_dispatched and len(token_counts) == 9
                else None,
                "input_tokens_observed": len(token_counts),
                "mean_latency_seconds": sum(latencies) / 9
                if all_dispatched and len(latencies) == 9
                else None,
                "known_cost_usd": str(sum(costs, Decimal(0))),
                "total_cost_usd": str(sum(costs, Decimal(0)))
                if all_dispatched and len(costs) == 9
                else None,
                "cost_unknown_calls": len(calls) - len(costs),
            }
        )
    return summaries


def execute_f1(
    prepared_path,
    *,
    profile_path,
    daily_limit_usd,
    campaign_limit_usd="1.50",
    execute=False,
    live_authorized=False,
    transport=None,
    env_file=None,
    allocation_receipt=None,
):
    require(execute is True and live_authorized is True, "EXPLICIT_LIVE_AUTHORIZATION_REQUIRED")
    cap = money(campaign_limit_usd)
    require(Decimal(0) < cap <= CAP and money(daily_limit_usd) > 0, "INVALID_F1_BUDGET")
    require(
        transport is None or isinstance(transport, httpx.MockTransport),
        "ONLY_OFFLINE_MOCK_TRANSPORT",
    )
    require(transport is not None or allocation_receipt is not None, "ALLOCATION_RECEIPT_REQUIRED")
    prepared = verify_preparation(prepared_path)
    require(
        transport is not None or prepared["provenance"] == "live", "FIXTURE_CANNOT_EXECUTE_LIVE"
    )
    profile_document = read_json(profile_path, max_bytes=256 * 1024)
    require(
        profile_document.get("run_budget_mode", "strict_reservation") == "strict_reservation",
        "STRICT_RESERVATION_REQUIRED",
    )
    package = Path(prepared_path).resolve().parent
    execution_dir = package / "execution"
    execution_dir.mkdir(mode=0o700, exist_ok=False)
    result = {
        "schema": SCHEMA,
        "mode": "execute",
        "provenance": "offline_fixture" if transport is not None else "live",
        "preparation_sha256": prepared["preparation_sha256"],
        "request_policy": policy_metadata(),
        "scoring_policy": scoring_metadata(),
        "scoring_policy_sha256": prepared["scoring_policy_sha256"],
        "campaign_limit_usd": str(cap),
        "denominator": 9,
        "planned_requests": 27,
        "completed_all_requests": False,
        "within_budget": None,
        "study_complete_within_budget": False,
        "total_cost_usd": None,
        "known_cost_usd": "0",
        "stop_reason": None,
        "rows": [],
        "conditions": [],
    }
    for row in prepared["rows"]:
        result["rows"].append(
            {k: row[k] for k in ("scenario_id", "condition", "truth", "expected_model")}
            | {
                "status": "not_executed",
                "dispatched": False,
                "first_cause_match": None,
                "valid_correct_first_cause": None,
            }
        )
    write_json(execution_dir / "ablation.json", result)
    active = None
    try:
        with acceptance_run(
            case_id="final48-f1-diagnosis-only",
            artifact_dir=execution_dir / "runtime",
            profile_path=profile_path,
            run_limit_usd=str(cap),
            daily_limit_usd=daily_limit_usd,
            execute=True,
            live_authorized=True,
            project_root=prepared["project_root"],
            transport=transport,
            env_file=env_file,
            max_http_retries=0,
            allocation_receipt=allocation_receipt,
            allocation_scope="F1" if allocation_receipt is not None else None,
            allocation_execution_key="once",
            preparation_sha256=prepared["preparation_sha256"],
            scoring_policy_sha256=prepared["scoring_policy_sha256"],
        ) as active:
            result["run_id"] = active.run_id
            require(
                active.profile.run_budget_mode == "strict_reservation",
                "STRICT_RESERVATION_REQUIRED",
            )
            for index, (request, row) in enumerate(
                zip(prepared["rows"], result["rows"], strict=True)
            ):
                payload = request["_payload"]
                # Recheck all frozen inputs before every call; never reuse a changed artifact.
                verify_preparation(prepared_path)
                if active.allocation is not None:
                    active.allocation.revalidate()
                require(
                    active.bundle.client.config.model_for(request["role"]).model_id
                    == row["expected_model"],
                    "EXACT_MODEL_REQUIRED",
                )
                before_ids = {c["id"] for c in active.store.llm_calls(active.run_id)}
                started = time.monotonic()
                response = None
                try:
                    response = active.router.chat(
                        request["role"],
                        payload["messages"],
                        payload["schema"],
                        max_tokens=FINAL48_DIAGNOSIS_ONLY.max_completion_tokens,
                        reasoning=FINAL48_DIAGNOSIS_ONLY.reasoning,
                    )
                    checked = validate_diagnosis(
                        response.parsed,
                        evidence=payload["evidence"],
                        policy=Policy().model_dump(),
                        required_saving_gb=None,
                    )
                    first = (
                        checked.diagnosis.root_causes[0].category
                        if checked.diagnosis and checked.diagnosis.root_causes
                        else None
                    )
                    truth = row["truth"]["category"]
                    row.update(
                        status="diagnosed" if checked.valid else "invalid_diagnosis",
                        first_cause=first,
                        diagnosis_valid=checked.valid,
                        raw_first_cause_match=first == truth if truth is not None else None,
                        valid_correct_first_cause=bool(checked.valid and first == truth)
                        if truth is not None
                        else None,
                        validation_issues=[asdict(issue) for issue in checked.issues],
                    )
                except ResponseValidationError as error:
                    response = error.response
                    row.update(
                        status="invalid_response",
                        diagnosis_valid=False,
                        response_error=error.reason,
                        valid_correct_first_cause=False
                        if row["truth"]["category"] is not None
                        else None,
                    )
                except (BudgetExceeded, LLMError) as error:
                    row.update(status="request_failed", error_type=type(error).__name__)
                    result["stop_reason"] = type(error).__name__
                finally:
                    row["elapsed_seconds"] = time.monotonic() - started
                    calls = [
                        c
                        for c in active.store.llm_calls(active.run_id)
                        if c["id"] not in before_ids
                    ]
                    row["call_ids"] = [c["id"] for c in calls]
                    dispatch = dispatch_summary(calls)
                    row["dispatch"] = dispatch
                    row["dispatched"] = (
                        None if dispatch["dispatch_unresolved"] else dispatch["attempted_calls"] > 0
                    )
                    if row.get("error_type") == "BudgetExceeded" and row["dispatched"] is False:
                        row["status"] = "not_dispatched"
                    row["call_count"] = len(calls)
                    require(len(calls) <= 1, "F1_CALL_COUNT_VIOLATION")
                    row["usage"] = [
                        {
                            key: c.get(key)
                            for key in (
                                "model",
                                "response_model",
                                "prompt_tokens",
                                "completion_tokens",
                                "reasoning_tokens",
                                "cost_usd",
                                "http_status",
                                "settled",
                                "outcome",
                                "request_evidence",
                            )
                        }
                        | {
                            key: (c.get("usage") or {}).get(key)
                            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens")
                        }
                        for c in calls
                    ]
                    if response is not None:
                        response_text = response.text
                        first, extraction, references_valid = strict_first_category(
                            response_text, payload["schema"]
                        )
                        truth = row["truth"]["category"]
                        primary = (
                            first == truth if first is not None and truth is not None else None
                        )
                        row.update(
                            first_cause=first,
                            first_category_extraction=extraction,
                            references_valid=references_valid,
                            first_cause_match=primary,
                            raw_first_cause_match=primary,
                            valid_correct_first_cause=bool(
                                row.get("diagnosis_valid") and primary is True
                            )
                            if truth is not None
                            else None,
                        )
                        artifact = execution_dir / f"{index + 1:02d}-response.json"
                        write_json(
                            artifact,
                            {
                                "text": response_text[: 256 * 1024],
                                "text_sha256": digest(response_text.encode()),
                                "text_truncated": len(response_text) > 256 * 1024,
                                "parsed": getattr(response, "parsed", None),
                                "model": response.model,
                                "finish_reason": response.finish_reason,
                            },
                        )
                        row["response_artifact"] = artifact.name
                    if any(
                        c.get("settled") is not True or c.get("cost_usd") is None for c in calls
                    ):
                        result["stop_reason"] = result["stop_reason"] or "UNKNOWN_REQUEST_COST"
                    result["conditions"] = summarize(result["rows"])
                    write_json(execution_dir / "ablation.json", result)
                if result["stop_reason"] is not None:
                    break
    except (OSError, ValueError, TypeError, KeyError, LLMError, BudgetExceeded) as error:
        result["stop_reason"] = str(error) if isinstance(error, F1Refused) else type(error).__name__
    finally:
        runtime_path = execution_dir / "runtime/runtime.json"
        if runtime_path.exists():
            runtime = read_json(runtime_path, max_bytes=MAX_JSON)
            usage = runtime.get("usage") or {}
            result["known_cost_usd"] = usage.get("known_cost_usd")
            result["total_cost_usd"] = (
                usage.get("total_cost_usd") if usage.get("complete") is True else None
            )
            result["runtime_cleanup_errors"] = runtime.get("cleanup_errors", [])
            if runtime.get("cleanup_errors"):
                result["stop_reason"] = result["stop_reason"] or "RUNTIME_CLEANUP_INCOMPLETE"
        result["completed_all_requests"] = result["stop_reason"] is None and all(
            r.get("call_count") == 1 and r["dispatched"] is True for r in result["rows"]
        )
        total = result["total_cost_usd"]
        result["within_budget"] = money(total) <= cap if total is not None else None
        result["study_complete_within_budget"] = (
            result["completed_all_requests"] and result["within_budget"] is True
        )
        result["conditions"] = summarize(result["rows"])
        write_json(execution_dir / "ablation.json", result)
    return result
