"""R5 draft only: measured candidate counts; no new validation gate.

Not executed. Requires candidate-capture-counts.patch plus its declared stage
dependency. Captured scalars can outnumber completed updates and include a
nonfinite-marker entry; these quantities do not establish numerical acceptance.
"""

import copy
import json

import pytest
from test_solver_context import fixture_artifacts

from headroom.diagnose import round_verification_feedback
from headroom.solver_context import candidate_capture_counts, candidate_evidence


def captured(*, loss_series=(123.456789, 2.5, 1.5), updates=1, complete=True):
    return {
        "number": 1,
        "verification": {
            "completed": complete,
            "checks": {
                "loss_series_aligned_to_updates": False,
                "numerical_acceptance": False,
            },
            "after": {
                "run_id": "candidate",
                "protocol": "headroom.lab.v1",
                "pid": 123,
                "capture_complete": complete,
                "execution_status": "completed" if complete else "oom",
                "status": "completed" if complete else "oom",
                "loss_series": list(loss_series),
                "steps": updates,
                "step_records": [{"step": index} for index in range(1, updates + 1)],
                "optimizer_update_observation": {
                    "protocol": "headroom.optimizer_updates.v1",
                    "logical_boundary_complete": True,
                    "logical_updates": updates,
                },
            },
        },
    }


def test_counts_are_distinct_quantities_and_do_not_leak_values_or_pass_gates():
    row = captured()
    original = copy.deepcopy(row)
    counts = candidate_capture_counts(row, patch_status="applied")
    assert counts["backward_scalar_count"] == 3
    assert counts["logical_update_count"] == 1
    assert counts["backward_scalar_scope"] == "finalized_capture"
    assert counts["logical_update_scope"] == "finalized_capture"
    assert "123.456789" not in json.dumps(counts)
    assert "numerical_acceptance" not in counts
    assert row == original


@pytest.mark.parametrize("complete", [False, True])
def test_measured_empty_sequences_are_zero_not_missing(complete):
    counts = candidate_capture_counts(captured(loss_series=(), updates=0, complete=complete))
    assert counts["backward_scalar_count"] == 0
    assert counts["logical_update_count"] == 0
    expected = "finalized_capture" if complete else "captured_prefix"
    assert counts["backward_scalar_scope"] == expected
    assert counts["logical_update_scope"] == expected


def test_partial_capture_counts_are_observed_prefix_not_completed_training():
    counts = candidate_capture_counts(captured(complete=False))
    assert counts["capture_complete"] is False
    assert counts["backward_scalar_count"] == 3
    assert counts["backward_scalar_scope"] == "captured_prefix"


@pytest.mark.parametrize("value", [None, "3", [True], ["1.0"], [float("inf")]])
def test_missing_or_malformed_scalar_sequence_is_unknown_not_zero(value):
    row = captured()
    row["verification"]["after"]["loss_series"] = value
    counts = candidate_capture_counts(row)
    assert counts["backward_scalar_count"] is None
    assert counts["backward_scalar_scope"] == "unavailable"
    assert counts["logical_update_count"] == 1


def test_absent_scalar_key_is_unknown_but_explicit_nonfinite_marker_is_recorded_entry():
    row = captured()
    del row["verification"]["after"]["loss_series"]
    assert candidate_capture_counts(row)["backward_scalar_count"] is None
    row["verification"]["after"]["loss_series"] = [None]
    # None is how the real hook records a scalar rejected for nonfiniteness.
    # Counting the observation must not imply a finite or usable loss.
    counts = candidate_capture_counts(row)
    assert counts["backward_scalar_count"] == 1
    assert row["verification"]["checks"]["numerical_acceptance"] is False


@pytest.mark.parametrize(
    "row",
    [
        {"number": 1},
        {"number": 1, "verification": {"after": {"run_id": "allocated", "status": "error"}}},
        {"number": 1, "verification": {"after": {"execution": {"status": "completed"}}}},
    ],
)
def test_run_id_status_or_execution_dictionary_does_not_establish_capture(row):
    counts = candidate_capture_counts(row)
    assert counts["capture_complete"] is None
    assert counts["backward_scalar_count"] is None
    assert counts["logical_update_count"] is None


@pytest.mark.parametrize(
    "reason", ["GPU_BUSY", "GPU_UNAVAILABLE", "PREPARATION_FAILED", "CONTAINER_CREATE_FAILED"]
)
def test_preparation_failure_with_capture_claim_is_unknown(reason):
    row = captured()
    row["verification"]["after"]["reason"] = reason
    counts = candidate_capture_counts(row)
    assert counts["backward_scalar_count"] is None
    assert counts["logical_update_count"] is None


def test_rejected_patch_contradicting_capture_does_not_expose_measured_counts():
    counts = candidate_capture_counts(captured(), patch_status="rejected")
    assert counts["backward_scalar_count"] is None
    assert counts["logical_update_count"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"steps": True},
        {"steps": 2},
        {"step_records": []},
        {"step_records": [{"step": True}]},
        {"step_records": [{"step": 2}]},
        {"optimizer_update_observation": {}},
        {
            "optimizer_update_observation": {
                "protocol": "headroom.optimizer_updates.v1",
                "logical_boundary_complete": False,
                "logical_updates": 1,
            }
        },
        {
            "optimizer_update_observation": {
                "protocol": "headroom.optimizer_updates.v1",
                "logical_boundary_complete": True,
                "logical_updates": True,
            }
        },
    ],
)
def test_incomplete_or_inconsistent_update_measurements_remain_unknown(change):
    row = captured()
    row["verification"]["after"].update(change)
    counts = candidate_capture_counts(row)
    assert counts["logical_update_count"] is None
    assert counts["logical_update_scope"] == "unavailable"
    assert counts["backward_scalar_count"] == 3


def test_owned_status_supplies_identical_counts_to_feedback_and_candidate_context(tmp_path):
    metadata, _ = fixture_artifacts(tmp_path)
    path = tmp_path / "rounds/01/patch-result.json"
    document = json.loads(path.read_text())
    document["status"] = "applied"
    path.write_text(json.dumps(document))
    row = {**metadata, **captured()}
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    feedback = round_verification_feedback(
        row,
        patch_status=candidate["status"] if candidate["patch_result_available"] else None,
        selected_result={"status": "oom", "loss_series": [999.0] * 50},
        selected_round=None,
        selected_target_met=False,
    )
    assert candidate["capture_counts"] == feedback["capture_counts"]
    assert feedback["capture_counts"]["backward_scalar_count"] == 3
    assert feedback["capture_counts"]["logical_update_count"] == 1
    assert "999" not in json.dumps(feedback["capture_counts"])
