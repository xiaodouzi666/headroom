"""CPU unit tests for capture boundaries; no GPU workloads or user scripts."""

from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path

import pytest
import torch

from headroom.lab import hooks
from headroom.lab.hooks import (
    CaptureSession,
    CaptureTimeout,
    StepLimitReached,
    is_cuda_oom,
    native_snapshot,
    parse_oom_details,
)


@pytest.fixture(autouse=True)
def cleanup_capture():
    yield
    session = hooks.active_session()
    if session is not None:
        session.finish("error", RuntimeError("Test cleanup after incomplete capture"))


def test_adamw_override_is_counted_after_real_update(tmp_path: Path):
    original = torch.Tensor.backward
    session = CaptureSession(tmp_path, max_steps=2, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    optimizer = torch.optim.AdamW([parameter], lr=0.1)
    with pytest.raises(StepLimitReached) as stopped:
        for _ in range(10):
            optimizer.zero_grad()
            parameter.square().sum().backward()
            optimizer.step()
    result = session.finish(exc=stopped.value)
    assert not issubclass(StepLimitReached, Exception)
    assert result["steps"] == 2
    assert len(result["loss_series"]) == 2
    assert parameter.item() < 0.9
    assert result["status"] == "completed"
    assert result["termination_reason"] == "step_limit"
    assert all("AdamW" in record["optimizer"] for record in result["step_records"])
    assert torch.Tensor.backward is original


def test_global_hook_covers_distinct_optimizer_classes(tmp_path: Path):
    session = CaptureSession(tmp_path, max_steps=3, device="cpu").start()
    first = torch.nn.Parameter(torch.tensor([1.0]))
    second = torch.nn.Parameter(torch.tensor([2.0]))
    for parameter, optimizer in [
        (first, torch.optim.SGD([first], lr=0.1)),
        (second, torch.optim.AdamW([second], lr=0.1)),
    ]:
        parameter.square().sum().backward()
        optimizer.step()
    result = session.finish()
    assert result["steps"] == 2
    assert result["loss_series"] == [1.0, 4.0]


def test_non_scalar_backward_keeps_real_gradients_without_fake_loss(tmp_path: Path):
    session = CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.tensor([1.0, 2.0], requires_grad=True)
    parameter.square().backward(torch.ones(2))
    result = session.finish()
    assert torch.equal(parameter.grad, torch.tensor([2.0, 4.0]))
    assert result["loss_series"] == []
    assert result["steps"] == 0


def _seeded_losses(directory: Path) -> list[float]:
    session = CaptureSession(directory, max_steps=6, seed=23, device="cpu").start()
    model = torch.nn.Linear(3, 1)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.02)
    inputs = torch.randn(4, 3)
    targets = torch.randn(4, 1)
    for _ in range(5):
        optimizer.zero_grad()
        (model(inputs) - targets).square().mean().backward()
        optimizer.step()
    return session.finish()["loss_series"]


def test_same_seed_repeats_first_five_actual_cpu_losses(tmp_path: Path):
    assert _seeded_losses(tmp_path / "one") == _seeded_losses(tmp_path / "two")


def test_cpu_artifacts_do_not_claim_cuda_measurements(tmp_path: Path):
    result = CaptureSession(tmp_path, device="cpu").start().finish()
    for name in [
        "result.json",
        "snapshot.pickle",
        "snapshot.json",
        "memory_stats.json",
        "memory_summary.txt",
        "traceback.txt",
        "env.json",
        "capture-ready.json",
    ]:
        assert (tmp_path / name).is_file()
    assert result["protocol"] == "headroom.lab.v1"
    assert result["capture_complete"] is True
    assert result["peak_allocated_bytes"] is None
    assert result["peak_alloc_gb"] is None
    assert result["snapshot_trace_count"] is None
    assert json.loads((tmp_path / "snapshot.json").read_text()) is None
    assert json.loads((tmp_path / "memory_stats.json").read_text()) is None
    ready = json.loads((tmp_path / "capture-ready.json").read_text())
    assert ready["protocol"] == "headroom.lab.v1"
    assert ready["history_enabled"] is False


def test_second_process_capture_directory_does_not_replace_primary(tmp_path: Path):
    first = CaptureSession(tmp_path, device="cpu").start()
    first.finish()
    original = (tmp_path / "result.json").read_bytes()
    second = CaptureSession(tmp_path, device="cpu").start()
    result = second.finish()
    assert result["is_primary"] is False
    assert second.output_dir.parent.name == "processes"
    assert (tmp_path / "result.json").read_bytes() == original
    assert (second.output_dir / "result.json").is_file()


