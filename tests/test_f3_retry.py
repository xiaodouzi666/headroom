"""Bounded offline F3 revisions use synthetic temporary receipts and real ledgers."""

import copy
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_diagnosis_acceptance import profile
from test_final48_ablation import offline as offline  # noqa: PLC0414
from test_final48_repair import prepared as prepared  # noqa: PLC0414

from headroom.acceptance import allocation as alloc
from headroom.acceptance import f3_retry as retry
from headroom.acceptance import final48_repair as repair
from headroom.acceptance.demo_binding import DemoAllocation
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.cli_execution import allocation_budget_factory, verify_invocation_allocation
from headroom.ledger_path import BUDGET_DB_ENV
from headroom.orchestrator import FixRequest
from headroom.runtime import read_live_profile


@pytest.fixture
def finished(prepared, monkeypatch):
    root, original_path, pack = prepared
    BudgetLedger(root / ".cache/budget.db", total_limit="6", daily_limit="6")
    profile_path, _ = profile(root)
    document = json.loads(profile_path.read_text())
    document["authorized_total_usd"] = "6"
    document["available_credit_usd"] = "8"
    document["diagnosis_request_policy"] = repair.CONTROLS["request_policy"]
    plan = alloc.prepare_allocation_plan()
    plan["amounts"] = {
        "approved_net_usd": "6",
        "available_gift_usd": "8",
        "review_reserve_usd": "1",
        "tax_reserve_usd": "1",
        "daily_limit_usd": "6",
    }
    plan["balance_evidence_sha256"] = "1" * 64
    plan["task_run_caps_usd"]["F1"] = "1.5"
    plan["task_run_caps_usd"]["F2_demo"] = ".30"
    plan["task_run_caps_usd"]["F3"] = "4"
    plan["task_pins"]["F1"] = {"preparation_sha256": "2" * 64, "scoring_policy_sha256": "3" * 64}
    requests = repair.bound_requests(
        pack,
        profile_path=root / ".cache/final48-allocation/runtime-profile.json",
        daily_limit_usd="6",
    )
    pins = {key: alloc.request_sha256(value) for key, value in requests.items()}
    plan["task_pins"]["F3"] = {
        "preparation_sha256": pack["preparation_sha256"],
        "cell_requests_sha256": alloc.digest(pins),
    }
    receipt = alloc.activate_allocation(
        plan,
        {
            "state": "authorized",
            "scope": "FINAL48",
            "approved_net_usd": "6",
            "approval_message_ref": "offline-only",
            "statement_sha256": "5" * 64,
        },
        document,
        project_root=root,
    )
    receipt_path = root / ".cache/final48-allocation/receipt.json"
    parent = alloc.claim_f3_parent(
        receipt_path,
        project_root=root,
        preparation_sha256=pack["preparation_sha256"],
        cell_requests=pins,
        scope_limit_usd="4",
    )
    budget = BudgetLedger(receipt["ledger_path"], total_limit="6", daily_limit="6")
    for i, (name, request) in enumerate(requests.items()):
        child = alloc.claim_f3_child(parent, cell_id=name, request=request, run_id=f"old-{i}")
        budget.open_run(child["run_id"], ".60")
        budget.reserve(child["run_id"], f"old-attempt-{i}", ".05")
        budget.settle(child["run_id"], f"old-attempt-{i}", ".05")
        budget.close_run(child["run_id"])
        assert (
            alloc.finish_f3_child(child, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )
    alloc.finish_f3_parent(parent, status="completed")
    code = root / "fixture-implementation.txt"
    code.write_text("new implementation")
    monkeypatch.setattr(
        repair,
        "implementation_pins",
        lambda: {"fixture-implementation.txt": repair.file_record(code, 4096)},
    )
    current = repair.prepare_f3(project_root=root)
    path = root / "runs/new-preparation.json"
    path.write_text(json.dumps(current))
    demo = DemoAllocation(receipt_path, project_root=root)
    source = root / "demo-source/train.py"
    source.parent.mkdir()
    source.write_text("print('synthetic')\n")
    demo_request = FixRequest(
        script=str(source),
        source_root=str(source.parent),
        runtime_profile=receipt["profile_path"],
        budget_usd=".30",
        daily_budget_usd="6",
    )
    return SimpleNamespace(
        root=root,
        original_path=original_path,
        path=path,
        prepared=current,
        parent=parent,
        receipt=receipt,
        requests=requests,
        code=code,
        demo=demo,
        demo_request=demo_request,
    )


def proposal(f, revision="r8"):
    return retry.prepare_f3_retry(
        f.parent,
        f.path,
        original_prepared_path=f.original_path,
        expected_preparation_sha256=f.prepared["preparation_sha256"],
        revision=revision,
        approval_ref="offline-retry-only",
        approval_sha256="a" * 64,
    )


def claim(f, *, index=0, revision="r8", run_id=None):
    doc = proposal(f, revision)
    return retry.claim_f3_retry(
        doc,
        cell_id=retry.CELL_IDS[index],
        run_id=run_id or f"{index + 100:032x}",
        expected_sha256=alloc.digest(doc),
    )


def ledger(f, binding):
    request = f.requests[binding["cell_id"]]
    return retry.f3_retry_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(f.receipt["profile_path"])
    )


