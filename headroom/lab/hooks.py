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
import weakref
from functools import wraps
from pathlib import Path
from typing import Any

import torch
from torch.nn.modules.module import (
    register_module_forward_hook,
    register_module_forward_pre_hook,
    register_module_parameter_registration_hook,
)
from torch.optim.optimizer import (
    register_optimizer_step_post_hook,
    register_optimizer_step_pre_hook,
)

from headroom.lab.deadline import capture_window, configured_control
from headroom.lab.precision import CheckpointPrecisionAdapter, PrecisionObserver
from headroom.lab.snapshot_codec import encode_snapshot


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
    # Allocator histories can contain hundreds of thousands of native events.
    # Whitespace is not evidence; keep every value without the pretty-print expansion.
    indent = None if path.name == "snapshot.json" else 2
    temporary.write_text(json.dumps(value, allow_nan=False, indent=indent) + "\n")
    temporary.replace(path)


def _atomic_pickle(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        pickle.dump(value, handle)
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


_GROUP_OPTIONS = (
    "lr",
    "momentum",
    "weight_decay",
    "dampening",
    "nesterov",
    "betas",
    "eps",
    "amsgrad",
    "maximize",
    "foreach",
    "fused",
    "capturable",
    "differentiable",
    "initial_lr",
    "alpha",
    "rho",
    "lr_decay",
    "initial_accumulator_value",
    "lambd",
    "t0",
    "etas",
    "step_sizes",
    "momentum_decay",
    "decoupled_weight_decay",
)
_GROUP_MAX_OPTIMIZERS = 256
_GROUP_MAX_GROUPS = 64
_GROUP_MAX_GROUP_KEYS = 64
_GROUP_MAX_CONFIGS = 64
_GROUP_MAX_RECORDS = 256
_GROUP_MAX_MEMBERS = 16384
_GROUP_MAX_RAW_BYTES = 65536


def _optimizer_option_scalar(value):
    if value is None:
        return ["none", None]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int and -(2**63) <= value < 2**63:
        return ["int", value]
    if type(value) is float and math.isfinite(value):
        return ["float", value]
    return ["unsupported", None]


def _encode_optimizer_group_option(name, value):
    # Preserve the exact built-in scalar/container types. Never cast objects,
    # tensor scalars, numpy scalars, custom sequences or subclasses.
    if name in {"betas", "etas", "step_sizes"} and type(value) in (tuple, list):
        if len(value) != 2:
            return ["unsupported", None]
        values = [_optimizer_option_scalar(item) for item in value]
        if any(item[0] not in {"int", "float"} for item in values):
            return ["unsupported", None]
        return ["tuple" if type(value) is tuple else "list", values]
    return _optimizer_option_scalar(value)


def _optimizer_option_canonical(value):
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


class _OptimizerGroupOptionObserver:
    def __init__(self):
        self._identities = {}
        self._identity_count = 0
        self._configs = {}
        self._records = {}
        self._member_count = 0
        self.complete = True
        self.stopped = False
        self.events = {"base_constructor_return": 0, "step_pre": 0}

    def observe(self, optimizer, *, stage, call, identify):
        # Optional observer failures must never replace the target's native
        # result. Deadline/step-limit BaseExceptions still propagate.
        try:
            self._observe(optimizer, stage=stage, call=call, identify=identify)
        except Exception:  # noqa: BLE001 - optional metadata must not replace native behavior
            self.complete = False
            self.stopped = True

    def _observe(self, optimizer, *, stage, call, identify):
        if stage not in self.events or type(call) is not int or not 0 <= call <= 65536:
            raise ValueError("unsupported observation boundary")
        self.events[stage] += 1
        if self.events[stage] > 65536:
            raise ValueError("observation event limit")
        if self.stopped:
            return
        identity = self._identities.get(id(optimizer))
        if identity is None or identity[0]() is not optimizer:
            if self._identity_count >= _GROUP_MAX_OPTIMIZERS:
                raise ValueError("optimizer identity limit")
            self._identity_count += 1
            identity = (weakref.ref(optimizer), f"o{self._identity_count:04d}")
            self._identities[id(optimizer)] = identity
        # Access only the real instance dictionary and exact built-in
        # containers. Do not traverse properties or arbitrary mapping objects.
        attributes = object.__getattribute__(optimizer, "__dict__")
        if type(attributes) is not dict:
            raise ValueError("unsupported optimizer attributes")
        groups = attributes.get("param_groups")
        if type(groups) is not list or not 0 < len(groups) <= _GROUP_MAX_GROUPS:
            raise ValueError("unsupported optimizer groups")
        for index, group in enumerate(groups):
            if type(group) is not dict or len(group) > _GROUP_MAX_GROUP_KEYS:
                raise ValueError("unsupported optimizer group")
            params = group.get("params")
            if type(params) not in (list, tuple) or len(params) > 8192:
                raise ValueError("unsupported optimizer parameters")
            parameter_ids = [identify(parameter) for parameter in params]
            if any(
                type(token) is not str or re.fullmatch(r"p[0-9]{5,6}", token) is None
                for token in parameter_ids
            ):
                raise ValueError("unsupported parameter identity")
            if len(set(parameter_ids)) != len(parameter_ids):
                raise ValueError("duplicate optimizer parameter")
            present = {
                name: _encode_optimizer_group_option(name, group[name])
                for name in _GROUP_OPTIONS
                if name in group
            }
            unknown_keys = sum(
                type(key) is not str or key not in (*_GROUP_OPTIONS, "params") for key in group
            )
            config = {"present": present, "unrecognized_option_keys": unknown_keys}
            config_key = _optimizer_option_canonical(config)
            new_config = config_key not in self._configs
            if new_config and len(self._configs) >= _GROUP_MAX_CONFIGS:
                raise ValueError("configuration limit")
            config_record = self._configs.get(config_key) or {
                "id": f"c{len(self._configs) + 1:03d}",
                **config,
            }
            config_id = config_record["id"]
            key = _optimizer_option_canonical([identity[1], index, stage, config_id, parameter_ids])
            new_record = key not in self._records
            if new_record and (
                len(self._records) >= _GROUP_MAX_RECORDS
                or self._member_count + len(params) > _GROUP_MAX_MEMBERS
            ):
                raise ValueError("group record limit")
            record = (
                dict(self._records[key])
                if not new_record
                else {
                    "optimizer_id": identity[1],
                    "group_index": index,
                    "stage": stage,
                    "config_id": config_id,
                    "parameter_ids": parameter_ids,
                    "first_call": call,
                    "last_call": call,
                    "observations": 0,
                }
            )
            record["last_call"] = call
            record["observations"] += 1
            trial = self.snapshot()
            if new_config:
                trial["configurations"].append(config_record)
            trial["groups"] = [
                value for existing, value in self._records.items() if existing != key
            ] + [record]
            # New records/configs are byte-checked atomically. Unchanged rows
            # only grow bounded counters; reserve 4096 bytes for all such growth.
            if (new_config or new_record) and len(
                _optimizer_option_canonical(trial).encode()
            ) > _GROUP_MAX_RAW_BYTES - 4096:
                raise ValueError("raw metadata byte limit")
            if new_config:
                self._configs[config_key] = config_record
            self._records[key] = record
            if new_record:
                self._member_count += len(params)
            if unknown_keys or any(value[0] == "unsupported" for value in present.values()):
                self.complete = False

    def snapshot(self):
        return {
            "protocol": "headroom.optimizer_group_options.v1",
            "complete": bool(sum(self.events.values())) and self.complete and not self.stopped,
            "stopped_at_limit_or_error": self.stopped,
            "events": dict(self.events),
            "configurations": list(self._configs.values()),
            "groups": list(self._records.values()),
        }


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
        self._step_pre_handle: Any = None
        self._original_optimizer_init: Any = None
        self._optimizer_init_wrapper: Any = None
        self._optimizer_base_constructions_observed = 0
        self._optimizer_initial_catalog_complete = True
        self._optimizer_group_options = _OptimizerGroupOptionObserver()
        self._optimizer_pending: dict[tuple[int, int], dict[str, Any]] = {}
        self._backward_groups: dict[int, dict[str, Any]] = {}
        self._optimizer_step_calls = 0
        self._optimizer_successful_step_calls = 0
        self._update_identities: dict[int, tuple[Any, str]] = {}
        self._update_catalog: list[dict[str, Any]] = []
        self._recorded_update_members = 0
        self._backward_update_failures: list[dict[str, Any]] = []
        self._parameter_handles: list[Any] = []
        self._parameter_refs: dict[int, Any] = {}
        self._parameter_samples: list[int] = []
        self._root_parameter_counts: list[int] = []
        self._forward_depth = threading.local()
        self._precision_thread = threading.get_ident()
        self._original_backward: Any = None
        self._backward_wrapper: Any = None
        self._backward_active = threading.local()
        self._previous_alarm_handler: Any = None
        self._previous_timer: tuple[float, float] | None = None
        self._result: dict[str, Any] | None = None
        self.pairing_capture: Any = None
        self._pairing_hash_excluded = False
        self.precision_observer = PrecisionObserver(device)
        self._precision_mode = None
        self._checkpoint_precision = CheckpointPrecisionAdapter(
            self.precision_observer, self._observe_checkpoint_recompute
        )
        self.entrypoint_capture = None
        self.deadline_reached = False
        self.deadline_observation = {
            "basis": "relative_process_limit",
            "clock_verified": False,
            "max_seconds": max_seconds,
        }

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
            if os.getpid() != session.pid:
                return session._original_backward(tensor, *args, **kwargs)
            active = getattr(session._backward_active, "identities", None)
            if active is None:
                active = session._backward_active.identities = set()
            identity = id(tensor)
            # Tensor.backward can dispatch back to this wrapper through a
            # TorchFunctionMode. Record that same in-flight Tensor only once;
            # distinct nested losses and later calls remain observable.
            if identity in active:
                return session._original_backward(tensor, *args, **kwargs)
            outermost = not active
            active.add(identity)
            thread = threading.get_ident()
            group = session._backward_groups.get(thread)
            if outermost:
                group = {
                    "root": weakref.ref(tensor),
                    "expected": None,
                    "calls": 0,
                    "successful_calls": 0,
                    "updated": {},
                    "pending": set(),
                    "classes": set(),
                    "reasons": [],
                    "graph_task": None,
                    "restricted": kwargs.get("inputs") is not None
                    or (len(args) > 3 and args[3] is not None),
                    "higher_order": bool(
                        kwargs.get("create_graph", args[2] if len(args) > 2 else False)
                    ),
                }
                session._backward_groups[thread] = group
                if len(session._backward_groups) > 1:
                    for concurrent in session._backward_groups.values():
                        session._group_problem(concurrent, "concurrent_tensor_backward")
            elif group is not None:
                session._group_problem(group, "nested_distinct_tensor_backward")
            succeeded = False
            try:
                if session.pairing_capture is not None:
                    session.pairing_capture.backward(tensor, sys._getframe(1))
                if tensor.numel() == 1:
                    scalar = float(tensor.detach().item())
                    if not math.isfinite(scalar):
                        session._error("loss_nonfinite", ValueError(f"Scalar loss is {scalar}"))
                        session.loss_series.append(None)
                    else:
                        session.loss_series.append(scalar)
                returned = session._original_backward(tensor, *args, **kwargs)
                succeeded = True
            finally:
                active.remove(identity)
                if outermost:
                    session._backward_groups.pop(thread, None)
                    if not succeeded and group["calls"]:
                        session._group_problem(group, "backward_did_not_return_successfully")
                        session._reject_backward_group(group)
            if outermost and group["calls"]:
                # The autograd engine and all post-accumulate callbacks returned.
                # Raising a limit here cannot interrupt a partially updated model.
                session._complete_backward_group(group)
            return returned

        self._checkpoint_precision.install()
        self._backward_wrapper = recorded_backward
        torch.Tensor.backward = recorded_backward
        self._original_optimizer_init = torch.optim.Optimizer.__init__

        @wraps(self._original_optimizer_init)
        def recorded_optimizer_init(optimizer, *args, **kwargs):
            returned = session._original_optimizer_init(optimizer, *args, **kwargs)
            if os.getpid() == session.pid and not session.finished:
                session._optimizer_base_constructions_observed += 1
                try:
                    session._observe_optimizer_initial_parameters(optimizer)
                except Exception:  # noqa: BLE001 - optional metadata cannot replace native behavior
                    session._optimizer_initial_catalog_complete = False
                session._optimizer_group_options.observe(
                    optimizer,
                    stage="base_constructor_return",
                    call=0,
                    identify=session._existing_update_identity,
                )
            return returned

        self._optimizer_init_wrapper = recorded_optimizer_init
        torch.optim.Optimizer.__init__ = recorded_optimizer_init
        self._step_pre_handle = register_optimizer_step_pre_hook(self._optimizer_step_start)
        self._step_handle = register_optimizer_step_post_hook(self._optimizer_step)
        self._parameter_handles = [
            register_module_parameter_registration_hook(self._registered_parameter),
            register_module_forward_pre_hook(self._forward_start),
            register_module_forward_hook(self._forward_end, always_call=True),
        ]
        self.installed = True
        _ACTIVE_SESSION = self
        self.started_at = self.last_step_at = time.perf_counter()
        control = configured_control()
        remaining = self.max_seconds
        if control is not None:
            remaining, self.deadline_observation = capture_window(control, self.max_seconds)
        if threading.current_thread() is threading.main_thread():
            self._previous_alarm_handler = signal.getsignal(signal.SIGALRM)
            signal.signal(signal.SIGALRM, self._timeout)
            # A zero setitimer disarms the alarm. Expired windows are handled
            # explicitly below without executing the user's target.
            self._previous_timer = signal.setitimer(signal.ITIMER_REAL, remaining)
        else:
            self._error("timer", RuntimeError("Non-main thread: external timeout guard required"))
        _atomic_json(self.output_dir / "env.json", self.env)
        _atomic_json(
            self.output_dir / "capture-ready.json",
            {
                "protocol": "headroom.lab.v1",
                "pid": self.pid,
                "is_primary": self.is_primary,
                "device": self.device,
                "history_enabled": self.history_enabled,
                "optimizer_hook": "global_pre_post_hooks",
                "logical_update_boundary": "outer_optimizer_step_or_complete_tensor_backward",
                "deadline_observation": self.deadline_observation,
            },
        )
        self.ready = True
        if remaining <= 0:
            self._timeout(0, None)
        return self

    def _timeout(self, signum: int, frame: Any) -> None:
        self.deadline_reached = True
        self.deadline_observation["triggered"] = True
        self.deadline_observation.setdefault("triggered_monotonic_ns", time.monotonic_ns())
        raise CaptureTimeout("Lab observation deadline reached; hard deadline unchanged")

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

    def _track_parameter(self, parameter: Any) -> None:
        if not isinstance(parameter, torch.nn.Parameter):
            return
        identity = id(parameter)
        if identity in self._parameter_refs:
            return

        def released(reference: Any) -> None:
            if self._parameter_refs.get(identity) is reference:
                self._parameter_refs.pop(identity, None)

        self._parameter_refs[identity] = weakref.ref(parameter, released)

    def _registered_parameter(self, module: Any, name: str, parameter: Any) -> None:
        if os.getpid() == self.pid and not self.finished:
            self._track_parameter(parameter)
        # Never replace or retain a parameter through the registration hook.

    def _sample_parameters(self) -> None:
        if not self._root_parameter_counts:
            return
        count = 0
        for reference in list(self._parameter_refs.values()):
            parameter = reference()
            if parameter is not None:
                count += parameter.numel()
        if len(self._parameter_samples) < 10000:
            self._parameter_samples.append(count)
        else:
            self._error("parameter_count", RuntimeError("Parameter observation limit exceeded"))

    def _forward_start(self, module: torch.nn.Module, args: Any) -> None:
        if os.getpid() != self.pid or self.finished:
            return
        depth = getattr(self._forward_depth, "value", 0)
        if depth == 0:
            if self.pairing_capture is not None:
                self.pairing_capture.forward(args)
            # Root .parameters() deduplicates tied parameters. Weak references also
            # cover registered but unused modules without keeping their storage alive.
            parameters = list(module.parameters())
            for parameter in parameters:
                self._track_parameter(parameter)
            if len(self._root_parameter_counts) < 10000:
                self._root_parameter_counts.append(sum(p.numel() for p in parameters))
            self._sample_parameters()
            if (
                threading.get_ident() == self._precision_thread
                and self.precision_observer.operation_supported(module)
            ):
                try:
                    self._precision_mode = self.precision_observer.operation_mode()
                    self._precision_mode.__enter__()
                except Exception as exc:  # noqa: BLE001 - optional metadata must not break training
                    self._precision_mode = None
                    self._error("precision_observation", exc)
        self.precision_observer.active_observer().observe_pre(module, args)
        self._forward_depth.value = depth + 1

    def _forward_end(self, module: Any, args: Any, output: Any) -> None:
        if os.getpid() == self.pid and not self.finished:
            try:
                self.precision_observer.active_observer().observe_post(module, args, output)
            finally:
                depth = max(0, getattr(self._forward_depth, "value", 0) - 1)
                self._forward_depth.value = depth
                if depth == 0 and threading.get_ident() == self._precision_thread:
                    self._close_precision_mode()

    def _observe_checkpoint_recompute(self, function, args, kwargs):
        # This flag authorizes a scope, never substitutes for operation coverage.
        # The callback enters a real TorchFunctionMode before invoking function.
        group = self._backward_groups.get(self._precision_thread)
        task = self._graph_task()
        if (
            os.getpid() != self.pid
            or self.finished
            or group is None
            or len(self._backward_groups) != 1
            or task is None
            or task < 0
        ):
            self.precision_observer._error("checkpoint_scope_unverified")
            return function(*args, **kwargs)
        observer = self.precision_observer.explicit_worker_observer()
        if observer is None:
            return function(*args, **kwargs)
        return observer.observe_recompute(function, args, kwargs)

    def _close_precision_mode(self):
        if self._precision_mode is not None:
            if threading.get_ident() != self._precision_thread:
                self._error(
                    "precision_observation",
                    RuntimeError("Precision mode cleanup must run on its owning thread"),
                )
                return
            try:
                self._precision_mode.__exit__(None, None, None)
            except Exception as exc:  # noqa: BLE001 - preserve capture and mark precision unknown
                self._error("precision_observation", exc)
            self._precision_mode = None

    def _parameter_evidence(self) -> dict[str, Any]:
        stable = bool(self._parameter_samples) and len(set(self._parameter_samples)) == 1
        complete = stable and not any(e["stage"] == "parameter_count" for e in self.errors)
        return {
            "parameter_count": self._parameter_samples[-1] if self._parameter_samples else None,
            "parameter_count_complete": complete,
            "parameter_count_source": "lab_module_parameter_hooks",
            "parameter_count_observations": self._parameter_samples,
            "root_forward_parameter_counts": self._root_parameter_counts,
            "parameter_count_coverage": (
                "Unique live Parameters registered on nn.Module during capture, plus Parameters "
                "seen via root forward module.parameters(); sampled at root forwards and optimizer "
                "updates. Tied parameters count once; no tensor is retained. Standalone tensors, "
                "pre-capture unused modules, and no-root-forward construction failures are not covered. "
                "Changing observed counts are incomplete. This is runtime evidence, not authentication "
                "against a target that deliberately tampers with hooks."
            ),
        }

    @staticmethod
    def _group_problem(group, reason):
        if reason not in group["reasons"] and len(group["reasons"]) < 16:
            group["reasons"].append(reason)

    def _existing_update_identity(self, parameter):
        identity = self._update_identities.get(id(parameter))
        if identity is None or identity[0]() is not parameter:
            raise ValueError("parameter identity not previously observed")
        return identity[1]

    def _observe_optimizer_initial_parameters(self, optimizer):
        """Observe existing groups after base construction, without reading tensor values.

        This does not certify completion of a custom subclass constructor. Metadata
        failures must not replace the optimizer's return value or ordinary error;
        capture-control BaseExceptions (for example the deadline) still propagate.
        """
        members = 0
        for parameter_group in optimizer.param_groups:
            for parameter in parameter_group["params"]:
                members += 1
                if members > 8192:
                    raise ValueError("optimizer initial parameter observation limit")
                self._update_identity(parameter)

    def _update_identity(self, parameter):
        if not isinstance(parameter, torch.nn.Parameter):
            raise TypeError("standalone optimizer tensors lack Parameter coverage")
        identity = id(parameter)
        previous = self._update_identities.get(identity)
        if previous is not None and previous[0]() is parameter:
            return previous[1]
        if len(self._update_catalog) >= 8192:
            raise ValueError("parameter identity observation limit exceeded")
        token = f"p{len(self._update_catalog) + 1:05d}"
        self._update_identities[identity] = (weakref.ref(parameter), token)
        self._update_catalog.append(
            {
                "id": token,
                "numel": parameter.numel(),
                "requires_grad_at_observation": bool(parameter.requires_grad),
            }
        )
        return token

    def _backward_parameters(self, group):
        """Bounded graph-edge inspection; never read/copy tensor contents or saved tensors."""
        if group["restricted"] or group["higher_order"]:
            raise ValueError("restricted-input or higher-order backward is unsupported")
        root = group["root"]()
        if root is None:
            raise ValueError("backward root unavailable")
        expected = set()
        if isinstance(root, torch.nn.Parameter) and root.requires_grad and root.is_leaf:
            expected.add(self._update_identity(root))
        pending = [root.grad_fn]
        visited = set()
        while pending:
            node = pending.pop()
            if node is None or node in visited:
                continue
            visited.add(node)
            if len(visited) > 65536:
                raise ValueError("backward graph observation limit exceeded")
            variable = getattr(node, "variable", None)
            if isinstance(variable, torch.nn.Parameter) and variable.requires_grad:
                expected.add(self._update_identity(variable))
                if len(expected) > 4096:
                    raise ValueError("backward parameter coverage limit exceeded")
            pending.extend(next_node for next_node, _ in node.next_functions)
        if not expected:
            raise ValueError("no observable leaf Parameter update contract")
        return expected

    @staticmethod
    def _graph_task():
        try:
            value = torch._C._current_graph_task_id()
            return value if type(value) is int else None
        except (AttributeError, RuntimeError):
            return None

    def _optimizer_step_start(self, optimizer, args, kwargs):
        if os.getpid() != self.pid or self.finished:
            return
        self._optimizer_step_calls += 1
        self._optimizer_group_options.observe(
            optimizer,
            stage="step_pre",
            call=self._optimizer_step_calls,
            identify=self._existing_update_identity,
        )
        task = self._graph_task()
        groups = list(self._backward_groups.values())
        group = groups[0] if len(groups) == 1 and task is not None and task >= 0 else None
        unsupported = bool(groups) or task != -1
        if group is not None:
            unsupported = False
            group["calls"] += 1
            group["pending"].add(self._optimizer_step_calls)
            if group["graph_task"] is None:
                group["graph_task"] = task
            elif group["graph_task"] != task:
                self._group_problem(group, "multiple_autograd_graph_tasks")
            if group["expected"] is None:
                try:
                    group["expected"] = self._backward_parameters(group)
                except Exception:  # noqa: BLE001 - unsupported graph remains incomplete
                    group["expected"] = set()
                    self._group_problem(group, "backward_parameter_coverage_unavailable")
            if group["calls"] > 8192:
                self._group_problem(group, "optimizer_call_observation_limit")
                raise CaptureSetupError("Optimizer-in-backward observation limit exceeded")
        elif unsupported:
            for active in groups:
                self._group_problem(active, "optimizer_callback_scope_unverified")
            self._error(
                "optimizer_update",
                RuntimeError("Optimizer callback has no unique Tensor.backward boundary"),
            )
        key = (threading.get_ident(), id(optimizer))
        previous = self._optimizer_pending.get(key)
        if previous is not None and previous["group"] is not None:
            self._group_problem(previous["group"], "optimizer_call_did_not_complete")
        observed = []
        seen = set()
        # A closure can populate or replace gradients after this pre-hook.
        # Preserve ordinary step counting without claiming its update set is known.
        complete = not (
            kwargs.get("closure") is not None or any(callable(value) for value in args[1:])
        )
        try:
            for parameter_group in optimizer.param_groups:
                for parameter in parameter_group["params"]:
                    if parameter.grad is None:
                        continue
                    token = self._update_identity(parameter)
                    if token in seen:
                        raise ValueError("duplicate parameter in optimizer groups")
                    seen.add(token)
                    if len(seen) > 4096:
                        raise ValueError("optimizer parameter observation limit")
                    observed.append((weakref.ref(parameter), token, parameter._version))
        except Exception:  # noqa: BLE001 - ordinary steps retain prior counting, with unknown coverage
            complete = False
            if group is not None:
                self._group_problem(group, "optimizer_parameter_observation_unavailable")
        self._optimizer_pending[key] = {
            "group": group,
            "call": self._optimizer_step_calls,
            "observed": observed,
            "complete": complete,
            "unsupported": unsupported,
        }

    def _optimizer_step(self, optimizer: torch.optim.Optimizer, args: Any, kwargs: Any) -> None:
        if os.getpid() != self.pid or self.finished:
            return
        self._optimizer_successful_step_calls += 1
        frame = self._optimizer_pending.pop((threading.get_ident(), id(optimizer)), None)
        if frame is None:
            self._error(
                "optimizer_update", RuntimeError("Optimizer post hook has no matching pre hook")
            )
            return
        group = frame["group"]
        updated = []
        complete = frame["complete"] and bool(frame["observed"])
        for reference, token, version in frame["observed"]:
            parameter = reference()
            if parameter is not None and parameter._version > version:
                updated.append(token)
            else:
                complete = False
        optimizer_name = f"{type(optimizer).__module__}.{type(optimizer).__name__}"
        if group is not None:
            group["pending"].discard(frame["call"])
            group["successful_calls"] += 1
            group["classes"].add(optimizer_name)
            if not complete or not updated:
                self._group_problem(group, "parameter_update_not_observed")
            for token in updated:
                group["updated"][token] = group["updated"].get(token, 0) + 1
            return
        if frame["unsupported"]:
            return
        self._record_optimizer_update(
            optimizer,
            optimizer_name,
            "optimizer_post_hook",
            1,
            updated,
            parameter_coverage_complete=complete,
        )

    def _reject_backward_group(self, group):
        self._error("optimizer_update", RuntimeError("Incomplete optimizer-in-backward update"))
        if len(self._backward_update_failures) < 64:
            self._backward_update_failures.append(
                {
                    "optimizer_step_calls": group["calls"],
                    "successful_step_calls": group["successful_calls"],
                    "observed_updated_parameters": sorted(group["updated"]),
                    "expected_parameters": sorted(group["expected"] or []),
                    "reasons": list(group["reasons"]),
                }
            )
        # An exception may leave pre-hooks without a matching post-hook. Keep
        # their actual call counters, but do not retain the failed graph context.
        self._optimizer_pending = {
            key: frame
            for key, frame in self._optimizer_pending.items()
            if frame["group"] is not group
        }

    def _complete_backward_group(self, group):
        if group["pending"] or group["calls"] != group["successful_calls"]:
            self._group_problem(group, "optimizer_call_did_not_complete")
        if not group["expected"] or set(group["updated"]) != group["expected"]:
            self._group_problem(group, "backward_parameter_updates_not_fully_covered")
        if any(count != 1 for count in group["updated"].values()):
            self._group_problem(group, "parameter_updated_more_than_once")
        if group["reasons"]:
            self._reject_backward_group(group)
            return
        self._record_optimizer_update(
            None,
            "complete_tensor_backward",
            "complete_tensor_backward",
            group["calls"],
            sorted(group["updated"]),
            parameter_coverage_complete=True,
            optimizer_classes=sorted(group["classes"]),
        )

    def _record_optimizer_update(
        self,
        optimizer,
        name,
        basis,
        calls,
        updated,
        *,
        parameter_coverage_complete,
        optimizer_classes=None,
    ):
        if self._recorded_update_members + len(updated) > 65536:
            self._error(
                "optimizer_update", RuntimeError("Update-set evidence exceeds its bounded limit")
            )
            return
        self._recorded_update_members += len(updated)
        if self.device == "cuda":
            torch.cuda.synchronize(self.device_index)
        ended = time.perf_counter()
        if self.pairing_capture is not None:
            # None deliberately cannot match the fixed single-optimizer adapter.
            # Grouping callbacks must not manufacture a stronger pairing proof.
            self.pairing_capture.step(optimizer)
            if not self._pairing_hash_excluded:
                self.last_step_at += self.pairing_capture.hash_seconds
                self._pairing_hash_excluded = True
        self._sample_parameters()
        allocated, reserved = self._peaks()
        self.step_records.append(
            {
                "step": len(self.step_records) + 1,
                "optimizer": name,
                "update_basis": basis,
                "optimizer_step_calls": calls,
                "optimizer_classes": optimizer_classes or [name],
                "updated_parameter_ids": sorted(updated),
                "parameter_update_coverage_complete": parameter_coverage_complete,
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

    def _optimizer_update_evidence(self):
        boundary_complete = not any(e["stage"] == "optimizer_update" for e in self.errors)
        coverage_complete = bool(self.step_records) and all(
            record["parameter_update_coverage_complete"] for record in self.step_records
        )
        return {
            "protocol": "headroom.optimizer_updates.v1",
            "complete": boundary_complete and coverage_complete,
            "logical_boundary_complete": boundary_complete,
            "parameter_update_sets_complete": coverage_complete,
            "optimizer_step_calls": self._optimizer_step_calls,
            "successful_optimizer_step_calls": self._optimizer_successful_step_calls,
            "logical_updates": len(self.step_records),
            "parameter_catalog": self._update_catalog,
            "group_options": self._optimizer_group_options.snapshot(),
            "parameter_catalog_initialization": {
                "successful_base_constructor_returns": self._optimizer_base_constructions_observed,
                "complete": bool(self._optimizer_base_constructions_observed)
                and self._optimizer_initial_catalog_complete,
                "scope": "Metadata from groups after successful torch.optim.Optimizer.__init__; "
                "not custom-subclass completion or an optimizer update. Later step/graph "
                "observations may also add identities. No tensor values are read or copied.",
            },
            "failed_backward_groups": self._backward_update_failures,
            "coverage": "Process-local Parameter identities and optimizer pre/post hooks; "
            "version-counter changes are observations, not numerical equivalence. A grouped update "
            "requires one successful complete Tensor.backward and exactly-once coverage of its "
            "observable leaf Parameters. Restricted/nested/concurrent graphs are unsupported. "
            "Ordinary outer optimizer calls retain the legacy counting contract. "
            "This is cooperative instrumentation, not authentication against target tampering.",
        }

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
        if self.pairing_capture is not None:
            self.pairing_capture.close()
        if torch.optim.Optimizer.__init__ is self._optimizer_init_wrapper:
            torch.optim.Optimizer.__init__ = self._original_optimizer_init
        if self._step_pre_handle is not None:
            self._step_pre_handle.remove()
            self._step_pre_handle = None
        if self._step_handle is not None:
            self._step_handle.remove()
            self._step_handle = None
        for handle in self._parameter_handles:
            handle.remove()
        self._parameter_handles.clear()
        self._close_precision_mode()
        self._checkpoint_precision.close()
        if torch.Tensor.backward is self._backward_wrapper:
            torch.Tensor.backward = self._original_backward
        if _ACTIVE_SESSION is self:
            _ACTIVE_SESSION = None
        self.installed = False

    def _precision_evidence(self):
        evidence = self.precision_observer.snapshot()
        if any(error["stage"] == "precision_observation" for error in self.errors):
            evidence["complete"], evidence["precision"] = False, "unknown"
        return evidence

    def _entrypoint_evidence(self):
        if self.entrypoint_capture is None:
            return None
        try:
            return self.entrypoint_capture.finish()
        except Exception as exc:  # noqa: BLE001 - failure of optional metadata cannot erase the capture
            self._error("execution_entrypoint", exc)
            return {"schema_version": 1, "complete": False, "reason": "ENTRYPOINT_CAPTURE_FAILED"}

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
        self.finished = True
        reason = termination_reason or "script_exit"
        if self.deadline_reached:
            status, reason = "timeout", "timeout"
        elif isinstance(exc, StepLimitReached):
            status, reason = "completed", "step_limit"
        elif isinstance(exc, CaptureTimeout):
            status, reason = "timeout", "timeout"
        elif exc is not None:
            # Exception text can itself synchronize CUDA or block; classify it
            # only after the allocator snapshot and first durable observations.
            status, reason = "error", termination_reason or "exception"
        # Persist already observed facts before any potentially slow CUDA/history work.
        # A provisional completed/OOM execution must never look like an accepted capture.
        last_step = self.step_records[-1] if self.step_records else {}
        allocated = last_step.get("peak_allocated_bytes")
        reserved = last_step.get("peak_reserved_bytes")
        artifact_writes = {
            name: "pending"
            for name in (
                "memory_stats.json",
                "memory_summary.txt",
                "traceback.txt",
                "env.json",
                "snapshot.pickle",
                "snapshot.json",
            )
        }
        self._result = {
            "protocol": "headroom.lab.v1",
            "schema_version": 1,
            "capture_complete": False,
            "finalization_incomplete": True,
            "execution_status": status,
            "execution_termination_reason": reason,
            "status": "timeout" if status == "timeout" else "error",
            "termination_reason": "timeout" if status == "timeout" else "capture_incomplete",
            "pid": self.pid,
            "is_primary": self.is_primary,
            "optimizer_update_observation": self._optimizer_update_evidence(),
            "steps": len(self.step_records),
            "loss_series": self.loss_series,
            "step_records": self.step_records,
            "peak_allocated_bytes": allocated,
            "peak_reserved_bytes": reserved,
            "peak_alloc_gb": allocated / 1e9 if allocated is not None else None,
            "peak_reserved_gb": reserved / 1e9 if reserved is not None else None,
            "peak_observation": "last_completed_optimizer_update" if last_step else "unavailable",
            "deadline_observation": self.deadline_observation,
            "deadline_reached": self.deadline_reached,
            "snapshot": {"available": False, "trace_count": None},
            "snapshot_trace_count": None,
            "shared_gpu": self.shared_gpu,
            "gpu": self.gpu,
            "env": self.env,
            "errors": self.errors,
            "artifact_writes": artifact_writes,
        }

        def checkpoint(stage: str) -> None:
            self._result["finalization_stage"] = stage
            self._result["wall_seconds"] = time.perf_counter() - self.started_at
            _atomic_json(self.output_dir / "result.json", self._result)

        try:
            checkpoint("snapshot_capture")
            # Still the first CUDA operation in the exception finalization path.
            snapshot = self.take_snapshot()
        finally:
            # Even a failed first checkpoint or an interrupted snapshot must not
            # leave global optimizer/backward hooks installed.
            self._uninstall()
        allocated, reserved = self._peaks()
        self._result.update(
            peak_allocated_bytes=allocated,
            peak_reserved_bytes=reserved,
            peak_alloc_gb=allocated / 1e9 if allocated is not None else None,
            peak_reserved_gb=reserved / 1e9 if reserved is not None else None,
            peak_observation="capture_end" if allocated is not None else "unavailable",
        )
        trace_count = None
        if isinstance(snapshot, dict) and isinstance(snapshot.get("device_traces"), list):
            trace_count = sum(len(events) for events in snapshot["device_traces"])
        self._result.update(
            snapshot={"available": snapshot is not None, "trace_count": trace_count},
            snapshot_trace_count=trace_count,
        )
        checkpoint("exception_classification")
        if (
            exc is not None
            and not self.deadline_reached
            and not isinstance(exc, (StepLimitReached, CaptureTimeout))
            and is_cuda_oom(exc, self.device)
        ):
            status, reason = "oom", "oom"
        self._result.update(execution_status=status, execution_termination_reason=reason)
        checkpoint("exception_formatting")
        exception_text = "".join(traceback.format_exception(exc)) if exc is not None else ""
        checkpoint("memory_observations")
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
        oom = None
        if status == "oom":
            oom = parse_oom_details(snapshot, str(exc), self.device_index)
            oom["traceback"] = exception_text
        # Small observations reach disk before the full, unchanged allocator history.
        artifact_writers = {
            "memory_stats.json": lambda path: _atomic_json(path, memory_stats),
            "memory_summary.txt": lambda path: path.write_text(memory_summary),
            "traceback.txt": lambda path: path.write_text(exception_text),
            "env.json": lambda path: _atomic_json(path, self.env),
            "snapshot.pickle": lambda path: _atomic_pickle(path, snapshot),
            "snapshot.json": lambda path: _atomic_json(path, encode_snapshot(snapshot)),
        }
        for filename, writer in artifact_writers.items():
            checkpoint(f"write:{filename}")
            try:
                writer(self.output_dir / filename)
                artifact_writes[filename] = "complete"
            except Exception as artifact_error:  # noqa: BLE001 - report capture failures
                artifact_writes[filename] = "failed"
                self._error(f"write:{filename}", artifact_error)
        checkpoint("post_capture_observations")
        if self.gpu is not None:
            self.gpu["at_capture_end"] = self._gpu_processes()
            self.gpu["shared_gpu_basis"] = "compute processes before capture CUDA initialization"
        if self.history_enabled:
            try:
                torch.cuda.memory._record_memory_history(enabled=None)
            except Exception as history_error:  # noqa: BLE001 - report capture failures
                self._error("history_disable", history_error)
        execution_status = status
        critical_stages = {
            "snapshot",
            "peak_stats",
            "memory_stats",
            "memory_summary",
            "optimizer_update",
        }
        capture_complete = self.ready and not any(
            error["stage"] in critical_stages or error["stage"].startswith("write:")
            for error in self.errors
        )
        if self.device == "cuda" and (snapshot is None or allocated is None or reserved is None):
            capture_complete = False
        if not capture_complete and status != "timeout":
            status, reason = "error", "capture_error"
        self._result = {
            "protocol": "headroom.lab.v1",
            **self._parameter_evidence(),
            "precision_observation": self._precision_evidence(),
            "execution_entrypoint": self._entrypoint_evidence(),
            "deadline_observation": self.deadline_observation,
            "deadline_reached": self.deadline_reached,
            "pairing_capture": self.pairing_capture.evidence(len(self.step_records))
            if self.pairing_capture is not None
            else {"complete": False, "reason": "pairing requires a supported run_script target"},
            "schema_version": 1,
            "capture_complete": capture_complete,
            "finalization_incomplete": False,
            "finalization_stage": "finished",
            "artifact_writes": artifact_writes,
            "execution_status": execution_status,
            "status": status,
            "termination_reason": reason,
            "pid": self.pid,
            "is_primary": self.is_primary,
            "optimizer_update_observation": self._optimizer_update_evidence(),
            "steps": len(self.step_records),
            "loss_series": self.loss_series,
            "step_records": self.step_records,
            "peak_allocated_bytes": allocated,
            "peak_reserved_bytes": reserved,
            "peak_alloc_gb": allocated / 1e9 if allocated is not None else None,
            "peak_reserved_gb": reserved / 1e9 if reserved is not None else None,
            "peak_observation": "capture_end" if allocated is not None else "unavailable",
            "step_ms_median": statistics.median([record["step_ms"] for record in self.step_records])
            if self.step_records
            else None,
            "timing_note": "Intervals between completed optimizer updates; first includes target setup; "
            "pairing initialization hash time excluded, total wall time retains it; "
            "module/precision observation overhead remains in measured intervals",
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
        from headroom.lab.entrypoint import EntrypointCapture

        session.entrypoint_capture = EntrypointCapture()
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
