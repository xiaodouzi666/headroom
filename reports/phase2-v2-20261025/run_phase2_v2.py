"""Prepare one Phase 2 matrix; only explicit future freeze/execute modes spend.

Default planning and self-test do not read credentials, the profile or live ledger.
The $12 campaign ceiling is NOT a new pool: all calls retain the same cumulative
$9.99964904 authorization and full provider-bound reservation.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/phase2-v2-20261025"
DRIVER = OUT / "run_phase2_v2.py"
CAP = OUT / "cap-review.json"
REVIEW = OUT / "root-review.json"
PROTOCOL = "eval/protocol_v2.json"
MANIFEST = "eval/scenario_set_v2.yaml"
POOL = Decimal("9.99964904")
CAMPAIGN_MAX = Decimal(12)
PER_RUN = Decimal("0.6")
POLICIES = ("strict", "allow_precision")
IDS = (
    "s1_batch_too_big",
    "s2_capacity_v2",
    "s3_eval_no_grad_missing",
    "s4_loss_accumulation_graph",
    "s5_fragmentation_varlen",
    "s6_full_vocab_logits_fp32",
    "s7_frozen_params_optimizer_state",
    "s8_two_models_resident",
    "nanogpt",
    "hf_trainer",
)
HELPERS = {
    ".cache/setup/run_mvp_v7.py": "7fecfdc73a9f5a9f83a6daf422d5d34f5decca4ef89c45c1de670de9898d49b5",
    "reports/acceptance-v2-20261025/run_mvp_v2.py": "4ddb959611048ad44b89ce9a54ee91a0f7680c7f002a0415c5a1d312bad68a97",
}
MVP_AUDITOR_SHA = "09fa339c212966c8a0dca7a619689f6b51e1adedbd063dba73f05aa9a8323129"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def primitives():
    """Import reviewed helpers privately; do not execute their main functions."""
    for name, expected in HELPERS.items():
        require(digest(ROOT / name) == expected, "Reviewed helper changed")
    spec = importlib.util.spec_from_file_location(
        "phase2_mvp_guards", ROOT / "reports/acceptance-v2-20261025/run_mvp_v2.py"
    )
    mvp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mvp)
    require(mvp.POOL == mvp.old.POOL == POOL and mvp.old.PER_RUN == PER_RUN, "Pool drift")
    # This helper instance belongs only to this process. Preserve all ledger logic;
    # replace the obsolete MVP nominal ceiling, never its all-time pool or per-run cap.
    mvp.old.CAMPAIGN_MAX = CAMPAIGN_MAX
    return mvp, mvp.old


def plan():
    from headroom.acceptance.protocol_v2 import protocol_plan
    from headroom.evaluation import campaign_plan
    from headroom.orchestrator import FixRequest

    require(FixRequest.model_fields["max_rounds"].default == 6, "Search bound changed")
    value = protocol_plan(
        ROOT / PROTOCOL,
        scope="phase2_policy_matrix",
        project_root=ROOT,
        per_run_budget_usd=str(PER_RUN),
        campaign_budget_usd=str(CAMPAIGN_MAX),
        daily_budget_usd=str(POOL),
    )
    # protocol_plan validates scope/policy membership; the explicit CLI mode is
    # bounded_pareto even when the shared manifest defaults to until_target.
    value.update(
        campaign_plan(
            ROOT / MANIFEST,
            project_root=ROOT,
            scenario_ids=value["scenarios"],
            conditions=("full_ultra",),
            policy_names=POLICIES,
            search_mode="bounded_pareto",
            per_run_budget_usd=str(PER_RUN),
            campaign_budget_usd=str(CAMPAIGN_MAX),
            daily_budget_usd=str(POOL),
        )
    )
    require(
        value["scenarios"] == list(IDS)
        and [p["name"] for p in value["policies"]] == list(POLICIES)
        and value["search_mode"] == "bounded_pareto"
        and value["planned_pipeline_runs"] == 20
        and value["run_wall_limit_seconds"] == 480,
        "Approved ten-core/two-policy protocol changed",
    )
    value.update(
        fixed_pipeline_denominator=20,
        fixed_per_policy_denominator=10,
        maximum_search_rounds=6,
        combine_policy_successes=False,
        nominal_campaign_ceiling_usd=str(CAMPAIGN_MAX),
        same_cumulative_pool_usd=str(POOL),
        actual_campaign_cap="min(12, remaining_all_time_pool, remaining_utc_day)",
        remaining_unexecuted_slots="unknown; never removed from the denominator",
        cap_frozen=False,
        can_reserve_all_run_caps=None,
        full_reservation_feasibility="unknown until the post-MVP cumulative ledger freeze",
        reads_profile_or_ledger=False,
        mvp_gate_before_freeze="independent fixed-nine audit: targets >= 6 and valid/correct causes >= 6",
        phase1_all_items_certified=False,
    )
    return value


def argv_for(ids, effective):
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
        ",".join(POLICIES),
        "--search-mode",
        "bounded_pareto",
        "--budget",
        str(PER_RUN),
        "--campaign-budget",
        str(effective),
        "--daily-budget",
        str(POOL),
        "--runtime-profile",
        ".cache/tokenfactory-runtime.json",
    ]
    for identifier in ids:
        argv += ["--scenario", identifier]
    return argv


def inventory_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


MVP_TRUTH_GATES = (
    "new_execution_campaign_sha",
    "bound_root_review",
    "cap_unchanged",
    "driver_unchanged",
    "manifest_bound",
    "complete_tested_execution_sources_bound",
    "exact_v2_nine_slots",
    "unique_current_run_ids",
    "fixed_review_denominator",
    "minimum_remains_six",
    "full_quality_passed",
    "campaign_finished_live",
    "strict_full_ultra_only",
    "unchanged_gift_pool",
    "external_retained_debt_preserved",
    "historical_finance_preserved",
    "ledger_stable",
    "store_stable",
    "ledger_clear",
    "pool_not_exceeded",
    "artifact_sources_stable",
    "no_artifact_read_errors",
)
MVP_ROW_TRUTH_GATES = (
    "real_live_provenance",
    "run_identity_consistent",
    "source_hash_matches_manifest",
    "report_json_and_markdown",
    "owned_cleanup_verified",
    "cost_complete_and_consistent",
)


def mvp_pass_line(audit):
    """The original 6/9 pass line; outstanding CLI/item gates stay outstanding."""
    rows = audit.get("rows", [])
    require(
        audit.get("fixed_denominator") == 9
        and type(rows) is list
        and len(rows) == 9
        and [r.get("scenario_id") for r in rows] == list(IDS[:9])
        and len({r.get("run_id") for r in rows}) == 9
        and all(
            type(r.get("run_id")) is str
            and len(r["run_id"]) == 32
            and all(c in "0123456789abcdef" for c in r["run_id"])
            for r in rows
        ),
        "MVP needs nine distinct real scenario rows",
    )
    for key, field in (("targets", "target"), ("valid_correct_first_causes", "cause")):
        count = audit.get("counts", {}).get(key)
        require(
            type(count) is int
            and 6 <= count <= 9
            and count == sum(row.get(field) is True for row in rows),
            "MVP target/valid-first-cause pass line has not been met",
        )
    gates = audit.get("gates", {})
    require(
        all(gates.get(key) is True for key in MVP_TRUTH_GATES),
        "MVP source/financial/provenance evidence is incomplete",
    )
    require(
        all(
            row.get("observed", {}).get("gates", {}).get(key) is True
            for row in rows
            for key in MVP_ROW_TRUTH_GATES
        ),
        "MVP real row source/financial evidence is incomplete",
    )
    return {
        "targets": audit["counts"]["targets"],
        "valid_correct_first_causes": audit["counts"]["valid_correct_first_causes"],
        "fixed_denominator": 9,
        "retained_unpassed_global_gates": {k: v for k, v in gates.items() if v is not True},
        "retained_unpassed_row_gates": [
            {
                "scenario_id": row["scenario_id"],
                "gates": {k: v for k, v in row["observed"]["gates"].items() if v is not True},
            }
            for row in rows
            if any(v is not True for v in row["observed"]["gates"].values())
        ],
        "overall_campaign_all_item_gate": audit.get("accepted_observed_campaign_gates"),
        "phase1_all_items_certified": False,
    }


def mvp_qualification(old, audit_path):
    """Require this version's independently audited MVP gate; never merge old scores."""
    audit_path = old.path(audit_path)
    mvp_out = ROOT / "reports/acceptance-v2-20261025"
    require(audit_path.parent == mvp_out, "MVP audit must belong to the current version")
    audit = old.read(audit_path)
    execution_path = mvp_out / "execution.json"
    execution = old.read(execution_path)
    campaigns = execution.get("campaigns")
    require(
        audit.get("audit_kind") == "independent_v2_mvp_nine"
        and audit.get("audit_source_sha256") == MVP_AUDITOR_SHA
        and digest(mvp_out / "audit_mvp_v2.py") == MVP_AUDITOR_SHA
        and audit.get("fixed_denominator") == 9
        and audit.get("historical_scores_used") is False
        and audit.get("human_controls_counted") is False
        and type(audit.get("counts", {}).get("targets")) is int
        and audit["counts"]["targets"] >= 6
        and type(audit.get("counts", {}).get("valid_correct_first_causes")) is int
        and audit["counts"]["valid_correct_first_causes"] >= 6,
        "Independent fixed-nine MVP acceptance gate has not passed",
    )
    require(
        isinstance(campaigns, list)
        and len(campaigns) == 1
        and campaigns[0].get("status") == "finished"
        and execution.get("completed_utc")
        and audit.get("campaign") == campaigns[0]["path"],
        "MVP execution is incomplete or audit refers to another campaign",
    )
    pass_line = mvp_pass_line(audit)
    records = audit.get("source_hashes", {})
    require(
        old.sha(execution_path) == records.get(str(execution_path.relative_to(ROOT)))
        and old.sha(campaigns[0]["path"])
        == campaigns[0]["sha256"]
        == records.get(campaigns[0]["path"])
        and audit.get("source_binding", {}).get("accepted") is True
        and audit["source_binding"]["inventory_sha256"]["review"]
        == inventory_digest(old.inventory()),
        "MVP execution, campaign or complete audited sources changed",
    )
    return {
        "audit": str(audit_path.relative_to(ROOT)),
        "audit_sha256": old.sha(audit_path),
        "execution_sha256": old.sha(execution_path),
        "campaign": campaigns[0],
        "mvp_fixed_nine_gate_passed": True,
        "mvp_pass_line": pass_line,
        "phase1_all_items_certified": False,
        "remaining_separate_items": audit.get("limitations", []),
    }


