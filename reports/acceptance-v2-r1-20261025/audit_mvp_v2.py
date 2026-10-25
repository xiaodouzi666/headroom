"""Independent, read-only audit of the one approved v2 nine-case campaign.

Only versioned audit output may be written. No provider, GPU, subprocess, pickle,
profile construction, Store constructor, or BudgetLedger constructor is used.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUT = ROOT / "reports/acceptance-v2-r1-20261025"
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
POOL = Decimal("9.99964904")
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
        "unchanged_gift_pool": money(cap.get("pool_usd")) == POOL
        and cap.get("authorization", {}).get("gift_only") is True
        and cap.get("authorization", {}).get("recharge") is False,
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
        "pool_usd": str(POOL),
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
    gates["artifact_sources_stable"] = not changed
    errors = reader.errors + base.ERRORS
    gates["no_artifact_read_errors"] = not errors
    return {
        "schema_version": 1,
        "audit_kind": "independent_v2_mvp_nine",
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
        "audit_source_sha256": reader.digest(Path(__file__)),
        "actions": {
            "model_calls": 0,
            "gpu_jobs": 0,
            "subprocesses": 0,
            "credential_reads": 0,
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
    return {
        "self_test": "passed",
        "checks": len(checks),
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
