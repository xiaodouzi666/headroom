"""Offline gate boundaries: no GPU/model calls and no historical-score mutation."""

import json
from pathlib import Path

import pytest

from headroom.acceptance.s2_calibration import (
    CASES,
    LIMIT,
    classify_result,
    control_source,
    prepare,
)

ROOT = Path(__file__).resolve().parents[1]


def good(peak=20_000_000_000):
    return (
        {
            "status": "completed",
            "steps": 20,
            "capture_complete": True,
            "cleanup_verified": True,
            "shared_gpu": False,
        },
        {
            "header": {
                "recorded_peak_allocated_bytes": peak,
                "peak_allocated_bytes": peak,
                "history_complete": True,
                "peak_is_exact": True,
            },
            "category_bytes": {"optimizer_state": 8_000_000_000},
        },
        {
            "observed_after_update": 19,
            "parameters_total": 1,
            "parameters_initialized": 1,
            "all_parameter_states_initialized": True,
            "moment_layout_valid": True,
            "cuda_moment_tensor_bytes": 8_000_000_000,
            "moment_tensor_bytes": 8_000_000_000,
        },
    )


def test_classification_exact_40pct_boundary_and_one_byte_failure():
    result, analysis, inventory = good()
    assert classify_result("classification", result, analysis, inventory)["passed"]
    analysis["header"]["recorded_peak_allocated_bytes"] += 1
    analysis["header"]["peak_allocated_bytes"] += 1
    assert not classify_result("classification", result, analysis, inventory)["passed"]


@pytest.mark.parametrize("case", CASES[1:-1])
def test_already_fit_is_invalid_for_capacity_baseline_and_isolated_controls(case):
    assert not classify_result(case, *good(LIMIT))["passed"]
    assert classify_result(case, *good(LIMIT + 1))["passed"]


def test_combined_control_boundary_never_counts_as_model_score():
    value = classify_result("combined", *good(LIMIT))
    assert value["passed"] and value["repair_score_eligible"] is False
    assert not classify_result("combined", *good(LIMIT + 1))["passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "oom"),
        ("status", "timeout"),
        ("steps", 19),
        ("capture_complete", False),
        ("cleanup_verified", False),
        ("shared_gpu", None),
    ],
)
def test_incomplete_run_cannot_calibrate(field, value):
    result, analysis, inventory = good()
    result[field] = value
    assert not classify_result("classification", result, analysis, inventory)["passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("all_parameter_states_initialized", False),
        ("parameters_initialized", 0),
        ("moment_layout_valid", False),
        ("observed_after_update", 18),
        ("observed_after_update", 21),
        ("cuda_moment_tensor_bytes", 0),
        ("moment_tensor_bytes", 8_000_000_004),
    ],
)
def test_name_or_partial_state_is_not_sufficient(field, value):
    result, analysis, inventory = good()
    inventory[field] = value
    assert not classify_result("classification", result, analysis, inventory)["passed"]


def test_missing_history_and_mismatched_tensor_category_fail():
    result, analysis, inventory = good()
    analysis["header"]["history_complete"] = False
    assert not classify_result("classification", result, analysis, inventory)["passed"]
    analysis["header"]["history_complete"] = True
    analysis["category_bytes"]["optimizer_state"] += 512
    assert not classify_result("classification", result, analysis, inventory)["passed"]


def test_controls_are_exact_source_edits_and_fail_closed():
    source = (ROOT / "scenarios/s2_capacity_v2/train.py").read_text()
    changed = control_source(source, optimizer=True, checkpoint=True)
    assert "foreach=False" in changed
    assert "use_reentrant=False" in changed
    assert "else 24" in changed and "(2048, 34, 128)" in changed
    with pytest.raises(ValueError):
        control_source(changed, optimizer=True, checkpoint=False)


