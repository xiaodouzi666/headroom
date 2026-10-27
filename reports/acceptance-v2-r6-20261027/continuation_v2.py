"""Exact R5 failed-node financial continuation; preserves failed acceptance. Pure bytes only."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import PurePosixPath

SHA = re.compile(r"[0-9a-f]{64}")
ARTIFACT_KEYS = frozenset(
    {
        "audit",
        "audit_source",
        "execution",
        "campaign",
        "cap",
        "preflight",
        "review",
        "driver",
        "after",
        "active_profile",
        "transition",
    }
)
SCORE_GATES = frozenset({"at_least_six_targets", "at_least_six_valid_correct_first_causes"})
R5_GATE_KEYS = frozenset(
    [
        "active_capability_transition_bound",
        "all_nine_run_gates",
        "artifact_sources_stable",
        "at_least_six_targets",
        "at_least_six_valid_correct_first_causes",
        "audit_source_stable",
        "bound_root_review",
        "campaign_finished_live",
        "cap_unchanged",
        "complete_financial_history_chain_v2",
        "complete_tested_execution_sources_bound",
        "daily_pool_not_exceeded",
        "driver_unchanged",
        "exact_v2_nine_slots",
        "external_retained_debt_preserved",
        "fixed_review_denominator",
        "full_quality_passed",
        "historical_finance_preserved",
        "ledger_clear",
        "ledger_stable",
        "literal_nine_exit_zero",
        "manifest_bound",
        "minimum_remains_six",
        "new_execution_campaign_sha",
        "no_artifact_read_errors",
        "original_dispatch_daily_and_case_limits",
        "original_frozen_audit_preserved",
        "pool_not_exceeded",
        "r4_history_audit_preserved",
        "r5_single_probe_and_current_increment_bound",
        "retention_review_rows_stable",
        "reviewed_zero_sum_gift_partition",
        "source_application_evidence_complete",
        "store_stable",
        "strict_full_ultra_only",
        "unique_current_run_ids",
    ]
)

# This exception is only the independently frozen, actually failed R5 node.
# These hashes were reviewed by root; no self-recomputed "expected" values.
FROZEN_R5_NODE = {
    "audit": (
        "reports/acceptance-v2-r5-20261027/independent-audit-history-v3-final.json",
        "74a24f454312d36c4e2eac8077e6500fc4948f94cde428f4a81e9ff4461ee632",
    ),
    "audit_source": (
        "reports/acceptance-v2-r5-20261027/audit_mvp_v2_history_v3.py",
        "b74d03dbda3c75b48ecccc517b0dac86054e199c5eba0a1a6b9750341e8d27d3",
    ),
    "execution": (
        "reports/acceptance-v2-r5-20261027/execution.json",
        "fb12e27099d2bda4df32779677b94dd83238be393d0cfb1fa893ece051a021e0",
    ),
    "campaign": (
        "runs/evaluation/live/20261027T012645781689Z-c664cedf/campaign.json",
        "37bd60b6a8e5534814c3cd689517650e30cb521f13da9a610de026e28f959d44",
    ),
    "after": (
        ".cache/r5-final-finance-20261027/ledger-after.json",
        "539fab908493295aa84f0f65a79f9a54f601c62a34e7535e733a851f11f3aeb7",
    ),
}
# scenario, run UUID, terminal status, observed exit, target, first-cause, application evidence
FROZEN_R5_ROWS = (
    ("s1_batch_too_big", "9b8848bfa17a4265bfac52b6d24b530e", "completed", 0, False, True, True),
    ("s2_capacity_v2", "2942b1e3d8e34ead80baef0cdc468753", "completed", 0, True, True, True),
    (
        "s3_eval_no_grad_missing",
        "dd70d3a4742146d7a8192b38d84b77a2",
        "completed",
        0,
        True,
        True,
        True,
    ),
    (
        "s4_loss_accumulation_graph",
        "c1e990c9b3e148d580d510f2be726f76",
        "completed",
        0,
        True,
        True,
        True,
    ),
    (
        "s5_fragmentation_varlen",
        "10cd4f834ac8407ca2c6f421ffbe4a80",
        "needs_human",
        78,
        False,
        None,
        True,
    ),
    (
        "s6_full_vocab_logits_fp32",
        "3837b0c83e4e4b278556f84e3f4472b8",
        "needs_human",
        78,
        False,
        False,
        True,
    ),
    (
        "s7_frozen_params_optimizer_state",
        "e41010b22b264f5fa13c44ca80e053ed",
        "failed",
        1,
        False,
        True,
        None,
    ),
    (
        "s8_two_models_resident",
        "b53c73b733b5482f99ebba543328ae4d",
        "needs_human",
        78,
        False,
        True,
        True,
    ),
    ("nanogpt", "416ccae0aa6c42f08cf928f50e9973ea", "needs_human", 78, False, None, True),
)
OBSERVED_GATES = frozenset(
    [
        "billing_evidence_complete_and_consistent",
        "cost_complete_and_consistent",
        "harness_child_exit_zero",
        "markdown_7_sections",
        "owned_cleanup_verified",
        "real_live_provenance",
        "report_json_and_markdown",
        "report_numbers_provenance",
        "run_identity_consistent",
        "source_hash_matches_manifest",
        "wall_within_480_seconds",
    ]
)
CLI_CHECKS = frozenset(
    [
        "actual_return",
        "argv_recorded",
        "argv_semantics",
        "control_locations",
        "dispatched_once",
        "identity",
        "installed_stub",
        "invoked",
        "kind",
        "original_case_request",
        "original_preparation_request",
        "parent_exit_consistent",
        "parent_timing_consistent",
        "prepared_request",
        "quality_full_verified",
        "queued_nonpreparation_semantics",
        "raw_result",
        "receipt_projection",
        "report_identity",
        "report_request",
        "request_digest",
        "scenario_policy",
        "source_bound",
        "stderr_present",
        "stdout_present",
        "tested_bridge_source",
        "tested_cli_source",
        "worker_report_identity",
        "worker_report_request",
    ]
)
NANO_CLI_CHECKS = (CLI_CHECKS - {"original_preparation_request"}) | {
    "original_repository_request",
    "pinned_sources",
    "prepared_dataset",
    "repository_destination",
    "repository_identity",
    "repository_rewrite",
}

SEAL = object()


def need(value, code):
    if value is not True:
        raise ValueError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


@dataclass(frozen=True)
class ArtifactPin:
    path: str
    sha256: str


def validate_frozen_pins(pins):
    """Call before any reader callback. No PENDING or missing/extra artifact can pass."""
    need(type(pins) is dict and set(pins) == ARTIFACT_KEYS, "complete_r5_artifact_pins")
    paths = []
    for pin in pins.values():
        need(isinstance(pin, ArtifactPin), "pin_type")
        need(type(pin.sha256) is str and SHA.fullmatch(pin.sha256) is not None, "pending_pin")
        need(type(pin.path) is str, "pin_path")
        path = PurePosixPath(pin.path)
        need(
            bool(path.parts)
            and not path.is_absolute()
            and path.as_posix() == pin.path
            and all(x not in (".", "..") and not x.startswith(".env") for x in path.parts),
            "contained_canonical_nonsecret_path",
        )
        paths.append(pin.path)
    need(len(paths) == len(set(paths)), "distinct_artifact_paths")
    need(
        set(FROZEN_R5_NODE) == {"audit", "audit_source", "execution", "campaign", "after"},
        "complete_exact_failed_history_node",
    )
    for key, pair in FROZEN_R5_NODE.items():
        need(
            type(pair) is tuple
            and len(pair) == 2
            and type(pair[1]) is str
            and SHA.fullmatch(pair[1]) is not None,
            "pending_exact_failed_history_node",
        )
        need((pins[key].path, pins[key].sha256) == pair, "only_exact_reviewed_failed_r5_node")
    return True


def load_pinned_artifacts(pins, reader):
    """Reader must be the approved bounded no-follow reader. Never reads while PENDING."""
    validate_frozen_pins(pins)
    result = {}
    for key, pin in pins.items():
        raw = reader(pin.path)
        need(type(raw) is bytes and len(raw) <= 4 * 1024 * 1024, "bounded_raw_bytes")
        need(digest(raw) == pin.sha256, "artifact_hash")
        result[key] = raw
    return result


def source_gate_keys(source):
    tree = ast.parse(source.decode("utf-8"))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "audit"]
    need(len(functions) == 1, "one_frozen_audit_function")
    keys = []
    for node in ast.walk(functions[0]):
        if isinstance(node, ast.Assign):
            for dest in node.targets:
                if (
                    isinstance(dest, ast.Name)
                    and dest.id == "gates"
                    and isinstance(node.value, ast.Dict)
                ):
                    keys.extend(ast.literal_eval(k) for k in node.value.keys)
                if (
                    isinstance(dest, ast.Subscript)
                    and isinstance(dest.value, ast.Name)
                    and dest.value.id == "gates"
                ):
                    keys.append(ast.literal_eval(dest.slice))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "gates"
            and node.func.attr == "update"
        ):
            keys.extend(k.arg for k in node.keywords)
    need(len(keys) == len(set(keys)) and set(keys) == R5_GATE_KEYS, "frozen_full_gate_contract")
    return frozenset(keys)


def historical_non_score_gates(audit, source):
    """A financial-only classification of one immutable failed campaign, not acceptance."""
    source_gate_keys(source)
    gates = audit["gates"]
    need(type(gates) is dict and set(gates) == R5_GATE_KEYS, "complete_report_gate_contract")
    expected = dict.fromkeys(R5_GATE_KEYS, True)
    expected.update(
        all_nine_run_gates=False,
        literal_nine_exit_zero=False,
        source_application_evidence_complete=None,
        at_least_six_targets=False,
    )
    need(all(gates[key] is value for key, value in expected.items()), "exact_frozen_r5_gate_values")
    need(
        audit["accepted_observed_campaign_gates"] is False
        and type(audit["fixed_denominator"]) is int
        and audit["fixed_denominator"] == 9
        and audit["historical_scores_used"] is False
        and audit["human_controls_counted"] is False
        and audit["errors"] == [],
        "failed_campaign_facts_preserved",
    )
    counts = {
        "targets": 3,
        "targets_unknown": 0,
        "valid_correct_first_causes": 6,
        "first_causes_unknown": 2,
    }
    need(
        type(audit["counts"]) is dict
        and set(audit["counts"]) == set(counts)
        and all(
            type(audit["counts"][key]) is int and audit["counts"][key] == value
            for key, value in counts.items()
        ),
        "exact_frozen_r5_counts",
    )
    rows = audit["rows"]
    need(type(rows) is list and len(rows) == 9, "complete_frozen_r5_failure_rows")
    failures = []
    for row, identity in zip(rows, FROZEN_R5_ROWS, strict=True):
        scenario, run_id, status, code, target, cause, application = identity
        need(
            row["scenario_id"] == scenario
            and row["run_id"] == run_id
            and row["target"] is target
            and row["cause"] is cause
            and row["per_run_gates"] is (code == 0),
            "exact_frozen_r5_row_identity",
        )
        observed, cli, applied = row["observed"], row["cli"], row["source_application"]
        need(
            observed["status"] == status
            and type(observed["gates"]) is dict
            and set(observed["gates"]) == OBSERVED_GATES
            and all(
                value is (code == 0) if key == "harness_child_exit_zero" else value is True
                for key, value in observed["gates"].items()
            ),
            "only_recorded_terminal_exit_failure",
        )
        checks = NANO_CLI_CHECKS if scenario == "nanogpt" else CLI_CHECKS
        need(
            cli["chain_verified"] is True
            and type(cli["observed_exit_code"]) is int
            and cli["observed_exit_code"] == code
            and type(cli["checks"]) is dict
            and set(cli["checks"]) == checks
            and all(value is True for value in cli["checks"].values()),
            "complete_cli_evidence_despite_terminal_failure",
        )
        need(
            applied["row_evidence_complete"] is application and applied["errors"] == [],
            "only_s7_application_evidence_remains_unknown",
        )
        if not target:
            selection = applied["selection"]
            need(
                selection["selection"] == "explicit_none"
                and selection["selected_round"] is None
                and selection["selected_preserved_verified"] is True
                and selection["selected_code_chain_verified"] is None
                and selection["errors"] == [],
                "no_failed_case_patch_or_equivalence_claim",
            )
        if code != 0:
            failures.append(
                {
                    "scenario_id": scenario,
                    "run_id": run_id,
                    "status": status,
                    "observed_exit_code": code,
                    "target": False,
                    "harness_child_exit_zero": False,
                    "source_application_evidence_complete": application,
                    "cli_chain_verified": True,
                    "selected_patch": None,
                }
            )
    return {
        "scope": "financial_continuation_only",
        "historical_campaign_accepted": False,
        "historical_campaign_exit_code": 1,
        "historical_counts": counts,
        "historical_gate_values": dict(gates),
        "technical_failures": failures,
        "failed_values_rewritten": False,
        "s7_application_evidence_remains_unknown": True,
        "historical_targets_count_toward_next_round": False,
    }


def source_history_binding(finance, audit, review, preflight):
    """Recompute only frozen R5 inventories; never read R6's current source files."""
    inventory = finance.R4.complete_source_map(review["source_pins"])
    need(inventory is not None, "historical_complete_source_inventory")
    source = audit["source_binding"]
    expected = digest(canonical(inventory))
    need(
        source["accepted"] is True
        and source["quality_receipts_bound"] is True
        and source["complete_before_after_review_equal"] is True
        and source["all_listed_current_source_hashes_match"] is True
        and source["recorded_heads_valid"] is True,
        "historical_source_proof",
    )
    labels = {"before", "after", "review", "current"}
    need(
        set(source["inventory_sha256"]) == labels
        and all(x == expected for x in source["inventory_sha256"].values())
        and set(source["source_counts"]) == labels
        and all(type(x) is int and x == len(inventory) for x in source["source_counts"].values()),
        "historical_inventory_hashes",
    )
    need(
        all(audit["source_hashes"].get(path) == sha for path, sha in inventory.items()),
        "historical_read_hashes",
    )
    need(
        audit["quality"]["accepted"] is True
        and source["tested_head"] == audit["quality"]["git_head"]
        and source["executed_head"] == preflight["source_commit"]
        and all(
            type(h) is str and re.fullmatch(r"[0-9a-f]{40}", h)
            for h in (source["tested_head"], source["executed_head"])
        ),
        "historical_tested_executed_heads",
    )
    receipt = review["quality_receipt"]
    for path, sha in ((receipt["path"], receipt["sha256"]),):
        need(audit["source_hashes"].get(path) == sha, "historical_quality_receipt_pin")
    return {
        "inventory_sha256": expected,
        "source_count": len(inventory),
        "tested_head": source["tested_head"],
        "executed_head": source["executed_head"],
        "current_source_reread": False,
    }


