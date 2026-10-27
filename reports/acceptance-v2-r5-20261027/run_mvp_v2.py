"""One versioned nine-case strict campaign; gift-only shared reservations remain authoritative."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
import types
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/acceptance-v2-r5-20261027"
DRIVER = OUT / "run_mvp_v2.py"
CAP = OUT / "cap-review.json"
REVIEW = OUT / "root-review.json"
MANIFEST = "eval/mvp_phase1_v2.yaml"
PROFILE = ".cache/tokenfactory-runtime-v2-r2.json"
PROFILE_SHA = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"

# PENDING is intentional. Root must freeze real probe/transition artifacts before
# promotion. PROFILE/PROFILE_SHA above remain the immutable R2 funding anchor.
ACTIVE_PROFILE = ".cache/tokenfactory-runtime-v2-r5.json"
ACTIVE_PROFILE_SHA = "e115c2ff818c8a87853771742deff65dbba1f3a944ff6eae7636bf617bc7149e"
FINANCE_HELPER = "reports/acceptance-v2-r5-20261027/finance_chain.py"
FINANCE_HELPER_SHA = "e9219dbfdce76019a153fff41e71beb522056734e3ebf398a5a473f027ebd660"
FINANCE_INPUTS_HELPER = "reports/acceptance-v2-r5-20261027/finance_inputs.py"
FINANCE_INPUTS_HELPER_SHA = "1d7a8df00d791be52e96e20b44a08709df9f47ac43390d0b0682f6daf4962219"
TRANSITION_HELPER = "reports/acceptance-v2-r5-20261027/profile_transition.py"
TRANSITION_HELPER_SHA = "8bbc7d4a3be760a015b8571167ba1ebba97d609ff35d2802ffd6e4ac9e2b2ac4"
PROFILE_TRANSITION = "reports/acceptance-v2-r5-20261027/profile-transition.json"
PROFILE_TRANSITION_SHA = "087794985621e7cea3a70d5f3f2bfb6797578cc8625d9b3c25849e44c3d99b93"
R4_AFTER_PIN = [
    ".cache/r5-low-effort-finance-20261027/ledger-before.json",
    "ce620d98b05d4532e5a27a93e1421b7f3be5caded08bccb3cf0092166a34d30f",
]
PROBE_ARTIFACT_PINS = {
    "before": [
        ".cache/r5-low-effort-finance-20261027/ledger-before.json",
        "ce620d98b05d4532e5a27a93e1421b7f3be5caded08bccb3cf0092166a34d30f",
    ],
    "after": [
        ".cache/r5-low-effort-finance-20261027/ledger-after.json",
        "5f4aa1851586f239dc34f105b38ff2e190a1b0bed1df1ac1b2647ad78b6a8f58",
    ],
    "calls": [
        ".cache/r5-low-effort-finance-20261027/calls.json",
        "c6fd6b7037551dc1e5d88f9921238f89a84333224249d0e503fe0c73bdbf63d8",
    ],
    "probe_receipt": [
        "reports/acceptance-v2-r5-20261027/super-low-effort-probe.json",
        "d5363e9d8f02c0eda9afede433b5edce6194889dde1ee8ed1132711d94de159c",
    ],
    "request_payload": [
        ".cache/r5-low-effort-finance-20261027/request-payload.json",
        "a50922b4ef437053406a6545ea994c00c286b8767457891238232f96bc28c7c9",
    ],
}
# The reviewed prepared request and root-freeze authorization are independent of
# the eventual probe receipt. Never replace this anchor with the receipt's hash.
PREPARED_REQUEST_SHA = "fe36ea49b7e5c39cd0a5b30c418113f2076c641480d0648cf5ccde5c97eda25e"
PROBE_AUTHORIZATION_ARTIFACT_PINS = {
    "prepared": [
        ".cache/r5-low-effort-probe-20261027/prepared.json",
        "6284ef2030d3b802e2368162dd9ab7b8896f665200ba4ed01e88927cce30a028",
    ],
    "freeze": [
        ".cache/r5-low-effort-probe-20261027/root-freeze.json",
        "30e042dffb32e7890defc919f301d92350deb5efbf8ab279f68598c7fce88de8",
    ],
}

POOL = Decimal("14.17775754")
DAILY_POOL = Decimal("9.99964904")
BUDGET_HELPER = ROOT / "reports/acceptance-v2-r4-20261027/ledger_state_r2.py"
BUDGET_HELPER_SHA = "b27d8c04117502b65c7be0501cdd86208bb17d50b7ee2c668ed161a130baff6f"
FUNDING = ROOT / "reports/acceptance-v2-r2-20261025/funding-transition.json"
FUNDING_SHA = "cc31a24d0a6cdc91413b4521ef0d8b1f86a04e76ceb32fed3081d0998348784d"
spec = importlib.util.spec_from_file_location(
    "historical_budget_primitives", ROOT / ".cache/setup/run_mvp_v7.py"
)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
require, sha, read, save = old.require, old.sha, old.read, old.save

require(sha(BUDGET_HELPER) == BUDGET_HELPER_SHA, "budget partition helper drift")
budget_spec = importlib.util.spec_from_file_location("reviewed_r5_budget", BUDGET_HELPER)
budget_partition = importlib.util.module_from_spec(budget_spec)
budget_spec.loader.exec_module(budget_partition)


def ledger_state(cap):
    require(budget_partition.LIFETIME_POOL == POOL, "lifetime partition drift")
    require(budget_partition.DAILY_POOL == DAILY_POOL, "daily partition drift")
    return budget_partition.ledger_state(old, cap)


def funding():
    require(sha(FUNDING) == FUNDING_SHA, "funding transition drift")
    value = read(FUNDING)
    require(value["status"] == "external_allocation_closed", "external allocation not closed")
    require(Decimal(value["total_work_net_usd"]) == Decimal(16), "total funding changed")
    require(Decimal(value["runtime_lifetime_net_usd"]) == POOL, "runtime partition drift")
    require(Decimal(value["runtime_daily_net_usd"]) == DAILY_POOL, "daily cap drift")
    require(
        Decimal(value["external_retained_net_usd"]) + POOL == Decimal(16),
        "funding does not conserve original total",
    )
    require(Decimal(value["external_future_net_usd"]) == 0, "external allowance remains spendable")
    require(
        Decimal(value["judging_reserve_gross_usd"]) == Decimal(10)
        and Decimal(value["fee_rounding_reserve_gross_usd"]) == Decimal("0.89"),
        "preserved reserve changed",
    )
    require(value["new_money"] is False and value["recharge"] is False, "unapproved funding")
    require(
        sha(value["old_allocation_path"]) == value["old_allocation_sha256"],
        "historical allocation drift",
    )
    require(
        sha(value["old_profile_path"]) == value["old_profile_sha256"], "historical profile drift"
    )
    require(
        sha(value["retirement_receipt_path"]) == value["retirement_receipt_sha256"],
        "retirement receipt drift",
    )
    retirement = read(value["retirement_receipt_path"])
    require(
        retirement["status"] == "closed" and retirement["active_external_allowance_usd"] == "0",
        "probe closure unavailable",
    )
    for record in retirement["entrypoints"]:
        require(sha(record["path"]) == record["closed_sha256"], "standalone probe entry reopened")
        if record.get("archived_path"):
            require(
                sha(record["archived_path"]) == record["original_sha256"],
                "historical probe source not preserved",
            )
    return {"path": str(FUNDING.relative_to(ROOT)), "sha256": sha(FUNDING), "zero_sum": True}


def _frozen_sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read_pinned(path, expected):
    """Bounded project-relative no-follow reads, before importing reviewed helpers."""
    require(_frozen_sha(expected), "externally reviewed SHA required; PENDING refuses")
    require(type(path) is str, "relative artifact path required")
    relative = Path(path)
    require(
        not relative.is_absolute()
        and relative.parts
        and all(part not in ("", ".", "..") for part in relative.parts)
        and str(relative) == path,
        "artifact must be canonical and contained in project",
    )
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in relative.parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(leaf)
            require(
                stat.S_ISREG(info.st_mode) and info.st_size <= 4 * 1024 * 1024,
                "bounded regular artifact required",
            )
            chunks, total = [], 0
            while True:
                block = os.read(leaf, min(65536, 4 * 1024 * 1024 + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                require(total <= 4 * 1024 * 1024, "artifact grew beyond bound")
            raw = b"".join(chunks)
        finally:
            os.close(leaf)
    finally:
        os.close(fd)
    require(hashlib.sha256(raw).hexdigest() == expected, "frozen artifact bytes changed")
    return raw


def _load_pinned_module(name, path, expected):
    """One finance_chain instance is mandatory for the verifier's private seal."""
    raw = _read_pinned(path, expected)
    filename = str(ROOT / path)
    prior = sys.modules.get(name)
    if prior is not None:
        require(
            getattr(prior, "__file__", None) == filename
            and getattr(prior, "_reviewed_source_sha256", None) == expected,
            "module identity collision",
        )
        return prior
    module = types.ModuleType(name)
    module.__file__ = filename
    module.__package__ = ""
    module._reviewed_source_sha256 = expected
    sys.modules[name] = module
    try:
        exec(compile(raw, filename, "exec"), module.__dict__)  # noqa: S102 - execute only pinned helper bytes
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _reviewed_dynamic_pins():
    pins = {
        "r4_after": R4_AFTER_PIN[1],
        "probe_before": PROBE_ARTIFACT_PINS["before"][1],
        "probe_after": PROBE_ARTIFACT_PINS["after"][1],
        "probe_calls": PROBE_ARTIFACT_PINS["calls"][1],
        "probe_receipt": PROBE_ARTIFACT_PINS["probe_receipt"][1],
        "profile_transition": PROFILE_TRANSITION_SHA,
        "new_profile": ACTIVE_PROFILE_SHA,
        # No self-referential hashes: root-review seals cap; preflight seals the
        # explicit review SHA. Final independent audit freezes both actual files.
        "r5_cap": "PENDING",
        "r5_preflight": "PENDING",
    }
    require(
        all(_frozen_sha(pins[k]) for k in pins if not k.startswith("r5_")),
        "probe and profile pins must be frozen before cap preparation",
    )
    return pins


