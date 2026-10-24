"""Real CPU Docker precision capture; no model API or CUDA workload."""

import json
from pathlib import Path

import pytest

from headroom.lab.runner import run_script
from headroom.verify.compare import compare_runs

SOURCE = """
import sys
import torch

class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.eye(4))

    def forward(self, value):
        if sys.argv[1] == "fp32":
            result = torch.nn.functional.linear(value, self.weight)
        else:
            dtype = torch.bfloat16 if sys.argv[1] == "bf16" else torch.float16
            # Pure functional operation: no child module can expose this context.
            with torch.autocast("cpu", dtype=dtype):
                result = torch.nn.functional.linear(value, self.weight)
        loss = result.float().square().mean()
        print("FINAL_LOSS_DTYPE:" + str(loss.dtype))
        return loss

model = Model()
optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
inputs = torch.ones(2, 4)
for _ in range(3):
    optimizer.zero_grad()
    loss = model(inputs)
    loss.backward()
    optimizer.step()
"""


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in CPU precision integration tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.fixture(scope="module")
def captures(tmp_path_factory):
    root = tmp_path_factory.mktemp("precision-cpu")
    source = root / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(SOURCE)
    results = {}
    for name, precision in (
        ("fp32", "fp32"),
        ("bf16_before", "bf16"),
        ("bf16_after", "bf16"),
        ("unsupported", "fp16"),
    ):
        result = run_script(
            script,
            script_args=[precision],
            source_root=source,
            run_root=root / name,
            device="cpu",
            max_steps=3,
            max_seconds=30,
        )
        assert result["status"] == "completed", result
        assert result["capture_complete"] and result["cleanup_verified"]
        assert result["env"]["device"] == "cpu"
        assert result["steps"] == 3
        assert len(result["loss_series"]) == 3, "Each actual backward must be captured once"
        saved = json.loads((Path(result["run_dir"]) / "result.json").read_text())
        assert saved["precision_observation"] == result["precision_observation"]
        stdout = (Path(result["run_dir"]) / "stdout.log").read_text()
        assert stdout.count("FINAL_LOSS_DTYPE:torch.float32") == 3
        results[name] = result
    return results


def test_actual_cpu_forward_observations_are_persisted(captures):
    for name, precision in (("fp32", "fp32"), ("bf16_before", "bf16"), ("bf16_after", "bf16")):
        observed = captures[name]["precision_observation"]
        assert observed["precision"] == precision and observed["complete"], observed
        assert observed["counts"]["root_forwards"] == 3
        assert observed["dtypes"]["parameter"]["float32"] > 0
        assert observed["dtypes"]["output"]["float32"] > 0
    bf16 = captures["bf16_before"]["precision_observation"]
    assert bf16["autocast"]["bfloat16"] > 0
    assert bf16["dtypes"]["operation_output"]["bfloat16"] > 0


def test_bf16_baseline_and_candidate_use_bf16_tolerance_without_precision_change(captures):
    before, after = captures["bf16_before"], captures["bf16_after"]
    assert before["loss_series"] == after["loss_series"]
    report = compare_runs(before, after, required_steps=3)
    assert report.comparison_precision == "bf16"
    assert report.loss_tolerance == 2e-2
    assert report.observed_precision_change is False
    assert report.checks["numerics_policy"] is True
    assert report.loss_equivalence == "identical"
    # These CPU observations do not establish CUDA memory or throughput acceptance.
    assert report.target_met is False


def test_fp32_to_bf16_is_an_observed_change_requiring_existing_policy_permission(captures):
    report = compare_runs(captures["fp32"], captures["bf16_after"], required_steps=3)
    assert report.observed_precision_change is True
    assert report.checks["numerics_policy"] is False
    allowed = compare_runs(
        captures["fp32"],
        captures["bf16_after"],
        required_steps=3,
        policy={"allow_numerics_change": True},
    )
    assert allowed.observed_precision_change is True
    assert allowed.checks["numerics_policy"] is True


def test_unsupported_precision_stays_unknown_and_cannot_select_relaxed_tolerance(captures):
    unsupported = captures["unsupported"]["precision_observation"]
    assert unsupported["precision"] == "unknown" and unsupported["complete"] is False
    assert unsupported["autocast"]["unsupported"] > 0
    report = compare_runs(captures["fp32"], captures["unsupported"], required_steps=3)
    assert report.comparison_precision == "fp32"
    assert report.loss_tolerance == 1e-3
    assert report.observed_precision_change is None
    assert report.target_met is False


@pytest.mark.parametrize("compilation", ["jit", "compiled"])
def test_cpu_compiled_training_remains_usable_without_precision_mode(tmp_path, compilation):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(
        "import sys\nimport torch\n"
        "class Model(torch.nn.Module):\n"
        "    def __init__(self):\n"
        "        super().__init__()\n"
        "        self.weight = torch.nn.Parameter(torch.eye(4))\n"
        "    def forward(self, value):\n"
        "        return torch.nn.functional.linear(value, self.weight)\n"
        "model = Model()\n"
        "model = torch.jit.script(model) if sys.argv[1] == 'jit' else torch.compile(model, backend='eager')\n"
        "optimizer = torch.optim.SGD(model.parameters(), lr=0.01)\n"
        "value = torch.ones(2, 4)\n"
        "for _ in range(3):\n"
        "    optimizer.zero_grad()\n"
        "    model(value).square().mean().backward()\n"
        "    optimizer.step()\n"
    )
    result = run_script(
        script,
        script_args=[compilation],
        source_root=source,
        run_root=tmp_path / "runs",
        device="cpu",
        max_steps=3,
        max_seconds=30,
    )
    assert result["status"] == "completed", result
    assert result["capture_complete"] and result["cleanup_verified"]
    assert result["steps"] == len(result["loss_series"]) == 3
    assert result["env"]["device"] == "cpu"
    precision = result["precision_observation"]
    assert precision["precision"] == "unknown" and precision["complete"] is False
    assert precision["counts"]["operation_calls"] == 0
