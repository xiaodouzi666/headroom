"""Offline literal-evidence checks: no model, GPU, source execution or credentials."""

import copy
from types import SimpleNamespace

import pytest

from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.schemas import Diagnosis
from headroom.solver_context import execution_context, prompt_arguments


def payload():
    return {
        "root_causes": [
            {
                "id": "c",
                "title": "Measured activation allocation",
                "category": "activations",
                "bytes_gb": 1.0,
                "evidence_refs": ["stk"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "p",
                "type": "code",
                "title": "Recompute a block",
                "description": "Recompute intermediate activations during backward.",
                "expected_saving_gb": 1.0,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Measure cost",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": [],
    }


def evidence(args=("--samples=7", "--accum", "3")):
    return {
        "analysis": {"stack_catalog": {"stk": []}},
        "execution_context": {"script_args": prompt_arguments(args), "execution_argv": None},
    }


def check(reply, source=None):
    return validate_diagnosis(reply, evidence=source or evidence(), policy={})


def claim(token="--samples=7", index=0, source="script_args"):
    return {"source": source, "index": index, "token": token}


def test_historical_response_remains_valid_but_not_configuration_verified():
    result = check(payload())
    assert result.valid
    assert result.invocation_provenance["status"] == "unverified"
    assert result.invocation_provenance["target_effective_configuration"] == "unverified"
    assert not result.invocation_provenance["unstructured_prose_checked"]
    assert "invocation_claims" not in Diagnosis.model_json_schema()["required"]


def test_literal_matching_does_not_prove_target_runtime_configuration():
    reply = payload()
    reply["invocation_claims"] = [claim(), claim("3", index=2)]
    result = check(reply)
    assert result.valid
    assert result.invocation_provenance["status"] == "observed_tokens_verified"
    assert result.invocation_provenance["target_effective_configuration"] == "unverified"


def test_default_value_cannot_replace_retained_argument_in_a_declared_claim():
    reply = payload()
    reply["invocation_claims"] = [claim("--samples=19")]
    reply["needs_more_info"] = True
    result = check(reply)
    assert not result.valid and result.requires_supplement
    assert result.diagnosis.needs_more_info is True
    assert result.invocation_provenance["status"] == "contradicted"
    assert "--samples=7" in result.supplement_request
    assert "--samples=19" not in result.supplement_request
    assert "do not force a plan" in result.supplement_request


def test_out_of_range_claim_only_contradicted_when_complete():
    reply = payload()
    reply["invocation_claims"] = [claim("unknown", index=8)]
    assert check(reply).requires_supplement
    source = evidence()
    source["execution_context"]["script_args"].update(complete=False, omitted_count=10)
    result = check(reply, source)
    assert result.valid and not result.requires_supplement
    assert result.invocation_provenance["status"] == "unverified"


def test_redacted_values_never_become_validation_feedback():
    reply = payload()
    reply["invocation_claims"] = [claim("guess", index=1)]
    source = evidence(("--api-key", "canary-never-echo", "--samples=7"))
    result = check(reply, source)
    assert result.valid and not result.requires_supplement
    assert result.invocation_provenance["status"] == "unverified"
    assert "canary-never-echo" not in repr(result)


def test_missing_context_is_unsupported_instead_of_default_inference():
    reply = payload()
    reply["invocation_claims"] = [claim()]
    result = check(reply, {"analysis": {"stack_catalog": {"stk": []}}})
    assert result.valid and not result.requires_supplement
    assert result.invocation_provenance["status"] == "unsupported"


def request(reason="missing", field="execution_context.script_args"):
    return {"field": field, "reason": reason, "detail": "Need to establish configuration."}


def test_explicit_missing_complete_argv_gets_bounded_feedback_not_forced_plan():
    reply = payload()
    reply.update(needs_more_info=True, evidence_requests=[request()])
    result = check(reply)
    assert not result.valid and result.requires_supplement
    assert result.diagnosis.needs_more_info is True
    assert result.issues[0].code == "REQUESTED_INVOCATION_ALREADY_PRESENT"


@pytest.mark.parametrize(
    "reason", ["ambiguous", "policy_infeasible", "insufficient_saving", "other"]
)
def test_genuine_ambiguity_or_policy_limit_does_not_get_overridden(reason):
    reply = payload()
    reply.update(needs_more_info=True, evidence_requests=[request(reason)])
    result = check(reply)
    assert result.valid and not result.ready_for_patch and not result.requires_supplement


def test_unavailable_runtime_evidence_and_unstructured_notes_are_not_guessed():
    reply = payload()
    reply.update(
        needs_more_info=True,
        notes=["Missing argv despite a plan; source defaults claim samples=19."],
        evidence_requests=[request(field="target.runtime.effective_configuration")],
    )
    result = check(reply)
    assert result.valid and not result.requires_supplement


def test_incomplete_argv_cannot_disprove_missing_evidence():
    reply = payload()
    reply.update(needs_more_info=True, evidence_requests=[request()])
    source = evidence()
    source["execution_context"]["script_args"]["complete"] = False
    assert not check(reply, source).requires_supplement


class Router:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def chat(self, role, messages, schema, **kwargs):
        self.calls.append(copy.deepcopy((role, messages, schema, kwargs)))
        return SimpleNamespace(
            parsed=copy.deepcopy(self.responses[min(len(self.calls) - 1, len(self.responses) - 1)])
        )


def test_repair_uses_existing_single_supplement_budget_and_retains_true_gap():
    bad = payload()
    bad.update(needs_more_info=True, invocation_claims=[claim("--samples=19")])
    corrected = payload()
    corrected.update(
        needs_more_info=True,
        invocation_claims=[claim()],
        evidence_requests=[request("ambiguous", "target.runtime.effective_configuration")],
    )
    router = Router([bad, corrected])
    result = diagnose_with_router(
        router, "Measured evidence", evidence=evidence(), goal="reclaim", policy={}
    )
    assert len(router.calls) == 2
    assert result.valid and not result.ready_for_patch and result.diagnosis.needs_more_info
    assert len(router.calls[1][1]) == len(router.calls[0][1]) + 2
    assert all(c[3]["reasoning"] is True for c in router.calls)


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_repeated_contradictions_stop_at_existing_cap(limit):
    bad = payload()
    bad["invocation_claims"] = [claim("--samples=19")]
    router = Router([bad])
    result = diagnose_with_router(
        router,
        "Measured evidence",
        evidence=evidence(),
        goal="reclaim",
        policy={},
        max_supplements=limit,
    )
    assert len(router.calls) == limit + 1
    assert not result.valid and result.requires_supplement


def test_retained_invocation_metadata_never_claims_runtime_resolution():
    context = execution_context(
        script="train.py",
        script_args=["--samples=7"],
        execution_argv=None,
        source_files=[],
        selected_round=None,
        repository_mode=False,
        seed=5,
        max_steps=20,
        device="cpu",
        allocator_conf=None,
    )
    assert context["configuration_resolution"]["status"] == "unverified"
    assert context["configuration_resolution"]["runtime_values_verified"] is False
