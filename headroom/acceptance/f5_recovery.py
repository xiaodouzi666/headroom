"""One reviewed F5 recovery after an exact, zero-dispatch credential prerequisite failure.

Old claims and ledger rows are immutable. No credential is read or copied here.
The caller must review the exact proposal SHA; all execution still uses normal CLI
binding, budget and cleanup paths. This is not a general retry facility.
"""

import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from pathlib import Path

from headroom.acceptance.allocation import (
    LIMIT,
    VerifiedChildBinding,
    _budget_state,
    _checked_document,
    _cost_summary,
    _quiet_pool,
    _signed,
    digest,
    registry,
    require,
    safe,
    verify_receipt,
)
from headroom.acceptance.common import file_record, read_json
from headroom.budget import money

SCHEMA = "headroom.final48.f5-zero-dispatch-recovery.v1"
PROPOSAL = "headroom.final48.f5-zero-dispatch-proposal.v1"
TABLE = "f5_zero_dispatch_recoveries"
ENV_REASON = "Private regular .env file with mode 0600 is required"


def _original(conn, binding):
    rows = {}
    for key, table, column, value in (
        ("child", "feature_children", "run_id", binding["run_id"]),
        ("parent", "feature_parents", "parent_id", binding["parent_id"]),
        ("claim", "claims", "run_id", binding["parent_id"]),
    ):
        row = conn.execute(f"SELECT * FROM {table} WHERE {column}=?", (value,)).fetchone()
        require(row is not None, "F5_RECOVERY_ORIGINAL_MISSING")
        rows[key] = dict(row)
    require(
        binding["scope"] == "F5"
        and binding["slot_id"] == "clean-s3"
        and rows["child"]["state"] == "settled"
        and rows["parent"]["state"] == rows["claim"]["state"] == "completed"
        and rows["claim"]["task_scope"] == "F5"
        and rows["claim"]["execution_key"] == "once"
        and json.loads(rows["child"]["payload"]) == binding,
        "F5_RECOVERY_ORIGINAL_NOT_SETTLED",
    )
    settlement = json.loads(rows["child"]["settlement"])
    require(
        settlement["cost_resolved"] is True
        and money(settlement["actual_usd"]) == money(settlement["charged_usd"]) == 0,
        "F5_RECOVERY_ORIGINAL_NOT_ZERO",
    )
    return rows


def _proof(binding, outcome_path, receipt):
    """Independently check original ledger, Store, terminal receipt and absent Lab."""
    require(binding["receipt_sha256"] == receipt["receipt_sha256"], "F5_RECOVERY_RECEIPT_CHANGED")
    path = safe(Path(binding["project_root"]), Path(outcome_path))
    record = {"path": str(path), **file_record(path, LIMIT)}
    outcome = read_json(path, max_bytes=LIMIT)
    run_id = binding["run_id"]
    report, timing = outcome.get("report", {}), outcome.get("evaluation_timing", {})
    cli, search = timing.get("cli", {}), outcome.get("search", {})
    require(
        outcome.get("run_id") == run_id
        and outcome.get("status") == "needs_human"
        and outcome.get("reason") == ENV_REASON
        and outcome.get("target_met") is False
        and search.get("stop_reason") == "runtime_not_ready"
        and search.get("rounds_executed") == 0
        and report.get("evidence") == {}
        and report.get("rounds") == []
        and report.get("usage", {}).get("calls") == 0
        and timing.get("cleanup_verified") is True
        and timing.get("deadline_exceeded") is False
        and timing.get("within_wall_limit") is True
        and timing.get("worker_exit_code") == 78
        and cli.get("run_id") == run_id
        and cli.get("verified") is True
        and cli.get("invoked") is True
        and cli.get("observed_exit_code") == 78,
        "F5_RECOVERY_NOT_ENV_PREFLIGHT",
    )
    job = safe(Path(binding["project_root"]), Path(outcome["run_dir"]))
    require(job.name == run_id and not (job / "lab").exists(), "F5_RECOVERY_BASELINE_EXISTS")
    store = safe(Path(binding["project_root"]), job.parent.parent / "results.sqlite3")
    require(store.is_file() and not store.is_symlink(), "F5_RECOVERY_STORE_MISSING")
    with closing(sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)) as conn:
        require(
            conn.execute("SELECT count(*) FROM llm_calls WHERE run_id=?", (run_id,)).fetchone()[0]
            == 0,
            "F5_RECOVERY_PROVIDER_ATTEMPT",
        )
        require(
            conn.execute(
                "SELECT count(*) FROM events WHERE run_id=? AND kind LIKE 'baseline.%'", (run_id,)
            ).fetchone()[0]
            == 0,
            "F5_RECOVERY_BASELINE_EXISTS",
        )
    state = _budget_state(receipt)
    old = state["runs"].get(run_id)
    require(
        old is not None
        and old["status"] == "closed"
        and not old["halt_reason"]
        and old["budget_mode"] == "strict_reservation"
        and not any(row["run_id"] == run_id for row in state["attempts"]),
        "F5_RECOVERY_PROVIDER_ATTEMPT",
    )
    original_intent = report.get("run", {}).get("feature_intent")
    require(
        isinstance(original_intent, dict) and digest(original_intent) == binding["intent_sha256"],
        "F5_RECOVERY_OLD_INTENT_CHANGED",
    )
    require(
        file_record(path, LIMIT) == {k: v for k, v in record.items() if k != "path"},
        "F5_RECOVERY_EVIDENCE_CHANGED",
    )
    return record, original_intent, state


