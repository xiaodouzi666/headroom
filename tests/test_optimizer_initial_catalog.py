"""CPU-only optimizer-construction observations; no model API or GPU workloads."""

import gc
import weakref

import pytest
import torch

from headroom.lab import hooks


@pytest.fixture(autouse=True)
def cleanup_capture():
    yield
    session = hooks.active_session()
    if session is not None:
        session.finish("error", RuntimeError("CPU test cleanup"))


def observation(result):
    return result["optimizer_update_observation"]


def test_successful_base_constructor_records_all_groups_without_any_gradient_or_step(tmp_path):
    original = torch.optim.Optimizer.__init__
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    first = torch.nn.Parameter(torch.tensor([1.0, 2.0]))
    frozen = torch.nn.Parameter(torch.tensor([3.0, 4.0, 5.0]), requires_grad=False)
    second = torch.nn.Parameter(torch.tensor([6.0]))
    versions = [parameter._version for parameter in (first, frozen, second)]
    optimizer = torch.optim.SGD(
        [
            {"params": [first, frozen], "lr": 0.01},
            {"params": [second], "lr": 0.03},
        ],
        momentum=0.9,
    )
    result = session.finish(exc=RuntimeError("synthetic forward failure before first backward"))
    captured = observation(result)
    assert torch.optim.Optimizer.__init__ is original
    assert optimizer.state == {}
    assert [group["lr"] for group in optimizer.param_groups] == [0.01, 0.03]
    assert [parameter._version for parameter in (first, frozen, second)] == versions
    assert all(parameter.grad is None for parameter in (first, frozen, second))
    assert [
        (row["numel"], row["requires_grad_at_observation"]) for row in captured["parameter_catalog"]
    ] == [(2, True), (3, False), (1, True)]
    assert captured["parameter_catalog_initialization"]["successful_base_constructor_returns"] == 1
    assert captured["parameter_catalog_initialization"]["complete"] is True
    assert result["steps"] == captured["logical_updates"] == 0
    assert result["step_records"] == result["loss_series"] == []
    assert captured["optimizer_step_calls"] == captured["successful_optimizer_step_calls"] == 0
    assert captured["parameter_update_sets_complete"] is False
    assert captured["complete"] is False


