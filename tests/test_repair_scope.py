"""Scope records are offline observations, never new repair acceptance."""

import copy
import difflib
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from headroom.cli import app
from headroom.verify.applicability import build_scope, check_scope, load_json
from headroom.verify.pairing import source_contract

ROOT = Path(__file__).resolve().parents[1]
BASE_ID, CAND_ID = "a" * 32, "b" * 32
IMAGE = "sha256:" + "e" * 64
POLICY = {
    "allow_numerics_change": False,
    "allow_model_change": False,
    "allow_batch_grad_accum": True,
    "max_throughput_regression_pct": 25,
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, allow_nan=False) + "\n")


def alter(path, change):
    value = json.loads(path.read_text())
    change(value)
    write(path, value)


def make_job(root, name="job", *, peak=6000000000, batch=4):
    job = root / name
    source = (ROOT / "scenarios/s3_eval_no_grad_missing/train.py").read_text()
    fixed = source.replace("def evaluate(", "@torch.no_grad()\ndef evaluate(")
    args = ["--batch", str(batch)]
    for run_id, text, measured_peak in [(BASE_ID, source, 10000000000), (CAND_ID, fixed, peak)]:
        lab = job / "lab" / run_id
        (lab / "source").mkdir(parents=True)
        path = lab / "source/train.py"
        path.write_text(text)
        contract = source_contract(path)
        tensors = {
            name: {
                "sha256": hashlib.sha256((name + str(batch)).encode()).hexdigest(),
                "shape": [batch, 8, 32],
                "dtype": "torch.float32",
            }
            for name in contract["tensor_names"]
        }
        capture = {
            "protocol": "headroom.pairing.v1",
            "complete": True,
            "source_contract": contract,
            "tensors": tensors,
            "initial_parameters": [
                {"name": "w", "sha256": "c" * 64, "shape": [32, 32], "dtype": "torch.float32"}
            ],
            "updates": [
                {"step": i, "effective_batch": 1, "training_forwards": 1, "backwards": 1}
                for i in range(1, 21)
            ],
        }
        env = {
            "python": "3.12.fixture",
            "torch": "2.5.1",
            "cuda": "12.4",
            "cudnn": 90100,
            "device": "cuda",
            "seed": 1337,
            "gpu_name": "synthetic GPU fixture",
            "gpu_total_memory_bytes": 24 * 2**30,
            "seeded": {"torch": True, "python": True, "numpy": True},
            "deterministic_algorithms": True,
            "PYTORCH_CUDA_ALLOC_CONF": None,
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
        }
        manifest = {
            "source": {
                "files": {
                    "train.py": {
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "bytes": len(text.encode()),
                    }
                },
                "total_bytes": len(text.encode()),
            },
            "command": [
                "/opt/venv/bin/python",
                "-m",
                "headroom.lab.run_target",
                "--script",
                "/source/train.py",
                "--output",
                "/out",
                "--max-steps",
                "20",
                "--max-seconds",
                "120",
                "--seed",
                "1337",
                "--device",
                "cuda",
                "--",
                *args,
            ],
            "target_argv_override": None,
            "device": "cuda",
            "image_id": IMAGE,
            "max_steps": 20,
            "max_seconds": 120,
            "seed": 1337,
        }
        result = {
            "protocol": "headroom.lab.v1",
            "run_id": run_id,
            "capture_complete": True,
            "cleanup_verified": True,
            "status": "completed",
            "steps": 20,
            "loss_series": [1.0] * 20,
            "peak_allocated_bytes": measured_peak,
            "peak_reserved_bytes": measured_peak,
            "step_ms_median": 100.0,
            "parameter_count": 32 * 32,
            "parameter_count_complete": True,
            "parameter_count_source": "lab_module_parameter_hooks",
            "shared_gpu": False,
            "gpu_observation_complete": True,
            "env": env,
            "image_id": IMAGE,
            "pairing_capture": capture,
            "precision_observation": {
                "protocol": "headroom.precision.v1",
                "source": "lab_runtime_precision_observer_v1",
                "device": "cuda",
                "complete": True,
                "errors": {},
                "precision": "fp32",
                "root_modes": {"fp32": 20, "bf16": 0, "unknown": 0},
            },
        }
        write(lab / "manifest.json", manifest)
        write(lab / "result.json", result)
    patch = "".join(
        difflib.unified_diff(
            source.splitlines(True),
            fixed.splitlines(True),
            fromfile="a/train.py",
            tofile="b/train.py",
        )
    )
    config = job / "configurations/round-01"
    config.mkdir(parents=True)
    (config / "patch.diff").write_text(patch)
    write(
        config / "manifest.json",
        {
            "round": 1,
            "provenance": "offline_fixture",
            "policy": POLICY,
            "numerics_impact": "none",
            "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
        },
    )
    write(config / "cli.json", {"original": args, "effective": args})
    write(
        job / "report.json",
        {
            "run": {
                "provenance": "offline_fixture",
                "request": {
                    "target": "reclaim",
                    "reclaim_reduction_pct": 20,
                    "max_steps": 20,
                    "seed": 1337,
                    "device": "cuda",
                    "policy": POLICY,
                    "max_seconds": 120,
                },
            },
            "rounds": [
                {
                    "number": 1,
                    "verification": {"run_ids": {"baseline": BASE_ID, "candidate": CAND_ID}},
                }
            ],
        },
    )
    return {"job": name, "round": 1}


