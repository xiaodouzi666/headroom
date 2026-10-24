"""Real spawn supervision with only offline host fixtures, never target execution."""

import os
import signal
import socket
import time
from pathlib import Path
from uuid import uuid4

import pytest

from headroom import evaluation_worker as worker
from headroom.budget import BudgetLedger
from headroom.orchestrator import FixRequest
from headroom.report import generate_report
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Real network forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def _finish_fixture(request, store_path, run_root, run_id, result_path):
    store = Store(store_path)
    try:
        directory = Path(run_root) / run_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "saved-patch.diff").write_text("offline retained patch")
        after = {"status": "completed", "peak_allocated_bytes": 100}
        store.update_run(
            run_id,
            status="completed",
            target_met=True,
            after=after,
            search={"mode": "until_target", "stop_reason": "target_met"},
        )
        document = generate_report(
            directory,
            store.get_run(run_id),
            verification={"target_met": True, "after": after},
            usage=store.usage(run_id),
        )
        worker._write(
            Path(result_path),
            {
                "run_id": run_id,
                "status": "completed",
                "target_met": True,
                "run_dir": str(directory),
                "report": document,
            },
        )
    finally:
        store.close()


def success_entry(
    request, store_path, run_root, run_id, condition, audit_dir, result_path, deadline, preparation
):
    _finish_fixture(request, store_path, run_root, run_id, result_path)


def swallow_term_entry(
    request, store_path, run_root, run_id, condition, audit_dir, result_path, deadline, preparation
):
    stopped = []
    signal.signal(signal.SIGTERM, lambda *_: stopped.append(True))
    while not stopped:
        time.sleep(0.02)
    _finish_fixture(request, store_path, run_root, run_id, result_path)


def pending_ignore_term_entry(
    request, store_path, run_root, run_id, condition, audit_dir, result_path, deadline, preparation
):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    store = Store(store_path)
    ledger = BudgetLedger(Path(run_root).parent / "fixture-budget.db", total_limit="3")
    ledger.open_run(run_id, "0.6", budget_mode="actual_usage")
    ledger.reserve(run_id, "pending-attempt", "1.06")
    store.add_llm_call(
        run_id,
        {
            "model": "offline",
            "outcome": "pending",
            "settled": False,
            "reservation_usd": "1.06",
            "cost_usd": None,
        },
    )
    directory = Path(run_root) / run_id
    directory.mkdir(parents=True)
    (directory / "pending-marker").write_text("persisted before waiting")
    store.close()
    while True:
        time.sleep(1)


def crash_entry(*args):
    os._exit(23)


def setup_case(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("VALUE = 1\n")
    store = Store(tmp_path / "store.db")
    request = FixRequest(
        script=str(script),
        source_root=str(source),
        runtime_profile=str(tmp_path / "missing-reviewed-profile.json"),
        research_enabled=False,
    )
    return (
        request,
        store,
        {
            "store": store,
            "run_root": tmp_path / "jobs",
            "run_id": uuid4().hex,
            "condition": "full_ultra",
            "audit_dir": tmp_path / "audit",
            "started": time.monotonic(),
        },
    )


def test_real_spawn_preserves_completed_result_and_no_container(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=10,
            _entrypoint=success_entry,
        )
        assert result["status"] == "completed" and result["target_met"]
        assert result["report"]["summary"]["target_met"]
        assert result["evaluation_timing"]["worker_exit_code"] == 0
        assert result["evaluation_timing"]["cleanup_verified"]
        assert result["evaluation_timing"]["within_wall_limit"]
        assert Path(result["report_md"]).is_file()
        assert store.get_run(result["run_id"])["evaluation_worker_pid"] != os.getpid()
    finally:
        store.close()


def test_real_production_child_missing_profile_stops_before_gpu_or_key(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=10,
            preparation={
                "case": {
                    "id": "fixture",
                    "group": "synthetic",
                    "script": "source/train.py",
                    "source_root": "source",
                    "target": "fix-oom",
                    "expected_baseline": "oom",
                },
                "project_root": str(tmp_path),
                "input_dir": str(tmp_path / "prepared"),
            },
        )
        assert result["evaluation_preparation"]["source_sha256"]
        assert (tmp_path / "prepared").is_dir()
        assert result["status"] == "needs_human"
        assert result["evaluation_timing"]["worker_exit_code"] == 0
        assert not list((tmp_path / "jobs").rglob("gpu-before.json"))
        assert store.llm_calls(result["run_id"]) == []
    finally:
        store.close()


def test_prepare_elapsed_time_prevents_worker_start(tmp_path, monkeypatch):
    request, store, kwargs = setup_case(tmp_path)
    kwargs["started"] -= 3
    monkeypatch.setattr(
        worker.multiprocessing,
        "get_context",
        lambda *a: pytest.fail("Preparation exhausted the per-case deadline"),
    )
    try:
        result = worker.supervise_evaluation_run(request, **kwargs, wall_limit_seconds=1)
        assert result["status"] == "timeout" and result["target_met"] is False
        assert result["evaluation_timing"]["worker_exit_code"] is None
        assert Path(result["report_json"]).is_file()
    finally:
        store.close()


def test_swallowed_term_cannot_turn_timed_out_case_into_success(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=3,
            _entrypoint=swallow_term_entry,
            _grace_seconds=2,
        )
        assert result["status"] == "timeout" and result["target_met"] is False
        assert result["report"]["summary"]["target_met"] is False
        assert result["report"]["verification"]["target_met"] is True
        assert (Path(result["run_dir"]) / "saved-patch.diff").is_file()
        assert result["evaluation_timing"]["worker_exit_code"] == 0
        assert result["evaluation_timing"]["deadline_exceeded"]
    finally:
        store.close()


def test_ignore_term_hard_kill_retains_pending_billing_and_partial_report(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=3,
            _entrypoint=pending_ignore_term_entry,
            _grace_seconds=0.2,
        )
        assert result["status"] == "timeout"
        assert result["evaluation_timing"]["worker_exit_code"] == -signal.SIGKILL
        assert (Path(result["run_dir"]) / "pending-marker").is_file()
        ledger = BudgetLedger(tmp_path / "fixture-budget.db", total_limit="3")
        budget = ledger.snapshot(result["run_id"])
        assert budget["pending_attempts"] == 1
        assert budget["total_actual_usd"] is None and budget["reserved_or_actual_usd"] == "1.06"
        assert budget["dispatch_blocked"]
        assert store.usage(result["run_id"])["total_cost_usd"] is None
        assert result["report"]["summary"]["target_met"] is False
        assert Path(result["report_md"]).is_file()
    finally:
        store.close()


def test_crashed_worker_has_failed_partial_report(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=10,
            _entrypoint=crash_entry,
        )
        assert result["status"] == "failed" and result["target_met"] is False
        assert result["evaluation_timing"]["worker_exit_code"] == 23
        assert Path(result["report_json"]).is_file()
    finally:
        store.close()


def test_cleanup_failure_overrides_completed_worker(tmp_path, monkeypatch):
    request, store, kwargs = setup_case(tmp_path)
    seen = []
    monkeypatch.setattr(
        worker,
        "cleanup_owned_lab",
        lambda root, run: seen.append((root, run)) or False,
    )
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=10,
            _entrypoint=success_entry,
        )
        assert seen == [(kwargs["run_root"], kwargs["run_id"])]
        assert result["status"] == "needs_human" and not result["target_met"]
        assert result["evaluation_timing"]["cleanup_verified"] is False
    finally:
        store.close()


