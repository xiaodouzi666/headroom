"""Actual CPU precision observations; no GPU, model API or tensor-data reads."""

import gc
import json
import weakref
from contextlib import contextmanager

import pytest
import torch
from torch.nn.modules.module import register_module_forward_hook, register_module_forward_pre_hook

from headroom.lab.precision import PrecisionObserver


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network/GPU operations are forbidden in precision unit tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(torch.cuda, "synchronize", denied)


@contextmanager
def observing(observer, *, mode=True):
    pre = register_module_forward_pre_hook(observer.observe_pre)
    post = register_module_forward_hook(observer.observe_post, always_call=True)
    try:
        if mode:
            with observer.operation_mode():
                yield observer
        else:
            yield observer
    finally:
        post.remove()
        pre.remove()


class FunctionalInternalAutocast(torch.nn.Module):
    def __init__(self, dtype=torch.bfloat16):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.ones(4, 4))
        self.dtype = dtype

    def forward(self, value):
        with torch.autocast("cpu", dtype=self.dtype):
            value = torch.nn.functional.linear(value, self.weight)
            # The final FP32 loss must not erase BF16 autocast observed inside forward.
            return value.float().square().mean()


class NestedInternalAutocast(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.layer = torch.nn.Linear(4, 4)

    def forward(self, value):
        with torch.autocast("cpu", dtype=torch.bfloat16):
            value = self.layer(value)
        return value.float().mean()


def test_plain_fp32_forward_is_observed_with_complete_coverage():
    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Linear(4, 4), torch.ones(2, 4)
    with observing(observer):
        output = model(value)
    observed = observer.snapshot()
    assert output.dtype is torch.float32
    assert observed["precision"] == "fp32" and observed["complete"] is True
    assert observed["counts"]["root_forwards"] == 1
    assert observed["root_modes"] == {"fp32": 1, "bf16": 0, "unknown": 0}
    assert observed["dtypes"]["parameter"]["float32"] == 2
    assert observed["source"] == "lab_runtime_precision_observer_v1"
    assert observed["protocol"] == "headroom.precision.v1"
    assert observed["coverage"]["all_operator_dtypes_proven"] is False


@pytest.mark.parametrize("model_factory", [FunctionalInternalAutocast, NestedInternalAutocast])
def test_internal_bf16_autocast_survives_fp32_parameters_and_fp32_loss(model_factory):
    observer = PrecisionObserver("cpu")
    model, value = model_factory(), torch.ones(2, 4)
    with observing(observer):
        output = model(value)
    observed = observer.snapshot()
    assert output.dtype is torch.float32
    assert observed["precision"] == "bf16" and observed["complete"] is True, observed
    assert observed["dtypes"]["parameter"]["float32"] > 0
    assert observed["autocast"]["bfloat16"] > 0
    assert observed["dtypes"]["operation_output"]["bfloat16"] > 0
    assert observed["dtypes"]["output"]["float32"] > 0


def test_external_bf16_autocast_and_direct_bf16_parameters():
    for direct in (False, True):
        model, value = torch.nn.Linear(4, 4), torch.ones(2, 4)
        observer = PrecisionObserver("cpu")
        if direct:
            model, value = model.bfloat16(), value.bfloat16()
            with observing(observer):
                output = model(value)
        else:
            with observing(observer), torch.autocast("cpu", dtype=torch.bfloat16):
                output = model(value)
        assert output.dtype is torch.bfloat16
        assert observer.snapshot()["precision"] == "bf16"
        assert observer.snapshot()["complete"] is True


def test_bf16_observations_stay_bf16_for_both_baseline_and_candidate():
    observations = []
    for _ in range(2):
        observer = PrecisionObserver("cpu")
        model, value = FunctionalInternalAutocast(), torch.ones(2, 4)
        with observing(observer):
            for _ in range(3):
                model(value)
        observations.append(observer.snapshot())
    assert all(item["precision"] == "bf16" and item["complete"] for item in observations)
    assert observations[0]["precision"] == observations[1]["precision"]


def test_mixed_root_modes_remain_unknown():
    model, value = torch.nn.Linear(4, 4), torch.ones(2, 4)
    observer = PrecisionObserver("cpu")
    with observing(observer):
        model(value)
        with torch.autocast("cpu", dtype=torch.bfloat16):
            model(value)
    observed = observer.snapshot()
    assert observed["root_modes"] == {"fp32": 1, "bf16": 1, "unknown": 0}
    assert observed["precision"] == "unknown" and observed["complete"] is False


@pytest.mark.parametrize("dtype", [torch.float16, torch.float64, torch.complex64])
def test_unsupported_floating_precision_never_claims_bf16_or_fp32(dtype):
    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Identity(), torch.ones(2, 4, dtype=dtype)
    with observing(observer):
        model(value)
    observed = observer.snapshot()
    assert observed["precision"] == "unknown" and observed["complete"] is False
    assert observed["root_modes"]["unknown"] == 1


def test_fp16_autocast_is_unsupported_even_with_float32_final_loss():
    observer = PrecisionObserver("cpu")
    model, value = FunctionalInternalAutocast(torch.float16), torch.ones(2, 4)
    with observing(observer):
        assert model(value).dtype is torch.float32
    observed = observer.snapshot()
    assert observed["precision"] == "unknown" and observed["complete"] is False
    assert observed["autocast"]["unsupported"] > 0


def test_module_only_observation_keeps_internal_coverage_unknown():
    observer = PrecisionObserver("cpu")
    model, value = FunctionalInternalAutocast(), torch.ones(2, 4)
    with observing(observer, mode=False):
        model(value)
    observed = observer.snapshot()
    assert observed["precision"] == "unknown" and observed["complete"] is False
    assert observed["errors"]["operation_mode_missing"] == 1


def test_no_forward_or_nonfloating_forward_is_unknown():
    observer = PrecisionObserver("cpu")
    assert observer.snapshot()["precision"] == "unknown"
    assert observer.snapshot()["complete"] is False
    with observing(observer):
        torch.nn.Identity()(torch.ones(2, dtype=torch.long))
    assert observer.snapshot()["precision"] == "unknown"


def test_operation_mode_ignores_work_outside_forward():
    observer = PrecisionObserver("cpu")
    with observing(observer), torch.autocast("cpu", dtype=torch.bfloat16):
        torch.ones(2, 2) @ torch.ones(2, 2)
    observed = observer.snapshot()
    assert observed["counts"]["operation_calls"] == 0
    assert observed["autocast"]["bfloat16"] == 0
    assert observed["precision"] == "unknown"


def test_no_tensor_data_read_copy_or_gpu_synchronization(monkeypatch):
    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Identity(), torch.ones(2, 4)

    def denied(*args, **kwargs):
        pytest.fail("Precision observations must inspect metadata only")

    for name in ("item", "numpy", "cpu", "clone", "detach", "tolist"):
        monkeypatch.setattr(torch.Tensor, name, denied)
    with observing(observer):
        result = model(value)
    assert result is value
    assert observer.snapshot()["precision"] == "fp32"


def test_observer_does_not_retain_module_parameter_input_or_output():
    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Linear(4, 4), torch.ones(2, 4)
    with observing(observer):
        output = model(value)
    references = [weakref.ref(item) for item in (model, model.weight, value, output)]
    del model, value, output
    gc.collect()
    assert all(reference() is None for reference in references)
    assert observer.snapshot()["precision"] == "fp32"


def test_metadata_and_bounds_errors_are_limited_and_do_not_expose_exception_text(monkeypatch):
    observer = PrecisionObserver("cpu", max_nodes=2)
    model, value = torch.nn.Identity(), torch.ones(2)

    def broken(*args, **kwargs):
        raise RuntimeError("private contents must not appear in evidence")

    monkeypatch.setattr(torch, "is_autocast_enabled", broken)
    with observing(observer):
        for _ in range(10):
            model([value, value, value])
    observed = observer.snapshot()
    assert observed["precision"] == "unknown" and observed["complete"] is False
    assert set(observed["errors"]) == {"autocast_query_failed", "node_limit"}
    assert "private contents" not in json.dumps(observed)
    assert len(json.dumps(observed)) < 5000


def test_parameter_bound_and_unbalanced_hooks_remain_unknown():
    observer = PrecisionObserver("cpu", max_parameters=1)
    module = torch.nn.Linear(4, 4)
    with observing(observer):
        module(torch.ones(1, 4))
    assert observer.snapshot()["errors"]["parameter_limit"] == 1
    assert observer.snapshot()["precision"] == "unknown"
    second = PrecisionObserver("cpu")
    second.observe_post(module, (), None)
    assert second.snapshot()["errors"]["unbalanced_hooks"] == 1


def test_nested_operation_context_does_not_duplicate_samples():
    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Linear(4, 4), torch.ones(2, 4)
    with observing(observer), observer.operation_mode():
        model(value)
    observed = observer.snapshot()
    assert observed["counts"]["root_forwards"] == 1
    assert observed["root_modes"]["fp32"] == 1
    assert observed["complete"] is True


def test_counters_saturate_without_growing_state():
    from headroom.lab import precision

    observer = PrecisionObserver("cpu")
    observer._counts["module_pre"] = precision._MAX_COUNT
    with observing(observer):
        torch.nn.Identity()(torch.ones(1))
    assert observer.snapshot()["counts"]["module_pre"] == precision._MAX_COUNT
    assert observer.snapshot()["errors"]["counter_limit"] > 0
    assert observer.snapshot()["precision"] == "unknown"


def test_tensor_metadata_inside_forward_is_not_unsupported():
    class Metadata(torch.nn.Module):
        def forward(self, value):
            assert value.dtype is torch.float32
            assert value.device.type == "cpu"
            assert value.layout is torch.strided
            return value.reshape(value.shape)

    observer = PrecisionObserver("cpu")
    with observing(observer):
        Metadata()(torch.ones(2, 4))
    assert observer.snapshot()["precision"] == "fp32"


def test_known_compiled_module_stays_unknown():
    scripted = torch.jit.script(torch.nn.Linear(4, 4))
    observer = PrecisionObserver("cpu")
    with observing(observer, mode=observer.operation_supported(scripted)):
        output = scripted(torch.ones(2, 4))
    assert output.shape == (2, 4)
    result = observer.snapshot()
    assert result["precision"] == "unknown" and result["complete"] is False
    assert result["errors"]["compiled_module"] > 0


def test_cross_thread_forward_stays_unknown():
    import threading

    observer = PrecisionObserver("cpu")
    model, value = torch.nn.Identity(), torch.ones(1)
    with observing(observer):
        model(value)
        thread = threading.Thread(target=lambda: model(value))
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()
    assert observer.snapshot()["errors"]["cross_thread"] > 0
    assert observer.snapshot()["complete"] is False


def test_operation_context_restores_dispatch_after_forward_exception():
    class Explodes(torch.nn.Module):
        def forward(self, value):
            with torch.autocast("cpu", dtype=torch.bfloat16):
                raise ValueError("expected")

    observer = PrecisionObserver("cpu")
    with pytest.raises(ValueError, match="expected"), observing(observer):
        Explodes()(torch.ones(1))
    count = observer.snapshot()["counts"]["operation_calls"]
    torch.ones(1) + 1
    assert observer.snapshot()["counts"]["operation_calls"] == count
    assert observer._mode_depth == 0 and observer._depth == 0


def test_structure_depth_is_bounded_and_snapshot_is_detached():
    observer = PrecisionObserver("cpu", max_depth=2)
    value = torch.ones(1)
    with observing(observer):
        torch.nn.Identity()([[[[value]]]])
    first = observer.snapshot()
    assert first["precision"] == "unknown" and first["errors"]["node_limit"] > 0
    first["dtypes"]["input"]["float32"] = 999
    assert observer.snapshot()["dtypes"]["input"]["float32"] != 999


@pytest.mark.parametrize("dtype,expected", [(torch.bfloat16, "bf16"), (torch.float16, "unknown")])
def test_observed_cast_input_is_not_lost_when_output_returns_float32(dtype, expected):
    class InternalCast(torch.nn.Module):
        def forward(self, value):
            # Simulate an opaque/native region; its output becomes visible to .float().
            with torch._C.DisableTorchFunction():
                hidden = value.to(dtype)
            return hidden.float()

    observer = PrecisionObserver("cpu")
    with observing(observer):
        output = InternalCast()(torch.ones(2, 4))
    assert output.dtype is torch.float32
    assert observer.snapshot()["precision"] == expected
    bucket = "bfloat16" if dtype is torch.bfloat16 else "float16"
    assert observer.snapshot()["dtypes"]["operation_input"][bucket] > 0


@pytest.mark.parametrize("nested", [False, True])
def test_compiled_eager_module_runs_without_python_dispatch_precision_mode(nested):
    compiled = torch.compile(torch.nn.Linear(4, 4), backend="eager")
    model = torch.nn.Sequential(compiled) if nested else compiled
    observer = PrecisionObserver("cpu")
    assert observer.operation_supported(model) is False
    value = torch.ones(2, 4)
    with observing(observer, mode=observer.operation_supported(model)):
        output = model(value)
    assert output.dtype is torch.float32 and output.shape == (2, 4)
    evidence = observer.snapshot()
    assert evidence["precision"] == "unknown" and evidence["complete"] is False
    assert evidence["counts"]["operation_calls"] == 0


def test_plain_module_with_scripted_child_does_not_install_operation_mode():
    child = torch.jit.script(torch.nn.Linear(4, 4))
    parent = torch.nn.Sequential(child)
    observer = PrecisionObserver("cpu")
    assert observer.operation_supported(parent) is False
    with observing(observer, mode=observer.operation_supported(parent)):
        output = parent(torch.ones(2, 4))
    assert output.shape == (2, 4)
    evidence = observer.snapshot()
    assert evidence["precision"] == "unknown"
    assert evidence["counts"]["operation_calls"] == 0


def test_operation_mode_support_scan_is_bounded_without_retained_references():
    parent = torch.nn.ModuleList(torch.nn.Identity() for _ in range(4097))
    observer = PrecisionObserver("cpu")
    assert observer.operation_supported(parent) is False
    reference = weakref.ref(parent)
    del parent
    gc.collect()
    assert reference() is None
