"""Snapshot retries use temporary copies of the original shared pool; no provider/GPU."""

import hashlib
import shutil
from pathlib import Path

import pytest
from test_final48_ablation import offline as offline  # noqa: PLC0414
from test_snapshot_allocation_binding import pool as pool  # noqa: PLC0414

from headroom.acceptance import allocation as alloc
from headroom.acceptance import feature_allocation as feature
from headroom.acceptance import snapshot_retry as retry
from headroom.acceptance.demo_binding import DemoAllocation
from headroom.acceptance.snapshot_binding import snapshot_intent
from headroom.budget import BudgetLedger
from headroom.orchestrator import FixRequest
from headroom.runtime import read_live_profile


@pytest.fixture
def finished(pool, monkeypatch):
    original_prepare = alloc.prepare_allocation_plan

    def plan():
        document = original_prepare()
        document["task_run_caps_usd"]["F2_demo"] = "0.30"
        return document

    monkeypatch.setattr(alloc, "prepare_allocation_plan", plan)
    root, request, parent, _env = pool()
    monkeypatch.setattr(alloc, "prepare_allocation_plan", original_prepare)
    repo = Path(__file__).resolve().parents[1]
    for name in retry.CODE_FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / name, target)
    receipt = alloc.verify_receipt(parent["receipt_path"], project_root=root)
    budget = BudgetLedger(receipt["ledger_path"], total_limit="5", daily_limit="5")
    original = None
    for index, slot in enumerate(feature.GROUPS["F3b"]["slots"]):
        intent = snapshot_intent(request, daily_budget_usd="5")
        if slot == "watch-s1":
            intent = {**intent, "kind": "watch", "payload": {"fixture": "not-executed"}}
        child = feature.claim_feature_child(
            parent, slot_id=slot, intent=intent, run_id=f"{index + 1:032x}"
        )
        budget.open_run(child["run_id"], ".30")
        budget.reserve(child["run_id"], "old-" + slot, ".05")
        budget.settle(child["run_id"], "old-" + slot, ".05")
        budget.close_run(child["run_id"])
        feature.finish_feature_child(child, execution_terminal=True, cleanup_verified=True)
        if slot == "snapshot-s2":
            original = child
    feature.finish_feature_parent(parent, status="completed")
    demo = DemoAllocation(parent["receipt_path"], project_root=root)
    source = root / "demo-source" / "train.py"
    source.parent.mkdir()
    source.write_text("print('offline fixture')\n")
    demo_request = FixRequest(
        script=str(source),
        source_root=str(source.parent),
        runtime_profile=receipt["profile_path"],
        daily_budget_usd="5",
        budget_usd=".30",
    )
    return root, request, original, receipt, demo, demo_request, _env


def proposal(finished, *, revision="r1", run_id="b" * 32):
    _, request, original, _, _, _, _ = finished
    return retry.prepare_snapshot_retry(
        original,
        request,
        revision=revision,
        run_id=run_id,
        approval_ref="offline-synthetic-only",
        approval_sha256="a" * 64,
    )


def claim(finished, **kwargs):
    document = proposal(finished, **kwargs)
    binding = retry.claim_snapshot_retry(
        document, finished[1], expected_sha256=alloc.digest(document)
    )
    return binding


def ledger(finished, binding):
    return retry.snapshot_retry_budget_factory(binding)(
        binding["run_id"],
        finished[1],
        read_live_profile(finished[3]["profile_path"]).model_copy(
            update={"run_budget_mode": "strict_reservation"}
        ),
    )


def spend(finished, binding, amount=".10", *, cleanup=True):
    budget = ledger(finished, binding)
    run_id = binding["run_id"]
    budget.open_run(run_id, ".30")
    attempt_id = "retry-" + run_id
    budget.reserve(run_id, attempt_id, amount, dispatched=False)
    budget.mark_dispatched(run_id, attempt_id)
    budget.settle(run_id, attempt_id, amount)
    budget.close_run(run_id)
    return retry.finish_snapshot_retry(binding, execution_terminal=True, cleanup_verified=cleanup)


def test_retry_preserves_old_rows_and_uses_same_ledger_and_remaining_scope(finished):
    doc = proposal(finished)
    assert doc["scope_charged_usd"] == "0.20"
    assert doc["scope_cap_usd"] == "1"
    assert doc["total_limit_usd"] == "1.00"
    binding = retry.claim_snapshot_retry(doc, finished[1], expected_sha256=alloc.digest(doc))
    assert not finished[4].available
    assert ledger(finished, binding).path == Path(finished[3]["ledger_path"])
    outcome = spend(finished, binding)
    assert outcome["status"] == "settled" and outcome["actual_usd"] == "0.10"
    assert outcome["scope_charged_usd"] == "0.30"
    with alloc.registry(finished[0]) as conn:
        assert retry._original(conn, finished[2]) == doc["original_registry"]
    assert finished[4].available