def test_oom_classification_excludes_cpu_memory_failures():
    assert is_cuda_oom(torch.OutOfMemoryError("CUDA out of memory."), "cuda")
    assert not is_cuda_oom(torch.OutOfMemoryError("CPU out of memory."), "cuda")
    assert not is_cuda_oom(RuntimeError("DefaultCPUAllocator: can't allocate memory"), "cuda")
    assert not is_cuda_oom(torch.OutOfMemoryError("CUDA out of memory."), "cpu")
    assert not is_cuda_oom(MemoryError("Out of memory"), "cuda")


def test_oom_exact_allocator_bytes_override_rounded_error_message():
    snapshot = {
        "device_traces": [
            [
                {"action": "oom", "size": 1337, "device_free": 9},
            ]
        ]
    }
    details = parse_oom_details(snapshot, "CUDA out of memory. Tried to allocate 4.00 GiB")
    assert details["requested_bytes"] == 1337
    assert details["free_bytes"] == 9
    assert details["requested_source"] == "allocator_oom_event"
    assert details["requested_gb"] == 1337 / 1e9


def test_oom_unknown_fields_stay_null_and_text_units_are_labeled():
    unknown = parse_oom_details(None, "CUDA out of memory")
    assert unknown["requested_bytes"] is None
    assert unknown["free_bytes"] is None
    details = parse_oom_details(
        None,
        (
            "CUDA out of memory. Tried to allocate 2.50 MiB. GPU 0 has a total "
            "capacity of 24.00 GiB of which 64.00 KiB is free."
        ),
    )
    assert details["requested_bytes"] == 2621440
    assert details["free_bytes"] == 65536
    assert details["free_source"] == "exception_text_rounded"


def test_native_snapshot_rejects_object_values_and_nonfinite_scalars():
    assert native_snapshot({"frames": ({"line": 1, "name": "f"},)}) == {
        "frames": [{"line": 1, "name": "f"}]
    }
    with pytest.raises(TypeError):
        native_snapshot({"not_a_native_value": object()})
    with pytest.raises(ValueError):
        native_snapshot({"value": float("nan")})


def test_json_artifact_failure_is_not_reported_as_completed(tmp_path: Path, monkeypatch):
    session = CaptureSession(tmp_path, device="cpu").start()
    original_write = hooks._atomic_json

    def fail_snapshot(path: Path, value):
        if path.name == "snapshot.json":
            raise OSError("Injected JSON write failure")
        original_write(path, value)

    monkeypatch.setattr(hooks, "_atomic_json", fail_snapshot)
    result = session.finish()
    assert result["status"] == "error"
    assert result["execution_status"] == "completed"
    assert result["capture_complete"] is False
    assert result["termination_reason"] == "capture_error"
    assert any(error["stage"] == "write:snapshot.json" for error in result["errors"])
    assert json.loads((tmp_path / "result.json").read_text())["capture_complete"] is False


def test_cuda_snapshot_failure_downgrades_oom_with_cpu_mocks(tmp_path: Path, monkeypatch):
    session = CaptureSession(tmp_path, device="cpu").start()
    session.device = "cuda"
    session.history_enabled = True

    def unavailable_snapshot():
        raise RuntimeError("Injected snapshot API failure")

    monkeypatch.setattr(torch.cuda.memory, "_snapshot", unavailable_snapshot)
    monkeypatch.setattr(torch.cuda, "max_memory_allocated", lambda *_: 100)
    monkeypatch.setattr(torch.cuda, "max_memory_reserved", lambda *_: 200)
    monkeypatch.setattr(torch.cuda, "memory_stats", lambda *_: {})
    monkeypatch.setattr(torch.cuda, "memory_summary", lambda *_: "CPU mock")
    monkeypatch.setattr(torch.cuda.memory, "_record_memory_history", lambda **_: None)
    result = session.finish(exc=torch.OutOfMemoryError("CUDA out of memory."))
    assert result["status"] == "error"
    assert result["execution_status"] == "oom"
    assert result["capture_complete"] is False
    assert result["snapshot"]["available"] is False
    assert result["oom"]["requested_bytes"] is None


