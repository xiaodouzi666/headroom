"""Versioned R6 prepared-wire audit with bounded host truncation binding."""

import argparse
import copy
import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/acceptance-v2-r6-20261027"
EXECUTION = OUT / "execution.json"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CALLS = 2048
MAX_EVENTS = 8192
# The reviewed r2 profile uses this exact wire field, not a default/alias inference.
EXPECTED_CAP_FIELD = "max_completion_tokens"
CAP_FIELDS = {"max_tokens", "max_completion_tokens"}
ALLOWED_MODES = {
    "diagnose": ["diagnose_thinking", "diagnose_nonthinking_after_bound_truncation"],
    "patcher": ["thinking_low_effort_with_verified_contract", "nonthinking"],
}
# Root must connect existing frozen review/transition/runtime validation first.
PRODUCTION_CONTRACT_STATUS = "PENDING"
HEX = re.compile(r"[0-9a-f]{64}")
FINISH_REASONS = {"stop", "length", "tool_calls", "function_call", "content_filter"}
ROLES = {
    "diagnose": ("nvidia/Nemotron-3-Ultra-550b-a55b", 16384),
    "patcher": ("nvidia/nemotron-3-super-120b-a12b", 4000),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_json(path):
    require(path.is_file() and not path.is_symlink(), "missing or symbolic JSON input")
    require(path.stat().st_size <= MAX_JSON_BYTES, "JSON input exceeds size bound")
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON_BYTES, "JSON input grew beyond bound")
    value = json.loads(raw)
    require(isinstance(value, dict), "JSON object required")
    return value, digest(raw)


def nonnegative(value):
    return type(value) is int and value >= 0


R5_BASE_PROFILE_SHA256 = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"
_CONTRACT_SEAL = object()


@dataclass(frozen=True)
class ReasoningContractPins:
    active_profile_sha256: str
    root_review_sha256: str
    transition_receipt_sha256: str
    probe_receipt_sha256: str
    funding_transition_sha256: str

    def __post_init__(self):
        require(
            all(type(value) is str and HEX.fullmatch(value) for value in vars(self).values()),
            "R5 reasoning contract pins must be exact reviewed SHA256 values",
        )


@dataclass(frozen=True)
class VerifiedR5ReasoningContract:
    pins: ReasoningContractPins
    _seal: object = field(repr=False, compare=False)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON keys in contract evidence")
        result[key] = value
    return result


def _contract_json(raw, expected_sha):
    require(type(raw) is bytes and len(raw) <= MAX_JSON_BYTES, "invalid contract artifact bytes")
    require(digest(raw) == expected_sha, "contract artifact hash mismatch")

    def invalid(_):
        raise ValueError("nonfinite contract JSON")

    value = json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=invalid)
    require(type(value) is dict, "contract JSON object required")
    return value


def bind_verified_contract(
    *,
    pins,
    active_profile_raw,
    probe_receipt_raw,
    root_review_validation,
    transition_validation,
):
    """Cross-bind already-verified root/funding/transition results and pinned bytes.

    The validation mappings are trusted verifier RESULTS, never raw JSON claims.
    The root integration must independently verify their frozen files and emit
    these results. This factory is not a substitute for funding validation.
    No files, network, model calls, or database operations occur here.
    """
    require(type(pins) is ReasoningContractPins, "explicit R5 pins required")
    for result in (root_review_validation, transition_validation):
        require(
            type(result) is dict and result.get("valid") is True, "verified review results required"
        )
    root = root_review_validation
    transition = transition_validation
    require(
        root.get("root_review_sha256") == pins.root_review_sha256
        and root.get("active_profile_sha256") == pins.active_profile_sha256
        and root.get("funding_chain_verified") is True
        and root.get("capability_transition_verified") is True
        and root.get("active_profile_runtime_verified") is True
        and root.get("transition_receipt_sha256") == pins.transition_receipt_sha256
        and root.get("low_effort_probe_receipt_sha256") == pins.probe_receipt_sha256
        and root.get("funding_transition_sha256") == pins.funding_transition_sha256,
        "root review does not bind the active profile and capability pins",
    )
    require(
        transition.get("base_profile_sha256") == R5_BASE_PROFILE_SHA256
        and transition.get("new_profile_sha256") == pins.active_profile_sha256
        and transition.get("transition_receipt_sha256") == pins.transition_receipt_sha256
        and transition.get("low_effort_probe_receipt_sha256") == pins.probe_receipt_sha256
        and transition.get("funding_transition_sha256") == pins.funding_transition_sha256
        and transition.get("financial_or_ledger_changes") is False
        and transition.get("full_projection_equal") is True,
        "nonfinancial capability transition binding is incomplete",
    )
    profile = _contract_json(active_profile_raw, pins.active_profile_sha256)
    probe = _contract_json(probe_receipt_raw, pins.probe_receipt_sha256)
    models = profile.get("models")
    require(type(models) is dict and type(models.get("super")) is dict, "Super profile required")
    model = models["super"]
    caps = model.get("capabilities")
    require(type(caps) is dict, "Super capability object required")
    require(
        model.get("model_id") == ROLES["patcher"][0]
        and caps.get("reasoning_method") == "chat_template_kwargs"
        and caps.get("json_method") == "json_schema"
        and caps.get("low_effort_method") == "chat_template_kwargs"
        and caps.get("low_effort_evidence_sha256") == pins.probe_receipt_sha256
        and type(caps.get("low_effort_evidence")) is str
        and bool(caps["low_effort_evidence"]),
        "active Super profile does not bind the tested request combination",
    )
    reasoning, completion = probe.get("reasoning_tokens"), probe.get("completion_tokens")
    require(
        probe.get("scope") == "super_low_effort_schema_code_probe_v1"
        and probe.get("profile_sha256") == R5_BASE_PROFILE_SHA256
        and probe.get("provenance") == "live"
        and probe.get("accepted") is True
        and probe.get("verdict") == "request_combination_usable_in_one_sample"
        and probe.get("response_model") == ROLES["patcher"][0]
        and probe.get("base_url") == profile.get("base_url")
        and probe.get("finish_reason") == "stop"
        and type(reasoning) is int
        and type(completion) is int
        and 0 < reasoning <= completion <= 4000
        and json.dumps(probe.get("profile_model_compatibility"), sort_keys=True, allow_nan=False)
        == json.dumps(
            {key: value for key, value in model.items() if key != "capabilities"},
            sort_keys=True,
            allow_nan=False,
        ),
        "live capability receipt does not match the active Super context",
    )
    ultra = models.get("ultra")
    require(
        type(ultra) is dict
        and ultra.get("model_id") == ROLES["diagnose"][0]
        and type(ultra.get("capabilities")) is dict
        and ultra["capabilities"].get("reasoning_method") == "chat_template_kwargs"
        and ultra["capabilities"].get("json_method") == "json_schema",
        "active Ultra profile does not bind the previously verified template toggle",
    )
    return VerifiedR5ReasoningContract(pins, _CONTRACT_SEAL)


