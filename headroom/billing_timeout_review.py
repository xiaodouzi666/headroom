"""Review one transport timeout without usage by retaining its entire verified reservation.

Preparation is read-only. Execution needs an independently reviewed exact receipt
hash. No provider calls, refunds, actual-cost estimates or historical rewrites.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from headroom.billing_review import ATTEMPT_FIELDS, _canonical, _read, _ro
from headroom.budget import BudgetLedger, money
from headroom.config import ROLE_MODELS
from headroom.runtime import BillingBound, RuntimeNotReady, read_live_profile

SCHEMA = "headroom.timeout-full-retention.v1"
REASON = "transport_timeout_missing_usage_full_reservation"
RUN_FIELDS = ("id", "day", "limit_usd", "status", "halt_reason", "budget_mode")
CALL_FIELDS = (
    "id",
    "run_id",
    "model",
    "role",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "created_at",
)
FEES = {"image", "price_per_video_second", "request", "price_per_minute"}


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _call_identity(call):
    return {
        **{key: call[key] for key in CALL_FIELDS},
        "data_sha256": hashlib.sha256(call["data_json"].encode()).hexdigest(),
    }


def _request(data, call):
    evidence = data.get("request_evidence")
    if not isinstance(evidence, dict) or (
        evidence.get("schema_version") != 1
        or evidence.get("capture_point") != "httpx_pre_transport"
        or evidence.get("payload_status") != "captured"
        or evidence.get("delivery_confirmed") is not False
        or any(evidence.get(key) != data.get(key) for key in ("model", "role", "attempt"))
    ):
        raise ValueError("Exact unredacted prepared-request evidence is required")
    payload = evidence.get("payload")
    allowed = {
        "model",
        "messages",
        "max_completion_tokens",
        "response_format",
        "chat_template_kwargs",
        "n",
        "stream",
    }
    if not isinstance(payload, dict) or not set(payload) <= allowed:
        raise ValueError("Request contains an unreviewed parameter")
    if (
        payload.get("model") != call["model"]
        or type(payload.get("n", 1)) is not int
        or payload.get("n", 1) != 1
        or payload.get("stream", False) is not False
        or type(payload.get("max_completion_tokens")) is not int
        or payload["max_completion_tokens"] <= 0
    ):
        raise ValueError("Only one non-streaming capped completion is reviewable")
    messages = payload.get("messages")
    if (
        not isinstance(messages, list)
        or not messages
        or any(
            not isinstance(message, dict)
            or set(message) != {"role", "content"}
            or message["role"] not in {"system", "user", "assistant"}
            or not isinstance(message["content"], str)
            for message in messages
        )
    ):
        raise ValueError("Only plain text messages are reviewable")
    template = payload.get("chat_template_kwargs", {})
    if (
        not isinstance(template, dict)
        or set(template) - {"enable_thinking"}
        or any(type(value) is not bool for value in template.values())
    ):
        raise ValueError("Unreviewed chat template parameters")
    canonical = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    wire = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if (
        hashlib.sha256(canonical).hexdigest() != evidence.get("stored_payload_sha256")
        or hashlib.sha256(wire).hexdigest() != evidence.get("wire_body_sha256")
        or len(wire) != evidence.get("wire_body_utf8_bytes")
    ):
        raise ValueError("Captured payload does not reconstruct the exact prepared wire body")
    return payload, {
        key: evidence[key]
        for key in (
            "capture_point",
            "wire_body_sha256",
            "wire_body_utf8_bytes",
            "stored_payload_sha256",
            "payload_status",
            "delivery_confirmed",
        )
    }


def prepare_retention(*, ledger_path, store_path, profile_path, pricing_path, run_id, attempt_id):
    """Prepare a receipt without modifying either database or sending any request."""
    with _ro(ledger_path) as ledger:
        row = ledger.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
        attempts = [
            dict(item)
            for item in ledger.execute(
                "SELECT * FROM budget_attempts WHERE run_id=? ORDER BY id", (run_id,)
            )
        ]
    if row is None or len(attempts) != 1:
        raise ValueError("Exactly one closed run attempt is required")
    run = dict(row)
    by_id = {item["id"]: item for item in attempts}
    attempt = by_id.get(attempt_id)
    if attempt is None or (
        run["status"] != "closed"
        or run["halt_reason"] != "provider_charge_unknown"
        or attempt["actual_usd"] is not None
        or attempt["charge_status"] != "unknown"
        or attempt["review_sha256"] is not None
        or money(attempt["charged_usd"]) != money(attempt["upper_usd"])
    ):
        raise ValueError("Target must be a closed strict unknown with its full charge retained")
    for item in attempts:
        if (
            item["settled"] != 1
            or item["dispatched"] != 1
            or item["admission_kind"] != "verified_provider_bound"
            or money(item["charged_usd"]) > money(item["upper_usd"])
        ):
            raise ValueError("Every run attempt must be settled within a strict bound")
        if item["id"] != attempt_id and not (
            (
                item["charge_status"] == "exact"
                and item["actual_usd"] is not None
                and money(item["charged_usd"]) == money(item["actual_usd"])
            )
            or (
                item["charge_status"] == "upper_bound"
                and item["actual_usd"] is None
                and item["charge_basis"] == "verified_tariff_missing_cache_count"
            )
        ):
            raise ValueError("All other run attempts must already be settled and bounded")
    with _ro(store_path) as store:
        calls = [
            dict(item)
            for item in store.execute(
                "SELECT * FROM llm_calls WHERE run_id=? ORDER BY id", (run_id,)
            )
        ]
    if len(calls) != 1:
        raise ValueError("Exactly one corresponding timeout call is required")
    mapped = {}
    for call in calls:
        data = json.loads(call["data_json"])
        identity = data.get("budget_attempt_id")
        if (
            identity not in by_id
            or identity in mapped
            or (
                data.get("settled") is not True
                or data.get("model") != call["model"]
                or data.get("role") != call["role"]
                or data.get("admission_kind") != "verified_provider_bound"
                or money(data.get("reservation_usd")) != money(by_id[identity]["upper_usd"])
            )
        ):
            raise ValueError("Every persisted call needs one exact, settled ledger mapping")
        mapped[identity] = (call, data)
    if set(mapped) != set(by_id):
        raise ValueError("Run calls and attempts are not a bijection")
    call, data = mapped[attempt_id]
    cost = data.get("cost")
    if (
        call["id"] != calls[-1]["id"]
        or not isinstance(cost, dict)
        or (
            data.get("outcome") != "timeout"
            or data.get("http_status") is not None
            or data.get("attempt") != 1
            or data.get("usage") is not None
            or data.get("response_model") is not None
            or any(call[key] is not None for key in ("input_tokens", "output_tokens", "cost_usd"))
            or cost.get("usd") is not None
            or cost.get("status") != "unknown"
            or cost.get("reason") != "missing_or_invalid_usage"
            or data.get("billing_status") != "unresolved"
        )
    ):
        raise ValueError(
            "Only the final first-attempt transport timeout without usage is reviewable"
        )
    payload, request = _request(data, call)
    raw_profile, raw_pricing = _read(profile_path), _read(pricing_path)
    profile = read_live_profile(profile_path)
    pricing = json.loads(raw_pricing)
    model_role = ROLE_MODELS.get(call["role"])
    if model_role not in profile.models:
        raise ValueError("Unknown model role")
    item = profile.models[model_role]
    billing = item.billing
    if not isinstance(billing, BillingBound) or item.model_id != call["model"]:
        raise ValueError("Exact model requires a verified provider bound")
    spec = profile.runtime_config().models[model_role]
    tariff = pricing.get("models", {}).get(call["model"], {})
    fees = tariff.get("fee_components_per_request")
    if (
        pricing.get("verified") is not True
        or pricing.get("output_caps_include_reasoning") is not True
        or not isinstance(fees, dict)
        or set(fees) != FEES
        or any(money(value) != 0 for value in fees.values())
        or tariff.get("output_cap_field") != "max_completion_tokens"
        or tariff.get("prompt_token_ceiling") != billing.prompt_token_ceiling
        or billing.output_cap_field != "max_completion_tokens"
        or money(tariff.get("input_usd_per_million")) != spec.pricing.input_per_million
        or money(tariff.get("output_usd_per_million")) != spec.pricing.output_per_million
        or money(tariff.get("cached_input_usd_per_million"))
        != spec.pricing.cached_input_per_million
    ):
        raise ValueError("Reviewed tariff and zero ancillary fees must match the exact profile")
    upper = billing.upper_usd(spec, payload)
    cap = payload["max_completion_tokens"]
    if (
        data.get("output_cap_field") != "max_completion_tokens"
        or data.get("output_cap_tokens") != cap
        or data.get("provider_prompt_token_ceiling") != billing.prompt_token_ceiling
        or any(
            money(value) != upper
            for value in (
                data.get("provider_cost_upper_usd"),
                data.get("reservation_usd"),
                attempt["upper_usd"],
                attempt["charged_usd"],
            )
        )
        or _read(profile_path) != raw_profile
        or _read(pricing_path) != raw_pricing
    ):
        raise ValueError("Historical cap, full reservation or reviewed files changed")
    call_rows = [_call_identity(row) for row in calls]
    return {
        "schema": SCHEMA,
        "reason": REASON,
        **{
            key: str(Path(value).resolve())
            for key, value in (
                ("ledger_path", ledger_path),
                ("store_path", store_path),
                ("profile_path", profile_path),
                ("pricing_path", pricing_path),
            )
        },
        "profile_sha256": hashlib.sha256(raw_profile).hexdigest(),
        "pricing_sha256": hashlib.sha256(raw_pricing).hexdigest(),
        "run_id": run_id,
        "attempt_id": attempt_id,
        "expected_run": {key: run[key] for key in RUN_FIELDS},
        "expected_attempt": {key: attempt[key] for key in ATTEMPT_FIELDS},
        "expected_attempts": attempts,
        "expected_calls": call_rows,
        "run_mapping_sha256": _digest({"attempts": attempts, "calls": call_rows}),
        "call_id": call["id"],
        "request": request,
        "model": call["model"],
        "outcome": "timeout",
        "http_status": None,
        "usage": None,
        "output_cap_field": "max_completion_tokens",
        "output_cap_tokens": cap,
        "provider_prompt_token_ceiling": billing.prompt_token_ceiling,
        "tariff": tariff,
        "retained_full_upper_usd": attempt["upper_usd"],
        "actual_usd": None,
        "historical_result_reassessment": False,
        "authorized_total_usd": profile.authorized_total_usd,
    }


def execute_retention(receipt_path, *, expected_sha256, reviewed_by, daily_limit):
    """Apply exactly one reviewed retention; never release any part of its charge."""
    if not isinstance(reviewed_by, str) or not reviewed_by.strip():
        raise ValueError("An explicit reviewer is required")
    raw = _read(receipt_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Receipt differs from the explicitly reviewed SHA256")
    receipt = json.loads(raw)
    kwargs = {
        key: receipt[key]
        for key in (
            "ledger_path",
            "store_path",
            "profile_path",
            "pricing_path",
            "run_id",
            "attempt_id",
        )
    }
    if _canonical(prepare_retention(**kwargs)) != _canonical(receipt):
        raise ValueError("Review evidence changed; prepare and review again")
    ledger = BudgetLedger(
        receipt["ledger_path"],
        daily_limit=daily_limit,
        total_limit=receipt["authorized_total_usd"],
    )
    if _canonical(prepare_retention(**kwargs)) != _canonical(receipt):
        raise ValueError("Review evidence changed before its transaction")
    return ledger.review_retained(
        receipt["run_id"],
        receipt["attempt_id"],
        expected_attempt=receipt["expected_attempt"],
        receipt_sha256=digest,
        evidence={**receipt, "reviewed_by": reviewed_by.strip()},
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    for name in (
        "receipt",
        "expected-sha256",
        "reviewed-by",
        "daily-limit",
        "ledger",
        "store",
        "profile",
        "pricing",
        "run-id",
        "attempt-id",
    ):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    try:
        if args.execute:
            if not all((args.receipt, args.expected_sha256, args.reviewed_by, args.daily_limit)):
                raise ValueError("Execution needs exact receipt SHA256, reviewer and daily limit")
            result = execute_retention(
                args.receipt,
                expected_sha256=args.expected_sha256,
                reviewed_by=args.reviewed_by,
                daily_limit=args.daily_limit,
            )
        else:
            if not all(
                (args.ledger, args.store, args.profile, args.pricing, args.run_id, args.attempt_id)
            ):
                raise ValueError("Preparation needs ledger/store/profile/pricing/run/attempt")
            result = prepare_retention(
                ledger_path=args.ledger,
                store_path=args.store,
                profile_path=args.profile,
                pricing_path=args.pricing,
                run_id=args.run_id,
                attempt_id=args.attempt_id,
            )
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, RuntimeNotReady):
        parser.exit(2, "transport timeout retention review refused\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
