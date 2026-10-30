"""Temporary donor ledgers only: holds reduce availability without becoming charges."""

from decimal import Decimal

import test_demo_allocation as demos
import test_judge_binding as judges
import test_snapshot_public_binding as snapshots

from headroom.acceptance.allocation import _budget_state
from headroom.acceptance.demo_binding import demo_budget_factory
from headroom.acceptance.judge_binding import judge_budget_factory
from headroom.acceptance.snapshot_public_binding import snapshot_public_budget_factory
from headroom.budget import BudgetLedger
from headroom.runtime import read_live_profile

# Inherit the guard that denies provider/network/GPU and all production files/DBs.
offline = judges.offline
demo_pool = demos.demo_pool
pool = judges.pool
upload = snapshots.upload


def hold(pool, amount):
    ledger = BudgetLedger(
        pool["receipt"]["ledger_path"],
        daily_limit=pool["receipt"]["amounts"]["daily_limit_usd"],
        total_limit=pool["receipt"]["amounts"]["approved_net_usd"],
        require_existing=True,
        expected_identity=tuple(pool["receipt"]["ledger_identity"]),
    )
    ledger.encumber("offline-approved-transfer", amount, "b" * 64)
    state = _budget_state(pool["receipt"])
    assert state["charged"] == 0
    assert state["encumbered"] == Decimal(amount)
    assert state["attempts"] == []
    return ledger


def settle(ledger, binding, amount):
    ledger.reserve(binding["run_id"], "offline-attempt-" + binding["run_id"], amount)
    ledger.settle(binding["run_id"], "offline-attempt-" + binding["run_id"], amount)
    ledger.close_run(binding["run_id"])


def test_demo_hold_clips_run_without_reducing_binding_total_or_double_deducting(demo_pool):
    hold(demo_pool, "6.33")
    owner = demos.controller(demo_pool)
    assert owner.available
    request, binding = owner.begin("1" * 32, demo_pool["request"], source_sha256=demo_pool["sha"])
    assert Decimal(request.budget_usd) == Decimal(".10")
    assert Decimal(binding["total_limit_usd"]) == Decimal("6.43")
    ledger = demo_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(demo_pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    settle(ledger, binding, ".10")
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    assert Decimal(result["charged_usd"]) == Decimal(".10")
    state = _budget_state(demo_pool["receipt"])
    assert state["charged"] == Decimal(".10")
    assert state["encumbered"] == Decimal("6.33")
    assert not demos.controller(demo_pool).available


def test_judge_hold_clips_run_and_preserves_total_limit_for_ledger_admission(pool):
    hold(pool, "6.51")
    owner = judges.controller(pool)
    assert owner.available
    request, binding = owner.begin("2" * 32, pool["request"], source_sha256=pool["sha"])
    assert Decimal(request.budget_usd) == Decimal(".10")
    assert Decimal(binding["total_limit_usd"]) == Decimal("6.61")
    ledger = judge_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    settle(ledger, binding, ".10")
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    assert Decimal(result["charged_usd"]) == Decimal(".10")
    assert _budget_state(pool["receipt"])["encumbered"] == Decimal("6.51")
    assert not judges.controller(pool).available


def test_public_snapshot_uses_same_remaining_hold_once_and_no_synthetic_charge(pool, upload):
    hold(pool, "6.51")
    owner = snapshots.owner(pool)
    assert owner.available
    binding = owner.claim(upload, "3" * 32)
    request = upload.model_copy(update={"budget_usd": binding["run_limit_usd"]})
    assert Decimal(binding["run_limit_usd"]) == Decimal(".10")
    assert Decimal(binding["total_limit_usd"]) == Decimal("6.61")
    ledger = snapshot_public_budget_factory(binding, project_root=pool["root"])(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    settle(ledger, binding, ".10")
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    assert Decimal(result["charged_usd"]) == Decimal(".10")
    state = _budget_state(pool["receipt"])
    assert state["charged"] == Decimal(".10")
    assert state["encumbered"] == Decimal("6.51")
    assert not snapshots.owner(pool).available
    assert not judges.controller(pool).available