def build(root, selection):
    scope = build_scope(root, [selection])
    return scope, copy.deepcopy(scope["observations"][0]["context"])


def test_exact_point_is_empirical_and_not_new_mvp_score(tmp_path):
    scope, query = build(tmp_path, make_job(tmp_path))
    assert scope["observations"][0]["status"] == "tested_pass"
    assert scope["observations"][0]["provenance"] == "offline_fixture"
    assert check_scope(tmp_path, scope, query)["status"] == "tested_pass"
    assert any("MVP" in text for text in scope["limitations"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(peak_allocated_bytes=9500000000),
        lambda r: r["loss_series"].__setitem__(0, 2.0),
        lambda r: r["pairing_capture"]["updates"][0].update(effective_batch=2),
        lambda r: r["pairing_capture"]["tensors"]["train_inputs"].update(sha256="f" * 64),
        lambda r: r.update(parameter_count=512),
    ],
)
def test_observed_counterexample_is_not_hidden(tmp_path, mutate):
    selection = make_job(tmp_path)
    alter(tmp_path / "job/lab" / CAND_ID / "result.json", mutate)
    scope, query = build(tmp_path, selection)
    assert scope["observations"][0]["status"] == "tested_fail"
    assert check_scope(tmp_path, scope, query)["status"] == "tested_fail"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(peak_allocated_bytes=None),
        lambda r: r.update(parameter_count_complete=False),
        lambda r: r.pop("precision_observation"),
        lambda r: r["pairing_capture"].update(complete=False),
        lambda r: r["pairing_capture"].update(tensors={}),
        lambda r: r["pairing_capture"].update(initial_parameters=[]),
        lambda r: r.update(gpu_observation_complete=False),
        lambda r: r.update(capture_complete=False),
    ],
)
def test_missing_evidence_never_becomes_pass_or_counterexample(tmp_path, mutate):
    selection = make_job(tmp_path)
    alter(tmp_path / "job/lab" / CAND_ID / "result.json", mutate)
    scope = build_scope(tmp_path, [selection])
    assert scope["observations"][0]["status"] == "unknown"


@pytest.mark.parametrize(
    "path,value",
    [
        (["target"], "fit:8GB"),
        (["required_steps"], 40),
        (["required_steps"], True),
        (["effective_argv"], ["--batch", "8"]),
        (["workload", "inputs_sha256"], "0" * 64),
        (["workload", "updates_sha256"], "1" * 64),
        (["source_tree_sha256", "candidate"], "2" * 64),
        (["environment", "candidate", "image_id"], "sha256:" + "3" * 64),
        (["environment", "candidate", "gpu_name"], "different GPU"),
        (["environment", "candidate", "torch"], "different torch"),
        (["observed_precision", "candidate"], "bf16"),
        (["policy", "allow_numerics_change"], True),
    ],
)
def test_changed_conditions_are_unknown(tmp_path, path, value):
    scope, query = build(tmp_path, make_job(tmp_path))
    node = query
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    result = check_scope(tmp_path, scope, query)
    assert result["status"] == "unknown"


