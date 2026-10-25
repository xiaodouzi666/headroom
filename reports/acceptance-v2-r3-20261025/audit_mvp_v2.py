"""Independent, read-only audit of the one approved v2 nine-case campaign.

Only versioned audit output may be written. No provider, GPU, subprocess, pickle,
profile construction, Store constructor, or BudgetLedger constructor is used.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/acceptance-v2-r3-20261025"
MANIFEST = "eval/mvp_phase1_v2.yaml"
IDS = (
    "s1_batch_too_big",
    "s2_capacity_v2",
    "s3_eval_no_grad_missing",
    "s4_loss_accumulation_graph",
    "s5_fragmentation_varlen",
    "s6_full_vocab_logits_fp32",
    "s7_frozen_params_optimizer_state",
    "s8_two_models_resident",
    "nanogpt",
)
POOL = Decimal("14.17775754")
DAILY_POOL = Decimal("9.99964904")
PROFILE = ".cache/tokenfactory-runtime-v2-r2.json"
OLD_PROFILE = ".cache/tokenfactory-runtime.json"
FUNDING_PATH = "reports/acceptance-v2-r2-20261025/funding-transition.json"
RETIREMENT_PATH = "reports/acceptance-v2-r2-20261025/external-probe-retirement.json"
ALLOCATION_PATH = "reports/live-campaign-20261025/allocation.json"
BUDGET_HELPER_PATH = "reports/acceptance-v2-r3-20261025/ledger_state_r2.py"
HISTORICAL_HELPER_PATH = ".cache/setup/run_mvp_v7.py"
FUNDING_PINS = [
    {"path": PROFILE, "sha256": "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"},
    {
        "path": OLD_PROFILE,
        "sha256": "a15ee9a357b4e0c41aeb46219081066c4d5a2299a777f8f87127dde60118026c",
    },
    {
        "path": FUNDING_PATH,
        "sha256": "cc31a24d0a6cdc91413b4521ef0d8b1f86a04e76ceb32fed3081d0998348784d",
    },
    {
        "path": RETIREMENT_PATH,
        "sha256": "43befc9c20868610943273d2db98b6d4247c8d0fcd15ef6a0b18094ac9a8fdbe",
    },
    {
        "path": ALLOCATION_PATH,
        "sha256": "3db9675ddc542bb2ba42f9929748deea64d3810e913f13c303615e78f88203c0",
    },
    {
        "path": BUDGET_HELPER_PATH,
        "sha256": "b27d8c04117502b65c7be0501cdd86208bb17d50b7ee2c668ed161a130baff6f",
    },
    {
        "path": HISTORICAL_HELPER_PATH,
        "sha256": "7fecfdc73a9f5a9f83a6daf422d5d34f5decca4ef89c45c1de670de9898d49b5",
    },
]
RETIRED_ENTRYPOINTS = {
    "scripts/probe_models.py",
    ".cache/setup/probe-catalogue-frozen-20261025.py",
    ".cache/setup/probe_models-capability-matrix-ad82a776.py",
    ".cache/portable-checkout/20261024T130927Z-e8cf25eb/checkout/scripts/probe_models.py",
    ".cache/literal-cli-v6/scripts/probe_models.py",
    ".cache/source-spans-v6/scripts/probe_models.py",
    ".cache/feedback-v7/scripts/probe_models.py",
}
HEX = re.compile(r"^[0-9a-f]{64}$")
UUID = re.compile(r"^[0-9a-f]{32}$")
HELPERS = {
    "base": (
        ".cache/setup/audit_mvp_acceptance_v2.py",
        "4f937a04819285578cc714bee7eac5f68ef91f12cdda8a6b6941d6ed8b30b745",
    ),
    "cli": (
        ".cache/setup/audit_literal_cli_campaign.py",
        "0da858eafeeced69f98f66dd480d5696a84de3a23103533be1247348ec8926aa",
    ),
    "span": (
        ".cache/setup/audit_source_span_campaign_v2.py",
        "c7762109878024c6dd842ec5cb7b8e3ac7bd21627ab26c1ee78197452c1c2a76",
    ),
}
REF_DEFAULTS = {
    "strategy": "legacy_small_batch",
    "cpu_saved_tensor_limit_bytes": 16 * 1024**3,
    "disk_saved_tensor_limit_bytes": 0,
    "max_seconds": None,
}
EXTRA_OPTIONS = {
    "--allocator-conf",
    "--reference-strategy",
    "--reference-cpu-bytes",
    "--reference-disk-bytes",
    "--reference-max-seconds",
}
BASE_GATES = (
    "real_live_provenance",
    "run_identity_consistent",
    "source_hash_matches_manifest",
    "report_json_and_markdown",
    "harness_child_exit_zero",
    "owned_cleanup_verified",
    "cost_complete_and_consistent",
    "wall_within_480_seconds",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def tri(values):
    values = list(values)
    return False if False in values else None if not values or None in values else True


def money(value):
    if type(value) not in (str, int):
        raise ValueError("Exact money required")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise ValueError("Nonnegative finite money required")
    return number


def driver_funding_pins(source):
    """Parse literal pins without importing or running the dispatch driver."""
    wanted = {"PROFILE", "PROFILE_SHA", "FUNDING_SHA", "BUDGET_HELPER_SHA"}
    values = {}
    try:
        for node in ast.parse(source).body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in wanted:
                if target.id in values or not isinstance(node.value, ast.Constant):
                    return {}
                values[target.id] = node.value.value
    except (SyntaxError, TypeError, ValueError):
        return {}
    return values if set(values) == wanted and all(type(v) is str for v in values.values()) else {}


def funding_binding(funding, retirement, allocation, profile, cap, driver, hashes):
    """Independent exact monetary and provenance checks; no I/O or execution."""
    checks = {}
    try:
        if not all(
            isinstance(v, dict)
            for v in (funding, retirement, allocation, profile, cap, driver, hashes)
        ):
            raise ValueError("complete funding documents required")
        expected = {row["path"]: row["sha256"] for row in FUNDING_PINS}
        checks["funding_sources_pinned"] = all(hashes.get(k) == v for k, v in expected.items())
        checks["driver_profile_helper_funding_pins"] = driver == {
            "PROFILE": PROFILE,
            "PROFILE_SHA": expected[PROFILE],
            "FUNDING_SHA": expected[FUNDING_PATH],
            "BUDGET_HELPER_SHA": expected[BUDGET_HELPER_PATH],
        }
        checks["closed_zero_sum_partition"] = (
            funding["status"] == "external_allocation_closed"
            and money(funding["total_work_net_usd"]) == 16
            and money(funding["original_runtime_lifetime_net_usd"]) == DAILY_POOL
            and money(funding["runtime_lifetime_net_usd"]) == POOL
            and money(funding["runtime_daily_net_usd"]) == DAILY_POOL
            and money(funding["transferred_unused_external_net_usd"]) == POOL - DAILY_POOL
            and money(funding["external_retained_net_usd"]) == Decimal("1.82224246")
            and money(funding["external_retained_net_usd"]) + POOL == 16
            and money(funding["external_future_net_usd"]) == 0
            and funding["new_money"] is False
            and funding["recharge"] is False
            and funding["unknown_charges_released"] is False
            and funding["ledger_reset"] is False
            and funding["current_balance_is_not_funding_basis"] is True
        )
        checks["original_total_reserves_and_daily_preserved"] = (
            money(funding["original_builder_gift_gross_usd"]) == Decimal("30.25")
            and money(funding["preserved_tax_multiplier"]) == Decimal("1.21")
            and money(funding["judging_reserve_gross_usd"]) == 10
            and money(funding["fee_rounding_reserve_gross_usd"]) == Decimal("0.89")
            and Decimal(16) * money(funding["preserved_tax_multiplier"])
            + money(funding["judging_reserve_gross_usd"])
            + money(funding["fee_rounding_reserve_gross_usd"])
            == Decimal("30.25")
            and money(funding["combined_original_daily_net_usd"]) == 12
            and DAILY_POOL + money(funding["external_retained_net_usd"]) <= 12
        )
        retained = allocation["retained_unknown_probe_charges"]
        checks["original_allocation_and_retained_debt"] = (
            money(allocation["all_time_net_ceiling_usd"]) == 16
            and money(allocation["runtime_all_time_ceiling_usd"]) == DAILY_POOL
            and money(allocation["current_runtime_daily_cap_usd"]) == DAILY_POOL
            and money(allocation["new_probe_pool_remaining_usd"]) == POOL - DAILY_POOL
            and money(allocation["total_external_probe_known_or_retained_usd"])
            == Decimal("1.82224246")
            and money(allocation["new_probe_unknown_retained_usd"]) == Decimal("1.049344")
            and money(funding["external_unknown_retained_net_usd"]) == Decimal("1.049344")
            and allocation["pending_probe_claims"] == []
            and isinstance(retained, list)
            and len(retained) == 1
            and retained[0]["actual_cost_usd"] is None
            and money(retained[0]["retained_upper_usd"]) == Decimal("1.049344")
            and retained[0]["release_authorized"] is False
            and retained[0]["permanent_for_current_campaign"] is True
        )
        checks["historical_allocation_profile_and_closure_bound"] = all(
            funding[path_key] == path and funding[sha_key] == expected[path]
            for path_key, sha_key, path in (
                ("old_allocation_path", "old_allocation_sha256", ALLOCATION_PATH),
                ("old_profile_path", "old_profile_sha256", OLD_PROFILE),
                ("retirement_receipt_path", "retirement_receipt_sha256", RETIREMENT_PATH),
            )
        )
        entries = retirement["entrypoints"]
        checks["external_entrypoints_closed"] = (
            retirement["status"] == "closed"
            and money(retirement["active_external_allowance_usd"]) == 0
            and type(retirement["inference_requests"]) is int
            and retirement["inference_requests"] == 0
            and retirement["historical_source_bytes_preserved"] is True
            and retirement["historical_results_modified"] is False
            and isinstance(entries, list)
            and len(entries) == len(RETIRED_ENTRYPOINTS)
            and {r["path"] for r in entries} == RETIRED_ENTRYPOINTS
            and all(
                HEX.fullmatch(r["closed_sha256"])
                and hashes.get(r["path"]) == r["closed_sha256"]
                and HEX.fullmatch(r["original_sha256"])
                for r in entries
            )
            and all(
                r["path"] == "scripts/probe_models.py"
                or (
                    str(r.get("archived_path", "")).startswith(
                        ".cache/retired-external-probes-20261025-r2/"
                    )
                    and str(r.get("archived_path", "")).endswith(".py.retired")
                    and hashes.get(r["archived_path"]) == r["original_sha256"]
                    and r.get("refusal_exit_code") == 1
                )
                for r in entries
            )
        )
        checks["funded_profile_not_a_live_balance"] = (
            profile["live_enabled"] is True
            and profile["credit_confirmed"] is True
            and profile["run_budget_mode"] == "actual_usage"
            and money(profile["authorized_total_usd"]) == POOL
            and money(profile["available_credit_usd"]) == POOL
        )
        ledger = cap["ledger"]
        checks["same_ledger_and_full_history_snapshot"] = (
            funding["runtime_ledger_path"] == ".cache/budget.db"
            and HEX.fullmatch(funding["runtime_ledger_projection_sha256"]) is not None
            and ledger["projection_sha256"] == funding["runtime_ledger_projection_sha256"]
            and type(funding["runtime_closed_runs"]) is int
            and ledger["runs"] == funding["runtime_closed_runs"] > 0
            and type(funding["runtime_settled_attempts"]) is int
            and ledger["attempts"] == funding["runtime_settled_attempts"] > 0
            and money(ledger["conservative_charged_usd"])
            == money(funding["runtime_conservative_net_usd"])
            and money(funding["remaining_runtime_lifetime_net_usd"])
            == POOL - money(ledger["conservative_charged_usd"])
            and cap["historical_driver_sha256"] == expected[HISTORICAL_HELPER_PATH]
        )
        auth = cap["authorization"]
        checks["cap_explicitly_binds_transfer_and_original_limits"] = (
            cap["funding"]
            == {"path": FUNDING_PATH, "sha256": expected[FUNDING_PATH], "zero_sum": True}
            and cap["funding"]["zero_sum"] is True
            and cap["profile_sha256"] == expected[PROFILE]
            and cap["budget_helper_sha256"] == expected[BUDGET_HELPER_PATH]
            and money(cap["pool_usd"]) == POOL
            and money(cap["daily_pool_usd"]) == DAILY_POOL
            and money(cap["per_case_stop_usd"]) == Decimal("0.6")
            and money(cap["campaign_max_usd"]) == Decimal("5.4")
            and cap["unknown_costs_retain_verified_bounds"] is True
            and cap["no_history_exclusions"] is True
            and auth["gift_only"] is True
            and auth["recharge"] is False
            and auth["new_budget_pool"] is False
            and auth["zero_sum_partition_transfer"] is True
        )
    except (KeyError, TypeError, ValueError, ArithmeticError):
        checks["complete_well_formed_documents"] = False
    return {
        "accepted": bool(checks) and all(value is True for value in checks.values()),
        "checks": checks,
        "lifetime_net_usd": str(POOL),
        "daily_net_usd": str(DAILY_POOL),
        "funding_is_live_account_balance": False,
        "historical_money_released": False,
    }


def restricted_funding_bytes(name, allowed, records):
    """Only explicitly pinned profile/retirement files; never arbitrary cache or credentials."""
    if type(name) is not str or name not in allowed:
        raise ValueError("Private funding artifact is not explicitly allowed")
    relative = Path(name)
    if (
        relative.is_absolute()
        or relative.as_posix() != name
        or any(part in {".", ".."} or part.startswith(".env") for part in relative.parts)
    ):
        raise ValueError("Unsafe funding artifact path")
    path = ROOT
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Funding artifacts cannot follow symlinks")
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if name in {PROFILE, OLD_PROFILE} and stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("Runtime profile permissions changed")
        if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024:
            raise ValueError("Funding artifact must be a bounded regular file")
        raw = handle.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Funding artifact grew beyond bound")
    value = digest(raw)
    if name in records and records[name] != value:
        raise ValueError("Funding artifact changed during audit")
    records[name] = value
    return raw


def read_funding_binding(reader, cap):
    expected = {r["path"]: r["sha256"] for r in FUNDING_PINS}
    # Refuse absent, pending or replaced receipts before allowing any private read.
    for name in (
        FUNDING_PATH,
        RETIREMENT_PATH,
        ALLOCATION_PATH,
        BUDGET_HELPER_PATH,
        HISTORICAL_HELPER_PATH,
    ):
        if reader.digest(name) != expected[name]:
            raise ValueError("Missing or changed funding prerequisite")
    funding, retirement, allocation = (
        reader.json(name) for name in (FUNDING_PATH, RETIREMENT_PATH, ALLOCATION_PATH)
    )
    entries = retirement.get("entrypoints") if isinstance(retirement, dict) else None
    if (
        not isinstance(entries, list)
        or len(entries) != 7
        or {r.get("path") for r in entries} != RETIRED_ENTRYPOINTS
    ):
        raise ValueError("Complete fixed retirement inventory required")
    allowed = {PROFILE, OLD_PROFILE} | RETIRED_ENTRYPOINTS
    allowed |= {r["archived_path"] for r in entries if "archived_path" in r}
    records = {}
    profile = json.loads(restricted_funding_bytes(PROFILE, allowed, records))
    for name in sorted(allowed - {PROFILE}):
        restricted_funding_bytes(name, allowed, records)
    hashes = dict(reader.hashes) | records
    driver = driver_funding_pins(reader.raw(OUT / "run_mvp_v2.py").decode())
    result = funding_binding(funding, retirement, allocation, profile, cap, driver, hashes)
    return result, records, allowed


def funding_dispatch_binding(cap, preflight):
    try:
        before = preflight["budget_before"]
        argv = preflight["argv"]
        if not isinstance(argv, list) or not all(type(item) is str for item in argv):
            return False

        def option(name):
            if argv.count(name) != 1:
                raise ValueError("Missing or duplicate budget option")
            return argv[argv.index(name) + 1]

        started = datetime.fromisoformat(preflight["started_utc"])
        if started.tzinfo is None:
            return False
        charged = money(cap["ledger"]["conservative_charged_usd"])
        remaining = POOL - charged
        day_remaining = DAILY_POOL - money(before["day_conservative_usd"])
        effective = min(Decimal("5.4"), remaining, day_remaining)
        return (
            before["projection_sha256"] == cap["ledger"]["projection_sha256"]
            and before["history_exclusions"] == []
            and money(before["conservative_usd"]) == charged
            and money(before["all_time_limit_usd"]) == POOL
            and money(before["daily_limit_usd"]) == DAILY_POOL
            and money(before["remaining_all_time_usd"]) == remaining
            and money(before["remaining_day_usd"]) == day_remaining
            and money(before["effective_campaign_usd"]) == effective >= Decimal("0.6")
            and money(before["campaign_max_usd"]) == Decimal("5.4")
            and started.astimezone(UTC).date().isoformat() == before["utc_day"]
            and option("--runtime-profile") == PROFILE
            and money(option("--budget")) == Decimal("0.6")
            and money(option("--daily-budget")) == DAILY_POOL
            and money(option("--campaign-budget")) == effective
        )
    except (KeyError, TypeError, ValueError, ArithmeticError, IndexError):
        return False


def daily_ledger_bounds(runs, attempts):
    try:
        days = {r["id"]: r["day"] for r in runs}
        if len(days) != len(runs) or any(
            type(day) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) is None
            for day in days.values()
        ):
            raise ValueError("Unknown ledger UTC day")
        for day in days.values():
            datetime.strptime(day, "%Y-%m-%d")
        daily = {}
        for attempt in attempts:
            day = days[attempt["run_id"]]
            daily[day] = daily.get(day, Decimal(0)) + money(attempt["charged_usd"])
        return {
            "accepted": bool(days) and all(value <= DAILY_POOL for value in daily.values()),
            "daily_limit_usd": str(DAILY_POOL),
            "by_utc_day": [
                {"utc_day": day, "charged_usd": str(value)} for day, value in sorted(daily.items())
            ],
            "external_retained_debt_not_released": True,
        }
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return {"accepted": False, "reason": "incomplete or inconsistent ledger day evidence"}


def fixed_rows(rows):
    """Missing, duplicate and foreign slots never shrink the denominator."""
    grouped = {key: [] for key in IDS}
    foreign = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("scenario_id") in grouped:
            grouped[row["scenario_id"]].append(row)
        else:
            foreign.append(row.get("scenario_id") if isinstance(row, dict) else None)
    return (
        [
            grouped[key][0]
            if len(grouped[key]) == 1
            else {
                "scenario_id": key,
                "run_id": None,
                "audit_slot_problem": "missing" if not grouped[key] else "duplicate",
            }
            for key in IDS
        ],
        not foreign and all(len(grouped[key]) == 1 for key in IDS),
        foreign,
    )


def totals(attempts):
    known = sum(
        (money(a["actual_usd"]) for a in attempts if a["actual_usd"] is not None), Decimal(0)
    )
    charged = sum((money(a["charged_usd"]) for a in attempts), Decimal(0))
    unknown = [a for a in attempts if a["actual_usd"] is None]
    return {
        "attempts": len(attempts),
        "known_actual_subtotal_usd": str(known),
        "actual_total_usd": None if unknown else str(known),
        "conservative_charged_usd": str(charged),
        "unknown_retained_usd": str(sum((money(a["charged_usd"]) for a in unknown), Decimal(0))),
        "unknown_attempts": len(unknown),
        "pending": sum(not a["settled"] for a in attempts),
        "unresolved": sum(
            a["actual_usd"] is None
            and not (
                a["settled"]
                and a["dispatched"]
                and a["admission_kind"] == "verified_provider_bound"
                and a["charge_status"] in {"upper_bound", "reviewed_retained"}
            )
            for a in attempts
        ),
    }


def request_evidence(call):
    """Verify the stored bounded copy; exact wire hash is not a provider receipt."""
    item = call.get("request_evidence")
    if call.get("outcome") == "not_dispatched":
        return {"state": "not_dispatched", "metadata_valid": True, "payload_valid": None}
    if not isinstance(item, dict):
        return {"state": "unknown", "metadata_valid": None, "payload_valid": None}
    metadata = (
        item.get("schema_version") == 1
        and item.get("capture_point") == "httpx_pre_transport"
        and bool(HEX.fullmatch(str(item.get("wire_body_sha256", ""))))
        and type(item.get("wire_body_utf8_bytes")) is int
        and item["wire_body_utf8_bytes"] > 0
        and item.get("delivery_confirmed") is False
    )
    status, payload = item.get("payload_status"), item.get("payload")
    valid = None
    model_match = None
    if status in {"captured", "redacted"}:
        valid = isinstance(payload, dict) and digest(
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        ) == item.get("stored_payload_sha256")
        if isinstance(payload, dict):
            model_match = payload.get("model") == call.get("model")
    elif status == "omitted_size":
        valid = payload is None
    return {
        "state": status,
        "metadata_valid": metadata,
        "payload_valid": valid,
        "request_model_matches_call": model_match,
        "wire_body_sha256": item.get("wire_body_sha256"),
        "wire_body_utf8_bytes": item.get("wire_body_utf8_bytes"),
        "stored_payload_sha256": item.get("stored_payload_sha256"),
        "body_delivery_or_ingestion_proven": False,
    }


def load_helpers():
    loaded = {}
    # Base installs a read-only audit hook. Load it last; no helper main() is called.
    for name in ("cli", "span", "base"):
        relative, expected = HELPERS[name]
        path = ROOT / relative
        if digest(path.read_bytes()) != expected:
            raise ValueError("Reviewed legacy audit helper changed")
        spec = importlib.util.spec_from_file_location("v2_audit_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    cli = loaded["cli"]
    cli.IDS = IDS
    cli.REQUIRED_SOURCES = tuple(
        MANIFEST if p == "eval/mvp_phase1.yaml" else p for p in cli.REQUIRED_SOURCES
    ) + (
        "headroom/verify/reference_config.py",
        "headroom/lab/snapshot_codec.py",
        "headroom/lab/hooks.py",
        "headroom/lab/precision.py",
    )
    original_parse, original_match = cli.parse_argv, cli.argument_match

    def parse(argv):
        if not isinstance(argv, list) or not all(type(token) is str for token in argv):
            return None
        stripped, extra = [], {}
        index = 0
        while index < len(argv):
            token = argv[index]
            if token == "--":
                stripped.extend(argv[index:])
                break
            if token in EXTRA_OPTIONS:
                if token in extra or index + 1 >= len(argv) or type(argv[index + 1]) is not str:
                    return None
                extra[token] = argv[index + 1]
                index += 2
            else:
                stripped.append(token)
                index += 1
        parsed = original_parse(stripped)
        return None if parsed is None else parsed | extra

    def match(argv, request, repository):
        args = parse(argv)
        if (
            args is None
            or not EXTRA_OPTIONS <= args.keys()
            or not original_match(argv, request, repository)
        ):
            return False
        reference = request.get("numerical_reference")
        if not isinstance(reference, dict):
            return False
        try:
            return (
                args["--allocator-conf"] == (request.get("allocator_conf") or "")
                and args["--reference-strategy"] == reference["strategy"]
                and Decimal(args["--reference-cpu-bytes"])
                == reference["cpu_saved_tensor_limit_bytes"]
                and Decimal(args["--reference-disk-bytes"])
                == reference["disk_saved_tensor_limit_bytes"]
                and Decimal(args["--reference-max-seconds"]) == (reference["max_seconds"] or 0)
            )
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return False

    cli.parse_argv, cli.argument_match = parse, match
    return loaded


def cli_row(cli, reader, directory, row, state, quality, source_map, case, campaign):
    result = cli.audit_row(reader, directory, row, state, quality, source_map, case, campaign)
    if not result.get("checks"):
        return result
    request = cli.dict_value(state.get("request"))
    context = cli.dict_value(reader.json(directory / ("cli-context-" + row["run_id"] + ".json")))
    expected_reference = REF_DEFAULTS | case.get("numerical_reference", {})
    checks = result["checks"]
    # Versioned manifest semantics replace only the old fixed allocator=None/120 assumptions.
    checks["original_case_request"] = (
        request.get("target") == case.get("target")
        and cli.same(request.get("reclaim_reduction_pct"), case.get("reclaim_reduction_pct", 30))
        and type(request.get("max_steps")) is int
        and request["max_steps"] == case.get("max_steps", 20)
        and type(request.get("max_seconds")) is int
        and request["max_seconds"] == case.get("max_seconds", 120)
        and request.get("device") == "cuda"
        and request.get("seed") == 1337
        and request.get("research_enabled") is True
        and request.get("max_rounds") == 6
        and request.get("allocator_conf") == case.get("allocator_conf")
        and cli.same(request.get("numerical_reference"), expected_reference)
        and request.get("execution_entrypoint") is None
        and request.get("budget_usd") == "0.6"
        and request.get("daily_budget_usd")
        == cli.dict_value(campaign.get("limits")).get("daily_usd")
        and request.get("source_profile") == case.get("source_profile")
        and request.get("search_mode") == campaign.get("search_mode") == "until_target"
        and context.get("condition") == row.get("condition") == "full_ultra"
        and row.get("policy_name") == "strict"
    )
    complete = tri(checks.values())
    result["chain_verified"] = complete
    code = result.get("observed_exit_code")
    result["status"] = (
        "verified_zero"
        if complete is True and code == 0
        else (
            "verified_nonzero"
            if complete is True
            else "contradictory"
            if complete is False
            else "unknown"
        )
    )
    result["failed_checks"] = [key for key, value in checks.items() if value is False]
    result["unknown_checks"] = [key for key, value in checks.items() if value is None]
    return result


def complete_source_map(value):
    """Strict, complete inventories; no required-file subset or duplicate folding."""
    if type(value) is dict:
        rows = [{"path": path, "sha256": sha} for path, sha in value.items()]
    elif type(value) is list:
        rows = value
    else:
        return None
    if not rows:
        return None
    result = {}
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "sha256"}:
            return None
        path, sha = row["path"], row["sha256"]
        if (
            type(path) is not str
            or not path
            or path == "."
            or Path(path).is_absolute()
            or Path(path).as_posix() != path
            or ".." in Path(path).parts
            or any(part.startswith(".env") for part in Path(path).parts)
            or path in result
            or type(sha) is not str
            or not HEX.fullmatch(sha)
        ):
            return None
        result[path] = sha
    return result


def bind_complete_sources(before, after, pins, current, tested_head, executed_head):
    """A post-test commit is permitted only with identical complete inventories."""
    maps = [complete_source_map(value) for value in (before, after, pins, current)]
    valid = all(value is not None for value in maps)
    source_equal = valid and maps[0] == maps[1] == maps[2]
    current_equal = valid and maps[0] == maps[3]
    heads_valid = all(
        type(head) is str and re.fullmatch(r"[0-9a-f]{40}", head)
        for head in (tested_head, executed_head)
    )
    accepted = bool(source_equal and current_equal and heads_valid)
    return {
        "accepted": accepted,
        "complete_before_after_review_equal": bool(source_equal),
        "all_listed_current_source_hashes_match": bool(current_equal),
        "recorded_heads_valid": bool(heads_valid),
        "tested_head": tested_head,
        "executed_head": executed_head,
        "head_transition": (
            "same_commit"
            if accepted and tested_head == executed_head
            else "post_test_commit_identical_sources"
            if accepted
            else "unverified"
        ),
        "source_counts": {
            label: len(value) if value is not None else None
            for label, value in zip(("before", "after", "review", "current"), maps)
        },
        "inventory_sha256": {
            label: digest(canonical(value)) if value is not None else None
            for label, value in zip(("before", "after", "review", "current"), maps)
        },
        "execution_inventory_contract": (
            "The SHA-bound execution driver checks its complete Git source inventory "
            "against review.source_pins before launch; this reader hashes every listed "
            "source without starting Git or another subprocess."
        ),
    }


def ledger_projection(rows, attempts):
    return digest(canonical({"runs": rows, "attempts": attempts}))


def audit(execution_path):
    helpers = load_helpers()
    base, cli, span = (helpers[k] for k in ("base", "cli", "span"))
    reader = cli.Reader(ROOT)
    if reader.path(execution_path) != OUT / "execution.json":
        raise ValueError("Only this version's explicit execution receipt is accepted")
    execution = reader.json(execution_path)
    review = reader.json(OUT / "root-review.json")
    preflight = reader.json(OUT / "preflight.json")
    cap = reader.json(OUT / "cap-review.json")
    manifest = reader.json(MANIFEST)
    if not all(isinstance(item, dict) for item in (execution, review, preflight, cap, manifest)):
        raise ValueError("Complete bound execution/review/preflight/cap/manifest required")
    candidates = execution.get("campaigns")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise ValueError("Exactly one newly recorded campaign is required; no historical fallback")
    reference = candidates[0]
    campaign_path = reader.path(reference["path"])
    if campaign_path.name != "campaign.json" or not campaign_path.is_relative_to(
        ROOT / "runs/evaluation/live"
    ):
        raise ValueError("New campaign must be a live artifact")
    campaign = reader.json(campaign_path)
    cases = manifest.get("scenarios", [])
    if [c.get("id") for c in cases] != list(IDS):
        raise ValueError("The approved v2 nine-slot manifest is required")
    rows, exact_slots, foreign = fixed_rows(campaign.get("rows"))
    ids = [
        r["run_id"]
        for r in rows
        if isinstance(r.get("run_id"), str) and UUID.fullmatch(r["run_id"])
    ]
    unique_ids = len(ids) == len(set(ids))
    quality_path = review["quality_receipt"]["path"]
    quality, source_map = cli.quality_review(reader, reader.path(quality_path))
    quality_data = reader.json(quality_path)
    source_before = reader.json(quality_data["before"])
    source_after = reader.json(quality_data["after"])
    complete_before = complete_source_map(source_before)
    complete_after = complete_source_map(source_after)
    complete_pins = complete_source_map(review.get("source_pins"))
    source_names = sorted(
        set(complete_before or {}) | set(complete_after or {}) | set(complete_pins or {})
    )
    current_sources = {name: reader.digest(name) for name in source_names}
    source_binding = bind_complete_sources(
        source_before,
        source_after,
        review.get("source_pins"),
        current_sources,
        quality.get("git_head"),
        preflight.get("source_commit"),
    )
    quality_ref = review["quality_receipt"]
    source_binding["quality_receipts_bound"] = (
        reader.digest(quality_path) == quality_ref.get("sha256")
        and reader.digest(quality_data["before"]) == quality_ref.get("before_sha256")
        and reader.digest(quality_data["after"]) == quality_ref.get("after_sha256")
        and reader.digest(quality_data["log"]) == quality_ref.get("log_sha256")
        and complete_before is not None
        and quality_ref.get("source_count") == len(complete_before)
        and source_map == complete_before
        and quality_ref.get("post_test_changes") == []
    )
    source_binding["accepted"] = (
        source_binding["accepted"] and source_binding["quality_receipts_bound"]
    )
    funding_review, private_funding_hashes, private_funding_allowed = read_funding_binding(
        reader, cap
    )
    gates = {
        "new_execution_campaign_sha": reader.digest(campaign_path) == reference.get("sha256"),
        "bound_root_review": reader.digest(OUT / "root-review.json")
        == preflight.get("review_sha256"),
        "cap_unchanged": reader.digest(OUT / "cap-review.json") == review.get("cap_sha256"),
        "driver_unchanged": reader.digest(OUT / "run_mvp_v2.py") == review.get("driver_sha256"),
        "manifest_bound": reader.digest(MANIFEST)
        == review.get("manifest_sha256")
        == campaign.get("manifest_sha256")
        == source_map.get(MANIFEST),
        "complete_tested_execution_sources_bound": source_binding["accepted"],
        "exact_v2_nine_slots": exact_slots,
        "unique_current_run_ids": unique_ids and len(ids) == 9,
        "fixed_review_denominator": review.get("fixed_acceptance_denominator") == 9
        and execution.get("fixed_acceptance_denominator") == 9,
        "minimum_remains_six": review.get("minimum_target_met") == 6,
        "full_quality_passed": quality.get("accepted"),
        "campaign_finished_live": campaign.get("status") == "finished"
        and campaign.get("provenance") == "live",
        "strict_full_ultra_only": all(
            r.get("condition") == "full_ultra"
            and r.get("policy_name") == "strict"
            and r.get("search_mode") == "until_target"
            for r in rows
        ),
        "reviewed_zero_sum_gift_partition": funding_review["accepted"],
        "original_dispatch_daily_and_case_limits": funding_dispatch_binding(cap, preflight),
    }
    states, store_projection = cli.store_snapshot(reader, ids)
    raw_states, _, ledger_runs, attempts = span.db_snapshot(ids)
    before_projection = ledger_projection(ledger_runs, attempts)
    history_runs = [r for r in ledger_runs if r["id"] not in ids]
    history_attempts = [a for a in attempts if a["run_id"] not in ids]
    history_matches = (
        ledger_projection(history_runs, history_attempts) == cap["ledger"]["projection_sha256"]
        and len(history_runs) == cap["ledger"]["runs"]
        and len(history_attempts) == cap["ledger"]["attempts"]
    )
    # Reject a reused historical campaign before reading any of its score artifacts.
    if not history_matches:
        raise ValueError("Current campaign IDs do not preserve the complete pre-execution ledger")
    store, ledger = base.database("runs/headroom.db"), base.database(".cache/budget.db")
    prices = base.read_json("reports/live-campaign-20261025/pricing-reviewed.json")
    audited = []
    try:
        for case, row in zip(cases, rows):
            item = {"scenario_id": case["id"], "run_id": row.get("run_id")}
            if row.get("run_id") not in ids:
                item.update(
                    target=None,
                    cause=None,
                    cli=None,
                    source_application=None,
                    reason=row.get("audit_slot_problem", "not_executed"),
                )
                audited.append(item)
                continue
            run_id = row["run_id"]
            expected_job = campaign_path.parent / "jobs" / run_id
            if row.get("run_dir") != str(expected_job) or row.get("report_json") != str(
                expected_job / "report.json"
            ):
                item.update(target=None, cause=None, reason="foreign_or_unbound_run_artifacts")
                audited.append(item)
                continue
            ordinary = base.audit_row(case, row, store, ledger, prices)
            literal = cli_row(
                cli,
                reader,
                campaign_path.parent,
                row,
                states.get(run_id, {}),
                quality,
                source_map,
                case,
                campaign,
            )
            applied = span.audit_row(row, raw_states.get(run_id))
            selection = applied.get("selection", {})
            calls = base.rows(store, "llm_calls", run_id) or []
            body_receipts = [
                request_evidence(call)
                | {"call_id": call.get("id"), "budget_attempt_id": call.get("budget_attempt_id")}
                for call in calls
            ]
            item.update(
                target=tri(
                    [
                        ordinary.get("target"),
                        ordinary.get("selected_patch_applied"),
                        selection.get("selected_preserved_verified"),
                        selection.get("selected_code_chain_verified"),
                    ]
                ),
                cause=ordinary.get("cause"),
                first_cause=ordinary.get("first_cause"),
                truth_status=case.get("truth_status"),
                observed=ordinary,
                cli=literal,
                source_application=applied,
                prepared_request_evidence=body_receipts,
                per_run_gates=tri(ordinary.get("gates", {}).get(key) for key in BASE_GATES),
            )
            audited.append(item)
    finally:
        for connection in (store, ledger):
            if connection is not None:
                connection.close()
    campaign_attempts = [a for a in attempts if a["run_id"] in ids]
    history_runs = [r for r in ledger_runs if r["id"] not in ids]
    history_attempts = [a for a in attempts if a["run_id"] not in ids]
    global_totals = totals(attempts)
    daily_bounds = daily_ledger_bounds(ledger_runs, attempts)
    external = reader.json("reports/live-campaign-20261025/allocation.json")
    external_retained = external.get("retained_unknown_probe_charges", [])
    gates["external_retained_debt_preserved"] = (
        external.get("total_external_probe_known_or_retained_usd") == "1.82224246"
        and external.get("new_probe_unknown_retained_usd") == "1.049344"
        and len(external_retained) == 1
        and external_retained[0].get("actual_cost_usd") is None
        and external_retained[0].get("retained_upper_usd") == "1.049344"
        and external_retained[0].get("release_authorized") is False
        and external_retained[0].get("permanent_for_current_campaign") is True
    )
    finance = {
        "campaign": totals(campaign_attempts),
        "all_time": global_totals,
        "prior_projection": ledger_projection(history_runs, history_attempts),
        "prior_projection_matches_preflight": ledger_projection(history_runs, history_attempts)
        == cap["ledger"]["projection_sha256"],
        "all_time_projection_before": before_projection,
        "all_prior_rows_preserved": len(history_runs) == cap["ledger"]["runs"]
        and len(history_attempts) == cap["ledger"]["attempts"],
        "funding_partition": funding_review,
        "daily_ledger_bounds": daily_bounds,
        "pool_usd": str(POOL),
        "daily_pool_usd": str(DAILY_POOL),
        "remaining_pool_usd": str(POOL - money(global_totals["conservative_charged_usd"])),
        "external_probes": {
            key: external.get(key)
            for key in (
                "total_external_probe_known_or_retained_usd",
                "new_probe_unknown_retained_usd",
                "retained_unknown_probe_charges",
            )
        },
        "unknown_actual_never_zeroed": True,
        "not_provider_invoice_or_card_charge": True,
    }
    _, _, final_runs, final_attempts = span.db_snapshot(ids)
    finance["all_time_projection_after"] = ledger_projection(final_runs, final_attempts)
    final_states, final_store_projection = cli.store_snapshot(reader, ids)
    gates.update(
        all_nine_run_gates=tri(item.get("per_run_gates") for item in audited),
        source_application_evidence_complete=tri(
            (item.get("source_application") or {}).get("row_evidence_complete") for item in audited
        ),
        literal_nine_exit_zero=tri(
            (item.get("cli") or {}).get("chain_verified") is True
            and (item.get("cli") or {}).get("observed_exit_code") == 0
            if item.get("cli") is not None
            else None
            for item in audited
        ),
        historical_finance_preserved=finance["prior_projection_matches_preflight"]
        and finance["all_prior_rows_preserved"],
        ledger_stable=finance["all_time_projection_before"] == finance["all_time_projection_after"],
        store_stable=cli.same(states, final_states),
        ledger_clear=global_totals["pending"] == 0
        and global_totals["unresolved"] == 0
        and not any(r["halt_reason"] is not None or r["status"] != "closed" for r in ledger_runs),
        pool_not_exceeded=money(global_totals["conservative_charged_usd"]) <= POOL,
        daily_pool_not_exceeded=daily_bounds["accepted"],
        at_least_six_targets=base.threshold([item.get("target") for item in audited], 6),
        at_least_six_valid_correct_first_causes=base.threshold(
            [item.get("cause") for item in audited], 6
        ),
    )
    changed = []
    for path, expected in list(reader.hashes.items()):
        if reader.digest(path) != expected:
            changed.append(path)
    for path, expected in list(base.RECORDS.items()):
        if digest(base.read_bytes(path)) != expected["sha256"]:
            changed.append(path)
    for path, expected in list(span.RECORDS.items()):
        # The source-span helper stores native hashes, not audit result booleans.
        expected_sha = expected.get("sha256") if isinstance(expected, dict) else expected
        if digest(span.read(path)) != expected_sha:
            changed.append(path)
    for path, expected in private_funding_hashes.items():
        if digest(restricted_funding_bytes(path, private_funding_allowed, {})) != expected:
            changed.append(path)
    gates["artifact_sources_stable"] = not changed
    errors = reader.errors + base.ERRORS
    gates["no_artifact_read_errors"] = not errors
    return {
        "schema_version": 1,
        "audit_kind": "independent_v2_r3_mvp_nine_zero_sum_partition",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "campaign": str(campaign_path.relative_to(ROOT)),
        "fixed_denominator": 9,
        "historical_scores_used": False,
        "human_controls_counted": False,
        "accepted_observed_campaign_gates": tri(gates.values()),
        "full_original_plan_acceptance": None,
        "counts": {
            "targets": sum(i.get("target") is True for i in audited),
            "targets_unknown": sum(i.get("target") is None for i in audited),
            "valid_correct_first_causes": sum(i.get("cause") is True for i in audited),
            "first_causes_unknown": sum(i.get("cause") is None for i in audited),
        },
        "gates": gates,
        "rows": audited,
        "foreign_slots": foreign,
        "finance": finance,
        "quality": quality,
        "source_binding": source_binding,
        "store_before": store_projection,
        "store_after": final_store_projection,
        "source_hashes": reader.hashes,
        "changed_artifacts": changed,
        "errors": errors,
        "legacy_helpers": HELPERS,
        "funding_private_artifact_hashes": [
            {"path": k, "sha256": v} for k, v in sorted(private_funding_hashes.items())
        ],
        "audit_source_sha256": reader.digest(Path(__file__)),
        "actions": {
            "model_calls": 0,
            "gpu_jobs": 0,
            "subprocesses": 0,
            "credential_reads": 0,
            "runtime_profile_metadata_reads": 1,
            "ledger_writes": 0,
            "source_or_run_writes": 0,
        },
        "limitations": [
            "Prepared-body evidence proves local preparation, not delivery or provider ingestion.",
            "Stored copies may be redacted/size-omitted; absent semantic body evidence remains unknown.",
            "Unverified s5/nano cause truth remains unknown in the fixed denominator of nine.",
            "Independent Phase 2, negative controls, submission and full-plan gates remain separate.",
        ],
    }


def funding_fixture():
    pins = {r["path"]: r["sha256"] for r in FUNDING_PINS}
    funding = {
        "status": "external_allocation_closed",
        "total_work_net_usd": "16",
        "original_builder_gift_gross_usd": "30.25",
        "preserved_tax_multiplier": "1.21",
        "judging_reserve_gross_usd": "10",
        "fee_rounding_reserve_gross_usd": "0.89",
        "original_runtime_lifetime_net_usd": str(DAILY_POOL),
        "transferred_unused_external_net_usd": str(POOL - DAILY_POOL),
        "runtime_lifetime_net_usd": str(POOL),
        "runtime_daily_net_usd": str(DAILY_POOL),
        "combined_original_daily_net_usd": "12",
        "external_retained_net_usd": "1.82224246",
        "external_unknown_retained_net_usd": "1.049344",
        "external_future_net_usd": "0",
        "new_money": False,
        "recharge": False,
        "unknown_charges_released": False,
        "ledger_reset": False,
        "current_balance_is_not_funding_basis": True,
        "old_allocation_path": ALLOCATION_PATH,
        "old_allocation_sha256": pins[ALLOCATION_PATH],
        "old_profile_path": OLD_PROFILE,
        "old_profile_sha256": pins[OLD_PROFILE],
        "retirement_receipt_path": RETIREMENT_PATH,
        "retirement_receipt_sha256": pins[RETIREMENT_PATH],
        "runtime_ledger_path": ".cache/budget.db",
        "runtime_ledger_projection_sha256": "a" * 64,
        "runtime_closed_runs": 97,
        "runtime_settled_attempts": 517,
        "runtime_conservative_net_usd": "6.6",
        "remaining_runtime_lifetime_net_usd": str(POOL - Decimal("6.6")),
    }
    allocation = {
        "all_time_net_ceiling_usd": "16",
        "runtime_all_time_ceiling_usd": str(DAILY_POOL),
        "current_runtime_daily_cap_usd": str(DAILY_POOL),
        "new_probe_pool_remaining_usd": str(POOL - DAILY_POOL),
        "total_external_probe_known_or_retained_usd": "1.82224246",
        "new_probe_unknown_retained_usd": "1.049344",
        "pending_probe_claims": [],
        "retained_unknown_probe_charges": [
            {
                "actual_cost_usd": None,
                "retained_upper_usd": "1.049344",
                "release_authorized": False,
                "permanent_for_current_campaign": True,
            }
        ],
    }
    retirement = {
        "status": "closed",
        "active_external_allowance_usd": "0",
        "inference_requests": 0,
        "historical_source_bytes_preserved": True,
        "historical_results_modified": False,
        "entrypoints": [],
    }
    hashes = dict(pins)
    for index, path in enumerate(sorted(RETIRED_ENTRYPOINTS)):
        item = {
            "path": path,
            "original_sha256": digest(f"original-{index}".encode()),
            "closed_sha256": digest(f"closed-{index}".encode()),
        }
        hashes[path] = item["closed_sha256"]
        if path != "scripts/probe_models.py":
            item["archived_path"] = f".cache/retired-external-probes-20261025-r2/{index}.py.retired"
            item["refusal_exit_code"] = 1
            hashes[item["archived_path"]] = item["original_sha256"]
        retirement["entrypoints"].append(item)
    profile = {
        "live_enabled": True,
        "credit_confirmed": True,
        "run_budget_mode": "actual_usage",
        "authorized_total_usd": str(POOL),
        "available_credit_usd": str(POOL),
    }
    cap = {
        "ledger": {
            "projection_sha256": "a" * 64,
            "runs": 97,
            "attempts": 517,
            "conservative_charged_usd": "6.6",
        },
        "historical_driver_sha256": pins[HISTORICAL_HELPER_PATH],
        "funding": {"path": FUNDING_PATH, "sha256": pins[FUNDING_PATH], "zero_sum": True},
        "profile_sha256": pins[PROFILE],
        "budget_helper_sha256": pins[BUDGET_HELPER_PATH],
        "pool_usd": str(POOL),
        "daily_pool_usd": str(DAILY_POOL),
        "per_case_stop_usd": "0.6",
        "campaign_max_usd": "5.4",
        "unknown_costs_retain_verified_bounds": True,
        "no_history_exclusions": True,
        "authorization": {
            "gift_only": True,
            "recharge": False,
            "new_budget_pool": False,
            "zero_sum_partition_transfer": True,
        },
    }
    driver = {
        "PROFILE": PROFILE,
        "PROFILE_SHA": pins[PROFILE],
        "FUNDING_SHA": pins[FUNDING_PATH],
        "BUDGET_HELPER_SHA": pins[BUDGET_HELPER_PATH],
    }
    return [funding, retirement, allocation, profile, cap, driver, hashes]


def funding_self_test(check):
    data = funding_fixture()
    check(funding_binding(*data)["accepted"])
    mutations = [
        (0, ("status",), "pending"),
        (0, ("total_work_net_usd",), "17"),
        (0, ("runtime_lifetime_net_usd",), "15"),
        (0, ("runtime_daily_net_usd",), str(POOL)),
        (0, ("transferred_unused_external_net_usd",), "0"),
        (0, ("external_retained_net_usd",), "0"),
        (0, ("external_unknown_retained_net_usd",), "0"),
        (0, ("external_future_net_usd",), "1"),
        (0, ("judging_reserve_gross_usd",), "9"),
        (0, ("preserved_tax_multiplier",), "1"),
        (0, ("new_money",), True),
        (0, ("recharge",), True),
        (0, ("unknown_charges_released",), True),
        (0, ("ledger_reset",), True),
        (0, ("runtime_ledger_path",), ".cache/new-budget.db"),
        (0, ("runtime_ledger_projection_sha256",), "b" * 64),
        (0, ("old_profile_sha256",), "b" * 64),
        (1, ("status",), "pending"),
        (1, ("active_external_allowance_usd",), "4"),
        (1, ("entrypoints",), []),
        (1, ("historical_results_modified",), True),
        (2, ("pending_probe_claims",), ["pending"]),
        (2, ("retained_unknown_probe_charges", 0, "release_authorized"), True),
        (2, ("new_probe_pool_remaining_usd",), "6"),
        (3, ("authorized_total_usd",), "20"),
        (3, ("available_credit_usd",), "30"),
        (3, ("run_budget_mode",), "strict_reservation"),
        (4, ("funding", "zero_sum"), False),
        (4, ("ledger", "attempts"), 516),
        (4, ("ledger", "conservative_charged_usd"), "0"),
        (4, ("authorization", "new_budget_pool"), True),
        (4, ("no_history_exclusions",), False),
        (4, ("per_case_stop_usd",), "1"),
        (4, ("campaign_max_usd",), "6"),
        (5, ("FUNDING_SHA",), "PENDING_FUNDING_TRANSITION_SHA"),
        (5, ("PROFILE_SHA",), "PENDING_REVIEWED_PROFILE_SHA"),
        (5, ("BUDGET_HELPER_SHA",), "b" * 64),
        (6, (PROFILE,), "b" * 64),
        (6, (FUNDING_PATH,), "b" * 64),
        (6, ("scripts/probe_models.py",), "b" * 64),
    ]
    for position, path, value in mutations:
        variant = copy.deepcopy(data)
        target = variant[position]
        for name in path[:-1]:
            target = target[name]
        target[path[-1]] = value
        check(not funding_binding(*variant)["accepted"])
    for index in range(7):
        variant = copy.deepcopy(data)
        variant[index] = None
        check(not funding_binding(*variant)["accepted"])
    variant = copy.deepcopy(data)
    archive = next(r["archived_path"] for r in variant[1]["entrypoints"] if "archived_path" in r)
    variant[6][archive] = "b" * 64
    check(not funding_binding(*variant)["accepted"])
    code = "\n".join(f"{k} = {v!r}" for k, v in data[5].items())
    check(driver_funding_pins(code) == data[5])
    check(driver_funding_pins(code + "\nPROFILE_SHA = dynamic()") == {})
    check(driver_funding_pins("broken syntax !") == {})
    cap = data[4]
    remaining = DAILY_POOL - Decimal("6.6")
    before = {
        "projection_sha256": "a" * 64,
        "history_exclusions": [],
        "conservative_usd": "6.6",
        "all_time_limit_usd": str(POOL),
        "daily_limit_usd": str(DAILY_POOL),
        "remaining_all_time_usd": str(POOL - Decimal("6.6")),
        "remaining_day_usd": str(remaining),
        "day_conservative_usd": "6.6",
        "effective_campaign_usd": str(remaining),
        "campaign_max_usd": "5.4",
        "utc_day": "2026-10-25",
    }
    preflight = {
        "started_utc": "2026-10-25T10:00:00+00:00",
        "budget_before": before,
        "argv": [
            "headroom",
            "eval",
            "--runtime-profile",
            PROFILE,
            "--budget",
            "0.6",
            "--daily-budget",
            str(DAILY_POOL),
            "--campaign-budget",
            str(remaining),
        ],
    }
    check(funding_dispatch_binding(cap, preflight))
    for field, value in [
        ("daily_limit_usd", str(POOL)),
        ("all_time_limit_usd", str(DAILY_POOL)),
        ("effective_campaign_usd", "5.4"),
        ("history_exclusions", ["old"]),
        ("projection_sha256", "b" * 64),
        ("utc_day", "2026-10-24"),
    ]:
        variant = copy.deepcopy(preflight)
        variant["budget_before"][field] = value
        check(not funding_dispatch_binding(cap, variant))
    variant = copy.deepcopy(preflight)
    variant["argv"] += ["--daily-budget", str(DAILY_POOL)]
    check(not funding_dispatch_binding(cap, variant))
    for option, value in [
        ("--runtime-profile", OLD_PROFILE),
        ("--budget", "1"),
        ("--daily-budget", str(POOL)),
        ("--campaign-budget", "5.4"),
    ]:
        variant = copy.deepcopy(preflight)
        variant["argv"][variant["argv"].index(option) + 1] = value
        check(not funding_dispatch_binding(cap, variant))
    check(
        daily_ledger_bounds(
            [{"id": "x", "day": "2026-10-25"}], [{"run_id": "x", "charged_usd": "9"}]
        )["accepted"]
    )
    check(
        not daily_ledger_bounds(
            [{"id": "x", "day": "2026-10-25"}], [{"run_id": "x", "charged_usd": "10"}]
        )["accepted"]
    )
    check(
        not daily_ledger_bounds(
            [{"id": "x", "day": "2026-10-25"}], [{"run_id": "other", "charged_usd": "1"}]
        )["accepted"]
    )

    variant = copy.deepcopy(preflight)
    variant["started_utc"] = "2026-10-25T10:00:00"
    check(not funding_dispatch_binding(cap, variant))
    check(
        not daily_ledger_bounds(
            [{"id": "x", "day": "2026-99-25"}], [{"run_id": "x", "charged_usd": "1"}]
        )["accepted"]
    )
    variant = copy.deepcopy(data)
    variant[4]["funding"]["zero_sum"] = 1
    check(not funding_binding(*variant)["accepted"])
    variant = copy.deepcopy(data)
    variant[1]["inference_requests"] = False
    check(not funding_binding(*variant)["accepted"])

    # An absent prerequisite must refuse before any restricted private read.
    class MissingReader:
        def digest(self, name):
            return None

    try:
        read_funding_binding(MissingReader(), cap)
    except ValueError:
        check(True)
    else:
        check(False)
    for unsafe in (".env", "../outside", "/tmp/profile", ".cache/../profile"):
        try:
            restricted_funding_bytes(unsafe, {unsafe}, {})
        except ValueError:
            check(True)
        else:
            check(False)


def self_test():
    helpers = load_helpers()
    cli = helpers["cli"]
    checks = []

    def check(condition):
        assert condition
        checks.append(True)

    rows = [{"scenario_id": key, "run_id": str(i).zfill(32)} for i, key in enumerate(IDS)]
    selected, exact, _ = fixed_rows(rows)
    check(exact and len(selected) == 9)
    selected, exact, _ = fixed_rows(rows[:-1])
    check(not exact and len(selected) == 9 and selected[-1]["run_id"] is None)
    selected, exact, _ = fixed_rows(rows + rows[:1])
    check(not exact and selected[0]["run_id"] is None)
    _, exact, foreign = fixed_rows(rows + [{"scenario_id": "s2_fp32_adamw_1b"}])
    check(not exact and foreign == ["s2_fp32_adamw_1b"])
    check(cli.parse_argv(["fix", "--allocator-conf", "", "train.py"])["--allocator-conf"] == "")
    check(cli.parse_argv(["fix", "--allocator-conf", "", "--allocator-conf", "x"]) is None)
    check(
        cli.parse_argv(["fix", "train.py", "--", "--allocator-conf", "target-arg"])["script_args"]
        == ["--allocator-conf", "target-arg"]
    )
    payload = {"model": "test", "messages": []}
    receipt = {
        "schema_version": 1,
        "capture_point": "httpx_pre_transport",
        "wire_body_sha256": "a" * 64,
        "wire_body_utf8_bytes": 100,
        "delivery_confirmed": False,
        "payload": payload,
        "payload_status": "captured",
        "stored_payload_sha256": digest(
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        ),
    }
    check(request_evidence({"model": "test", "request_evidence": receipt})["payload_valid"] is True)
    receipt["payload"] = {"model": "tampered"}
    check(
        request_evidence({"model": "test", "request_evidence": receipt})["payload_valid"] is False
    )
    check(request_evidence({})["metadata_valid"] is None)
    retained = {
        "actual_usd": None,
        "charged_usd": ".2",
        "settled": 1,
        "dispatched": 1,
        "admission_kind": "verified_provider_bound",
        "charge_status": "reviewed_retained",
    }
    value = totals([retained])
    check(
        value["actual_total_usd"] is None
        and value["unknown_retained_usd"] == "0.2"
        and value["unresolved"] == 0
    )
    check(totals([retained | {"settled": 0}])["unresolved"] == 1)
    check(tri([True, None]) is None and tri([True, False, None]) is False)
    check(helpers["base"].threshold([True] + [None] * 8, 6) is None)
    request = {
        "target": "fit:22GB",
        "reclaim_reduction_pct": 20,
        "max_steps": 20,
        "max_seconds": 120,
        "budget_usd": "0.6",
        "daily_budget_usd": "9.99964904",
        "device": "cuda",
        "seed": 1337,
        "max_rounds": 6,
        "search_mode": "until_target",
        "allocator_conf": "expandable_segments:True",
        "numerical_reference": dict(REF_DEFAULTS),
        "runtime_profile": ".cache/tokenfactory-runtime.json",
        "research_enabled": True,
        "script": "/source/train.py",
        "source_root": "/source",
        "script_args": [],
        "repository_mode": False,
        "policy": {
            "allow_numerics_change": False,
            "allow_model_change": False,
            "allow_batch_grad_accum": True,
            "max_throughput_regression_pct": 25,
        },
    }
    argv = ["fix", "/source/train.py", "--source-root", "/source"]
    for option, field in (
        ("target", "target"),
        ("reclaim-reduction-pct", "reclaim_reduction_pct"),
        ("max-steps", "max_steps"),
        ("max-seconds", "max_seconds"),
        ("budget", "budget_usd"),
        ("daily-budget", "daily_budget_usd"),
        ("device", "device"),
        ("seed", "seed"),
        ("max-rounds", "max_rounds"),
        ("search-mode", "search_mode"),
        ("runtime-profile", "runtime_profile"),
        ("allocator-conf", "allocator_conf"),
    ):
        argv += ["--" + option, str(request[field])]
    argv += [
        "--max-throughput-regression-pct",
        "25",
        "--no-allow-numerics-change",
        "--allow-batch-grad-accum",
        "--research",
        "--reference-strategy",
        "legacy_small_batch",
        "--reference-cpu-bytes",
        str(16 * 1024**3),
        "--reference-disk-bytes",
        "0",
        "--reference-max-seconds",
        "0",
    ]
    check(cli.argument_match(argv, request, {}) is True)
    changed = list(argv)
    changed[changed.index("--allocator-conf") + 1] = ""
    check(cli.argument_match(changed, request, {}) is False)
    check(cli.argument_match(changed, request | {"allocator_conf": None}, {}) is True)
    for option in (
        "--reference-strategy",
        "--reference-cpu-bytes",
        "--reference-disk-bytes",
        "--reference-max-seconds",
    ):
        changed = list(argv)
        changed[changed.index(option) + 1] = "999"
        check(cli.argument_match(changed, request, {}) is False)
    check(
        cli.argument_match(argv + ["--reference-strategy", "legacy_small_batch"], request, {})
        is False
    )
    check(cli.parse_argv(["fix", {}]) is None)
    before = [
        {"path": "headroom/a.py", "sha256": "a" * 64},
        {"path": "tests/test_a.py", "sha256": "b" * 64},
    ]
    pins = {row["path"]: row["sha256"] for row in before}
    tested, committed = "1" * 40, "2" * 40
    same_head = bind_complete_sources(before, before, pins, pins, tested, tested)
    check(same_head["accepted"] and same_head["head_transition"] == "same_commit")
    post_commit = bind_complete_sources(before, before, pins, pins, tested, committed)
    check(
        post_commit["accepted"]
        and post_commit["head_transition"] == "post_test_commit_identical_sources"
        and post_commit["tested_head"] == tested
        and post_commit["executed_head"] == committed
    )
    changed = pins | {"tests/test_a.py": "c" * 64}
    omitted = {"headroom/a.py": "a" * 64}
    extra = pins | {"headroom/added.py": "d" * 64}
    for position in range(4):
        for mutation in (changed, omitted, extra):
            inputs = [before, before, pins, pins]
            inputs[position] = mutation
            check(not bind_complete_sources(*inputs, tested, committed)["accepted"])
    for invalid in (
        [],
        before + before[:1],
        [{"path": "../outside.py", "sha256": "a" * 64}],
        [{"path": "/absolute.py", "sha256": "a" * 64}],
        [{"path": "headroom//a.py", "sha256": "a" * 64}],
        [{"path": ".env", "sha256": "a" * 64}],
        [{"path": "headroom/a.py", "sha256": "invalid"}],
        [{"path": "headroom/a.py", "sha256": "a" * 64, "unknown": 1}],
        {".": "a" * 64},
    ):
        check(complete_source_map(invalid) is None)
    check(not bind_complete_sources(before, before, pins, pins, None, committed)["accepted"])
    legacy_count = len(checks)
    assert legacy_count == 47, "original audit tests must remain intact"
    funding_self_test(check)
    return {
        "self_test": "passed",
        "checks": len(checks),
        "legacy_checks_preserved": legacy_count,
        "funding_checks": len(checks) - legacy_count,
        "denominator": 9,
        "live_results_audited": False,
        "provider_calls": 0,
        "gpu_jobs": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execution", type=Path, default=OUT / "execution.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = None
    if args.output:
        path = args.output.absolute()
        if path.parent != OUT or path.exists():
            raise ValueError(
                "Only a new independent audit artifact in the v2 report directory is allowed"
            )
        output = path.open("x")
    try:
        result = self_test() if args.self_test else audit(args.execution)
        text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if output is not None:
            output.write(text)
        else:
            print(text, end="")
        return 0
    finally:
        if output is not None:
            output.close()


if __name__ == "__main__":
    raise SystemExit(main())
