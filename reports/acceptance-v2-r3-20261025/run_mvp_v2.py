"""One versioned nine-case strict campaign; gift-only shared reservations remain authoritative."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import stat
import subprocess
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/acceptance-v2-r3-20261025"
DRIVER = OUT / "run_mvp_v2.py"
CAP = OUT / "cap-review.json"
REVIEW = OUT / "root-review.json"
MANIFEST = "eval/mvp_phase1_v2.yaml"
PROFILE = ".cache/tokenfactory-runtime-v2-r2.json"
PROFILE_SHA = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"
POOL = Decimal("14.17775754")
DAILY_POOL = Decimal("9.99964904")
BUDGET_HELPER = OUT / "ledger_state_r2.py"
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
budget_spec = importlib.util.spec_from_file_location("reviewed_r3_budget", BUDGET_HELPER)
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


def capability():
    from headroom.runtime import read_live_profile

    require(sha(PROFILE) == PROFILE_SHA, "runtime profile changed")
    require(stat.S_IMODE((ROOT / PROFILE).stat().st_mode) == 0o600, "profile permissions")
    p = read_live_profile(ROOT / PROFILE)
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
        "path": "reports/acceptance-v2-r3-20261025/catalogue/report.json",
        "sha256": sha(OUT / "catalogue/report.json"),
        "verified": verified,
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
            "user_instruction": "那前两项就按你建议的方案改，保留历史结果和6/9门槛。nanoGPT和s7继续调研修复，只用现有赠送额度，不充值、不超额，继续把剩下的开发和验收做完。",
            "gift_only": True,
            "recharge": False,
            "new_budget_pool": False,
            "zero_sum_partition_transfer": True,
            "historical_iterations_preserved": True,
            "fixed_primary_denominator": 9,
            "minimum_target_met": 6,
        },
        "profile_sha256": PROFILE_SHA,
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
    _cap, ids = verify_cap()
    quality = old.verify_quality(quality_path)
    cal = calibration()
    checkpoint = checkpoint_qualification()
    value = {
        "reviewed_by": "root",
        "purpose": "mvp_v2_repair_round_3_strict_nine_case",
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
    with (ROOT / ".cache/setup/mvp-v2-repair-r3-strict.lock").open("a") as lock:
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
            PROFILE,
        ]
        save(
            OUT / "preflight.json",
            {
                "started_utc": datetime.now(UTC).isoformat(),
                "source_commit": head,
                "argv": argv,
                "review_sha256": expected_review_sha,
                "budget_before": budget,
                "scenario_ids": ids,
                "fixed_acceptance_denominator": 9,
                "per_case_wall_seconds": 480,
                "max_rounds": 6,
                "historical_results_preserved": True,
                "quality_early_stop": False,
                "recharge": False,
            },
        )
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
