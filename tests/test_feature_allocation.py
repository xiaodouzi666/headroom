"""Temporary explicit offline allocations; no real model, GPU, profile or pool."""

import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414

from headroom.acceptance import allocation as alloc
from headroom.acceptance import feature_allocation as feature
from headroom.budget import BudgetExceeded, BudgetLedger


@pytest.fixture
def feature_pool(tmp_path, request):
    root = tmp_path / "offline-project"
    root.mkdir()
    daily = getattr(request, "param", "6")
    old = BudgetLedger(root / ".cache/budget.db", total_limit="6", daily_limit="6")
    old.open_run("legacy", ".1")
    old.reserve("legacy", "unknown-legacy", ".01")
    old.settle("legacy", "unknown-legacy", None)
    history = alloc.historical_snapshot(root)
    path, _ = profile(root)
    document = json.loads(path.read_text())
    document["authorized_total_usd"] = "6"
    document["available_credit_usd"] = "8"
    profile_path = root / ".cache/final48-allocation/runtime-profile.json"
    intents = {
        slot: {
            "kind": kind,
            "runtime_profile": str(profile_path),
            "budget_usd": "0.30",
            "daily_budget_usd": daily,
            "payload": {"fixture": "offline_only", "input_sha256": str(i + 1) * 64},
        }
        for i, (slot, (kind, _)) in enumerate(
            slot for group in feature.GROUPS.values() for slot in group["slots"].items()
        )
    }
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6",
        "available_gift_usd": "8",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": daily,
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.5"
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    plan["feature_scope_caps_usd"] = {"F3b": "1", "F5": "0.30"}
    for scope, group in feature.GROUPS.items():
        for _, task_scope in group["slots"].values():
            plan["task_run_caps_usd"][task_scope] = "0.30"
        plan["task_pins"][scope] = {
            "preparation_sha256": ("4" if scope == "F3b" else "5") * 64,
            "slot_intents_sha256": alloc.digest(
                {slot: feature.intent_sha256(intents[slot]) for slot in group["slots"]}
            ),
        }
    authorization = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "6",
        "approval_message_ref": "offline-fixture-not-human-authorization",
        "statement_sha256": "6" * 64,
    }
    receipt = alloc.activate_allocation(plan, authorization, document, project_root=root)
    return {
        "root": root,
        "plan": plan,
        "authorization": authorization,
        "profile": document,
        "receipt": receipt,
        "path": root / ".cache/final48-allocation/receipt.json",
        "intents": intents,
        "history": history,
    }


def parent_for(pool, scope="F3b", **overrides):
    return feature.claim_feature_parent(
        pool["path"],
        **(
            {
                "project_root": pool["root"],
                "scope": scope,
                "preparation_sha256": pool["plan"]["task_pins"][scope]["preparation_sha256"],
                "slot_intents": {
                    slot: feature.intent_sha256(pool["intents"][slot])
                    for slot in feature.GROUPS[scope]["slots"]
                },
            }
            | overrides
        ),
    )


def child_for(pool, parent, slot):
    intent = pool["intents"][slot]
    binding = feature.claim_feature_child(
        parent, slot_id=slot, intent=intent, run_id="offline-" + slot
    )
    verified = feature.verify_feature_child_binding(
        binding, intent=intent, run_id=binding["run_id"], environ={}
    )
    budget = BudgetLedger(
        verified.database.path,
        require_existing=True,
        expected_identity=verified.database.file_identity,
        total_limit=verified.total_limit_usd,
        daily_limit=verified.daily_limit_usd,
    )
    return binding, verified, budget


def settle(binding, budget, actual="0.2"):
    run_id = binding["run_id"]
    budget.open_run(run_id, binding["run_limit_usd"])
    budget.reserve(run_id, run_id + "-attempt", binding["run_limit_usd"])
    budget.settle(run_id, run_id + "-attempt", actual)
    budget.close_run(run_id)
    return feature.finish_feature_child(binding, execution_terminal=True, cleanup_verified=True)


def test_feature_draft_has_no_money_or_files(tmp_path):
    plan = alloc.prepare_allocation_plan()
    assert plan["feature_scope_caps_usd"] == {"F3b": None, "F5": None}
    assert plan["task_pins"]["F3b"] == {"preparation_sha256": None, "slot_intents_sha256": None}
    assert plan["task_pins"]["F5"] == {"preparation_sha256": None, "slot_intents_sha256": None}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field,value", [("scope", "1.01"), ("child", "0.31"), ("pin", None)])
