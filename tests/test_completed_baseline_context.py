"""Only preserved completed original executions clarify the comparison reference."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from headroom.solver_context import MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES, solver_prompt_context
from headroom.verify.reference_context import numerical_reference_context


def original_run(tmp_path, args=()):
    source = tmp_path / "original.py"
    source.write_text("SOURCE_MARKER = 1\n")
    run_id = "a" * 32
    directory = tmp_path / run_id
    (directory / "artifacts").mkdir(parents=True)
    (directory / "source").mkdir()
    (directory / "source/train.py").write_bytes(source.read_bytes())
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    baseline = {
        "run_id": run_id,
        "run_dir": str(directory),
        "status": "completed",
        "protocol": "headroom.lab.v1",
        "capture_complete": True,
        "cleanup_verified": True,
        "finalization_incomplete": False,
        "steps": 20,
        "loss_series": [1.0] * 20,
        "step_records": [
            {
                "step": step,
                "updated_parameter_ids": ["p00001", "p00002"],
                "parameter_update_coverage_complete": True,
            }
            for step in range(1, 21)
        ],
        "optimizer_update_observation": {
            "protocol": "headroom.optimizer_updates.v1",
            "complete": True,
            "logical_boundary_complete": True,
            "logical_updates": 20,
            "parameter_update_sets_complete": True,
        },
        "env": {"device": "cuda"},
        "precision_observation": {
            "protocol": "headroom.precision.v1",
            "source": "lab_runtime_precision_observer_v1",
            "complete": True,
            "device": "cuda",
            "errors": {},
            "precision": "fp32",
            "root_modes": {"fp32": 20, "bf16": 0, "unknown": 0},
        },
    }
    manifest = {
        "command": [
            "python",
            "-m",
            "headroom.lab.run_target",
            "--script",
            "/source/train.py",
            "--",
            *args,
        ],
        "source": {"files": {"train.py": {"sha256": digest, "bytes": source.stat().st_size}}},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    save_run(baseline)
    return baseline, source, manifest


def save_run(baseline):
    directory = Path(baseline["run_dir"])
    for relative in ("result.json", "artifacts/result.json"):
        (directory / relative).write_text(json.dumps(baseline))


def render(baseline, source, **changes):
    values = {
        "baseline": baseline,
        "original_script": source,
        "original_args": [],
        "retained_script": source,
    }
    values.update(changes)
    return numerical_reference_context({"strategy": "legacy_small_batch"}, **values)


def test_completed_original_is_comparison_reference_not_a_new_small_batch_run(tmp_path):
    baseline, source, _ = original_run(tmp_path)
    before = copy.deepcopy(baseline)
    value = render(baseline, source)
    assert value["selected_strategy"] == "legacy_small_batch"
    assert value["capability_status"] == "not_needed_completed_baseline"
    comparison = value["comparison_reference"]
    assert comparison["kind"] == "completed_original_baseline"
    assert comparison["separate_reference_required"] is False
    observed = comparison["original_baseline"]
    assert observed["status"] == "observed"
    assert observed["source_and_argv_bound"] is True
    assert observed["observed_logical_updates"] == observed["loss_scalar_count"] == 20
    assert observed["capture_complete"] and observed["cleanup_verified"]
    assert observed["loss_scalar_count_matches_logical_updates"] is True
    assert "loss_scalars_aligned_to_updates" not in observed
    assert observed["precision"] == "fp32"
    assert observed["observed_updated_parameter_tensors_per_step"] == {"minimum": 2, "maximum": 2}
    assert observed["candidate_input_pairing_verified"] is None
    assert comparison["candidate_equivalence_verified"] is None
    assert value["reference_execution_verified"] is None
    assert value["candidate_equivalence_verified"] is None
    assert value["original_source"]["status"] == "unsupported"
    assert value["scalar_comparison"]["basis"] == "full_backward_scalar_series"
    assert value["scalar_comparison"]["automatic_microbatch_aggregation"] is False
    assert baseline == before
    assert (
        solver_prompt_context(numerical_reference_context=value)["numerical_reference_context"]
        == value
    )
    serialized = json.dumps(value)
    assert len(serialized.encode()) < MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES
    assert str(tmp_path) not in serialized and "SOURCE_MARKER" not in serialized


@pytest.mark.parametrize(
    "mutation",
    [
        "oom",
        "missing_host",
        "missing_capture",
        "missing_manifest",
        "host_status",
        "capture_status",
        "source_hash",
        "preserved_source",
        "unknown_source",
        "source_symlink",
        "argv",
        "source_path",
        "run_id",
        "cleanup",
        "incomplete_capture",
        "incomplete_finalization",
        "partial_steps",
        "bool_steps",
        "logical_count",
        "logical_boundary",
        "updates_complete",
        "record_order",
        "nan_loss",
        "scalar_count",
        "unknown_precision",
        "host_different_precision",
        "host_different_env",
        "capture_different_loss",
        "command_mode",
        "no_argv",
        "bool_required_steps",
        "selected_capture_mismatch",
    ],
)
def test_incomplete_completed_evidence_cannot_claim_original_comparator(tmp_path, mutation):
    baseline, source, manifest = original_run(tmp_path)
    directory = Path(baseline["run_dir"])
    changes = {}
    if mutation == "oom":
        baseline["status"] = "oom"
    elif mutation.startswith("missing_"):
        filename = {
            "missing_host": "result.json",
            "missing_capture": "artifacts/result.json",
            "missing_manifest": "manifest.json",
        }[mutation]
        (directory / filename).unlink()
    elif mutation in {"host_status", "capture_status"}:
        filename = "result.json" if mutation == "host_status" else "artifacts/result.json"
        other = copy.deepcopy(baseline)
        other["status"] = "error"
        (directory / filename).write_text(json.dumps(other))
    elif mutation == "source_hash":
        manifest["source"]["files"]["train.py"]["sha256"] = "0" * 64
    elif mutation == "preserved_source":
        (directory / "source/train.py").write_text("OTHER = 1\n")
    elif mutation == "unknown_source":
        changes["original_script"] = tmp_path / "missing.py"
    elif mutation == "source_symlink":
        (directory / "source/train.py").unlink()
        (directory / "source/train.py").symlink_to(source)
    elif mutation == "argv":
        changes["original_args"] = ["--batch=1"]
    elif mutation == "source_path":
        manifest["command"][4] = "/source/../original.py"
    elif mutation == "run_id":
        baseline["run_id"] = "b" * 32
    elif mutation == "cleanup":
        baseline["cleanup_verified"] = False
    elif mutation == "incomplete_capture":
        baseline["capture_complete"] = False
    elif mutation == "incomplete_finalization":
        baseline["finalization_incomplete"] = True
    elif mutation == "partial_steps":
        baseline["steps"] = 19
    elif mutation == "bool_steps":
        baseline["steps"] = True
    elif mutation == "logical_count":
        baseline["optimizer_update_observation"]["logical_updates"] = 19
    elif mutation == "logical_boundary":
        baseline["optimizer_update_observation"]["logical_boundary_complete"] = False
    elif mutation == "updates_complete":
        baseline["optimizer_update_observation"]["complete"] = False
    elif mutation == "record_order":
        baseline["step_records"][0]["step"] = 2
    elif mutation == "nan_loss":
        baseline["loss_series"][0] = float("nan")
    elif mutation == "scalar_count":
        baseline["loss_series"].append(1.0)
    elif mutation == "unknown_precision":
        baseline["precision_observation"]["complete"] = False
    elif mutation.startswith("host_different_"):
        other = copy.deepcopy(baseline)
        if mutation == "host_different_env":
            other["env"]["device"] = "cpu"
        else:
            other["precision_observation"]["complete"] = False
        (directory / "result.json").write_text(json.dumps(other))
    elif mutation == "capture_different_loss":
        other = copy.deepcopy(baseline)
        other["loss_series"][0] = 9.0
        (directory / "artifacts/result.json").write_text(json.dumps(other))
    elif mutation == "command_mode":
        changes["command_mode"] = True
    elif mutation == "no_argv":
        changes["original_args"] = None
    elif mutation == "bool_required_steps":
        changes["required_steps"] = True
    elif mutation == "selected_capture_mismatch":
        baseline["selected_capture_relative"] = "artifacts/processes/child"
    if mutation in {
        "oom",
        "run_id",
        "cleanup",
        "incomplete_capture",
        "incomplete_finalization",
        "partial_steps",
        "bool_steps",
        "logical_count",
        "logical_boundary",
        "updates_complete",
        "record_order",
        "nan_loss",
        "scalar_count",
        "unknown_precision",
        "selected_capture_mismatch",
    }:
        save_run(baseline)
    if mutation in {"source_hash", "source_path"}:
        (directory / "manifest.json").write_text(json.dumps(manifest))
    value = render(baseline, source, **changes)
    assert value["comparison_reference"]["original_baseline"]["status"] == "unknown"
    assert value["comparison_reference"]["kind"] != "completed_original_baseline"
    assert value["capability_status"] != "not_needed_completed_baseline"
    assert value["candidate_equivalence_verified"] is None


@pytest.mark.parametrize("count_mutation", ["missing", "duplicate", "not_covered"])
def test_unknown_parameter_update_sets_are_not_invented(tmp_path, count_mutation):
    baseline, source, _ = original_run(tmp_path)
    if count_mutation == "missing":
        baseline["step_records"][0].pop("updated_parameter_ids")
    elif count_mutation == "duplicate":
        baseline["step_records"][0]["updated_parameter_ids"] = ["p1", "p1"]
    else:
        baseline["step_records"][0]["parameter_update_coverage_complete"] = False
    save_run(baseline)
    value = render(baseline, source)
    assert value["comparison_reference"]["original_baseline"]["status"] == "observed"
    assert (
        value["comparison_reference"]["original_baseline"][
            "observed_updated_parameter_tensors_per_step"
        ]
        is None
    )


def test_argv_and_environment_values_are_bound_but_not_disclosed(tmp_path):
    args = ["--private=SECRET_ARG"]
    baseline, source, _ = original_run(tmp_path, args)
    baseline["env"]["PRIVATE"] = "SECRET_ENV"
    save_run(baseline)
    value = render(baseline, source, original_args=args)
    assert value["comparison_reference"]["original_baseline"]["status"] == "observed"
    assert "SECRET_" not in json.dumps(value)


def test_completed_original_does_not_certify_different_retained_candidate(tmp_path):
    baseline, source, _ = original_run(tmp_path)
    candidate = tmp_path / "candidate.py"
    candidate.write_text("DIFFERENT_TRAINING_OBJECTIVE = True\n")
    value = render(baseline, source, retained_script=candidate)
    assert value["comparison_reference"]["kind"] == "completed_original_baseline"
    assert value["candidate_equivalence_verified"] is None
    assert (
        value["comparison_reference"]["original_baseline"]["candidate_input_pairing_verified"]
        is None
    )
    assert value["original_source"]["source_sha256"] != value["retained_source"]["source_sha256"]
