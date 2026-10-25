"""Read-only control fingerprints have explicit type and memory boundaries."""

import json

import pytest
import torch

from headroom.optim.control_capture import TrainingControlCapture


def test_control_capture_preserves_values_and_records_actual_state(tmp_path):
    torch.manual_seed(13)
    model = torch.nn.Linear(3, 2)
    optimizer = torch.optim.AdamW(model.parameters(), foreach=False)
    inputs = torch.randn(4, 3)
    loss = model(inputs).square().mean()
    loss.backward()
    optimizer.step()
    parameters = [item.detach().clone() for item in model.parameters()]
    state = {
        parameter: {name: tensor.clone() for name, tensor in items.items()}
        for parameter, items in optimizer.state.items()
    }
    capture = TrainingControlCapture(tmp_path, chunk_bytes=4)
    first = capture.snapshot("first", model, optimizer, {"inputs": inputs})
    second = capture.snapshot("second", model, optimizer, {"inputs": inputs})
    for key in ("parameters", "optimizer_state", "inputs", "parameter_groups", "bytes_hashed"):
        assert first[key] == second[key]
    assert first["counts_toward_model_acceptance"] is False
    for actual, expected in zip(model.parameters(), parameters, strict=True):
        assert torch.equal(actual, expected)
    for parameter, items in optimizer.state.items():
        for name, actual in items.items():
            assert torch.equal(actual, state[parameter][name])
    saved = json.loads((tmp_path / "control-first.json").read_text())
    assert saved == json.loads(json.dumps(first))


def test_control_fingerprint_changes_on_real_mutation_and_is_chunk_independent(tmp_path):
    small = TrainingControlCapture(tmp_path, chunk_bytes=4)
    large = TrainingControlCapture(tmp_path, chunk_bytes=64)
    tensor = torch.arange(12, dtype=torch.float32).reshape(3, 4)
    before = small.tensor(tensor)
    assert before == large.tensor(tensor)
    tensor[0, 0] = -1
    assert before["sha256"] != large.tensor(tensor)["sha256"]


def test_control_snapshot_bound_and_unsupported_layout_fail_closed(tmp_path):
    capture = TrainingControlCapture(tmp_path, max_bytes=7)
    with pytest.raises(ValueError, match="budget"):
        capture.tensor(torch.ones(2))
    capture = TrainingControlCapture(tmp_path)
    with pytest.raises(ValueError, match="contiguous"):
        capture.tensor(torch.ones(2, 3).t())
    with pytest.raises(ValueError, match="contiguous"):
        capture.tensor(torch.sparse_coo_tensor([[0]], [1.0], (2,)))


@pytest.mark.parametrize("kwargs", [{"max_bytes": 0}, {"chunk_bytes": 0}, {"chunk_bytes": 2**27}])
def test_control_capture_invalid_memory_limits_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        TrainingControlCapture(tmp_path, **kwargs)