def contract_is_bound(contract):
    return (
        type(contract) is VerifiedR5ReasoningContract
        and contract._seal is _CONTRACT_SEAL
        and type(contract.pins) is ReasoningContractPins
    )


def reasoning_mode(role, payload, contract):
    """Report actual strict-bool wire values; do not infer a fallback trigger."""
    result = {
        "enable_thinking": None,
        "low_effort_present": None,
        "low_effort": None,
        "observed_reasoning_mode": "unknown",
        "allowed_mode_matches": None,
        "low_effort_contract_bound": contract_is_bound(contract),
        "fallback_trigger_verified": False,
    }
    problems = []
    if payload is None:
        return result, problems
    template = payload.get("chat_template_kwargs")
    if type(template) is not dict:
        result.update(observed_reasoning_mode="invalid", allowed_mode_matches=False)
        return result, ["missing_or_invalid_reasoning_template"]
    value = template.get("enable_thinking")
    result["enable_thinking"] = value if type(value) is bool else None
    result["low_effort_present"] = "low_effort" in template
    low = template.get("low_effort")
    result["low_effort"] = low if type(low) is bool else None
    result.update(observed_reasoning_mode="invalid", allowed_mode_matches=False)
    if type(value) is not bool:
        problems.append("missing_or_invalid_enable_thinking")
    if "low_effort" in template and type(low) is not bool:
        problems.append("invalid_low_effort_type")
    if set(template) - {"enable_thinking", "low_effort"}:
        problems.append("unreviewed_reasoning_template_parameter")
    if problems:
        return result, problems
    if role == "diagnose":
        allowed = value is True and "low_effort" not in template
        result.update(
            observed_reasoning_mode="diagnose_thinking" if allowed else "invalid",
            allowed_mode_matches=allowed,
        )
    elif value is False and "low_effort" not in template:
        result.update(observed_reasoning_mode="nonthinking", allowed_mode_matches=True)
    elif value is True and low is True:
        result.update(
            observed_reasoning_mode="thinking_low_effort",
            allowed_mode_matches=contract_is_bound(contract),
        )
        if not contract_is_bound(contract):
            problems.append("low_effort_contract_not_verified")
    if result["allowed_mode_matches"] is False and not problems:
        problems.append("reasoning_mode_outside_role_contract")
    return result, problems


