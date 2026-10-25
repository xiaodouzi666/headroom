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
    "checkpoint_scope_unverified",
    "checkpoint_context_unverified",
    "checkpoint_recompute_failed",
    "checkpoint_reentrant_unsupported",
    "checkpoint_adapter_changed",
    "thread_observer_limit",
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
        self._worker_observers = {}
        self._function_scope_depth = 0
        self._mode_entries = self._mode_exits = 0
        self._checkpoint_counts = dict.fromkeys(("entered", "exited", "early_stops", "failed"), 0)
        self._graph_metadata_outputs = 0
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

    def active_observer(self):
        """An unregistered or inactive thread still routes to the rejecting owner."""
        if threading.get_ident() == self._owner_thread:
            return self
        child = self._worker_observers.get(threading.get_ident())
        return child if child is not None and child._function_scope_depth else self

    def explicit_worker_observer(self):
        """Only the Lab's verified checkpoint callback may provision this observer."""
        if threading.get_ident() == self._owner_thread:
            return self
        thread = threading.get_ident()
        if thread not in self._worker_observers:
            if len(self._worker_observers) >= 8:
                self._error("thread_observer_limit")
                return None
            self._worker_observers[thread] = PrecisionObserver(
                self.device,
                max_nodes=self.max_nodes,
                max_depth=self.max_depth,
                max_parameters=self.max_parameters,
                max_forward_depth=self.max_forward_depth,
            )
        return self._worker_observers[thread]

    def observe_recompute(self, function, args, kwargs):
        """Observe the actual function body, including module-free operations."""
        from torch.utils.checkpoint import _StopRecomputationError

        self._function_scope_depth += 1
        self._checkpoint_counts["entered"] += 1
        try:
            with self.operation_mode():
                synthetic = self._depth == 0
                if synthetic:
                    self._root = {
                        "bf16": False,
                        "unsupported": False,
                        "unknown": False,
                        "floating": False,
                        "mode_covered": self._mode_depth > 0,
                    }
                    self._depth = 1
                self._observing = True
                try:
                    self._autocast_state()
                    self._values(args, "input")
                    self._values(kwargs, "input")
                except Exception:  # noqa: BLE001 - metadata errors cannot change target execution
                    self._error("metadata_failed")
                finally:
                    self._observing = False
                try:
                    result = function(*args, **kwargs)
                    self._observing = True
                    try:
                        self._autocast_state()
                        self._values(result, "output")
                    except Exception:  # noqa: BLE001 - metadata errors cannot change target execution
                        self._error("metadata_failed")
                    finally:
                        self._observing = False
                    return result
                except _StopRecomputationError:
                    # Official non-reentrant early-stop is successful coverage
                    # of the function prefix that actually executed.
                    self._checkpoint_counts["early_stops"] += 1
                    raise
                except BaseException:
                    self._checkpoint_counts["failed"] += 1
                    self._error("checkpoint_recompute_failed")
                    raise
                finally:
                    if synthetic:
                        if self._depth != 1:
                            self._error("unbalanced_hooks")
                        self._depth = 0
                        self._finish_root()
        finally:
            self._checkpoint_counts["exited"] += 1
            self._function_scope_depth -= 1

    def _finish_root(self):
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
            self._finish_root()

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
                self._mode_entries += 1
                try:
                    yield
                finally:
                    self._mode_exits += 1
        finally:
            self._mode_depth = 0
            if self._depth:
                self._error("operation_mode_error")

    def _own_snapshot(self) -> dict:
        errors = {name: count for name, count in self._errors.items() if count}
        if self._depth or self._mode_depth or self._function_scope_depth:
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
            "checkpoint_recompute": dict(self._checkpoint_counts),
            "operation_mode_lifecycle": {"entered": self._mode_entries, "exited": self._mode_exits},
            "recognized_graph_metadata_outputs": self._graph_metadata_outputs,
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
                    "Known compiled wrappers and unregistered or unobserved worker forwards remain unknown.",
                    "Metadata observation adds Python overhead; no tensor data or GPU synchronization is added.",
                    "Runtime hooks are not authentication against deliberate target tampering.",
                ],
            },
        }

    def snapshot(self):
        result = self._own_snapshot()
        children = [child._own_snapshot() for child in self._worker_observers.values()]
        for child in children:
            for field in (
                "root_modes",
                "counts",
                "autocast",
                "errors",
                "checkpoint_recompute",
                "operation_mode_lifecycle",
            ):
                for key, value in child[field].items():
                    result[field][key] = result[field].get(key, 0) + value
            for role in _ROLES:
                for key, value in child["dtypes"][role].items():
                    result["dtypes"][role][key] += value
            result["recognized_graph_metadata_outputs"] += child[
                "recognized_graph_metadata_outputs"
            ]
        observed = [name for name, count in result["root_modes"].items() if count]
        result["complete"] = bool(
            not result["errors"]
            and result["counts"]["root_forwards"] > 0
            and result["root_modes"]["unknown"] == 0
            and len(observed) == 1
            and result["operation_mode_lifecycle"]["entered"]
            == result["operation_mode_lifecycle"]["exited"]
            and result["checkpoint_recompute"]["entered"]
            == result["checkpoint_recompute"]["exited"]
        )
        result["precision"] = observed[0] if result["complete"] else "unknown"
        result["worker_observers"] = {
            "registered": len(children),
            "basis": "explicit checkpoint function boundary with actual thread-local operation mode",
            "snapshots": [
                {
                    key: child[key]
                    for key in (
                        "complete",
                        "precision",
                        "root_modes",
                        "operation_mode_lifecycle",
                        "checkpoint_recompute",
                        "errors",
                    )
                }
                for child in children
            ],
        }
        return result


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
            if (
                getattr(func, "__name__", None) == "__get__"
                and getattr(func, "__self__", None) is torch.Tensor.grad_fn
                and isinstance(result, torch.autograd.graph.Node)
            ):
                # Tensor.grad_fn returns graph metadata, not an unobserved dtype.
                observer._graph_metadata_outputs += 1
            else:
                observer._values(result, "operation_output")
        except Exception:  # noqa: BLE001
            observer._error("metadata_failed")
        finally:
            observer._observing = False
        return result