def test_metadata_failure_does_not_replace_native_optimizer_behavior(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    with monkeypatch.context() as patch:
        patch.setattr(
            session,
            "_observe_optimizer_initial_parameters",
            lambda optimizer: (_ for _ in ()).throw(RuntimeError("metadata unavailable")),
        )
        optimizer = torch.optim.SGD([parameter], lr=0.1)
    assert optimizer.param_groups[0]["params"] == [parameter]
    assert session._optimizer_initial_catalog_complete is False
    parameter.square().sum().backward()
    optimizer.step()
    result = session.finish()
    assert parameter.item() == pytest.approx(0.8)
    assert result["steps"] == 1
    assert observation(result)["parameter_catalog_initialization"]["complete"] is False


def test_failed_native_base_constructor_does_not_create_initial_catalog_or_swallow_error(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    with pytest.raises(ValueError, match="empty parameter list"):
        torch.optim.SGD([], lr=0.1)
    result = session.finish()
    assert observation(result)["parameter_catalog"] == []
    assert (
        observation(result)["parameter_catalog_initialization"][
            "successful_base_constructor_returns"
        ]
        == 0
    )
    assert result["steps"] == 0


def test_native_constructor_missing_dependency_error_is_preserved(tmp_path, monkeypatch):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))

    def missing(*args, **kwargs):
        raise ModuleNotFoundError("native optional dependency unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(session, "_original_optimizer_init", missing)
        with pytest.raises(ModuleNotFoundError, match="native optional dependency unavailable"):
            torch.optim.SGD([parameter], lr=0.1)
    result = session.finish()
    assert observation(result)["parameter_catalog"] == []
    assert (
        observation(result)["parameter_catalog_initialization"][
            "successful_base_constructor_returns"
        ]
        == 0
    )


def test_base_return_is_not_claimed_as_custom_subclass_completion(tmp_path):
    class LaterFailure(torch.optim.SGD):
        def __init__(self, params):
            super().__init__(params, lr=0.1)
            raise ValueError("custom subclass did not finish")

    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    with pytest.raises(ValueError, match="custom subclass did not finish"):
        LaterFailure([parameter])
    result = session.finish()
    captured = observation(result)
    assert len(captured["parameter_catalog"]) == 1
    assert "not custom-subclass completion" in captured["parameter_catalog_initialization"]["scope"]
    assert captured["logical_updates"] == captured["optimizer_step_calls"] == 0


def test_constructor_observation_does_not_retain_optimizer_or_parameter(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    optimizer = torch.optim.AdamW([parameter], lr=0.1)
    parameter_ref, optimizer_ref = weakref.ref(parameter), weakref.ref(optimizer)
    del parameter, optimizer
    gc.collect()
    assert parameter_ref() is None and optimizer_ref() is None
    result = session.finish()
    assert observation(result)["parameter_catalog"][0]["numel"] == 1
    assert result["steps"] == 0


def test_constructor_metadata_never_copies_reads_values_or_synchronizes(tmp_path, monkeypatch):
    parameter = torch.nn.Parameter(torch.tensor([1.0, 2.0]))
    # Warm the native lazy optimizer imports before instrumenting only the new call.
    torch.optim.SGD([parameter], lr=0.1)
    session = hooks.CaptureSession(tmp_path, device="cpu").start()

    def forbidden(*args, **kwargs):
        raise AssertionError("constructor observation must use CPU metadata only")

    with monkeypatch.context() as patch:
        for method in ("cpu", "cuda", "to", "clone", "detach", "item", "numpy"):
            patch.setattr(torch.Tensor, method, forbidden)
        patch.setattr(torch.cuda, "synchronize", forbidden)
        optimizer = torch.optim.SGD([parameter], lr=0.1)
        assert optimizer.param_groups[0]["params"][0] is parameter
        assert session._optimizer_initial_catalog_complete
        assert session._update_catalog[0]["numel"] == 2
    result = session.finish()
    assert observation(result)["logical_updates"] == 0


def test_pid_and_finished_guards_leave_later_constructors_unobserved(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    pid = session.pid
    session.pid = pid + 1
    try:
        torch.optim.SGD([parameter], lr=0.1)
    finally:
        session.pid = pid
    held_wrapper = torch.optim.Optimizer.__init__
    result = session.finish()
    dummy = object.__new__(torch.optim.Optimizer)
    held_wrapper(dummy, [parameter], {})
    assert observation(result)["parameter_catalog"] == []
    assert session._optimizer_base_constructions_observed == 0


def test_install_uninstall_is_idempotent_and_does_not_overwrite_foreign_replacement(tmp_path):
    original = torch.optim.Optimizer.__init__
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    owned = torch.optim.Optimizer.__init__
    assert session.start() is session
    assert torch.optim.Optimizer.__init__ is owned

    def foreign(optimizer, *args, **kwargs):
        return original(optimizer, *args, **kwargs)

    torch.optim.Optimizer.__init__ = foreign
    try:
        first = session.finish()
        assert torch.optim.Optimizer.__init__ is foreign
        assert session.finish() is first
    finally:
        torch.optim.Optimizer.__init__ = original


def test_unsupported_standalone_tensors_only_lower_initial_catalog_capability(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    value = torch.tensor([1.0], requires_grad=True)
    optimizer = torch.optim.SGD([value], lr=0.1)
    assert optimizer.param_groups[0]["params"] == [value]
    result = session.finish()
    assert observation(result)["parameter_catalog_initialization"]["complete"] is False
    assert observation(result)["parameter_catalog"] == []
    assert result["steps"] == 0


def test_constructor_catalog_limit_is_bounded_without_rejecting_native_optimizer(tmp_path):
    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameters = [torch.nn.Parameter(torch.ones(1)) for _ in range(8193)]
    optimizer = torch.optim.SGD(parameters, lr=0.1)
    result = session.finish()
    assert len(optimizer.param_groups[0]["params"]) == 8193
    assert len(observation(result)["parameter_catalog"]) == 8192
    assert observation(result)["parameter_catalog_initialization"]["complete"] is False
    assert result["steps"] == 0


def test_34_parameter_child_optimizers_reuse_ids_and_keep_twenty_logical_updates(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()
    parameters = [torch.nn.Parameter(torch.tensor([0.2 + i / 100])) for i in range(34)]
    optimizers = [
        torch.optim.AdamW([parameter], lr=0.001, foreach=False) for parameter in parameters
    ]
    handles = []
    for parameter, optimizer in zip(parameters, optimizers, strict=True):

        def update(value, optimizer=optimizer):
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

        handles.append(parameter.register_post_accumulate_grad_hook(update))
    try:
        with pytest.raises(hooks.StepLimitReached) as stopped:
            for _ in range(21):
                sum(parameter.square().sum() for parameter in parameters).backward()
        result = session.finish(exc=stopped.value)
    finally:
        for handle in handles:
            handle.remove()
    captured = observation(result)
    assert (
        len(captured["parameter_catalog"])
        == len({row["id"] for row in captured["parameter_catalog"]})
        == 34
    )
    assert captured["parameter_catalog_initialization"]["successful_base_constructor_returns"] == 34
    assert result["steps"] == len(result["loss_series"]) == captured["logical_updates"] == 20
    assert captured["optimizer_step_calls"] == captured["successful_optimizer_step_calls"] == 680
    assert all(len(record["updated_parameter_ids"]) == 34 for record in result["step_records"])
    assert result["capture_complete"] and captured["complete"]


def test_native_and_owned_optimizer_constructors_share_parameter_identity_without_updates(tmp_path):
    from headroom.optim.in_backward_adamw import AdamWInBackward

    session = hooks.CaptureSession(tmp_path, device="cpu").start()
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    first = torch.optim.AdamW([parameter], lr=0.01, foreach=False)
    second = torch.optim.SGD([parameter], lr=0.02)
    owned = AdamWInBackward([parameter], lr=0.01)
    try:
        captured = session._optimizer_update_evidence()
        assert len(captured["parameter_catalog"]) == 1
        assert (
            captured["parameter_catalog_initialization"]["successful_base_constructor_returns"] == 3
        )
        assert (
            first.param_groups[0]["params"][0] is second.param_groups[0]["params"][0] is parameter
        )
        assert owned.param_groups[0]["params"][0] is parameter
        assert captured["optimizer_step_calls"] == captured["logical_updates"] == 0
    finally:
        owned.close()
        session.finish()
