"""Real R8 contract failures replayed offline without forcing readiness."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_diagnosis_bounded_repair import provider_client
from test_evidence_blockers import payload, request, source

from headroom.diagnose import DiagnosisIssue, diagnose_with_router, validate_diagnosis
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.llm.router import LLMRouter
from headroom.schemas import Diagnosis
from headroom.validation_feedback import MAX_CONTEXT_BYTES, validation_issue_context

FIXTURE = Path(__file__).parent / "fixtures/r8_validation_feedback.json"


def records():
    return json.loads(FIXTURE.read_text())["records"]


def feedback(result):
    return json.loads(result.supplement_request.split("Errors: ", 1)[1])


@pytest.mark.parametrize("record", records(), ids=lambda value: value["case"])
def test_real_failed_request_gets_exact_context_without_mutation_or_readiness(record):
    saved = copy.deepcopy(record)
    result = validate_diagnosis(
        record["diagnosis"], evidence=record["evidence"], policy=record["policy"]
    )
    issue = record["original_issues"][0]
    assert not result.valid and not result.ready_for_patch and result.requires_supplement
    assert result.diagnosis.needs_more_info
    data = next(item for item in feedback(result)["issues"] if item["code"] == issue["code"])
    assert data["message"] == issue["message"]
    number = int(issue["path"].rsplit("/", 1)[1])
    context = data["request_context"]
    assert context["offending_evidence_request"] == record["diagnosis"]["evidence_requests"][number]
    assert context["current_plan_ids"] == [p["fix_id"] for p in record["diagnosis"]["plan"]]
    assert context["needs_more_info"] is True
    observation = context["declared_reference_observation"]
    assert observation["runtime_values_verified"] is False
    if record["case"] == "s1":
        assert "blocked_plan_ids=[]" in context["scope_contract"]
    elif record["case"] == "s2":
        assert observation["kind"] == "source"
        assert observation["visible_ranges"] == [[1, 175]]
        assert "advertised_unknown_runtime_reference" not in context
        assert "availability check verifies no runtime values" in context["availability_contract"]
        assert "does not negate separate scoped observations" in context["availability_contract"]
    else:
        assert observation["kind"] == "field"
        assert "must both be null" in context["range_contract"]
    assert len(json.dumps(feedback(result), ensure_ascii=True).encode()) <= 14000
    assert record == saved

    # A model-shaped response fixes only the contradictory declaration, not the
    # genuine missing evidence or the policy. The helper does not make this edit.
    corrected = copy.deepcopy(record["diagnosis"])
    request_value = corrected["evidence_requests"][number]
    if record["case"] == "s1":
        request_value["blocked_plan_ids"] = []
    elif record["case"] == "s2":
        request_value["reason"] = "ambiguous"
    else:
        request_value["source_line_start"] = request_value["source_line_end"] = None
    checked = validate_diagnosis(corrected, evidence=record["evidence"], policy=record["policy"])
    assert checked.valid
    assert checked.diagnosis.needs_more_info and not checked.ready_for_patch


@pytest.mark.parametrize("max_supplements,expected_calls", [(0, 1), (1, 2)])
def test_sdk_repeated_invalid_response_keeps_original_call_and_token_bounds(
    max_supplements, expected_calls
):
    evidence, markdown = source()
    reply = payload()
    reply["evidence_requests"] = [
        request(
            evidence_ref="execution_context.runtime_input_observations",
            field="runtime shape",
            reason="ambiguous",
        )
    ]
    requests = []
    with provider_client([reply], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={},
            max_supplements=max_supplements,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert len(requests) == expected_calls
    assert not result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    for sent in requests:
        assert sent["max_tokens"] == 2000
        assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    if expected_calls == 2:
        assert "must both be null" in requests[-1]["messages"][-1]["content"]


def test_valid_genuine_unknown_remains_blocked_after_shared_review():
    evidence, markdown = source()
    reply = payload()
    reply["evidence_requests"] = [
        request(
            evidence_ref="execution_context.runtime_input_observations",
            field="runtime shape",
            reason="missing",
            source_line_start=None,
            source_line_end=None,
        )
    ]
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
    assert len(requests) == 2
    assert result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    assert [item["purpose"] for item in result.response_request_modes] == [
        "initial",
        "prerequisite_review",
    ]


@pytest.mark.parametrize(
    "secret",
    [
        '{"password": "[synthetic-fixture-redacted]"}',
        "{'api_key': '[synthetic-fixture-redacted]'}",
        "NEBIUS_API_KEY=canary-never-echo",
        'password = "[synthetic-fixture-redacted]"',
        "access_token = '[synthetic-fixture-redacted]'",
        r"secret = \"[synthetic-fixture-redacted]\"",
    ],
)
def test_credentials_and_large_context_are_not_echoed(secret):
    data = payload()
    data["evidence_requests"] = [request(detail=secret)]
    diagnosis = Diagnosis.model_validate(data)
    issue = DiagnosisIssue("INVALID_EVIDENCE_RANGE", "Host rule", "/evidence_requests/0")
    value = validation_issue_context(issue, diagnosis, {})
    assert value["request_context"]["status"] == "withheld"
    assert secret not in json.dumps(value)
    assert "[synthetic-fixture-redacted]" not in json.dumps(value)

    data["evidence_requests"][0]["detail"] = "界" * 1024
    data["evidence_requests"][0]["blocked_plan_ids"] = ["界" * 160] * 16
    value = validation_issue_context(issue, Diagnosis.model_validate(data), {})
    assert value["request_context"]["status"] == "withheld"
    assert len(json.dumps(value).encode()) < MAX_CONTEXT_BYTES


def test_catalog_absence_and_bad_paths_never_invent_visibility_or_fail_validation():
    diagnosis = Diagnosis.model_validate(payload() | {"evidence_requests": [request()]})
    issue = DiagnosisIssue(
        "EVIDENCE_AVAILABILITY_CONTRADICTED", "Host rule", "/evidence_requests/0"
    )
    value = validation_issue_context(issue, diagnosis, {})
    assert "declared_reference_observation" not in value["request_context"]
    assert "advertised_unknown_runtime_reference" not in value["request_context"]
    assert "availability_contract" not in value["request_context"]
    for path in ("/evidence_requests/99", "/evidence_requests/-1", "/../secrets", None):
        result = validation_issue_context(
            SimpleNamespace(code=issue.code, message="rule", path=path), diagnosis, {}
        )
        assert len(json.dumps(result).encode()) < MAX_CONTEXT_BYTES
