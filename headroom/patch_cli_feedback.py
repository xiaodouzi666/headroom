"""Explain the existing host CLI allowlist without changing policy or target arguments."""

from __future__ import annotations

import re

from headroom.solver_context import _SECRET_OPTION
from headroom.verify.policy import (
    _CREDENTIAL_PATTERN,
    ACCUM_KEYS,
    BATCH_KEYS,
    MEMORY_CLI,
    MODEL_KEYS,
    PRECISION_CLI,
    TRAIN_KEYS,
    _argv_options,
)

MAX_OFFENDING_FLAGS = 20
MAX_FLAG_BYTES = 96
_TOKEN_LIKE_FLAG = re.compile(r"(?:nvapi-|[A-Za-z0-9]{24,})", re.IGNORECASE)


def _allowed_keys():
    return MODEL_KEYS | TRAIN_KEYS | BATCH_KEYS | ACCUM_KEYS | PRECISION_CLI | MEMORY_CLI


def cli_override_contract():
    """Membership is not permission, target parser support, or runtime evidence."""
    keys = sorted(_allowed_keys())
    return {
        "schema": "headroom.cli_override_contract.v1",
        "basis": "existing_host_cli_option_allowlist",
        "normalized_option_keys": keys,
        "canonical_long_options": sorted(
            {"--" + key for key in keys} | {"--" + key.replace("_", "-") for key in keys}
        ),
        "normalization": "Host option keys are case-insensitive; hyphens normalize to underscores.",
        "scope": (
            "Allowlist membership only. All existing policy restrictions still apply, including "
            "training limits, model shape, precision and batch permissions. The target parser must "
            "accept the selected spelling and its value; do not invent aliases or omit required values."
        ),
    }


def rejected_cli_feedback(changes, *, reason, issues=()):
    """Describe only the host's existing forbidden-option result; never echo values."""
    result = {
        "schema": "headroom.rejected_cli_options.v1",
        "basis": "existing_host_cli_option_guard",
        "status": "not_applicable",
        "offending_flags": [],
        "withheld_flag_count": 0,
        "omitted_flag_count": 0,
        "values_included": False,
        "cli_override_contract": cli_override_contract(),
    }
    if reason != "CLI_OPTION_FORBIDDEN" or not any(
        getattr(issue, "code", None) == "CLI_OPTION_FORBIDDEN" for issue in issues
    ):
        return result
    if (
        not isinstance(changes, (list, tuple))
        or len(changes) > 60
        or any(not isinstance(token, str) or len(token) > 1000 for token in changes)
    ):
        result.update(status="unavailable", reason="invalid_or_unbounded_cli_evidence")
        return result
    try:
        positional, options = _argv_options(changes)
    except (TypeError, ValueError):
        result.update(status="unavailable", reason="invalid_cli_evidence")
        return result
    if positional:
        result.update(status="unavailable", reason="invalid_cli_evidence")
        return result
    flags = [flag for key, (flag, _) in options.items() if key not in _allowed_keys()]
    if not flags:
        result.update(status="unavailable", reason="host_issue_not_reproduced_by_option_membership")
        return result
    for flag in flags:
        # Never shorten a flag into a different apparent option. Values, raw argv
        # and parser error strings are never rendered, even for malformed input.
        if (
            len(flag.encode()) > MAX_FLAG_BYTES
            or _CREDENTIAL_PATTERN.search(flag)
            or _SECRET_OPTION.search(flag)
            or _TOKEN_LIKE_FLAG.search(flag)
        ):
            result["withheld_flag_count"] += 1
        elif len(result["offending_flags"]) >= MAX_OFFENDING_FLAGS:
            result["omitted_flag_count"] += 1
        else:
            result["offending_flags"].append(flag)
    result["status"] = (
        "partial" if result["withheld_flag_count"] or result["omitted_flag_count"] else "complete"
    )
    return result