def active_profile_binding():
    """Rebuild sealed R4 -> probe -> profile proof; never deserialize a seal."""
    from headroom.runtime import read_live_profile

    funding()  # Keep the original monetary authorization verification intact.
    dynamic_pins = _reviewed_dynamic_pins()
    for path, expected in PROBE_AUTHORIZATION_ARTIFACT_PINS.values():
        _read_pinned(path, expected)
    finance = _load_pinned_module("finance_chain", FINANCE_HELPER, FINANCE_HELPER_SHA)
    adapter = _load_pinned_module(
        "finance_inputs", FINANCE_INPUTS_HELPER, FINANCE_INPUTS_HELPER_SHA
    )
    transition = _load_pinned_module("profile_transition", TRANSITION_HELPER, TRANSITION_HELPER_SHA)
    require(adapter.finance is finance, "finance adapter must share sealed verifier identity")
    artifact_pins = {k: adapter.ArtifactPin(*v) for k, v in PROBE_ARTIFACT_PINS.items()}
    # Explicit frozen adapter interface; no compatibility fallback is permitted.
    proof, inventory = adapter.verify_frozen_root_and_probe(
        r4_after_pin=adapter.ArtifactPin(*R4_AFTER_PIN),
        probe_artifact_pins=artifact_pins,
        dynamic_pins=dynamic_pins,
        authorization_artifact_pins={
            k: adapter.ArtifactPin(*v) for k, v in PROBE_AUTHORIZATION_ARTIFACT_PINS.items()
        },
        expected_request_sha256=PREPARED_REQUEST_SHA,
    )
    require(
        proof["accepted"] is True and proof["dispatch_permitted"] is False,
        "independent sealed root and probe validation required",
    )
    require(
        finance.is_verified_probe_finance(proof["probe_finance"]),
        "serialized/foreign probe proof is forbidden",
    )
    transition_proof = transition.verify_transition(
        ROOT,
        transition.TransitionPins(
            transition_receipt_path=PROFILE_TRANSITION,
            transition_receipt_sha256=PROFILE_TRANSITION_SHA,
            new_profile_path=ACTIVE_PROFILE,
            new_profile_sha256=ACTIVE_PROFILE_SHA,
            funding_transition_path=str(FUNDING.relative_to(ROOT)),
            funding_transition_sha256=FUNDING_SHA,
            low_effort_probe_receipt_path=PROBE_ARTIFACT_PINS["probe_receipt"][0],
            low_effort_probe_receipt_sha256=PROBE_ARTIFACT_PINS["probe_receipt"][1],
        ),
        probe_finance=proof["probe_finance"],
    )
    require(transition_proof["valid"] is True, "complete nonfinancial transition required")
    _read_pinned(PROFILE, PROFILE_SHA)
    _read_pinned(ACTIVE_PROFILE, ACTIVE_PROFILE_SHA)
    require(
        stat.S_IMODE((ROOT / ACTIVE_PROFILE).stat().st_mode) == 0o600, "active profile permissions"
    )
    profile = read_live_profile(ROOT / ACTIVE_PROFILE)
    _read_pinned(ACTIVE_PROFILE, ACTIVE_PROFILE_SHA)
    adapter.verify_inputs_still_pinned(inventory)
    public = {
        "base_funding_profile_sha256": PROFILE_SHA,
        "active_profile_path": ACTIVE_PROFILE,
        "active_profile_sha256": ACTIVE_PROFILE_SHA,
        "profile_transition": transition_proof,
        "probe_finance": finance.public_probe_finance(proof["probe_finance"]),
        "finance_helpers": {
            FINANCE_HELPER: FINANCE_HELPER_SHA,
            FINANCE_INPUTS_HELPER: FINANCE_INPUTS_HELPER_SHA,
            TRANSITION_HELPER: TRANSITION_HELPER_SHA,
        },
        "input_file_hashes": inventory,
        "funding_chain_verified": True,
        "active_profile_runtime_verified": True,
    }
    return profile, public, finance, adapter, inventory


