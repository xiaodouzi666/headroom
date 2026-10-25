"""Explicit transformed references remain baseline-bound and fail closed."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from headroom.lab.runner import run_script
from headroom.verify.checkpoint import (
    PROTOCOL,
    STRATEGY,
    TRANSFORM,
    attest_reference,
    prepare_reference,
    reference_proof,
    transform_source,
)
from headroom.verify.compare import compare_runs
from headroom.verify.pairing import CONTRACTS, source_contract
from headroom.verify.reference_config import NumericalReference
from headroom.verify.runner import verify_script

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scenarios/s1_batch_too_big/train.py"
SOURCE = SCRIPT.read_bytes()
SOURCE_HASH = hashlib.sha256(SOURCE).hexdigest()
TRANSFORMED = transform_source(SOURCE)
TRANSFORMED_HASH = hashlib.sha256(TRANSFORMED).hexdigest()
ARGS = ["--tiny", "--device", "cpu", "--steps", "20"]


def measured(status="completed", transformed=False):
    from test_verify_offload_reference import measured as offload_fixture

    result = offload_fixture(status)
    result["pairing_capture"]["source_contract"].update(
        profile="s1",
        contract_sha256=CONTRACTS["s1"]["digest"],
        source_sha256=TRANSFORMED_HASH if transformed else SOURCE_HASH,
        checkpointed=transformed,
    )
    result["pairing_capture"]["checkpoint_recomputation_root_forwards"] = 40 if transformed else 0
    return result


def reference():
    result = measured(transformed=True)
    binding = {
        "valid": True,
        "baseline_run_id": "baseline-oom",
        "source_sha256": SOURCE_HASH,
        "original_args": ["--batch=32"],
    }
    result["original_baseline_binding"] = binding
    result["reference_checkpoint"] = {
        "protocol": PROTOCOL,
        "mode": STRATEGY,
        "transform_version": TRANSFORM,
        "source_kind": "baseline_derived_transformed_reference",
        "original_source_sha256": SOURCE_HASH,
        "transformed_source_sha256": TRANSFORMED_HASH,
        "script_args": ["--batch=32"],
        "max_seconds": 120,
        "required_steps": 20,
        "performance_comparable": False,
        "use_reentrant": False,
        "preserve_rng_state": True,
        "request_verified": True,
        "failure": None,
    }
    return result


def test_explicit_transformed_reference_keeps_scalar_tolerance_and_candidate_metrics():
    baseline, candidate, ref = measured("oom"), measured(transformed=True), reference()
    ref["peak_allocated_bytes"], ref["step_ms_median"] = 1, 90000
    report = compare_runs(baseline, candidate, reference=ref, reference_strategy=STRATEGY)
    assert report.target_met
    assert report.checks["original_workload_checkpoint_reference"]
    assert report.numerical_basis == "baseline_derived_checkpoint_first_five_backward_scalars"
    assert report.loss_tolerance == 1e-3
    assert report.peak_after == 2.0
    assert any("not byte-for-byte" in note for note in report.notes)
    candidate["loss_series"][0] += 0.01
    failed = compare_runs(baseline, candidate, reference=ref, reference_strategy=STRATEGY)
    assert not failed.target_met and failed.loss_equivalence == "changed"
    assert failed.loss_tolerance == 1e-3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["reference_checkpoint"].update(transform_version="unreviewed"),
        lambda r: r["reference_checkpoint"].update(request_verified=False),
        lambda r: r["reference_checkpoint"].update(original_source_sha256="other-source"),
        lambda r: r["reference_checkpoint"].update(transformed_source_sha256=SOURCE_HASH),
        lambda r: r["reference_checkpoint"].update(script_args=["--batch=1"]),
        lambda r: r["reference_checkpoint"].update(max_seconds=481),
        lambda r: r["reference_checkpoint"].update(max_seconds=True),
        lambda r: r["reference_checkpoint"].update(use_reentrant=True),
        lambda r: r["reference_checkpoint"].update(preserve_rng_state=False),
        lambda r: r["reference_checkpoint"].update(failure="failed"),
        lambda r: r["reference_checkpoint"].update(performance_comparable=True),
        lambda r: r["pairing_capture"].update(checkpoint_recomputation_root_forwards=0),
        lambda r: r["pairing_capture"].update(initial_parameters=["different-init"]),
        lambda r: r["pairing_capture"]["tensors"].update(inputs="different-inputs"),
        lambda r: r["pairing_capture"]["updates"][0].update(effective_batch=1),
        lambda r: r["precision_observation"].update(complete=False, precision="unknown"),
        lambda r: r["precision_observation"].update(precision="bf16"),
        lambda r: r.update(steps=19),
        lambda r: r.update(cleanup_verified=False),
        lambda r: r.update(status="timeout"),
        lambda r: r["env"].update(torch="2.6.0"),
    ],
)
def test_matching_losses_and_caller_pairing_cannot_override_failed_proof(mutation):
    ref = reference()
    mutation(ref)
    report = compare_runs(
        measured("oom"),
        measured(transformed=True),
        reference=ref,
        reference_strategy=STRATEGY,
        pairing=dict.fromkeys(("same_inputs", "same_effective_batch", "same_objective"), True),
    )
    assert not report.target_met
    assert not report.checks["original_workload_checkpoint_reference"]
    assert report.loss_equivalence == "n/a"


def test_checkpoint_failure_never_uses_repository_no_reference_exception():
    report = compare_runs(
        measured("oom"),
        measured(),
        reference_strategy=STRATEGY,
        acceptance_scope="repository",
    )
    assert not report.target_met
    assert report.checks["repository_no_reference_exception"] is False


def test_original_initial_values_and_precision_are_required():
    for mutation in (
        lambda b: b["pairing_capture"].update(initial_parameters=["changed"]),
        lambda b: b["pairing_capture"]["tensors"].update(inputs="changed"),
        lambda b: b["precision_observation"].update(complete=False),
        lambda b: b["pairing_capture"]["source_contract"].update(checkpointed=True),
    ):
        baseline = measured("oom")
        mutation(baseline)
        assert not reference_proof(reference(), measured(transformed=True), baseline=baseline)[
            "valid"
        ]


def test_checkpoint_configuration_is_explicit_and_does_not_expand_resources():
    options = NumericalReference(strategy=STRATEGY, max_seconds=480)
    assert options.verify_kwargs() == {"reference_strategy": STRATEGY, "reference_max_seconds": 480}
    assert NumericalReference().verify_kwargs() == {}
    for bad in (
        {"disk_saved_tensor_limit_bytes": 1},
        {"cpu_saved_tensor_limit_bytes": 1024},
        {"max_seconds": 481},
    ):
        with pytest.raises(ValidationError):
            NumericalReference(strategy=STRATEGY, **bad)


def test_runner_rejects_supplied_reference_and_unsupported_settings_before_dispatch(monkeypatch):
    from headroom.verify import runner

    monkeypatch.setattr(runner, "run_script", lambda *a, **kw: pytest.fail("must not dispatch"))
    for options in (
        {"reference": reference()},
        {"required_steps": 19},
        {"reference_max_seconds": 481},
        {"reference_offload_disk_bytes": 1},
        {"reference_offload_bytes": 1024},
    ):
        with pytest.raises(ValueError):
            verify_script(measured("oom"), SCRIPT, reference_strategy=STRATEGY, **options)


def test_transformation_deterministic_and_contract_bound(tmp_path):
    path = tmp_path / "train.py"
    path.write_bytes(TRANSFORMED)
    contract = source_contract(path)
    assert contract["supported"] and contract["profile"] == "s1" and contract["checkpointed"]
    assert transform_source(SOURCE) == TRANSFORMED
    assert SOURCE_HASH != TRANSFORMED_HASH


def test_real_cpu_wrapper_attests_transformed_source_original_argv_and_twenty_updates(tmp_path):
    # A completed CPU run supplies real captured tensors/manifest. Only the OOM
    # trigger is emulated here; this cannot certify a GPU OOM or acceptance.
    original = run_script(SCRIPT, script_args=ARGS, device="cpu", run_root=tmp_path / "runs")
    assert original["status"] == "completed" and original["steps"] == 20
    baseline = copy.deepcopy(original)
    baseline["status"] = "oom"
    candidate_script = tmp_path / "candidate" / "train.py"
    candidate_script.parent.mkdir()
    candidate_script.write_bytes(TRANSFORMED)
    result = verify_script(
        baseline,
        candidate_script,
        baseline_script=SCRIPT,
        script_args=ARGS,
        reference_strategy=STRATEGY,
        reference_max_seconds=60,
        device="cpu",
        run_root=tmp_path / "runs",
    )
    ref = result["reference"]
    receipt = ref["reference_checkpoint"]
    assert ref["status"] == "completed" and ref["steps"] == 20
    assert ref["precision_observation"]["complete"]
    assert ref["precision_observation"]["precision"] == "fp32"
    assert result["candidate"]["precision_observation"]["precision"] == "fp32"
    assert receipt["request_verified"] and receipt["failure"] is None
    assert receipt["original_source_sha256"] == SOURCE_HASH
    assert receipt["transformed_source_sha256"] == TRANSFORMED_HASH
    assert receipt["script_args"] == ARGS
    assert receipt["source_kind"] == "baseline_derived_transformed_reference"
    assert ref["pairing_capture"]["checkpoint_recomputation_root_forwards"] == 40
    assert all(result["pairing_evidence"]["checks"].values())
    assert ref["loss_series"] == result["candidate"]["loss_series"] == original["loss_series"]
    assert not result["report"].target_met  # CPU evidence cannot meet CUDA gates.
    assert len(result["reference_discovery"]["attempts"]) == 1
    manifest = json.loads((Path(ref["run_dir"]) / "manifest.json").read_text())
    assert "--reference-offload-bytes" not in manifest["command"]
    transformed_script = (
        Path(result["candidate"]["run_dir"]) / "checkpoint-reference-source/train.py"
    )
    transformed_script.write_bytes(TRANSFORMED + b"# changed after execution\n")
    changed = attest_reference(ref, receipt, SCRIPT, transformed_script)
    assert not changed["reference_checkpoint"]["request_verified"]
    assert changed["reference_checkpoint"]["failure"] is not None


def test_bad_baseline_argv_and_non_original_source_cannot_prepare(tmp_path):
    baseline = measured("oom")
    baseline["run_dir"] = str(tmp_path / "baseline")
    directory = Path(baseline["run_dir"])
    (directory / "artifacts").mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "command": [
                    "/opt/venv/bin/python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                    "--",
                    "--batch=32",
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="bound original"):
        prepare_reference(baseline, SCRIPT, ["--batch=1"], tmp_path / "invalid", 120)
    transformed_script = tmp_path / "transformed.py"
    transformed_script.write_bytes(TRANSFORMED)
    with pytest.raises(ValueError, match="bound original"):
        prepare_reference(baseline, transformed_script, ["--batch=32"], tmp_path / "invalid2", 120)
    assert not (tmp_path / "invalid").exists()
    assert not (tmp_path / "invalid2").exists()


@pytest.mark.parametrize("failure_status", ["oom", "timeout", "error"])
def test_failed_reference_is_attempted_once_with_original_argv_no_legacy_fallback(
    tmp_path, monkeypatch, failure_status
):
    from headroom.verify import runner

    original_args = ["--batch=32"]
    baseline = measured("oom")
    original_dir = tmp_path / "baseline"
    (original_dir / "artifacts").mkdir(parents=True)
    baseline["run_dir"] = str(original_dir)
    (original_dir / "manifest.json").write_text(
        json.dumps(
            {
                "command": [
                    "/opt/venv/bin/python",
                    "-m",
                    "headroom.lab.run_target",
                    "--script",
                    "/source/train.py",
                    "--",
                    *original_args,
                ],
            }
        )
    )
    calls = []

    def fake_lab(script, **kwargs):
        calls.append((Path(script), kwargs))
        directory = tmp_path / ("candidate" if len(calls) == 1 else "reference")
        (directory / "artifacts").mkdir(parents=True)
        item = measured(transformed=len(calls) == 2)
        item["run_dir"] = str(directory)
        if len(calls) == 2:
            item.update(status=failure_status, steps=0)
            assert Path(script).read_bytes() == TRANSFORMED
            assert kwargs["script_args"] == original_args
            assert kwargs["max_seconds"] == 120
            assert "reference_offload_bytes" not in kwargs
        command = [
            "/opt/venv/bin/python",
            "-m",
            "headroom.lab.run_target",
            "--script",
            "/source/train.py",
            "--max-steps",
            "20",
            "--max-seconds",
            "120",
            "--",
            *kwargs["script_args"],
        ]
        (directory / "manifest.json").write_text(json.dumps({"command": command}))
        return item

    monkeypatch.setattr(runner, "run_script", fake_lab)
    result = verify_script(
        baseline,
        SCRIPT,
        baseline_script=SCRIPT,
        script_args=["--batch=16"],
        baseline_args=original_args,
        reference_strategy=STRATEGY,
    )
    assert len(calls) == 2
    assert result["reference"]["status"] == failure_status
    assert len(result["reference_discovery"]["attempts"]) == 1
    assert not result["report"].target_met
    assert not result["report"].checks["original_workload_checkpoint_reference"]


def test_source_or_argv_mismatch_never_dispatches_a_reference(tmp_path, monkeypatch):
    from headroom.verify import runner

    baseline = measured("oom")
    baseline["run_dir"] = str(tmp_path / "missing-original-capture")
    candidate_dir = tmp_path / "candidate"
    candidate_dir.mkdir()
    candidate = measured()
    candidate["run_dir"] = str(candidate_dir)
    calls = []

    def fake_lab(*args, **kwargs):
        calls.append((args, kwargs))
        return candidate

    monkeypatch.setattr(runner, "run_script", fake_lab)
    result = verify_script(
        baseline,
        SCRIPT,
        baseline_script=SCRIPT,
        baseline_args=["--batch=32"],
        reference_strategy=STRATEGY,
    )
    assert len(calls) == 1
    assert result["reference"] is None
    assert result["reference_discovery"]["attempts"] == []
    assert "preparation failed" in result["reference_discovery"]["reason"]
    assert not result["report"].target_met
