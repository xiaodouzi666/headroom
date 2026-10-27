"""Pure R5 finance proofs composed with the unchanged pinned R4 validator.

No database/network/write operation. Live dynamic pins remain PENDING until
reviewed artifacts exist. Raw JSON bytes are required to bind exact file hashes.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
ROOT = Path("/home/xiaodouzi/workspace/headroom")
R4_SOURCE = "reports/acceptance-v2-r4-20261027/audit_mvp_v2_history_v2.py"
R4_SOURCE_SHA = "039f8dd9c86533b206fa62b6b167531e16cf81326ca6b75d0560bf11c7e01870"
BASE_PROFILE_SHA = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"
LIFETIME = Decimal("14.17775754")
DAILY = Decimal("9.99964904")
R4_FINAL_PROJECTION = "1860e237659fe3ec7a051ed897bca5859d30fdf69390fea95c3499bbfee0d48e"
R4_FINAL_RUNS = 124
R4_FINAL_ATTEMPTS = 690
PROBE_MAX_NET_USD = Decimal("0.0823")
R4_FIXED_PINS = {
    "audit": "086f7fe55e698e65f4c67028c945134e17faba546e9bb38b80fa333091f684c8",
    "execution": "6ec6a1d7aec27650f9107ee54463d75bd49d5d2e6ee1f3d5b6058c8add6b25d7",
    "campaign": "19528c254d1ae2c704c66fe8c8900a80c9dd1cafa6e8d545dea8248b894a1f95",
    "cap": "35cbf2e6ec929bb9ad99d37010cba579c46fb45838b8716c9255aa9f556695c3",
    "preflight": "1a488aeecf1d9ad8cf0831d8e5952f90a57539f80b673b832f05060f44dc7410",
}
SHA = re.compile(r"[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}")
_SEAL = object()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def need(condition, code):
    if condition is not True:
        raise ValueError("Finance proof rejected: " + code)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def parse(raw, expected_sha=None):
    need(type(raw) is bytes and len(raw) <= 4 * 1024 * 1024, "bounded_raw_json")
    if expected_sha is not None:
        need(
            type(expected_sha) is str and SHA.fullmatch(expected_sha) is not None,
            "frozen_sha_required",
        )
        need(digest(raw) == expected_sha, "artifact_sha")
    return json.loads(
        raw, object_pairs_hook=_pairs, parse_constant=lambda _: need(False, "nonfinite_json")
    )


def load_r4():
    """The sole I/O: load the exact reviewed R4 code, never its audit/main."""
    path = ROOT / R4_SOURCE
    need(not path.is_symlink() and digest(path.read_bytes()) == R4_SOURCE_SHA, "r4_source_pin")
    spec = importlib.util.spec_from_file_location("headroom_r4_finance_root", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R4 = load_r4()


def snapshot(raw, expected_sha=None):
    value = parse(raw, expected_sha)
    need(
        type(value) is dict
        and set(value) == {"budget_runs", "budget_attempts", "budget_retention_reviews"},
        "complete_snapshot_tables",
    )
    runs = R4.exact_rows(value["budget_runs"], R4.RUN_FIELDS)
    attempts = R4.exact_rows(value["budget_attempts"], R4.ATTEMPT_FIELDS)
    reviews = R4.exact_rows(value["budget_retention_reviews"], R4.REVIEW_FIELDS, "attempt_id")
    ids = {r["id"] for r in runs}
    need(all(type(r["id"]) is str and IDENTIFIER.fullmatch(r["id"]) for r in runs), "run_identity")
    need(all(a["run_id"] in ids for a in attempts), "orphan_attempt")
    return {"budget_runs": runs, "budget_attempts": attempts, "budget_retention_reviews": reviews}


def projection(value):
    return R4.ledger_projection(value["budget_runs"], value["budget_attempts"])


def summary(value):
    return R4.history_summary(value["budget_runs"], value["budget_attempts"])


def closed(value):
    runs, attempts = value["budget_runs"], value["budget_attempts"]
    need(all(r["status"] == "closed" and r["halt_reason"] is None for r in runs), "closed_runs")
    need(all(type(a["settled"]) is int and a["settled"] == 1 for a in attempts), "settled_attempts")
    totals = R4.totals(attempts)
    need(totals["pending"] == 0 and totals["unresolved"] == 0, "no_unresolved")
    need(R4.money(totals["conservative_charged_usd"]) <= LIFETIME, "lifetime_limit")
    need(R4.daily_ledger_bounds(runs, attempts)["accepted"] is True, "daily_limit")


@dataclass(frozen=True)
class VerifiedProbeFinance:
    schema: str
    probe_receipt_sha256: str
    run_id: str
    budget_attempt_id: str
    call_id: int
    store_path: str
    ledger_path: str
    before_ledger_sha256: str
    after_ledger_sha256: str
    calls_sha256: str
    base_profile_sha256: str
    conservative_charged_usd: str
    actual_usd: str | None
    _seal: Any = field(repr=False, compare=False)
    _fingerprint: str = field(default="", repr=False, compare=False)


def _proof_fingerprint(value):
    return digest(
        canonical({key: item for key, item in vars(value).items() if not key.startswith("_")})
    )


def is_verified_probe_finance(value):
    return (
        isinstance(value, VerifiedProbeFinance)
        and value._seal is _SEAL
        and value._fingerprint == _proof_fingerprint(value)
    )


def public_probe_finance(value):
    need(is_verified_probe_finance(value), "sealed_probe_finance_required")
    return {key: item for key, item in vars(value).items() if not key.startswith("_")}


def verify_probe_delta(
    before,
    after,
    calls,
    probe_receipt,
    *,
    before_sha256,
    after_sha256,
    probe_receipt_sha256,
    base_profile_sha256,
    base_profile_raw,
    request_payload_raw,
    expected_request_sha256,
):
    """Exact raw bytes in; sealed finance proof out. No arbitrary success booleans.

    calls is a list of one complete sanitized call for this probe run; schema
    below is deliberately narrow and must be frozen from the real store row.
    """
    need(
        type(expected_request_sha256) is str and SHA.fullmatch(expected_request_sha256) is not None,
        "independent_expected_request_pin",
    )
    need(base_profile_sha256 == BASE_PROFILE_SHA, "fixed_original_profile")
    old = snapshot(before, before_sha256)
    need(
        projection(old) == R4_FINAL_PROJECTION
        and len(old["budget_runs"]) == R4_FINAL_RUNS
        and len(old["budget_attempts"]) == R4_FINAL_ATTEMPTS,
        "fixed_r4_probe_start",
    )
    new = snapshot(after, after_sha256)
    receipt = parse(probe_receipt, probe_receipt_sha256)
    profile = parse(base_profile_raw, base_profile_sha256)
    records = parse(calls)
    need(type(records) is list and len(records) == 1, "exactly_one_call")
    call = records[0]
    required_call = {
        "id",
        "run_id",
        "budget_attempt_id",
        "created_at",
        "model",
        "response_model",
        "role",
        "attempt",
        "outcome",
        "http_status",
        "settled",
        "usage",
        "cost",
        "billing_status",
        "output_cap_field",
        "output_cap_tokens",
        "request_evidence",
    }
    need(type(call) is dict and set(call) == required_call, "call_metadata_schema")
    need(type(call["id"]) is int and call["id"] > 0, "call_id")
    run_id, attempt_id = call["run_id"], call["budget_attempt_id"]
    need(type(run_id) is str and IDENTIFIER.fullmatch(run_id) is not None, "probe_run_id")
    need(
        type(attempt_id) is str and re.fullmatch(r"[0-9a-f]{32}", attempt_id) is not None,
        "probe_attempt_id",
    )
    need(
        receipt.get("run_id") == run_id
        and receipt.get("budget_attempt_id") == attempt_id
        and type(receipt.get("call_id")) is int
        and receipt["call_id"] == call["id"],
        "receipt_mapping",
    )
    need(receipt.get("profile_sha256") == base_profile_sha256, "receipt_original_profile")
    need(
        receipt.get("ledger_path") == ".cache/budget.db"
        and receipt.get("store_path") == "runs/acceptance/headroom.db",
        "canonical_ledger_store",
    )
    need(
        profile["run_budget_mode"] == "actual_usage"
        and R4.money(profile["authorized_total_usd"]) == LIFETIME
        and R4.money(profile["available_credit_usd"]) == LIFETIME,
        "original_limits",
    )
    model = profile["models"]["super"]
    need(
        call["model"] == call["response_model"] == model["model_id"]
        and call["role"] == "patcher"
        and type(call["attempt"]) is int
        and call["attempt"] == 1
        and call["outcome"] == "response"
        and type(call["http_status"]) is int
        and call["http_status"] == 200
        and call["settled"] is True,
        "one_successful_dispatch",
    )
    old_runs = {r["id"]: r for r in old["budget_runs"]}
    new_runs = {r["id"]: r for r in new["budget_runs"]}
    old_attempts = {a["id"]: a for a in old["budget_attempts"]}
    new_attempts = {a["id"]: a for a in new["budget_attempts"]}
    need(run_id not in old_runs and set(new_runs) == set(old_runs) | {run_id}, "one_new_run")
    need(
        attempt_id not in old_attempts and set(new_attempts) == set(old_attempts) | {attempt_id},
        "one_new_attempt",
    )
    need(
        all(canonical(new_runs[k]) == canonical(v) for k, v in old_runs.items())
        and all(canonical(new_attempts[k]) == canonical(v) for k, v in old_attempts.items())
        and canonical(old["budget_retention_reviews"])
        == canonical(new["budget_retention_reviews"]),
        "all_prior_rows_preserved",
    )
    run, attempt = new_runs[run_id], new_attempts[attempt_id]
    need(
        attempt["run_id"] == run_id
        and run["budget_mode"] == "actual_usage"
        and run["status"] == "closed"
        and run["halt_reason"] is None
        and 0 < R4.money(run["limit_usd"]) <= PROBE_MAX_NET_USD,
        "probe_run_contract",
    )
    created = datetime.fromisoformat(call["created_at"])
    need(
        created.utcoffset() is not None
        and created.astimezone(UTC).date().isoformat() == run["day"],
        "probe_utc_day",
    )
    need(
        type(attempt["settled"]) is int
        and attempt["settled"] == 1
        and type(attempt["dispatched"]) is int
        and attempt["dispatched"] == 1
        and attempt["admission_kind"] == "verified_provider_bound"
        and attempt["review_sha256"] is None,
        "settled_verified_attempt",
    )
    evidence = call["request_evidence"]
    need(
        type(evidence) is dict
        and set(evidence)
        == {
            "capture_point",
            "wire_body_sha256",
            "wire_body_utf8_bytes",
            "stored_payload_sha256",
            "payload_status",
            "delivery_confirmed",
        },
        "safe_request_hashes_only",
    )
    need(
        evidence["capture_point"] == "httpx_pre_transport"
        and evidence["payload_status"] == "captured"
        and evidence["delivery_confirmed"] is False
        and type(evidence["wire_body_utf8_bytes"]) is int
        and evidence["wire_body_utf8_bytes"] > 0
        and all(
            type(evidence[k]) is str and SHA.fullmatch(evidence[k])
            for k in ("wire_body_sha256", "stored_payload_sha256")
        ),
        "request_hash_evidence",
    )
    payload = parse(request_payload_raw)
    need(
        type(payload) is dict
        and set(payload)
        == {
            "model",
            "messages",
            "max_completion_tokens",
            "response_format",
            "chat_template_kwargs",
        },
        "exact_probe_wire_fields",
    )
    need(
        payload["model"] == model["model_id"]
        and payload["max_completion_tokens"] == 4000
        and type(payload["max_completion_tokens"]) is int
        and payload["chat_template_kwargs"] == {"enable_thinking": True, "low_effort": True}
        and type(payload["chat_template_kwargs"].get("enable_thinking")) is bool
        and type(payload["chat_template_kwargs"].get("low_effort")) is bool
        and type(payload["messages"]) is list
        and bool(payload["messages"])
        and all(
            type(m) is dict
            and set(m) == {"role", "content"}
            and m["role"] in {"system", "user"}
            and type(m["content"]) is str
            for m in payload["messages"]
        )
        and type(payload["response_format"]) is dict
        and payload["response_format"].get("type") == "json_schema",
        "exact_low_effort_plain_text_contract",
    )
    stored = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    wire = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    fingerprint = digest(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
    )
    need(
        digest(stored) == digest(request_payload_raw) == evidence["stored_payload_sha256"]
        and digest(wire) == evidence["wire_body_sha256"]
        and len(wire) == evidence["wire_body_utf8_bytes"]
        and receipt.get("request_sha256") == fingerprint == expected_request_sha256,
        "exact_wire_and_reviewed_request_fingerprint",
    )
    billing = model["billing"]
    cap = call["output_cap_tokens"]
    need(
        billing["mode"] == "verified_provider_bound"
        and billing["verified"] is True
        and billing["output_cap_includes_reasoning"] is True
        and call["output_cap_field"] == billing["output_cap_field"]
        and type(cap) is int
        and cap == 4000
        and cap <= billing["max_completion_tokens"],
        "original_output_bound",
    )
    input_price = R4.money(model["input_usd_per_million"])
    output_price = R4.money(model["output_usd_per_million"])
    cached_price = R4.money(model["cached_input_usd_per_million"])
    upper = (
        billing["prompt_token_ceiling"] * max(input_price, cached_price) + cap * output_price
    ) / Decimal(1000000)
    need(R4.money(attempt["upper_usd"]) == upper <= PROBE_MAX_NET_USD, "full_provider_reservation")
    usage = call["usage"]
    need(
        type(usage) is dict
        and set(usage)
        == {
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "cached_tokens",
            "reasoning_tokens",
        },
        "usage_schema",
    )
    prompt, completion, total = (
        usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    need(
        all(type(v) is int and v >= 0 for v in (prompt, completion, total))
        and total == prompt + completion
        and prompt <= billing["prompt_token_ceiling"]
        and completion <= cap,
        "provider_usage_bounds",
    )
    cached, reasoning = usage["cached_tokens"], usage["reasoning_tokens"]
    need(cached is None or type(cached) is int and 0 <= cached <= prompt, "cache_usage")
    need(
        reasoning is None or type(reasoning) is int and 0 <= reasoning <= completion,
        "reasoning_usage",
    )
    need(
        receipt.get("scope") == "super_low_effort_schema_code_probe_v1"
        and receipt.get("provenance") == "live"
        and receipt.get("accepted") is True
        and receipt.get("verdict") == "request_combination_usable_in_one_sample"
        and receipt.get("finish_reason") == "stop"
        and receipt.get("response_model") == call["response_model"]
        and receipt.get("billing_status") == call["billing_status"]
        and all(
            type(receipt.get(key)) is int and receipt[key] == usage[key]
            for key in ("prompt_tokens", "completion_tokens", "reasoning_tokens")
        )
        and type(reasoning) is int
        and 0 < reasoning <= completion,
        "capability_receipt_matches_actual_call",
    )
    cost = call["cost"]
    charged = R4.money(attempt["charged_usd"])
    if cached is None:
        expected = (prompt * max(input_price, cached_price) + completion * output_price) / Decimal(
            1000000
        )
        need(
            attempt["actual_usd"] is None
            and attempt["charge_status"] == "upper_bound"
            and attempt["charge_basis"] == "verified_tariff_missing_cache_count"
            and call["billing_status"] == "bounded"
            and cost
            == {
                "usd": None,
                "status": "upper_bound",
                "reason": "missing_cached_token_usage",
                "upper_usd": str(charged),
                "basis": "verified_tariff_missing_cache_count",
            },
            "unknown_actual_retained",
        )
    else:
        expected = (
            (prompt - cached) * input_price + cached * cached_price + completion * output_price
        ) / Decimal(1000000)
        need(
            attempt["actual_usd"] is not None
            and R4.money(attempt["actual_usd"]) == expected
            and attempt["charge_status"] == "exact"
            and attempt["charge_basis"] is None
            and call["billing_status"] == "known"
            and cost == {"usd": attempt["actual_usd"], "status": "known", "reason": None},
            "known_actual",
        )
    need(charged == expected <= upper and charged <= R4.money(run["limit_usd"]), "charged_amount")
    closed(old)
    closed(new)
    proof = VerifiedProbeFinance(
        "headroom.verified-probe-finance.v1",
        probe_receipt_sha256,
        run_id,
        attempt_id,
        call["id"],
        "runs/acceptance/headroom.db",
        ".cache/budget.db",
        before_sha256,
        after_sha256,
        digest(calls),
        base_profile_sha256,
        str(charged),
        attempt["actual_usd"],
        _SEAL,
    )
    object.__setattr__(proof, "_fingerprint", _proof_fingerprint(proof))
    return proof


def verify_r4_extension(prior, after, *, campaign, audit, execution):
    """Pure exact addition check; caller separately binds fixed R4 artifact bytes."""
    before, final = snapshot(prior), snapshot(after)
    rows = campaign["rows"]
    need([row["scenario_id"] for row in rows] == list(R4.IDS), "r4_fixed_nine_slots")
    ids = [row["run_id"] for row in rows]
    need(
        len(ids) == len(set(ids)) == 9 and all(R4.UUID.fullmatch(x) for x in ids),
        "r4_unique_nine_runs",
    )
    refs = execution["campaigns"]
    need(
        len(refs) == 1
        and refs[0]["path"] == "runs/evaluation/live/20261027T002717226380Z-119f2528/campaign.json"
        and refs[0]["sha256"] == R4_FIXED_PINS["campaign"],
        "r4_execution_identity",
    )
    old_ids = {r["id"] for r in before["budget_runs"]}
    need(not old_ids.intersection(ids), "new_campaign_ids")
    prior_rows = [r for r in final["budget_runs"] if r["id"] not in ids]
    prior_attempts = [a for a in final["budget_attempts"] if a["run_id"] not in ids]
    need(
        canonical(prior_rows) == canonical(before["budget_runs"])
        and canonical(prior_attempts) == canonical(before["budget_attempts"])
        and canonical(final["budget_retention_reviews"])
        == canonical(before["budget_retention_reviews"]),
        "r4_all_prior_rows",
    )
    additions = [a for a in final["budget_attempts"] if a["run_id"] in ids]
    finance = audit["finance"]
    need(
        len(final["budget_runs"]) == 124
        and len(final["budget_attempts"]) == 690
        and len(additions) == 58,
        "r4_exact_additions",
    )
    need(
        projection(before) == finance["prior_projection"]
        and projection(final)
        == finance["all_time_projection_before"]
        == finance["all_time_projection_after"],
        "r4_finance_projections",
    )
    need(
        R4.same_totals(R4.totals(additions), finance["campaign"])
        and R4.same_totals(R4.totals(final["budget_attempts"]), finance["all_time"]),
        "r4_finance_amounts",
    )
    need(
        R4.money(finance["remaining_pool_usd"])
        == LIFETIME - R4.money(summary(final)["conservative_charged_usd"]),
        "r4_remaining",
    )
    closed(final)
    return {"accepted": True, "history_scores_used": False, "r4_after": summary(final)}


def verify_r4_root(
    *, legacy_documents, legacy_hashes, funding_args, r4_documents, r4_raw, r4_after
):
    """Invoke both unchanged R4 proofs before permitting the R4 campaign addition."""
    need(set(r4_raw) == set(R4_FIXED_PINS), "complete_r4_fixed_sources")
    for name, expected in R4_FIXED_PINS.items():
        need(parse(r4_raw[name], expected) == r4_documents[name], "r4_parsed_binding")
    original_after = legacy_documents["after"]
    prior_raw = canonical(original_after)
    history = R4.financial_history_binding(
        funding_args[0],
        r4_documents["cap"],
        r4_documents["preflight"],
        legacy_documents,
        legacy_hashes,
        original_after["budget_runs"],
        original_after["budget_attempts"],
        original_after["budget_retention_reviews"],
    )
    need(history["accepted"] is True, "unchanged_r4_history_root")
    args = copy.deepcopy(funding_args)
    args[4] = r4_documents["cap"]
    funding = R4.funding_binding(*args, history=history)
    need(funding["accepted"] is True, "unchanged_r4_funding_root")
    extension = verify_r4_extension(
        prior_raw,
        r4_after,
        campaign=r4_documents["campaign"],
        audit=r4_documents["audit"],
        execution=r4_documents["execution"],
    )
    need(projection(snapshot(r4_after)) == R4_FINAL_PROJECTION, "fixed_r4_final_projection")
    return {
        "schema": "headroom.r5-r4-finance-root.v1",
        "accepted": True,
        "r4_history": history,
        "r4_funding": funding,
        "r4_extension": extension,
        "historical_scores_used": False,
    }


def verify_r5_dispatch(after, cap, preflight, *, active_profile_path, active_profile_sha256):
    """R5 cap/preflight bind complete current history and the unchanged original limits."""
    value = snapshot(after)
    closed(value)
    totals = R4.totals(value["budget_attempts"])
    need(R4.same_summary(summary(value), cap["ledger"]), "r5_cap_full_history")
    need(
        cap["no_history_exclusions"] is True
        and cap["unknown_costs_retain_verified_bounds"] is True
        and cap["authorization"]["gift_only"] is True
        and cap["authorization"]["recharge"] is False
        and cap["authorization"]["new_budget_pool"] is False
        and R4.money(cap["pool_usd"]) == LIFETIME
        and R4.money(cap["daily_pool_usd"]) == DAILY
        and R4.money(cap["per_case_stop_usd"]) == Decimal("0.6")
        and R4.money(cap["campaign_max_usd"]) == Decimal("5.4"),
        "r5_original_limits",
    )
    need(
        type(active_profile_sha256) is str
        and SHA.fullmatch(active_profile_sha256) is not None
        and cap["profile_sha256"] == BASE_PROFILE_SHA
        and cap["active_profile_path"] == active_profile_path
        and cap["active_profile_sha256"] == active_profile_sha256
        and preflight["active_profile_sha256"] == active_profile_sha256
        and preflight["base_funding_profile_sha256"] == BASE_PROFILE_SHA,
        "r5_profile_binding",
    )
    before = preflight["budget_before"]
    argv = preflight["argv"]

    def option(key):
        need(type(argv) is list and argv.count(key) == 1, "unique_dispatch_option")
        return argv[argv.index(key) + 1]

    started = datetime.fromisoformat(preflight["started_utc"])
    need(started.utcoffset() is not None, "utc_dispatch")
    day = started.astimezone(UTC).date().isoformat()
    days = {r["id"]: r["day"] for r in value["budget_runs"]}
    day_charge = sum(
        (R4.money(a["charged_usd"]) for a in value["budget_attempts"] if days[a["run_id"]] == day),
        Decimal(0),
    )
    charged = R4.money(totals["conservative_charged_usd"])
    effective = min(Decimal("5.4"), LIFETIME - charged, DAILY - day_charge)
    need(
        before["projection_sha256"] == projection(value)
        and before["closed_runs"] == len(value["budget_runs"])
        and before["settled_attempts"] == len(value["budget_attempts"])
        and before["history_exclusions"] == []
        and before["utc_day"] == day
        and R4.money(before["conservative_usd"]) == charged
        and R4.money(before["known_subtotal_usd"]) == R4.money(totals["known_actual_subtotal_usd"])
        and before["actual_total_usd"] == totals["actual_total_usd"]
        and R4.money(before["day_conservative_usd"]) == day_charge
        and R4.money(before["all_time_limit_usd"]) == LIFETIME
        and R4.money(before["daily_limit_usd"]) == DAILY
        and R4.money(before["remaining_all_time_usd"]) == LIFETIME - charged
        and R4.money(before["remaining_day_usd"]) == DAILY - day_charge
        and R4.money(before["effective_campaign_usd"]) == effective >= Decimal("0.6")
        and R4.money(before["campaign_max_usd"]) == Decimal("5.4"),
        "r5_preflight_full_history",
    )
    need(
        option("--runtime-profile") == active_profile_path
        and R4.money(option("--budget")) == Decimal("0.6")
        and R4.money(option("--daily-budget")) == DAILY
        and R4.money(option("--campaign-budget")) == effective,
        "r5_dispatch_limits",
    )
    return {
        "schema": "headroom.r5-financial-dispatch.v1",
        "accepted": True,
        "snapshot": summary(value),
        "remaining_net_usd": str(LIFETIME - charged),
        "effective_campaign_usd": str(effective),
        "new_funding": False,
    }


def require_frozen_pins(pins, *, stage="audit"):
    """Use on the externally reviewed R5 manifest; PENDING can never pass."""
    required = {
        "r4_after",
        "probe_before",
        "probe_after",
        "probe_calls",
        "probe_receipt",
        "profile_transition",
        "new_profile",
        "r5_cap",
        "r5_preflight",
    }
    need(type(pins) is dict and set(pins) == required, "complete_dynamic_pins")
    need(stage in {"probe", "audit"}, "known_pin_stage")
    selected = (
        {"r4_after", "probe_before", "probe_after", "probe_calls", "probe_receipt"}
        if stage == "probe"
        else required
    )
    need(
        all(type(pins[key]) is str and SHA.fullmatch(pins[key]) is not None for key in selected),
        "pending_or_unknown_pins",
    )
    return True


def verify_root_and_probe(*, r4_inputs, probe_inputs, pins):
    """Pre-profile finance proof only. A positive result never admits R5 dispatch."""
    require_frozen_pins(pins, stage="probe")
    need(digest(r4_inputs["r4_after"]) == pins["r4_after"], "r4_snapshot_pin")
    need(
        probe_inputs["before_sha256"] == pins["probe_before"]
        and probe_inputs["after_sha256"] == pins["probe_after"]
        and probe_inputs["probe_receipt_sha256"] == pins["probe_receipt"]
        and digest(probe_inputs["calls"]) == pins["probe_calls"],
        "probe_frozen_pins",
    )
    need(probe_inputs["base_profile_sha256"] == BASE_PROFILE_SHA, "probe_original_funding_profile")
    root = verify_r4_root(**r4_inputs)
    need(
        canonical(snapshot(probe_inputs["before"], pins["probe_before"]))
        == canonical(snapshot(r4_inputs["r4_after"], pins["r4_after"])),
        "probe_begins_at_exact_r4_end",
    )
    proof = verify_probe_delta(**probe_inputs)
    return {
        "schema": "headroom.r5-root-and-probe-finance.v1",
        "scope": "pre_profile_probe_finance_only",
        "accepted": True,
        "r4_root": root,
        "probe_finance": proof,
        "dispatch_permitted": False,
        "profile_transition_verified": False,
        "historical_scores_used": False,
    }
