"""Offline shared-supplement replanning; unknowns never become host readiness."""

import copy
import json

import pytest
from test_diagnosis_bounded_repair import payload, provider_client
from test_evidence_blockers import source

from headroom.budget import BudgetExceeded
from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.prerequisite_review import MAX_REVIEW_BYTES, prerequisite_review
from headroom.schemas import Diagnosis


def blocked():
    reply = payload()
    reply.update(
        needs_more_info=True,
        evidence_requests=[
            {
                "field": "original loss weighting",
                "reason": "ambiguous",
                "detail": "This strategy needs the original weighting and update boundary.",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": ["fix"],
            }
        ],
    )
    return reply


def invoke(replies, *, limit=1):
    requests = []
    evidence, markdown = source()
    original = copy.deepcopy(evidence)
    with provider_client(replies, requests) as sdk:
        result = diagnose_with_router(
            LLMRouter(sdk),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={},
            required_saving_gb=0.5,
            max_supplements=limit,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
        assert len(sdk.ledger.entries) == len(requests)
    assert evidence == original
    return result, requests


def test_model_can_replace_strategy_but_full_validator_decides_readiness():
    first = blocked()
    before = copy.deepcopy(first)
    second = payload()
    second["plan"][0].update(
        fix_id="independent",
        title="Release unused retained temporary",
        description="Release a temporary only after its final consuming operation.",
    )
    result, requests = invoke([first, second])
    assert result.ready_for_patch and len(requests) == 2
    assert result.diagnosis.plan[0].fix_id == "independent"
    assert first == before and first["needs_more_info"] is True
    assert [item["purpose"] for item in result.response_request_modes] == [
        "initial",
        "prerequisite_review",
    ]
    followup = requests[1]["messages"]
    assert [item["role"] for item in followup] == [
        *[item["role"] for item in requests[0]["messages"]],
        "user",
    ]
    assert followup[:-1] == requests[0]["messages"]
    review = followup[-1]["content"]
    assert "No new measurement or missing fact" in review
    assert "abandon an inapplicable or blocked strategy" in review
    data = json.loads(review.split("Prior prerequisite metadata: ", 1)[1])
    assert data["new_runtime_evidence_supplied"] is False
    entry = data["requests"][0]["declared_reference_observation"]
    assert entry["availability"] == "unsupported" and entry["runtime_values_verified"] is False
    assert all(request["max_tokens"] == 2000 for request in requests)
    assert all(
        request["chat_template_kwargs"] == {"enable_thinking": False} for request in requests
    )
    assert requests[0]["response_format"] == requests[1]["response_format"]


@pytest.mark.parametrize("limit,expected_calls", [(0, 1), (1, 2), (3, 2)])
def test_genuine_unknown_stays_blocked_after_at_most_one_review(limit, expected_calls):
    reply = blocked()
    result, requests = invoke([reply], limit=limit)
    assert len(requests) == expected_calls
    assert result.valid and result.diagnosis.needs_more_info and not result.ready_for_patch
    assert result.diagnosis.evidence_requests[0].detail == reply["evidence_requests"][0]["detail"]


def test_policy_repair_and_review_spend_the_same_allowance():
    invalid = payload()
    invalid["plan"][0]["title"] = "Switch to bf16"
    result, requests = invoke([invalid, blocked()])
    assert len(requests) == 2
    assert result.valid and result.diagnosis.needs_more_info and not result.ready_for_patch
    assert [item["purpose"] for item in result.response_request_modes] == [
        "initial",
        "validation_repair",
    ]


@pytest.mark.parametrize("mutation", ["policy", "known_saving"])
def test_replanning_cannot_bypass_original_checks(mutation):
    reply = payload()
    if mutation == "policy":
        reply["plan"][0]["title"] = "Switch to bf16"
        expected = "NUMERICS_CHANGE_FORBIDDEN"
    elif mutation == "known_saving":
        reply["plan"][0]["expected_saving_gb"] = 0.1
        expected = "INSUFFICIENT_EXPECTED_SAVING"
    result, requests = invoke([blocked(), reply])
    assert len(requests) == 2 and not result.ready_for_patch and not result.valid
    assert expected in {issue.code for issue in result.issues}


@pytest.mark.parametrize("mutation", ["ready", "no_plan", "legacy", "withheld"])
def test_no_review_for_ready_absent_plan_or_unstructured_unsafe_request(mutation):
    reply = blocked()
    if mutation == "ready":
        reply = payload()
    elif mutation == "no_plan":
        reply["plan"] = []
        reply["evidence_requests"][0].update(
            blocking_scope="overall_feasibility", blocked_plan_ids=[]
        )
    elif mutation == "legacy":
        reply["evidence_requests"] = [{"field": "loss", "reason": "ambiguous", "detail": "Unknown"}]
    else:
        reply["evidence_requests"][0]["detail"] = "password = synthetic-fixture-only"
    result, requests = invoke([reply])
    assert len(requests) == 1
    assert result.ready_for_patch is (mutation == "ready")
    if mutation != "ready":
        assert result.diagnosis.needs_more_info


def test_review_metadata_bounded_without_source_content_or_new_runtime_values():
    reply = blocked()
    reply["evidence_requests"] = [
        dict(reply["evidence_requests"][0], detail="A" * 900, field=f"unresolved requirement {i}")
        for i in range(16)
    ]
    evidence, _ = source(lines=("private_source_canary = 42", "pass"))
    diagnosis = Diagnosis.model_validate(reply)
    before = diagnosis.model_dump()
    review = prerequisite_review(diagnosis, evidence)
    assert review is not None and len(review.encode()) <= MAX_REVIEW_BYTES
    assert "private_source_canary" not in review
    data = json.loads(review.split("Prior prerequisite metadata: ", 1)[1])
    assert len(data["requests"]) <= 4 and data["omitted_requests"] > 0
    assert diagnosis.model_dump() == before


def test_replan_schema_reference_rejection_still_raises_at_shared_limit():
    reply = payload()
    reply["root_causes"][0]["evidence_refs"] = ["not_a_measured_stack"]
    requests = []
    evidence, markdown = source()
    with provider_client([blocked(), reply], requests) as sdk:
        with pytest.raises(ResponseValidationError) as caught:
            diagnose_with_router(
                LLMRouter(sdk),
                markdown,
                evidence=evidence,
                goal="reclaim",
                policy={},
                max_supplements=1,
                request_policy=FINAL48_DIAGNOSIS_ONLY,
            )
        assert caught.value.reason == "schema_mismatch"
        assert len(sdk.ledger.entries) == len(requests) == 2


def test_denied_budget_for_review_never_dispatches_or_bypasses_admission(monkeypatch):
    requests = []
    admissions = []
    evidence, markdown = source()
    with provider_client([blocked(), payload()], requests) as sdk:

        def admit(*args):
            admissions.append(True)
            if len(admissions) > 1:
                raise BudgetExceeded("Offline shared-pool admission denied")

        monkeypatch.setattr(sdk, "_before_attempt", admit)
        with pytest.raises(BudgetExceeded):
            diagnose_with_router(
                LLMRouter(sdk),
                markdown,
                evidence=evidence,
                goal="reclaim",
                policy={},
                max_supplements=1,
                request_policy=FINAL48_DIAGNOSIS_ONLY,
            )
        assert len(admissions) == 2
        assert len(requests) == len(sdk.ledger.entries) == 1
