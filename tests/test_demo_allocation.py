"""Real temporary allocation metadata and accounting; no provider or GPU execution."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414

from headroom.acceptance import allocation as alloc
from headroom.acceptance.demo_binding import DemoAllocation, demo_budget_factory
from headroom.budget import BudgetLedger
from headroom.orchestrator import FixRequest
from headroom.runtime import read_live_profile


@pytest.fixture
def demo_pool(tmp_path):
    root = tmp_path / "offline-project"
    root.mkdir()
    old = BudgetLedger(root / ".cache/budget.db", daily_limit="1", total_limit="1")
    old.open_run("historical", ".1")
    old.reserve("historical", "historical-unknown", ".01")
    old.settle("historical", "historical-unknown", None)
    history = alloc.historical_snapshot(root)
    original_profile, _ = profile(root)
    document = json.loads(original_profile.read_text())
    document.update(authorized_total_usd="6.43", available_credit_usd="10")
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6.43",
        "available_gift_usd": "10",
        "review_reserve_usd": "2",
        "tax_reserve_usd": "1",
        "daily_limit_usd": "6.43",
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.50"
    plan["task_run_caps_usd"]["F2_demo"] = ".30"
    plan["task_pins"]["F1"] = {
        "preparation_sha256": "2" * 64,
        "scoring_policy_sha256": "3" * 64,
    }
    receipt = alloc.activate_allocation(
        plan,
        {
            "state": "authorized",
            "scope": "FINAL48",
            "approved_net_usd": "6.43",
            "approval_message_ref": "offline-only-fixture",
            "statement_sha256": "4" * 64,
        },
        document,
        project_root=root,
    )
    source = root / "input"
    source.mkdir()
    script = source / "train.py"
    script.write_text("raise AssertionError('source must never run in these tests')\n")
    request = FixRequest(
        script=str(script),
        source_root=str(source),
        runtime_profile=receipt["profile_path"],
        daily_budget_usd="6.43",
        budget_usd=".30",
    )
    return {
        "root": root,
        "receipt": receipt,
        "path": root / ".cache/final48-allocation/receipt.json",
        "request": request,
        "source": script,
        "sha": hashlib.sha256(script.read_bytes()).hexdigest(),
        "history": history,
    }


def controller(pool, **kwargs):
    return DemoAllocation(pool["path"], project_root=pool["root"], **kwargs)


def begin(pool, index, owner=None):
    owner = owner or controller(pool)
    request, binding = owner.begin(f"{index:032x}", pool["request"], source_sha256=pool["sha"])
    ledger = demo_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    return owner, request, binding, ledger


def charge(binding, ledger, actual):
    attempt = binding["run_id"] + "-attempt"
    ledger.reserve(binding["run_id"], attempt, binding["run_limit_usd"])
    ledger.settle(binding["run_id"], attempt, actual)
    ledger.close_run(binding["run_id"])


def test_aggregate_cap_survives_restart_and_inherits_real_daily_limit(demo_pool):
    owner, request, binding, ledger = begin(demo_pool, 1)
    assert ledger.daily_limit == Decimal("6.43")
    assert ledger.total_limit == Decimal("6.43")
    charge(binding, ledger, ".20")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    restarted = controller(demo_pool)
    assert restarted.available
    owner, request, binding, ledger = begin(demo_pool, 2, restarted)
    assert Decimal(request.budget_usd) == Decimal(".10")
    charge(binding, ledger, ".10")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not controller(demo_pool).available
    with pytest.raises(alloc.AllocationRefused, match="DEMO_SCOPE_EXHAUSTED"):
        controller(demo_pool).begin(
            f"{3:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
        )
    assert alloc.historical_snapshot(demo_pool["root"]) == demo_pool["history"]


@pytest.mark.parametrize("cap", [".31", "0"])
def test_scope_cap_cannot_exceed_authorized_demo_limit(demo_pool, cap):
    with pytest.raises(alloc.AllocationRefused, match="DEMO_SCOPE_LIMIT_INVALID"):
        controller(demo_pool, scope_limit_usd=cap)


def test_source_mutation_between_requests_is_rejected_before_second_reserve(demo_pool):
    _, _, binding, ledger = begin(demo_pool, 1)
    ledger.reserve(binding["run_id"], "first", ".01")
    ledger.settle(binding["run_id"], "first", ".01")
    demo_pool["source"].write_text("changed source\n")
    with pytest.raises(alloc.AllocationRefused, match="DEMO_INPUT_CHANGED"):
        ledger.reserve(binding["run_id"], "second", ".01")
    assert len(alloc._budget_state(demo_pool["receipt"])["attempts"]) == 1


@pytest.mark.parametrize("case", ["unknown", "cleanup", "not_terminal"])
def test_unknown_or_unclean_run_blocks_next_demo_after_restart(demo_pool, case):
    owner, _, binding, ledger = begin(demo_pool, 1)
    charge(binding, ledger, None if case == "unknown" else ".1")
    result = owner.finish(
        binding, execution_terminal=case != "not_terminal", cleanup_verified=case != "cleanup"
    )
    assert result["status"] == "blocked"
    if case == "unknown":
        assert result["actual_usd"] is None
    assert not controller(demo_pool).available
    with pytest.raises(alloc.AllocationRefused):
        controller(demo_pool).begin(
            f"{2:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
        )


def test_parallel_demo_claims_cannot_spend_the_same_remaining_allowance(demo_pool):
    owner = controller(demo_pool)
    barrier = Barrier(2)

    def claim(index):
        barrier.wait(timeout=5)
        try:
            return owner.begin(
                f"{index:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
            )
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, [1, 2]))
    assert sum(isinstance(result, tuple) for result in results) == 1
    assert results.count("DEMO_PREVIOUS_RUN_UNSETTLED") == 1


@pytest.mark.parametrize("field,value", [("daily_budget_usd", ".30"), ("budget_usd", ".31")])
def test_request_cannot_replace_pool_day_limit_or_increase_per_run_cap(demo_pool, field, value):
    request = demo_pool["request"].model_copy(update={field: value})
    with pytest.raises(alloc.AllocationRefused, match="DEMO_REQUEST_CONFIGURATION_CHANGED"):
        controller(demo_pool).begin(f"{1:032x}", request, source_sha256=demo_pool["sha"])