class CheckpointPrecisionAdapter:
    """Pinned torch 2.5.1 non-reentrant recompute boundary, preserving user contexts.

    The official generator closes over fn for recomputation, while the public
    API calls the original fn for the initial forward. Wrapping that argument
    covers the actual recomputation function, including functional-only code.
    Non-default user contexts execute unchanged but remain unverified: custom
    dispatch modes may hide internal operations from an outer observer.
    Existing imported aliases of checkpoint still resolve this module helper.
    """

    def __init__(self, observer, recompute):
        self.observer, self.recompute = observer, recompute
        self.module = None
        self.original = self.original_reentrant = None
        self.wrapper = self.reentrant_wrapper = None

    def install(self):
        import inspect

        import torch.utils.checkpoint as module

        try:
            original = module._checkpoint_without_reentrant_generator
            reentrant = module.CheckpointFunction.forward
            parameters = list(inspect.signature(original).parameters.values())
            compatible = (
                str(torch.__version__).split("+")[0] == "2.5.1"
                and callable(original)
                and callable(reentrant)
                and original.__module__ == "torch.utils.checkpoint"
                and original.__name__ == "_checkpoint_without_reentrant_generator"
                and reentrant.__module__ == "torch.utils.checkpoint"
                and reentrant.__qualname__ == "CheckpointFunction.forward"
                and [item.name for item in parameters]
                == [
                    "fn",
                    "preserve_rng_state",
                    "context_fn",
                    "determinism_check",
                    "debug",
                    "args",
                    "kwargs",
                ]
                and [item.kind for item in parameters]
                == [
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ]
                and parameters[2].default is module.noop_context_fn
            )
        except Exception:  # noqa: BLE001 - an optional observer cannot break training
            compatible = False
        if not compatible:
            self.observer._error("checkpoint_scope_unverified")
            return
        self.module, self.original, self.original_reentrant = module, original, reentrant

        def generator(function, *args, **kwargs):
            if torch.compiler.is_compiling():
                return self.original(function, *args, **kwargs)
            if (
                isinstance(function, (torch.jit.ScriptModule, torch.jit.ScriptFunction))
                or hasattr(function, "_torchdynamo_orig_callable")
                or (
                    isinstance(function, torch.nn.Module)
                    and not self.observer.operation_supported(function)
                )
            ):
                self.observer._error("compiled_module")
                return self.original(function, *args, **kwargs)
            forward_observer = self.observer.active_observer()
            if forward_observer._root is None or not forward_observer._mode_depth:
                self.observer._error("operation_mode_missing")
            context = args[1] if len(args) > 1 else kwargs.get("context_fn", module.noop_context_fn)
            if context is not module.noop_context_fn:
                self.observer._error("checkpoint_context_unverified")
                # Do not change dispatch-mode ordering inside unreviewed contexts.
                return self.original(function, *args, **kwargs)

            def observed_function(*inputs, **keywords):
                return self.recompute(function, inputs, keywords)

            return self.original(observed_function, *args, **kwargs)

        def reentrant(*args, **kwargs):
            self.observer._error("checkpoint_reentrant_unsupported")
            return self.original_reentrant(*args, **kwargs)

        self.wrapper, self.reentrant_wrapper = generator, reentrant
        module._checkpoint_without_reentrant_generator = generator
        module.CheckpointFunction.forward = staticmethod(reentrant)

    def close(self):
        if self.module is None:
            return
        if self.module._checkpoint_without_reentrant_generator is self.wrapper:
            self.module._checkpoint_without_reentrant_generator = self.original
        else:
            self.observer._error("checkpoint_adapter_changed")
        if self.module.CheckpointFunction.forward is self.reentrant_wrapper:
            self.module.CheckpointFunction.forward = staticmethod(self.original_reentrant)
        else:
            self.observer._error("checkpoint_adapter_changed")
        self.module = None