def analyze_call(row, *, contract=None):
    """Whitelist metadata only; missing persisted values remain unknown."""
    record = row["data"]
    role = row["role"]
    model, expected_cap = ROLES[role]
    problems = []
    if record.get("model") != row["model"] or record.get("role") != role:
        problems.append("store_identity_mismatch")
    if row["model"] != model:
        problems.append("unexpected_model")
    evidence = record.get("request_evidence")
    payload = None
    metadata_valid = None
    payload_valid = None
    state = "unknown"
    wire_hash = stored_hash = None
    if isinstance(evidence, dict):
        state = evidence.get("payload_status")
        if state not in {"captured", "redacted", "omitted_size", "invalid_json"}:
            state = "unknown"
        metadata_valid = (
            type(evidence.get("schema_version")) is int
            and evidence["schema_version"] == 1
            and evidence.get("capture_point") == "httpx_pre_transport"
            and bool(HEX.fullmatch(str(evidence.get("wire_body_sha256", ""))))
            and type(evidence.get("wire_body_utf8_bytes")) is int
            and evidence["wire_body_utf8_bytes"] > 0
            and evidence.get("delivery_confirmed") is False
        )
        if metadata_valid:
            wire_hash = evidence["wire_body_sha256"]
        else:
            problems.append("request_metadata_invalid")
        if state in {"captured", "redacted"}:
            candidate = evidence.get("payload")
            stored_hash = evidence.get("stored_payload_sha256")
            payload_valid = (
                isinstance(candidate, dict)
                and bool(HEX.fullmatch(str(stored_hash)))
                and len(canonical(candidate)) <= 256 * 1024
                and digest(canonical(candidate)) == stored_hash
            )
            if not payload_valid:
                problems.append("request_payload_invalid")
            elif metadata_valid:
                payload = candidate
        elif evidence.get("payload") is not None:
            problems.append("unexpected_uncaptured_payload")

    cap = cap_field = request_model_matches = None
    if payload is not None:
        request_model_matches = payload.get("model") == row["model"] == model
        if not request_model_matches:
            problems.append("request_model_mismatch")
        present_caps = CAP_FIELDS.intersection(payload)
        if len(present_caps) > 1:
            problems.append("conflicting_output_cap_fields")
        elif present_caps:
            cap_field = next(iter(present_caps))
            value = payload[cap_field]
            cap = value if type(value) is int and value > 0 else None
            if cap_field != EXPECTED_CAP_FIELD:
                problems.append("unexpected_output_cap_field")

    mode, mode_problems = reasoning_mode(role, payload, contract)
    problems.extend(mode_problems)

    usage = record.get("usage")
    completion = reasoning = None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        output = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        valid = all(nonnegative(x) for x in (prompt, output, total)) and total == prompt + output
        if valid:
            completion = output
            value = usage.get("reasoning_tokens")
            if value is None or (nonnegative(value) and value <= completion):
                reasoning = value
            else:
                problems.append("invalid_reasoning_token_count")
        else:
            problems.append("invalid_usage_totals")

    finish = record.get("finish_reason")
    finish = finish if isinstance(finish, str) and finish in FINISH_REASONS else None
    outcome = record.get("outcome")
    known_outcomes = {
        "response",
        "http_error",
        "timeout",
        "transport_error",
        "response_error",
        "interrupted",
        "not_dispatched",
    }
    outcome = outcome if isinstance(outcome, str) and outcome in known_outcomes else "unknown"
    return {
        "call_id": row["id"],
        "run_id": row["run_id"],
        "role": role,
        "model": row["model"] if row["model"] == model else "unexpected",
        "outcome": outcome,
        "request_capture_state": state,
        "request_metadata_valid": metadata_valid,
        "request_payload_valid": payload_valid,
        "request_model_matches": request_model_matches,
        "wire_body_sha256": wire_hash,
        "stored_payload_sha256": stored_hash if payload_valid else None,
        **mode,
        "expected_reasoning_modes": list(ALLOWED_MODES[role]),
        "expected_output_cap_field": EXPECTED_CAP_FIELD,
        "observed_output_cap_field": cap_field,
        "expected_output_cap_tokens": expected_cap,
        "observed_output_cap_tokens": cap,
        "cap_field_matches": None if cap_field is None else cap_field == EXPECTED_CAP_FIELD,
        "cap_matches": None
        if cap is None
        else cap == expected_cap and cap_field == EXPECTED_CAP_FIELD,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "finish_reason": finish,
        "finish_reason_basis": "persisted_call_field"
        if finish is not None
        else "not_persisted_or_unknown",
        "length_finish": None if finish is None else finish == "length",
        "completion_reached_request_cap": None
        if completion is None or cap is None
        else completion == cap,
        "integrity_issues": problems,
        "provider_delivery_or_ingestion_proven": False,
    }


_USAGE_FIELDS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cached_tokens",
    "reasoning_tokens",
)
_VALIDATION_FIELDS = ("schema", "error_reason", "finish_reason", "role", "usage")
_RESEND_MESSAGE = {
    "role": "user",
    "content": (
        "The previous response failed structured-output validation (truncated). "
        "Return one complete JSON object matching the supplied schema. "
        "Start again from the original evidence; do not continue the prior response. "
        "Keep fields concise while preserving evidence references, uncertainty, "
        "all policy constraints and required verification. Do not invent missing "
        "facts or omit required fields. Return JSON only."
    ),
}


class _Unavailable(ValueError):
    """Missing evidence cannot establish a reviewed host trigger."""


def _need(condition, reason):
    if not condition:
        raise _Unavailable(reason)