def test_activation_requires_group_cap_child_cap_and_reviewed_slots(feature_pool, field, value):
    plan = copy.deepcopy(feature_pool["plan"])
    if field == "scope":
        plan["feature_scope_caps_usd"]["F3b"] = value
    elif field == "child":
        plan["task_run_caps_usd"]["F3b_snapshot"] = value
    else:
        plan["task_pins"]["F3b"]["slot_intents_sha256"] = value
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_"):
        alloc.activate_allocation(
            plan,
            feature_pool["authorization"],
            feature_pool["profile"],
            project_root=feature_pool["root"],
        )


def test_fixed_intents_and_once_parent_cannot_be_bypassed(feature_pool):
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_INPUT_BINDING_CHANGED"):
        parent_for(feature_pool, preparation_sha256="0" * 64)
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_FIXED_SLOTS_REQUIRED"):
        parent_for(feature_pool, slot_intents={"snapshot-web": "0" * 64})
    for scope in ("F3b_snapshot", "F3b_watch", "F5"):
        with pytest.raises(alloc.AllocationRefused, match="FEATURE_PARENT_CHILD_BINDING_REQUIRED"):
            alloc.verify_and_claim_allocation(
                feature_pool["path"],
                project_root=feature_pool["root"],
                task_scope=scope,
                execution_key="new-key",
                profile_path=feature_pool["receipt"]["profile_path"],
                run_limit_usd=".30",
                daily_limit_usd="6",
            )
    parent = parent_for(feature_pool)
    feature.finish_feature_parent(parent, status="stopped")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        parent_for(feature_pool)


def test_snapshots_watch_and_clean_fix_share_db_but_have_independent_scope_caps(feature_pool):
    receipt = feature_pool["receipt"]
    budget = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="6")
    budget.open_run("prior-f1", "1.5")
    budget.reserve("prior-f1", "prior", "1.5")
    budget.settle("prior-f1", "prior", "1.5")
    budget.close_run("prior-f1")
    parent = parent_for(feature_pool)
    assert parent["total_limit_usd"] == "2.5"
    for slot in feature.GROUPS["F3b"]["slots"]:
        binding, verified, budget = child_for(feature_pool, parent, slot)
        assert verified.daily_limit_usd == "6"
        assert verified.total_limit_usd == "2.5"
        assert settle(binding, budget)["status"] == "settled"
    account = feature.feature_accounting(parent)
    assert account["scope_spent_usd"] == "0.8"
    assert account["new_pool_charged_usd"] == "2.3"
    assert account["status"] == "settled"
    feature.finish_feature_parent(parent, status="completed")
    f5 = parent_for(feature_pool, "F5")
    assert f5["total_limit_usd"] == "2.60"
    binding, verified, budget = child_for(feature_pool, f5, "clean-s3")
    assert verified.run_limit_usd == "0.30"
    assert settle(binding, budget, actual="0.1")["status"] == "settled"
    feature.finish_feature_parent(f5, status="completed")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        parent_for(feature_pool, "F5")
    assert alloc.historical_snapshot(feature_pool["root"]) == feature_pool["history"]


def test_f3b_shared_one_dollar_is_not_reset_for_watch(feature_pool):
    parent = parent_for(feature_pool)
    for slot in ("snapshot-s2", "snapshot-nanogpt", "snapshot-web"):
        binding, _, budget = child_for(feature_pool, parent, slot)
        assert settle(binding, budget, actual="0.30")["status"] == "settled"
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_SCOPE_EXHAUSTED"):
        child_for(feature_pool, parent, "watch-s1")
    assert feature.feature_accounting(parent)["scope_spent_usd"] == "0.90"


@pytest.mark.parametrize("case", ["unknown", "pending", "open", "cleanup", "not_terminal"])
def test_unknown_or_unclean_child_stops_all_other_feature_slots(feature_pool, case):
    parent = parent_for(feature_pool)
    binding, _, budget = child_for(feature_pool, parent, "snapshot-s2")
    run_id = binding["run_id"]
    budget.open_run(run_id, ".30")
    budget.reserve(run_id, "attempt", ".30")
    if case == "unknown":
        budget.settle(run_id, "attempt", None)
    elif case != "pending":
        budget.settle(run_id, "attempt", ".1")
    if case != "open":
        budget.close_run(run_id)
    outcome = feature.finish_feature_child(
        binding, execution_terminal=case != "not_terminal", cleanup_verified=case != "cleanup"
    )
    assert outcome["status"] == "blocked"
    if case in {"unknown", "pending"}:
        assert outcome["actual_usd"] is None
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_PREVIOUS_CHILD_UNSETTLED"):
        child_for(feature_pool, parent, "watch-s1")
    assert feature.feature_accounting(parent)["status"] == "blocked"


