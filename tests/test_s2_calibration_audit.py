"""Offline aggregation and provenance failures, never real measurement fixtures."""

import json
from pathlib import Path

import pytest

import headroom.acceptance.s2_calibration_audit as audit
from headroom.acceptance.s2_calibration import CASES, digest, prepare

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    for relative in (
        "scenarios/s2_capacity_v2/train.py",
        "scenarios/s2_optimizer_classification_v2/train.py",
        "scenarios/s2_fp32_adamw_1b/train.py",
        "eval/mvp_phase1.yaml",
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    original = tmp_path / "reports/original"
    prepare(original, project_root=tmp_path)
    run_dir = original / "lab/classification"
    run_dir.mkdir(parents=True)
    result = {
        "status": "completed",
        "steps": 20,
        "capture_complete": True,
        "cleanup_verified": True,
        "shared_gpu": False,
    }
    (run_dir / "result.json").write_text(json.dumps(result))
    receipt = {
        "case": "classification",
        "run_dir": str(run_dir),
        "passed": True,
        "preregistration_sha256": digest(original / "preregistration.json"),
        "source_sha256": digest(tmp_path / "scenarios/s2_optimizer_classification_v2/train.py"),
        "result_sha256": digest(run_dir / "result.json"),
        "analysis_header": {
            "recorded_peak_allocated_bytes": 20_000_000_000,
            "peak_allocated_bytes": 20_000_000_000,
            "history_complete": True,
            "peak_is_exact": True,
        },
        "optimizer_state_category_bytes": 8_000_000_000,
        "optimizer_inventory": {
            "observed_after_update": 19,
            "parameters_total": 1,
            "parameters_initialized": 1,
            "all_parameter_states_initialized": True,
            "moment_layout_valid": True,
            "cuda_moment_tensor_bytes": 8_000_000_000,
            "moment_tensor_bytes": 8_000_000_000,
        },
    }
    classification = original / "classification.json"
    classification.write_text(json.dumps(receipt))
    directory = tmp_path / "reports/current"
    prepare(
        directory,
        project_root=tmp_path,
        allocator_conf="expandable_segments:True",
        classification_receipt=classification,
    )
    for case in CASES[1:]:
        (directory / (case + ".json")).write_text(
            json.dumps(
                {
                    "case": case,
                    "preregistration_sha256": digest(directory / "preregistration.json"),
                }
            )
        )
    manifest = tmp_path / "eval/new.yaml"
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "scenarios": [
                    {
                        "id": "s2_capacity_v2",
                        "group": "synthetic",
                        "script": "scenarios/s2_capacity_v2/train.py",
                        "source_root": "scenarios/s2_capacity_v2",
                        "script_args": ["--seed", "1337"],
                        "target": "fit:22GB",
                        "expected_baseline": "completed",
                        "allocator_conf": "expandable_segments:True",
                        "source_sha256": digest(tmp_path / "scenarios/s2_capacity_v2/train.py"),
                    }
                ],
            }
        )
    )
    measured = {
        case: {
            "case": case,
            "accepted": True,
            "image_id": "sha256:offline-mock",
            "environment_sha256": "e" * 64,
        }
        for case in CASES
    }

    def mocked_measurement(receipt_path, *args, **kwargs):
        return measured[json.loads(receipt_path.read_text())["case"]]

    monkeypatch.setattr(audit, "audit_case", mocked_measurement)
    return tmp_path, manifest, directory, classification, measured


def run(tree):
    root, manifest, directory, _, _ = tree
    return audit.audit_calibration(manifest, directory, project_root=root)


def test_all_five_measurements_required_and_never_score_credit(tree):
    result = run(tree)
    assert result["accepted"] and len(result["cases"]) == 5
    assert result["repair_scores_awarded"] == result["model_calls"] == 0
    assert result["executed"] is False


@pytest.mark.parametrize("case", CASES)
def test_a_failed_recomputed_measurement_cannot_be_overridden_by_receipts(tree, case):
    tree[-1][case]["accepted"] = False
    assert not run(tree)["accepted"]


def test_missing_control_is_pending(tree):
    (tree[2] / "combined.json").unlink()
    result = run(tree)
    assert not result["accepted"] and "combined: missing receipt" in result["errors"]


def test_runtime_image_drift_is_not_a_common_environment(tree):
    tree[-1]["combined"]["image_id"] = "sha256:different"
    result = run(tree)
    assert not result["accepted"] and not result["capacity_runtime_image_consistent"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("allocator_conf", None),
        ("target", "fit:23GB"),
        ("script_args", ["--batch", "1"]),
    ],
)
def test_manifest_environment_and_target_drift_fails(tree, field, value):
    path = tree[1]
    data = json.loads(path.read_text())
    data["scenarios"][0][field] = value
    path.write_text(json.dumps(data))
    assert not run(tree)["accepted"]


@pytest.mark.parametrize(
    "relative",
    [
        "scenarios/s2_capacity_v2/train.py",
        "scenarios/s2_fp32_adamw_1b/train.py",
        "eval/mvp_phase1.yaml",
    ],
)
def test_current_or_historical_source_drift_fails(tree, relative):
    path = tree[0] / relative
    path.write_text(path.read_text() + "\n")
    assert not run(tree)["accepted"]


def test_classification_reference_digest_is_bound(tree):
    path = tree[3]
    path.write_text(path.read_text() + "\n")
    assert not run(tree)["accepted"]


def test_receipt_cannot_claim_another_preregistration(tree):
    path = tree[2] / "combined.json"
    data = json.loads(path.read_text())
    data["preregistration_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    assert not run(tree)["accepted"]


def test_runtime_environment_drift_is_not_accepted(tree):
    tree[-1]["combined"]["environment_sha256"] = "f" * 64
    result = run(tree)
    assert not result["accepted"] and not result["capacity_environment_consistent"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("original_failure_receipt_sha256", "0" * 64),
        ("supplement_reason", "threshold_override"),
        ("run_dir", "/different/run"),
    ],
)
def test_supplement_cannot_replace_original_failure_without_valid_linkage(tree, field, value):
    directory = tree[2]
    original = directory / "optimizer_only.json"
    source = json.loads(original.read_text())
    source.update(run_dir="/same/run", result_sha256="r" * 64)
    original.write_text(json.dumps(source))
    supplement = source | {
        "original_failure_receipt_sha256": digest(original),
        "supplement_reason": "snapshot_indentation_normalization",
    }
    supplement[field] = value
    (directory / "optimizer_only.supplement.json").write_text(json.dumps(supplement))
    assert not run(tree)["accepted"]
