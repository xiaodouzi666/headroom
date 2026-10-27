"""R5 draft only: canonical patch evidence reaches both solver boundaries.

Not run. Requires compat-atomic-stage.patch. Existing source/tests stay frozen.
"""

import copy

import pytest
from test_orchestrator import search_run
from test_solver_context import fixture_artifacts, request_payload

from headroom.diagnose import round_verification_feedback
from headroom.solver_context import candidate_evidence


def paired_feedback(root, row):
    candidate = candidate_evidence(root, row, selected_round=None)
    feedback = round_verification_feedback(
        row,
        patch_status=candidate["status"] if candidate["patch_result_available"] else None,
        selected_result={"run_id": "retained-only", "status": "oom", "steps": 0},
        selected_round=None,
        selected_target_met=False,
    )
    return candidate, feedback


def test_one_owned_rejection_has_same_stage_in_both_outbound_model_requests(tmp_path):
    bad = {"before": "VALUE = 1\n", "after": "VALUE = (\n"}
    result, store, calls, verifies, _ = search_run(tmp_path, [bad, bad], max_rounds=2)
    try:
        assert not verifies and not result["target_met"]
        ultra, patcher = request_payload(calls[5]), request_payload(calls[6])
        ultra_candidate = ultra["candidate_evidence"][0]
        ultra_feedback = ultra["verification_feedback"][0]
        assert ultra_candidate["outcome_stage"] == ultra_feedback["outcome_stage"]
        assert ultra_feedback["outcome_stage"]["stage"] == "rejected_before_execution"
        assert ultra_feedback["outcome_stage"]["candidate_runtime_observed"] is False
        assert ultra_feedback["candidate"] is None
        assert ultra_candidate == patcher["evidence_context"]["candidate_evidence"][0]
        assert ultra_feedback == patcher["evidence_context"]["verification_feedback"][0]
    finally:
        store.close()


def test_same_owned_patch_result_yields_same_candidate_and_feedback_stage(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    original = copy.deepcopy(row)
    candidate, feedback = paired_feedback(tmp_path, row)
    assert candidate["patch_result_available"]
    assert candidate["outcome_stage"] == feedback["outcome_stage"]
    assert feedback["outcome_stage"]["candidate_runtime_observed"] is False
    assert feedback["selected_after_round"]["status"] == "oom"
    assert feedback["candidate"] is None
    assert row == original


@pytest.mark.parametrize("reason", [None, "TRAINING_TRUNCATED", "candidate OOM"])
def test_missing_patch_bytes_stay_unknown_even_with_suggestive_reason(tmp_path, reason):
    row = {"number": 1, "reason": reason}
    candidate, feedback = paired_feedback(tmp_path, row)
    assert not candidate["patch_result_available"]
    assert candidate["outcome_stage"] == feedback["outcome_stage"]
    assert feedback["outcome_stage"]["candidate_runtime_observed"] is None
    assert feedback["outcome_stage"]["stage"] == "candidate_verification_unavailable"


def test_rejected_patch_plus_recorded_verification_is_inconsistent_not_not_run(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    row["verification"] = {
        "completed": True,
        "after": {
            "run_id": "candidate",
            "protocol": "headroom.lab.v1",
            "pid": 123,
            "capture_complete": True,
            "execution_status": "completed",
            "status": "completed",
        },
    }
    candidate, feedback = paired_feedback(tmp_path, row)
    assert candidate["outcome_stage"] == feedback["outcome_stage"]
    assert feedback["outcome_stage"]["stage"] == "inconsistent_patch_and_verification_evidence"
    assert feedback["outcome_stage"]["candidate_runtime_observed"] is None


def test_legacy_feedback_without_patch_evidence_stays_unknown(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    # The helper does not read artifact paths. Its caller must supply the
    # previously read owned patch status; a reason string is not a substitute.
    feedback = round_verification_feedback(
        row,
        selected_result={"status": "oom"},
        selected_round=None,
        selected_target_met=False,
    )
    assert feedback["outcome_stage"]["candidate_runtime_observed"] is None


def test_unsafe_owned_patch_artifact_does_not_create_known_stage(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    path = tmp_path / "rounds/01/patch-result.json"
    outside = tmp_path / "unowned-result.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    candidate, feedback = paired_feedback(tmp_path, row)
    assert not candidate["patch_result_available"]
    assert candidate["outcome_stage"] == feedback["outcome_stage"]
    assert feedback["outcome_stage"]["candidate_runtime_observed"] is None
