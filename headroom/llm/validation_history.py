"""Bounded terminal validation history; never copy text, bodies or reasoning."""

from headroom.llm.router import response_validation_metadata

MAX_FAILURE_HISTORY = 2
_REASONS = {"invalid_json", "empty_json", "truncated", "filtered", "schema_mismatch", "unknown"}
_FINISHES = {"stop", "length", "tool_calls", "content_filter", "function_call"}
_ROLES = {"annotate", "diagnose", "patcher", "research"}
_USAGE = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "reasoning_tokens",
)


def _integer(value):
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def _record(value):
    value = value if type(value) is dict else {}
    usage = value.get("usage")
    usage = usage if type(usage) is dict else {}
    reason, finish, role = (value.get(key) for key in ("error_reason", "finish_reason", "role"))
    return {
        "schema": "headroom.response-validation-metadata.v1",
        "error_reason": reason if type(reason) is str and reason in _REASONS else "unknown",
        "finish_reason": finish if type(finish) is str and finish in _FINISHES else None,
        "role": role if type(role) is str and role in _ROLES else None,
        "usage": {name: _integer(usage.get(name)) for name in _USAGE},
        "request_index": _integer(value.get("request_index")),
        "requested_reasoning": value.get("requested_reasoning")
        if type(value.get("requested_reasoning")) is bool
        else None,
    }


def attach_validation_failure_history(error, records):
    """Attach only the last two public records; retain an explicit omitted count."""
    if not isinstance(records, (list, tuple)) or not 1 <= len(records) <= 4:
        return
    error._headroom_validation_history = {
        "schema": "headroom.response-validation-history.v1",
        "status": "recorded",
        "failures": [_record(value) for value in records[-MAX_FAILURE_HISTORY:]],
        "total_failures": len(records),
        "omitted_failures": max(0, len(records) - MAX_FAILURE_HISTORY),
    }


def response_validation_history(error):
    """Re-whitelist serialized history and bind its final item to this error."""
    last = _record(response_validation_metadata(error))
    fallback = {
        "schema": "headroom.response-validation-history.v1",
        "status": "last_error_only",
        "failures": [last],
        "total_failures": None,
        "omitted_failures": None,
    }
    history = getattr(error, "_headroom_validation_history", None)
    if type(history) is not dict:
        return fallback
    records, total, omitted = (
        history.get("failures"),
        history.get("total_failures"),
        history.get("omitted_failures"),
    )
    if not (
        type(records) is list
        and 1 <= len(records) <= MAX_FAILURE_HISTORY
        and type(total) is int
        and len(records) <= total <= 4
        and type(omitted) is int
        and omitted == total - len(records)
    ):
        return fallback
    safe = [_record(value) for value in records]
    # Requested mode/index are host request metadata, not fields of the response.
    fields = ("schema", "error_reason", "finish_reason", "role", "usage")
    if any(safe[-1][key] != last[key] for key in fields):
        return fallback
    return {
        "schema": "headroom.response-validation-history.v1",
        "status": "recorded",
        "failures": safe,
        "total_failures": total,
        "omitted_failures": omitted,
    }
