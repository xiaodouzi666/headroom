"""Replay an actual availability rejection; correcting wording never clears unknowns."""

import copy
import json
from pathlib import Path

from test_diagnosis_bounded_repair import provider_client
from test_evidence_blockers import payload, request, source

from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.llm.router import LLMRouter

FIXTURE = Path(__file__).parent / "fixtures/r11_availability_feedback.json"


def checked(record):
    return validate_diagnosis(
        record["diagnosis"],
        evidence=record["evidence"],
        policy=record["policy"],
        required_saving_gb=record["required_saving_gb"],
    )


def test_real_rejection_identifies_reason_scalar_without_mutating_any_response():
    record = json.loads(FIXTURE.read_text())
    original = copy.deepcopy(record)
    result = checked(record)
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("EVIDENCE_AVAILABILITY_CONTRADICTED", "/evidence_requests/1")
    ]
    assert not result.valid and not result.ready_for_patch and result.diagnosis.needs_more_info
    feedback = json.loads(result.supplement_request.split("Errors: ", 1)[1])
    context = feedback["issues"][0]["request_context"]
    declaration = context["availability_declaration"]
    assert declaration["reason_field_path"] == "/evidence_requests/1/reason"
    assert declaration["declared_reason"] == "missing"
    assert declaration["evidence_ref"] == "source[0]"
    assert declaration["semantic_answer_supplied"] is False
    assert declaration["correcting_reason_resolves_prerequisite"] is False
    assert "missing feature inside visible source" in context["availability_contract"]
    assert "actual source objective" in context["availability_contract"]
    assert context["declared_reference_observation"]["visible_ranges"] == [[1, 175]]
    assert context["declared_reference_observation"]["runtime_values_verified"] is False
    assert record == original


def test_model_shaped_reason_correction_keeps_original_semantic_blocker_unready():
    record = json.loads(FIXTURE.read_text())
    original = copy.deepcopy(record)
    # This is a hypothetical model reply, not an operation performed by host code.
    record["diagnosis"]["evidence_requests"][1]["reason"] = "ambiguous"
    result = checked(record)
    assert result.valid and not result.ready_for_patch and result.diagnosis.needs_more_info
    assert result.diagnosis.plan[0].description == original["diagnosis"]["plan"][0]["description"]
    assert (
        result.diagnosis.evidence_requests[0].detail
        == original["diagnosis"]["evidence_requests"][0]["detail"]
    )
    assert "MSE" in result.diagnosis.plan[0].description
    assert "cross-entropy" in result.diagnosis.plan[0].description
    assert result.diagnosis.evidence_requests[1].reason == "ambiguous"


def test_sdk_repetition_does_not_add_a_third_call_or_weaken_the_host_rule():
    evidence, markdown = source()
    reply = payload()
    reply["evidence_requests"] = [
        request(
            field="streaming_helper_availability",
            reason="missing",
            detail="No equivalent streaming helper was identified in the visible source.",
            source_line_start=None,
            source_line_end=None,
        )
    ]
    original = copy.deepcopy(reply)
    requests = []
    with provider_client([reply], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={},
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
        assert len(client.ledger.entries) == len(requests) == 2
    assert not result.valid and not result.ready_for_patch and result.diagnosis.needs_more_info
    assert reply == original
    review = requests[1]["messages"][-1]["content"]
    assert "/evidence_requests/0/reason" in review
    assert "correcting_reason_resolves_prerequisite" in review
    assert all(item["max_tokens"] == 2000 for item in requests)
    assert all(item["chat_template_kwargs"] == {"enable_thinking": False} for item in requests)
