"""Bound the 2k request, never trim a response or bypass diagnosis validation."""

import copy

import pytest
from jsonschema import Draft202012Validator
from test_diagnosis_bounded_repair import evidence, payload, provider_client

from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.diagnosis_protocol import (
    COMPACT_DIAGNOSIS_INSTRUCTIONS,
    FINAL48_DIAGNOSIS_ONLY,
    compact_diagnosis_schema,
    diagnosis_prompt,
)
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.llm.router import LLMRouter


def test_only_explicit_bounded_request_gets_compact_schema_and_original_is_immutable():
    original = build_diagnosis_schema(evidence=evidence(), policy={})
    before = copy.deepcopy(original)
    assert compact_diagnosis_schema(original) is original
    compact = compact_diagnosis_schema(original, request_policy=FINAL48_DIAGNOSIS_ONLY)
    Draft202012Validator.check_schema(compact)
    assert original == before
    assert compact["properties"]["plan"]["maxItems"] == 1
    assert compact["properties"]["root_causes"]["maxItems"] == 2
    assert compact["properties"]["evidence_requests"]["maxItems"] == 2
    assert compact["properties"]["notes"]["maxItems"] == 3
    assert compact["$defs"]["RootCause"]["properties"]["evidence_refs"]["maxItems"] == 4
    assert compact["required"] == original["required"]
    assert compact["additionalProperties"] is False
    Draft202012Validator(compact).validate(payload())


def test_bounded_instructions_are_explicit_and_other_protocols_keep_original_prompt():
    template = "Cap: {{HEADROOM_DIAGNOSIS_COMPLETION_CAP}}"
    assert diagnosis_prompt(template) == "Cap: 16384"
    assert diagnosis_prompt(template, "common-diagnosis-4000-v1") == "Cap: 4000"
    bounded = diagnosis_prompt(template, request_policy=FINAL48_DIAGNOSIS_ONLY)
    assert bounded.startswith(COMPACT_DIAGNOSIS_INSTRUCTIONS)
    assert bounded.endswith("Cap: 2000")
    assert "EVERY genuine unresolved prerequisite" in bounded
    assert "retain needs_more_info=true" in bounded
    assert "the dependency list is incomplete" in bounded


def test_schema_rejects_excess_plan_without_mutating_response_and_reuses_only_one_call():
    first = payload()
    first["plan"].append(dict(first["plan"][0], fix_id="other"))
    original = copy.deepcopy(first)
    requests = []
    with provider_client([first, payload()], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            "Measured stacks and source",
            evidence=evidence(),
            goal="reclaim",
            policy={},
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
        assert len(client.ledger.entries) == 2
    assert len(requests) == 2
    assert first == original and len(first["plan"]) == 2
    assert result.ready_for_patch
    assert all(request["max_tokens"] == 2000 for request in requests)
    assert all(
        request["chat_template_kwargs"] == {"enable_thinking": False} for request in requests
    )
    assert requests[0]["response_format"] == requests[1]["response_format"]
    schema = requests[0]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["plan"]["maxItems"] == 1
    assert "JSON_SCHEMA_MISMATCH" in requests[1]["messages"][-1]["content"]


def test_compact_shape_does_not_allow_forbidden_precision():
    answer = payload()
    answer["plan"][0]["description"] = "Switch the source computation to bf16."
    schema = compact_diagnosis_schema(
        build_diagnosis_schema(evidence=evidence(), policy={}),
        request_policy=FINAL48_DIAGNOSIS_ONLY,
    )
    Draft202012Validator(schema).validate(answer)
    checked = validate_diagnosis(answer, evidence=evidence(), policy={})
    assert not checked.ready_for_patch
    assert "NUMERICS_CHANGE_FORBIDDEN" in {issue.code for issue in checked.issues}


def test_real_blockers_remain_blockers_even_without_a_candidate():
    answer = payload()
    answer.update(
        needs_more_info=True,
        plan=[],
        evidence_requests=[
            {
                "field": "target.loss_contract",
                "reason": "missing",
                "detail": "Reduction weighting and cross-sample coupling are unresolved.",
                "blocking_scope": "overall_feasibility",
                "blocked_plan_ids": [],
            }
        ],
    )
    schema = compact_diagnosis_schema(
        build_diagnosis_schema(evidence=evidence(), policy={}),
        request_policy=FINAL48_DIAGNOSIS_ONLY,
    )
    Draft202012Validator(schema).validate(answer)
    checked = validate_diagnosis(answer, evidence=evidence(), policy={})
    assert checked.valid and not checked.ready_for_patch
    assert checked.diagnosis.needs_more_info
    assert checked.diagnosis.evidence_requests[0].detail == answer["evidence_requests"][0]["detail"]


def test_compact_builder_fails_closed_for_unrecognized_schema():
    with pytest.raises(ValueError, match="Unsupported diagnosis schema"):
        compact_diagnosis_schema({}, request_policy=FINAL48_DIAGNOSIS_ONLY)
