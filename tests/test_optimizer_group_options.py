"""CPU-only actual group options; no model API/GPU workloads or source defaults."""

import gc
import json
import math
import weakref

import pytest
import torch

from headroom import optimizer_observations as summary_module
from headroom.lab import hooks


@pytest.fixture(autouse=True)
def cleanup_capture():
    yield
    session = hooks.active_session()
    if session is not None:
        session.finish("error", RuntimeError("CPU metadata test cleanup"))


def source_bound_result(options=None):
    observation = {
        "protocol": "headroom.optimizer_updates.v1",
        "complete": False,
        "logical_boundary_complete": True,
        "parameter_update_sets_complete": False,
        "optimizer_step_calls": 0,
        "successful_optimizer_step_calls": 0,
        "logical_updates": 0,
        "parameter_catalog": [{"id": "p00001", "numel": 1, "requires_grad_at_observation": True}],
        "parameter_catalog_initialization": {"successful_base_constructor_returns": 1},
    }
    if options is not None:
        observation["group_options"] = options
    return {
        "protocol": "headroom.lab.v1",
        "run_id": "1" * 32,
        "capture_complete": True,
        "pairing_capture": {"source_contract": {"source_sha256": "a" * 64}},
        "parameter_count": 1,
        "parameter_count_complete": True,
        "steps": 0,
        "step_records": [],
        "optimizer_update_observation": observation,
    }


def summarize(result, *, digest="a" * 64):
    return summary_module.runtime_optimizer_observations(
        result, [{"path": "train.py", "sha256": digest}], script="train.py"
    )


class MetadataOptimizer:
    def __init__(self, **options):
        self.param_groups = [{"params": [object()], **options}]


def metadata(**options):
    optimizer = MetadataOptimizer(**options)
    observer = hooks._OptimizerGroupOptionObserver()
    observer.observe(
        optimizer, stage="base_constructor_return", call=0, identify=lambda p: "p00001"
    )
    return observer.snapshot()


def test_constructor_observes_actual_sgd_group_options_without_inventing_updates(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    first = torch.nn.Parameter(torch.tensor([1.0], device="cpu"))
    second = torch.nn.Parameter(torch.tensor([2.0], device="cpu"))
    optimizer = torch.optim.SGD(
        [{"params": [first], "lr": 0.01}, {"params": [second], "lr": 0.03}], momentum=0.9
    )
    result = session.finish(exc=RuntimeError("synthetic forward failure before backward"))
    observation = result["optimizer_update_observation"]
    raw = observation["group_options"]
    assert raw["events"] == {"base_constructor_return": 1, "step_pre": 0}
    assert [row["present"]["lr"] for row in raw["configurations"]] == [
        ["float", 0.01],
        ["float", 0.03],
    ]
    assert all(row["present"]["momentum"] == ["float", 0.9] for row in raw["configurations"])
    assert [row["parameter_ids"] for row in raw["groups"]] == [["p00001"], ["p00002"]]
    assert optimizer.state == {}
    assert (
        result["steps"]
        == observation["logical_updates"]
        == observation["optimizer_step_calls"]
        == 0
    )
    assert observation["complete"] is False
    assert observation["parameter_update_sets_complete"] is False


def test_step_pre_records_changed_actual_lr_without_mutating_native_step(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0], device="cpu"))
    optimizer = torch.optim.SGD([parameter], lr=0.1)
    optimizer.param_groups[0]["lr"] = 0.05
    parameter.square().sum().backward()
    optimizer.step()
    result = session.finish()
    raw = result["optimizer_update_observation"]["group_options"]
    assert [row["present"]["lr"] for row in raw["configurations"]] == [
        ["float", 0.1],
        ["float", 0.05],
    ]
    assert [row["stage"] for row in raw["groups"]] == ["base_constructor_return", "step_pre"]
    assert parameter.item() == pytest.approx(0.9)
    assert result["steps"] == 1


def test_optional_group_metadata_failure_does_not_replace_native_behavior(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()

    def broken(*args, **kwargs):
        raise RuntimeError("optional unavailable")

    monkeypatch.setattr(session._optimizer_group_options, "_observe", broken)
    parameter = torch.nn.Parameter(torch.tensor([1.0], device="cpu"))
    optimizer = torch.optim.SGD([parameter], lr=0.1)
    parameter.square().sum().backward()
    optimizer.step()
    result = session.finish()
    assert parameter.item() == pytest.approx(0.8)
    assert result["steps"] == 1
    assert result["optimizer_update_observation"]["group_options"]["complete"] is False


def test_group_metadata_never_populates_legacy_catalog_after_initial_observer_failure(
    tmp_path, monkeypatch
):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()

    def broken(*args, **kwargs):
        raise RuntimeError("initial unavailable")

    monkeypatch.setattr(session, "_observe_optimizer_initial_parameters", broken)
    parameter = torch.nn.Parameter(torch.tensor([1.0], device="cpu"))
    optimizer = torch.optim.SGD([parameter], lr=0.1)
    assert optimizer.param_groups[0]["params"][0] is parameter
    result = session.finish()
    raw = result["optimizer_update_observation"]
    assert raw["parameter_catalog"] == []
    assert raw["group_options"]["complete"] is False


def test_added_no_grad_group_does_not_expand_legacy_catalog_via_optional_metadata(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    first = torch.nn.Parameter(torch.tensor([1.0], device="cpu"))
    second = torch.nn.Parameter(torch.tensor([2.0], device="cpu"))
    optimizer = torch.optim.SGD([first], lr=0.1)
    optimizer.add_param_group({"params": [second]})
    first.square().sum().backward()
    optimizer.step()
    result = session.finish()
    raw = result["optimizer_update_observation"]
    assert len(raw["parameter_catalog"]) == 1
    assert raw["group_options"]["complete"] is False
    assert second.grad is None


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -(2**63) - 1,
        2**63,
        "private-value",
        {"secret": "private-value"},
        object(),
    ],
)
def test_unsupported_values_are_unknown_without_copying_values(value):
    raw = metadata(lr=value)
    assert raw["complete"] is False
    assert raw["configurations"][0]["present"]["lr"] == ["unsupported", None]
    assert "private-value" not in json.dumps(raw)