def cap_snapshot(old, catalogue):
    """Called only after the MVP gate; all old rows/unknown charges remain included."""
    runs, attempts = old.ledger_rows()
    with localcontext() as context:
        context.prec = 256
        charged = sum((old.money(r["charged_usd"]) for r in attempts), Decimal(0))
        known = sum(
            (old.money(r["actual_usd"]) for r in attempts if r["actual_usd"] is not None),
            Decimal(0),
        )
    cap = {
        "authorization": {"gift_only": True, "recharge": False, "new_budget_pool": False},
        "pool_usd": str(POOL),
        "campaign_max_usd": str(CAMPAIGN_MAX),
        "per_case_stop_usd": str(PER_RUN),
        "catalogue": catalogue,
        "ledger": {
            "projection_sha256": old.sha_bytes(old.canonical({"runs": runs, "attempts": attempts})),
            "runs": len(runs),
            "attempts": len(attempts),
            "conservative_charged_usd": str(charged),
            "known_actual_subtotal_usd": str(known),
        },
        "history_exclusions": [],
        "unknown_costs_retain_verified_bounds": True,
        "full_provider_bound_required_for_every_attempt": True,
    }
    cap["budget_at_review"] = old.ledger_state(cap)
    return cap


def freeze(quality_path, audit_path):
    mvp, old = primitives()
    require(not CAP.exists() and not REVIEW.exists(), "This version was already frozen")
    planned = plan()
    parent = mvp_qualification(old, audit_path)
    quality = old.verify_quality(quality_path)
    cap = cap_snapshot(old, mvp.capability())
    # Resource qualifications remain independent from the model's MVP score.
    resources = {"s2": mvp.calibration(), "s1": mvp.checkpoint_qualification()}
    review = {
        "purpose": "phase2_v2_ten_core_two_policy",
        "source_pins": old.inventory(),
        "driver_sha256": old.sha(DRIVER),
        "helper_sha256": HELPERS,
        "protocol_sha256": old.sha(PROTOCOL),
        "manifest_sha256": old.sha(MANIFEST),
        "quality_receipt": quality,
        "mvp": parent,
        "resource_qualifications": resources,
        "plan": planned,
        "phase1_all_items_certified": False,
    }
    old.ledger_state(cap)  # Fail if any prior row changed during the read-only freeze.
    old.save(CAP, cap)
    review["cap_sha256"] = old.sha(CAP)
    old.save(REVIEW, review)
    return {"review": str(REVIEW.relative_to(ROOT)), "sha256": old.sha(REVIEW)}


