"""FINAL48 authorization binding with temporary fixtures only; no real allocation."""

import json
import shutil
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import httpx
import pytest
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414 - shared pytest fixture
from test_final48_ablation import prepare, transport_for
from test_final48_ablation import project as project  # noqa: PLC0414 - shared pytest fixture

from headroom.acceptance import allocation as alloc
from headroom.acceptance import final48_ablation as f1
from headroom.budget import BudgetLedger
from headroom.ledger_path import LedgerPathError


@pytest.fixture
def activated(project):
    root, _, _ = project
    old = BudgetLedger(root / ".cache/budget.db", total_limit="5", daily_limit="5")
    old.open_run("offline-legacy", "0.1")
    old.reserve("offline-legacy", "offline-unknown", "0.01")
    old.settle("offline-legacy", "offline-unknown", None)
    before = alloc.historical_snapshot(root)
    prepared, prepared_path = prepare(project)
    profile_path, credentials = profile(root)
    document = json.loads(profile_path.read_text())
    document["authorized_total_usd"] = "3"
    document["models"]["super"]["capabilities"] = {
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline fixture only",
    }
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "3",
        "available_gift_usd": "5",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": "3",
    }
    plan["task_run_caps_usd"] = {scope: "1.5" for scope in alloc.SCOPES}
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_pins"]["F1"] = {
        "preparation_sha256": prepared["preparation_sha256"],
        "scoring_policy_sha256": prepared["scoring_policy_sha256"],
    }
    authorization = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "3",
        "approval_message_ref": "offline-fixture-no-human-authorization",
        "statement_sha256": "2" * 64,
    }
    receipt = alloc.activate_allocation(plan, authorization, document, project_root=root)
    receipt_path = root / ".cache/final48-allocation/receipt.json"
    return (
        root,
        plan,
        authorization,
        document,
        receipt,
        receipt_path,
        prepared,
        prepared_path,
        credentials,
        before,
    )


def claim(values, **overrides):
    root, _, _, _, receipt, path, prepared, _, _, _ = values
    args = {
        "project_root": root,
        "task_scope": "F1",
        "execution_key": "caller-cannot-evade-once",
        "profile_path": Path(receipt["profile_path"]),
        "run_limit_usd": "1.5",
        "daily_limit_usd": "3",
        "preparation_sha256": prepared["preparation_sha256"],
        "scoring_policy_sha256": prepared["scoring_policy_sha256"],
    }
    return alloc.verify_and_claim_allocation(path, **(args | overrides))


def test_default_plan_has_null_money_and_no_side_effects(tmp_path):
    plan = alloc.prepare_allocation_plan()
    assert all(value is None for value in plan["amounts"].values())
    assert all(value is None for value in plan["task_run_caps_usd"].values())
    assert plan["task_scopes"] == list(alloc.SCOPES)
    assert list(tmp_path.iterdir()) == []