def _intent(original, new, receipt):
    from headroom.acceptance.feature_allocation import intent_sha256
    from headroom.cli_execution import feature_checkout

    old, candidate = json.loads(json.dumps(original)), json.loads(json.dumps(new))
    old_checkout = old["payload"].pop("checkout")
    new_checkout = candidate["payload"].pop("checkout")
    require(
        old == candidate and old_checkout["path"] == new_checkout["path"],
        "F5_RECOVERY_REQUEST_CHANGED",
    )
    require(
        new["kind"] == "fix"
        and new["runtime_profile"] == receipt["profile_path"]
        and money(new["daily_budget_usd"]) == money(receipt["amounts"]["daily_limit_usd"])
        and 0 < money(new["budget_usd"]) <= money("0.30"),
        "F5_RECOVERY_CAP_CHANGED",
    )
    # Only code pins/commit may change; the exact Lab workload remains identical.
    workload = "scenarios/s3_eval_no_grad_missing/"
    require(
        {k: v for k, v in old_checkout["source_files"].items() if k.startswith(workload)}
        == {k: v for k, v in new_checkout["source_files"].items() if k.startswith(workload)},
        "F5_RECOVERY_WORKLOAD_CHANGED",
    )
    checkout = feature_checkout(new)
    require(checkout != Path(receipt["project_root"]), "F5_RECOVERY_CLEAN_CHECKOUT_REQUIRED")
    # Metadata only: do not consume the recovery while the same prerequisite is broken.
    env = checkout / ".env"
    info = env.lstat() if env.exists() or env.is_symlink() else None
    require(
        info is not None
        and stat.S_ISREG(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_uid == os.getuid(),
        "F5_RECOVERY_ENV_NOT_READY",
    )
    return intent_sha256(new)


def _pool_digest(state):
    return digest({"runs": state["runs"], "attempts": state["attempts"]})


def prepare_f5_recovery(original_binding, intent, *, outcome_path, run_id):
    """Read-only proposal. No claim, credential access, runtime, or model dispatch."""
    require(
        isinstance(run_id, str) and re.fullmatch(r"[0-9a-f]{32}", run_id),
        "F5_RECOVERY_RUN_ID_INVALID",
    )
    _checked_document(original_binding, "headroom.final48.feature-child.v1")
    root = original_binding["project_root"]
    receipt = verify_receipt(original_binding["receipt_path"], project_root=root)
    evidence, original_intent, state = _proof(original_binding, outcome_path, receipt)
    require(run_id not in state["runs"], "F5_RECOVERY_RUN_ALREADY_EXISTS")
    _quiet_pool(state)
    from headroom.acceptance.feature_allocation import _quiet_registry

    with registry(root) as conn:
        _quiet_registry(conn)
        original = _original(conn, original_binding)
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
        ).fetchone():
            require(
                not conn.execute(
                    f"SELECT 1 FROM {TABLE} WHERE original_run_id=? OR run_id=?",
                    (original_binding["run_id"], run_id),
                ).fetchone(),
                "F5_RECOVERY_ALREADY_CLAIMED",
            )
    intent_hash = _intent(original_intent, intent, receipt)
    cap = min(
        money("0.30"),
        money(receipt["feature_scope_caps_usd"]["F5"]),
        money(receipt["task_run_caps_usd"]["F5"]),
    )
    require(money(intent["budget_usd"]) <= cap, "F5_RECOVERY_CAP_CHANGED")
    ceiling = min(money(receipt["amounts"]["approved_net_usd"]), state["charged"] + cap)
    require(state["charged"] + money(intent["budget_usd"]) <= ceiling, "F5_RECOVERY_POOL_EXHAUSTED")
    return {
        "schema": PROPOSAL,
        "original_binding": original_binding,
        "original_registry": original,
        "outcome": evidence,
        "intent": intent,
        "intent_sha256": intent_hash,
        "run_id": run_id,
        "pool_state_sha256": _pool_digest(state),
        "prior_charged_usd": str(state["charged"]),
        "total_limit_usd": str(ceiling),
        "combined_f5_limit_usd": str(cap),
    }