def execute(expected_review_sha):
    mvp, old = primitives()
    with (ROOT / ".cache/setup/phase2-v2.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ("preflight.json", "execution.log", "execution.json"):
            require(not (OUT / name).exists(), "Version already dispatched; no overwrite or retry")
        require(old.sha(REVIEW) == expected_review_sha, "Explicit review SHA required")
        review, cap = old.read(REVIEW), old.read(CAP)
        require(
            review["driver_sha256"] == old.sha(DRIVER)
            and review["cap_sha256"] == old.sha(CAP)
            and review["helper_sha256"] == HELPERS
            and review["source_pins"] == old.inventory()
            and review["protocol_sha256"] == old.sha(PROTOCOL)
            and review["manifest_sha256"] == old.sha(MANIFEST)
            and review["plan"] == plan()
            and review["quality_receipt"] == old.verify_quality(review["quality_receipt"]["path"])
            and review["mvp"] == mvp_qualification(old, review["mvp"]["audit"])
            and cap["catalogue"] == mvp.capability(),
            "Reviewed source/protocol/quality/MVP/financial capability changed",
        )
        require(
            review["resource_qualifications"]
            == {"s2": mvp.calibration(), "s1": mvp.checkpoint_qualification()},
            "Resource qualification changed",
        )
        require(not old.git("status", "--porcelain"), "Clean committed checkout required")
        head = old.git("rev-parse", "HEAD")
        require(head == old.git("rev-parse", "origin/main"), "Pushed reviewed commit required")
        budget = old.ledger_state(cap)
        apps = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ],
            text=True,
        ).strip()
        require(not apps, "GPU busy; never stop foreign processes")
        argv = argv_for(IDS, budget["effective_campaign_usd"])
        old.save(
            OUT / "preflight.json",
            {
                "started_utc": datetime.now(UTC).isoformat(),
                "source_commit": head,
                "review_sha256": expected_review_sha,
                "argv": argv,
                "budget_before": budget,
                "fixed_denominator": 20,
                "per_policy_denominator": 10,
                "maximum_search_rounds": 6,
                "run_wall_limit_seconds": 480,
                "combine_policy_successes": False,
                "recharge": False,
            },
        )
        before = set((ROOT / "runs/evaluation/live").glob("*/campaign.json"))
        started = time.monotonic()
        with (OUT / "execution.log").open("x") as handle:
            child = subprocess.Popen(argv, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
            print(json.dumps({"pid": child.pid, "log": str(OUT / "execution.log")}), flush=True)
            code = child.wait()
        campaigns = [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": old.sha(path),
                "status": old.read(path).get("status"),
            }
            for path in sorted(
                set((ROOT / "runs/evaluation/live").glob("*/campaign.json")) - before
            )
        ]
        result = {
            "exit_code": code,
            "campaigns": campaigns,
            "elapsed_seconds": time.monotonic() - started,
            "completed_utc": datetime.now(UTC).isoformat(),
            "fixed_denominator": 20,
            "per_policy_denominator": 10,
            "combine_policy_successes": False,
            "unexecuted_slots_remain_unknown": True,
            "no_automatic_rerun": True,
            "not_an_independent_acceptance_audit": True,
        }
        old.save(OUT / "execution.json", result)
        print(json.dumps(result), flush=True)
        return code