def spend(f, binding, amount=".10", *, cleanup=True):
    budget = ledger(f, binding)
    run_id = binding["run_id"]
    budget.open_run(run_id, ".60")
    budget.reserve(run_id, run_id + "-attempt", amount, dispatched=False)
    budget.mark_dispatched(run_id, run_id + "-attempt")
    budget.settle(run_id, run_id + "-attempt", amount)
    budget.close_run(run_id)
    return retry.finish_f3_retry(binding, execution_terminal=True, cleanup_verified=cleanup)


def test_independent_fixed9_keeps_all_original12_costs_and_same_ledger(finished):
    f = finished
    doc = proposal(f)
    assert doc["cell_ids"] == list(retry.CELL_IDS)
    assert doc["planned_cells"] == doc["fixed_denominator"] == 9
    assert doc["minimum_targets"] == 6 and not doc["additional_funding"]
    before = doc["original_registry"]
    assert retry.f3_retry_accounting(doc)["scope_charged_usd"] == "0.60"
    binding = claim(f)
    assert ledger(f, binding).path == Path(f.receipt["ledger_path"])
    assert binding["total_limit_usd"] == "4.00"
    result = spend(f, binding)
    assert result["scope_charged_usd"] == "0.70" and result["status"] == "settled"
    assert proposal(f)["original_registry"] == before
    with pytest.raises(alloc.AllocationRefused, match="ALREADY_CLAIMED"):
        claim(f, run_id="f" * 32)
    with pytest.raises(alloc.AllocationRefused, match="ALREADY_CLAIMED"):
        alloc.claim_f3_parent(
            f.parent["receipt_path"],
            project_root=f.root,
            preparation_sha256=f.parent["preparation_sha256"],
            cell_requests=f.parent["cell_requests"],
        )


def test_all_revisions_share_four_dollars_and_stop_before_partial_allowance(finished):
    f = finished
    for i in range(5):
        assert (
            spend(f, claim(f, revision=f"r{i}", run_id=f"{i + 200:032x}"), ".60")["status"]
            == "settled"
        )
    doc = proposal(f, "r6")
    assert retry.f3_retry_accounting(doc)["scope_remaining_usd"] == "0.40"
    with pytest.raises(alloc.AllocationRefused, match="SCOPE_OR_POOL_EXHAUSTED"):
        claim(f, revision="r6", run_id="e" * 32)


def test_other_f48_spend_reduces_pool_without_becoming_new_f3_allowance(finished):
    f = finished
    budget = BudgetLedger(f.receipt["ledger_path"], total_limit="6", daily_limit="6")
    budget.open_run("other-scope", "5")
    budget.reserve("other-scope", "other-attempt", "5")
    budget.settle("other-scope", "other-attempt", "5")
    budget.close_run("other-scope")
    with pytest.raises(alloc.AllocationRefused, match="SCOPE_OR_POOL_EXHAUSTED"):
        claim(f)


@pytest.mark.parametrize(
    "field", ["max_steps", "seed", "max_rounds", "budget_usd", "daily_budget_usd"]
)
def test_reviewed_request_cannot_change_controls(finished, field):
    binding = claim(finished)
    request = finished.requests[binding["cell_id"]]
    value = "0.59" if field.endswith("usd") else 1
    changed = request.model_copy(update={field: value})
    with pytest.raises(alloc.AllocationRefused, match="REQUEST_CHANGED"):
        retry.verify_f3_retry(binding, changed, run_id=binding["run_id"])


def test_original_input_source_cannot_be_swapped_under_same_path(finished):
    f = finished
    p = f.root / f.prepared["cells"][0]["case"]["script"]
    p.write_text("different workload\n")
    with pytest.raises(repair.F3Refused):
        proposal(f)


def test_reprepared_changed_workload_is_not_a_new_authorized_protocol(finished):
    f = finished
    changed = copy.deepcopy(f.prepared)
    changed["input_pins"]["new-source"] = {"sha256": "e" * 64, "bytes": 1}
    # The authentic old pack hash remains pinned in its once claim.
    original = json.loads(f.original_path.read_text())
    original["input_pins"] = changed["input_pins"]
    original.pop("preparation_sha256")
    original["preparation_sha256"] = repair.digest(original)
    f.original_path.write_text(json.dumps(original))
    with pytest.raises(alloc.AllocationRefused, match="ORIGINAL_PREPARATION_CHANGED"):
        proposal(f)


