import copy
import json

import pytest
import torch

from headroom.lab import hooks


@pytest.fixture(autouse=True)
def cleanup():
    yield
    session = hooks.active_session()
    if session is not None:
        session.finish("error", RuntimeError("test cleanup"))


class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.first = torch.nn.Parameter(torch.tensor([0.2, 0.3]))
        self.second = torch.nn.Parameter(torch.tensor([0.4, 0.5]))

    def forward(self, value):
        return (self.first * value).sum() + (self.second * value).sum()


def loss(model):
    return (model(torch.tensor([0.7, 0.9])) - 0.1).square()


def install_steps(
    model, *, include=None, repeats=1, explode=False, optimizer_type=torch.optim.Adam
):
    opts = {p: optimizer_type([p], lr=0.01, foreach=False) for p in model.parameters()}
    returned = []
    handles = []
    for index, (parameter, optimizer) in enumerate(opts.items()):
        if include is not None and index not in include:
            continue

        def update(p, optimizer=optimizer):
            for _ in range(repeats):
                optimizer.step()
            optimizer.zero_grad()
            returned.append(p)
            if explode:
                raise RuntimeError("callback failed after actual update")

        handles.append(parameter.register_post_accumulate_grad_hook(update))
    return opts, handles, returned


def test_twenty_complete_backward_updates_match_twenty_full_model_updates(tmp_path):
    model = Model()
    reference = copy.deepcopy(model)
    baseline = torch.optim.Adam(reference.parameters(), lr=0.01, foreach=False)
    reference_losses = []
    for _ in range(20):
        baseline.zero_grad()
        value = loss(reference)
        reference_losses.append(value.item())
        value.backward()
        baseline.step()
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()
    optimizers, handles, returned = install_steps(model)
    with pytest.raises(hooks.StepLimitReached) as stop:
        for _ in range(100):
            loss(model).backward()
    result = session.finish(exc=stop.value)
    for handle in handles:
        handle.remove()
    assert result["capture_complete"] and result["status"] == "completed"
    assert result["steps"] == len(result["loss_series"]) == 20
    assert len(returned) == 40
    assert result["loss_series"] == reference_losses
    for parameter, expected in zip(model.parameters(), reference.parameters()):
        torch.testing.assert_close(parameter, expected, rtol=0, atol=0)
        assert optimizers[parameter].state[parameter]["step"].item() == 20
        assert parameter.grad is None
    observation = result["optimizer_update_observation"]
    assert (
        observation["optimizer_step_calls"] == observation["successful_optimizer_step_calls"] == 40
    )
    assert observation["logical_updates"] == 20 and observation["complete"]
    assert all(r["optimizer_step_calls"] == 2 for r in result["step_records"])
    assert all(len(r["updated_parameter_ids"]) == 2 for r in result["step_records"])
    assert all(r["step_ms"] > 0 for r in result["step_records"])
    assert all(r["update_basis"] == "complete_tensor_backward" for r in result["step_records"])
    assert all(r["parameter_update_coverage_complete"] for r in result["step_records"])


@pytest.mark.parametrize(
    "kind",
    [
        "partial",
        "duplicate",
        "exception",
        "unobservable",
        "optimizer_exception",
        "restricted",
        "unknown_task",
    ],
)
def test_incomplete_or_unobservable_update_never_counts_as_complete(tmp_path, kind, monkeypatch):
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()

    class Unobservable(torch.optim.SGD):
        def step(self, closure=None):
            for group in self.param_groups:
                for parameter in group["params"]:
                    parameter.data.add_(parameter.grad, alpha=-group["lr"])

    class Broken(torch.optim.SGD):
        def step(self, closure=None):
            super().step(closure)
            raise RuntimeError("optimizer failed after mutation")

    _, handles, _ = install_steps(
        model,
        include={0} if kind == "partial" else None,
        repeats=2 if kind == "duplicate" else 1,
        explode=kind == "exception",
        optimizer_type=Unobservable
        if kind == "unobservable"
        else Broken
        if kind == "optimizer_exception"
        else torch.optim.Adam,
    )
    if kind == "unknown_task":
        monkeypatch.setattr(session, "_graph_task", lambda: None)
    exception = None
    try:
        loss(model).backward(**({"inputs": [model.first]} if kind == "restricted" else {}))
    except RuntimeError as error:
        exception = error
    result = session.finish(exc=exception)
    for handle in handles:
        handle.remove()
    assert result["steps"] == 0
    assert not result["capture_complete"] and result["status"] == "error"
    assert not result["optimizer_update_observation"]["complete"]
    assert result["optimizer_update_observation"]["optimizer_step_calls"] > 0