def self_test():
    from types import SimpleNamespace

    from headroom.orchestrator import FixRequest

    _mvp, old = primitives()
    value = plan()
    require(FixRequest.model_fields["max_rounds"].default == 6, "Search bound changed")
    require(value["planned_pipeline_runs"] == 20, "Fixed matrix changed")
    argv = argv_for(IDS, "1.25")
    require(
        argv.count("--scenario") == 10 and "vit_random" not in argv and "t5_random" not in argv,
        "Library case leaked into matrix",
    )
    require(argv[argv.index("--campaign-budget") + 1] == "1.25", "Effective cap ignored")
    day = datetime.now(UTC).date().isoformat()
    runs = [{"id": "historical", "status": "closed", "halt_reason": None, "day": day}]
    attempts = [
        {
            "run_id": "historical",
            "settled": 1,
            "charged_usd": "0.2",
            "upper_usd": "0.2",
            "actual_usd": None,
            "charge_status": "reviewed_retained",
            "dispatched": 1,
            "admission_kind": "verified_provider_bound",
        }
    ]
    saved = old.ledger_rows
    old.ledger_rows = lambda: (runs, attempts)
    checks = 4
    try:
        cap = cap_snapshot(old, {})
        state = cap["budget_at_review"]
        require(
            state["campaign_max_usd"] == "12"
            and state["conservative_usd"] == "0.2"
            and Decimal(state["effective_campaign_usd"]) == POOL - Decimal("0.2")
            and Decimal(state["effective_campaign_usd"]) > Decimal("5.4"),
            "Old nominal cap or unknown-charge reset",
        )
        checks += 1
        for changed in (
            {"settled": 0},
            {"admission_kind": "unverified"},
            {"charged_usd": "9.5", "upper_usd": "9.5"},
        ):
            original = dict(attempts[0])
            attempts[0].update(changed)
            try:
                cap_snapshot(old, {})
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Unsafe synthetic ledger was accepted")
            finally:
                attempts[0] = original
    finally:
        old.ledger_rows = saved
    audit = {
        "fixed_denominator": 9,
        "counts": {"targets": 6, "valid_correct_first_causes": 6},
        "accepted_observed_campaign_gates": False,
        "gates": {k: True for k in MVP_TRUTH_GATES} | {"literal_nine_exit_zero": False},
        "rows": [
            {
                "scenario_id": identifier,
                "run_id": format(index, "032x"),
                "target": index < 6,
                "cause": index < 6,
                "observed": {
                    "gates": {k: True for k in MVP_ROW_TRUTH_GATES}
                    | {"harness_child_exit_zero": index < 8}
                },
            }
            for index, identifier in enumerate(IDS[:9])
        ],
    }
    passed = mvp_pass_line(audit)
    require(
        passed["targets"] == 6
        and passed["retained_unpassed_global_gates"] == {"literal_nine_exit_zero": False}
        and passed["retained_unpassed_row_gates"]
        and passed["phase1_all_items_certified"] is False,
        "MVP gate was raised to all original items passing",
    )
    checks += 1
    for invalid in (
        audit | {"fixed_denominator": 8},
        audit | {"counts": {"targets": 5, "valid_correct_first_causes": 6}},
        audit | {"counts": {"targets": 6, "valid_correct_first_causes": 5}},
        audit | {"gates": audit["gates"] | {"ledger_clear": False}},
    ):
        try:
            mvp_pass_line(invalid)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("Invalid MVP gate was accepted")
    # Exercise the actual future-freeze qualification path, not just its inner
    # pass-line helper. An outstanding original CLI item must not create a 9/9 gate.
    mock_audit_path = ROOT / "reports/acceptance-v2-20261025/memory-only-audit.json"
    mock_execution_path = ROOT / "reports/acceptance-v2-20261025/execution.json"
    campaign_path = "runs/evaluation/live/memory-only/campaign.json"
    sources = {"headroom/mock.py": "d" * 64}
    audit.update(
        audit_kind="independent_v2_mvp_nine",
        audit_source_sha256=MVP_AUDITOR_SHA,
        historical_scores_used=False,
        human_controls_counted=False,
        campaign=campaign_path,
        source_hashes={
            str(mock_execution_path.relative_to(ROOT)): "a" * 64,
            campaign_path: "b" * 64,
        },
        source_binding={
            "accepted": True,
            "inventory_sha256": {"review": inventory_digest(sources)},
        },
    )
    execution = {
        "completed_utc": "offline",
        "campaigns": [{"path": campaign_path, "status": "finished", "sha256": "b" * 64}],
    }
    documents = {mock_audit_path: audit, mock_execution_path: execution}
    hashes = {
        mock_audit_path: "c" * 64,
        mock_execution_path: "a" * 64,
        ROOT / campaign_path: "b" * 64,
    }
    mock = SimpleNamespace(
        path=lambda path: ROOT / path,
        read=lambda path: documents[ROOT / path],
        sha=lambda path: hashes[ROOT / path],
        inventory=lambda: sources,
    )
    qualified = mvp_qualification(mock, mock_audit_path)
    require(
        qualified["mvp_fixed_nine_gate_passed"] is True
        and qualified["mvp_pass_line"]["overall_campaign_all_item_gate"] is False
        and qualified["mvp_pass_line"]["targets"] == 6,
        "Outer qualification accidentally requires all original items to pass",
    )
    checks += 1
    for invalid in (
        audit | {"counts": {"targets": 5, "valid_correct_first_causes": 6}},
        audit | {"gates": audit["gates"] | {"ledger_clear": False}},
        audit | {"source_hashes": audit["source_hashes"] | {campaign_path: "f" * 64}},
    ):
        documents[mock_audit_path] = invalid
        try:
            mvp_qualification(mock, mock_audit_path)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("Actual qualification accepted an invalid MVP artifact")
    return {
        "self_test": "passed",
        "checks": checks,
        "provider_calls": 0,
        "gpu_jobs": 0,
        "live_ledger_reads": 0,
        "cap_frozen": False,
    }


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--freeze-quality")
    mode.add_argument("--execute-review-sha256")
    parser.add_argument("--mvp-audit")
    args = parser.parse_args()
    if args.execute_review_sha256:
        return execute(args.execute_review_sha256)
    if args.freeze_quality:
        require(args.mvp_audit, "Passed independent current MVP audit required")
        result = freeze(args.freeze_quality, args.mvp_audit)
    else:
        require(not args.mvp_audit, "MVP audit is only used by future freeze mode")
        result = self_test() if args.self_test else plan()
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