def test_code_changed_after_reservation_is_refused_before_dispatch(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".60")
    budget.reserve(binding["run_id"], "a", ".05", dispatched=False)
    finished.code.write_text("changed after reserve")
    with pytest.raises(repair.F3Refused, match="INPUTS_CHANGED"):
        budget.mark_dispatched(binding["run_id"], "a")
    budget.cancel_undispatched(binding["run_id"], "a")
    budget.close_run(binding["run_id"])
    assert (
        retry.finish_f3_retry(binding, execution_terminal=True, cleanup_verified=True)["status"]
        == "settled"
    )


def test_review_hash_and_extra_tier_refused(finished):
    doc = proposal(finished)
    with pytest.raises(alloc.AllocationRefused, match="REVIEW_CHANGED"):
        retry.claim_f3_retry(
            doc, cell_id=retry.CELL_IDS[0], run_id="a" * 32, expected_sha256="0" * 64
        )
    with pytest.raises(alloc.AllocationRefused, match="FIXED_NINE_ONLY"):
        retry.claim_f3_retry(
            doc, cell_id="hf-trainer", run_id="a" * 32, expected_sha256=alloc.digest(doc)
        )


def test_pending_claim_blocks_demo_and_reverse_gap_is_closed(finished):
    f = finished
    binding = claim(f)
    assert not f.demo.available
    with pytest.raises(alloc.AllocationRefused, match="OTHER_RUN_UNSETTLED"):
        f.demo.begin(
            "d" * 32,
            f.demo_request,
            source_sha256=repair.file_record(f.demo_request.script, 4096)["sha256"],
        )
    assert (
        retry.finish_f3_retry(binding, execution_terminal=True, cleanup_verified=True)["status"]
        == "settled"
    )
    _, demo_binding = f.demo.begin(
        "e" * 32,
        f.demo_request,
        source_sha256=repair.file_record(f.demo_request.script, 4096)["sha256"],
    )
    with pytest.raises(alloc.AllocationRefused, match="DEMO_UNSETTLED"):
        claim(f, index=1)
    assert (
        f.demo.finish(demo_binding, execution_terminal=True, cleanup_verified=True)["status"]
        == "settled"
    )


@pytest.mark.parametrize("cleanup", [False, None])
def test_cleanup_uncertainty_blocks_future_claims(finished, cleanup):
    result = spend(finished, claim(finished), cleanup=cleanup)
    assert result["status"] == "blocked"
    assert not finished.demo.available
    with pytest.raises(alloc.AllocationRefused, match="UNSETTLED"):
        claim(finished, index=1)


def test_unknown_cost_is_not_zero_or_a_settlement(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".60")
    budget.reserve(binding["run_id"], "unknown", ".10")
    budget.settle(binding["run_id"], "unknown", None)
    budget.close_run(binding["run_id"])
    result = retry.finish_f3_retry(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "blocked" and result["actual_usd"] is None
    assert result["cost_resolved"] is False


@pytest.mark.parametrize("mutation", ["run_id", "mode", "limit"])
def test_raw_ledger_open_cannot_change_bound_controls(finished, mutation):
    binding = claim(finished)
    budget = ledger(finished, binding)
    with pytest.raises(alloc.AllocationRefused, match="LEDGER_RUN_CHANGED"):
        budget.open_run(
            "other" if mutation == "run_id" else binding["run_id"],
            ".59" if mutation == "limit" else ".60",
            budget_mode="actual_usage" if mutation == "mode" else "strict_reservation",
        )


@pytest.mark.parametrize("mutation", ["limit", "day", "mode"])
def test_existing_ledger_tamper_fails_closed(finished, mutation):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".60")
    column, value = {
        "limit": ("limit_usd", ".59"),
        "day": ("day", "1900-01-01"),
        "mode": ("budget_mode", "actual_usage"),
    }[mutation]
    with sqlite3.connect(finished.receipt["ledger_path"]) as conn:
        conn.execute(f"UPDATE budget_runs SET {column}=? WHERE id=?", (value, binding["run_id"]))
    with pytest.raises(alloc.AllocationRefused, match="LEDGER_RUN_CHANGED"):
        retry.verify_f3_retry(
            binding, finished.requests[binding["cell_id"]], run_id=binding["run_id"]
        )


