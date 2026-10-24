"""Real CPU fixture/capture parity, never a CUDA memory or repair acceptance claim."""

import json
import math

import pytest
import yaml

from headroom.lab.runner import PROJECT_ROOT, run_command, run_script

TRAINING = """import torch
from torch import nn
torch.set_num_threads(1)
model = nn.Sequential(nn.Linear(8, 16), nn.Tanh(), nn.Linear(16, 1))
optimizer = torch.optim.{optimizer}(model.parameters(), lr=0.01)
for step in range(100):
    inputs = torch.randn(4, 8)
    optimizer.zero_grad(set_to_none=True)
    loss = model(inputs).square().mean()
    loss.backward()
    optimizer.step()
"""


def test_hf_manifest_distinguishes_full_profile_from_cpu_smoke():
    manifest = yaml.safe_load((PROJECT_ROOT / "repos/hf_trainer.yaml").read_text())
    assert manifest["command"] == "python train.py"
    assert manifest["profile"] == "full" and not manifest["acceptance"]["verified"]
    assert manifest["cpu_smoke_command"].endswith("--profile cpu-smoke --device cpu")
    script = PROJECT_ROOT / manifest["source_root"] / manifest["script"]
    source = script.read_text()
    assert "from_pretrained" not in source and "report_to=[]" in source
    assert 'output_dir="/tmp/headroom-hf-trainer"' in source


@pytest.mark.parametrize("scenario", ["sgd", "adamw", "hf_trainer"])
def test_three_cpu_scenarios_match_wrapper_and_injected_command(tmp_path, scenario):
    args = []
    steps = 4
    if scenario == "hf_trainer":
        script = PROJECT_ROOT / "repos/hf_trainer/train.py"
        args = ["--profile", "cpu-smoke", "--device", "cpu"]
        steps = 20
    else:
        source = tmp_path / "source"
        source.mkdir()
        script = source / "train.py"
        script.write_text(TRAINING.format(optimizer="SGD" if scenario == "sgd" else "AdamW"))
    first = run_script(
        script,
        script_args=args,
        run_root=tmp_path / "runs",
        device="cpu",
        max_steps=steps,
        max_seconds=90,
        seed=1337,
    )
    second = run_command(
        script.parent,
        ["python", script.name, *args],
        run_root=tmp_path / "runs",
        device="cpu",
        max_steps=steps,
        max_seconds=90,
        seed=1337,
    )
    for result in (first, second):
        assert result["status"] == "completed", result
        assert result["steps"] == steps and len(result["loss_series"]) == steps
        assert all(math.isfinite(value) for value in result["loss_series"])
        assert result["parameter_count_complete"]
        assert result["cleanup_verified"] and result["peak_alloc_gb"] is None
    assert first["loss_series"] == second["loss_series"]
    assert first["parameter_count"] == second["parameter_count"]
    report = {
        "scenario": scenario,
        "device": "cpu",
        "same_loss_series": True,
        "parameter_count": first["parameter_count"],
        "steps": steps,
        "paths": [first["run_dir"], second["run_dir"]],
        "both_paths_docker_isolated": True,
        "cuda_peak_delta_pct": None,
        "t2_7_acceptance": "pending: CPU has no CUDA peak; both paths use Docker",
    }
    (tmp_path / "cpu-parity.json").write_text(json.dumps(report, indent=2) + "\n")