def test_no_tensor_scalar_read_or_custom_object_conversion(monkeypatch):
    value = torch.tensor(0.1, device="cpu")

    def forbidden(*args, **kwargs):
        raise AssertionError("tensor value read")

    monkeypatch.setattr(torch.Tensor, "item", forbidden)
    monkeypatch.setattr(torch.Tensor, "__float__", forbidden)
    monkeypatch.setattr(torch.Tensor, "cpu", forbidden)
    monkeypatch.setattr(torch.Tensor, "numpy", forbidden)
    raw = metadata(lr=value)
    assert raw["configurations"][0]["present"]["lr"] == ["unsupported", None]


def test_betas_types_and_absent_keys_are_not_synthesized():
    summary = summarize(source_bound_result(metadata(betas=(0.9, 0.999), foreach=None)))
    values = summary["optimizer_group_hyperparameters"]["configurations"][0]["present"]
    assert values == {
        "betas": ["tuple", [["float", 0.9], ["float", 0.999]]],
        "foreach": ["none", None],
    }
    assert "lr" not in values
    assert hooks._encode_optimizer_group_option("betas", [0.9, 0.99])[0] == "list"
    assert hooks._encode_optimizer_group_option("betas", (True, 0.99))[0] == "unsupported"


def test_unknown_group_names_and_values_are_not_exposed():
    raw = metadata(lr=0.1, private_label="private-value")
    assert raw["complete"] is False
    assert raw["configurations"][0]["unrecognized_option_keys"] == 1
    assert "private_label" not in json.dumps(raw)
    assert "private-value" not in json.dumps(raw)


def test_source_mismatch_still_hides_all_new_metadata():
    summary = summarize(source_bound_result(metadata(lr=0.1)), digest="b" * 64)
    assert summary["status"] == "unverified"
    assert summary["optimizer_group_hyperparameters"] == "not_captured"


def test_legacy_capture_and_near_cap_restore_old_observed_facts(monkeypatch):
    old = summarize(source_bound_result())
    assert old["optimizer_group_hyperparameters"] == "not_captured"
    monkeypatch.setattr(
        summary_module,
        "MAX_OPTIMIZER_OBSERVATION_BYTES",
        len(json.dumps(old, ensure_ascii=True, allow_nan=False).encode()),
    )
    new = summarize(source_bound_result(metadata(lr=0.1)))
    assert new == old


def test_oversized_raw_rejects_only_options_not_parent_facts():
    raw = metadata(lr=0.1)
    raw["untrusted_extra"] = "x" * 65536
    result = summarize(source_bound_result(raw))
    assert result["optimizer_group_hyperparameters"]["status"] == "unverified"
    assert result["status"] == "partial"
    assert result["parameters"]["catalog_entries"] == 1
    assert result["logical_updates"] == 0
    assert len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()) <= 3072


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["configurations"][0]["present"].update(lr=[[], 0.1]),
        lambda r: r["groups"][0].update(stage=[]),
        lambda r: r["groups"][0].update(parameter_ids=["unknown"]),
        lambda r: r["groups"][0].update(first_call=1),
        lambda r: r["events"].update(step_pre=True),
        lambda r: r["configurations"][0]["present"].update(lr=["float", math.nan]),
    ],
)
def test_malformed_metadata_is_unverified_without_losing_parent_facts(mutation):
    raw = metadata(lr=0.1)
    mutation(raw)
    result = summarize(source_bound_result(raw))
    assert result["optimizer_group_hyperparameters"]["status"] == "unverified"
    assert result["parameters"]["catalog_entries"] == 1


def test_observer_retains_no_strong_optimizer_reference():
    optimizer = MetadataOptimizer(lr=0.1)
    ref = weakref.ref(optimizer)
    observer = hooks._OptimizerGroupOptionObserver()
    observer.observe(
        optimizer, stage="base_constructor_return", call=0, identify=lambda p: "p00001"
    )
    del optimizer
    gc.collect()
    assert ref() is None


def test_deadline_baseexception_propagates():
    class Deadline(BaseException):
        pass

    def identify(parameter):
        raise Deadline()

    with pytest.raises(Deadline):
        hooks._OptimizerGroupOptionObserver().observe(
            MetadataOptimizer(), stage="base_constructor_return", call=0, identify=identify
        )