def capability():
    require(sha(PROFILE) == PROFILE_SHA, "funding profile changed")
    require(stat.S_IMODE((ROOT / PROFILE).stat().st_mode) == 0o600, "profile permissions")
    p, runtime_binding, _finance, _adapter, _inventory = active_profile_binding()
    require(
        p.run_budget_mode == "actual_usage" and Decimal(p.authorized_total_usd) == POOL,
        "reviewed zero-sum lifetime partition required",
    )
    catalogue = read(OUT / "catalogue/report.json")
    require(
        catalogue["status"] == "complete" and catalogue["inference_requests"] == 0,
        "fresh directory required",
    )
    require(len(catalogue["catalogues"]) == 2, "both official directories required")
    verified = []
    for endpoint in catalogue["catalogues"]:
        require(
            endpoint["http_status"] == 200 and endpoint["catalogue_available"],
            "directory unavailable",
        )
        rows = {row["id"]: row for row in endpoint["models"]}
        for role, model in p.models.items():
            row = rows[model.model_id]["advertised_metadata"]
            price = row["pricing"]
            require(
                Decimal(price["prompt"]) * 1000000 == Decimal(model.input_usd_per_million),
                "input price changed",
            )
            require(
                Decimal(price["completion"]) * 1000000 == Decimal(model.output_usd_per_million),
                "output price changed",
            )
            require(
                row["context_length"] == model.billing.prompt_token_ceiling, "context bound changed"
            )
            for key in ("image", "price_per_video_second", "request", "price_per_minute"):
                require(Decimal(price[key]) == 0, "non-token price changed")
            cache = price.get("input_cache_read")
            if cache is not None:
                require(
                    Decimal(cache) * 1000000 == Decimal(model.cached_input_usd_per_million),
                    "cache price changed",
                )
            else:
                require(role == "nano", "unexpected absent cache price")
            verified.append(
                {
                    "endpoint": endpoint["endpoint"],
                    "role": role,
                    "model": model.model_id,
                    "context_tokens": row["context_length"],
                    "input_usd_per_million": str(model.input_usd_per_million),
                    "output_usd_per_million": str(model.output_usd_per_million),
                    "cached_price_basis": "catalogue"
                    if cache is not None
                    else "retained authenticated account price observation",
                    "prompt_upper_bound_unchanged": True,
                }
            )
    return {
        "path": "reports/acceptance-v2-r5-20261027/catalogue/report.json",
        "sha256": sha(OUT / "catalogue/report.json"),
        "verified": verified,
        "runtime_profile_binding": runtime_binding,
    }