def test_outer_optimizer_with_two_backwards_preserves_existing_counting(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()
    model = Model()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    with pytest.raises(hooks.StepLimitReached) as stopped:
        for _ in range(30):
            optimizer.zero_grad()
            loss(model).backward()
            loss(model).backward()
            optimizer.step()
    result = session.finish(exc=stopped.value)
    assert result["steps"] == 20 and len(result["loss_series"]) == 40
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 20
    assert result["capture_complete"]
    assert all(r["update_basis"] == "optimizer_post_hook" for r in result["step_records"])


def test_direct_autograd_backward_without_tensor_boundary_is_unknown(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()
    _, handles, _ = install_steps(model)
    torch.autograd.backward(loss(model))
    result = session.finish()
    for handle in handles:
        handle.remove()
    assert result["steps"] == 0 and not result["capture_complete"]
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 2


def test_snapshot_compaction_preserves_native_data_and_metadata_readability(tmp_path):
    payload = {"segments": [{"blocks": [{"size": 12, "state": "active"}]}], "device_traces": []}
    hooks._atomic_json(tmp_path / "snapshot.json", payload)
    hooks._atomic_json(tmp_path / "result.json", payload)
    compact = (tmp_path / "snapshot.json").read_text()
    pretty = (tmp_path / "result.json").read_text()
    assert json.loads(compact) == json.loads(pretty) == payload
    assert len(compact) < len(pretty) and compact.count("\n") == 1
    assert pretty.count("\n") > 1


def test_twentieth_backward_failure_keeps_only_nineteen_complete_updates(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()
    model = Model()
    optimizers = {p: torch.optim.Adam([p], lr=0.01, foreach=False) for p in model.parameters()}
    callbacks = []
    handles = []

    def update(parameter):
        optimizers[parameter].step()
        optimizers[parameter].zero_grad()
        callbacks.append(parameter)
        if len(callbacks) == 39:
            raise RuntimeError("failure after the first parameter of the twentieth update")

    for parameter in model.parameters():
        handles.append(parameter.register_post_accumulate_grad_hook(update))
    with pytest.raises(RuntimeError) as failure:
        for _ in range(20):
            loss(model).backward()
    result = session.finish(exc=failure.value)
    for handle in handles:
        handle.remove()
    assert result["steps"] == 19 and len(result["loss_series"]) == 20
    assert result["status"] == "error" and not result["capture_complete"]
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 39
    assert sorted(
        optimizer.state[parameter]["step"].item() for parameter, optimizer in optimizers.items()
    ) == [19, 20]


def test_boundary_and_timing_wait_for_entire_post_accumulate_callback(tmp_path):
    import time

    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()
    optimizers = {p: torch.optim.SGD([p], lr=0.01) for p in model.parameters()}
    returned = []
    handles = []

    def update(parameter):
        optimizers[parameter].step()
        optimizers[parameter].zero_grad()
        time.sleep(0.005)
        returned.append(parameter)

    for parameter in model.parameters():
        handles.append(parameter.register_post_accumulate_grad_hook(update))
    with pytest.raises(hooks.StepLimitReached) as stop:
        loss(model).backward()
    result = session.finish(exc=stop.value)
    for handle in handles:
        handle.remove()
    assert len(returned) == 2 and result["steps"] == 1
    assert result["step_records"][0]["step_ms"] >= 10
    assert result["capture_complete"]


def test_unused_module_parameter_is_not_invented_as_a_backward_participant(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()
    model.unused = torch.nn.Parameter(torch.tensor([3.0]))
    _, handles, returned = install_steps(model)
    with pytest.raises(hooks.StepLimitReached) as stop:
        loss(model).backward()
    result = session.finish(exc=stop.value)
    for handle in handles:
        handle.remove()
    assert result["capture_complete"] and result["steps"] == 1
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 2
    assert len(returned) == 2 and model.unused.grad is None


def test_multiple_outer_optimizers_keep_original_individual_step_count(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()
    model = Model()
    optimizers = [torch.optim.SGD([p], lr=0.01) for p in model.parameters()]
    with pytest.raises(hooks.StepLimitReached) as stop:
        for _ in range(20):
            for optimizer in optimizers:
                optimizer.zero_grad()
            loss(model).backward()
            for optimizer in optimizers:
                optimizer.step()
    result = session.finish(exc=stop.value)
    assert result["capture_complete"] and result["steps"] == 20
    assert len(result["loss_series"]) == 10
    assert all(record["update_basis"] == "optimizer_post_hook" for record in result["step_records"])


def test_direct_autograd_grad_optimizer_callbacks_have_no_proven_boundary(tmp_path):
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()
    optimizers = {p: torch.optim.SGD([p], lr=0.01) for p in model.parameters()}
    handles = []
    for parameter, optimizer in optimizers.items():

        def update(gradient, parameter=parameter, optimizer=optimizer):
            parameter.grad = gradient
            optimizer.step()
            optimizer.zero_grad()
            return gradient

        handles.append(parameter.register_hook(update))
    torch.autograd.grad(loss(model), tuple(model.parameters()))
    result = session.finish()
    for handle in handles:
        handle.remove()
    assert result["steps"] == 0 and not result["capture_complete"]
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 2


@pytest.mark.parametrize("task", [None, -2])
def test_no_graph_task_proof_cannot_fall_back_to_outer_step_count(tmp_path, monkeypatch, task):
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    model = Model()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss(model).backward()
    monkeypatch.setattr(session, "_graph_task", lambda: task)
    optimizer.step()
    result = session.finish()
    assert result["steps"] == 0 and not result["capture_complete"]
    assert result["optimizer_update_observation"]["optimizer_step_calls"] == 1


@pytest.mark.parametrize("existing_gradient", [False, True])
def test_outer_closure_keeps_count_but_parameter_coverage_is_unknown(tmp_path, existing_gradient):
    model = Model()
    initial = [parameter.detach().clone() for parameter in model.parameters()]
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    if existing_gradient:
        model.first.grad = torch.ones_like(model.first)
    session = hooks.CaptureSession(tmp_path, max_steps=20, device="cpu").start()

    def closure():
        optimizer.zero_grad()
        value = loss(model)
        value.backward()
        return value

    with pytest.raises(hooks.StepLimitReached) as stopped:
        for _ in range(30):
            optimizer.step(closure)
    result = session.finish(exc=stopped.value)
    assert result["steps"] == 20
    assert len(result["loss_series"]) == 20
    assert result["capture_complete"]
    assert all(
        not torch.equal(parameter, before) for parameter, before in zip(model.parameters(), initial)
    )
    observation = result["optimizer_update_observation"]
    assert observation["logical_boundary_complete"]
    assert not observation["parameter_update_sets_complete"] and not observation["complete"]
    assert all(
        not record["parameter_update_coverage_complete"] for record in result["step_records"]
    )
    assert all(record["update_basis"] == "optimizer_post_hook" for record in result["step_records"])


def test_outer_step_without_observable_gradients_has_unknown_parameter_coverage(tmp_path):
    model = Model()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    session = hooks.CaptureSession(tmp_path, max_steps=1, device="cpu").start()
    with pytest.raises(hooks.StepLimitReached) as stopped:
        optimizer.step()
    result = session.finish(exc=stopped.value)
    assert result["steps"] == 1
    observation = result["optimizer_update_observation"]
    assert observation["logical_boundary_complete"]
    assert not observation["parameter_update_sets_complete"] and not observation["complete"]
    assert result["step_records"][0]["updated_parameter_ids"] == []
    assert not result["step_records"][0]["parameter_update_coverage_complete"]
