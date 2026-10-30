"""Offline shared-supplement replanning; unknowns never become host readiness."""

import copy
import json

import pytest
from test_diagnosis_bounded_repair import payload, provider_client
from test_evidence_blockers import source

from headroom.budget import BudgetExceeded
from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.evidence_blockers import validate_evidence_requests
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


def invoke(replies, *, limit=1, goal="reclaim", required_saving_gb=0.5):
    requests = []
    evidence, markdown = source()
    original = copy.deepcopy(evidence)
    with provider_client(replies, requests) as sdk:
        result = diagnose_with_router(
            LLMRouter(sdk),
            markdown,
            evidence=evidence,
            goal=goal,
            policy={},
            required_saving_gb=required_saving_gb,
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
    entry = data["prior_requests"][0]["declared_reference_observation"]
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


@pytest.mark.parametrize("mutation", ["ready", "no_plan", "withheld"])
def test_no_review_for_ready_absent_plan_or_withheld_scoped_request(mutation):
    reply = blocked()
    if mutation == "ready":
        reply = payload()
    elif mutation == "no_plan":
        reply["plan"] = []
        reply["evidence_requests"][0].update(
            blocking_scope="overall_feasibility", blocked_plan_ids=[]
        )
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
    assert len(data["prior_requests"]) <= 4 and data["omitted_prior_requests"] > 0
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


def unlocatable(kind):
    reply = blocked()
    if kind == "empty":
        reply["evidence_requests"] = []
    elif kind == "legacy":
        reply["evidence_requests"] = [
            {
                "field": "loss",
                "reason": "ambiguous",
                "detail": "unsafe_question_canary password=do-not-copy",
            }
        ]
    else:
        reply["evidence_requests"][0].update(
            field="required_saving_gb",
            reason="missing",
            detail="unsafe_question_canary password=do-not-copy",
            evidence_ref=None,
            blocking_scope="overall_feasibility",
            blocked_plan_ids=[],
        )
    reply["notes"] = ["unsafe_notes_canary password=do-not-copy"]
    return reply


@pytest.mark.parametrize("kind", ["empty", "required_saving_null", "legacy"])
def test_neutral_review_for_empty_or_unlocatable_requests_never_copies_unsafe_text(kind):
    reply = unlocatable(kind)
    diagnosis = Diagnosis.model_validate(reply)
    before = diagnosis.model_dump()
    evidence, _ = source(lines=("source_bytes_canary = 1", "pass"))
    review = prerequisite_review(diagnosis, evidence)
    assert review is not None
    assert len(review.encode()) <= MAX_REVIEW_BYTES
    assert "unsafe_question_canary" not in review
    assert "unsafe_notes_canary" not in review
    assert "source_bytes_canary" not in review
    assert "password=" not in review
    data = json.loads(review.split("Prior prerequisite metadata: ", 1)[1])
    assert data["prior_request_context_status"] == "none_locatable"
    assert data["prior_needs_more_info"] is True
    assert data["new_runtime_evidence_supplied"] is False
    assert data["prior_requests"] == []
    assert data["omitted_prior_requests"] == len(reply["evidence_requests"])
    assert diagnosis.model_dump() == before


@pytest.mark.parametrize("kind", ["empty", "required_saving_null"])
@pytest.mark.parametrize("limit,expected_calls", [(0, 1), (1, 2), (3, 2)])
def test_real_unknown_stays_blocked_after_neutral_review_with_shared_limit(
    kind, limit, expected_calls
):
    reply = unlocatable(kind)
    result, requests = invoke([reply], limit=limit, goal="fix-oom", required_saving_gb=None)
    assert len(requests) == expected_calls
    assert result.valid and result.diagnosis.needs_more_info and not result.ready_for_patch
    assert result.diagnosis.evidence_requests == Diagnosis.model_validate(reply).evidence_requests
    if expected_calls == 2:
        assert requests[1]["messages"][:-1] == requests[0]["messages"]
        assert result.response_request_modes[-1]["purpose"] == "prerequisite_review"
        assert "unconfigured numerical savings threshold" in requests[1]["messages"][-1]["content"]


@pytest.mark.parametrize("kind", ["empty", "required_saving_null"])
def test_model_can_independently_replace_unlocatable_blocker_but_host_never_clears_it(kind):
    first = unlocatable(kind)
    before = copy.deepcopy(first)
    result, requests = invoke([first, payload()], goal="fix-oom", required_saving_gb=None)
    assert len(requests) == 2
    assert result.ready_for_patch and result.valid
    assert first == before and first["needs_more_info"] is True
    assert result.response_request_modes[-1]["purpose"] == "prerequisite_review"
    initial = json.loads(requests[0]["messages"][-1]["content"])
    assert initial["goal"] == "fix-oom" and initial["required_saving_gb"] is None


def test_neutral_review_cannot_add_a_call_after_existing_validation_supplement():
    invalid = payload()
    invalid["plan"][0]["title"] = "Switch to bf16"
    result, requests = invoke([invalid, unlocatable("empty")])
    assert len(requests) == 2
    assert result.valid and result.diagnosis.needs_more_info and not result.ready_for_patch
    assert [item["purpose"] for item in result.response_request_modes] == [
        "initial",
        "validation_repair",
    ]


# Exact dependency fields and plan IDs preserved from the R13 read-only audit.
# Root-cause/metric fields in the tests remain synthetic: this is not a GPU replay.
_R13_DEPENDENCY_CASES = [
    {
        "scenario_id": "s1_batch_too_big",
        "run_id": "78fc3b8b1a1742e4bc24b0890e7470c1",
        "final_plan_ids": ["p1"],
        "final_evidence_requests": [
            {
                "field": "execution_context.runtime_input_observations.logical_updates",
                "reason": "missing",
                "detail": "Optimizer update boundary, effective batch per update, and loss reduction semantics are unobserved because OOM occurred before first update; required to verify gradient accumulation equivalence if pursued.",
                "evidence_ref": "execution_context.runtime_input_observations.logical_updates",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": [],
            }
        ],
        "prior_plan_ids": ["grad_accum"],
        "prior_requests": [
            {
                "field": "numerical_reference_context.comparison_reference.supported_candidate_boundaries",
                "reason": "ambiguous",
                "detail": "Host-selected numerical reference strategy and its supported candidate boundaries are described but not proven equivalent for microbatch rewrite. Need to confirm the same loss denominator, masking, and update count are enforced.",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": ["grad_accum"],
            },
            {
                "field": "execution_context.runtime_input_observations.logical_updates.observed_optimizer_updates",
                "reason": "missing",
                "detail": "Zero optimizer updates observed (OOM before first update). Cannot verify effective_batch_per_optimizer_update or scheduler cadence from runtime; must rely on source defaults (--steps=20, batch=32).",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": ["grad_accum"],
            },
        ],
    },
    {
        "scenario_id": "s2_capacity_v2",
        "run_id": "d2a1601ccea94ec989459eeba1a423b6",
        "final_plan_ids": [],
        "final_evidence_requests": [
            {
                "field": "execution_context.runtime_input_observations.logical_updates.effective_batch_per_optimizer_update",
                "reason": "ambiguous",
                "detail": "Source shows effective_batch_per_optimizer_update=24 but policy allows batch/accumulation changes; need runtime confirmation that microbatch chunks preserve single optimizer step, scheduler step, gradient reset, and loss weighting by valid element count over total N.",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": [],
            },
            {
                "field": "execution_context.runtime_input_observations.logical_updates.backwards_per_optimizer_update",
                "reason": "ambiguous",
                "detail": "Source shows backwards_per_optimizer_update=1; any microbatch plan must preserve exactly one backward per optimizer step without introducing multiple backwards that are not multiple optimizer updates.",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": [],
            },
        ],
        "prior_plan_ids": ["cfg1"],
        "prior_requests": [
            {
                "field": "policy.allow_batch_grad_accum",
                "reason": "missing",
                "detail": "Policy does not declare allow_batch_grad_accum; gradient accumulation changes require this permission to be proposed.",
                "evidence_ref": "execution_context.runtime_input_observations",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": ["cfg1"],
            },
            {
                "field": "source_files.train.py lines 139-146",
                "reason": "ambiguous",
                "detail": "Source shows optimizer.zero_grad(set_to_none=True) each step; loss is mean squared error over [batch, width]. Microbatch equivalence would require per-chunk weighting by valid element count divided by total N, single optimizer.step, scheduler step, and gradient reset at original effective-update boundary. Cross-sample ops (LayerNorm/GELU) may prevent equivalence. Need explicit confirmation of loss reduction semantics and that no cross-sample coupling exists.",
                "evidence_ref": "source[0]",
                "source_line_start": 139,
                "source_line_end": 146,
                "blocking_scope": "overall_feasibility",
                "blocked_plan_ids": [],
            },
        ],
    },
]


@pytest.mark.parametrize("case", _R13_DEPENDENCY_CASES, ids=lambda case: case["scenario_id"])
def test_r13_prior_dependency_proof_is_labeled_as_a_prior_response_not_new_ids(case):
    reply = blocked()
    reply["plan"][0]["fix_id"] = case["prior_plan_ids"][0]
    reply["evidence_requests"] = copy.deepcopy(case["prior_requests"])
    diagnosis = Diagnosis.model_validate(reply)
    evidence, _ = source()
    before = diagnosis.model_dump()
    review = prerequisite_review(diagnosis, evidence)
    assert review is not None and len(review.encode()) <= MAX_REVIEW_BYTES
    data = json.loads(review.split("Prior prerequisite metadata: ", 1)[1])
    assert data["metadata_scope"] == "prior_response_snapshot_only_not_the_new_plan"
    assert data["prior_needs_more_info"] is True
    assert data["new_runtime_evidence_supplied"] is False
    assert len(data["prior_requests"]) == len(case["prior_requests"])
    for entry, original in zip(data["prior_requests"], case["prior_requests"], strict=True):
        assert entry["prior_plan_ids"] == case["prior_plan_ids"]
        assert entry["prior_needs_more_info"] is True
        assert entry["prior_declared_evidence_request"] == original
        assert entry["prior_dependency_scope_contract"]
        assert "current_plan_ids" not in entry
        assert "needs_more_info" not in entry
        assert "scope_contract" not in entry
    assert "plan=[] cannot have a current_plan dependency" in review
    assert "THIS NEW response" in review
    assert "Do not carry a discarded alternative's unknowns" in review
    assert "yourself return false for a complete independently supported replacement" in review
    assert diagnosis.model_dump() == before


@pytest.mark.parametrize("case", _R13_DEPENDENCY_CASES, ids=lambda case: case["scenario_id"])
def test_real_r13_empty_dependency_shapes_are_still_rejected_without_host_repair(case):
    reply = payload()
    reply["needs_more_info"] = True
    if case["final_plan_ids"]:
        reply["plan"][0]["fix_id"] = case["final_plan_ids"][0]
    else:
        reply["plan"] = []
    reply["evidence_requests"] = copy.deepcopy(case["final_evidence_requests"])
    diagnosis = Diagnosis.model_validate(reply)
    before = diagnosis.model_dump()
    evidence, _ = source()
    issues, _, _ = validate_evidence_requests(diagnosis, evidence)
    dependency_issues = [item for item in issues if item["code"] == "INVALID_EVIDENCE_DEPENDENCY"]
    assert [item["path"] for item in dependency_issues] == [
        f"/evidence_requests/{i}" for i in range(len(case["final_evidence_requests"]))
    ]
    assert diagnosis.model_dump() == before
    assert diagnosis.needs_more_info
    assert all(not request.blocked_plan_ids for request in diagnosis.evidence_requests)


def test_replacement_must_use_its_own_plan_ids_not_any_prior_id():
    first = blocked()
    first["plan"][0]["fix_id"] = "prior_fix"
    first["evidence_requests"][0]["blocked_plan_ids"] = ["prior_fix"]
    second = blocked()
    second["plan"][0]["fix_id"] = "new_fix"
    second["evidence_requests"][0]["blocked_plan_ids"] = ["prior_fix"]
    result, requests = invoke([first, second])
    assert len(requests) == 2
    assert not result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    assert "INVALID_EVIDENCE_DEPENDENCY" in {issue.code for issue in result.issues}
    assert result.diagnosis.evidence_requests[0].blocked_plan_ids == ["prior_fix"]


def test_model_may_keep_a_real_unknown_with_correct_replacement_ids_and_no_third_call():
    first = blocked()
    first["plan"][0]["fix_id"] = "prior_fix"
    first["evidence_requests"][0]["blocked_plan_ids"] = ["prior_fix"]
    second = blocked()
    second["plan"][0]["fix_id"] = "new_fix"
    second["evidence_requests"][0]["blocked_plan_ids"] = ["new_fix"]
    result, requests = invoke([first, second])
    assert len(requests) == 2
    assert result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    assert result.diagnosis.evidence_requests[0].blocked_plan_ids == ["new_fix"]