def test_all_revisions_share_original_f3b_cap(finished):
    assert spend(finished, claim(finished), ".30")["status"] == "settled"
    assert (
        spend(finished, claim(finished, revision="r2", run_id="c" * 32), ".30")["status"]
        == "settled"
    )
    with pytest.raises(alloc.AllocationRefused, match="SCOPE_OR_POOL_EXHAUSTED"):
        proposal(finished, revision="r3", run_id="d" * 32)


def test_reviewed_proposal_and_content_are_pinned(finished):
    doc = proposal(finished)
    with pytest.raises(alloc.AllocationRefused, match="REVIEW_HASH"):
        retry.claim_snapshot_retry(doc, finished[1], expected_sha256="0" * 64)
    finished[1].snapshot.write_bytes(b"changed")
    with pytest.raises(alloc.AllocationRefused, match="INTENT_CHANGED"):
        retry.claim_snapshot_retry(doc, finished[1], expected_sha256=alloc.digest(doc))


@pytest.mark.parametrize("code_file", retry.CODE_FILES)
def test_code_rechecked_between_reservation_and_dispatch(finished, code_file):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "a", ".05", dispatched=False)
    (finished[0] / code_file).write_text("# changed reviewed source\n")
    with pytest.raises(alloc.AllocationRefused, match="CODE_CHANGED"):
        budget.mark_dispatched(binding["run_id"], "a")
    budget.cancel_undispatched(binding["run_id"], "a")
    budget.close_run(binding["run_id"])
    assert (
        retry.finish_snapshot_retry(binding, execution_terminal=True, cleanup_verified=True)[
            "status"
        ]
        == "settled"
    )


def test_profile_rechecked_before_new_budget(finished):
    binding = claim(finished)
    profile = read_live_profile(finished[3]["profile_path"]).model_copy(
        update={"run_budget_mode": "strict_reservation"}
    )
    Path(finished[3]["profile_path"]).write_text("{}")
    with pytest.raises(alloc.AllocationRefused, match="PROFILE_CHANGED"):
        retry.snapshot_retry_budget_factory(binding)(binding["run_id"], finished[1], profile)


@pytest.mark.parametrize("cleanup", [False, None])
def test_cleanup_uncertainty_blocks_shared_demo_and_further_retry(finished, cleanup):
    binding = claim(finished)
    assert spend(finished, binding, cleanup=cleanup)["status"] == "blocked"
    assert not finished[4].available
    with pytest.raises(alloc.AllocationRefused, match="UNSETTLED"):
        proposal(finished, revision="r2", run_id="c" * 32)