@dataclass(frozen=True)
class VerifiedR5Continuation:
    public_json: bytes
    _seal: object
    _fingerprint: str
    _finance: object


def is_verified(value, finance):
    return (
        isinstance(value, VerifiedR5Continuation)
        and value._seal is SEAL
        and value._finance is finance
        and digest(value.public_json) == value._fingerprint
    )


def public_continuation(value, finance):
    need(is_verified(value, finance), "verified_continuation_required")
    return json.loads(value.public_json)


def verify_completed_r5_history(*, finance, r4_inputs, probe_inputs, chain_pins, artifacts, pins):
    """Rebuild old chain, then admit exactly the frozen R5 addition. Never dispatches."""
    validate_frozen_pins(pins)
    need(type(artifacts) is dict and set(artifacts) == ARTIFACT_KEYS, "complete_artifacts")
    for key, pin in pins.items():
        need(
            type(artifacts[key]) is bytes
            and len(artifacts[key]) <= 4 * 1024 * 1024
            and digest(artifacts[key]) == pin.sha256,
            "artifact_hash",
        )
    finance.require_frozen_pins(chain_pins, stage="audit")
    need(
        chain_pins["r5_cap"] == pins["cap"].sha256
        and chain_pins["r5_preflight"] == pins["preflight"].sha256
        and chain_pins["new_profile"] == pins["active_profile"].sha256
        and chain_pins["profile_transition"] == pins["transition"].sha256,
        "chain_pins_match_r5",
    )
    root = finance.verify_root_and_probe(
        r4_inputs=r4_inputs, probe_inputs=probe_inputs, pins=chain_pins
    )
    need(
        root["accepted"] is True and finance.is_verified_probe_finance(root["probe_finance"]),
        "original_sealed_chain_required",
    )
    docs = {
        k: finance.parse(v) for k, v in artifacts.items() if k not in {"driver", "audit_source"}
    }
    audit, execution, campaign, cap, preflight, review = (
        docs[k] for k in ("audit", "execution", "campaign", "cap", "preflight", "review")
    )
    for key in ("cap", "preflight", "review", "driver"):
        need(
            audit["source_hashes"].get(pins[key].path) == pins[key].sha256,
            "r5_auxiliary_pins_bound_to_fixed_audit",
        )
    classification = historical_non_score_gates(audit, artifacts["audit_source"])
    need(
        audit["audit_source_sha256"] == pins["audit_source"].sha256
        and audit["campaign"] == pins["campaign"].path
        and review["driver_sha256"] == pins["driver"].sha256
        and review["cap_sha256"] == pins["cap"].sha256
        and preflight["review_sha256"] == pins["review"].sha256
        and execution["exit_code"] == 1
        and type(execution["exit_code"]) is int
        and len(execution["campaigns"]) == 1
        and execution["campaigns"][0]["path"] == pins["campaign"].path
        and execution["campaigns"][0]["sha256"] == pins["campaign"].sha256,
        "r5_artifact_identity",
    )
    ids = [row["run_id"] for row in campaign["rows"]]
    need(
        [row["scenario_id"] for row in campaign["rows"]] == list(finance.R4.IDS)
        and len(ids) == len(set(ids)) == 9
        and all(type(x) is str and finance.R4.UUID.fullmatch(x) for x in ids)
        and [row["run_id"] for row in audit["rows"]] == ids
        and [row["scenario_id"] for row in audit["rows"]] == list(finance.R4.IDS),
        "r5_exact_nine_identity",
    )
    need(
        campaign["status"] == "finished"
        and campaign["provenance"] == "live"
        and all(
            row["condition"] == "full_ultra"
            and row["policy_name"] == "strict"
            and row["search_mode"] == "until_target"
            for row in campaign["rows"]
        ),
        "r5_original_execution_mode",
    )
    source = source_history_binding(finance, audit, review, preflight)
    binding = review["runtime_profile_binding"]
    need(
        binding
        == cap["catalogue"]["runtime_profile_binding"]
        == audit["runtime_capability_binding"],
        "frozen_runtime_binding",
    )
    active_sha, active_path = pins["active_profile"].sha256, pins["active_profile"].path
    need(
        binding["active_profile_sha256"] == active_sha
        and binding["active_profile_path"] == active_path
        and binding["base_funding_profile_sha256"] == finance.BASE_PROFILE_SHA,
        "same_active_profile",
    )
    old_profile, active_profile = (
        finance.parse(probe_inputs["base_profile_raw"]),
        copy.deepcopy(docs["active_profile"]),
    )
    caps = active_profile["models"]["super"]["capabilities"]
    allowed = {"low_effort_method", "low_effort_evidence", "low_effort_evidence_sha256"}
    need(
        not (allowed & old_profile["models"]["super"]["capabilities"].keys())
        and caps["low_effort_method"] == "chat_template_kwargs"
        and caps["low_effort_evidence_sha256"] == chain_pins["probe_receipt"]
        and binding["input_file_hashes"].get(caps["low_effort_evidence"])
        == chain_pins["probe_receipt"],
        "same_verified_capability",
    )
    for key in allowed:
        caps.pop(key)
    need(
        canonical(active_profile) == canonical(old_profile),
        "no_financial_model_price_profile_change",
    )
    transition = binding["profile_transition"]
    need(
        transition["valid"] is True
        and transition["financial_or_ledger_changes"] is False
        and transition["full_projection_equal"] is True
        and transition["transition_receipt_sha256"] == pins["transition"].sha256
        and transition["new_profile_sha256"] == active_sha
        and transition["base_profile_sha256"] == finance.BASE_PROFILE_SHA,
        "same_transition",
    )
    dispatch = finance.verify_r5_dispatch(
        probe_inputs["after"],
        cap,
        preflight,
        active_profile_path=active_path,
        active_profile_sha256=active_sha,
    )
    before, after = finance.snapshot(probe_inputs["after"]), finance.snapshot(artifacts["after"])
    finance.closed(after)
    old_ids = {row["id"] for row in before["budget_runs"]}
    need(not old_ids.intersection(ids), "r5_ids_are_new")
    need({row["id"] for row in after["budget_runs"]} == old_ids | set(ids), "only_nine_new_runs")
    need(
        canonical([row for row in after["budget_runs"] if row["id"] not in ids])
        == canonical(before["budget_runs"]),
        "all_prior_run_columns",
    )
    need(
        canonical([row for row in after["budget_attempts"] if row["run_id"] not in ids])
        == canonical(before["budget_attempts"]),
        "all_prior_attempt_columns",
    )
    need(
        canonical(after["budget_retention_reviews"])
        == canonical(before["budget_retention_reviews"]),
        "all_retention_review_columns",
    )
    need(
        all(
            row["budget_mode"] == "actual_usage"
            and finance.R4.money(row["limit_usd"]) == Decimal("0.6")
            for row in after["budget_runs"]
            if row["id"] in ids
        ),
        "original_case_limits",
    )
    additions = [row for row in after["budget_attempts"] if row["run_id"] in ids]
    totals = finance.R4.totals(after["budget_attempts"])
    report = audit["finance"]
    history = report["financial_history_transition"]
    need(
        history["accepted"] is True
        and history["r4_root"] == root["r4_root"]
        and history["single_probe"] == finance.public_probe_finance(root["probe_finance"])
        and history["r5_dispatch"] == dispatch,
        "unchanged_r4_probe_dispatch_chain",
    )
    need(
        report["prior_projection"] == finance.projection(before)
        and report["all_time_projection_before"]
        == report["all_time_projection_after"]
        == finance.projection(after)
        and finance.R4.same_totals(report["campaign"], finance.R4.totals(additions))
        and finance.R4.same_totals(report["all_time"], totals)
        and finance.R4.money(report["remaining_pool_usd"])
        == finance.LIFETIME - finance.R4.money(totals["conservative_charged_usd"])
        and report["daily_ledger_bounds"]
        == finance.R4.daily_ledger_bounds(after["budget_runs"], after["budget_attempts"]),
        "r5_audit_exact_finance",
    )
    need(
        finance.R4.money(finance.R4.totals(additions)["conservative_charged_usd"])
        <= finance.R4.money(dispatch["effective_campaign_usd"]),
        "r5_campaign_limit",
    )
    public = {
        "schema": "headroom.r6-r5-financial-continuation.v2",
        "financial_history_verified": True,
        "historical_campaign_accepted": False,
        "dispatch_permitted": False,
        "historical_failure_classification": classification,
        "r5_after_sha256": pins["after"].sha256,
        "r5_after_projection": finance.projection(after),
        "r5_after": finance.summary(after),
        "r5_audit_sha256": pins["audit"].sha256,
        "r5_audit_source_sha256": pins["audit_source"].sha256,
        "original_probe_receipt_sha256": chain_pins["probe_receipt"],
        "original_probe_after_sha256": chain_pins["probe_after"],
        "active_profile_path": active_path,
        "active_profile_sha256": active_sha,
        "base_funding_profile_sha256": finance.BASE_PROFILE_SHA,
        "source_history": source,
        "historical_scores_used": False,
        "new_probe_or_funding": False,
    }
    raw = canonical(public)
    return VerifiedR5Continuation(raw, SEAL, digest(raw), finance)


