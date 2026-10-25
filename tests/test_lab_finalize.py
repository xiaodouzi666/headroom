"""Partial-first capture finalization; synthetic unit data and CPU Docker only."""

import json
from pathlib import Path

import pytest
import torch

from headroom.lab import hooks
from headroom.lab.runner import read_capture, run_script
from headroom.verify.compare import compare_runs


class InterruptedFinalization(BaseException):
    """Simulate an interruption that normal artifact error handling cannot catch."""


@pytest.fixture(autouse=True)
def restore_capture():
    yield
    session = hooks.active_session()
    if session is not None:
        session._uninstall()


@pytest.mark.parametrize("execution_status", ["completed", "oom", "timeout"])
def test_core_checkpoint_precedes_snapshot_and_is_never_accepted(
    tmp_path, monkeypatch, execution_status
):
    parameter = torch.nn.Parameter(torch.tensor(1.0))
    optimizer = torch.optim.SGD([parameter], lr=0.01)
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    monkeypatch.setattr(session, "_peaks", lambda: (100, 200))
    # Generate the record through real pre/post hooks; finalization interruption
    # remains the unit under test rather than a hand-built historical schema.
    parameter.square().backward()
    optimizer.step()
    assert len(session.step_records) == 1
    assert session.step_records[0]["parameter_update_coverage_complete"]
    if execution_status == "timeout":
        session.deadline_reached = True

    def interrupted_snapshot():
        checkpoint = read_capture(tmp_path / "result.json")
        assert checkpoint["finalization_stage"] == "snapshot_capture"
        assert checkpoint["capture_complete"] is False
        assert checkpoint["finalization_incomplete"] is True
        assert checkpoint["execution_status"] == execution_status
        raise InterruptedFinalization()

    monkeypatch.setattr(session, "take_snapshot", interrupted_snapshot)
    with pytest.raises(InterruptedFinalization):
        session.finish(execution_status)
    assert hooks.active_session() is None
    assert not session.installed
    checkpoint = read_capture(tmp_path / "result.json")
    assert checkpoint["status"] == ("timeout" if execution_status == "timeout" else "error")
    assert checkpoint["steps"] == 1 and checkpoint["loss_series"] == [1.0]
    assert checkpoint["peak_allocated_bytes"] == 100
    assert checkpoint["peak_observation"] == "last_completed_optimizer_update"
    assert checkpoint["artifact_writes"]["snapshot.json"] == "pending"
    verification = compare_runs(checkpoint, checkpoint)
    assert not verification.target_met
    assert not verification.checks["baseline_capture"]
    assert not verification.checks["candidate_completed_required_steps"]