def prepare_cap():
    catalogue = capability()
    runs, attempts = old.ledger_rows()
    total = sum((old.money(row["charged_usd"]) for row in attempts), Decimal(0))
    known = sum(
        (old.money(row["actual_usd"]) for row in attempts if row["actual_usd"] is not None),
        Decimal(0),
    )
    cap = {
        "authorization": {
            "user_instruction": "那个计费异常你先排查解决一下，然后继续修剩下没通过的场景，重点把自动修复从3/9做到至少6/9。还是只用现有赠送额度，不充值、不超额。",
            "gift_only": True,
            "recharge": False,
            "new_budget_pool": False,
            "zero_sum_partition_transfer": True,
            "historical_iterations_preserved": True,
            "fixed_primary_denominator": 9,
            "minimum_target_met": 6,
        },
        "profile_sha256": PROFILE_SHA,
        "active_profile_path": ACTIVE_PROFILE,
        "active_profile_sha256": ACTIVE_PROFILE_SHA,
        "funding": funding(),
        "budget_helper_sha256": BUDGET_HELPER_SHA,
        "daily_pool_usd": str(DAILY_POOL),
        "catalogue": catalogue,
        "ledger": {
            "projection_sha256": old.sha_bytes(old.canonical({"runs": runs, "attempts": attempts})),
            "runs": len(runs),
            "attempts": len(attempts),
            "conservative_charged_usd": str(total),
            "known_actual_subtotal_usd": str(known),
        },
        "historical_driver_sha256": sha(".cache/setup/run_mvp_v7.py"),
        "old_manifest_sha256": old.MANIFEST_SHA,
        "pool_usd": str(POOL),
        "per_case_stop_usd": "0.6",
        "campaign_max_usd": "5.4",
        "unknown_costs_retain_verified_bounds": True,
        "no_history_exclusions": True,
    }
    cap["budget_at_review"] = ledger_state(cap)
    save(CAP, cap)
    print(json.dumps({"prepared": str(CAP.relative_to(ROOT)), "budget": cap["budget_at_review"]}))


