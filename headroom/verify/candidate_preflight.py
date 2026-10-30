"""Static candidate capability checks; never execute code or certify equivalence."""

from collections.abc import Mapping
from pathlib import Path

from headroom.verify.checkpoint import STRATEGY as CHECKPOINT_STRATEGY
from headroom.verify.offload import STRATEGY as OFFLOAD_STRATEGY
from headroom.verify.reference_context import _contract

SCHEMA = "headroom.candidate_reference_preflight.v1"
_EXPLICIT_STRATEGIES = {CHECKPOINT_STRATEGY, OFFLOAD_STRATEGY}


def reference_family_reading_aid(context):
    """Highlight the existing active verifier boundary without inventing a repair."""
    if not isinstance(context, Mapping):
        return None
    boundary = context.get("source_contract_boundary")
    if not isinstance(boundary, Mapping) or not (
        context.get("protocol") == "headroom.numerical_reference_context.v1"
        and isinstance(context.get("selected_strategy"), str)
        and context.get("selected_strategy") in _EXPLICIT_STRATEGIES
        and boundary.get("active_for_this_oom_baseline") is True
        and boundary.get("candidate_source_must_remain_within_reviewed_contract") is True
    ):
        return None
    return {
        "schema": "headroom.reference_family_reading_aid.v1",
        "active": True,
        "selected_strategy": context["selected_strategy"],
        "capability_details": "numerical_reference_context.source_contract_boundary",
        "planning_constraint": (
            "Choose a candidate within the reviewed source contract and all exact edit-family "
            "requirements in capability_details. Policy permission alone does not establish "
            "verifier support. With a known original static contract, known unsupported applied "
            "source is rejected before candidate execution; otherwise the existing verifier decides."
        ),
        "unknowns": (
            "Static support is not reference execution, runtime pairing, numerical equivalence, "
            "memory savings or target success. Do not clear a real missing-evidence dependency."
        ),
    }


def candidate_reference_preflight(candidate_script, context):
    """Reject only a known violation of an already active static verifier boundary.

    Unreadable or unbound metadata stays unknown and follows the existing verifier.
    A successful check permits that verifier to run; it proves no runtime property.
    """
    result = {
        "schema": SCHEMA,
        "status": "not_applicable",
        "reason": None,
        "selected_strategy": None,
        "candidate_source_sha256": None,
        "candidate_contract_sha256": None,
        "expected_contract_sha256": None,
        "execution_performed_by_preflight": False,
        "candidate_equivalence_verified": None,
        "scope": "static source capability only; not runtime or acceptance evidence",
    }
    aid = reference_family_reading_aid(context)
    if aid is None:
        return result
    result["selected_strategy"] = aid["selected_strategy"]
    original = context.get("original_source")
    original = original if isinstance(original, Mapping) else {}
    expected = original.get("normalized_contract_sha256")
    if (
        original.get("status") != "supported"
        or not isinstance(expected, str)
        or len(expected) != 64
    ):
        result.update(status="unverified", reason="original_source_contract_unknown")
        return result
    result["expected_contract_sha256"] = expected
    candidate = _contract(Path(candidate_script))
    result["candidate_source_sha256"] = candidate.get("source_sha256")
    result["candidate_contract_sha256"] = candidate.get("contract_sha256")
    supported = candidate.get("supported")
    if supported is False:
        result.update(status="rejected", reason="candidate_source_contract_unsupported")
    elif supported is True and candidate.get("contract_sha256") != expected:
        result.update(status="rejected", reason="candidate_source_contract_mismatch")
    elif supported is True:
        result.update(status="admitted_static", reason=None)
    else:
        result.update(status="unverified", reason="candidate_source_contract_unknown")
    if result["status"] == "rejected":
        result["next_action"] = (
            "Replan from the currently retained source using the exact reviewed edit families "
            "in numerical_reference_context.source_contract_boundary. Do not retry this "
            "unsupported source, infer a numeric mismatch, or relax the numerical requirement."
        )
    return result
