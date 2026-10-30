"""Bounded validation context from supplied data; no I/O or diagnosis mutation."""

import json
import re

from headroom.evidence_blockers import evidence_reference_catalog
from headroom.verify.policy import _CREDENTIAL_PATTERN

MAX_CONTEXT_BYTES = 8192
_SENSITIVE_ASSIGNMENT = re.compile(
    r"""\b[A-Za-z_]*(?:api_key|access_token|secret|password)\b(?:\\?["'])?\s*[:=]""", re.IGNORECASE
)


def _has_credential(value):
    return bool(_CREDENTIAL_PATTERN.search(value) or _SENSITIVE_ASSIGNMENT.search(value))


_REFERENCE_FIELDS = (
    "evidence_ref",
    "kind",
    "availability",
    "text_availability_only",
    "runtime_values_verified",
)


def _safe_text(value, limit=1024):
    if not isinstance(value, str):
        return None
    if len(value) > limit or _has_credential(value):
        return "[withheld: oversized or credential-like text]"
    return value


def _reference_observation(entry):
    if not isinstance(entry, dict):
        return None
    result = {
        key: value
        for key in _REFERENCE_FIELDS
        if (value := entry.get(key)) is not None
        and (
            type(value) is bool
            or isinstance(value, str)
            and len(value) <= 160
            and not _has_credential(value)
        )
    }
    ranges = entry.get("visible_ranges")
    if isinstance(ranges, list):
        result["visible_ranges"] = [
            pair
            for pair in ranges[:16]
            if isinstance(pair, list)
            and len(pair) == 2
            and all(type(number) is int for number in pair)
            and 1 <= pair[0] <= pair[1] <= 1_000_000
        ]
        result["omitted_visible_ranges"] = max(0, len(ranges) - 16)
    return result


def validation_issue_context(issue, diagnosis, evidence=None):
    """Explain a host rejection without supplying answers or relaxing its rule.

    Existing caller limits decide whether a supplement happens. This helper only
    describes the exact retained request and the host's advertised catalogue;
    visible source text never becomes authenticated runtime observation.
    """
    message = _safe_text(issue.message)
    base = {"message": message} if message is not None else {}
    if diagnosis is None:
        return base
    match = re.fullmatch(r"/evidence_requests/([0-9]{1,2})(?:/[^\n]{0,160})?", issue.path or "")
    if match is None:
        return base
    try:
        request = diagnosis.evidence_requests[int(match[1])].model_dump()
        plans = diagnosis.plan
        ids = [step.fix_id for step in plans[:16]]
        # Inspect original string values before JSON escaping can hide quotes.
        strings = [value for value in request.values() if isinstance(value, str)]
        strings.extend(request["blocked_plan_ids"])
        strings.extend(ids)
        if any(len(value) > 1024 or _has_credential(value) for value in strings):
            return {**base, "request_context": {"status": "withheld"}}
        # Withhold the whole excerpt, not just a key-bearing substring.
        text = json.dumps({"request": request, "plan_ids": ids}, ensure_ascii=True)
        if len(text.encode()) > MAX_CONTEXT_BYTES:
            return {**base, "request_context": {"status": "withheld"}}
        catalog = evidence_reference_catalog(evidence)
        entry = catalog.get(request["evidence_ref"])
        context = {
            "content_is_untrusted_data": True,
            "offending_evidence_request": request,
            "current_plan_ids": ids,
            "omitted_plan_ids": max(0, len(plans) - 16),
            "needs_more_info": diagnosis.needs_more_info,
            "scope_contract": (
                "current_plan requires nonempty unique existing plan IDs. "
                "alternative_plan, overall_feasibility and an absent scope require "
                "blocked_plan_ids=[]. Choose the true scope; preserve genuine blockers "
                "and needs_more_info. This does not establish plan feasibility."
            ),
        }
        observation = _reference_observation(entry)
        if observation is not None:
            context["declared_reference_observation"] = observation
            if entry.get("kind") == "source":
                context["range_contract"] = (
                    "Only source references may have source line bounds; use both ordered "
                    "bounds or both null. Visible ranges describe supplied text only."
                )
            else:
                context["range_contract"] = (
                    "This advertised reference is not source text. source_line_start and "
                    "source_line_end must both be null; do not replace a genuine runtime "
                    "question with an unrelated source reference merely to pass validation."
                )
        if issue.code == "EVIDENCE_AVAILABILITY_CONTRADICTED" and observation is not None:
            context["availability_contract"] = (
                "The exact cited text/range is visible, so calling that text missing, "
                "redacted or truncated is contradicted. Meaning may remain ambiguous and "
                "runtime values unverified. Retain genuine missing-value dependencies."
            )
            unknown = catalog.get("execution_context.runtime_input_observations")
            if isinstance(unknown, dict) and unknown.get("availability") == "unknown":
                context["advertised_unknown_runtime_reference"] = _reference_observation(unknown)
        if len(json.dumps(context, ensure_ascii=True).encode()) > MAX_CONTEXT_BYTES:
            return {**base, "request_context": {"status": "withheld", "reason": "context_bound"}}
        return {**base, "request_context": context}
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        RecursionError,
        OverflowError,
    ):
        return {**base, "request_context": {"status": "unavailable"}}