def test_passes_at_endpoints_do_not_cover_an_untested_midpoint(tmp_path):
    selections = [make_job(tmp_path, "four", batch=4), make_job(tmp_path, "sixteen", batch=16)]
    scope = build_scope(tmp_path, selections)
    assert [x["status"] for x in scope["observations"]] == ["tested_pass"] * 2
    query = copy.deepcopy(scope["observations"][0]["context"])
    query["original_argv"] = query["effective_argv"] = ["--batch", "8"]
    assert check_scope(tmp_path, scope, query)["status"] == "unknown"


def test_identical_context_counterexample_overrides_success(tmp_path):
    selections = [make_job(tmp_path, "good"), make_job(tmp_path, "bad", peak=9500000000)]
    scope = build_scope(tmp_path, selections)
    assert scope["observations"][0]["context"] == scope["observations"][1]["context"]
    verdict = check_scope(tmp_path, scope, scope["observations"][0]["context"])
    assert verdict["status"] == "tested_fail"
    assert len(scope["observations"]) == 2


@pytest.mark.parametrize(
    "relative",
    [
        f"job/lab/{CAND_ID}/result.json",
        f"job/lab/{BASE_ID}/source/train.py",
        "job/configurations/round-01/patch.diff",
        "job/report.json",
    ],
)
def test_changed_archive_invalidates_existing_record(tmp_path, relative):
    scope, query = build(tmp_path, make_job(tmp_path))
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b" ")
    assert check_scope(tmp_path, scope, query)["status"] == "invalid_evidence"


def test_tampered_claim_or_deleted_counterexample_invalidates_scope(tmp_path):
    selections = [make_job(tmp_path, "good"), make_job(tmp_path, "bad", peak=9500000000)]
    scope = build_scope(tmp_path, selections)
    query = scope["observations"][0]["context"]
    scope["observations"].pop()
    assert check_scope(tmp_path, scope, query)["status"] == "invalid_evidence"


@pytest.mark.parametrize(
    "selection",
    [{"job": "../escape", "round": 1}, {"job": "/tmp", "round": 1}, {"job": "job", "round": True}],
)
def test_selection_validation(tmp_path, selection):
    make_job(tmp_path)
    with pytest.raises(ValueError):
        build_scope(tmp_path, [selection])


def test_linked_artifact_and_unlisted_source_are_rejected(tmp_path):
    selection = make_job(tmp_path)
    path = tmp_path / "job/lab" / CAND_ID / "source/train.py"
    original = path.read_text()
    path.unlink()
    outside = tmp_path / "outside.py"
    outside.write_text(original)
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        build_scope(tmp_path, [selection])
    path.unlink()
    path.write_text(original)
    (path.parent / "unexpected.py").write_text("pass\n")
    with pytest.raises(ValueError):
        build_scope(tmp_path, [selection])


@pytest.mark.parametrize("text", ['{"x": 1, "x": 2}', '{"x": NaN}', '{"x": 1e999}'])
def test_ambiguous_or_nonfinite_json_rejected(tmp_path, text):
    path = tmp_path / "input.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_json(path)


def test_cli_build_check_and_no_overwrite(tmp_path):
    selection = make_job(tmp_path)
    spec, record, query = [tmp_path / name for name in ("spec.json", "scope.json", "query.json")]
    write(spec, {"selections": [selection]})
    runner = CliRunner()
    args = ["scope", "build", str(spec), "--evidence-root", str(tmp_path), "--output", str(record)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    before = record.read_bytes()
    result = runner.invoke(app, args)
    assert result.exit_code == 78
    assert record.read_bytes() == before
    write(query, json.loads(before)["observations"][0]["context"])
    result = runner.invoke(
        app, ["scope", "check", str(record), str(query), "--evidence-root", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    alter(query, lambda q: q.update(required_steps=21))
    result = runner.invoke(
        app, ["scope", "check", str(record), str(query), "--evidence-root", str(tmp_path)]
    )
    assert result.exit_code == 78 and json.loads(result.output)["status"] == "unknown"
