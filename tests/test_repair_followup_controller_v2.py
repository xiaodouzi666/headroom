"""Controller v2 accounting uses temporary ledgers; provider/GPU dispatch is forbidden."""

import hashlib
import importlib.machinery
import importlib.util
import json
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.acceptance.allocation import AllocationRefused
from headroom.budget import BudgetLedger
from headroom.orchestrator import FixRequest

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "reports/repair-followup-20261030/execute-fixed9-v2.py.txt"
R12_HASH = "ee21edd154eb5a3a7ff99aa302555c45cc22af8f91e298444d2057bd9da51544"
CAP = "4.890504400"


@pytest.fixture(autouse=True)
def no_dispatch(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Provider/network/GPU/worker subprocess forbidden in offline controller tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)


@pytest.fixture
def controller():
    loader = importlib.machinery.SourceFileLoader(
        "repair_followup_controller_v2_offline", str(CONTROLLER)
    )
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture
def pool(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.db", daily_limit=CAP, total_limit=CAP)
    ledger.require_actual_pool()
    return ledger, {"ledger_path": str(ledger.path), "target_net_usd": CAP}


def charge(ledger, *, run_id="historical", amount=".10", actual=".10", close=True):
    ledger.open_run(run_id, ".60", budget_mode="actual_usage")
    ledger.reserve(run_id, run_id + "-attempt", amount)
    ledger.settle(run_id, run_id + "-attempt", actual)
    if close:
        ledger.close_run(run_id)


def test_r12_controller_bytes_and_read_only_v1_copy_are_unchanged():
    for name in ("execute-fixed9.py.txt", "execute-fixed9-v1-r12.py.txt"):
        path = CONTROLLER.with_name(name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == R12_HASH


def test_unknown_actual_is_reported_with_real_charge_remaining_halt_and_unresolved_rows(
    controller, pool
):
    ledger, receipt = pool
    charge(ledger, amount=".01644864", actual=None)
    state, summary = controller.accounting(receipt)
    assert Decimal(summary["scope_charged_usd"]) == Decimal(".01644864")
    assert summary["scope_actual_usd"] is None
    assert Decimal(summary["scope_remaining_usd"]) == Decimal(CAP) - Decimal(".01644864")
    assert summary["all_costs_known"] is False
    assert summary["all_costs_resolved"] is False
    assert summary["open_runs"] == []
    assert summary["halted_runs"][0]["halt_reason"] == "provider_charge_unknown"
    assert summary["unresolved_attempts"][0]["actual_usd"] is None
    assert summary["unresolved_attempts"][0]["charged_usd"] == "0.01644864"
    json.dumps(summary, allow_nan=False)
    with pytest.raises(AllocationRefused, match="UNSETTLED"):
        controller.require_admission(state, receipt)


def test_open_run_does_not_block_reading_but_still_blocks_admission(controller, pool):
    ledger, receipt = pool
    ledger.open_run("open", ".60", budget_mode="actual_usage")
    state, summary = controller.accounting(receipt)
    assert summary["open_runs"][0]["run_id"] == "open"
    assert summary["all_costs_resolved"] is True
    with pytest.raises(AllocationRefused, match="RUN_ACTIVE"):
        controller.require_admission(state, receipt)


def test_closed_resolved_historical_spend_is_kept_and_may_admit_a_fresh_campaign(controller, pool):
    ledger, receipt = pool
    charge(ledger)
    state, summary = controller.accounting(receipt)
    assert Decimal(summary["scope_charged_usd"]) == Decimal(".10")
    assert Decimal(summary["scope_actual_usd"]) == Decimal(".10")
    assert Decimal(summary["scope_remaining_usd"]) == Decimal(CAP) - Decimal(".10")
    assert summary["all_costs_known"] and summary["all_costs_resolved"]
    assert summary["open_runs"] == summary["halted_runs"] == []
    controller.require_admission(state, receipt)


def configure_main(controller, pool, tmp_path, monkeypatch):
    ledger, receipt = pool
    receipt["profile_path"] = str(tmp_path / "synthetic-profile.json")
    monkeypatch.setattr(controller, "ROOT", tmp_path)
    request = FixRequest(
        script=str(tmp_path / "synthetic-train.py"),
        runtime_profile=str(tmp_path / "synthetic-profile.json"),
        budget_usd=".60",
        daily_budget_usd=CAP,
    )
    cells = [
        {"cell_id": cell_id, "result_group": "fixed_nine", "case": {}, "policy_name": "strict"}
        for cell_id in controller.CELL_IDS
    ]
    prepared = {"cells": cells}
    requests = {cell["cell_id"]: request for cell in cells}
    monkeypatch.setattr(controller, "funding", lambda *args: receipt)
    monkeypatch.setattr(controller.repair, "verify_preparation", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(controller.repair, "bound_requests", lambda *args, **kwargs: requests)
    monkeypatch.setattr(
        controller.repair,
        "_empty_row",
        lambda *args: {
            "status": "not_run",
            "target_met": None,
            "cost_usd": None,
            "charged_usd": None,
            "run_id": None,
        },
    )
    monkeypatch.setattr(controller, "Scenario", SimpleNamespace(model_validate=lambda value: value))
    monkeypatch.setattr(
        controller, "result_row", lambda *args, **kwargs: {"status": "timeout", "target_met": True}
    )
    _, initial = controller.accounting(receipt)
    proposal = {
        "controller_sha256": hashlib.sha256(CONTROLLER.read_bytes()).hexdigest(),
        "funding_receipt_path": "unused-fixture-receipt.json",
        "funding_receipt_sha256": "a" * 64,
        "prepared_path": "unused-fixture-prepared.json",
        "preparation_sha256": "b" * 64,
        "requests": {key: value.model_dump(mode="json") for key, value in requests.items()},
        "starting_pool_accounting": initial,
        "revision": "offline-controller-fixture",
    }
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(proposal))
    output = tmp_path / "runs" / "fresh-campaign"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "controller",
            "--proposal",
            str(path),
            "--expected-sha256",
            controller.alloc.digest(proposal),
            "--output",
            str(output),
            "--execute-reviewed",
        ],
    )
    return ledger, output, proposal