def claim_f5_recovery(proposal_path, *, expected_sha256):
    """Claim exactly one reviewed proposal; never change any original row."""
    path = Path(proposal_path)
    record = file_record(path, LIMIT)
    require(record["sha256"] == expected_sha256, "F5_RECOVERY_PROPOSAL_CHANGED")
    proposal = read_json(path, max_bytes=LIMIT)
    require(proposal.get("schema") == PROPOSAL, "F5_RECOVERY_SCHEMA_INVALID")
    fresh = prepare_f5_recovery(
        proposal["original_binding"],
        proposal["intent"],
        outcome_path=proposal["outcome"]["path"],
        run_id=proposal["run_id"],
    )
    require(
        fresh == proposal and file_record(path, LIMIT) == record, "F5_RECOVERY_PROPOSAL_CHANGED"
    )
    old, intent = proposal["original_binding"], proposal["intent"]
    binding = _signed(
        {
            "schema": SCHEMA,
            "scope": "F5",
            "slot_id": "clean-s3",
            "run_id": proposal["run_id"],
            "project_root": old["project_root"],
            "receipt_path": old["receipt_path"],
            "receipt_sha256": old["receipt_sha256"],
            "run_limit_usd": intent["budget_usd"],
            "daily_limit_usd": intent["daily_budget_usd"],
            "total_limit_usd": proposal["total_limit_usd"],
            "intent_sha256": proposal["intent_sha256"],
            "proposal_sha256": expected_sha256,
            "proposal": proposal,
        }
    )
    receipt = verify_receipt(old["receipt_path"], project_root=old["project_root"])
    with registry(old["project_root"]) as conn:
        from headroom.acceptance.feature_allocation import _quiet_registry

        _quiet_registry(conn)
        require(
            _original(conn, old) == proposal["original_registry"], "F5_RECOVERY_ORIGINAL_CHANGED"
        )
        state = _budget_state(receipt)
        _quiet_pool(state)
        require(_pool_digest(state) == proposal["pool_state_sha256"], "F5_RECOVERY_POOL_CHANGED")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {TABLE}("
            "original_run_id TEXT PRIMARY KEY,run_id TEXT UNIQUE NOT NULL,"
            "payload TEXT NOT NULL,state TEXT NOT NULL,settlement TEXT)"
        )
        try:
            conn.execute(
                f"INSERT INTO {TABLE} VALUES(?,?,?,'claimed',NULL)",
                (old["run_id"], binding["run_id"], json.dumps(binding, sort_keys=True)),
            )
        except sqlite3.IntegrityError:
            require(False, "F5_RECOVERY_ALREADY_CLAIMED")
    return binding


