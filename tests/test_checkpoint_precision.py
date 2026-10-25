"""Real CPU checkpoint precision scopes; production files are not changed."""

import threading
from contextlib import contextmanager

import pytest
import torch
from torch.utils.checkpoint import checkpoint as preimported_checkpoint

from headroom.lab.hooks import CaptureSession
from headroom.lab.precision import PrecisionObserver


class FunctionalCheckpoint(torch.nn.Module):
    def __init__(self, *, bf16=False, failing=False, events=None, context_fn=None):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.randn(4, 4))
        self.bf16, self.failing = bf16, failing
        self.events, self.context_fn = events if events is not None else [], context_fn

    def body(self, value):
        from torch.overrides import _get_current_function_mode_stack

        task = torch._C._current_graph_task_id()
        self.events.append(
            {
                "task": task,
                "thread": threading.get_ident(),
                "covered": any(
                    type(mode).__name__ == "_PrecisionMode"
                    for mode in _get_current_function_mode_stack()
                ),
            }
        )
        if self.failing and task >= 0:
            raise RuntimeError("real-recompute-failure")
        with torch.autocast("cpu", dtype=torch.bfloat16, enabled=self.bf16):
            return torch.nn.functional.linear(value, self.weight).float().sin()

    def forward(self, value):
        kwargs = {"use_reentrant": False}
        if self.context_fn is not None:
            kwargs["context_fn"] = self.context_fn
        return preimported_checkpoint(self.body, value, **kwargs)


def capture(tmp_path, model, *, fail=False):
    session = CaptureSession(tmp_path, device="cpu", max_steps=20).start()
    try:
        value = torch.randn(2, 4)
        loss = model(value).square().mean()
        if fail:
            with pytest.raises(RuntimeError, match="real-recompute-failure"):
                loss.backward()
        else:
            loss.backward()
    finally:
        result = session.finish()
    return result["precision_observation"]


@pytest.mark.parametrize("bf16", [False, True])
def test_functional_only_checkpoint_body_has_actual_operation_coverage(tmp_path, bf16):
    model = FunctionalCheckpoint(bf16=bf16)
    evidence = capture(tmp_path, model)
    assert evidence["complete"], evidence
    assert evidence["precision"] == ("bf16" if bf16 else "fp32")
    assert evidence["recognized_graph_metadata_outputs"] > 0
    assert (
        evidence["checkpoint_recompute"]["entered"]
        == evidence["checkpoint_recompute"]["exited"]
        == 1
    )
    assert evidence["checkpoint_recompute"]["early_stops"] == 1
    assert any(event["task"] >= 0 for event in model.events)
    assert all(event["covered"] for event in model.events)
    assert (
        evidence["operation_mode_lifecycle"]["entered"]
        == evidence["operation_mode_lifecycle"]["exited"]
    )


def test_recompute_exception_exits_tls_and_is_unknown(tmp_path):
    from torch.overrides import _get_current_function_mode_stack

    evidence = capture(tmp_path, FunctionalCheckpoint(failing=True), fail=True)
    assert not evidence["complete"] and evidence["precision"] == "unknown"
    assert evidence["errors"]["checkpoint_recompute_failed"] == 1
    assert (
        evidence["checkpoint_recompute"]["entered"]
        == evidence["checkpoint_recompute"]["exited"]
        == 1
    )
    assert (
        evidence["operation_mode_lifecycle"]["entered"]
        == evidence["operation_mode_lifecycle"]["exited"]
    )
    assert not any(
        type(mode).__name__ == "_PrecisionMode" for mode in _get_current_function_mode_stack()
    )


def test_user_contexts_are_preserved_and_observer_is_inside_recompute_context(tmp_path):
    events, active = [], []

    @contextmanager
    def context(name):
        events.append(name + ":enter")
        active.append(name)
        try:
            yield
        finally:
            active.pop()
            events.append(name + ":exit")

    model = FunctionalCheckpoint(context_fn=lambda: (context("forward"), context("recompute")))
    original_body = model.body

    def body(value):
        assert active == (["recompute"] if torch._C._current_graph_task_id() >= 0 else ["forward"])
        return original_body(value)

    model.body = body
    evidence = capture(tmp_path, model)
    assert not evidence["complete"]
    assert evidence["errors"]["checkpoint_context_unverified"] > 0
    assert events == ["forward:enter", "forward:exit", "recompute:enter", "recompute:exit"]
    assert model.events[0]["covered"]
    assert not model.events[-1]["covered"]  # custom contexts execute without our fn wrapper


def test_unknown_output_structure_remains_unknown(tmp_path):
    class Bad(torch.nn.Module):
        def forward(self, value):
            return value, object()

    session = CaptureSession(tmp_path, device="cpu").start()
    Bad()(torch.ones(2, 4))
    evidence = session.finish()["precision_observation"]
    assert evidence["precision"] == "unknown"
    assert evidence["errors"]["structure_unsupported"] > 0


def test_unregistered_worker_forward_remains_unknown(tmp_path):
    session = CaptureSession(tmp_path, device="cpu").start()
    model = torch.nn.Linear(4, 4)
    model(torch.ones(2, 4))
    worker = threading.Thread(target=lambda: model(torch.ones(2, 4)))
    worker.start()
    worker.join()
    evidence = session.finish()["precision_observation"]
    assert not evidence["complete"] and evidence["errors"]["cross_thread"] > 0
    assert evidence["worker_observers"]["registered"] == 0


