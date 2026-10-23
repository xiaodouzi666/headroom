"""In-sandbox PyTorch capture. No pickle is ever loaded by this module."""

from __future__ import annotations

import atexit
import csv
import io
import json
import math
import os
import pickle
import random
import re
import signal
import statistics
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import torch
from torch.optim.optimizer import register_optimizer_step_post_hook


class StepLimitReached(BaseException):
    """A completed optimizer update reached the configured capture boundary."""


class CaptureTimeout(BaseException):
    """The in-process wall-clock guard fired; the host also enforces a deadline."""


class CaptureSetupError(RuntimeError):
    """Capture could not be installed; the target must not run unobserved."""


_ACTIVE_SESSION: CaptureSession | None = None
_BYTE_UNITS = {
    "b": 1,
    "byte": 1,
    "bytes": 1,
    "kb": 10**3,
    "mb": 10**6,
    "gb": 10**9,
    "tb": 10**12,
    "kib": 2**10,
    "mib": 2**20,
    "gib": 2**30,
    "tib": 2**40,
}
_AMOUNT = r"([0-9]+(?:\.[0-9]+)?)\s*(bytes?|[KMGT]?i?B)"


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, allow_nan=False, indent=2) + "\n")
    temporary.replace(path)


def native_snapshot(value: Any, depth: int = 0) -> Any:
    """Reject object instances rather than stringify them into exported evidence."""
    if depth > 128:
        raise ValueError("Snapshot container nesting exceeds 128 levels")
    if type(value) in (type(None), bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite snapshot scalar")
        return value
    if type(value) in (list, tuple):
        return [native_snapshot(item, depth + 1) for item in value]
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("Snapshot dictionary keys must be native strings")
        return {key: native_snapshot(item, depth + 1) for key, item in value.items()}
    raise TypeError(f"Unsupported snapshot value type: {type(value).__name__}")


def is_cuda_oom(exc: BaseException, device: str) -> bool:
    """CPU allocation failures must never satisfy a CUDA OOM acceptance gate."""
    message = str(exc).lower()
    if not device.startswith("cuda") or "cpuallocator" in message or "cpu out of memory" in message:
        return False
    return isinstance(exc, (torch.OutOfMemoryError, RuntimeError)) and (
        "cuda out of memory" in message or "cuda error: out of memory" in message
    )


def parse_oom_details(snapshot: Any, message: str, device_index: int = 0) -> dict[str, Any]:
    """Prefer exact allocator-event bytes; label rounded exception-text fallbacks."""
    result: dict[str, Any] = {
        "requested_bytes": None,
        "free_bytes": None,
        "requested_source": None,
        "free_source": None,
    }
    traces = snapshot.get("device_traces", []) if isinstance(snapshot, dict) else []
    if device_index < len(traces):
        for entry in reversed(traces[device_index]):
            if entry.get("action") != "oom":
                continue
            for field, source in (("requested_bytes", "size"), ("free_bytes", "device_free")):
                if type(entry.get(source)) is int and entry[source] >= 0:
                    result[field] = entry[source]
                    result[field.replace("_bytes", "_source")] = "allocator_oom_event"
            break
    patterns = {
        "requested_bytes": [rf"tried to allocate\s+{_AMOUNT}"],
        "free_bytes": [rf"of which\s+{_AMOUNT}\s+is free", rf"{_AMOUNT}\s+free"],
    }
    for field, alternatives in patterns.items():
        if result[field] is not None:
            continue
        for pattern in alternatives:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                amount, unit = match.groups()
                result[field] = round(float(amount) * _BYTE_UNITS[unit.lower()])
                result[field.replace("_bytes", "_source")] = "exception_text_rounded"
                break
    result["requested_gb"] = (
        result["requested_bytes"] / 1e9 if result["requested_bytes"] is not None else None
    )
    result["free_gb"] = result["free_bytes"] / 1e9 if result["free_bytes"] is not None else None
    return result


def _claim_output_directory(base: Path) -> tuple[Path, bool]:
    base.mkdir(parents=True, exist_ok=True)
    try:
        with (base / ".capture-owner.json").open("x") as owner:
            json.dump({"pid": os.getpid(), "started_ns": time.time_ns()}, owner)
        return base, True
    except FileExistsError:
        # Subprocesses, or a second capture, must not replace the primary result.
        child = base / "processes" / str(os.getpid())
        if child.exists():
            child = base / "processes" / f"{os.getpid()}-{time.time_ns()}"
        child.mkdir(parents=True)
        return child, False


class CaptureSession:
    """Per-process capture; instantiated inside a network/filesystem sandbox."""

    def __init__(
        self,
        output_dir: str | Path,
        max_steps: int = 20,
        max_seconds: float = 120,
        seed: int = 1337,
        device: str = "cuda",
    ) -> None:
        if max_steps < 1 or max_seconds <= 0:
            raise ValueError("max_steps and max_seconds must be positive")
        if device not in ("cpu", "cuda"):
            raise ValueError("device must be cpu or cuda")
        self.output_dir, self.is_primary = _claim_output_directory(Path(output_dir))
        self.device = device
        self.device_index = 0
        self.max_steps, self.max_seconds, self.seed = max_steps, max_seconds, seed
        self.pid = os.getpid()
        self.loss_series: list[float | None] = []
        self.step_records: list[dict[str, Any]] = []
        self.errors: list[dict[str, str]] = []
        self.env: dict[str, Any] = {}
        self.gpu: dict[str, Any] | None = None
        self.shared_gpu: bool | None = None
        self.started_at = time.perf_counter()
        self.last_step_at = self.started_at
        self.finished = False
        self.installed = False
        self.ready = False
        self.history_enabled = False
        self._snapshot: Any = None
        self._snapshot_attempted = False
        self._step_handle: Any = None
        self._original_backward: Any = None
        self._backward_wrapper: Any = None
        self._previous_alarm_handler: Any = None
        self._previous_timer: tuple[float, float] | None = None
        self._result: dict[str, Any] | None = None

    def _error(self, stage: str, exc: BaseException) -> None:
        self.errors.append({"stage": stage, "type": type(exc).__name__, "message": str(exc)})

    def _gpu_processes(self) -> dict[str, Any]:
        try:
            response = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-compute-apps=pid,process_name,used_gpu_memory",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            rows = list(csv.reader(io.StringIO(response.stdout)))
            return {
                "returncode": response.returncode,
                "stdout": response.stdout,
                "stderr": response.stderr,
                "processes": [
                    {
                        "pid": row[0].strip(),
                        "process_name": row[1].strip(),
                        "used_memory_mib": row[2].strip(),
                    }
                    for row in rows
                    if len(row) == 3
                ],
            }
        except (OSError, subprocess.SubprocessError) as exc:
            self._error("nvidia_smi", exc)
            return {"returncode": None, "processes": None, "error": str(exc)}

    def start(self) -> CaptureSession:
        global _ACTIVE_SESSION
        if self.installed:
            return self
        if _ACTIVE_SESSION is not None:
            raise CaptureSetupError("Another capture is already installed in this process")
        self.env = {
            "pid": self.pid,
            "is_primary": self.is_primary,
            "python": sys.version,
            "torch": str(torch.__version__),
            "cuda": torch.version.cuda,
            "device": self.device,
            "seed": self.seed,
            "max_steps": self.max_steps,
            "max_seconds": self.max_seconds,
            "PYTORCH_CUDA_ALLOC_CONF": os.environ.get("PYTORCH_CUDA_ALLOC_CONF"),
            "CUDA_VISIBLE_DEVICES": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "seeded": {"python": False, "torch": False, "numpy": False},
        }
        if self.device == "cuda":
            initial = self._gpu_processes()
            self.gpu = {"before_cuda_initialization": initial}
            try:
                devices = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,name,driver_version,memory.total,memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.gpu["device_query"] = {
                    "returncode": devices.returncode,
                    "stdout": devices.stdout,
                    "stderr": devices.stderr,
                }
                self.env["driver_query"] = self.gpu["device_query"]
            except (OSError, subprocess.SubprocessError) as exc:
                self._error("nvidia_smi_driver", exc)
            if initial["returncode"] == 0:
                self.shared_gpu = bool(initial["processes"])
            if not torch.cuda.is_available():
                raise CaptureSetupError("CUDA requested but torch.cuda.is_available() is false")
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        random.seed(self.seed)
        self.env["seeded"]["python"] = True
        torch.manual_seed(self.seed)
        self.env["seeded"]["torch"] = True
        try:
            import numpy as np

            np.random.seed(self.seed % (2**32))
            self.env["seeded"]["numpy"] = True
        except ImportError as exc:
            self._error("numpy_seed_unavailable", exc)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        self.env["deterministic_algorithms"] = True
        self.env["CUBLAS_WORKSPACE_CONFIG"] = os.environ["CUBLAS_WORKSPACE_CONFIG"]
        if self.device == "cuda":
            torch.cuda.set_device(self.device_index)
            properties = torch.cuda.get_device_properties(self.device_index)
            self.env["gpu_name"] = properties.name
            self.env["gpu_total_memory_bytes"] = properties.total_memory
            self.env["cudnn"] = torch.backends.cudnn.version()
            torch.cuda.memory._record_memory_history(max_entries=200_000)
            self.history_enabled = True
            torch.cuda.reset_peak_memory_stats(self.device_index)
        self._original_backward = torch.Tensor.backward
        session = self

        def recorded_backward(tensor: torch.Tensor, *args: Any, **kwargs: Any) -> Any:
            if os.getpid() == session.pid and tensor.numel() == 1:
                scalar = float(tensor.detach().item())
                if not math.isfinite(scalar):
                    session._error("loss_nonfinite", ValueError(f"Scalar loss is {scalar}"))
                    session.loss_series.append(None)
                else:
                    session.loss_series.append(scalar)
            return session._original_backward(tensor, *args, **kwargs)

        self._backward_wrapper = recorded_backward
        torch.Tensor.backward = recorded_backward
        self._step_handle = register_optimizer_step_post_hook(self._optimizer_step)
        self.installed = True
        _ACTIVE_SESSION = self
        if threading.current_thread() is threading.main_thread():
            self._previous_alarm_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, self._timeout)
            self._previous_timer = signal.setitimer(signal.ITIMER_REAL, self.max_seconds)
        else:
            self._error("timer", RuntimeError("Non-main thread: external timeout guard required"))
        self.started_at = self.last_step_at = time.perf_counter()
        _atomic_json(self.output_dir / "env.json", self.env)
        _atomic_json(
            self.output_dir / "capture-ready.json",
            {
                "protocol": "headroom.lab.v1",
                "pid": self.pid,
                "is_primary": self.is_primary,
                "device": self.device,
                "history_enabled": self.history_enabled,
                "optimizer_hook": "global_post_hook",
            },
        )
        self.ready = True
        return self

    def _timeout(self, signum: int, frame: Any) -> None:
        raise CaptureTimeout(f"Capture exceeded {self.max_seconds:g} seconds")

    def _peaks(self) -> tuple[int | None, int | None]:
        if self.device != "cuda" or not self.history_enabled:
            return None, None
        try:
            return (
                int(torch.cuda.max_memory_allocated(self.device_index)),
                int(torch.cuda.max_memory_reserved(self.device_index)),
            )
        except Exception as exc:  # noqa: BLE001 - preserve failed capture evidence
            self._error("peak_stats", exc)
            return None, None

    def _optimizer_step(self, optimizer: torch.optim.Optimizer, args: Any, kwargs: Any) -> None:
        if os.getpid() != self.pid or self.finished:
            return
        if self.device == "cuda":
            torch.cuda.synchronize(self.device_index)
        ended = time.perf_counter()
        allocated, reserved = self._peaks()
        self.step_records.append(
            {
                "step": len(self.step_records) + 1,
                "optimizer": f"{type(optimizer).__module__}.{type(optimizer).__name__}",
                "step_ms": (ended - self.last_step_at) * 1000,
                "elapsed_ms": (ended - self.started_at) * 1000,
                "wall_time_us": time.time_ns() // 1000,
                "peak_allocated_bytes": allocated,
                "peak_reserved_bytes": reserved,
            }
        )
        self.last_step_at = ended
        if len(self.step_records) >= self.max_steps:
            raise StepLimitReached(f"Reached {self.max_steps} optimizer updates")

    def take_snapshot(self) -> Any:
        if self._snapshot_attempted:
            return self._snapshot
        self._snapshot_attempted = True
        if self.device != "cuda" or not self.history_enabled:
            return None
        try:
            # This is the first CUDA operation in the exception finalization path.
            self._snapshot = torch.cuda.memory._snapshot()
        except Exception as exc:  # noqa: BLE001 - preserve failed capture evidence
            self._error("snapshot", exc)
        return self._snapshot

    def _cancel_timer(self) -> None:
        if self._previous_timer is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, self._previous_alarm_handler)
            remaining, interval = self._previous_timer
            if remaining or interval:
                signal.setitimer(signal.ITIMER_REAL, remaining, interval)
            self._previous_timer = None

    def _uninstall(self) -> None:
        global _ACTIVE_SESSION
        self._cancel_timer()
        if self._step_handle is not None:
            self._step_handle.remove()
            self._step_handle = None
        if torch.Tensor.backward is self._backward_wrapper:
            torch.Tensor.backward = self._original_backward
        if _ACTIVE_SESSION is self:
            _ACTIVE_SESSION = None
        self.installed = False

    def finish(
        self,
        status: str = "completed",
        exc: BaseException | None = None,
        termination_reason: str | None = None,
    ) -> dict[str, Any]:
        if os.getpid() != self.pid:
            return {"status": "error", "termination_reason": "fork_without_capture"}
        if self.finished:
            return self._result or {}
        # Do not let a second timer interrupt serialization after the capture boundary.
        self._cancel_timer()
        # Grab the allocator state before formatting exceptions or querying external tools.
        snapshot = self.take_snapshot()
        self.finished = True
        self._uninstall()
        reason = termination_reason or "script_exit"
        if isinstance(exc, StepLimitReached):
            status, reason = "completed", "step_limit"
        elif isinstance(exc, CaptureTimeout):
            status, reason = "timeout", "timeout"
        elif exc is not None:
            if is_cuda_oom(exc, self.device):
                status, reason = "oom", "oom"
            else:
                status, reason = "error", termination_reason or "exception"
        exception_text = "".join(traceback.format_exception(exc)) if exc is not None else ""
        allocated, reserved = self._peaks()
        memory_stats: Any = None
        memory_summary = "CUDA memory summary unavailable for CPU capture.\n"
        if self.device == "cuda" and self.history_enabled:
            try:
                memory_stats = dict(torch.cuda.memory_stats(self.device_index))
            except Exception as stats_error:  # noqa: BLE001 - report capture failures
                self._error("memory_stats", stats_error)
            try:
                memory_summary = torch.cuda.memory_summary(self.device_index)
            except Exception as summary_error:  # noqa: BLE001 - report capture failures
                self._error("memory_summary", summary_error)
                memory_summary = f"Unavailable: {type(summary_error).__name__}: {summary_error}\n"
        trace_count = None
        if isinstance(snapshot, dict) and isinstance(snapshot.get("device_traces"), list):
            trace_count = sum(len(events) for events in snapshot["device_traces"])
        oom = None
        if status == "oom":
            oom = parse_oom_details(snapshot, str(exc), self.device_index)
            oom["traceback"] = exception_text
        artifact_writers = {
            "snapshot.pickle": lambda path: path.write_bytes(pickle.dumps(snapshot)),
            "snapshot.json": lambda path: _atomic_json(path, native_snapshot(snapshot)),
            "memory_stats.json": lambda path: _atomic_json(path, memory_stats),
            "memory_summary.txt": lambda path: path.write_text(memory_summary),
            "traceback.txt": lambda path: path.write_text(exception_text),
            "env.json": lambda path: _atomic_json(path, self.env),
        }
        for filename, writer in artifact_writers.items():
            try:
                writer(self.output_dir / filename)
            except Exception as artifact_error:  # noqa: BLE001 - report capture failures
                self._error(f"write:{filename}", artifact_error)
        if self.gpu is not None:
            self.gpu["at_capture_end"] = self._gpu_processes()
            self.gpu["shared_gpu_basis"] = "compute processes before capture CUDA initialization"
        if self.history_enabled:
            try:
                torch.cuda.memory._record_memory_history(enabled=None)
            except Exception as history_error:  # noqa: BLE001 - report capture failures
                self._error("history_disable", history_error)
        execution_status = status
        critical_stages = {"snapshot", "peak_stats", "memory_stats", "memory_summary"}
        capture_complete = self.ready and not any(
            error["stage"] in critical_stages or error["stage"].startswith("write:")
            for error in self.errors
        )
        if self.device == "cuda" and (snapshot is None or allocated is None or reserved is None):
            capture_complete = False
        if not capture_complete:
            status, reason = "error", "capture_error"
        self._result = {
            "protocol": "headroom.lab.v1",
            "schema_version": 1,
            "capture_complete": capture_complete,
            "execution_status": execution_status,
            "status": status,
            "termination_reason": reason,
            "pid": self.pid,
            "is_primary": self.is_primary,
            "steps": len(self.step_records),
            "loss_series": self.loss_series,
            "step_records": self.step_records,
            "peak_allocated_bytes": allocated,
            "peak_reserved_bytes": reserved,
            "peak_alloc_gb": allocated / 1e9 if allocated is not None else None,
            "peak_reserved_gb": reserved / 1e9 if reserved is not None else None,
            "step_ms_median": statistics.median([record["step_ms"] for record in self.step_records])
            if self.step_records
            else None,
            "timing_note": "Intervals between completed optimizer updates; first includes target setup",
            "wall_seconds": time.perf_counter() - self.started_at,
            "snapshot": {"available": snapshot is not None, "trace_count": trace_count},
            "snapshot_trace_count": trace_count,
            "oom": oom,
            "shared_gpu": self.shared_gpu,
            "gpu": self.gpu,
            "env": self.env,
            "errors": self.errors,
            "exception": {"type": type(exc).__name__, "message": str(exc)} if exc else None,
        }
        _atomic_json(self.output_dir / "result.json", self._result)
        return self._result


def active_session() -> CaptureSession | None:
    return _ACTIVE_SESSION


def install_from_environment() -> CaptureSession:
    """Used by sitecustomize in a separate command-mode Python interpreter."""
    if _ACTIVE_SESSION is not None:
        return _ACTIVE_SESSION
    session = CaptureSession(
        output_dir=os.environ["HEADROOM_OUTPUT_DIR"],
        max_steps=int(os.environ.get("HEADROOM_MAX_STEPS", "20")),
        max_seconds=float(os.environ.get("HEADROOM_MAX_SECONDS", "120")),
        seed=int(os.environ.get("HEADROOM_SEED", "1337")),
        device=os.environ.get("HEADROOM_DEVICE", "cuda"),
    )
    try:
        session.start()
    except BaseException as exc:
        session.finish("error", exc, "setup_error")
        raise
    previous_excepthook = sys.excepthook

    def exception_hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
        try:
            session.finish("error", exc)
        finally:
            # Preserve the real exception/traceback on stderr, including controlled exits.
            previous_excepthook(exc_type, exc, tb)

    sys.excepthook = exception_hook
    atexit.register(session.finish)
    return session
