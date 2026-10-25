"""Prepare one Phase 2 matrix; only explicit future freeze/execute modes spend.

Default planning and self-test do not read credentials, the profile or live ledger.
The $12 campaign ceiling is NOT a new pool: all calls retain the same cumulative
$14.17775754 lifetime partition and $9.99964904 daily limit and full provider-bound reservation.
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
OUT = ROOT / "reports/phase2-v2-r2-20261025"
DRIVER = OUT / "run_phase2_v2.py"
CAP = OUT / "cap-review.json"
REVIEW = OUT / "root-review.json"
MVP_OUT = ROOT / "reports/acceptance-v2-r2-20261025"
PROTOCOL = "eval/protocol_v2.json"
MANIFEST = "eval/scenario_set_v2.yaml"
POOL = Decimal("14.17775754")
DAILY_POOL = Decimal("9.99964904")
PROFILE = ".cache/tokenfactory-runtime-v2-r2.json"
PROFILE_SHA = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"
FUNDING_SHA = "cc31a24d0a6cdc91413b4521ef0d8b1f86a04e76ceb32fed3081d0998348784d"
BUDGET_HELPER = OUT / "ledger_state_phase2_r2.py"
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
    "reports/acceptance-v2-r2-20261025/run_mvp_v2.py": "9b5fa2d558b56ca475ed7279f2cae6d29cd93b986b1778c7a84953c8b72c74fe",
    "reports/acceptance-v2-r2-20261025/full_regression_driver.py": "e287296b1f2a445a72413643be10877fe6876c32cf291c1cdbbae2b67a25c938",
    "reports/phase2-v2-r2-20261025/ledger_state_phase2_r2.py": "14ac606a5c26c013b6059aac57d9c4186f800597962689bd5bcabab4419411c1",
}
MVP_AUDITOR_SHA = "947da8f1066922a764c38f47fe24ce4bb53a3c026f0a8abaf8bcd5af0ab2ef1f"


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
        "phase2_mvp_guards", ROOT / "reports/acceptance-v2-r2-20261025/run_mvp_v2.py"
    )
    mvp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mvp)
    require(
        mvp.POOL == POOL
        and mvp.DAILY_POOL == DAILY_POOL
        and mvp.old.POOL == DAILY_POOL
        and mvp.old.PER_RUN == PER_RUN
        and mvp.PROFILE == PROFILE,
        "Lifetime/daily/profile partition drift",
    )
    return mvp, mvp.old


def ledger_state(old, cap):
    """Use a separate reviewed Phase 2 helper; never change historical globals."""
    relative = str(BUDGET_HELPER.relative_to(ROOT))
    require(digest(BUDGET_HELPER) == HELPERS[relative], "Phase 2 budget helper drift")
    spec = importlib.util.spec_from_file_location("phase2_r2_partition", BUDGET_HELPER)
    budget = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(budget)
    require(
        budget.LIFETIME_POOL == POOL
        and budget.DAILY_POOL == DAILY_POOL
        and budget.PER_RUN == PER_RUN
        and budget.CAMPAIGN_MAX == CAMPAIGN_MAX,
        "Phase 2 budget constants drift",
    )
    return budget.ledger_state(old, cap)


def funding_qualification(mvp):
    require(mvp.PROFILE == PROFILE, "Phase 2 profile must share the reviewed runtime")
    require(
        digest(ROOT / PROFILE) == mvp.PROFILE_SHA == PROFILE_SHA, "Funded runtime profile changed"
    )
    return {
        "funding_event": mvp.funding(),
        "profile_path": PROFILE,
        "profile_sha256": mvp.PROFILE_SHA,
        "budget_helper_sha256": digest(BUDGET_HELPER),
        "lifetime_pool_usd": str(POOL),
        "daily_pool_usd": str(DAILY_POOL),
        "new_budget_pool": False,
        "phase2_requires_fresh_post_mvp_ledger_snapshot": True,
        "funding_event_snapshot_is_not_phase2_cap": True,
    }


def verify_phase2_cap(cap, funding):
    try:
        require(
            cap["funding"] == funding
            and funding["funding_event"]
            == {
                "path": str((MVP_OUT / "funding-transition.json").relative_to(ROOT)),
                "sha256": FUNDING_SHA,
                "zero_sum": True,
            }
            and funding["funding_event"]["zero_sum"] is True
            and funding["profile_path"] == PROFILE
            and funding["profile_sha256"] == PROFILE_SHA
            and funding["budget_helper_sha256"] == HELPERS[str(BUDGET_HELPER.relative_to(ROOT))]
            and Decimal(funding["lifetime_pool_usd"]) == POOL
            and Decimal(funding["daily_pool_usd"]) == DAILY_POOL
            and funding["new_budget_pool"] is False
            and funding["phase2_requires_fresh_post_mvp_ledger_snapshot"] is True
            and funding["funding_event_snapshot_is_not_phase2_cap"] is True
            and cap["authorization"]
            == {"gift_only": True, "recharge": False, "new_budget_pool": False}
            and Decimal(cap["pool_usd"]) == POOL
            and Decimal(cap["daily_pool_usd"]) == DAILY_POOL
            and Decimal(cap["campaign_max_usd"]) == CAMPAIGN_MAX
            and Decimal(cap["per_case_stop_usd"]) == PER_RUN
            and cap["history_exclusions"] == []
            and cap["unknown_costs_retain_verified_bounds"] is True
            and cap["full_provider_bound_required_for_every_attempt"] is True
            and cap["post_mvp_snapshot_required"] is True,
            "Reviewed Phase 2 funding or original budget limits changed",
        )
    except (KeyError, TypeError, ArithmeticError) as exc:
        raise ValueError("Complete Phase 2 funding qualification is required") from exc


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
        daily_budget_usd=str(DAILY_POOL),
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
            daily_budget_usd=str(DAILY_POOL),
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
        daily_pool_usd=str(DAILY_POOL),
        profile_path=PROFILE,
        funding_basis="same reviewed zero-sum runtime partition; no new pool",
        fresh_post_mvp_snapshot_required=True,
        actual_campaign_cap="min(12, remaining_all_time_pool, remaining_utc_day)",
        remaining_unexecuted_slots="unknown; never removed from the denominator",
        cap_frozen=False,
        can_reserve_all_run_caps=False,
        full_reservation_feasibility="20 simultaneous 0.6 caps exceed the unchanged daily limit; sequential actual-usage completion remains unknown until measured",
        reads_profile_or_ledger=False,
        mvp_gate_before_freeze="independent fixed-nine audit: targets >= 6 and valid/correct causes >= 6",
        phase1_all_items_certified=False,
        phase2_output=str(OUT.relative_to(ROOT)),
        required_mvp_output=str(MVP_OUT.relative_to(ROOT)),
        required_quality_output=str(MVP_OUT.relative_to(ROOT)),
        execution_qualification="not established by planning or self-test",
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
        str(DAILY_POOL),
        "--runtime-profile",
        PROFILE,
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
    "reviewed_zero_sum_gift_partition",
    "original_dispatch_daily_and_case_limits",
    "daily_pool_not_exceeded",
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
    audit_path = old.path(audit_path).resolve()
    mvp_out = MVP_OUT
    require(audit_path.parent == mvp_out, "MVP audit must belong to the current version")
    audit = old.read(audit_path)
    execution_path = mvp_out / "execution.json"
    execution = old.read(execution_path)
    campaigns = execution.get("campaigns")
    require(
        audit.get("audit_kind") == "independent_v2_r2_mvp_nine_zero_sum_partition"
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


def quality_qualification(old, receipt_path):
    """Bind receipt and its source inventories/log to this MVP revision."""
    receipt_path = old.path(receipt_path).resolve()
    require(
        receipt_path.parent == MVP_OUT and receipt_path.name.endswith("-receipt.json"),
        "Full quality receipt must belong to MVP r2",
    )
    quality = old.read(receipt_path)
    require(
        all(
            isinstance(quality.get(name), str)
            and old.path(quality[name]).resolve().parent == MVP_OUT
            for name in ("before", "after", "log")
        ),
        "Full quality evidence must belong to MVP r2",
    )
    # Existing full-suite/PLAN/guard/current source inventory checks are unchanged.
    return old.verify_quality(receipt_path)


def require_execution_artifacts():
    """Reject an unqualified revision before helper/ledger/profile/GPU access."""
    require(
        all(
            path.is_file() and not path.is_symlink()
            for path in (REVIEW, CAP, MVP_OUT / "execution.json")
        ),
        "Phase 2 r2 requires its own frozen review/cap and completed MVP r2 execution",
    )


def cap_snapshot(old, catalogue, funding):
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
        "funding": funding,
        "pool_usd": str(POOL),
        "daily_pool_usd": str(DAILY_POOL),
        "post_mvp_snapshot_required": True,
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
    verify_phase2_cap(cap, funding)
    cap["budget_at_review"] = ledger_state(old, cap)
    return cap


def freeze(quality_path, audit_path):
    mvp, old = primitives()
    require(not CAP.exists() and not REVIEW.exists(), "This version was already frozen")
    planned = plan()
    parent = mvp_qualification(old, audit_path)
    quality = quality_qualification(old, quality_path)
    cap = cap_snapshot(old, mvp.capability(), funding_qualification(mvp))
    # Resource qualifications remain independent from the model's MVP score.
    resources = {"s2": mvp.calibration(), "s1": mvp.checkpoint_qualification()}
    review = {
        "purpose": "phase2_v2_r2_ten_core_two_policy",
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
    ledger_state(old, cap)  # Fail if any prior row changed during the read-only freeze.
    old.save(CAP, cap)
    review["cap_sha256"] = old.sha(CAP)
    old.save(REVIEW, review)
    return {"review": str(REVIEW.relative_to(ROOT)), "sha256": old.sha(REVIEW)}


def execute(expected_review_sha):
    require_execution_artifacts()
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
            and review["quality_receipt"]
            == quality_qualification(old, review["quality_receipt"]["path"])
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
        verify_phase2_cap(cap, funding_qualification(mvp))
        budget = ledger_state(old, cap)
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
    from copy import deepcopy
    from types import SimpleNamespace
    from unittest.mock import patch

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
    synthetic_funding = {
        "funding_event": {
            "path": str((MVP_OUT / "funding-transition.json").relative_to(ROOT)),
            "sha256": FUNDING_SHA,
            "zero_sum": True,
        },
        "profile_path": PROFILE,
        "profile_sha256": PROFILE_SHA,
        "budget_helper_sha256": HELPERS[str(BUDGET_HELPER.relative_to(ROOT))],
        "lifetime_pool_usd": str(POOL),
        "daily_pool_usd": str(DAILY_POOL),
        "new_budget_pool": False,
        "phase2_requires_fresh_post_mvp_ledger_snapshot": True,
        "funding_event_snapshot_is_not_phase2_cap": True,
    }
    saved = old.ledger_rows
    old.ledger_rows = lambda: (runs, attempts)
    checks = 4
    try:
        cap = cap_snapshot(old, {}, synthetic_funding)
        state = cap["budget_at_review"]
        require(
            state["campaign_max_usd"] == "12"
            and state["conservative_usd"] == "0.2"
            and Decimal(state["effective_campaign_usd"]) == DAILY_POOL - Decimal("0.2")
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
                cap_snapshot(old, {}, synthetic_funding)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Unsafe synthetic ledger was accepted")
            finally:
                attempts[0] = original
        original_attempt = dict(attempts[0])
        original_day = runs[0]["day"]
        try:
            runs[0]["day"] = "2000-01-01"
            attempts[0].update(charged_usd="13", upper_usd="13")
            prior_day = cap_snapshot(old, {}, synthetic_funding)["budget_at_review"]
            require(
                Decimal(prior_day["remaining_day_usd"]) == DAILY_POOL
                and Decimal(prior_day["remaining_all_time_usd"]) == POOL - Decimal(13)
                and Decimal(prior_day["effective_campaign_usd"]) == POOL - Decimal(13),
                "UTC rollover reset cumulative history or raised daily authority",
            )
            checks += 1
            attempts[0].update(charged_usd="14", upper_usd="14")
            try:
                cap_snapshot(old, {}, synthetic_funding)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Insufficient lifetime reservation was accepted")
        finally:
            attempts[0] = original_attempt
            runs[0]["day"] = original_day
        attempts[0].update(charged_usd="0.3", upper_usd="0.3")
        try:
            try:
                ledger_state(old, cap)
            except ValueError:
                checks += 1
            else:
                raise AssertionError("Pre-MVP ledger projection reused after additional charge")
            refreshed = cap_snapshot(old, {}, synthetic_funding)
            require(
                refreshed["ledger"]["projection_sha256"] != cap["ledger"]["projection_sha256"]
                and refreshed["budget_at_review"]["conservative_usd"] == "0.3",
                "Fresh post-MVP cap omitted newly charged history",
            )
            checks += 1
        finally:
            attempts[0] = original_attempt
    finally:
        old.ledger_rows = saved
    require(argv[argv.index("--daily-budget") + 1] == str(DAILY_POOL), "Daily cap drift")
    require(argv[argv.index("--runtime-profile") + 1] == PROFILE, "Profile not versioned")
    require(
        old.POOL == DAILY_POOL and old.CAMPAIGN_MAX == Decimal("5.4"), "Historical helper mutated"
    )
    checks += 3
    for field, value in (
        ("funding", {}),
        ("daily_pool_usd", str(POOL)),
        ("pool_usd", str(DAILY_POOL)),
        ("per_case_stop_usd", "1"),
        ("campaign_max_usd", "13"),
        ("history_exclusions", ["old"]),
        ("unknown_costs_retain_verified_bounds", False),
        ("post_mvp_snapshot_required", False),
    ):
        altered = deepcopy(cap)
        altered[field] = value
        try:
            verify_phase2_cap(altered, synthetic_funding)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("Altered funding cap accepted")
    for field, value in (
        ("funding_event", {"path": "pending", "sha256": "PENDING", "zero_sum": True}),
        ("profile_path", ".cache/tokenfactory-runtime.json"),
        ("profile_sha256", "PENDING_PROFILE_SHA"),
        ("budget_helper_sha256", "0" * 64),
        ("new_budget_pool", True),
        ("daily_pool_usd", str(POOL)),
        ("phase2_requires_fresh_post_mvp_ledger_snapshot", False),
    ):
        altered_funding = deepcopy(synthetic_funding)
        altered_funding[field] = value
        altered = deepcopy(cap)
        altered["funding"] = altered_funding
        try:
            verify_phase2_cap(altered, altered_funding)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("Pending or unbound funding accepted")
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
    mock_audit_path = ROOT / "reports/acceptance-v2-r2-20261025/memory-only-audit.json"
    mock_execution_path = ROOT / "reports/acceptance-v2-r2-20261025/execution.json"
    campaign_path = "runs/evaluation/live/memory-only/campaign.json"
    sources = {"headroom/mock.py": "d" * 64}
    audit.update(
        audit_kind="independent_v2_r2_mvp_nine_zero_sum_partition",
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

    # Old revisions cannot satisfy either qualification, even with otherwise
    # valid synthetic data. These tests never read the live ledger/profile.
    for prior in (
        ROOT / "reports/acceptance-v2-20261025/memory-only-audit.json",
        MVP_OUT / "../acceptance-v2-20261025/memory-only-audit.json",
    ):
        try:
            mvp_qualification(mock, prior)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("A different MVP revision was accepted")

    quality_path = MVP_OUT / "memory-only-receipt.json"
    quality_document = {
        "before": str((MVP_OUT / "memory-only-before.json").relative_to(ROOT)),
        "after": str((MVP_OUT / "memory-only-after.json").relative_to(ROOT)),
        "log": str((MVP_OUT / "memory-only.log").relative_to(ROOT)),
    }
    quality_calls = []
    quality_mock = SimpleNamespace(
        path=lambda path: ROOT / path,
        read=lambda path: quality_document,
        verify_quality=lambda path: quality_calls.append(path) or {"offline": True},
    )
    require(
        quality_qualification(quality_mock, quality_path) == {"offline": True}
        and quality_calls == [quality_path],
        "Current revision did not delegate unchanged full quality verification",
    )
    checks += 1
    for prior in (
        ROOT / "reports/acceptance-v2-20261025/memory-only-receipt.json",
        MVP_OUT / "../acceptance-v2-20261025/memory-only-receipt.json",
    ):
        try:
            quality_qualification(quality_mock, prior)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("A different quality revision was accepted")
    for field in ("before", "after", "log"):
        saved_value = quality_document[field]
        quality_document[field] = "reports/acceptance-v2-20261025/old-evidence.json"
        try:
            quality_qualification(quality_mock, quality_path)
        except ValueError:
            checks += 1
        else:
            raise AssertionError("Old quality evidence was accepted")
        finally:
            quality_document[field] = saved_value
    require(quality_calls == [quality_path], "Rejected quality reached verification")
    with (
        patch.object(Path, "is_file", return_value=False),
        patch.dict(
            globals(),
            primitives=lambda: (_ for _ in ()).throw(
                AssertionError("Unqualified execution imported helpers")
            ),
        ),
        patch.object(subprocess, "Popen", side_effect=AssertionError("Unexpected execution")),
        patch.object(subprocess, "check_output", side_effect=AssertionError("Unexpected GPU/git")),
    ):
        try:
            execute("0" * 64)
        except ValueError as error:
            require("requires its own frozen review/cap" in str(error), "Wrong early rejection")
            checks += 1
        else:
            raise AssertionError("Unqualified revision was dispatched")

    return {
        "self_test": "passed",
        "checks": checks,
        "provider_calls": 0,
        "gpu_jobs": 0,
        "live_ledger_reads": 0,
        "cap_frozen": False,
        "execution_qualification": False,
        "old_revision_rejected": True,
        "quality_revision_bound": True,
        "missing_qualification_rejected_before_helpers": True,
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