def _time(value):
    _need(type(value) is str, "missing_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _Unavailable("unparseable_timestamp") from None
    _need(parsed.tzinfo is not None and parsed.utcoffset() is not None, "unscoped_timestamp")
    return parsed.astimezone(UTC)


def _validation_bound(failure, call, index, reasoning):
    _need(type(failure) is dict, "missing_validation_record")
    require(
        failure.get("schema") == "headroom.response-validation-metadata.v1"
        and failure.get("role") == "diagnose"
        and type(failure.get("request_index")) is int
        and failure["request_index"] == index
        and failure.get("requested_reasoning") is reasoning,
        "validation_identity_conflict",
    )
    require(
        failure.get("error_reason")
        in {"truncated", "empty_json", "invalid_json", "filtered", "schema_mismatch"}
        and failure.get("finish_reason") in FINISH_REASONS,
        "validation_reason_conflict",
    )
    usage, recorded = failure.get("usage"), call["data"].get("usage")
    _need(type(usage) is dict and type(recorded) is dict, "missing_validation_usage")
    for key in _USAGE_FIELDS:
        _need(key in usage and key in recorded, "missing_validation_usage_field")
        value = usage[key]
        require(
            (value is None or nonnegative(value))
            and type(value) is type(recorded[key])
            and value == recorded[key],
            "validation_usage_conflict",
        )
    persisted = call["data"].get("finish_reason")
    require(
        persisted is None or persisted == failure["finish_reason"],
        "persisted_finish_conflict",
    )


def _bound_pair(call, calls, events, contract):
    _need(contract_is_bound(contract), "unverified_profile_contract")
    run_id = call["run_id"]
    peers = sorted([row for row in calls if row["run_id"] == run_id], key=lambda row: row["id"])
    host = sorted(
        [row for row in events if row["run_id"] == run_id], key=lambda row: row["sequence"]
    )
    _need(host, "missing_host_events")
    require(
        all(type(row["id"]) is int and row["id"] > 0 for row in peers + host)
        and len({row["id"] for row in peers}) == len(peers)
        and len({row["id"] for row in host}) == len(host)
        and all(type(row["sequence"]) is int and row["sequence"] > 0 for row in host)
        and len({row["sequence"] for row in host}) == len(host),
        "duplicate_or_invalid_identity",
    )
    times = [_time(row.get("created_at")) for row in host]
    call_times = [_time(row.get("created_at")) for row in peers]
    require(
        all(a < b for a, b in pairwise(times)) and all(a < b for a, b in pairwise(call_times)),
        "ambiguous_event_or_call_order",
    )
    target_time = _time(call.get("created_at"))
    matches = [
        index
        for index, event in enumerate(host[:-1])
        if event["kind"] == "diagnose.started" and times[index] < target_time < times[index + 1]
    ]
    _need(len(matches) == 1, "no_unique_diagnosis_window")
    position = matches[0]
    start, end = host[position : position + 2]
    _need(end["sequence"] == start["sequence"] + 1, "missing_event_sequence")
    first_time, last_time = times[position : position + 2]
    _need(end["kind"] in {"diagnose.done", "run.failed"}, "missing_diagnosis_close")
    start_data, end_data = start["data"], end["data"]
    _need(type(start_data) is dict and type(end_data) is dict, "missing_host_metadata")
    number = start_data.get("round")
    require(
        type(number) is int and number > 0 and start_data.get("role") == "diagnose",
        "invalid_diagnosis_start",
    )
    require(
        sum(
            row["kind"] == "diagnose.started"
            and type(row.get("data")) is dict
            and row["data"].get("round") == number
            for row in host
        )
        == 1
        and sum(
            row["kind"] == "diagnose.done"
            and type(row.get("data")) is dict
            and row["data"].get("round") == number
            for row in host
        )
        <= 1,
        "duplicate_diagnosis_round",
    )
    require(
        all(moment not in {first_time, last_time} for moment in call_times),
        "ambiguous_call_at_event_boundary",
    )
    window = [
        row
        for row, moment in zip(peers, call_times, strict=True)
        if first_time < moment < last_time
    ]
    require(
        len(window) == 2
        and window[1]["id"] == call["id"]
        and all(row["role"] == "diagnose" for row in window),
        "not_exactly_two_same_round_diagnosis_calls",
    )
    attempts = []
    for index, row in enumerate(window, 1):
        data = row["data"]
        result = analyze_call(row, contract=contract)
        problems = set(result["integrity_issues"]) - {"reasoning_mode_outside_role_contract"}
        _need(
            result["request_capture_state"] == "captured"
            and result["request_metadata_valid"] is True
            and result["request_payload_valid"] is True,
            "missing_complete_prepared_wire",
        )
        require(
            not problems
            and result["cap_matches"] is True
            and result["request_model_matches"] is True
            and result["enable_thinking"] is (index == 1)
            and result["low_effort_present"] is False
            and result["completion_tokens"] is not None
            and result["completion_tokens"] <= 16384,
            "prepared_wire_contract_conflict",
        )
        evidence = data["request_evidence"]
        require(
            data.get("outcome") == "response"
            and type(data.get("http_status")) is int
            and data["http_status"] == 200
            and data.get("response_model") == ROLES["diagnose"][0]
            and type(data.get("attempt")) is int
            and data["attempt"] == 1
            and evidence.get("attempt") == 1
            and type(evidence.get("attempt")) is int
            and evidence.get("role") == "diagnose"
            and evidence.get("model") == ROLES["diagnose"][0],
            "dispatch_identity_or_retry_conflict",
        )
        attempt_id = data.get("budget_attempt_id")
        _need(
            type(attempt_id) is str and re.fullmatch(r"[0-9a-f]{32}", attempt_id),
            "missing_budget_attempt_identity",
        )
        attempts.append(attempt_id)
    require(len(set(attempts)) == 2, "reused_budget_attempt")
    left, right = [row["data"]["request_evidence"]["payload"] for row in window]
    response_format = left.get("response_format")
    require(
        type(response_format) is dict
        and response_format.get("type") == "json_schema"
        and type(response_format.get("json_schema")) is dict
        and type(response_format["json_schema"].get("schema")) is dict,
        "missing_reviewed_schema_request",
    )
    messages = left.get("messages")
    _need(type(messages) is list and messages, "missing_original_messages")
    require(
        right.get("messages") == [*messages, _RESEND_MESSAGE],
        "original_evidence_or_resend_conflict",
    )
    rest = {
        key: value for key, value in left.items() if key not in {"messages", "chat_template_kwargs"}
    }
    require(
        rest
        == {
            key: value
            for key, value in right.items()
            if key not in {"messages", "chat_template_kwargs"}
        },
        "schema_or_other_request_parameter_changed",
    )
    if end["kind"] == "diagnose.done":
        require(
            type(end_data.get("round")) is int and end_data["round"] == number,
            "round_identity_conflict",
        )
        modes = end_data.get("response_request_modes")
        _need(type(modes) is list and len(modes) == 2, "missing_complete_request_modes")
        for index, mode in enumerate(modes, 1):
            require(
                type(mode) is dict
                and type(mode.get("request_index")) is int
                and mode["request_index"] == index
                and mode.get("requested_reasoning") is (index == 1)
                and type(mode.get("max_completion_tokens")) is int
                and mode["max_completion_tokens"] == 16384
                and mode.get("scope") == "host_requested_mode_only",
                "host_request_mode_conflict",
            )
        failures = end_data.get("response_validation_failures")
        _need(type(failures) is list, "missing_validation_failures")
        require(len(failures) == 1, "success_failure_count_conflict")
        details = end_data.get("llm_calls")
        _need(type(details) is list and len(details) == 2, "missing_phase_call_count")
        require(
            all(
                type(row) is dict
                and row.get("model") == ROLES["diagnose"][0]
                and row.get("role") == "diagnose"
                and row.get("outcome") == "response"
                for row in details
            ),
            "phase_identity_conflict",
        )
    else:
        require(
            end_data.get("reason") == "Pipeline failed: ResponseValidationError"
            and not any(moment > last_time for moment in call_times)
            and not any(
                row["kind"] in {"diagnose.started", "diagnose.done"} for row in host[position + 2 :]
            ),
            "nonterminal_failure_conflict",
        )
        history = end_data.get("response_validation_history")
        _need(
            type(history) is dict and history.get("status") == "recorded",
            "missing_complete_failure_history",
        )
        require(
            history.get("schema") == "headroom.response-validation-history.v1"
            and type(history.get("total_failures")) is int
            and history["total_failures"] == 2
            and type(history.get("omitted_failures")) is int
            and history["omitted_failures"] == 0,
            "failure_history_count_conflict",
        )
        failures = history.get("failures")
        require(type(failures) is list and len(failures) == 2, "failure_history_count_conflict")
        _validation_bound(failures[1], window[1], 2, False)
        terminal = end_data.get("response_validation")
        _need(type(terminal) is dict, "missing_terminal_validation")
        require(
            all(terminal.get(key) == failures[1].get(key) for key in _VALIDATION_FIELDS),
            "terminal_validation_conflict",
        )
    _validation_bound(failures[0], window[0], 1, True)
    require(
        failures[0]["error_reason"] == "truncated" and failures[0]["finish_reason"] == "length",
        "first_failure_not_truncated_length",
    )
    return {
        "status": "verified",
        "scope": "host_truncation_and_prepared_request_binding_only",
        "round": number,
        "start_event_id": start["id"],
        "close_event_id": end["id"],
        "start_sequence": start["sequence"],
        "close_sequence": end["sequence"],
        "close_kind": end["kind"],
        "event_pair_sha256": digest(canonical([start, end])),
        "call_ids": [row["id"] for row in window],
        "budget_attempt_ids": attempts,
        "call_pair_sha256": digest(canonical(window)),
        "wire_body_sha256": [row["data"]["request_evidence"]["wire_body_sha256"] for row in window],
        "stored_payload_sha256": [
            row["data"]["request_evidence"]["stored_payload_sha256"] for row in window
        ],
        "first_error_reason": "truncated",
        "first_finish_reason": "length",
        "same_evidence_and_schema": True,
        "provider_effect_proven": False,
        "fallback_improvement_causality_proven": False,
    }


def apply_diagnosis_fallbacks(selected, call_rows, event_rows, *, contract=None):
    """Bind a narrow exception using full owned rows; never accept a success bool."""
    indexed = {row["id"]: row for row in call_rows}
    output = copy.deepcopy(selected)
    for result in output:
        if result["role"] != "diagnose" or result["enable_thinking"] is not False:
            continue
        try:
            proof = _bound_pair(indexed[result["call_id"]], call_rows, event_rows, contract)
        except _Unavailable as error:
            proof = {"status": "unknown", "reason": str(error)}
        except (ValueError, KeyError, TypeError, OverflowError):
            proof = {"status": "contradicted", "reason": "host_or_wire_evidence_conflict"}
        result["diagnosis_fallback_binding"] = proof
        if proof["status"] == "verified":
            result["allowed_mode_matches"] = True
            result["observed_reasoning_mode"] = "diagnose_nonthinking_after_bound_truncation"
            result["fallback_trigger_verified"] = True
            result["integrity_issues"] = [
                issue
                for issue in result["integrity_issues"]
                if issue != "reasoning_mode_outside_role_contract"
            ]
        elif proof["status"] == "unknown":
            result["allowed_mode_matches"] = None
            result["observed_reasoning_mode"] = "diagnose_nonthinking_unverified"
            result["integrity_issues"] = [
                issue
                for issue in result["integrity_issues"]
                if issue != "reasoning_mode_outside_role_contract"
            ]
            result["integrity_issues"].append("diagnosis_fallback_evidence_unknown")
        else:
            result["allowed_mode_matches"] = False
            result["integrity_issues"].append("diagnosis_fallback_evidence_contradicted")
    return output


def aggregate(rows):
    def counts(key, expected):
        return {
            "matching": sum(row[key] == expected for row in rows if row[key] is not None),
            "contradicted": sum(row[key] != expected for row in rows if row[key] is not None),
            "unknown": sum(row[key] is None for row in rows),
        }

    known_reasoning = [
        row["reasoning_tokens"] for row in rows if row["reasoning_tokens"] is not None
    ]
    unknown_reasoning = len(rows) - len(known_reasoning)
    return {
        "attempts": len(rows),
        "enable_thinking_true": counts("enable_thinking", True),
        "low_effort_present": counts("low_effort_present", True),
        "low_effort_true": counts("low_effort", True),
        "allowed_mode_expected": counts("allowed_mode_matches", True),
        "observed_reasoning_modes": dict(Counter(row["observed_reasoning_mode"] for row in rows)),
        "enable_thinking_true_scope": "descriptive count only; use allowed_mode_expected for the role contract",
        "output_cap_expected": counts("cap_matches", True),
        "output_cap_field_expected": counts("cap_field_matches", True),
        "reasoning_tokens_known_subtotal": sum(known_reasoning) if known_reasoning else None,
        "reasoning_tokens_unknown_attempts": unknown_reasoning,
        "reasoning_tokens_total": sum(known_reasoning) if rows and not unknown_reasoning else None,
        "finish_reasons": dict(Counter(row["finish_reason"] or "unknown" for row in rows)),
        "length_finish": counts("length_finish", True),
        "completion_reached_cap": counts("completion_reached_request_cap", True),
        "outcomes": dict(Counter(row["outcome"] for row in rows)),
        "integrity_issue_attempts": sum(bool(row["integrity_issues"]) for row in rows),
    }


def audit(execution_path, campaign_path, *, contract=None):
    require(
        contract_is_bound(contract), "R5 root/profile/capability contract is PENDING or unverified"
    )
    require(execution_path.resolve() == EXECUTION, "only explicit R6 execution receipt accepted")
    execution, execution_sha = bounded_json(execution_path)
    require(execution.get("fixed_acceptance_denominator") == 9, "nine-case execution required")
    require(execution.get("completed_utc"), "completed execution receipt required")
    references = execution.get("campaigns")
    require(isinstance(references, list) and len(references) == 1, "one new campaign required")
    ref = references[0]
    require(isinstance(ref, dict), "campaign reference object required")
    relative = Path(ref.get("path", ""))
    require(not relative.is_absolute() and ".." not in relative.parts, "unsafe campaign path")
    expected_path = ROOT / relative
    require(
        campaign_path.resolve() == expected_path.resolve(),
        "explicit campaign does not match receipt",
    )
    require(
        expected_path.is_relative_to(ROOT / "runs/evaluation/live"), "live campaign path required"
    )
    campaign, campaign_sha = bounded_json(campaign_path)
    require(campaign_sha == ref.get("sha256"), "campaign receipt hash mismatch")
    require(campaign.get("status") == "finished", "unfinished campaign")
    cases = campaign.get("rows")
    require(isinstance(cases, list) and len(cases) == 9, "nine rows required")
    require(all(isinstance(row, dict) for row in cases), "invalid scenario row")
    # The approved manifest supplies the fixed scenario IDs; no historical result is read.
    manifest, manifest_sha = bounded_json(ROOT / "eval/mvp_phase1_v2.yaml")
    planned = manifest.get("scenarios", [])
    ids = [row.get("id") for row in planned if isinstance(row, dict)]
    require(len(ids) == 9 and len(set(ids)) == 9, "fixed nine manifest slots required")
    require(
        {row.get("scenario_id") for row in cases} == set(ids),
        "scenario set differs from manifest",
    )
    require(campaign.get("manifest_sha256") == manifest_sha, "campaign manifest hash mismatch")
    require(
        all(row.get("condition") == "full_ultra" for row in cases), "unexpected campaign condition"
    )
    run_ids = [row.get("run_id") for row in cases]
    require(
        all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{32}", x) for x in run_ids),
        "real run IDs required",
    )
    require(len(set(run_ids)) == 9, "duplicate run IDs")
    con = sqlite3.connect((ROOT / "runs/headroom.db").as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        con.execute("BEGIN")
        placeholders = ",".join("?" for _ in run_ids)
        records = con.execute(
            f"SELECT id,run_id,model,role,created_at,data_json FROM llm_calls WHERE run_id IN ({placeholders}) ORDER BY id LIMIT ?",
            (*run_ids, MAX_CALLS + 1),
        ).fetchall()
        require(len(records) <= MAX_CALLS, "attempt count exceeds bound")
        observed = []
        selected = []
        call_rows = []
        for call_id, run_id, model, role, created_at, raw in records:
            require(
                isinstance(raw, str) and len(raw.encode()) <= 1024 * 1024,
                "call record exceeds bound",
            )
            observed.append([call_id, run_id, model, role, digest(raw.encode())])
            data = json.loads(raw)
            require(isinstance(data, dict), "invalid call JSON")
            call_rows.append(
                {
                    "id": call_id,
                    "run_id": run_id,
                    "model": model,
                    "role": role,
                    "created_at": created_at,
                    "data": data,
                }
            )
            if role not in ROLES:
                continue
            selected.append(
                analyze_call(
                    {"id": call_id, "run_id": run_id, "model": model, "role": role, "data": data},
                    contract=contract,
                )
            )
        event_records = con.execute(
            f"SELECT id,run_id,sequence,kind,created_at,data_json FROM events WHERE run_id IN ({placeholders}) ORDER BY run_id,sequence LIMIT ?",
            (*run_ids, MAX_EVENTS + 1),
        ).fetchall()
        require(len(event_records) <= MAX_EVENTS, "event count exceeds bound")
        event_rows, event_inventory = [], []
        for event_id, run_id, sequence, kind, created_at, raw in event_records:
            require(
                type(raw) is str and len(raw.encode()) <= 1024 * 1024,
                "event record exceeds bound",
            )
            data = json.loads(raw)
            require(type(data) is dict, "invalid event JSON")
            event_rows.append(
                {
                    "id": event_id,
                    "run_id": run_id,
                    "sequence": sequence,
                    "kind": kind,
                    "created_at": created_at,
                    "data": data,
                }
            )
            event_inventory.append(
                [event_id, run_id, sequence, kind, created_at, digest(raw.encode())]
            )
        selected = apply_diagnosis_fallbacks(selected, call_rows, event_rows, contract=contract)
        require(
            {row["run_id"] for row in selected} == set(run_ids),
            "not all nine runs have diagnosis/patch attempts",
        )
    finally:
        con.close()
    return {
        "schema": "headroom.reasoning_wire_audit.v4",
        "reasoning_mode_contract": "headroom.r6_reasoning_modes.v1",
        "expected_reasoning_modes_by_role": copy.deepcopy(ALLOWED_MODES),
        "verified_contract_pins": vars(contract.pins),
        "fallback_trigger_boundary": "Only diagnosis second requests may have a bound host truncation trigger. Patcher fallback triggers remain unproven; no provider-effect or improvement causality is claimed.",
        "server_low_effort_recognition_proven": False,
        "execution_sha256": execution_sha,
        "campaign_sha256": campaign_sha,
        "manifest_sha256": manifest_sha,
        "fixed_scenario_denominator": 9,
        "campaign_run_ids": run_ids,
        "all_roles_attempt_count": len(observed),
        "call_record_inventory_sha256": digest(canonical(observed)),
        "event_record_inventory_sha256": digest(canonical(event_inventory)),
        "event_record_count": len(event_inventory),
        "scope": "supplementary request and persisted usage audit; no acceptance score or billing recalculation",
        "request_evidence_boundary": "SHA-checked local httpx pre-transport copy, not provider ingestion proof",
        "finish_reason_boundary": "Per-call finish fields remain unknown when absent. The narrow diagnosis trigger is separately bound to whitelisted host failure metadata and exact Store usage; no finish is inferred from cap or reasoning-token counts.",
        "length_boundary": "Reaching max_tokens does not establish a length finish or explain parse failure",
        "causal_boundary": "Multiple contracts changed together; no accuracy change is attributed solely to reasoning",
        "hidden_reasoning_or_request_contents_copied": False,
        "new_provider_calls": 0,
        "new_gpu_runs": 0,
        "by_role": {
            role: aggregate([row for row in selected if row["role"] == role]) for role in ROLES
        },
        "attempts": selected,
    }


def self_test():
    payload = {
        "model": ROLES["diagnose"][0],
        "max_completion_tokens": 16384,
        "chat_template_kwargs": {"enable_thinking": True},
        "messages": [{"content": "PRIVATE_PROMPT"}],
    }
    captured = {
        "schema_version": 1,
        "capture_point": "httpx_pre_transport",
        "wire_body_sha256": "a" * 64,
        "wire_body_utf8_bytes": 100,
        "delivery_confirmed": False,
        "payload_status": "captured",
        "payload": payload,
        "stored_payload_sha256": digest(canonical(payload)),
    }
    row = {
        "id": 1,
        "run_id": "a" * 32,
        "model": payload["model"],
        "role": "diagnose",
        "data": {
            "role": "diagnose",
            "model": payload["model"],
            "outcome": "response",
            "request_evidence": captured,
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 16384,
                "total_tokens": 16386,
                "reasoning_tokens": 4096,
            },
            "reasoning_content": "PRIVATE_REASONING",
        },
    }
    checks = []

    def check(value):
        checks.append(bool(value))
        assert value

    result = analyze_call(row)
    check(result["enable_thinking"] is True and result["cap_matches"] is True)
    check(result["reasoning_tokens"] == 4096)
    check(result["completion_reached_request_cap"] is True and result["length_finish"] is None)
    check("PRIVATE" not in json.dumps(result))
    check(aggregate([result])["reasoning_tokens_total"] == 4096)
    for field_name, value in [
        ("reasoning_tokens", None),
        ("reasoning_tokens", True),
        ("reasoning_tokens", 16385),
    ]:
        changed = copy.deepcopy(row)
        changed["data"]["usage"][field_name] = value
        check(analyze_call(changed)["reasoning_tokens"] is None)
    changed = copy.deepcopy(row)
    changed["data"]["usage"]["reasoning_tokens"] = 0
    check(analyze_call(changed)["reasoning_tokens"] == 0)
    changed = copy.deepcopy(row)
    changed["data"]["finish_reason"] = "length"
    check(analyze_call(changed)["length_finish"] is True)
    changed = copy.deepcopy(row)
    changed["data"]["request_evidence"]["stored_payload_sha256"] = "b" * 64
    check(analyze_call(changed)["enable_thinking"] is None)
    changed = copy.deepcopy(row)
    changed["data"].pop("request_evidence")
    check(analyze_call(changed)["observed_output_cap_tokens"] is None)
    check(aggregate([analyze_call(changed)])["enable_thinking_true"]["unknown"] == 1)
    changed = copy.deepcopy(row)
    changed["data"].pop("usage")
    check(aggregate([analyze_call(changed)])["reasoning_tokens_total"] is None)
    check(aggregate([])["reasoning_tokens_total"] is None)
    for role, (model, cap) in ROLES.items():
        changed = copy.deepcopy(row)
        changed.update(role=role, model=model)
        changed["data"].update(role=role, model=model)
        evidence = changed["data"]["request_evidence"]
        body = evidence["payload"]
        body.update(model=model, max_completion_tokens=cap)
        evidence["stored_payload_sha256"] = digest(canonical(body))
        check(analyze_call(changed)["cap_matches"] is True)
        for value in (True, False):
            body["chat_template_kwargs"]["enable_thinking"] = value
            evidence["stored_payload_sha256"] = digest(canonical(body))
            actual = analyze_call(changed)
            check(actual["enable_thinking"] is value)
            expected = value if role == "diagnose" else not value
            check(actual["allowed_mode_matches"] is expected)
            summary = aggregate([actual])
            check(summary["allowed_mode_expected"]["matching"] == int(expected))
            check(summary["enable_thinking_true"]["matching"] == int(value))
        for value in (None, 0, "false"):
            body["chat_template_kwargs"]["enable_thinking"] = value
            evidence["stored_payload_sha256"] = digest(canonical(body))
            actual = analyze_call(changed)
            check(actual["allowed_mode_matches"] is False)
            check(aggregate([actual])["allowed_mode_expected"]["contradicted"] == 1)
        body.pop("chat_template_kwargs")
        evidence["stored_payload_sha256"] = digest(canonical(body))
        check(analyze_call(changed)["allowed_mode_matches"] is False)
    changed = copy.deepcopy(row)
    evidence = changed["data"]["request_evidence"]
    evidence["payload"]["max_completion_tokens"] = 4000
    evidence["stored_payload_sha256"] = digest(canonical(evidence["payload"]))
    check(analyze_call(changed)["cap_matches"] is False)
    evidence["payload"]["max_completion_tokens"] = True
    evidence["stored_payload_sha256"] = digest(canonical(evidence["payload"]))
    check(analyze_call(changed)["observed_output_cap_tokens"] is None)
    evidence["capture_point"] = "not_transport"
    check(analyze_call(changed)["enable_thinking"] is None)
    changed = copy.deepcopy(row)
    changed["data"]["request_evidence"]["payload_status"] = "redacted"
    check(analyze_call(changed)["enable_thinking"] is True)
    changed = copy.deepcopy(row)
    changed["data"]["finish_reason"] = "PRIVATE_REASONING"
    check(analyze_call(changed)["finish_reason"] is None)
    # Recognize the legacy spelling, but never accept it as the reviewed profile field.
    changed = copy.deepcopy(row)
    evidence = changed["data"]["request_evidence"]
    body = evidence["payload"]
    body["max_tokens"] = body.pop("max_completion_tokens")
    evidence["stored_payload_sha256"] = digest(canonical(body))
    result = analyze_call(changed)
    check(result["observed_output_cap_field"] == "max_tokens")
    check(result["observed_output_cap_tokens"] == 16384 and result["cap_matches"] is False)
    check("unexpected_output_cap_field" in result["integrity_issues"])
    body.pop("max_tokens")
    evidence["stored_payload_sha256"] = digest(canonical(body))
    check(analyze_call(changed)["cap_matches"] is None)
    for second_value in (16384, 4000):
        body.update(max_tokens=second_value, max_completion_tokens=16384)
        evidence["stored_payload_sha256"] = digest(canonical(body))
        result = analyze_call(changed)
        check(result["observed_output_cap_tokens"] is None and result["cap_matches"] is None)
        check("conflicting_output_cap_fields" in result["integrity_issues"])
    try:
        audit(OUT / "missing-execution.json", ROOT / "missing-campaign.json")
    except ValueError:
        check(True)
    else:
        check(False)
    return {
        "self_test": "passed",
        "checks": len(checks),
        "new_provider_calls": 0,
        "new_gpu_runs": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        require(
            args.execution is None and args.campaign is None and args.output is None,
            "self-test cannot use live inputs",
        )
        print(json.dumps(self_test(), indent=2))
        return
    require(
        args.execution is not None and args.campaign is not None and args.output is not None,
        "explicit completed R6 execution, campaign and fresh output required",
    )
    require(args.output.parent.resolve() == OUT, "output must be in R6 report directory")
    # Do not infer a verified contract from profile flags or CLI values.
    # Root will replace this guard with the frozen production verification adapter.
    require(False, "R6 production root/profile/capability contract adapter is PENDING")
    result = audit(args.execution, args.campaign, contract=None)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "attempts": len(result["attempts"]),
                "integrity_issue_attempts": sum(
                    bool(row["integrity_issues"]) for row in result["attempts"]
                ),
            }
        )
    )
    raise SystemExit(int(any(row["integrity_issues"] for row in result["attempts"])))


if __name__ == "__main__":
    main()
