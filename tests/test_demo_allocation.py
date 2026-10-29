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
def demo_pool(tmp_path, request):
    daily = getattr(request, "param", {}).get("daily", "6.43")
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
        "daily_limit_usd": daily,
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.50"
    plan["task_run_caps_usd"]["F2_demo"] = getattr(request, "param", {}).get("run_cap", ".30")
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
        daily_budget_usd=daily,
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
    owner, request, binding, ledger = begin(
        demo_pool, 1, controller(demo_pool, scope_limit_usd=".30")
    )
    assert ledger.daily_limit == Decimal("6.43")
    assert ledger.total_limit == Decimal("6.43")
    charge(binding, ledger, ".20")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    restarted = controller(demo_pool, scope_limit_usd=".30")
    assert restarted.available
    owner, request, binding, ledger = begin(demo_pool, 2, restarted)
    assert Decimal(request.budget_usd) == Decimal(".10")
    charge(binding, ledger, ".10")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not controller(demo_pool, scope_limit_usd=".30").available
    with pytest.raises(alloc.AllocationRefused, match="DEMO_SCOPE_EXHAUSTED"):
        controller(demo_pool, scope_limit_usd=".30").begin(
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


def registry_snapshot(pool):
    """Exact stored payload/settlement strings, including legacy scope rows."""
    with alloc.registry(pool["root"]) as conn:
        return {
            table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
            for table in ("f2_demo_scope", "f2_demo_runs", "claims")
        }


def test_v2_runs_share_pool_without_rewriting_legacy_rows(demo_pool):
    receipt_bytes = demo_pool["path"].read_bytes()
    legacy = controller(demo_pool, scope_limit_usd=".30")
    owner, _, old_binding, ledger = begin(demo_pool, 1, legacy)
    assert old_binding["schema"].endswith(".v1")
    charge(old_binding, ledger, ".20")
    assert (
        owner.finish(old_binding, execution_terminal=True, cleanup_verified=True)["status"]
        == "settled"
    )
    old_rows = registry_snapshot(demo_pool)
    state_before = alloc._budget_state(demo_pool["receipt"])
    for index in (2, 3):
        owner, request, binding, ledger = begin(demo_pool, index)
        assert binding["schema"].endswith(".v2")
        assert binding["run_cap_usd"] == "0.30"
        assert "scope_limit_usd" not in binding
        assert Decimal(request.budget_usd) == Decimal(".30")
        assert ledger.total_limit == ledger.daily_limit == Decimal("6.43")
        charge(binding, ledger, ".20")
        assert (
            owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )
    assert controller(demo_pool).available
    assert alloc._budget_state(demo_pool["receipt"])["charged"] == Decimal(".60")
    after_rows = registry_snapshot(demo_pool)
    assert after_rows["f2_demo_scope"] == old_rows["f2_demo_scope"]
    assert after_rows["f2_demo_runs"][0] == old_rows["f2_demo_runs"][0]
    assert after_rows["claims"][0] == old_rows["claims"][0]
    state_after = alloc._budget_state(demo_pool["receipt"])
    assert state_after["runs"][old_binding["run_id"]] == state_before["runs"][old_binding["run_id"]]
    assert state_after["attempts"][0] == state_before["attempts"][0]
    assert demo_pool["path"].read_bytes() == receipt_bytes
    assert alloc.historical_snapshot(demo_pool["root"]) == demo_pool["history"]


def test_new_controller_can_finish_active_v1_without_migrating_it(demo_pool):
    _, _request, binding, ledger = begin(demo_pool, 1, controller(demo_pool, scope_limit_usd=".30"))
    before = registry_snapshot(demo_pool)
    assert not controller(demo_pool).available
    assert registry_snapshot(demo_pool) == before
    ledger.reserve(binding["run_id"], "old-active", ".10")
    ledger.settle(binding["run_id"], "old-active", ".10")
    ledger.close_run(binding["run_id"])
    result = controller(demo_pool).finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    after = registry_snapshot(demo_pool)
    assert after["f2_demo_scope"] == before["f2_demo_scope"]
    # Only the ordinary terminal state/settlement changes; no payload migration.
    assert after["f2_demo_runs"][0][2] == before["f2_demo_runs"][0][2]
    assert json.loads(after["f2_demo_runs"][0][2]) == binding


def test_all_other_tasks_count_against_demo_pool(demo_pool):
    receipt = demo_pool["receipt"]
    other = BudgetLedger(receipt["ledger_path"], daily_limit="6.43", total_limit="6.43")
    for name, amount in (
        ("f1-existing", "1.50"),
        ("f3-existing", "4"),
        ("feature-existing", ".70"),
    ):
        other.open_run(name, amount)
        other.reserve(name, name + "-attempt", amount)
        other.settle(name, name + "-attempt", amount)
        other.close_run(name)
    owner, request, binding, ledger = begin(demo_pool, 1)
    assert Decimal(request.budget_usd) == Decimal(".23")
    assert Decimal(binding["total_limit_usd"]) == Decimal("6.43")
    charge(binding, ledger, ".23")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not controller(demo_pool).available
    with pytest.raises(alloc.AllocationRefused, match="DEMO_SCOPE_EXHAUSTED"):
        begin(demo_pool, 2)
    assert alloc._budget_state(receipt)["charged"] == Decimal("6.43")


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "headroom.final48.demo-run.v3"),
        ("run_cap_usd", ".31"),
        ("run_limit_usd", ".31"),
        ("daily_limit_usd", "7"),
        ("total_limit_usd", "7"),
    ],
)
def test_v2_changed_limits_are_rejected_even_if_registry_payload_is_changed(
    demo_pool, field, value
):
    from headroom.acceptance.demo_binding import verify_demo_binding

    owner = controller(demo_pool)
    request, binding = owner.begin(
        f"{1:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
    )
    binding[field] = value
    with alloc.registry(demo_pool["root"]) as conn:
        conn.execute(
            "UPDATE f2_demo_runs SET payload=? WHERE run_id=?",
            (json.dumps(binding, sort_keys=True), binding["run_id"]),
        )
    with pytest.raises(alloc.AllocationRefused):
        verify_demo_binding(binding, request, binding["run_id"])
    assert not alloc._budget_state(demo_pool["receipt"])["attempts"]


