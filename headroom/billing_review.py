"""Explicit, read-only preparation and reviewed retention of one historical charge.

No keys, provider calls, or actual-charge edits. Default CLI operation only prints a
proposal. Execution requires an independently reviewed exact receipt SHA256.
"""

import argparse
import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from headroom.budget import BudgetLedger, money
from headroom.config import ROLE_MODELS
from headroom.llm.cost import Usage, calculate_cost
from headroom.runtime import BillingBound, read_live_profile

ATTEMPT_FIELDS = (
    "id",
    "run_id",
    "upper_usd",
    "charged_usd",
    "actual_usd",
    "settled",
    "admission_kind",
    "dispatched",
)


def _read(path):
    path = Path(path).resolve()
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Review input must be a regular file")
        raw = handle.read(1048577)
    if len(raw) > 1048576:
        raise ValueError("Review input exceeds its limit")
    return raw


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


@contextmanager
def _ro(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    try:
        yield conn
    finally:
        conn.close()


def prepare_retention(*, ledger_path, store_path, profile_path, run_id, attempt_id):
    """Bind one unambiguous historical response to its unchanged full reservation."""
    with _ro(ledger_path) as ledger:
        run_row = ledger.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
        attempts = list(ledger.execute("SELECT * FROM budget_attempts WHERE run_id=?", (run_id,)))
    if run_row is None or len(attempts) != 1 or attempts[0]["id"] != attempt_id:
        raise ValueError("Review requires one exact run/attempt; ambiguous mappings are refused")
    run, attempt = dict(run_row), dict(attempts[0])
    if (
        run["status"] != "closed"
        or run["halt_reason"] != "provider_charge_unknown"
        or attempt["actual_usd"] is not None
        or attempt["settled"] != 1
        or attempt["dispatched"] != 1
        or attempt["admission_kind"] != "verified_provider_bound"
        or money(attempt["charged_usd"]) != money(attempt["upper_usd"])
        or attempt.get("charge_status", "unknown") != "unknown"
        or attempt.get("review_sha256") is not None
    ):
        raise ValueError("Target is not a retained strict unknown charge")
    with _ro(store_path) as store:
        calls = list(store.execute("SELECT * FROM llm_calls WHERE run_id=?", (run_id,)))
    if len(calls) != 1:
        raise ValueError("Review requires exactly one corresponding persisted call")
    call = dict(calls[0])
    data = json.loads(call["data_json"])
    cost = data.get("cost", {})
    usage_data = data.get("usage")
    if not isinstance(usage_data, dict):
        raise TypeError("Valid complete usage is required")
    usage = Usage(**usage_data)
    if (
        data.get("outcome") != "response"
        or data.get("http_status") != 200
        or data.get("settled") is not True
        or data.get("attempt") != 1
        or data.get("model") != call["model"]
        or data.get("response_model") != call["model"]
        or data.get("role") != call["role"]
        or call["cost_usd"] is not None
        or cost.get("usd") is not None
        or cost.get("status") != "unknown"
        or cost.get("reason") != "missing_cached_token_usage"
        or usage.cached_tokens is not None
        or data.get("admission_kind") != "verified_provider_bound"
        or (data.get("budget_attempt_id") is not None and data["budget_attempt_id"] != attempt_id)
        or call["input_tokens"] != usage.prompt_tokens
        or call["output_tokens"] != usage.completion_tokens
    ):
        raise ValueError("Historical identity, usage or unknown reason is not reviewable")
    raw_profile = _read(profile_path)
    profile = read_live_profile(profile_path)
    if _read(profile_path) != raw_profile:
        raise ValueError("Profile changed while preparing review")
    model_role = ROLE_MODELS.get(call["role"])
    if model_role not in profile.models:
        raise ValueError("Unknown call role")
    item = profile.models[model_role]
    billing = item.billing
    if not isinstance(billing, BillingBound) or item.model_id != call["model"]:
        raise ValueError("The exact model needs a verified provider bound")
    spec = profile.runtime_config().models[model_role]
    output_cap = data.get("output_cap_tokens")
    if type(output_cap) is not int or output_cap < 1:
        raise ValueError("Historical output cap is invalid")
    expected_upper = billing.upper_usd(spec, {"messages": [], billing.output_cap_field: output_cap})
    if (
        data.get("output_cap_field") != billing.output_cap_field
        or data.get("provider_prompt_token_ceiling") != billing.prompt_token_ceiling
        or usage.prompt_tokens > billing.prompt_token_ceiling
        or usage.completion_tokens > output_cap
        or money(data.get("reservation_usd")) != expected_upper
        or money(data.get("provider_cost_upper_usd")) != expected_upper
        or money(attempt["upper_usd"]) != expected_upper
    ):
        raise ValueError("Historical cap or reservation does not match reviewed bounds")
    calculated = calculate_cost(usage, spec.pricing)
    if calculated.status != "upper_bound" or calculated.upper_usd > expected_upper:
        raise ValueError("The observed usage cannot be bounded by this reservation")
    return {
        "schema": "headroom.retained-charge-review.v1",
        "reason": "missing_cached_token_usage",
        "ledger_path": str(Path(ledger_path).resolve()),
        "store_path": str(Path(store_path).resolve()),
        "profile_path": str(Path(profile_path).resolve()),
        "profile_sha256": hashlib.sha256(raw_profile).hexdigest(),
        "run_id": run_id,
        "attempt_id": attempt_id,
        "expected_attempt": {key: attempt[key] for key in ATTEMPT_FIELDS},
        "expected_run": {
            key: run[key]
            for key in ("id", "day", "limit_usd", "status", "halt_reason", "budget_mode")
        },
        "call_id": call["id"],
        "call_data_sha256": hashlib.sha256(call["data_json"].encode()).hexdigest(),
        "response_model": data["response_model"],
        "usage": usage_data,
        "tariff": {
            "input_per_million": str(spec.pricing.input_per_million),
            "cached_input_per_million": str(spec.pricing.cached_input_per_million),
            "output_per_million": str(spec.pricing.output_per_million),
        },
        "observed_usage_upper_usd": str(calculated.upper_usd),
        "retained_full_upper_usd": attempt["upper_usd"],
        "actual_usd": None,
        "historical_result_reassessment": False,
        "authorized_total_usd": profile.authorized_total_usd,
    }


def execute_retention(receipt_path, *, expected_sha256, reviewed_by, daily_limit):
    """Explicit mutation of one reviewed ledger entry; never called during preparation."""
    if not isinstance(reviewed_by, str) or not reviewed_by.strip():
        raise ValueError("An explicit reviewer is required")
    raw = _read(receipt_path)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("Receipt differs from the explicitly reviewed SHA256")
    receipt = json.loads(raw)
    kwargs = {
        key: receipt[key]
        for key in ("ledger_path", "store_path", "profile_path", "run_id", "attempt_id")
    }
    current = prepare_retention(**kwargs)
    if _canonical(current) != _canonical(receipt):
        raise ValueError("Review evidence changed; prepare and review again")
    ledger = BudgetLedger(
        receipt["ledger_path"],
        daily_limit=daily_limit,
        total_limit=receipt["authorized_total_usd"],
    )
    # Recheck after migration/lock wait as well. The ledger method atomically
    # compares the complete original attempt and the specific permitted halt.
    current = prepare_retention(**kwargs)
    if _canonical(current) != _canonical(receipt):
        raise ValueError("Review target changed before its transaction")
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
    parser.add_argument("--receipt")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--reviewed-by")
    parser.add_argument("--daily-limit")
    parser.add_argument("--ledger")
    parser.add_argument("--store")
    parser.add_argument("--profile")
    parser.add_argument("--run-id")
    parser.add_argument("--attempt-id")
    args = parser.parse_args()
    try:
        if args.execute:
            if not all((args.receipt, args.expected_sha256, args.reviewed_by, args.daily_limit)):
                raise ValueError("Execution needs receipt, exact SHA256, reviewer and daily limit")
            result = execute_retention(
                args.receipt,
                expected_sha256=args.expected_sha256,
                reviewed_by=args.reviewed_by,
                daily_limit=args.daily_limit,
            )
        else:
            if not all((args.ledger, args.store, args.profile, args.run_id, args.attempt_id)):
                raise ValueError("Preparation needs exact ledger/store/profile/run/attempt")
            result = prepare_retention(
                ledger_path=args.ledger,
                store_path=args.store,
                profile_path=args.profile,
                run_id=args.run_id,
                attempt_id=args.attempt_id,
            )
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        parser.exit(2, "Retention review refused: " + type(error).__name__ + "\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