def test_unknown_charge_is_not_zero_and_blocks_retry(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    run_id = binding["run_id"]
    budget.open_run(run_id, ".30")
    budget.reserve(run_id, "a", ".05", dispatched=False)
    budget.mark_dispatched(run_id, "a")
    budget.settle(run_id, "a", None)
    budget.close_run(run_id)
    result = retry.finish_snapshot_retry(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "blocked" and result["actual_usd"] is None
    assert result["charged_usd"] == "0.05" and not result["cost_resolved"]
    assert not finished[4].available


def test_demo_claim_before_ledger_open_blocks_retry(finished):
    _, _, _, _, demo, request, _ = finished
    source_hash = hashlib.sha256(Path(request.script).read_bytes()).hexdigest()
    demo.begin("c" * 32, request, source_sha256=source_hash)
    with pytest.raises(alloc.AllocationRefused, match="DEMO_UNSETTLED"):
        proposal(finished)


def test_retry_claim_before_ledger_open_blocks_demo_and_old_feature(finished):
    claim(finished)
    _, _, _, _, demo, request, _ = finished
    source_hash = hashlib.sha256(Path(request.script).read_bytes()).hexdigest()
    with pytest.raises(alloc.AllocationRefused, match="DEMO_OTHER_RUN_UNSETTLED"):
        demo.begin("c" * 32, request, source_sha256=source_hash)
    with (
        alloc.registry(finished[0]) as conn,
        pytest.raises(alloc.AllocationRefused, match="FEATURE_OTHER_CHILD_UNSETTLED"),
    ):
        feature._quiet_registry(conn)


def test_foreign_run_and_modified_limit_fail_before_ledger_open(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    for run_id, limit in [("c" * 32, ".30"), (binding["run_id"], ".31")]:
        with pytest.raises(alloc.AllocationRefused, match="RUN_LIMIT_CHANGED"):
            budget.open_run(run_id, limit)
    assert alloc._budget_state(finished[3])["runs"].get(binding["run_id"]) is None


def test_revision_cannot_be_replayed_after_settlement(finished):
    binding = claim(finished)
    spend(finished, binding)
    with pytest.raises(alloc.AllocationRefused, match="REVISION_ALREADY_CLAIMED"):
        proposal(finished, run_id="c" * 32)


def test_input_rechecked_between_reservation_and_dispatch(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".30")
    budget.reserve(binding["run_id"], "a", ".05", dispatched=False)
    finished[1].snapshot.write_bytes(b"replacement after reservation")
    with pytest.raises(alloc.AllocationRefused, match="INPUT_CHANGED"):
        budget.mark_dispatched(binding["run_id"], "a")


def test_competing_demo_and_retry_claims_have_one_winner(finished):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    doc = proposal(finished)
    barrier = Barrier(2)
    _, request, _, _, demo, demo_request, _ = finished
    source_hash = hashlib.sha256(Path(demo_request.script).read_bytes()).hexdigest()

    def new_retry():
        barrier.wait()
        try:
            retry.claim_snapshot_retry(doc, request, expected_sha256=alloc.digest(doc))
            return "retry"
        except alloc.AllocationRefused:
            return "denied"

    def new_demo():
        barrier.wait()
        try:
            demo.begin("c" * 32, demo_request, source_sha256=source_hash)
            return "demo"
        except alloc.AllocationRefused:
            return "denied"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(new_retry), executor.submit(new_demo)]
        results = [future.result(timeout=10) for future in futures]
    assert results.count("denied") == 1
    assert len({result for result in results if result != "denied"}) == 1
    assert all(
        row["status"] == "closed" for row in alloc._budget_state(finished[3])["runs"].values()
    )


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("day", "1900-01-01"),
        ("limit_usd", "0.31"),
        ("budget_mode", "actual_usage"),
    ],
)
def test_raw_run_limits_and_day_cannot_change_before_reserve(finished, column, value):
    import sqlite3

    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".30")
    with sqlite3.connect(finished[3]["ledger_path"]) as conn:
        conn.execute(f"UPDATE budget_runs SET {column}=? WHERE id=?", (value, binding["run_id"]))
    with pytest.raises(alloc.AllocationRefused, match="RUN_LIMIT_CHANGED"):
        budget.reserve(binding["run_id"], "a", ".01", dispatched=False)
    assert not any(
        a["run_id"] == binding["run_id"] for a in alloc._budget_state(finished[3])["attempts"]
    )


@pytest.mark.parametrize(
    "field", ["run_limit_usd", "daily_limit_usd", "total_limit_usd", "scope_cap_usd"]
)
def test_resigned_caps_still_must_match_reviewed_proposal(finished, field):
    binding = claim(finished)
    changed = {k: v for k, v in binding.items() if k != "binding_sha256"}
    changed[field] = "100"
    with pytest.raises(alloc.AllocationRefused, match="REVIEW_CHANGED"):
        retry.verify_snapshot_retry(alloc._signed(changed), finished[1], run_id=binding["run_id"])


def test_factory_checks_complete_profile_not_only_total(finished):
    binding = claim(finished)
    profile = read_live_profile(finished[3]["profile_path"]).model_copy(
        update={"run_budget_mode": "strict_reservation", "authorized_total_usd": "6"}
    )
    with pytest.raises(alloc.AllocationRefused, match="PROFILE_CHANGED"):
        retry.snapshot_retry_budget_factory(binding)(binding["run_id"], finished[1], profile)


def test_normal_runtime_and_sdk_use_retry_ledger_without_runtime_injection(finished, monkeypatch):
    from test_snapshot_allocation_binding import sdk_runtime

    from headroom import snapshot_diagnosis as core
    from headroom.acceptance.snapshot_binding import snapshot_cleanup_verified

    root, request = finished[:2]
    binding = claim(finished, run_id="a" * 32)
    calls = sdk_runtime(monkeypatch, root, finished[6])
    result = core.run_snapshot_diagnosis(
        request,
        run_root=root / "runs/uploads",
        run_id=binding["run_id"],
        services=core.SnapshotServices(budget_factory=retry.snapshot_retry_budget_factory(binding)),
    )
    assert result["status"] == "completed" and len(calls) == 1
    assert result["provenance"] == "live_model"  # normal branch, synthetic SDK transport
    assert result["cost_usd"] == 0.0004
    cleanup = snapshot_cleanup_verified(root / "runs/uploads", binding["run_id"])
    assert cleanup is True
    outcome = retry.finish_snapshot_retry(
        binding, execution_terminal=True, cleanup_verified=cleanup
    )
    assert outcome["status"] == "settled" and outcome["actual_usd"] == "0.0004"
    assert result["verification"]["status"] == "not_run"