def test_cli_routes_schema_and_checks_selected_database_and_full_profile(finished, monkeypatch):
    binding = claim(finished)
    request = finished.requests[binding["cell_id"]]
    spec = SimpleNamespace(
        allocation_child_binding=binding,
        queued_request=request.model_dump(),
        run_id=binding["run_id"],
        feature_intent=None,
    )
    monkeypatch.setenv(BUDGET_DB_ENV, finished.receipt["ledger_path"])
    verified = verify_invocation_allocation(
        binding, spec.queued_request, spec.run_id, require_selected=True
    )
    assert verified.database.path == Path(finished.receipt["ledger_path"])
    factory = allocation_budget_factory(spec)
    profile = read_live_profile(finished.receipt["profile_path"])
    with pytest.raises(alloc.AllocationRefused, match="PROFILE_CHANGED"):
        factory(spec.run_id, request, profile.model_copy(update={"live_enabled": False}))
    assert factory(spec.run_id, request, profile).path == verified.database.path
    monkeypatch.setenv(BUDGET_DB_ENV, "/tmp/not-this-pool.db")
    with pytest.raises(ValueError, match="ENVIRONMENT_LEDGER_CONFLICT"):
        verify_invocation_allocation(
            binding, spec.queued_request, spec.run_id, require_selected=True
        )


def test_open_floor_cannot_reserve_beyond_per_run_allowance(finished):
    binding = claim(finished)
    budget = ledger(finished, binding)
    budget.open_run(binding["run_id"], ".60")
    with pytest.raises(BudgetExceeded):
        budget.reserve(binding["run_id"], "too-much", ".61")


def test_new_valid_preparation_with_altered_workload_still_rejected(finished):
    f = finished
    manifest = f.root / "eval/mvp_phase1_v2.yaml"
    data = json.loads(manifest.read_text())
    entry = data["scenarios"][0]
    source = f.root / entry["script"]
    source.write_text("raise AssertionError('changed synthetic input')\n")
    entry["source_sha256"] = repair.file_record(source, 4096)["sha256"]
    manifest.write_text(json.dumps(data))
    fresh = repair.prepare_f3(project_root=f.root)
    f.path.write_text(json.dumps(fresh))
    f.prepared = fresh
    with pytest.raises(alloc.AllocationRefused, match="ORIGINAL_INPUTS_CHANGED"):
        proposal(f)


def test_atomic_claims_cannot_race_same_revision_cell(finished):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    doc = proposal(finished)
    barrier = Barrier(2)

    def one(index):
        barrier.wait(timeout=5)
        try:
            return retry.claim_f3_retry(
                doc,
                cell_id=retry.CELL_IDS[0],
                run_id=f"{500 + index:032x}",
                expected_sha256=alloc.digest(doc),
            )
        except alloc.AllocationRefused as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(one, (0, 1)))
    assert sum(isinstance(row, dict) for row in results) == 1
    assert sum(isinstance(row, str) for row in results) == 1
    with alloc.registry(finished.root) as conn:
        assert conn.execute("SELECT COUNT(*) FROM feature_children").fetchone()[0] == 1


def test_real_runtime_sdk_transport_uses_bound_ledger_and_settles(finished, monkeypatch):
    import httpx

    from headroom.runtime import build_live_runtime
    from headroom.store.db import Store

    f = finished
    binding = claim(f)
    request = f.requests[binding["cell_id"]]
    monkeypatch.setenv(BUDGET_DB_ENV, f.receipt["ledger_path"])
    spec = SimpleNamespace(
        allocation_child_binding=binding,
        queued_request=request.model_dump(),
        run_id=binding["run_id"],
        feature_intent=None,
    )
    profile = read_live_profile(f.receipt["profile_path"])
    budget = allocation_budget_factory(spec)(spec.run_id, request, profile)
    budget.open_run(spec.run_id, ".60")
    store = Store(f.root / "observations.db")
    store.create_run(spec.run_id)
    calls = []

    def respond(http_request):
        body = json.loads(http_request.content)
        calls.append(body)
        state = alloc._budget_state(f.receipt)
        own = [a for a in state["attempts"] if a["run_id"] == spec.run_id]
        assert len(own) == 1 and own[0]["dispatched"] == 1
        return httpx.Response(
            200,
            json={
                "id": "offline-completion",
                "object": "chat.completion",
                "created": 1,
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "{}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 150,
                    "total_tokens": 250,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    bundle = build_live_runtime(
        spec.run_id,
        profile=profile,
        budget=budget,
        store=store,
        env_file=f.root / "credential.fixture",
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    try:
        bundle.client.complete(
            "diagnose",
            [{"role": "user", "content": "synthetic fixture"}],
            max_tokens=2000,
            reasoning=False,
        )
    finally:
        bundle.close()
        store.close()
    assert len(calls) == 1
    budget.close_run(spec.run_id)
    result = retry.finish_f3_retry(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["actual_usd"] == "0.0004"
