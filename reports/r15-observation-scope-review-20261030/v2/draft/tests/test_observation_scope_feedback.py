"""Literal availability cannot negate independent runtime metadata or clear needs."""

import copy
import json

from test_evidence_blockers import checked, payload, request, source

from headroom.evidence_blockers import build_evidence_availability_catalog


def observed_sibling():
    evidence, markdown = source()
    evidence["execution_context"]["runtime_optimizer_observations"] = {
        "schema": "headroom.runtime_optimizer_observations.v1",
        "status": "observed",
        "scope": "selected_run_cooperative_optimizer_capture_only",
        "selected_run_id": "a" * 32,
        "source_sha256": evidence["sources"][0]["sha256"],
        "source_binding": "capture source digest matches retained entrypoint source",
        "logical_updates": 20,
        "parameter_update_sets_complete": True,
        "numerical_equivalence_proven": False,
        "parameters": {"catalog_entries": 12, "requires_grad_true_entries": 12},
        "updates": {"recorded_logical_updates": 20},
    }
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    return evidence


def runtime_request(**kwargs):
    ref = "execution_context.runtime_optimizer_observations.parameters"
    return request(
        field=ref, evidence_ref=ref, source_line_start=None, source_line_end=None, **kwargs
    )


def test_scope_feedback_preserves_observed_sibling_and_genuine_unknown_without_authorizing_plan():
    evidence = observed_sibling()
    before = copy.deepcopy(evidence)
    reply = payload()
    reply["evidence_requests"] = [
        runtime_request(
            reason="missing",
            detail="Need a distinct optimizer-internal value not reported by the parameter counts.",
        )
    ]
    result = checked(reply, evidence)
    assert not result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    feedback = json.loads(result.supplement_request.split("Errors: ", 1)[1])
    issue = next(
        item for item in feedback["issues"] if item["code"] == "EVIDENCE_AVAILABILITY_CONTRADICTED"
    )
    context = issue["request_context"]
    assert context["declared_reference_observation"]["runtime_values_verified"] is False
    assert context["availability_declaration"]["semantic_answer_supplied"] is False
    assert "does not negate separate scoped observations" in context["availability_contract"]
    literal = feedback["literal_observations"][0]["observation"]
    assert "does not override separate scoped observations" in literal
    assert "runtime values and semantic prerequisites remain unverified" not in literal
    assert evidence == before
    assert evidence["execution_context"]["runtime_optimizer_observations"]["logical_updates"] == 20
    assert (
        evidence["execution_context"]["runtime_optimizer_observations"][
            "numerical_equivalence_proven"
        ]
        is False
    )

    corrected = copy.deepcopy(reply)
    corrected["evidence_requests"][0]["reason"] = "ambiguous"
    still_blocked = checked(corrected, evidence)
    assert still_blocked.valid
    assert still_blocked.diagnosis.needs_more_info
    assert not still_blocked.ready_for_patch


def test_runtime_reference_source_bounds_remain_invalid_and_needs_stays_true():
    reply = payload()
    item = runtime_request(reason="ambiguous")
    item["source_line_start"], item["source_line_end"] = 1, 2
    reply["evidence_requests"] = [item]
    result = checked(reply, observed_sibling())
    assert any(issue.code == "INVALID_EVIDENCE_RANGE" for issue in result.issues)
    assert result.diagnosis.needs_more_info
    assert not result.valid and not result.ready_for_patch