def verify_next_dispatch(
    value, *, finance, after_raw, current_snapshot_raw, active_profile_raw, cap, preflight
):
    """Requires a fresh caller-read three-table snapshot, not just a monetary total."""
    proof = public_continuation(value, finance)
    need(
        digest(after_raw) == proof["r5_after_sha256"]
        and digest(active_profile_raw) == proof["active_profile_sha256"],
        "same_frozen_parent_profile",
    )
    need(
        canonical(finance.snapshot(current_snapshot_raw)) == canonical(finance.snapshot(after_raw)),
        "current_full_three_table_snapshot_equals_parent",
    )
    need(
        cap["financial_parent"] == proof
        and preflight["financial_parent_sha256"] == value._fingerprint,
        "r6_parent_binding",
    )
    need(
        cap["authorization"]["fixed_primary_denominator"] == 9
        and cap["authorization"]["minimum_target_met"] == 6
        and preflight["scenario_ids"] == list(finance.R4.IDS)
        and preflight["fixed_acceptance_denominator"] == 9
        and preflight["max_rounds"] == 6
        and preflight["per_case_wall_seconds"] == 480
        and preflight["historical_results_preserved"] is True
        and preflight["quality_early_stop"] is False
        and preflight["recharge"] is False,
        "unchanged_fixed_nine_acceptance_contract",
    )
    result = finance.verify_r5_dispatch(
        after_raw,
        cap,
        preflight,
        active_profile_path=proof["active_profile_path"],
        active_profile_sha256=proof["active_profile_sha256"],
    )
    return result | {
        "schema": "headroom.r6-financial-dispatch.v2",
        "historical_campaign_accepted": False,
        "parent_sha256": value._fingerprint,
        "new_probe_or_funding": False,
    }
