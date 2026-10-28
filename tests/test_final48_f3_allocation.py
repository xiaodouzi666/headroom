"""F3 allocation tests activate temporary offline fixtures, never the project pool."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414

from headroom.acceptance import allocation as alloc
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.orchestrator import FixRequest


@pytest.fixture
def f3_pool(tmp_path, request):
    approved_daily = getattr(request, "param", "6")
    root = tmp_path / "offline-project"
    root.mkdir()
    old = BudgetLedger(root / ".cache/budget.db", total_limit="6", daily_limit="6")
    old.open_run("offline-old", "0.1")
    old.reserve("offline-old", "offline-unknown", "0.01")
    old.settle("offline-old", "offline-unknown", None)
    historical = alloc.historical_snapshot(root)
    profile_path, _ = profile(root)
    document = json.loads(profile_path.read_text())
    document["authorized_total_usd"] = "6"
    document["available_credit_usd"] = "8"
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6",
        "available_gift_usd": "8",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": approved_daily,
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.5"
    plan["task_run_caps_usd"]["F3"] = "4"
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    bound_profile = root / ".cache/final48-allocation/runtime-profile.json"
    requests = {
        f"cell-{i}": FixRequest(
            script=f"offline-{i}.py",
            budget_usd="0.6",
            daily_budget_usd=approved_daily,
            runtime_profile=str(bound_profile),
            research_enabled=False,
        )
        for i in range(12)
    }
    cells = {key: alloc.request_sha256(value) for key, value in requests.items()}
    plan["task_pins"]["F3"] = {
        "preparation_sha256": "4" * 64,
        "cell_requests_sha256": alloc.digest(cells),
    }
    authorization = {
        "state": "authorized",
        "scope": "FINAL48",
        "approved_net_usd": "6",
        "approval_message_ref": "offline-fixture-not-human-authorization",
        "statement_sha256": "5" * 64,
    }
    receipt = alloc.activate_allocation(plan, authorization, document, project_root=root)
    receipt_path = root / ".cache/final48-allocation/receipt.json"
    return root, receipt, receipt_path, requests, cells, historical


def parent_for(pool, **overrides):
    root, _, path, _, cells, _ = pool
    return alloc.claim_f3_parent(
        path,
        **(
            {
                "project_root": root,
                "preparation_sha256": "4" * 64,
                "cell_requests": cells,
                "scope_limit_usd": "4",
            }
            | overrides
        ),
    )


def child_for(pool, parent, index=0):
    request = pool[3][f"cell-{index}"]
    binding = alloc.claim_f3_child(
        parent, cell_id=f"cell-{index}", request=request, run_id=f"offline-child-{index}"
    )
    verified = alloc.verify_child_binding(
        binding, request=request, run_id=binding["run_id"], environ={}
    )
    budget = BudgetLedger(
        verified.database.path,
        require_existing=True,
        expected_identity=verified.database.file_identity,
        total_limit=verified.total_limit_usd,
        daily_limit=verified.daily_limit_usd,
    )
    return request, binding, verified, budget


def settle_child(binding, budget, actual="0.3", *, close=True):
    run_id = binding["run_id"]
    budget.open_run(run_id, binding["run_limit_usd"])
    budget.reserve(run_id, run_id + "-attempt", binding["run_limit_usd"])
    budget.settle(run_id, run_id + "-attempt", actual)
    if close:
        budget.close_run(run_id)


def test_f3_requires_pinned_twelve_inputs_and_scope_cap(f3_pool):
    with pytest.raises(alloc.AllocationRefused, match="F3_SCOPE_LIMIT_EXCEEDED"):
        parent_for(f3_pool, scope_limit_usd="4.01")
    with pytest.raises(alloc.AllocationRefused, match="F3_INPUT_BINDING_CHANGED"):
        parent_for(f3_pool, preparation_sha256="0" * 64)
    altered = dict(f3_pool[4])
    altered["cell-0"] = "0" * 64
    with pytest.raises(alloc.AllocationRefused, match="F3_INPUT_BINDING_CHANGED"):
        parent_for(f3_pool, cell_requests=altered)
    with pytest.raises(alloc.AllocationRefused, match="F3_PARENT_CHILD_BINDING_REQUIRED"):
        alloc.verify_and_claim_allocation(
            f3_pool[2],
            project_root=f3_pool[0],
            task_scope="F3",
            execution_key="bypass",
            profile_path=f3_pool[1]["profile_path"],
            run_limit_usd="4",
            daily_limit_usd="6",
        )


def test_parent_once_is_atomic_and_never_resets(f3_pool):
    barrier = Barrier(2)

    def attempt():
        barrier.wait(timeout=5)
        try:
            return parent_for(f3_pool)
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: attempt(), range(2)))
    parent = next(row for row in outcomes if isinstance(row, dict))
    assert outcomes.count("ALLOCATION_EXECUTION_ALREADY_CLAIMED") == 1
    alloc.finish_f3_parent(parent, status="stopped")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_EXECUTION_ALREADY_CLAIMED"):
        parent_for(f3_pool)


def test_twelve_children_share_one_ledger_and_do_not_reset_scope(f3_pool):
    parent = parent_for(f3_pool)
    for index in range(12):
        _, binding, verified, budget = child_for(f3_pool, parent, index)
        assert verified.total_limit_usd == "4"
        assert verified.database.path == Path(f3_pool[1]["ledger_path"])
        settle_child(binding, budget)
        result = alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)
        assert result["status"] == "settled"
    state = alloc.f3_accounting(parent)
    assert state["scope_spent_usd"] == "3.6"
    assert state["status"] == "settled"
    alloc.finish_f3_parent(parent, status="completed")
    assert alloc.historical_snapshot(f3_pool[0]) == f3_pool[5]
    with sqlite3.connect(f3_pool[1]["ledger_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_runs").fetchone()[0] == 12
        assert conn.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 12


def test_fixed_total_ceiling_enforces_f3_cap_after_prior_other_task_cost(f3_pool):
    receipt = f3_pool[1]
    shared = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="6")
    shared.open_run("prior-f1", "1")
    shared.reserve("prior-f1", "prior-attempt", "1")
    shared.settle("prior-f1", "prior-attempt", "1")
    shared.close_run("prior-f1")
    parent = parent_for(f3_pool)
    assert parent["prior_charged_usd"] == "1"
    assert parent["total_limit_usd"] == "5"
    for index in range(6):
        _, binding, verified, budget = child_for(f3_pool, parent, index)
        assert verified.total_limit_usd == "5"
        settle_child(binding, budget, actual="0.6")
        assert (
            alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )
    with pytest.raises(alloc.AllocationRefused, match="F3_SCOPE_EXHAUSTED"):
        child_for(f3_pool, parent, 6)
    assert alloc.f3_accounting(parent)["scope_spent_usd"] == "3.6"
    # Even bypassing the driver cannot open another full child using the fixed ceiling.
    with pytest.raises(BudgetExceeded):
        budget.open_run("cannot-reset-to-four", "0.6")


@pytest.mark.parametrize("case", ["unknown", "pending", "open", "cleanup"])
def test_unsettled_child_blocks_next_even_if_retained_bound_exists(f3_pool, case):
    parent = parent_for(f3_pool)
    _, binding, _, budget = child_for(f3_pool, parent)
    run_id = binding["run_id"]
    budget.open_run(run_id, "0.6")
    budget.reserve(run_id, "attempt", "0.6")
    if case == "unknown":
        budget.settle(run_id, "attempt", None)
    elif case != "pending":
        budget.settle(run_id, "attempt", "0.1")
    if case != "open":
        budget.close_run(run_id)
    result = alloc.finish_f3_child(
        binding, execution_terminal=True, cleanup_verified=case != "cleanup"
    )
    assert result["status"] == "blocked"
    assert (
        result["actual_usd"] is None
        if case in {"unknown", "pending"}
        else result["actual_usd"] == "0.1"
    )
    with pytest.raises(alloc.AllocationRefused, match="F3_PREVIOUS_CHILD_UNSETTLED"):
        child_for(f3_pool, parent, 1)
    assert alloc.f3_accounting(parent)["status"] == "blocked"


def test_child_cannot_be_reclaimed_or_changed_and_checks_queued_request(f3_pool):
    parent = parent_for(f3_pool)
    request, binding, _, budget = child_for(f3_pool, parent)
    for altered_request in (
        request.model_copy(update={"script": "prepared-different-path.py"}),
        request.model_copy(update={"budget_usd": "0.61"}),
    ):
        with pytest.raises(alloc.AllocationRefused, match="F3_CHILD_REQUEST_CHANGED"):
            alloc.verify_child_binding(binding, request=altered_request, run_id=binding["run_id"])
    with pytest.raises(alloc.AllocationRefused, match="F3_CHILD_RUN_CHANGED"):
        alloc.verify_child_binding(binding, request=request, run_id="different")
    altered = dict(binding, total_limit_usd="6")
    altered["binding_sha256"] = alloc.digest(
        {k: v for k, v in altered.items() if k != "binding_sha256"}
    )
    with pytest.raises(alloc.AllocationRefused, match="F3_CHILD_NOT_REGISTERED"):
        alloc.verify_child_binding(altered, request=request, run_id=binding["run_id"])
    settle_child(binding, budget)
    alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)
    with pytest.raises(alloc.AllocationRefused, match="F3_CHILD_ALREADY_CLAIMED"):
        alloc.claim_f3_child(parent, cell_id="cell-0", request=request, run_id="new-id")


def test_concurrent_children_allow_only_one_active_claim(f3_pool):
    parent = parent_for(f3_pool)
    barrier = Barrier(2)

    def attempt(index):
        barrier.wait(timeout=5)
        try:
            return alloc.claim_f3_child(
                parent,
                cell_id=f"cell-{index}",
                request=f3_pool[3][f"cell-{index}"],
                run_id=f"concurrent-{index}",
            )
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(attempt, range(2)))
    assert sum(isinstance(row, dict) for row in outcomes) == 1
    assert outcomes.count("F3_PREVIOUS_CHILD_UNSETTLED") == 1


def test_pre_dispatch_startup_failure_can_settle_zero_without_fabricating_model_usage(f3_pool):
    parent = parent_for(f3_pool)
    _, binding, _, _ = child_for(f3_pool, parent)
    result = alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled"
    assert result["actual_usd"] == "0"
    with sqlite3.connect(f3_pool[1]["ledger_path"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM budget_attempts").fetchone()[0] == 0


def test_receipt_and_profile_revalidated_after_child_claim(f3_pool):
    parent = parent_for(f3_pool)
    request, binding, _, _ = child_for(f3_pool, parent)
    path = Path(f3_pool[1]["profile_path"])
    path.write_text(path.read_text() + " ")
    with pytest.raises(alloc.AllocationRefused, match="ALLOCATION_PROFILE_CHANGED"):
        alloc.verify_child_binding(binding, request=request, run_id=binding["run_id"])


def test_new_pool_unknown_stops_parent_without_using_old_unknown_as_blocker(f3_pool):
    receipt = f3_pool[1]
    budget = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="6")
    budget.open_run("new-unknown", "0.6")
    budget.reserve("new-unknown", "new-attempt", "0.6")
    budget.settle("new-unknown", "new-attempt", None)
    budget.close_run("new-unknown")
    with pytest.raises(alloc.AllocationRefused, match="F3_NEW_POOL_UNSETTLED"):
        parent_for(f3_pool)
    with sqlite3.connect(f3_pool[0] / ".cache/final48-allocation-registry.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM f3_parents").fetchone()[0] == 0
    assert alloc.historical_snapshot(f3_pool[0]) == f3_pool[5]


def test_request_hash_normalizes_real_queue_python_dump_and_rejects_extra_fields(f3_pool):
    request = f3_pool[3]["cell-0"]
    assert alloc.request_sha256(request) == alloc.request_sha256(request.model_dump())
    assert alloc.request_sha256(request) == alloc.request_sha256(request.model_dump(mode="json"))
    parent = parent_for(f3_pool)
    binding = alloc.claim_f3_child(
        parent, cell_id="cell-0", request=request.model_dump(), run_id="canonical-child"
    )
    alloc.verify_child_binding(binding, request=request, run_id="canonical-child")
    with pytest.raises(alloc.AllocationRefused, match="F3_REQUEST_REQUIRED"):
        alloc.request_sha256(request.model_dump() | {"unreviewed_field": "extra"})


@pytest.mark.parametrize(
    ("f3_pool", "allowed_children"), [("6", 12), ("4", 7)], indirect=["f3_pool"]
)
def test_prior_f1_cost_preserves_f3_scope_without_raising_approved_daily_limit(
    f3_pool, allowed_children
):
    receipt = f3_pool[1]
    approved_daily = receipt["amounts"]["daily_limit_usd"]
    shared = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit=approved_daily)
    shared.open_run("completed-f1", "1.5")
    shared.reserve("completed-f1", "known-f1-attempt", "1.5")
    shared.settle("completed-f1", "known-f1-attempt", "1.5")
    shared.close_run("completed-f1")
    parent = parent_for(f3_pool)
    assert parent["prior_charged_usd"] == "1.5"
    assert parent["scope_limit_usd"] == "4"
    assert parent["total_limit_usd"] == "5.5"

    for index in range(allowed_children):
        _, binding, verified, budget = child_for(f3_pool, parent, index)
        assert verified.daily_limit_usd == approved_daily
        assert verified.total_limit_usd == "5.5"
        settle_child(binding, budget, actual="0.3")
        assert (
            alloc.finish_f3_child(binding, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )

    if approved_daily == "6":
        accounting = alloc.f3_accounting(parent)
        assert accounting["scope_spent_usd"] == "3.6"
        assert accounting["new_pool_charged_usd"] == "5.1"
        assert accounting["status"] == "settled"
    else:
        _, binding, verified, budget = child_for(f3_pool, parent, allowed_children)
        assert verified.daily_limit_usd == "4"
        with pytest.raises(BudgetExceeded):
            budget.open_run(binding["run_id"], binding["run_limit_usd"])
        accounting = alloc.f3_accounting(parent)
        assert accounting["scope_spent_usd"] == "2.1"
        assert accounting["new_pool_charged_usd"] == "3.6"
        with sqlite3.connect(receipt["ledger_path"]) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM budget_runs WHERE id=?", (binding["run_id"],)
                ).fetchone()[0]
                == 0
            )
    assert alloc.historical_snapshot(f3_pool[0]) == f3_pool[5]