def test_reentrant_functional_only_checkpoint_remains_unknown(tmp_path):
    class Reentrant(torch.nn.Module):
        def forward(self, value):
            return preimported_checkpoint(lambda item: item.sin(), value, use_reentrant=True)

    session = CaptureSession(tmp_path, device="cpu").start()
    Reentrant()(torch.ones(2, 4, requires_grad=True)).sum().backward()
    evidence = session.finish()["precision_observation"]
    assert not evidence["complete"]
    assert evidence["errors"]["checkpoint_reentrant_unsupported"] > 0


def test_recompute_does_not_certify_an_unobserved_original_function_forward(tmp_path):
    session = CaptureSession(tmp_path, device="cpu").start()
    weight = torch.randn(4, 4, requires_grad=True)
    value = torch.ones(2, 4, requires_grad=True)
    preimported_checkpoint(
        lambda x: (x @ weight).sin(), value, use_reentrant=False
    ).sum().backward()
    evidence = session.finish()["precision_observation"]
    assert not evidence["complete"]
    assert evidence["errors"]["operation_mode_missing"] > 0


def test_explicit_worker_function_mode_is_thread_local_and_exits():
    from torch.overrides import _get_current_function_mode_stack

    parent = PrecisionObserver("cpu")
    seen = []

    def worker():
        child = parent.explicit_worker_observer()

        def function(value):
            seen.append(
                any(
                    type(mode).__name__ == "_PrecisionMode"
                    for mode in _get_current_function_mode_stack()
                )
            )
            with torch.autocast("cpu", dtype=torch.bfloat16):
                return (value @ value).float()

        child.observe_recompute(function, (torch.ones(4, 4),), {})
        seen.append(not _get_current_function_mode_stack())

    task = threading.Thread(target=worker)
    task.start()
    task.join()
    evidence = parent.snapshot()
    assert seen == [True, True]
    assert evidence["complete"] and evidence["precision"] == "bf16"
    assert evidence["worker_observers"]["registered"] == 1


def test_adapter_restores_official_functions_after_recompute_exception(tmp_path):
    import torch.utils.checkpoint as module

    before = module._checkpoint_without_reentrant_generator
    before_reentrant = module.CheckpointFunction.forward
    capture(tmp_path, FunctionalCheckpoint(failing=True), fail=True)
    assert module._checkpoint_without_reentrant_generator is before
    assert module.CheckpointFunction.forward is before_reentrant


def test_graph_metadata_is_not_accepted_as_arbitrary_module_output(tmp_path):
    class MetadataOutput(torch.nn.Module):
        def forward(self, value):
            return value.square().grad_fn

    session = CaptureSession(tmp_path, device="cpu").start()
    MetadataOutput()(torch.ones(2, requires_grad=True))
    evidence = session.finish()["precision_observation"]
    assert evidence["recognized_graph_metadata_outputs"] == 1
    assert not evidence["complete"]
    assert evidence["errors"]["structure_unsupported"] > 0


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_incompatible_private_api_only_disables_optional_observation(
    tmp_path, monkeypatch, missing
):
    import torch.utils.checkpoint as module

    if missing:
        monkeypatch.delattr(module, "_checkpoint_without_reentrant_generator")
    else:
        monkeypatch.setattr(
            module, "_checkpoint_without_reentrant_generator", lambda arbitrary: None
        )
    session = CaptureSession(tmp_path, device="cpu").start()
    model = torch.nn.Linear(4, 4)
    loss = model(torch.ones(2, 4)).square().mean()
    loss.backward()
    torch.optim.SGD(model.parameters(), lr=0.01).step()
    result = session.finish()
    assert result["status"] == "completed"
    assert result["precision_observation"]["precision"] == "unknown"
    assert result["precision_observation"]["errors"]["checkpoint_scope_unverified"] == 1


def test_custom_dispatch_context_keeps_execution_but_cannot_claim_fp32(tmp_path):
    from torch.overrides import TorchFunctionMode

    events = []

    class HiddenPrecision(TorchFunctionMode):
        def __init__(self, dtype):
            super().__init__()
            self.dtype = dtype

        def __torch_function__(self, func, types, args=(), kwargs=None):
            if func is torch.sin:
                events.append(self.dtype)
                coefficient = args[0].detach().to(self.dtype).cos().float()
                return torch.sin(args[0]) * coefficient
            return func(*args, **(kwargs or {}))

    class Model(torch.nn.Module):
        def forward(self, value):
            return preimported_checkpoint(
                lambda item: torch.sin(item),
                value,
                use_reentrant=False,
                context_fn=lambda: (
                    HiddenPrecision(torch.float32),
                    HiddenPrecision(torch.bfloat16),
                ),
            )

    session = CaptureSession(tmp_path, device="cpu").start()
    Model()(torch.randn(2, 4, requires_grad=True)).sum().backward()
    evidence = session.finish()["precision_observation"]
    assert torch.float32 in events and torch.bfloat16 in events
    assert evidence["precision"] == "unknown" and not evidence["complete"]
    assert evidence["errors"]["checkpoint_context_unverified"] > 0