@pytest.mark.parametrize("prior_spend", ["0", ".10"])
def test_finally_persists_unknown_cost_instead_of_stale_zero_and_does_not_retry(
    controller, pool, tmp_path, monkeypatch, prior_spend
):
    ledger, _ = pool
    if Decimal(prior_spend):
        charge(ledger, amount=prior_spend, actual=prior_spend)
    ledger, output, _ = configure_main(controller, pool, tmp_path, monkeypatch)
    dispatches = []

    def failed_child(request, **kwargs):
        dispatches.append(kwargs["run_id"])
        charge(ledger, run_id=kwargs["run_id"], amount=".01644864", actual=None)
        return {
            "status": "timeout",
            "evaluation_timing": {
                "cleanup_verified": False,
                "within_wall_limit": False,
                "cli": {"verified": True},
            },
        }

    monkeypatch.setattr(controller, "supervise_evaluation_run", failed_child)
    controller.main()
    document = json.loads((output / "campaign.json").read_text())
    assert len(dispatches) == 1
    assert document["status"] == "partial"
    assert document["stop_reason"] == "child_execution_or_cost_unverified"
    assert Decimal(document["starting_pool_accounting"]["scope_charged_usd"]) == Decimal(
        prior_spend
    )
    expected_charge = Decimal(prior_spend) + Decimal(".01644864")
    assert Decimal(document["accounting"]["scope_charged_usd"]) == expected_charge
    assert document["accounting"]["scope_actual_usd"] is None
    assert document["accounting"]["all_costs_resolved"] is False
    assert document["accounting"]["halted_runs"]
    assert Decimal(document["accounting"]["scope_remaining_usd"]) == Decimal(CAP) - expected_charge
    assert document["rows"][0]["target_met"] is False
    assert document["target_met_count"] == 0 and document["fixed_denominator"] == 9
    assert document["minimum_targets"] == 6
    assert len(document["rows"]) == 9
    assert all(
        row["target_met"] is row["charged_usd"] is row["run_id"] is None
        for row in document["rows"][1:]
    )