def test_partial_setup_cannot_claim_complete_capture(tmp_path: Path, monkeypatch):
    session = CaptureSession(tmp_path, device="cpu")

    def fail_setup(*args, **kwargs):
        raise RuntimeError("Injected deterministic setup failure")

    monkeypatch.setattr(torch, "use_deterministic_algorithms", fail_setup)
    with pytest.raises(RuntimeError) as failed:
        session.start()
    result = session.finish("error", failed.value, "setup_error")
    assert result["status"] == "error"
    assert result["capture_complete"] is False
    assert not (tmp_path / "capture-ready.json").exists()


def test_in_process_timeout_raises_baseexception_and_restores_alarm(tmp_path: Path):
    original_handler = signal.getsignal(signal.SIGALRM)
    session = CaptureSession(tmp_path, max_seconds=0.05, device="cpu").start()
    with pytest.raises(CaptureTimeout) as timed_out:
        time.sleep(1)
    result = session.finish(exc=timed_out.value)
    assert result["status"] == "timeout"
    assert result["termination_reason"] == "timeout"
    assert signal.getsignal(signal.SIGALRM) is original_handler


def test_command_exception_hook_records_controlled_terminal_reason(tmp_path: Path, monkeypatch):
    callbacks = []
    forwarded = []
    monkeypatch.setenv("HEADROOM_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("HEADROOM_DEVICE", "cpu")
    monkeypatch.setenv("HEADROOM_MAX_STEPS", "20")
    monkeypatch.setattr(hooks.atexit, "register", callbacks.append)
    monkeypatch.setattr(sys, "excepthook", lambda *args: forwarded.append(args))
    session = hooks.install_from_environment()
    exc = StepLimitReached("Controlled test boundary")
    sys.excepthook(type(exc), exc, None)
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["status"] == "completed"
    assert result["termination_reason"] == "step_limit"
    assert result["capture_complete"] is True
    assert len(callbacks) == 1
    assert len(forwarded) == 1
    assert session.finished


def test_precision_mode_only_applies_during_forward_and_backward_is_not_duplicated(tmp_path):
    from torch.overrides import has_torch_function_unary

    session = CaptureSession(tmp_path, device="cpu").start()
    model = torch.nn.Linear(2, 1)
    value = torch.ones(1, 2)
    assert not has_torch_function_unary(value)
    loss = model(value).square().sum()
    assert not has_torch_function_unary(loss)
    loss.backward(retain_graph=True)
    loss.backward()
    result = session.finish()
    assert len(result["loss_series"]) == 2
    assert result["loss_series"][0] == result["loss_series"][1]
    assert result["precision_observation"]["precision"] == "fp32"
    assert not has_torch_function_unary(loss)


def test_backward_inside_forward_is_captured_once_and_preserves_gradient(tmp_path):
    class Inner(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(torch.tensor(2.0))

        def forward(self, value):
            loss = (self.weight * value).square()
            loss.backward()
            return loss.detach()

    session = CaptureSession(tmp_path, device="cpu").start()
    model = Inner()
    assert model(torch.tensor(3.0)).item() == 36
    result = session.finish()
    assert result["loss_series"] == [36]
    assert model.weight.grad.item() == 36
    assert result["precision_observation"]["complete"]


def test_cross_thread_forward_cannot_pop_or_leak_the_owner_precision_mode(tmp_path):
    import threading

    from torch.overrides import _get_current_function_mode

    entered, release = threading.Event(), threading.Event()
    failures = []

    class Child(torch.nn.Module):
        def forward(self, value):
            entered.set()
            assert release.wait(5)
            return value * 2

    class Parent(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.child = Child()
            self.worker = None

        def forward(self, value):
            def work():
                try:
                    self.child(value)
                except BaseException as exc:  # noqa: BLE001 - relay worker failures to the main test
                    failures.append(exc)

            self.worker = threading.Thread(target=work)
            self.worker.start()
            assert entered.wait(5)
            return value + 1

    previous = _get_current_function_mode()
    session = CaptureSession(tmp_path, device="cpu").start()
    model = Parent()
    try:
        assert model(torch.tensor(1.0)).item() == 2
        assert _get_current_function_mode() is previous
    finally:
        release.set()
        if model.worker is not None:
            model.worker.join(5)
        result = session.finish()
    assert not failures
    assert _get_current_function_mode() is previous
    assert result["precision_observation"]["complete"] is False
    assert result["precision_observation"]["errors"]["cross_thread"] > 0
    assert not [error for error in result["errors"] if error["stage"] == "precision_observation"]
