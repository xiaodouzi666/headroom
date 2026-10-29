"""Bounded costs remain unknown actuals, while conservative caps remain enforceable."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

import pytest
from test_demo_allocation import begin, controller
from test_demo_allocation import demo_pool as demo_pool  # noqa: PLC0414
from test_feature_allocation import child_for as feature_child
from test_feature_allocation import feature_pool as feature_pool  # noqa: PLC0414
from test_feature_allocation import parent_for as feature_parent
from test_final48_ablation import offline as offline  # noqa: PLC0414
from test_final48_f3_allocation import child_for as f3_child
from test_final48_f3_allocation import f3_pool as f3_pool  # noqa: PLC0414
from test_final48_f3_allocation import parent_for as f3_parent

from headroom.acceptance import allocation as alloc
from headroom.acceptance import feature_allocation as feature
from headroom.acceptance.demo_recovery import execute_demo_recovery, prepare_demo_recovery


def bounded(ledger, run_id, *, amount=".00378462", cap=".01644864", open_run=False):
    if open_run:
        ledger.open_run(run_id, ".30")
    ledger.reserve(run_id, run_id + "-attempt", cap)
    ledger.settle_upper_bound(
        run_id, run_id + "-attempt", amount, basis="verified_tariff_missing_cache_count"
    )
    ledger.close_run(run_id)


@pytest.mark.parametrize("legacy", [False, True])
def test_bound_allows_next_demo_without_claiming_actual_or_resetting_cap(demo_pool, legacy):
    kwargs = {"scope_limit_usd": ".30"} if legacy else {}
    owner, _, binding, ledger = begin(demo_pool, 1, controller(demo_pool, **kwargs))
    bounded(ledger, binding["run_id"])
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    assert result["actual_usd"] is None and result["cost_resolved"]
    assert result["charged_usd"] == "0.00378462"
    state = alloc._budget_state(demo_pool["receipt"])
    assert state["resolved"] and not state["known"]
    assert state["attempts"][0]["actual_usd"] is None
    assert controller(demo_pool).available
    _, request, _, _ = begin(demo_pool, 2, controller(demo_pool, **kwargs))
    assert Decimal(request.budget_usd) == Decimal(".29621538" if legacy else ".30")
    assert alloc.historical_snapshot(demo_pool["root"]) == demo_pool["history"]


def test_f3_bound_is_resolved_and_charged_while_actual_remains_unknown(f3_pool):
    parent = f3_parent(f3_pool)
    _, binding, _, ledger = f3_child(f3_pool, parent)
    bounded(ledger, binding["run_id"], open_run=True)
    result = alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["actual_usd"] is None
    account = alloc.f3_accounting(parent)
    assert account["all_costs_resolved"] and not account["all_costs_known"]
    assert account["scope_spent_usd"] is None
    assert account["scope_charged_usd"] == "0.00378462"
    f3_child(f3_pool, parent, index=1)


def test_feature_bound_allows_next_slot_without_fabricating_actual(feature_pool):
    parent = feature_parent(feature_pool)
    binding, _, ledger = feature_child(feature_pool, parent, "snapshot-s2")
    bounded(ledger, binding["run_id"], open_run=True)
    result = feature.finish_feature_child(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["actual_usd"] is None
    account = feature.feature_accounting(parent)
    assert account["all_costs_resolved"] and not account["all_costs_known"]
    assert account["scope_spent_usd"] is None
    assert account["scope_charged_usd"] == "0.00378462"
    feature_child(feature_pool, parent, "snapshot-nanogpt")


@pytest.mark.parametrize(
    "change",
    [
        {"settled": 0},
        {"dispatched": 0},
        {"admission_kind": "local_estimate"},
        {"charge_status": "unknown"},
        {"charge_basis": "guess"},
        {"charged_usd": ".01644865"},
        {"charge_status": "reviewed_retained"},
    ],
)
def test_unfinalized_or_unverified_cost_is_not_resolved(demo_pool, change):
    _, _, binding, ledger = begin(demo_pool, 1)
    bounded(ledger, binding["run_id"])
    state = alloc._budget_state(demo_pool["receipt"])
    row = state["attempts"][0] | change
    assert not alloc._attempt_resolved(row)


def test_reviewed_retention_requires_matching_persisted_review(demo_pool):
    _, _, binding, ledger = begin(demo_pool, 1)
    bounded(ledger, binding["run_id"])
    row = alloc._budget_state(demo_pool["receipt"])["attempts"][0]
    row.update(
        charge_status="reviewed_retained",
        charge_basis="manual_full_reservation_retained",
        charged_usd=row["upper_usd"],
        review_sha256="1" * 64,
    )
    assert not alloc._attempt_resolved(row)
    assert not alloc._attempt_resolved(row, {("1" * 64, row["id"], "wrong-run")})
    assert alloc._attempt_resolved(row, {("1" * 64, row["id"], row["run_id"])})


def old_bridge_failure(pool):
    # The recovery fixture models an actual historical v1 payload.
    _, _, binding, ledger = begin(pool, 1, controller(pool, scope_limit_usd=".30"))
    bounded(ledger, binding["run_id"])
    ledger.halt(binding["run_id"], "local_accounting_incomplete")
    with alloc.registry(pool["root"]) as conn:
        conn.execute(
            "UPDATE f2_demo_runs SET state='blocked',settlement=? WHERE run_id=?",
            (json.dumps({"status": "blocked", "actual_usd": None}), binding["run_id"]),
        )
        conn.execute("UPDATE claims SET state='blocked' WHERE run_id=?", (binding["run_id"],))
    evidence = pool["root"] / "cleanup-review.json"
    evidence.write_text(
        json.dumps(
            {
                "run_id": binding["run_id"],
                "execution_terminal": True,
                "cleanup_verified": True,
                "reviewed_by": "offline-test",
                "evidence": "Fake worker is terminal; no process launched.",
            }
        )
    )
    return binding, ledger, evidence


def proposal_for(pool, binding, evidence):
    proposal = prepare_demo_recovery(
        pool["path"],
        project_root=pool["root"],
        run_id=binding["run_id"],
        execution_evidence_path=evidence,
    )
    path = pool["root"] / "review-proposal.json"
    path.write_text(json.dumps(proposal, sort_keys=True))
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_recovery_preserves_original_blocked_state_and_unknown_charge(demo_pool):
    binding, _, evidence = old_bridge_failure(demo_pool)
    before = alloc._budget_state(demo_pool["receipt"])
    path, sha = proposal_for(demo_pool, binding, evidence)
    assert not controller(demo_pool).available  # preparation is read only
    result = execute_demo_recovery(path, expected_sha256=sha)
    after = alloc._budget_state(demo_pool["receipt"])
    assert before["attempts"] == after["attempts"]
    assert after["runs"][binding["run_id"]]["halt_reason"] is None
    assert result["actual_usd"] is None and result["charged_usd"] == "0.00378462"
    assert result["previous_settlement"] == {"status": "blocked", "actual_usd": None}
    assert controller(demo_pool).available
    with sqlite3.connect(demo_pool["receipt"]["ledger_path"]) as conn:
        audit = json.loads(
            conn.execute("SELECT evidence_json FROM budget_accounting_reviews").fetchone()[0]
        )
    assert audit["expected_ledger"]["runs"][0]["halt_reason"] == "local_accounting_incomplete"
    assert audit["original_registry"]["demo"]["state"] == "blocked"
    assert audit["receipt_sha256"] == demo_pool["receipt"]["receipt_sha256"]
    _, request, _, _ = begin(demo_pool, 2, controller(demo_pool, scope_limit_usd=".30"))
    assert Decimal(request.budget_usd) == Decimal(".29621538")


@pytest.mark.parametrize("mutation", ["sha", "evidence", "attempt", "halt"])
def test_recovery_refuses_changed_evidence_without_clearing_halt(demo_pool, mutation):
    binding, _, evidence = old_bridge_failure(demo_pool)
    path, sha = proposal_for(demo_pool, binding, evidence)
    if mutation == "sha":
        sha = "0" * 64
    elif mutation == "evidence":
        value = json.loads(evidence.read_text())
        value["cleanup_verified"] = False
        evidence.write_text(json.dumps(value))
    else:
        with sqlite3.connect(demo_pool["receipt"]["ledger_path"]) as conn:
            if mutation == "attempt":
                conn.execute("UPDATE budget_attempts SET charged_usd='.004'")
            else:
                conn.execute("UPDATE budget_runs SET halt_reason='provider_charge_unknown'")
    with pytest.raises(alloc.AllocationRefused):
        execute_demo_recovery(path, expected_sha256=sha)
    assert alloc._budget_state(demo_pool["receipt"])["runs"][binding["run_id"]]["halt_reason"]
    assert not controller(demo_pool).available


def test_existing_exact_retention_review_is_resolved_but_remains_unknown(demo_pool):
    owner, _, binding, ledger = begin(demo_pool, 1)
    run_id = binding["run_id"]
    ledger.reserve(run_id, "review-me", ".01")
    ledger.settle(run_id, "review-me", None)
    ledger.close_run(run_id)
    before = alloc._budget_state(demo_pool["receipt"])
    row = before["attempts"][0]
    keys = (
        "id",
        "run_id",
        "upper_usd",
        "charged_usd",
        "actual_usd",
        "settled",
        "admission_kind",
        "dispatched",
    )
    ledger.review_retained(
        run_id,
        "review-me",
        expected_attempt={k: row[k] for k in keys},
        receipt_sha256="1" * 64,
        evidence={"reason": "missing_cached_token_usage", "expected_run": before["runs"][run_id]},
    )
    state = alloc._budget_state(demo_pool["receipt"])
    assert state["resolved"] and not state["known"]
    assert state["charged"] == Decimal(".01")
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["actual_usd"] is None
    assert result["charged_usd"] == "0.01"
    assert controller(demo_pool).available


def test_interrupted_cross_database_recovery_can_finish_without_duplicate_audit(
    demo_pool, monkeypatch
):
    from headroom.acceptance import demo_recovery as recovery

    binding, _, evidence = old_bridge_failure(demo_pool)
    path, sha = proposal_for(demo_pool, binding, evidence)
    real_registry = recovery.registry

    @contextmanager
    def interrupted(root):
        with real_registry(root) as conn:
            yield conn
            raise RuntimeError("offline injected registry commit failure")

    monkeypatch.setattr(recovery, "registry", interrupted)
    with pytest.raises(RuntimeError, match="injected"):
        execute_demo_recovery(path, expected_sha256=sha)
    assert (
        alloc._budget_state(demo_pool["receipt"])["runs"][binding["run_id"]]["halt_reason"] is None
    )
    assert not controller(demo_pool).available  # registry remains blocked
    monkeypatch.setattr(recovery, "registry", real_registry)
    result = execute_demo_recovery(path, expected_sha256=sha)
    assert result["status"] == "settled"
    with sqlite3.connect(demo_pool["receipt"]["ledger_path"]) as conn:
        assert conn.execute("SELECT count(*) FROM budget_accounting_reviews").fetchone()[0] == 1
    assert controller(demo_pool).available
