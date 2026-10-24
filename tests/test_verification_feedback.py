"""Bounded recorded verification feedback through the real SDK mock transport."""

import copy
import json
from pathlib import Path

import pytest
from test_orchestrator import search_run

from headroom.diagnose import build_diagnosis_messages, round_verification_feedback


def summarize(row, *, selected=None, selected_round=None):
    return round_verification_feedback(
        row, selected_result=selected, selected_round=selected_round, selected_target_met=None
    )


def test_next_ultra_request_receives_rejected_verification_and_actual_retained_state(tmp_path):
    plans = [
        {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25, "ms": 110},
        {
            "before": "VALUE = 2\n",
            "after": "VALUE = 3\n",
            "peak": 20,
            "ms": 115,
            "loss": "changed",
            "checks": {"numerical_acceptance": False, "loss_tolerance": False, "same_inputs": None},
            "verification_extra": {
                "max_loss_delta": 0.125,
                "loss_tolerance": 0.001,
                "peak_before": 30.0,
                "peak_after": 20.0,
                "numerical_basis": "original_plan_full_backward_scalar_series",
                "snapshot": "RAW_SNAPSHOT_MUST_NOT_REACH_PROMPT",
            },
        },
        {"before": "VALUE = 2\n", "after": "VALUE = 4\n", "peak": 19, "ms": 120, "target": True},
    ]
    result, store, calls, _, _ = search_run(tmp_path, plans)
    try:
        assert result["target_met"]
        first = json.loads(calls[0]["messages"][-1]["content"])
        second = json.loads(calls[2]["messages"][-1]["content"])
        third = json.loads(calls[4]["messages"][-1]["content"])
        assert first["verification_feedback"] == []
        assert second["verification_feedback"][0]["candidate_selected"] is True
        failed = third["verification_feedback"][1]
        assert failed["fix_id"] == "f2" and failed["decision"] == "revert"
        assert failed["change"]["patch_artifact"].startswith("rounds/02/")
        assert failed["candidate"]["peak_allocated_bytes"] == 20_000_000_000
        assert failed["selected_after_round"]["peak_allocated_bytes"] == 25_000_000_000
        assert failed["selected_after_round"]["round"] == 1
        assert failed["candidate_selected"] is False
        verify = failed["verification"]
        assert verify["max_loss_delta"] == 0.125 and verify["loss_tolerance"] == 0.001
        assert verify["peak_after"] == 20.0
        assert {"numerical_acceptance", "loss_tolerance"} <= set(verify["failed_checks"])
        assert "same_inputs" in verify["unknown_checks"]
        assert "RAW_SNAPSHOT_MUST_NOT_REACH_PROMPT" not in json.dumps(third)
        assert failed["provenance"] == "offline_fixture"
        rows = store.rounds(result["run_id"])
        assert rows[1]["verification_feedback"] == failed
        assert rows[1]["verification"]["snapshot"] == "RAW_SNAPSHOT_MUST_NOT_REACH_PROMPT"
    finally:
        store.close()


def test_absent_verification_is_unknown_not_empty_pass():
    row = {
        "number": 1,
        "decision": "revert",
        "reason": "COMPILE_FAILED",
        "failure": "compile failed",
    }
    feedback = summarize(row)
    assert feedback["verification_available"] is False
    assert feedback["verification"] is None and feedback["candidate"] is None
    assert feedback["reason"] == "COMPILE_FAILED" and feedback["failure"] == "compile failed"
    assert feedback["selected_after_round"]["status"] is None
    assert feedback["selected_after_round"]["target_met"] is None
    assert feedback["candidate_selected"] is False


def test_feedback_limits_text_and_preserves_unknown_without_mutating_source():
    row = {
        "number": 2,
        "fix_id": "fix" * 100,
        "decision": "revert",
        "plan_step": {"title": "解释" * 1000},
        "verification": {
            "completed": "true",
            "peak_after": float("nan"),
            "max_loss_delta": None,
            "checks": {"passed": True, "failed": False, "unknown": None, "invalid": "true"},
            "notes": ["note" * 1000] * 20,
            "after": {"status": "error", "steps": None, "peak_allocated_bytes": None},
        },
    }
    original = copy.deepcopy(row)
    feedback = summarize(row)
    verification = feedback["verification"]
    assert verification["completed"] is None and verification["peak_after"] is None
    assert verification["max_loss_delta"] is None
    assert verification["failed_checks"] == ["failed"]
    assert verification["unknown_checks"] == ["unknown", "invalid"]
    assert len(verification["notes"]) == 8 and verification["notes_omitted"] == 12
    assert feedback["truncated_fields"]
    assert row["verification"]["notes"] == original["verification"]["notes"]
    assert row["fix_id"] == original["fix_id"]
    assert len(json.dumps([feedback] * 6, ensure_ascii=False).encode()) < 64_000


