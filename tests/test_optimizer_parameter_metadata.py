"""CPU installed-hook/native metadata and offline SDK visibility; no GPU/provider."""

import copy
import gc
import json
import weakref

import pytest
import torch
from test_diagnosis_bounded_repair import payload, provider_client
from test_evidence_blockers import source
from test_optimizer_group_options import source_bound_result, summarize

from headroom import optimizer_observations as summaries
from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.lab import hooks
from headroom.llm.router import LLMRouter


@pytest.fixture(autouse=True)
def cleanup():
    yield
    session = hooks.active_session()
    if session:
        session.finish("error", RuntimeError("CPU test cleanup"))


def capture(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu", max_steps=2).start()
    model = torch.nn.Linear(2, 1)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    for _ in range(2):
        optimizer.zero_grad(set_to_none=True)
        model(torch.ones(1, 2)).square().mean().backward()
        try:
            optimizer.step()
        except hooks.StepLimitReached:
            break
    return session.finish(), model, optimizer


def bound(actual):
    # Only the source-binding fixture is synthetic; metadata comes from the real
    # installed CPU hook. No historical source or target execution is fabricated.
    result = source_bound_result()
    result["optimizer_update_observation"] = actual["optimizer_update_observation"]
    result["parameter_count"] = actual["parameter_count"]
    result["steps"] = actual["steps"]
    result["step_records"] = actual["step_records"]
    return result


def test_real_installed_constructor_pre_successful_post_and_last_step_limit(tmp_path):
    actual, _, optimizer = capture(tmp_path)
    raw = actual["optimizer_update_observation"]["parameter_tensor_metadata"]
    assert raw["events"] == {
        "base_constructor_return": 1,
        "step_pre": 2,
        "successful_step_post": 2,
    }
    assert actual["steps"] == 2
    assert raw["uniform"] == {
        "dtype": "float32",
        "device_type": "cpu",
        "device_index": None,
        "layout": "strided",
        "is_leaf": True,
    }
    assert raw["state_tensors"] == "not_captured" and optimizer.state == {}
    result = summarize(bound(actual))
    observed = result["parameter_tensor_metadata"]
    assert observed["status"] == "observed" and observed["events"] == [1, 2, 2]
    assert observed["all_observed"] == raw["uniform"]
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= 3072


def test_constructor_only_never_invents_post_state_or_updates(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.ones(1))
    optimizer = torch.optim.AdamW([parameter])
    result = session.finish("oom", RuntimeError("synthetic no-update failure"))
    raw = result["optimizer_update_observation"]["parameter_tensor_metadata"]
    assert list(raw["events"].values()) == [1, 0, 0]
    assert optimizer.state == {} and result["steps"] == 0
    assert raw["state_tensors"] == "not_captured"


def test_metadata_never_reads_values_state_or_copies_and_does_not_keep_tensors(monkeypatch):
    parameter = torch.nn.Parameter(torch.ones(1))
    reference = weakref.ref(parameter)

    class Owner:
        param_groups = None

        @property
        def state(self):
            pytest.fail("state must not be read")

    optimizer = Owner()
    optimizer.param_groups = [{"params": [parameter]}]
    observer = hooks._OptimizerParameterMetadataObserver()

    def forbidden(*args, **kwargs):
        pytest.fail("metadata-only observer performed data access")

    with monkeypatch.context() as patch:
        for method in (
            "item",
            "cpu",
            "cuda",
            "to",
            "numpy",
            "clone",
            "detach",
            "data_ptr",
            "storage",
        ):
            patch.setattr(torch.Tensor, method, forbidden)
        patch.setattr(torch.cuda, "synchronize", forbidden)
        observer.observe(optimizer, stage="base_constructor_return", identify=lambda p: "p00001")
    assert observer.snapshot()["complete"]
    del optimizer, parameter
    gc.collect()
    assert reference() is None


def test_custom_parameter_subclass_unknown_without_reading_its_metadata():
    class Custom(torch.nn.Parameter):
        @property
        def dtype(self):
            pytest.fail("custom dtype must not execute")

    parameter = Custom(torch.ones(1))
    optimizer = type("Owner", (), {})()
    optimizer.param_groups = [{"params": [parameter]}]
    observer = hooks._OptimizerParameterMetadataObserver()
    observer.observe(optimizer, stage="base_constructor_return", identify=lambda p: "p00001")
    assert observer.snapshot()["complete"] is False
    assert observer.snapshot()["uniform"] is None


def test_changed_and_mixed_metadata_never_flatten_to_uniform_fp32():
    first = torch.nn.Parameter(torch.ones(1))
    second = torch.nn.Parameter(torch.ones(1, dtype=torch.float64))
    optimizer = type("Owner", (), {})()
    optimizer.param_groups = [{"params": [first, second]}]
    observer = hooks._OptimizerParameterMetadataObserver()
    identify = lambda p: "p00001" if p is first else "p00002"
    observer.observe(optimizer, stage="base_constructor_return", identify=identify)
    assert observer.snapshot()["mixed"] and observer.snapshot()["uniform"] is None
    first.data = first.data.to(torch.float64)
    observer.observe(optimizer, stage="step_pre", identify=identify)
    assert observer.snapshot()["changed_parameters"] == 1
    assert observer.snapshot()["complete"] is False and observer.snapshot()["uniform"] is None


@pytest.mark.parametrize("kind", ["meta", "sparse", "unknown_id"])
def test_unsupported_values_and_unknown_weak_identity_stay_unknown(kind):
    if kind == "meta":
        parameter = torch.nn.Parameter(torch.ones(1, device="meta"))
    elif kind == "sparse":
        parameter = torch.nn.Parameter(torch.sparse_coo_tensor([[0]], [1.0], (2,)))
    else:
        parameter = torch.nn.Parameter(torch.ones(1))
    optimizer = type("Owner", (), {})()
    optimizer.param_groups = [{"params": [parameter]}]
    observer = hooks._OptimizerParameterMetadataObserver()

    def identify(value):
        if kind == "unknown_id":
            raise ValueError("not previously catalogued")
        return "p00001"

    observer.observe(optimizer, stage="base_constructor_return", identify=identify)
    assert observer.snapshot()["complete"] is False


def test_failed_native_step_has_no_successful_post_metadata(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    p = torch.nn.Parameter(torch.ones(1))
    optimizer = torch.optim.SGD([p])

    def fail(*args):
        raise ValueError("native pre failure")

    handle = optimizer.register_step_pre_hook(fail)
    with pytest.raises(ValueError, match="native pre failure"):
        optimizer.step()
    handle.remove()
    result = session.finish()
    raw = result["optimizer_update_observation"]["parameter_tensor_metadata"]
    assert raw["events"]["step_pre"] == 1
    assert raw["events"]["successful_step_post"] == 0
    assert result["steps"] == 0


def test_optional_raw_envelope_overflow_preserves_group_evidence(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    p = torch.nn.Parameter(torch.ones(1))
    optimizer = torch.optim.SGD([p])
    groups = {"padding": "x" * 65536}
    monkeypatch.setattr(session._optimizer_group_options, "snapshot", lambda: copy.deepcopy(groups))
    captured = session._optimizer_update_evidence()
    assert captured["group_options"] == groups
    assert "parameter_tensor_metadata" not in captured
    assert optimizer.param_groups[0]["params"][0] is p


def test_optional_summary_bound_preserves_legacy_fields(tmp_path, monkeypatch):
    actual, _, _ = capture(tmp_path)
    result = bound(actual)
    before = copy.deepcopy(result)
    legacy = copy.deepcopy(result)
    del legacy["optimizer_update_observation"]["parameter_tensor_metadata"]
    baseline = summarize(legacy)
    baseline.pop("parameter_tensor_metadata", None)
    cap = len(json.dumps(baseline, ensure_ascii=True, allow_nan=False).encode())
    monkeypatch.setattr(summaries, "MAX_OPTIMIZER_OBSERVATION_BYTES", cap)
    assert summarize(result) == baseline
    assert result == before


@pytest.mark.parametrize("mutation", ["old", "source", "events", "ids", "raw_cap", "wrong_type"])
def test_old_stale_and_malformed_metadata_never_upgrades_legacy_observations(tmp_path, mutation):
    actual, _, _ = capture(tmp_path)
    result = bound(actual)
    raw = result["optimizer_update_observation"]["parameter_tensor_metadata"]
    if mutation == "old":
        del result["optimizer_update_observation"]["parameter_tensor_metadata"]
    elif mutation == "source":
        result["pairing_capture"]["source_contract"]["source_sha256"] = "b" * 64
    elif mutation == "events":
        raw["events"]["successful_step_post"] = 20
    elif mutation == "ids":
        raw["parameter_ids"] = ["p99999"]
    elif mutation == "raw_cap":
        raw["padding"] = "x" * 65536
    else:
        raw["uniform"]["dtype"] = []
    value = summarize(result)
    new = value.get("parameter_tensor_metadata", {})
    assert new.get("status") != "observed"
    assert result["steps"] == 2


def test_actual_mock_sdk_request_contains_fresh_cpu_metadata_without_new_call(tmp_path):
    actual, _, _ = capture(tmp_path)
    observed = summarize(bound(actual))
    evidence, markdown = source()
    evidence["execution_context"]["runtime_optimizer_observations"] = observed
    requests = []
    with provider_client([payload()], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={},
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert result.ready_for_patch and len(requests) == 1
    request = json.loads(requests[0]["messages"][2]["content"])
    metadata = request["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    assert metadata["all_observed"]["dtype"] == "float32"
    assert metadata["events"] == [1, 2, 2]
    assert requests[0]["max_tokens"] == 2000 and requests[0].get("tools") is None


def test_optional_snapshot_failure_preserves_legacy_capture(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    p = torch.nn.Parameter(torch.ones(1))
    optimizer = torch.optim.SGD([p])

    def broken():
        raise RuntimeError("optional snapshot unavailable")

    monkeypatch.setattr(session._optimizer_parameter_metadata, "snapshot", broken)
    result = session.finish()
    assert result["steps"] == 0
    assert len(result["optimizer_update_observation"]["parameter_catalog"]) == 1
    assert "parameter_tensor_metadata" not in result["optimizer_update_observation"]
    assert optimizer.state == {}


def test_native_metadata_descriptors_and_types_are_prebound(monkeypatch):
    parameter = torch.nn.Parameter(torch.ones(1))
    optimizer = type("Owner", (), {})()
    optimizer.param_groups = [{"params": [parameter]}]
    observer = hooks._OptimizerParameterMetadataObserver()

    def forbidden(value):
        pytest.fail("dynamic Tensor dtype property was consulted")

    with monkeypatch.context() as patch:
        patch.setattr(torch.Tensor, "dtype", property(forbidden))
        patch.setattr(torch, "device", lambda *a: None)
        patch.setattr(torch, "strided", object())
        observer.observe(optimizer, stage="base_constructor_return", identify=lambda p: "p00001")
    assert observer.snapshot()["uniform"]["dtype"] == "float32"
    assert observer.snapshot()["complete"]


def test_exact_parameter_class_check_never_calls_custom_metaclass_equality():
    compared = []

    class EqualityMeta(type(torch.nn.Parameter)):
        def __eq__(cls, other):
            compared.append(True)
            raise AssertionError("user-defined class equality must not run")

        __hash__ = type.__hash__

    class Custom(torch.nn.Parameter, metaclass=EqualityMeta):
        pass

    parameter = Custom(torch.ones(1))
    optimizer = type("Owner", (), {})()
    optimizer.param_groups = [{"params": [parameter]}]
    compared.clear()
    observer = hooks._OptimizerParameterMetadataObserver()
    observer.observe(optimizer, stage="base_constructor_return", identify=lambda p: "p00001")
    assert compared == []
    assert observer.snapshot()["complete"] is False
    assert observer.snapshot()["uniform"] is None