@pytest.mark.parametrize("limit", [0, -1, 481])
def test_supervisor_cannot_extend_reviewed_wall_limit(tmp_path, limit):
    request, store, kwargs = setup_case(tmp_path)
    try:
        with pytest.raises(ValueError, match="deadlines"):
            worker.supervise_evaluation_run(request, **kwargs, wall_limit_seconds=limit)
    finally:
        store.close()


def test_live_campaign_routes_to_supervisor_and_stops_after_cleanup_failure(tmp_path, monkeypatch):
    import test_evaluation as fixtures

    from headroom import evaluation

    manifest = fixtures.manifest(tmp_path, count=2)
    monkeypatch.setattr("headroom.runtime.read_live_profile", lambda path: object())
    seen = []

    def supervised(request, **kwargs):
        seen.append((request, kwargs))
        store = kwargs["store"]
        store.create_run(kwargs["run_id"], {"status": "needs_human"})
        return {
            "run_id": kwargs["run_id"],
            "status": "needs_human",
            "report": {"summary": {"target_met": False}},
            "evaluation_timing": {"cleanup_verified": False},
        }

    monkeypatch.setattr(worker, "supervise_evaluation_run", supervised)
    monkeypatch.setattr(
        evaluation,
        "condition_services",
        lambda *a: pytest.fail("Condition closures must be constructed in the child"),
    )
    result = evaluation.run_campaign(
        manifest,
        project_root=tmp_path,
        execute=True,
        live_authorized=True,
        runtime_profile=tmp_path / "reviewed-profile",
        campaign_budget_usd="3",
    )
    assert len(seen) == 1
    assert seen[0][0].budget_usd == "0.6"
    assert seen[0][1]["started"] <= time.monotonic()
    assert result["halt_reason"] == "evaluation_cleanup_unverified"
    assert result["limits"]["run_wall_seconds"] == 480
    assert result["rows"][1]["status"] == "pending"


def slow_preparation_entry(*args):
    from headroom import evaluation

    def delayed(*_args):
        time.sleep(60)
        raise AssertionError("Deadline did not stop preparation")

    evaluation._prepare = delayed
    worker._evaluation_entry(*args)


def test_preparation_itself_is_inside_owned_deadline_process(tmp_path):
    request, store, kwargs = setup_case(tmp_path)
    try:
        result = worker.supervise_evaluation_run(
            request,
            **kwargs,
            wall_limit_seconds=3,
            _entrypoint=slow_preparation_entry,
            _grace_seconds=0.2,
            preparation={
                "case": {
                    "id": "fixture",
                    "group": "synthetic",
                    "script": "source/train.py",
                    "source_root": "source",
                    "target": "fix-oom",
                    "expected_baseline": "oom",
                },
                "project_root": str(tmp_path),
                "input_dir": str(tmp_path / "prepared"),
            },
        )
        assert result["status"] == "timeout"
        assert result["evaluation_timing"]["deadline_exceeded"]
        assert result["evaluation_preparation"] is None
        assert store.llm_calls(result["run_id"]) == []
        assert Path(result["report_json"]).exists()
    finally:
        store.close()
