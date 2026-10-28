"""Explicit reviewed recovery of a bridge-only halt after verified bounded billing.

Preparation is read-only. Execution needs the exact proposal file SHA256 and an
independent terminal/cleanup evidence file. Neither operation changes costs,
attempt states, provider usage, the approval, or historical result artifacts.
"""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from headroom.acceptance.allocation import (
    LIMIT,
    _budget_state,
    _cost_summary,
    paths,
    registry,
    require,
    verify_receipt,
)
from headroom.acceptance.common import file_record, read_json
from headroom.budget import money
from headroom.ledger_path import require_initialized_ledger

SCHEMA = "headroom.final48.demo-bound-recovery.v1"


def _evidence(path, run_id):
    record = file_record(Path(path), LIMIT)
    evidence = read_json(Path(path), max_bytes=LIMIT)
    require(
        evidence.get("run_id") == run_id
        and evidence.get("execution_terminal") is True
        and evidence.get("cleanup_verified") is True
        and isinstance(evidence.get("reviewed_by"), str)
        and bool(evidence["reviewed_by"].strip())
        and isinstance(evidence.get("evidence"), str)
        and bool(evidence["evidence"].strip()),
        "DEMO_RECOVERY_EXECUTION_EVIDENCE_REQUIRED",
    )
    require(file_record(Path(path), LIMIT) == record, "DEMO_RECOVERY_EVIDENCE_CHANGED")
    return {"path": str(Path(path).resolve()), **record}, evidence


def _snapshot(state):
    return {
        "runs": sorted(state["runs"].values(), key=lambda r: r["id"]),
        "attempts": sorted(state["attempts"], key=lambda r: r["id"]),
    }


def _rows(conn, run_id):
    demo = conn.execute("SELECT * FROM f2_demo_runs WHERE run_id=?", (run_id,)).fetchone()
    claim = conn.execute("SELECT * FROM claims WHERE run_id=?", (run_id,)).fetchone()
    require(demo is not None and claim is not None, "DEMO_RECOVERY_CLAIM_MISSING")
    return {"demo": dict(demo), "claim": dict(claim)}


def _check(proposal, receipt, state, original):
    binding = json.loads(original["demo"]["payload"])
    run_id = proposal["run_id"]
    require(
        binding["run_id"] == run_id
        and binding["receipt_sha256"] == receipt["receipt_sha256"]
        and binding["project_root"] == proposal["project_root"]
        and original["demo"]["allocation_id"] == receipt["allocation_id"]
        and original["demo"]["state"] == original["claim"]["state"] == "blocked"
        and original["claim"]["task_scope"] == "F2_demo"
        and original["claim"]["preparation_sha"] == binding["request_sha256"],
        "DEMO_RECOVERY_CLAIM_CHANGED",
    )
    run = state["runs"].get(run_id)
    own = [row for row in state["attempts"] if row["run_id"] == run_id]
    cost = _cost_summary(state, own)
    require(
        run is not None
        and run["status"] == "closed"
        and run["halt_reason"] == "local_accounting_incomplete"
        and run["budget_mode"] == "strict_reservation"
        and bool(own)
        and cost["resolved"]
        and any(row["actual_usd"] is None for row in own)
        and all(
            row["actual_usd"] is not None
            or row["charge_status"] == "upper_bound"
            and row["charge_basis"] == "verified_tariff_missing_cache_count"
            for row in own
        )
        and state["resolved"]
        and all(
            row["status"] == "closed" and (row["id"] == run_id or row["halt_reason"] is None)
            for row in state["runs"].values()
        )
        and cost["charged"] <= money(binding["run_limit_usd"])
        and state["charged"] <= money(binding["total_limit_usd"]),
        "DEMO_RECOVERY_NOT_FINALIZED_BOUND_ONLY",
    )
    return binding, cost


