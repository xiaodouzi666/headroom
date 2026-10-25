"""Static batch discovery and real CPU Docker verification; no CUDA runs."""

import json
from pathlib import Path

import pytest

from headroom.lab.runner import run_script
from headroom.verify.compare import compare_runs
from headroom.verify.runner import batch_arguments, discover_batch, verify_script

TRAINING = """import argparse
import torch
from torch import nn
parser=argparse.ArgumentParser()
parser.add_argument("--batch",type=int,default=4)
parser.add_argument("--width",type=int,default=16)
args=parser.parse_args()
torch.set_num_threads(1)
model=nn.Sequential(nn.Linear(8,args.width),nn.Tanh(),nn.Linear(args.width,1))
optimizer=torch.optim.SGD(model.parameters(),lr=0.01)
x=torch.arange(args.batch*8,dtype=torch.float32).reshape(args.batch,8)/100
target=torch.ones(args.batch,1)
for step in range(100):
    optimizer.zero_grad()
    loss=(model(x)-target).square().mean()
    loss.backward()
    optimizer.step()
"""
PAIR = {"same_inputs": True, "same_effective_batch": True, "same_objective": True}


@pytest.fixture
def training(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(TRAINING)
    return script


def test_discover_argparse_batch_without_executing_script(training):
    details = discover_batch(training, ["--batch=8"])
    assert details["found"] and details["flag"] == "--batch"
    assert details["original_batch"] == 8
    assert batch_arguments(["--width", "16", "--batch=8"], "--batch", 1) == [
        "--width",
        "16",
        "--batch=1",
    ]


def test_explicit_yaml_batch_mapping_is_safe_and_supported(training):
    (training.parent / "headroom.yaml").write_text("batch:\n  arg: --batch_size\n  value: 32\n")
    details = discover_batch(training)
    assert details["flag"] == "--batch_size" and details["original_batch"] == 32


def test_unsafe_yaml_and_ambiguous_batch_do_not_trigger_execution(training):
    (training.parent / "headroom.yaml").write_text("!!python/object/apply:os.system ['false']")
    assert not discover_batch(training)["found"]


def test_no_discoverable_flag_means_no_reference_guess(tmp_path):
    script = tmp_path / "plain.py"
    script.write_text("raise RuntimeError('must never import')")
    assert not discover_batch(script)["found"]


def test_cpu_pair_is_identical_and_half_model_is_rejected(training, tmp_path):
    root = tmp_path / "runs"
    baseline = run_script(training, run_root=root, device="cpu", max_steps=20, seed=17)
    assert baseline["status"] == "completed", baseline
    assert baseline["parameter_count"] == 161 and baseline["parameter_count_complete"]
    same = verify_script(
        baseline, training, run_root=root, device="cpu", target="reclaim", pairing=PAIR
    )
    report = same["report"]
    assert same["candidate"]["status"] == "completed"
    assert report.loss_equivalence == "identical"
    assert report.parameter_count_before == report.parameter_count_after == 161
    assert not report.target_met and report.peak_after is None
    half = verify_script(
        baseline,
        training,
        script_args=["--width", "8"],
        run_root=root,
        device="cpu",
        target="reclaim",
        pairing=PAIR,
    )
    assert half["candidate"]["status"] == "completed"
    assert half["report"].parameter_count_after == 81
    assert half["report"].loss_equivalence == "changed"
    assert half["report"].max_loss_delta > 1e-3
    assert not half["report"].target_met
    for result in (baseline, same["candidate"], half["candidate"]):
        assert result["cleanup_verified"]
    saved = Path(half["candidate"]["run_dir"]) / "verification.json"
    assert json.loads(saved.read_text())["report"]["loss_equivalence"] == "changed"


def test_existing_saved_lab_result_cannot_supply_missing_parameter_evidence():
    # Existing actual Lab captures predate parameter hooks. Read without altering them.
    root = Path(__file__).resolve().parents[1]
    source = root / "reports/t1.1-acceptance.json"
    if not source.exists():
        pytest.skip("Historical acceptance report is not available in this checkout")
    records = json.loads(source.read_text())["runs"]
    candidates = []
    for entry in records.values():
        path = root / entry["run_dir"] / "result.json"
        if path.exists():
            value = json.loads(path.read_text())
            if value.get("status") == "completed":
                candidates.append(value)
    if len(candidates) < 2:
        pytest.skip("Historical paired completed captures are unavailable")
    report = compare_runs(candidates[0], candidates[1], target="reclaim", pairing=PAIR)
    assert not report.target_met
    assert report.checks["parameter_count_unchanged"] is None


def test_oom_reference_runs_original_smallest_batch_through_lab_only(
    training, tmp_path, monkeypatch
):
    from headroom.verify import runner

    calls = []

    def fake_lab(script, **kwargs):
        calls.append((Path(script), kwargs))
        index = len(calls)
        return {
            "status": "completed",
            "steps": 20,
            "run_id": str(index),
            "loss_series": [1.0] * 20,
            "env": {"seed": 7},
            "cleanup_verified": True,
        }

    monkeypatch.setattr(runner, "run_script", fake_lab)
    baseline = {"status": "oom", "env": {"seed": 7}}
    outcome = verify_script(
        baseline,
        training,
        baseline_script=training,
        script_args=["--width", "8"],
        baseline_args=["--width", "16", "--batch=4"],
        device="cpu",
        run_root=tmp_path / "runs",
    )
    assert len(calls) == 2
    assert calls[1][1]["script_args"] == ["--width", "16", "--batch=1"]
    assert calls[1][1]["seed"] == calls[0][1]["seed"] == 7
    assert calls[1][1]["max_steps"] == 20
    assert outcome["reference_discovery"]["reference_batch"] == 1
    assert not outcome["report"].target_met


def test_undiscoverable_batch_never_runs_a_guessed_reference(tmp_path, monkeypatch):
    from headroom.verify import runner

    script = tmp_path / "plain.py"
    script.write_text("print('no configurable batch')")
    calls = []

    def fake_lab(*args, **kwargs):
        calls.append(args)
        return {"status": "completed", "steps": 20, "env": {"seed": 7}}

    monkeypatch.setattr(runner, "run_script", fake_lab)
    outcome = verify_script(
        {"status": "oom", "env": {"seed": 7}},
        script,
        baseline_script=script,
        baseline_args=[],
        device="cpu",
    )
    assert len(calls) == 1
    assert outcome["reference"] is None
    assert not outcome["report"].target_met


def test_reference_batch_preserves_nanogpt_equals_configurator_syntax():
    original = ["--batch_size=32", "--n_layer=24", "--dataset=headroom_synthetic"]
    result = batch_arguments(original, "--batch_size", 1)
    assert result == ["--n_layer=24", "--dataset=headroom_synthetic", "--batch_size=1"]
    # Mirror upstream's required key=value parsing, without importing its code.
    settings = {key[2:]: value for key, value in (arg.split("=", 1) for arg in result)}
    assert settings["batch_size"] == "1"
    assert original[0] == "--batch_size=32"


def test_reference_batch_preserves_separate_value_and_removes_duplicates():
    assert batch_arguments(["--batch", "4", "--width", "16"], "--batch", 1) == [
        "--width",
        "16",
        "--batch",
        "1",
    ]
    assert batch_arguments(["--batch", "4", "--batch=8"], "--batch", 1) == ["--batch=1"]
    assert batch_arguments([], "--batch", 1) == ["--batch", "1"]


def test_oom_candidate_skips_reference_discovery_and_reports_why(training, monkeypatch):
    from headroom.verify import runner

    calls = []

    def fake_lab(script, **kwargs):
        calls.append((script, kwargs))
        return {"status": "oom", "steps": 0, "env": {"seed": 7}}

    def forbidden_discovery(*args, **kwargs):
        raise AssertionError("An incomplete candidate must not trigger reference discovery")

    monkeypatch.setattr(runner, "run_script", fake_lab)
    monkeypatch.setattr(runner, "discover_batch", forbidden_discovery)
    outcome = verify_script(
        {"status": "oom", "env": {"seed": 7}},
        training,
        baseline_script=training,
        baseline_args=["--batch=4"],
        device="cpu",
    )
    reason = "Candidate did not complete; small-batch reference was not executed"
    assert len(calls) == 1
    assert outcome["reference"] is None
    assert outcome["reference_discovery"] == {"found": False, "reason": reason, "attempts": []}
    assert not outcome["report"].target_met
    assert "Reference discovery: " + reason in outcome["report"].notes