def test_prepare_is_single_use_and_has_no_execution(tmp_path):
    directory = tmp_path / "calibration"
    plan = prepare(directory)
    assert plan["model_calls"] == 0 and plan["repair_score_eligible"] is False
    assert set(plan["source_pins"]) == set(CASES)
    assert not (directory / "lab").exists()
    assert json.loads((directory / "preregistration.json").read_text()) == plan
    with pytest.raises(FileExistsError):
        prepare(directory)


def test_new_manifest_preserves_nine_and_only_replaces_logical_s2():
    old = json.loads((ROOT / "eval/mvp_phase1.yaml").read_text())
    new = json.loads((ROOT / "eval/mvp_phase1_v2.yaml").read_text())
    assert len(old["scenarios"]) == len(new["scenarios"]) == 9

    def training_fields(rows):
        return [
            {k: v for k, v in row.items() if k not in {"numerical_reference", "notes"}}
            for row in rows
        ]

    assert training_fields(old["scenarios"][:1] + old["scenarios"][2:]) == training_fields(
        new["scenarios"][:1] + new["scenarios"][2:]
    )
    assert new["scenarios"][1]["target"] == "fit:22GB"
    assert new["scenarios"][1]["expected_baseline"] == "completed"
    assert not any("classification" in row["id"] for row in new["scenarios"])


def test_offline_execute_records_config_and_can_reuse_classification(tmp_path, monkeypatch):
    from headroom import evidence_analysis
    from headroom.acceptance.s2_calibration import execute_case
    from headroom.lab import runner

    result, analysis, inventory = good()
    seen = []
    monkeypatch.setattr(runner, "gpu_state", lambda: {"available": True, "processes": []})
    monkeypatch.setattr(evidence_analysis, "analyze_snapshot", lambda *args: analysis)

    def fake_lab(script, **kwargs):
        seen.append(kwargs)
        run_dir = Path(kwargs["run_root"]) / "offline-test"
        artifacts = run_dir / "artifacts"
        artifacts.mkdir(parents=True)
        (artifacts / "snapshot.json").write_text("{}")
        (run_dir / "stdout.log").write_text(
            json.dumps({"event": "step", "step": 19, "optimizer_inventory": inventory}) + "\n"
        )
        captured = result | {"run_dir": str(run_dir), "target_artifact_dir": str(artifacts)}
        (run_dir / "result.json").write_text(json.dumps(captured))
        return captured

    monkeypatch.setattr(runner, "run_script", fake_lab)
    first = tmp_path / "first"
    prepare(first)
    observed = execute_case(first, "classification")
    assert observed["passed"] and observed["optimizer_inventory"]["observed_after_update"] == 19
    with pytest.raises(FileExistsError):
        execute_case(first, "classification")

    second = tmp_path / "second"
    planned = prepare(
        second,
        allocator_conf="expandable_segments:True",
        classification_receipt=first / "classification.json",
    )
    assert planned["cases"] == list(CASES[1:]) and planned["max_runs"] == 4
    with pytest.raises(ValueError):
        execute_case(second, "classification")
    analysis["header"].update(
        recorded_peak_allocated_bytes=LIMIT + 1, peak_allocated_bytes=LIMIT + 1
    )
    capacity = execute_case(second, "capacity_baseline")
    assert capacity["passed"]
    assert seen[-1]["allocator_conf"] == "expandable_segments:True"
    assert seen[-1]["max_steps"] == 20 and seen[-1]["max_seconds"] == 180
    assert capacity["repair_score_eligible"] is False


def test_failed_previous_gate_blocks_next_dispatch(tmp_path, monkeypatch):
    from headroom.acceptance.s2_calibration import execute_case
    from headroom.lab import runner

    directory = tmp_path / "calibration"
    prepare(directory)
    (directory / "classification.json").write_text(json.dumps({"passed": False}))
    monkeypatch.setattr(runner, "run_script", lambda *a, **kw: pytest.fail("Must not dispatch"))
    with pytest.raises(ValueError, match="Previous calibration"):
        execute_case(directory, "capacity_baseline")