@pytest.mark.parametrize("change", ["receipt", "profile", "run_limit", "budget_mode"])
def test_v2_second_reserve_rechecks_binding_and_real_run_limit(demo_pool, change):
    _, _, binding, ledger = begin(demo_pool, 1)
    ledger.reserve(binding["run_id"], "first", ".01")
    ledger.settle(binding["run_id"], "first", ".01")
    if change == "receipt":
        demo_pool["path"].write_text("{}")
    elif change == "profile":
        from pathlib import Path

        Path(demo_pool["receipt"]["profile_path"]).write_text("{}")
    else:
        field, value = (
            ("limit_usd", ".31") if change == "run_limit" else ("budget_mode", "actual_usage")
        )
        with ledger._transaction() as conn:
            conn.execute(f"UPDATE budget_runs SET {field}=? WHERE id=?", (value, binding["run_id"]))
    with pytest.raises((alloc.AllocationRefused, ValueError)):
        ledger.reserve(binding["run_id"], "second", ".01")
    assert len(alloc._budget_state(demo_pool["receipt"])["attempts"]) == 1


def test_bound_ledger_cannot_open_larger_or_different_run(demo_pool):
    owner = controller(demo_pool)
    request, binding = owner.begin(
        f"{1:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
    )
    ledger = demo_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(demo_pool["receipt"]["profile_path"])
    )
    with pytest.raises(alloc.AllocationRefused, match="DEMO_RUN_LIMIT_CHANGED"):
        ledger.open_run(binding["run_id"], ".31")
    with pytest.raises(alloc.AllocationRefused, match="DEMO_RUN_LIMIT_CHANGED"):
        ledger.open_run("other", ".30")
    ledger.open_run(binding["run_id"], ".30")
    with pytest.raises(alloc.AllocationRefused, match="DEMO_RUN_CHANGED"):
        ledger.reserve("other", "wrong-run", ".01")
    from headroom.budget import BudgetExceeded

    with pytest.raises(BudgetExceeded, match="Run budget"):
        ledger.reserve(binding["run_id"], "too-large", ".31")
    assert not alloc._budget_state(demo_pool["receipt"])["attempts"]


@pytest.mark.parametrize("demo_pool", [{"daily": ".30"}], indirect=True)
def test_real_daily_limit_still_blocks_before_any_model_attempt(demo_pool):
    from headroom.budget import BudgetExceeded

    owner, _, binding, ledger = begin(demo_pool, 1)
    charge(binding, ledger, ".20")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    owner = controller(demo_pool)
    request, binding = owner.begin(
        f"{2:032x}", demo_pool["request"], source_sha256=demo_pool["sha"]
    )
    ledger = demo_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(demo_pool["receipt"]["profile_path"])
    )
    assert ledger.daily_limit == Decimal(".30")
    with pytest.raises(BudgetExceeded, match="Daily budget"):
        ledger.open_run(binding["run_id"], request.budget_usd)
    assert len(alloc._budget_state(demo_pool["receipt"])["attempts"]) == 1


@pytest.mark.parametrize("demo_pool", [{"run_cap": ".20"}], indirect=True)
def test_v2_honors_lower_receipt_task_run_cap(demo_pool):
    from headroom.acceptance.demo_binding import verify_demo_binding

    with pytest.raises(alloc.AllocationRefused, match="DEMO_SCOPE_NOT_AUTHORIZED"):
        controller(demo_pool)
    _owner, request, binding, _ledger = begin(
        demo_pool, 1, controller(demo_pool, run_limit_usd=".20")
    )
    assert Decimal(request.budget_usd) == Decimal(".20")
    binding["run_cap_usd"] = ".30"
    with alloc.registry(demo_pool["root"]) as conn:
        conn.execute(
            "UPDATE f2_demo_runs SET payload=? WHERE run_id=?",
            (json.dumps(binding, sort_keys=True), binding["run_id"]),
        )
    with pytest.raises(alloc.AllocationRefused, match="DEMO_BINDING_LIMIT_CHANGED"):
        verify_demo_binding(binding, request, binding["run_id"])
    assert not alloc._budget_state(demo_pool["receipt"])["attempts"]