def _record(binding):
    _checked_document(binding, SCHEMA)
    proposal = binding["proposal"]
    require(
        digest(proposal["intent"]) == binding["intent_sha256"]
        and proposal["run_id"] == binding["run_id"],
        "F5_RECOVERY_BINDING_CHANGED",
    )
    receipt = verify_receipt(binding["receipt_path"], project_root=binding["project_root"])
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "F5_RECOVERY_RECEIPT_CHANGED")
    with registry(binding["project_root"]) as conn:
        from headroom.acceptance.feature_allocation import _quiet_registry

        _quiet_registry(conn, allowed_run=binding["run_id"])
        row = conn.execute(f"SELECT * FROM {TABLE} WHERE run_id=?", (binding["run_id"],)).fetchone()
        require(
            row is not None and row["state"] == "claimed" and json.loads(row["payload"]) == binding,
            "F5_RECOVERY_NOT_ACTIVE",
        )
        require(
            _original(conn, proposal["original_binding"]) == proposal["original_registry"],
            "F5_RECOVERY_ORIGINAL_CHANGED",
        )
    evidence, original, state = _proof(
        proposal["original_binding"], proposal["outcome"]["path"], receipt
    )
    require(evidence == proposal["outcome"], "F5_RECOVERY_EVIDENCE_CHANGED")
    _intent(original, proposal["intent"], receipt)
    return receipt, state


def verify_f5_recovery(binding, *, intent, run_id, project_root=None, environ=None):
    """Called through the standard feature verifier, including every reserve."""
    require(
        run_id == binding["run_id"]
        and (project_root is None or str(Path(project_root).resolve()) == binding["project_root"])
        and digest(intent) == binding["intent_sha256"],
        "F5_RECOVERY_INTENT_CHANGED",
    )
    receipt, state = _record(binding)
    # Also enforce a caller's explicit environment selection through the existing verifier.
    verify_receipt(binding["receipt_path"], project_root=binding["project_root"], environ=environ)
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    require(
        run is None
        or run["status"] == "open"
        and run["budget_mode"] == "strict_reservation"
        and money(run["limit_usd"]) <= money(binding["run_limit_usd"]),
        "F5_RECOVERY_RUN_CHANGED",
    )
    own = [r for r in state["attempts"] if r["run_id"] == run_id]
    require(
        _cost_summary(state, own)["charged"] <= money(binding["proposal"]["combined_f5_limit_usd"])
        and state["charged"] < money(binding["total_limit_usd"]),
        "F5_RECOVERY_CAP_EXCEEDED",
    )
    return VerifiedChildBinding(
        receipt,
        run_id,
        binding["run_limit_usd"],
        binding["daily_limit_usd"],
        binding["total_limit_usd"],
    )


def finish_f5_recovery(binding, *, execution_terminal, cleanup_verified):
    _receipt, state = _record(binding)
    run = state["runs"].get(binding["run_id"])
    own = [r for r in state["attempts"] if r["run_id"] == binding["run_id"]]
    cost = _cost_summary(state, own)
    settled = (
        execution_terminal is True
        and cleanup_verified is True
        and run is not None
        and run["status"] == "closed"
        and not run["halt_reason"]
        and cost["resolved"]
        and state["resolved"]
        and all(r["status"] == "closed" and not r["halt_reason"] for r in state["runs"].values())
        and cost["charged"] <= money(binding["run_limit_usd"])
        and cost["charged"] <= money(binding["proposal"]["combined_f5_limit_usd"])
        and state["charged"] <= money(binding["total_limit_usd"])
    )
    result = {
        "status": "settled" if settled else "blocked",
        "actual_usd": str(cost["actual"]) if cost["actual"] is not None else None,
        "charged_usd": str(cost["charged"]),
        "cost_resolved": cost["resolved"],
        "combined_f5_charged_usd": str(cost["charged"]),
        "original_run_id": binding["proposal"]["original_binding"]["run_id"],
        "recovery_run_id": binding["run_id"],
        "execution_terminal": execution_terminal,
        "cleanup_verified": cleanup_verified,
    }
    with registry(binding["project_root"]) as conn:
        cursor = conn.execute(
            f"UPDATE {TABLE} SET state=?,settlement=? WHERE run_id=? AND state='claimed'",
            (result["status"], json.dumps(result, sort_keys=True), binding["run_id"]),
        )
        require(cursor.rowcount == 1, "F5_RECOVERY_NOT_ACTIVE")
    return result