def verify_cap():
    cap = read(CAP)
    require(cap["funding"] == funding(), "funding qualification drift")
    require(
        cap["budget_helper_sha256"] == sha(BUDGET_HELPER) == BUDGET_HELPER_SHA,
        "budget helper drift",
    )
    require(Decimal(cap["daily_pool_usd"]) == DAILY_POOL, "daily allocation changed")
    require(cap["profile_sha256"] == sha(PROFILE) == PROFILE_SHA, "profile drift")
    require(
        cap["active_profile_path"] == ACTIVE_PROFILE
        and cap["active_profile_sha256"] == ACTIVE_PROFILE_SHA,
        "active capability profile drift",
    )
    require(
        cap["historical_driver_sha256"] == sha(".cache/setup/run_mvp_v7.py"),
        "budget primitives changed",
    )
    require(
        cap["old_manifest_sha256"] == sha("eval/mvp_phase1.yaml") == old.MANIFEST_SHA,
        "old manifest drift",
    )
    require(sha("docs/PLAN.md") == old.PLAN_SHA, "canonical plan drift")
    require(cap["catalogue"] == capability(), "fresh catalogue or price bindings drift")
    require(
        Decimal(cap["pool_usd"]) == POOL
        and cap["authorization"]["gift_only"]
        and not cap["authorization"]["recharge"]
        and not cap["authorization"]["new_budget_pool"],
        "funding authorization",
    )
    manifest = read(MANIFEST)
    require(len(manifest["scenarios"]) == 9, "exactly nine cases required")
    original_ids = [r["id"] for r in read("eval/mvp_phase1.yaml")["scenarios"]]
    ids = [r["id"] for r in manifest["scenarios"]]
    require(
        [("s2_fp32_adamw_1b" if x == "s2_capacity_v2" else x) for x in ids] == original_ids,
        "only approved s2 slot may change",
    )
    for row in manifest["scenarios"]:
        require(sha(row["script"]) == row["source_sha256"], "scenario source drift")
    return cap, ids


def calibration():
    from headroom.acceptance.s2_calibration_audit import audit_calibration

    value = audit_calibration(Path(MANIFEST), Path("reports/s2-calibration-v2-20261025-c"))
    require(value.get("accepted") is True, "s2 calibration not accepted")
    return value


