"""Bounded runtime precision evidence from module forwards and TorchFunctionMode.

Only tensor metadata is inspected. No tensor is copied, hashed, converted to a
scalar, synchronized, or retained. This describes observed forward precision,
not the dtype of every operator or proof against deliberate hook tampering.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import torch
from torch.overrides import TorchFunctionMode

PROTOCOL = "headroom.precision.v1"
SOURCE = "lab_runtime_precision_observer_v1"
_MAX_COUNT = 2**31 - 1
_DTYPES = ("float32", "bfloat16", "float16", "float64", "complex", "other_floating", "non_floating")
_ROLES = ("parameter", "input", "output", "operation_input", "operation_output")
_ERRORS = (
    "autocast_query_failed",
    "metadata_failed",
    "structure_unsupported",
    "node_limit",
    "parameter_limit",
    "forward_depth_limit",
    "unbalanced_hooks",
    "cross_thread",
    "counter_limit",
    "operation_mode_missing",
    "operation_mode_error",
    "compiled_module",
)


class PrecisionObserver:
    """Observe all module hooks; use operation_mode only inside each root forward.

    The operation mode catches autocast enabled *inside* a root forward even
    when a functional operation's BF16 output is converted back to FP32 before
    the module returns. Each root forward requires this coverage for complete
    evidence. A module-only snapshot remains diagnostic and cannot select a
    relaxed numeric threshold.

    Pass the same device type used by the Lab. The caller owns global hook
    installation/removal: enter operation_mode just before the root pre sample,
    exit after the root post sample in a finally block, and retain cleanup as a
    fallback. Never keep the mode active across external backward/optimizer calls,
    since even a passthrough mode changes TorchFunction dispatch. Skip mode when
    operation_supported(root) is false. Observation methods always return None.
    """

    def __init__(
        self,
        device: str,
        *,
        max_nodes: int = 256,
        max_depth: int = 8,
        max_parameters: int = 256,
        max_forward_depth: int = 256,
    ) -> None:
        if device not in {"cpu", "cuda"}:
            raise ValueError("Precision observation requires cpu or cuda")
        for limit in (max_nodes, max_depth, max_parameters, max_forward_depth):
            if type(limit) is not int or not 1 <= limit <= 4096:
                raise ValueError("Precision observation bounds must be integers from 1 to 4096")
        self.device = device
        self.max_nodes, self.max_depth = max_nodes, max_depth
        self.max_parameters, self.max_forward_depth = max_parameters, max_forward_depth
        self._owner_thread = threading.get_ident()
        self._depth = 0
        self._mode_depth = 0
        self._observing = False
        self._root: dict[str, Any] | None = None
        self._errors = dict.fromkeys(_ERRORS, 0)
        self._counts = dict.fromkeys(
            (
                "module_pre",
                "module_post",
                "root_forwards",
                "operation_calls",
                "tensor_metadata",
                "ignored_device_tensors",
            ),
            0,
        )
        self._autocast = dict.fromkeys(("disabled", "bfloat16", "unsupported", "unknown"), 0)
        self._dtypes = {role: dict.fromkeys(_DTYPES, 0) for role in _ROLES}
        self._roots = dict.fromkeys(("fp32", "bf16", "unknown"), 0)

    @staticmethod
    def operation_supported(module: torch.nn.Module) -> bool:
        """Do not install a Python dispatch mode around known compiled subtrees.

        Inspect only module metadata, with a bound and no retained references.
        Checking children matters: a normal root can contain a scripted/compiled
        block whose behavior must remain unchanged.
        """
        pending, seen = [module], set()
        try:
            while pending:
                current = pending.pop()
                identity = id(current)
                if identity in seen:
                    continue
                seen.add(identity)
                if len(seen) > 4096 or isinstance(current, torch.jit.ScriptModule):
                    return False
                if type(current).__module__.startswith("torch._dynamo."):
                    return False
                children = vars(current).get("_modules", {})
                if not isinstance(children, dict) or len(pending) + len(children) > 4096:
                    return False
                pending.extend(child for child in children.values() if child is not None)
        except Exception:  # noqa: BLE001 - unavailable metadata must not break the target
            return False
        return True

    def _increment(self, values: dict, name: str) -> None:
        if values[name] < _MAX_COUNT:
            values[name] += 1
        else:
            self._errors["counter_limit"] = 1

    def _error(self, code: str) -> None:
        self._increment(self._errors, code)
        if self._root is not None:
            self._root["unknown"] = True

    def _owned_thread(self) -> bool:
        if threading.get_ident() == self._owner_thread:
            return True
        self._error("cross_thread")
        return False

    def _autocast_state(self) -> None:
        try:
            enabled = torch.is_autocast_enabled(self.device)
            if not enabled:
                self._increment(self._autocast, "disabled")
                return
            dtype = torch.get_autocast_dtype(self.device)
            if dtype is torch.bfloat16:
                self._increment(self._autocast, "bfloat16")
                self._root["bf16"] = True
            else:
                self._increment(self._autocast, "unsupported")
                self._root["unsupported"] = True
        except Exception:  # noqa: BLE001 - diagnostic observation must not change the workload
            self._increment(self._autocast, "unknown")
            self._error("autocast_query_failed")

    def _tensor(self, tensor: torch.Tensor, role: str) -> None:
        self._increment(self._counts, "tensor_metadata")
        if tensor.device.type != self.device:
            self._increment(self._counts, "ignored_device_tensors")
            return
        dtype = tensor.dtype
        if dtype is torch.float32:
            bucket = "float32"
        elif dtype is torch.bfloat16:
            bucket = "bfloat16"
        elif dtype is torch.float16:
            bucket = "float16"
        elif dtype is torch.float64:
            bucket = "float64"
        elif dtype.is_complex:
            bucket = "complex"
        elif dtype.is_floating_point:
            bucket = "other_floating"
        else:
            bucket = "non_floating"
        self._increment(self._dtypes[role], bucket)
        if bucket == "non_floating":
            return
        self._root["floating"] = True
        if bucket == "bfloat16":
            self._root["bf16"] = True
        elif bucket != "float32":
            self._root["unsupported"] = True

    def _values(self, value: Any, role: str, *, strict_structure: bool = True) -> None:
        # Iterators live only for this call and are bounded. No input/output
        # object, tensor, parameter, module, or iterator is stored on self.
        remaining = self.max_nodes

        def visit(current: Any, depth: int) -> None:
            nonlocal remaining
            if remaining == 0 or depth > self.max_depth:
                self._error("node_limit")
                return
            remaining -= 1
            if isinstance(current, torch.Tensor):
                self._tensor(current, role)
            elif isinstance(current, (tuple, list, dict)):
                values = current.values() if isinstance(current, dict) else current
                for item in values:
                    if remaining == 0:
                        self._error("node_limit")
                        break
                    visit(item, depth + 1)
            elif (
                current is None
                or type(current) in (bool, int, float, str)
                or isinstance(
                    current, (torch.dtype, torch.device, torch.layout, torch.memory_format)
                )
            ):
                pass
            elif strict_structure:
                self._error("structure_unsupported")

        visit(value, 0)

    def observe_pre(self, module: torch.nn.Module, args: Any) -> None:
        # Dynamo recognizes this predicate without tracing our thread/state work.
        # The compiled outer module already remains unknown without operation mode.
        if torch.compiler.is_compiling():
            return
        if not self._owned_thread():
            return
        self._increment(self._counts, "module_pre")
        if self._depth == 0:
            self._root = {
                "bf16": False,
                "unsupported": False,
                "unknown": False,
                "floating": False,
                "mode_covered": self._mode_depth > 0,
            }
            if not self._root["mode_covered"]:
                self._error("operation_mode_missing")
        self._depth = min(self._depth + 1, _MAX_COUNT)
        if self._depth > self.max_forward_depth:
            self._error("forward_depth_limit")
        self._observing = True
        try:
            # Known compiled module wrappers can hide internal autocast entirely.
            if isinstance(module, torch.jit.ScriptModule) or type(module).__module__.startswith(
                "torch._dynamo."
            ):
                self._error("compiled_module")
            self._autocast_state()
            self._values(args, "input")
            for index, parameter in enumerate(module.parameters(recurse=False)):
                if index >= self.max_parameters:
                    self._error("parameter_limit")
                    break
                self._tensor(parameter, "parameter")
        except Exception:  # noqa: BLE001
            self._error("metadata_failed")
        finally:
            self._observing = False

    def observe_post(self, module: torch.nn.Module, args: Any, output: Any) -> None:
        del module, args
        if torch.compiler.is_compiling():
            return
        if not self._owned_thread():
            return
        self._increment(self._counts, "module_post")
        if self._depth <= 0 or self._root is None:
            self._error("unbalanced_hooks")
            return
        self._observing = True
        try:
            self._autocast_state()
            self._values(output, "output")
        except Exception:  # noqa: BLE001
            self._error("metadata_failed")
        finally:
            self._observing = False
            self._depth -= 1
        if self._depth == 0:
            self._increment(self._counts, "root_forwards")
            root = self._root
            mode = (
                "unknown"
                if root["unknown"] or root["unsupported"] or not root["floating"]
                else "bf16"
                if root["bf16"]
                else "fp32"
            )
            self._increment(self._roots, mode)
            self._root = None

    @contextmanager
    def operation_mode(self) -> Iterator[None]:
        """Scope this to one root forward only; leave on the same thread."""
        if not self._owned_thread():
            yield
            return
        if self._mode_depth:
            # Avoid duplicate interception if a caller nests the context.
            self._mode_depth += 1
            try:
                yield
            finally:
                self._mode_depth -= 1
            return
        self._mode_depth = 1
        try:
            with _PrecisionMode(self):
                yield
        finally:
            self._mode_depth = 0
            if self._depth:
                self._error("operation_mode_error")

    def snapshot(self) -> dict:
        errors = {name: count for name, count in self._errors.items() if count}
        if self._depth:
            errors["unbalanced_hooks"] = max(errors.get("unbalanced_hooks", 0), 1)
        observed = [name for name, count in self._roots.items() if count]
        complete = (
            not errors
            and self._counts["root_forwards"] > 0
            and self._roots["unknown"] == 0
            and len(observed) == 1
        )
        precision = observed[0] if complete else "unknown"
        return {
            "protocol": PROTOCOL,
            "source": SOURCE,
            "device": self.device,
            "precision": precision,
            "complete": complete,
            "root_modes": dict(self._roots),
            "counts": dict(self._counts),
            "autocast": dict(self._autocast),
            "dtypes": {role: dict(counts) for role, counts in self._dtypes.items()},
            "errors": errors,
            "coverage": {
                "module_hooks": "Every observed module pre/post forward; direct registered parameters",
                "internal_autocast": "TorchFunctionMode samples autocast and tensor argument/output metadata during forwards",
                "root_summary": "Mixed root forward modes, unknown/unsupported dtypes, errors or limits are unknown",
                "tensor_data_access": False,
                "gpu_synchronization": False,
                "tensor_references_retained": False,
                "all_operator_dtypes_proven": False,
                "limitations": [
                    (
                        "TorchFunctionMode observes Python-dispatched torch functions; C++/compiled/custom "
                        "operators may not expose internal autocast or every intermediate dtype."
                    ),
                    "Metadata records observed precision, not tensor values or full numerical equivalence.",
                    "Known compiled module wrappers and cross-thread module forwards remain unknown.",
                    "Metadata observation adds Python overhead; no tensor data or GPU synchronization is added.",
                    "Runtime hooks are not authentication against deliberate target tampering.",
                ],
            },
        }


class _PrecisionMode(TorchFunctionMode):
    def __init__(self, observer: PrecisionObserver):
        super().__init__()
        self.observer = observer

    def __torch_function__(self, func, types, args=(), kwargs=None):
        observer = self.observer
        if observer._observing or observer._root is None:
            return func(*args, **(kwargs or {}))
        observer._increment(observer._counts, "operation_calls")
        observer._observing = True
        try:
            observer._autocast_state()
            observer._values(args, "operation_input", strict_structure=False)
            observer._values(kwargs or {}, "operation_input", strict_structure=False)
        except Exception:  # noqa: BLE001
            observer._error("metadata_failed")
        finally:
            observer._observing = False
        result = func(*args, **(kwargs or {}))
        observer._observing = True
        try:
            observer._values(result, "operation_output")
        except Exception:  # noqa: BLE001
            observer._error("metadata_failed")
        finally:
            observer._observing = False
        return result