def test_changed_starting_pool_snapshot_stops_before_output_or_child(
    controller, pool, tmp_path, monkeypatch
):
    ledger, output, _ = configure_main(controller, pool, tmp_path, monkeypatch)
    charge(ledger)
    monkeypatch.setattr(
        controller,
        "supervise_evaluation_run",
        lambda *args, **kwargs: pytest.fail("Stale proposal must not dispatch"),
    )
    with pytest.raises(AssertionError):
        controller.main()
    assert not output.exists()


def unknown_child(ledger):
    def child(request, **kwargs):
        charge(ledger, run_id=kwargs["run_id"], amount=".01644864", actual=None)
        return {"status": "timeout", "evaluation_timing": {"cleanup_verified": False}}

    return child


def test_store_close_failure_still_refreshes_true_unknown_accounting_and_persists(
    controller, pool, tmp_path, monkeypatch
):
    ledger, output, _ = configure_main(controller, pool, tmp_path, monkeypatch)
    original_store = controller.Store

    def failing_store(path):
        real = original_store(path)

        def close():
            real.close()
            raise OSError("offline injected close failure")

        return SimpleNamespace(get_run=real.get_run, usage=real.usage, close=close)

    monkeypatch.setattr(controller, "Store", failing_store)
    monkeypatch.setattr(controller, "supervise_evaluation_run", unknown_child(ledger))
    with pytest.raises(OSError, match="close failure"):
        controller.main()
    document = json.loads((output / "campaign.json").read_text())
    assert document["status"] == "partial"
    assert document["store_close_error_type"] == "OSError"
    assert document["accounting"]["status"] == "observed"
    assert Decimal(document["accounting"]["scope_charged_usd"]) == Decimal(".01644864")
    assert document["accounting"]["scope_actual_usd"] is None
    assert document["accounting"]["all_costs_resolved"] is False
    assert document["accounting"]["halted_runs"]
    assert document["rows"][0]["target_met"] is False


def test_final_ledger_read_failure_marks_current_accounting_unavailable_and_keeps_old_snapshot_separate(
    controller, pool, tmp_path, monkeypatch
):
    ledger, output, _ = configure_main(controller, pool, tmp_path, monkeypatch)
    original_accounting = controller.accounting
    reads = []

    def fail_final(receipt):
        reads.append(True)
        if len(reads) == 3:
            raise OSError("offline injected final ledger read failure")
        return original_accounting(receipt)

    monkeypatch.setattr(controller, "accounting", fail_final)
    monkeypatch.setattr(controller, "supervise_evaluation_run", unknown_child(ledger))
    with pytest.raises(OSError, match="final ledger read failure"):
        controller.main()
    document = json.loads((output / "campaign.json").read_text())
    assert len(reads) == 3
    assert document["status"] == "partial"
    current = document["accounting"]
    assert current["status"] == "unavailable" and current["read_error_type"] == "OSError"
    for field in (
        "scope_charged_usd",
        "scope_actual_usd",
        "scope_encumbered_usd",
        "scope_remaining_usd",
        "all_costs_known",
        "all_costs_resolved",
        "open_runs",
        "halted_runs",
        "unresolved_attempts",
    ):
        assert current[field] is None
    assert document["last_known_accounting"]["status"] == "observed"
    assert Decimal(document["last_known_accounting"]["scope_charged_usd"]) == 0
    # The real temporary ledger still records the retained charge; no zero/refund was written.
    _, truth = original_accounting(pool[1])
    assert Decimal(truth["scope_charged_usd"]) == Decimal(".01644864")
    assert truth["scope_actual_usd"] is None and truth["all_costs_resolved"] is False