def checkpoint_qualification():
    """Bind manual resource evidence; it cannot certify pairing or model success."""
    from headroom.acceptance.common import file_record, read_json
    from headroom.evidence_analysis import analyze_snapshot
    from headroom.lab.snapshot_codec import MAX_SNAPSHOT_BYTES, read_snapshot_artifact
    from headroom.verify.precision import observed_precision

    directory = ROOT / "runs/research/s1-checkpoint-reference-20261025-v3"
    plan_path = directory / "plan.json"
    receipt_path = directory / "calibration.json"
    plan, receipt = read_json(plan_path), read_json(receipt_path)
    required_sources = {
        "headroom/lab/precision.py",
        "headroom/lab/snapshot_codec.py",
        "headroom/evidence_analysis.py",
        "headroom/verify/checkpoint.py",
        "headroom/verify/pairing.py",
        "headroom/verify/precision.py",
        "headroom/lab/runner.py",
        "headroom/lab/run_target.py",
        "headroom/lab/hooks.py",
        "scripts/research_checkpoint_reference.py",
    }
    required_checks = {
        "completed_20_logical_updates",
        "capture_complete",
        "cleanup_verified",
        "exclusive_cuda_observed",
        "measured_cuda_peak",
        "within_480_wall_seconds",
        "actual_fp32",
        "finite_20_backward_scalars",
        "reviewed_runtime_and_image",
        "actual_source_argv_transformation",
        "actual_pairing_capture_complete",
        "source_unchanged",
        "snapshot_analysis_at_original_limit",
    }
    require(
        plan["kind"] == receipt["kind"] == "manual_checkpoint_reference_resource_feasibility"
        and type(plan["maximum_gpu_runs"]) is int
        and plan["maximum_gpu_runs"] == 1
        and plan["counts_toward_model_acceptance"] is False
        and receipt["counts_toward_model_acceptance"] is False
        and plan["runs_original_baseline"] is False
        and plan["runs_model"] is False
        and plan["required_logical_updates"] == 20
        and plan["required_precision"] == "fp32"
        and plan["snapshot_reader_limit_bytes"] == MAX_SNAPSHOT_BYTES,
        "checkpoint resource control identity",
    )
    require(
        receipt["resource_feasible"] is True
        and set(receipt["resource_checks"]) == required_checks
        and all(value is True for value in receipt["resource_checks"].values())
        and receipt["snapshot_reader"]["readable"] is True
        and receipt["snapshot_reader"]["limit_bytes"] == MAX_SNAPSHOT_BYTES
        and receipt["original_baseline_pairing_proven"] is False
        and receipt["candidate_run_present"] is False,
        "checkpoint resource/precision/snapshot qualification failed",
    )
    source_hashes = plan["measurement_source_hashes"]
    require(
        isinstance(source_hashes, dict)
        and set(source_hashes) == required_sources
        and all(sha(name) == digest for name, digest in source_hashes.items()),
        "checkpoint qualification source scope or hashes changed",
    )

    def artifact_path(value):
        path = Path(value)
        path = path if path.is_absolute() else ROOT / path
        require(not path.is_symlink(), "checkpoint artifact cannot be a symlink")
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(ROOT.resolve()), "checkpoint artifact outside project")
        return resolved

    def record(value, limit=2 * 1024**2):
        path = artifact_path(value)
        return {"path": str(path.relative_to(ROOT)), **file_record(path, limit)}

    reference = receipt["reference"]
    run_dir = artifact_path(reference["run_dir"])
    target_dir = artifact_path(reference["target_artifact_dir"])
    require(run_dir.is_relative_to(directory / "runs"), "checkpoint run outside registered control")
    require(target_dir.is_relative_to(run_dir), "checkpoint capture outside its run")
    result_path = run_dir / "result.json"
    manifest_path = run_dir / "manifest.json"
    raw_reference = read_json(result_path)
    require(raw_reference == reference, "checkpoint receipt no longer matches saved result")
    require(
        reference["status"] == "completed"
        and reference["steps"] == 20
        and reference["capture_complete"] is True
        and reference["cleanup_verified"] is True
        and observed_precision(reference) == "fp32",
        "checkpoint resource capture incomplete",
    )
    transformation = plan["transformation"]
    scenario = next(row for row in read(MANIFEST)["scenarios"] if row["id"] == "s1_batch_too_big")
    original_source = artifact_path(plan["original_script"])
    reference_source = artifact_path(plan["reference_script"])
    baseline_result = artifact_path(plan["baseline_result"])
    require(
        artifact_path(scenario["script"]) == original_source
        and reference_source == directory / "reference-source/train.py"
        and baseline_result.is_relative_to(ROOT / "runs/evaluation")
        and baseline_result.name == "result.json"
        and scenario["source_sha256"] == transformation["original_source_sha256"]
        and scenario["numerical_reference"]["strategy"] == "original_workload_checkpoint",
        "checkpoint qualification belongs to another scenario/reference",
    )
    require(
        sha(original_source) == transformation["original_source_sha256"]
        and sha(reference_source) == transformation["transformed_source_sha256"]
        and sha(baseline_result) == plan["baseline_result_sha256"],
        "checkpoint source or historical baseline evidence changed",
    )
    snapshot_path = target_dir / "snapshot.json"
    require(
        artifact_path(receipt["snapshot_reader"]["path"]) == snapshot_path,
        "checkpoint snapshot reader path mismatch",
    )
    artifacts = {
        "original_source": record(plan["original_script"]),
        "reference_source": record(plan["reference_script"]),
        "historical_baseline_result": record(plan["baseline_result"]),
        "reference_result": record(result_path),
        "reference_manifest": record(manifest_path),
        "reference_attestation": record(run_dir / "reference-checkpoint.json"),
        "target_result": record(target_dir / "result.json"),
        "snapshot": record(snapshot_path, MAX_SNAPSHOT_BYTES),
    }
    require(
        type(receipt["snapshot_reader"]["actual_bytes"]) is int
        and artifacts["snapshot"]["bytes"] == receipt["snapshot_reader"]["actual_bytes"],
        "checkpoint snapshot actual size changed",
    )
    snapshot = read_snapshot_artifact(snapshot_path, MAX_SNAPSHOT_BYTES)
    analysis = analyze_snapshot(snapshot, reference)
    reader = receipt["snapshot_reader"]
    require(
        isinstance(snapshot, dict)
        and isinstance(snapshot.get("segments"), list)
        and isinstance(snapshot.get("device_traces"), list)
        and bool(snapshot["segments"])
        and any(snapshot["device_traces"])
        and len(snapshot["segments"]) == reader["segments"]
        and sum(len(events) for events in snapshot["device_traces"])
        == reader["device_trace_events"]
        and sorted(analysis) == reader["analysis_keys"]
        and analysis.get("metrics", {}) == reader["metrics"],
        "checkpoint snapshot no longer passes original analysis",
    )
    require(
        record(snapshot_path, MAX_SNAPSHOT_BYTES) == artifacts["snapshot"],
        "checkpoint snapshot changed during qualification",
    )
    return {
        "plan": str(plan_path.relative_to(ROOT)),
        "plan_sha256": sha(plan_path),
        "receipt": str(receipt_path.relative_to(ROOT)),
        "receipt_sha256": sha(receipt_path),
        "artifacts": artifacts,
        "measurement_source_hashes": source_hashes,
        "resource_feasible": True,
        "counts_toward_model_acceptance": False,
        "historical_baseline_pairing_proven": False,
        "fresh_formal_baseline_pairing_still_required": True,
    }