def prepare_demo_recovery(receipt_path, *, project_root, run_id, execution_evidence_path):
    """Return a proposal, never mutate a ledger or unblock an allocation."""
    receipt = verify_receipt(receipt_path, project_root=project_root)
    evidence_record, evidence = _evidence(execution_evidence_path, run_id)
    root, _, registry_path = paths(project_root)
    with closing(sqlite3.connect(registry_path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        original = _rows(conn, run_id)
    state = _budget_state(receipt)
    proposal = {
        "schema": SCHEMA,
        "project_root": str(root),
        "receipt_path": str(Path(receipt_path).resolve()),
        "receipt_sha256": receipt["receipt_sha256"],
        "run_id": run_id,
        "execution_evidence": evidence_record,
        "reviewed_execution": evidence,
        "original_registry": original,
        "expected_ledger": _snapshot(state),
        "actual_charges_modified": False,
        "historical_result_reassessment": False,
    }
    _, cost = _check(proposal, receipt, state, original)
    return proposal | {"retained_charged_usd": str(cost["charged"]), "actual_usd": None}


def execute_demo_recovery(proposal_path, *, expected_sha256):
    """Apply one exact reviewed proposal; preserve the blocked decision in both DBs.

    Commit the ledger audit before clearing its halt, then finalize registry state.
    A crash between databases leaves the registry blocked; the same exact proposal
    can finish that second step without erasing or replaying the prior audit.
    """
    proposal_path = Path(proposal_path)
    record = file_record(proposal_path, LIMIT)
    require(record["sha256"] == expected_sha256, "DEMO_RECOVERY_PROPOSAL_CHANGED")
    proposal = read_json(proposal_path, max_bytes=LIMIT)
    require(file_record(proposal_path, LIMIT) == record, "DEMO_RECOVERY_PROPOSAL_CHANGED")
    require(proposal.get("schema") == SCHEMA, "DEMO_RECOVERY_SCHEMA_INVALID")
    evidence_record, evidence = _evidence(
        proposal["execution_evidence"]["path"], proposal["run_id"]
    )
    require(
        evidence_record == proposal["execution_evidence"]
        and evidence == proposal["reviewed_execution"],
        "DEMO_RECOVERY_EVIDENCE_CHANGED",
    )
    receipt = verify_receipt(proposal["receipt_path"], project_root=proposal["project_root"])
    require(receipt["receipt_sha256"] == proposal["receipt_sha256"], "DEMO_RECEIPT_CHANGED")
    ledger_path = require_initialized_ledger(
        receipt["ledger_path"], expected_identity=tuple(receipt["ledger_identity"])
    )
    run_id = proposal["run_id"]
    with registry(proposal["project_root"]) as conn:
        original = _rows(conn, run_id)
        require(original == proposal["original_registry"], "DEMO_RECOVERY_CLAIM_CHANGED")
        with closing(
            sqlite3.connect(Path(ledger_path).as_uri() + "?mode=rw", uri=True, isolation_level=None)
        ) as ledger:
            ledger.row_factory = sqlite3.Row
            ledger.execute("BEGIN IMMEDIATE")
            try:
                ledger.execute(
                    "CREATE TABLE IF NOT EXISTS budget_accounting_reviews("
                    "receipt_sha256 TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE,"
                    "reviewed_at TEXT NOT NULL,evidence_json TEXT NOT NULL)"
                )
                previous = ledger.execute(
                    "SELECT evidence_json FROM budget_accounting_reviews WHERE receipt_sha256=?",
                    (expected_sha256,),
                ).fetchone()
                state = _budget_state(receipt)
                if previous is not None:
                    require(json.loads(previous[0]) == proposal, "DEMO_RECOVERY_AUDIT_CHANGED")
                    require(
                        state["runs"][run_id]["halt_reason"] is None, "DEMO_RECOVERY_HALT_CHANGED"
                    )
                    state["runs"][run_id]["halt_reason"] = "local_accounting_incomplete"
                require(
                    _snapshot(state) == proposal["expected_ledger"], "DEMO_RECOVERY_LEDGER_CHANGED"
                )
                _binding, cost = _check(proposal, receipt, state, original)
                if previous is None:
                    ledger.execute(
                        "INSERT INTO budget_accounting_reviews VALUES(?,?,?,?)",
                        (
                            expected_sha256,
                            run_id,
                            datetime.now(UTC).isoformat(),
                            json.dumps(proposal, sort_keys=True),
                        ),
                    )
                    ledger.execute(
                        "UPDATE budget_runs SET halt_reason=NULL WHERE id=? "
                        "AND halt_reason='local_accounting_incomplete'",
                        (run_id,),
                    )
                ledger.commit()
            except BaseException:
                ledger.rollback()
                raise
        result = {
            "status": "settled",
            "actual_usd": None,
            "charged_usd": str(cost["charged"]),
            "cost_resolved": True,
            "cost_basis": "conservative_bound",
            "recovery_sha256": expected_sha256,
            "previous_state": original["demo"]["state"],
            "previous_settlement": json.loads(original["demo"]["settlement"]),
            "execution_terminal": True,
            "cleanup_verified": True,
        }
        conn.execute(
            "CREATE TABLE IF NOT EXISTS f2_demo_recoveries("
            "receipt_sha256 TEXT PRIMARY KEY,run_id TEXT NOT NULL UNIQUE,evidence_json TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO f2_demo_recoveries VALUES(?,?,?)",
            (expected_sha256, run_id, json.dumps(proposal, sort_keys=True)),
        )
        conn.execute(
            "UPDATE f2_demo_runs SET state='settled',settlement=? WHERE run_id=?",
            (json.dumps(result, sort_keys=True), run_id),
        )
        conn.execute("UPDATE claims SET state='settled' WHERE run_id=?", (run_id,))
    return result
