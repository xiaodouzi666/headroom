"""Pure fixture regressions for host F821 stage attribution; no live execution."""

import copy
import json

import pytest

from headroom.diagnose import round_verification_feedback
from headroom.solver_context import (
    candidate_capture_counts,
    candidate_evidence,
    candidate_outcome_stage,
)

REJECTED = {
    "stage": "rejected_before_execution",
    "candidate_runtime_observed": False,
    "candidate_numerical_comparison": "unknown",
}


def owned_patch(tmp_path, *, status="failed", reason="NEW_UNDEFINED_NAME"):
    artifact = tmp_path / "rounds/01/patch-result.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"status": status, "reason": reason}))
    return artifact


def feedback(row, candidate):
    return round_verification_feedback(
        row,
        patch_status=candidate["status"] if candidate["patch_result_available"] else None,
        patch_reason=candidate["reason"] if candidate["patch_result_available"] else None,
        selected_result={
            "status": "oom",
            "steps": 20,
            "loss_series": [1.0] * 20,
            "run_id": "retained-baseline-only",
        },
        selected_round=None,
        selected_target_met=False,
    )


def capture():
    return {
        "completed": True,
        "checks": {"loss_series_comparison_available": True},
        "after": {
            "status": "completed",
            "protocol": "headroom.lab.v1",
            "pid": 123,
            "capture_complete": True,
            "execution_status": "completed",
            "loss_series": [1.0, 0.9],
        },
    }


def test_owned_host_f821_is_consistent_at_both_feedback_paths(tmp_path):
    owned_patch(tmp_path)
    row = {"number": 1, "decision": "revert", "reason": "other free-text reason"}
    original = copy.deepcopy(row)
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    result = feedback(row, candidate)
    assert candidate["patch_result_available"]
    assert candidate["outcome_stage"] == result["outcome_stage"] == REJECTED
    assert candidate["capture_counts"] == result["capture_counts"]
    assert result["capture_counts"]["backward_scalar_count"] is None
    assert result["candidate"] is None
    assert result["selected_after_round"]["status"] == "oom"
    assert row == original


@pytest.mark.parametrize("verification", [{}, capture(), False, "malformed", []])
def test_contradictory_or_malformed_verification_never_claims_no_execution(tmp_path, verification):
    owned_patch(tmp_path)
    row = {"number": 1, "verification": verification}
    original = copy.deepcopy(row)
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    result = feedback(row, candidate)
    assert candidate["outcome_stage"] == result["outcome_stage"]
    assert candidate["outcome_stage"] == {
        "stage": "inconsistent_patch_and_verification_evidence",
        "candidate_runtime_observed": None,
        "candidate_numerical_comparison": "unknown",
    }
    assert candidate["capture_counts"] == result["capture_counts"]
    assert result["capture_counts"]["backward_scalar_count"] is None
    assert row == original


@pytest.mark.parametrize(
    "reason",
    [
        None,
        "",
        "NAME_CHECK_UNAVAILABLE",
        "COMPILE_FAILED",
        "new_undefined_name",
        "NEW_UNDEFINED_NAME ",
        "NEW_UNDEFINED_NAME: missing",
        {"reason": "NEW_UNDEFINED_NAME"},
        ["NEW_UNDEFINED_NAME"],
    ],
)
def test_only_exact_host_reason_classifies_failed_result(tmp_path, reason):
    owned_patch(tmp_path, reason=reason)
    row = {
        "number": 1,
        "reason": "NEW_UNDEFINED_NAME",
        "failure": "The model says NEW_UNDEFINED_NAME",
    }
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    result = feedback(row, candidate)
    assert candidate["outcome_stage"] == result["outcome_stage"]
    assert candidate["outcome_stage"]["stage"] == "candidate_verification_unavailable"
    assert candidate["outcome_stage"]["candidate_runtime_observed"] is None


@pytest.mark.parametrize("status", [None, "", "failure", "failed ", ["failed"]])
def test_reason_without_exact_failed_status_is_not_proof(tmp_path, status):
    owned_patch(tmp_path, status=status)
    candidate = candidate_evidence(tmp_path, {"number": 1}, selected_round=None)
    assert candidate["outcome_stage"]["stage"] == "candidate_verification_unavailable"
    assert candidate["outcome_stage"]["candidate_runtime_observed"] is None