def test_no_authorization_cannot_initialize_profile_or_ledger(tmp_path):
    with pytest.raises(alloc.AllocationRefused, match="AMOUNT_AUTHORIZATION_REQUIRED"):
        alloc.activate_allocation(alloc.prepare_allocation_plan(), {}, {}, project_root=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_activation_keeps_old_unknown_and_uses_one_shared_pool(activated):
    root, _, _, _, receipt, path, _, _, _, before = activated
    assert alloc.historical_snapshot(root) == before
    assert before["unknown_attempts"] == 1
    assert receipt["historical_ledger"] == before
    assert receipt["task_scopes"] == list(alloc.SCOPES)
    assert (
        alloc.verify_receipt(path, project_root=root)["allocation_id"] == receipt["allocation_id"]
    )
    with sqlite3.connect(receipt["ledger_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 0


def test_same_authorization_cannot_recreate_pool_even_after_directory_removed(activated):
    root, plan, authorization, document, *_ = activated
    shutil.rmtree(root / ".cache/final48-allocation")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_ALREADY_ACTIVATED"):
        alloc.activate_allocation(plan, authorization, document, project_root=root)
    assert not (root / ".cache/final48-allocation").exists()


@pytest.mark.parametrize("mutation", ["profile", "receipt", "copied_db", "foreign_env"])
def test_changed_binding_refused(activated, monkeypatch, mutation):
    root, _, _, _, receipt, path, *_ = activated
    if mutation == "profile":
        profile_path = Path(receipt["profile_path"])
        profile_path.write_text(profile_path.read_text() + " ")
    elif mutation == "receipt":
        changed = json.loads(path.read_text())
        changed["amounts"]["approved_net_usd"] = "4"
        path.write_text(json.dumps(changed))
    elif mutation == "copied_db":
        ledger = Path(receipt["ledger_path"])
        backup = ledger.with_suffix(".old")
        ledger.rename(backup)
        shutil.copyfile(backup, ledger)
    else:
        monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(root / ".cache/budget.db"))
    with pytest.raises((alloc.AllocationRefused, LedgerPathError)):
        alloc.verify_receipt(path, project_root=root)


def test_fixed_f1_inputs_caps_and_single_execution_claim(activated):
    with pytest.raises(alloc.AllocationRefused, match="F1_INPUT_BINDING_CHANGED"):
        claim(activated, preparation_sha256="0" * 64)
    with pytest.raises(alloc.AllocationRefused, match="TASK_LIMIT_EXCEEDED"):
        claim(activated, run_limit_usd="1.51")
    with pytest.raises(alloc.AllocationRefused, match="TASK_SCOPE_NOT_AUTHORIZED"):
        claim(activated, task_scope="unapproved_task")
    binding = claim(activated)
    binding.revalidate()
    alloc.finish_claim(binding, status="failed")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_CLAIM_NOT_ACTIVE"):
        binding.revalidate()
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        claim(activated, execution_key="new-key-cannot-reset-F1")


def test_f1_live_entry_requires_receipt_before_loading_inputs():
    with pytest.raises(f1.F1Refused, match="ALLOCATION_RECEIPT_REQUIRED"):
        f1.execute_f1(
            "/missing",
            profile_path="/missing",
            daily_limit_usd="1.5",
            execute=True,
            live_authorized=True,
        )


def test_f1_real_runtime_uses_bound_new_ledger_and_preserves_old_unknown(activated):
    root, _, _, _, receipt, path, prepared, prepared_path, credentials, before = activated
    transport, requests = transport_for(prepared, prepared_path)
    result = f1.execute_f1(
        prepared_path,
        profile_path=receipt["profile_path"],
        daily_limit_usd="3",
        execute=True,
        live_authorized=True,
        transport=transport,
        env_file=credentials,
        allocation_receipt=path,
    )
    assert len(requests) == 27, result
    assert result["study_complete_within_budget"] is True
    runtime = json.loads((prepared_path.parent / "execution/runtime/runtime.json").read_text())
    assert runtime["allocation"]["id"] == receipt["allocation_id"]
    assert runtime["allocation"]["scope"] == "F1"
    with sqlite3.connect(receipt["ledger_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 27
    assert alloc.historical_snapshot(root) == before
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        claim(activated)


def test_concurrent_f1_once_claim_allows_exactly_one_execution(activated):
    ready = Barrier(2)

    def attempt():
        ready.wait(timeout=5)
        try:
            return claim(activated)
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: attempt(), range(2)))
    winners = [result for result in outcomes if isinstance(result, alloc.AllocationBinding)]
    assert len(winners) == 1
    assert outcomes.count("ALLOCATION_EXECUTION_ALREADY_CLAIMED") == 1
    winners[0].revalidate()


def test_f1_revalidates_allocation_before_the_second_request(activated):
    _, _, _, _, receipt, path, prepared, prepared_path, credentials, _ = activated
    original, requests = transport_for(prepared, prepared_path)
    profile_path = Path(receipt["profile_path"])

    def handle(request):
        response = original.handle_request(request)
        if len(requests) == 1:
            profile_path.write_text(profile_path.read_text() + " ")
        return response

    result = f1.execute_f1(
        prepared_path,
        profile_path=profile_path,
        daily_limit_usd="3",
        execute=True,
        live_authorized=True,
        transport=httpx.MockTransport(handle),
        env_file=credentials,
        allocation_receipt=path,
    )
    assert len(requests) == 1
    assert result["stop_reason"] == "AllocationRefused"
    assert not result["completed_all_requests"]
    assert all(row["status"] == "not_executed" for row in result["rows"][1:])