def test_feedback_is_bounded_at_diagnosis_request_boundary():
    with pytest.raises(ValueError, match="at most six"):
        build_diagnosis_messages(
            "evidence", goal="fix-oom", policy={}, verification_feedback=[{}] * 7
        )
    with pytest.raises(ValueError, match="bounded context"):
        build_diagnosis_messages(
            "evidence", goal="fix-oom", policy={}, verification_feedback=[{"text": "x" * 64_000}]
        )


def test_bounded_six_rounds_accumulate_feedback_without_extra_model_calls(tmp_path):
    plans = [
        {
            "before": f"VALUE = {index}\n",
            "after": f"VALUE = {index + 1}\n",
            "peak": 29 - index,
            "ms": 100,
            "target": True,
        }
        for index in range(1, 7)
    ]
    result, store, calls, verifies, _ = search_run(
        tmp_path, plans, max_rounds=6, search_mode="bounded_pareto"
    )
    try:
        assert len(verifies) == 6 and len(calls) == 12
        assert result["search"]["rounds_executed"] == 6
        for round_number, call in enumerate(calls[::2], 1):
            request = json.loads(call["messages"][-1]["content"])
            feedback = request["verification_feedback"]
            assert len(feedback) == round_number - 1
            if feedback:
                assert feedback[-1]["selected_after_round"]["round"] == round_number - 1
            assert len(json.dumps(feedback).encode()) < 20_000
    finally:
        store.close()


def test_annotation_bundle_return_enters_prompt_without_reusing_it_for_new_capture(
    tmp_path, monkeypatch
):
    calls_to_helper = []
    marker = "OFFLINE_NANO_OPINION_FROM_BASELINE_ONLY"

    def annotations(*args):
        return {"status": "completed", "complete": True, "annotations": []}

    def attach(bundle, labels, *, provenance):
        calls_to_helper.append((bundle, labels, provenance))
        destination = Path(bundle["evidence_md"]).with_name("annotated-evidence.md")
        destination.write_text(Path(bundle["evidence_md"]).read_text() + "\n" + marker)
        return {**bundle, "evidence_md": str(destination)}

    monkeypatch.setattr("headroom.orchestrator._optional_annotations", annotations)
    monkeypatch.setattr("headroom.orchestrator.annotate_evidence_bundle", attach)
    result, store, calls, _, _ = search_run(
        tmp_path,
        [
            {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25, "ms": 110},
            {
                "before": "VALUE = 2\n",
                "after": "VALUE = 3\n",
                "peak": 20,
                "ms": 115,
                "target": True,
            },
        ],
        max_rounds=2,
    )
    try:
        assert result["target_met"] and len(calls_to_helper) == 1
        first = json.loads(calls[0]["messages"][-1]["content"])["evidence_markdown"]
        second = json.loads(calls[2]["messages"][-1]["content"])["evidence_markdown"]
        assert marker in first and marker not in second
        assert "VALUE = 2" in second
        saved = json.loads(Path(result["report_json"]).read_text())
        assert saved["evidence"]["before"]["evidence_md"].endswith("annotated-evidence.md")
    finally:
        store.close()


def test_candidate_exception_reaches_next_request_without_raw_traceback(tmp_path):
    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "checks": {"candidate_completed_required_steps": False},
            "verification_extra": {"completed": False},
            "candidate_extra": {
                "status": "error",
                "reason": None,
                "error": "Candidate import failed",
                "exception": {
                    "type": "ModuleNotFoundError",
                    "message": "No module named optional_optimizer",
                },
                "oom": {
                    "requested_bytes": None,
                    "free_bytes": None,
                    "traceback": "DO_NOT_COPY_TRACEBACK",
                },
            },
        },
        {"before": "VALUE = 1\n", "after": "VALUE = 3\n", "peak": 20, "ms": 110, "target": True},
    ]
    result, store, calls, _, _ = search_run(tmp_path, plans, max_rounds=2)
    try:
        assert result["target_met"]
        request = json.loads(calls[2]["messages"][-1]["content"])
        rejected = request["verification_feedback"][0]
        assert rejected["candidate"]["status"] == "error"
        assert rejected["candidate"]["reason"] is None
        assert rejected["candidate"]["error"] == "Candidate import failed"
        assert rejected["candidate"]["exception"] == {
            "type": "ModuleNotFoundError",
            "message": "No module named optional_optimizer",
        }
        assert rejected["selected_after_round"]["basis"] == "original_baseline"
        assert rejected["selected_after_round"]["exception"]["type"] is None
        assert "DO_NOT_COPY_TRACEBACK" not in json.dumps(request)
    finally:
        store.close()
