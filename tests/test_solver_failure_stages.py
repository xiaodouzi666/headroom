"""Offline regressions for candidate/baseline failure attribution."""

import copy
import json

import pytest
from test_orchestrator import search_run
from test_solver_context import fixture_artifacts, request_payload

from headroom.diagnose import round_verification_feedback
from headroom.solver_context import candidate_evidence, candidate_outcome_stage


def test_static_rejection_and_retained_oom_remain_distinct_at_both_solver_boundaries(tmp_path):
    bad = {"before": "VALUE = 1\n", "after": "VALUE = (\n"}
    result, store, calls, verifies, _ = search_run(tmp_path, [bad, bad], max_rounds=2)
    try:
        assert not verifies and not result["target_met"]
        ultra, patcher = request_payload(calls[5]), request_payload(calls[6])
        candidate = ultra["candidate_evidence"][0]
        assert candidate == patcher["evidence_context"]["candidate_evidence"][0]
        assert candidate["outcome_stage"] == {
            "stage": "rejected_before_execution",
            "candidate_runtime_observed": False,
            "candidate_numerical_comparison": "unknown",
        }
        feedback = ultra["verification_feedback"][0]
        assert feedback == patcher["evidence_context"]["verification_feedback"][0]
        assert feedback["candidate"] is None
        assert feedback["outcome_stage"] == candidate["outcome_stage"]
        # No fictitious candidate OOM or numerical failure may be synthesized from retained state.
        row = store.rounds(result["run_id"])[0]
        retained = {"run_id": "baseline-oom", "status": "oom", "steps": 0}
        replay = round_verification_feedback(
            row, selected_result=retained, selected_round=None, selected_target_met=False
        )
        assert replay["selected_after_round"]["status"] == "oom"
        assert replay["candidate"] is None
        assert replay["outcome_stage"]["candidate_runtime_observed"] is None
        assert replay["outcome_stage"]["candidate_numerical_comparison"] == "unknown"
    finally:
        store.close()


def test_missing_patch_artifact_cannot_assert_candidate_was_not_executed(tmp_path):
    value = candidate_evidence(tmp_path, {"number": 1}, selected_round=None)
    assert value["outcome_stage"]["candidate_runtime_observed"] is None
    assert value["outcome_stage"]["stage"] == "candidate_verification_unavailable"


@pytest.mark.parametrize("status", ["oom", "error", "timeout"])
def test_recorded_runtime_failure_does_not_become_measured_numerical_disagreement(status):
    row = {
        "verification": {
            "completed": False,
            "after": {
                "run_id": "candidate",
                "status": status,
                "protocol": "headroom.lab.v1",
                "pid": 123,
                "capture_complete": True,
                "execution_status": status,
            },
            "checks": {
                "loss_series_comparison_available": False,
                "numerical_acceptance": False,
                "loss_tolerance": False,
            },
            "loss_equivalence": "n/a",
        }
    }
    original = copy.deepcopy(row)
    value = candidate_outcome_stage(row)
    assert value["stage"] == "candidate_execution_failed"
    assert value["candidate_runtime_observed"] is True
    assert value["candidate_numerical_comparison"] == "unavailable"
    assert row == original


def test_completed_measured_numerical_failure_keeps_available_comparison():
    row = {
        "verification": {
            "completed": True,
            "after": {
                "status": "completed",
                "protocol": "headroom.lab.v1",
                "pid": 123,
                "capture_complete": True,
                "execution_status": "completed",
            },
            "checks": {"loss_series_comparison_available": True, "numerical_acceptance": False},
            "loss_equivalence": "changed",
        }
    }
    value = candidate_outcome_stage(row)
    assert value["stage"] == "candidate_execution_completed"
    assert value["candidate_numerical_comparison"] == "available"
    assert row["verification"]["checks"]["numerical_acceptance"] is False