def freeze(quality_path):
    cap, ids = verify_cap()
    quality = old.verify_quality(quality_path)
    cal = calibration()
    checkpoint = checkpoint_qualification()
    value = {
        "reviewed_by": "root",
        "purpose": "mvp_v2_repair_round_5_strict_nine_case",
        "runtime_profile_binding": cap["catalogue"]["runtime_profile_binding"],
        "source_pins": old.inventory(),
        "driver_sha256": sha(DRIVER),
        "cap_sha256": sha(CAP),
        "manifest_sha256": sha(MANIFEST),
        "quality_receipt": quality,
        "calibration": cal,
        "checkpoint_qualification": checkpoint,
        "scenario_ids": ids,
        "max_rounds": 6,
        "per_case_wall_seconds": 480,
        "fixed_acceptance_denominator": 9,
        "minimum_target_met": 6,
        "human_controls_in_model_inputs": False,
        "human_controls_counted_as_model_success": False,
    }
    save(REVIEW, value)
    print(json.dumps({"root_review": str(REVIEW.relative_to(ROOT)), "sha256": sha(REVIEW)}))


def execute(expected_review_sha):
    with (ROOT / ".cache/setup/mvp-v2-repair-r5-strict.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ("preflight.json", "execution.log", "execution.json"):
            require(not (OUT / name).exists(), "version already dispatched; no overwrite/retry")
        require(sha(REVIEW) == expected_review_sha, "explicit review bytes required")
        review = read(REVIEW)
        require(
            review["driver_sha256"] == sha(DRIVER) and review["cap_sha256"] == sha(CAP),
            "review drift",
        )
        require(review["source_pins"] == old.inventory(), "source drift")
        require(review["manifest_sha256"] == sha(MANIFEST), "manifest drift")
        require(
            old.verify_quality(review["quality_receipt"]["path"]) == review["quality_receipt"],
            "Full quality artifacts changed after freeze",
        )
        require(not old.git("status", "--porcelain"), "clean committed checkout required")
        head = old.git("rev-parse", "HEAD")
        require(head == old.git("rev-parse", "origin/main"), "pushed reviewed commit required")
        cap, ids = verify_cap()
        require(
            review["runtime_profile_binding"] == cap["catalogue"]["runtime_profile_binding"],
            "root review active capability chain drift",
        )
        require(
            calibration() == review["calibration"],
            "Calibration artifacts changed after freeze",
        )
        require(
            checkpoint_qualification() == review["checkpoint_qualification"],
            "Checkpoint resource artifacts changed after freeze",
        )
        budget = ledger_state(cap)
        apps = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        require(not apps, "GPU busy; never stop foreign processes")
        argv = [
            "uv",
            "run",
            "--offline",
            "--no-sync",
            "headroom",
            "eval",
            "--manifest",
            MANIFEST,
            "--live",
            "--conditions",
            "full_ultra",
            "--policies",
            "strict",
            "--search-mode",
            "until_target",
            "--budget",
            "0.6",
            "--campaign-budget",
            budget["effective_campaign_usd"],
            "--daily-budget",
            str(DAILY_POOL),
            "--runtime-profile",
            ACTIVE_PROFILE,
        ]
        preflight = {
            "started_utc": datetime.now(UTC).isoformat(),
            "source_commit": head,
            "argv": argv,
            "review_sha256": expected_review_sha,
            "base_funding_profile_sha256": PROFILE_SHA,
            "active_profile_path": ACTIVE_PROFILE,
            "active_profile_sha256": ACTIVE_PROFILE_SHA,
            "budget_before": budget,
            "scenario_ids": ids,
            "fixed_acceptance_denominator": 9,
            "per_case_wall_seconds": 480,
            "max_rounds": 6,
            "historical_results_preserved": True,
            "quality_early_stop": False,
            "recharge": False,
        }
        _profile, binding, finance, adapter, inventory = active_profile_binding()
        require(binding == review["runtime_profile_binding"], "dispatch capability chain drift")
        after_raw = _read_pinned(*PROBE_ARTIFACT_PINS["after"])
        financial_dispatch = finance.verify_r5_dispatch(
            after_raw,
            cap,
            preflight,
            active_profile_path=ACTIVE_PROFILE,
            active_profile_sha256=ACTIVE_PROFILE_SHA,
        )
        require(financial_dispatch["accepted"] is True, "full-history dispatch gate failed")
        adapter.verify_inputs_still_pinned(inventory)
        require(ledger_state(cap) == budget, "ledger changed during final qualification")
        preflight["financial_dispatch"] = financial_dispatch
        save(OUT / "preflight.json", preflight)
        before = set((ROOT / "runs/evaluation/live").glob("*/campaign.json"))
        started = time.monotonic()
        with (OUT / "execution.log").open("x") as handle:
            child = subprocess.Popen(argv, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            print(
                json.dumps(
                    {
                        "pid": child.pid,
                        "source_commit": head,
                        "log": str((OUT / "execution.log").relative_to(ROOT)),
                    }
                ),
                flush=True,
            )
            code = child.wait()
        campaigns = []
        for p in sorted(set((ROOT / "runs/evaluation/live").glob("*/campaign.json")) - before):
            value = read(p)
            rows = value.get("rows", [])
            campaigns.append(
                {
                    "path": str(p.relative_to(ROOT)),
                    "sha256": sha(p),
                    "status": value.get("status"),
                    "halt_reason": value.get("halt_reason"),
                    "summary": value.get("summary"),
                    "exact_nine_rows": [r.get("scenario_id") for r in rows] == ids,
                    "all_nine_have_run_ids": len(rows) == 9 and all(r.get("run_id") for r in rows),
                }
            )
        result = {
            "exit_code": code,
            "elapsed_seconds": time.monotonic() - started,
            "campaigns": campaigns,
            "completed_utc": datetime.now(UTC).isoformat(),
            "fixed_acceptance_denominator": 9,
            "not_an_independent_acceptance_audit": True,
            "pending_cases_remain_unknown": True,
            "no_automatic_rerun": True,
        }
        save(OUT / "execution.json", result)
        print(json.dumps(result), flush=True)
        return code


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-cap", action="store_true")
    modes.add_argument("--freeze-quality")
    modes.add_argument("--execute-review-sha256")
    args = parser.parse_args()
    if args.prepare_cap:
        prepare_cap()
    elif args.freeze_quality:
        freeze(args.freeze_quality)
    else:
        return execute(args.execute_review_sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