@pytest.mark.parametrize(
    "mutation", ["intent", "cap", "profile", "receipt", "run_id", "child_state"]
)
def test_verifier_rejects_post_claim_changes(feature_pool, mutation):
    parent = parent_for(feature_pool)
    binding, _, _ = child_for(feature_pool, parent, "snapshot-s2")
    intent = copy.deepcopy(feature_pool["intents"]["snapshot-s2"])
    run_id = binding["run_id"]
    if mutation == "intent":
        intent["payload"]["input_sha256"] = "0" * 64
    elif mutation == "cap":
        binding["total_limit_usd"] = "6"
        binding["binding_sha256"] = alloc.digest(
            {key: value for key, value in binding.items() if key != "binding_sha256"}
        )
    elif mutation == "profile":
        path = Path(feature_pool["receipt"]["profile_path"])
        path.write_text(path.read_text() + " ")
    elif mutation == "receipt":
        document = json.loads(feature_pool["path"].read_text())
        document["feature_scope_caps_usd"]["F3b"] = "5"
        feature_pool["path"].write_text(json.dumps(document))
    elif mutation == "run_id":
        run_id = "not-the-approved-run"
    else:
        feature.finish_feature_child(binding, execution_terminal=True, cleanup_verified=True)
    with pytest.raises(alloc.AllocationRefused):
        feature.verify_feature_child_binding(binding, intent=intent, run_id=run_id)


def test_concurrent_parent_and_children_each_have_one_winner(feature_pool):
    barrier = Barrier(2)

    def attempt_parent():
        barrier.wait(timeout=5)
        try:
            return parent_for(feature_pool)
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        parents = list(workers.map(lambda _: attempt_parent(), range(2)))
    assert parents.count("ALLOCATION_EXECUTION_ALREADY_CLAIMED") == 1
    parent = next(row for row in parents if isinstance(row, dict))
    barrier = Barrier(2)

    def attempt_child(slot):
        barrier.wait(timeout=5)
        try:
            return feature.claim_feature_child(
                parent, slot_id=slot, intent=feature_pool["intents"][slot], run_id=slot
            )
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        children = list(workers.map(attempt_child, ("snapshot-s2", "watch-s1")))
    assert children.count("FEATURE_PREVIOUS_CHILD_UNSETTLED") == 1
    assert sum(isinstance(row, dict) for row in children) == 1


@pytest.mark.parametrize("feature_pool", ["2"], indirect=True)
def test_receipt_daily_limit_is_inherited_and_cannot_be_raised(feature_pool):
    receipt = feature_pool["receipt"]
    budget = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="2")
    budget.open_run("prior-f1", "1.5")
    budget.reserve("prior-f1", "prior", "1.5")
    budget.settle("prior-f1", "prior", "1.5")
    budget.close_run("prior-f1")
    parent = parent_for(feature_pool)
    binding, verified, budget = child_for(feature_pool, parent, "snapshot-s2")
    assert verified.daily_limit_usd == "2"
    assert verified.total_limit_usd == "2.5"
    assert settle(binding, budget, actual=".30")["status"] == "settled"
    binding, verified, budget = child_for(feature_pool, parent, "snapshot-web")
    assert verified.daily_limit_usd == "2"
    with pytest.raises(BudgetExceeded):
        budget.open_run(binding["run_id"], binding["run_limit_usd"])
    with sqlite3.connect(receipt["ledger_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 2


def test_intent_rejects_nonfinite_and_unknown_contract_fields(feature_pool):
    intent = copy.deepcopy(feature_pool["intents"]["snapshot-s2"])
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_INTENT_REQUIRED"):
        feature.intent_sha256(intent | {"unreviewed": True})
    intent["payload"]["bad_number"] = float("inf")
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_INTENT_INVALID"):
        feature.intent_sha256(intent)


def test_uncertain_cleanup_cannot_be_escaped_by_switching_to_f5(feature_pool):
    parent = parent_for(feature_pool)
    binding, _, budget = child_for(feature_pool, parent, "snapshot-web")
    run_id = binding["run_id"]
    budget.open_run(run_id, ".30")
    budget.reserve(run_id, "attempt", ".30")
    budget.settle(run_id, "attempt", ".1")
    budget.close_run(run_id)
    assert (
        feature.finish_feature_child(binding, execution_terminal=True, cleanup_verified=False)[
            "status"
        ]
        == "blocked"
    )
    with pytest.raises(alloc.AllocationRefused, match="FEATURE_OTHER_CHILD_UNSETTLED"):
        parent_for(feature_pool, "F5")