def test_snapshot_json_interruption_keeps_core_and_small_artifacts(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    snapshot = {"device_traces": [[{"action": "alloc", "size": 100}]]}
    monkeypatch.setattr(session, "take_snapshot", lambda: snapshot)
    monkeypatch.setattr(session, "_peaks", lambda: (100, 200))

    def interrupt_conversion(value):
        assert value is snapshot
        raise InterruptedFinalization()

    monkeypatch.setattr(hooks, "encode_snapshot", interrupt_conversion)
    with pytest.raises(InterruptedFinalization):
        session.finish()
    checkpoint = read_capture(tmp_path / "result.json")
    assert checkpoint["finalization_stage"] == "write:snapshot.json"
    assert checkpoint["finalization_incomplete"] and not checkpoint["capture_complete"]
    assert checkpoint["peak_observation"] == "capture_end"
    assert checkpoint["peak_allocated_bytes"] == 100
    assert checkpoint["snapshot_trace_count"] == 1
    assert checkpoint["artifact_writes"]["snapshot.pickle"] == "complete"
    assert checkpoint["artifact_writes"]["snapshot.json"] == "pending"
    for name in ("snapshot.pickle", "memory_stats.json", "memory_summary.txt", "traceback.txt"):
        assert (tmp_path / name).is_file()
    assert not (tmp_path / "snapshot.json").exists()


def test_pickle_failure_leaves_only_temporary_data_and_final_failure(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()

    def fail_dump(value, handle):
        handle.write(b"interrupted pickle")
        raise OSError("Injected pickle serialization failure")

    monkeypatch.setattr(hooks.pickle, "dump", fail_dump)
    result = session.finish()
    assert result["status"] == "error" and not result["capture_complete"]
    assert result["execution_status"] == "completed"
    assert result["finalization_stage"] == "finished" and not result["finalization_incomplete"]
    assert result["artifact_writes"]["snapshot.pickle"] == "failed"
    assert not (tmp_path / "snapshot.pickle").exists()
    assert len(list(tmp_path.glob(".snapshot.pickle.*.tmp"))) == 1
    assert any(error["stage"] == "write:snapshot.pickle" for error in result["errors"])
    assert read_capture(tmp_path / "result.json") == result


def test_atomic_pickle_does_not_replace_previous_file_on_failure(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.pickle"
    path.write_bytes(b"prior complete artifact")

    def interrupted_dump(value, handle):
        handle.write(b"incomplete replacement")
        raise InterruptedFinalization()

    monkeypatch.setattr(hooks.pickle, "dump", interrupted_dump)
    with pytest.raises(InterruptedFinalization):
        hooks._atomic_pickle(path, None)
    assert path.read_bytes() == b"prior complete artifact"


def test_complete_finalization_atomically_replaces_partial_result(tmp_path, monkeypatch):
    observed = []
    original = hooks._atomic_json

    def record_result(path, value):
        if path.name == "result.json":
            observed.append(json.loads(json.dumps(value)))
        original(path, value)

    monkeypatch.setattr(hooks, "_atomic_json", record_result)
    result = hooks.CaptureSession(tmp_path, device="cpu").start().finish()
    assert len(observed) > 2
    assert all(row["capture_complete"] is False for row in observed[:-1])
    assert all(row["finalization_incomplete"] is True for row in observed[:-1])
    assert observed[-1] == result
    assert result["status"] == "completed" and result["capture_complete"]
    assert not result["finalization_incomplete"] and result["finalization_stage"] == "finished"
    assert set(result["artifact_writes"].values()) == {"complete"}


def test_real_cpu_hard_stop_during_serialization_keeps_partial_timeout(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "slow_serialization.py"
    script.write_text(
        "import time\n"
        "from headroom.lab import hooks\n"
        "def blocked_conversion(value):\n"
        "    time.sleep(60)\n"
        "hooks.encode_snapshot = blocked_conversion\n"
        "while True:\n"
        "    time.sleep(0.02)\n"
    )
    result = run_script(script, device="cpu", max_seconds=6, run_root=tmp_path / "runs")
    assert result["status"] == "timeout" and result["execution"]["timed_out"], result
    assert result["cleanup_verified"]
    assert result["steps"] == 0 and result["loss_series"] == []
    assert result["capture_complete"] is False and result["finalization_incomplete"] is True
    assert result["finalization_stage"] == "write:snapshot.json"
    assert result["deadline_reached"] and result["execution_status"] == "timeout"
    assert result["execution_capture"]["complete"] is False
    assert result["artifact_writes"]["snapshot.pickle"] == "complete"
    assert result["artifact_writes"]["snapshot.json"] == "pending"
    assert result["peak_allocated_bytes"] is None
    artifacts = Path(result["artifact_dir"])
    assert not (artifacts / "snapshot.json").exists()
    assert (artifacts / "memory_stats.json").exists()
    assert read_capture(artifacts / "result.json")["finalization_incomplete"]
    control = result["execution"]["deadline_control"]
    assert control["hard_deadline_monotonic_ns"] - control["started_monotonic_ns"] == 6_000_000_000
    assert control["capture_reserve_seconds"] == pytest.approx(0.6)
    verification = compare_runs(result, result)
    assert not verification.target_met and not verification.completed


@pytest.mark.parametrize("interrupt_text", [False, True])
def test_exception_text_cannot_precede_snapshot_or_erase_core(
    tmp_path, monkeypatch, interrupt_text
):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    order = []

    def snapshot():
        assert read_capture(tmp_path / "result.json")["finalization_incomplete"]
        order.append("snapshot")

    class ExceptionWithWorkInText(RuntimeError):
        def __str__(self):
            order.append("exception_text")
            checkpoint = read_capture(tmp_path / "result.json")
            assert checkpoint["steps"] == 0
            assert checkpoint["finalization_incomplete"] and not checkpoint["capture_complete"]
            assert order[0] == "snapshot"
            if interrupt_text:
                raise InterruptedFinalization()
            return "Synthetic exception without GPU work"

    monkeypatch.setattr(session, "take_snapshot", snapshot)
    if interrupt_text:
        with pytest.raises(InterruptedFinalization):
            session.finish(exc=ExceptionWithWorkInText())
        result = read_capture(tmp_path / "result.json")
        assert result["finalization_stage"] == "exception_classification"
        assert result["finalization_incomplete"]
    else:
        result = session.finish(exc=ExceptionWithWorkInText())
        assert not result["finalization_incomplete"]
    assert order[0] == "snapshot" and "exception_text" in order
    assert result["status"] == "error"


def test_failed_first_checkpoint_always_uninstalls_capture(tmp_path, monkeypatch):
    original_backward = hooks.torch.Tensor.backward
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    original_write = hooks._atomic_json

    def fail_core(path, value):
        if path.name == "result.json":
            raise OSError("Injected first checkpoint write failure")
        original_write(path, value)

    monkeypatch.setattr(hooks, "_atomic_json", fail_core)
    with pytest.raises(OSError, match="first checkpoint"):
        session.finish()
    assert hooks.active_session() is None
    assert hooks.torch.Tensor.backward is original_backward
    assert not session.installed and session._step_handle is None
    assert session.finish()["capture_complete"] is False


def test_artifact_failure_preserves_already_observed_timeout(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    session.deadline_reached = True

    def fail_dump(value, handle):
        raise OSError("Injected pickle failure after soft timeout")

    monkeypatch.setattr(hooks.pickle, "dump", fail_dump)
    result = session.finish(exc=hooks.CaptureTimeout())
    assert result["status"] == result["execution_status"] == "timeout"
    assert result["termination_reason"] == "timeout"
    assert not result["capture_complete"] and not result["finalization_incomplete"]
    assert result["artifact_writes"]["snapshot.pickle"] == "failed"
    assert not compare_runs(result, result).target_met