@pytest.mark.parametrize("kind", ["missing", "symlink", "malformed", "last_attempt_only"])
def test_missing_or_invalid_owned_evidence_cannot_borrow_row_reason(tmp_path, kind):
    row = {
        "number": 1,
        "status": "failed",
        "reason": "NEW_UNDEFINED_NAME",
        "candidate_evidence": {"status": "failed", "reason": "NEW_UNDEFINED_NAME"},
    }
    if kind != "missing":
        artifact = owned_patch(tmp_path)
        if kind == "symlink":
            target = tmp_path / "foreign.json"
            artifact.rename(target)
            artifact.symlink_to(target)
        elif kind == "malformed":
            artifact.write_text("{")
        else:
            artifact.write_text(
                json.dumps({"attempts": [{"status": "failed", "reason": "NEW_UNDEFINED_NAME"}]})
            )
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    result = feedback(row, candidate)
    assert result["outcome_stage"] == candidate["outcome_stage"]
    assert result["outcome_stage"]["candidate_runtime_observed"] is None
    direct = round_verification_feedback(
        row, selected_result={"status": "oom"}, selected_round=None, selected_target_met=False
    )
    assert direct["outcome_stage"]["candidate_runtime_observed"] is None


@pytest.mark.parametrize("reason", [None, "NEW_UNDEFINED_NAME", "OTHER"])
def test_existing_rejected_status_keeps_its_stage(reason):
    assert candidate_outcome_stage({}, patch_status="rejected", patch_reason=reason) == REJECTED
    result = candidate_outcome_stage(
        {"verification": capture()}, patch_status="rejected", patch_reason=reason
    )
    assert result["stage"] == "inconsistent_patch_and_verification_evidence"


def test_explicit_none_verification_is_absent_and_unknown_counts_stay_null():
    row = {"verification": None}
    assert (
        candidate_outcome_stage(row, patch_status="failed", patch_reason="NEW_UNDEFINED_NAME")
        == REJECTED
    )
    counts = candidate_capture_counts(row, patch_status="failed", patch_reason="NEW_UNDEFINED_NAME")
    assert counts["backward_scalar_count"] is None
    assert counts["logical_update_count"] is None


def test_unknown_failed_reason_does_not_erase_real_capture():
    value = candidate_outcome_stage(
        {"verification": capture()}, patch_status="failed", patch_reason="UNKNOWN"
    )
    assert value["stage"] == "candidate_execution_completed"
    assert value["candidate_runtime_observed"] is True
    assert value["candidate_numerical_comparison"] == "available"


def test_real_host_f821_never_reaches_verifier_and_both_solver_requests_agree(tmp_path):
    from test_orchestrator import search_run

    from headroom.config import ULTRA_MODEL

    bad = {"before": "VALUE = 1\n", "after": "VALUE = missing_name\n"}
    result, store, calls, verifies, _ = search_run(tmp_path, [bad, bad], max_rounds=2)
    try:
        assert not verifies and not result["target_met"]
        rounds = store.rounds(result["run_id"])
        assert len(rounds) == 2
        for row in rounds:
            candidate = row["candidate_evidence"]
            assert candidate["status"] == "failed"
            assert candidate["reason"] == "NEW_UNDEFINED_NAME"
            assert candidate["outcome_stage"] == REJECTED
            assert row["verification_feedback"]["outcome_stage"] == REJECTED

        seen = set()
        for call in calls:
            payload = json.loads(call["messages"][-1]["content"])
            context = (
                payload if "candidate_evidence" in payload else payload.get("evidence_context")
            )
            if not isinstance(context, dict) or not context.get("candidate_evidence"):
                continue
            candidate = context["candidate_evidence"][0]
            result_feedback = context["verification_feedback"][0]
            assert candidate["reason"] == "NEW_UNDEFINED_NAME"
            assert candidate["outcome_stage"] == result_feedback["outcome_stage"] == REJECTED
            assert candidate["capture_counts"] == result_feedback["capture_counts"]
            assert result_feedback["candidate"] is None
            seen.add("diagnose" if call["model"] == ULTRA_MODEL else "patcher")
        assert seen == {"diagnose", "patcher"}
    finally:
        store.close()
