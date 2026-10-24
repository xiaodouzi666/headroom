import gc
import weakref

import pytest
import torch

from headroom.lab.hooks import CaptureSession, StepLimitReached, active_session


@pytest.fixture(autouse=True)
def finish_session():
    yield
    session = active_session()
    if session is not None:
        session.finish()


def test_root_parameter_counts_include_unused_registered_model_and_deduplicate(tmp_path):
    session = CaptureSession(tmp_path, device="cpu").start()
    model = torch.nn.Sequential(torch.nn.Linear(3, 1))
    model.add_module("alias", model[0])
    unused = torch.nn.Linear(2, 2)
    # Call only the root Linear: shared registration must not double count it.
    model[0](torch.ones(1, 3))
    result = session.finish()
    assert result["parameter_count"] == 10
    assert result["parameter_count_complete"]
    assert result["root_forward_parameter_counts"] == [4]
    assert sum(p.numel() for p in unused.parameters()) == 6


def test_parameter_observation_does_not_keep_module_or_tensor_alive(tmp_path):
    session = CaptureSession(tmp_path, device="cpu").start()
    dead = torch.nn.Linear(100, 100)
    reference = weakref.ref(dead.weight)
    del dead
    gc.collect()
    assert reference() is None
    model = torch.nn.Linear(3, 1)
    model(torch.ones(1, 3))
    result = session.finish()
    assert result["parameter_count"] == 4
    assert result["parameter_count_complete"]


def test_missing_root_forward_cannot_certify_constructed_model(tmp_path):
    session = CaptureSession(tmp_path, device="cpu").start()
    model = torch.nn.Linear(3, 1)
    result = session.finish("error", RuntimeError("construction failed"))
    assert model.weight.numel() == 3
    assert result["parameter_count"] is None
    assert not result["parameter_count_complete"]


def test_real_optimizer_limit_captures_parameter_count_and_removes_hooks(tmp_path):
    session = CaptureSession(tmp_path, max_steps=2, device="cpu").start()
    model = torch.nn.Sequential(torch.nn.Linear(3, 4), torch.nn.ReLU(), torch.nn.Linear(4, 1))
    optimizer = torch.optim.SGD(model.parameters(), lr=0.001)
    with pytest.raises(StepLimitReached) as stopped:
        for _ in range(10):
            optimizer.zero_grad()
            model(torch.ones(1, 3)).square().mean().backward()
            optimizer.step()
    result = session.finish(exc=stopped.value)
    assert result["parameter_count"] == sum(p.numel() for p in model.parameters()) == 21
    assert result["parameter_count_complete"]
    before = list(result["root_forward_parameter_counts"])
    model(torch.ones(1, 3))
    assert session._root_parameter_counts == before
    assert not session._parameter_handles