def test_inconsistent_patch_and_verification_is_unknown_not_preexecution_claim(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    row["verification"] = {"completed": True, "after": {"status": "completed"}}
    value = candidate_evidence(tmp_path, row, selected_round=None)
    assert value["outcome_stage"]["stage"] == "inconsistent_patch_and_verification_evidence"
    assert value["outcome_stage"]["candidate_runtime_observed"] is None


def test_malformed_observation_cannot_create_execution_or_comparison_fact():
    row = {
        "verification": {
            "completed": "true",
            "after": {"run_id": "", "status": {"untrusted": "completed"}},
            "checks": {"loss_series_comparison_available": "true"},
        }
    }
    value = candidate_outcome_stage(row)
    assert value["candidate_runtime_observed"] is None
    assert value["candidate_numerical_comparison"] == "unknown"
    assert len(json.dumps(value)) < 300


def test_applied_patch_without_verification_remains_unknown():
    value = candidate_outcome_stage({"number": 1}, patch_status="applied")
    assert value["stage"] == "patch_applied_verification_unavailable"
    assert value["candidate_runtime_observed"] is None


@pytest.mark.parametrize(
    "reason",
    [
        "GPU_BUSY",
        "GPU_UNAVAILABLE",
        "PREPARATION_FAILED",
        "CONTAINER_CREATE_FAILED",
    ],
)
def test_runner_preparation_failure_is_not_candidate_execution(reason):
    row = {
        "verification": {
            "completed": False,
            "after": {"run_id": "allocated-before-launch", "status": "error", "reason": reason},
        }
    }
    value = candidate_outcome_stage(row)
    assert value["candidate_runtime_observed"] is None
    assert value["stage"] == "runner_failure_without_target_capture"
    assert value["candidate_numerical_comparison"] == "unknown"


@pytest.mark.parametrize(
    "after",
    [
        {"run_id": "allocated-before-launch"},
        {"run_id": "allocated-before-launch", "status": "error"},
        {"status": "timeout"},
        {"status": "completed"},
        {"execution": {}},
        {"execution": {"timed_out": False, "returncode": None}},
        {"execution": {"state": {"Running": True}}},
        {"protocol": "headroom.lab.v1", "capture_complete": True},
        {
            "protocol": "headroom.lab.v1",
            "pid": True,
            "capture_complete": True,
            "execution_status": "completed",
        },
        {
            "protocol": "headroom.lab.v1",
            "pid": 123,
            "capture_complete": "true",
            "execution_status": "completed",
        },
    ],
)
def test_identifiers_status_and_container_metadata_do_not_prove_target_capture(after):
    value = candidate_outcome_stage({"verification": {"after": after}})
    assert value["candidate_runtime_observed"] is None
    assert value["stage"] == "verification_without_candidate_execution_evidence"


def test_nested_container_creation_failure_remains_unknown_even_if_host_reason_overwritten():
    after = {
        "status": "error",
        "reason": "CONTAINER_CLEANUP_UNVERIFIED",
        "execution": {"error": "CONTAINER_CREATE_FAILED", "returncode": 1},
    }
    value = candidate_outcome_stage({"verification": {"after": after}})
    assert value["candidate_runtime_observed"] is None
    assert value["stage"] == "runner_failure_without_target_capture"


def test_conflicting_preparation_and_capture_fields_are_not_promoted_to_execution():
    after = {
        "status": "error",
        "reason": "PREPARATION_FAILED",
        "protocol": "headroom.lab.v1",
        "pid": 123,
        "capture_complete": True,
        "execution_status": "completed",
    }
    value = candidate_outcome_stage({"verification": {"after": after}})
    assert value["candidate_runtime_observed"] is None
    assert value["stage"] == "inconsistent_preparation_and_capture_evidence"


def test_incomplete_target_capture_still_records_observed_target_failure():
    after = {
        "status": "timeout",
        "protocol": "headroom.lab.v1",
        "pid": 123,
        "capture_complete": False,
        "execution_status": "timeout",
    }
    value = candidate_outcome_stage({"verification": {"after": after, "completed": False}})
    assert value["candidate_runtime_observed"] is True
    assert value["stage"] == "candidate_execution_failed"
