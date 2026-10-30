"""Reviewed snapshot retries inside the original F3b cap and FINAL48 ledger.

No original claim, receipt, profile or ledger identity is replaced. Retry claims
use the existing feature tables so ordinary demo/feature admission sees them.
"""

import json
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from headroom.acceptance.allocation import (
    AllocationRefused,
    VerifiedChildBinding,
    _budget_state,
    _checked_document,
    _cost_summary,
    _quiet_pool,
    _signed,
    digest,
    hash64,
    registry,
    require,
    safe,
    verify_receipt,
)
from headroom.acceptance.common import file_record
from headroom.acceptance.feature_allocation import (
    CHILD_SCHEMA,
    _check_intent,
    _quiet_registry,
)
from headroom.acceptance.snapshot_binding import snapshot_intent
from headroom.budget import BudgetLedger, current_utc_day, money
from headroom.runtime import read_live_profile

SCHEMA = "headroom.final48.snapshot-retry.v1"
PROPOSAL = "headroom.final48.snapshot-retry-proposal.v1"
PREFIX = "F3b-retry:"
CODE_FILES = (
    "headroom/snapshot_diagnosis.py",
    "headroom/api/snapshot_queue.py",
    "headroom/snapshot_evidence.py",
    "headroom/prompts/snapshot_diagnose.md",
    "headroom/acceptance/snapshot_retry.py",
    "headroom/evidence_blockers.py",
    "headroom/diagnose.py",
    "headroom/diagnosis_schema.py",
    "headroom/runtime.py",
    "headroom/llm/router.py",
    "headroom/llm/client.py",
    "headroom/budget.py",
    "headroom/patch.py",
    "headroom/patch_structure.py",
    "headroom/prompts/patch.md",
)


def _code(root):
    return {name: file_record(safe(root, root / name), 512 * 1024)["sha256"] for name in CODE_FILES}


def _original(conn, original):
    _checked_document(original, CHILD_SCHEMA)
    require(
        original["scope"] == "F3b"
        and original["slot_id"] in {"snapshot-s2", "snapshot-nanogpt", "snapshot-web"},
        "RETRY_SNAPSHOT_ONLY",
    )
    child = conn.execute(
        "SELECT * FROM feature_children WHERE run_id=?", (original["run_id"],)
    ).fetchone()
    parent = conn.execute(
        "SELECT * FROM feature_parents WHERE parent_id=?", (original["parent_id"],)
    ).fetchone()
    claim = conn.execute("SELECT * FROM claims WHERE run_id=?", (original["parent_id"],)).fetchone()
    require(
        child is not None and parent is not None and claim is not None, "RETRY_ORIGINAL_MISSING"
    )
    require(
        child["state"] == "settled"
        and parent["state"] == claim["state"] == "completed"
        and parent["scope"] == claim["task_scope"] == "F3b"
        and json.loads(child["payload"]) == original,
        "RETRY_ORIGINAL_NOT_SETTLED",
    )
    require(
        conn.execute(
            "SELECT 1 FROM feature_children WHERE parent_id=? AND state!='settled'",
            (original["parent_id"],),
        ).fetchone()
        is None,
        "RETRY_ORIGINAL_NOT_SETTLED",
    )
    return {"child": dict(child), "parent": dict(parent), "claim": dict(claim)}


def _quiet_claims(conn, allowed_run=None):
    _quiet_registry(conn, allowed_run=allowed_run)
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='f2_demo_runs'").fetchone():
        require(
            conn.execute("SELECT 1 FROM f2_demo_runs WHERE state!='settled' LIMIT 1").fetchone()
            is None,
            "RETRY_DEMO_UNSETTLED",
        )


def _scope_cost(conn, state, original_parent):
    parents = {original_parent}
    for row in conn.execute(
        "SELECT parent_id,payload FROM feature_parents WHERE scope LIKE ?", (PREFIX + "%",)
    ):
        doc = json.loads(row["payload"])
        require(
            doc.get("schema") == SCHEMA and doc.get("original_parent_id") == original_parent,
            "RETRY_SCOPE_HISTORY_INVALID",
        )
        parents.add(row["parent_id"])
    ids = {
        row["run_id"]
        for row in conn.execute("SELECT run_id,parent_id FROM feature_children")
        if row["parent_id"] in parents
    }
    return _cost_summary(state, [a for a in state["attempts"] if a["run_id"] in ids])


def _proposal(conn, original, request, receipt, *, revision, run_id, approval_ref, approval_sha256):
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", revision or "") is not None,
        "RETRY_REVISION_REQUIRED",
    )
    require(re.fullmatch(r"[0-9a-f]{32}", run_id or "") is not None, "RETRY_RUN_ID_INVALID")
    require(
        isinstance(approval_ref, str) and 0 < len(approval_ref) <= 256 and hash64(approval_sha256),
        "RETRY_AUTHORIZATION_REQUIRED",
    )
    old = _original(conn, original)
    parent = json.loads(old["parent"]["payload"])
    require(original["receipt_sha256"] == receipt["receipt_sha256"], "RETRY_RECEIPT_CHANGED")
    intent = snapshot_intent(request, daily_budget_usd=receipt["amounts"]["daily_limit_usd"])
    # Reuse identical inputs and original per-run allowance, never a used claim.
    intent_hash = _check_intent(receipt, parent, original["slot_id"], intent)
    require(intent_hash == original["intent_sha256"], "RETRY_INPUT_CHANGED")
    _quiet_claims(conn)
    state = _budget_state(receipt)
    _quiet_pool(state)
    require(run_id not in state["runs"], "RETRY_RUN_ALREADY_EXISTS")
    key = PREFIX + revision + ":" + original["slot_id"]
    require(
        conn.execute("SELECT 1 FROM feature_parents WHERE scope=?", (key,)).fetchone() is None,
        "RETRY_REVISION_ALREADY_CLAIMED",
    )
    cost = _scope_cost(conn, state, original["parent_id"])
    require(cost["resolved"], "RETRY_SCOPE_UNRESOLVED")
    cap = min(
        money("1"),
        money(parent["scope_limit_usd"]),
        money(receipt["feature_scope_caps_usd"]["F3b"]),
    )
    remaining = cap - cost["charged"]
    allowance = money(intent["budget_usd"])
    ceiling = min(money(receipt["amounts"]["approved_net_usd"]), state["charged"] + remaining)
    require(state["charged"] + allowance <= ceiling, "RETRY_SCOPE_OR_POOL_EXHAUSTED")
    return {
        "schema": PROPOSAL,
        "original": original,
        "original_registry": old,
        "project_root": original["project_root"],
        "receipt_path": original["receipt_path"],
        "receipt_sha256": receipt["receipt_sha256"],
        "revision": revision,
        "registry_scope": key,
        "run_id": run_id,
        "ledger_day": current_utc_day(),
        "approval_ref": approval_ref,
        "approval_sha256": approval_sha256,
        "intent": intent,
        "intent_sha256": intent_hash,
        "code_sha256": _code(Path(original["project_root"])),
        "pool_state_sha256": digest({"runs": state["runs"], "attempts": state["attempts"]}),
        "scope_cap_usd": str(cap),
        "scope_charged_usd": str(cost["charged"]),
        "run_limit_usd": str(allowance),
        "daily_limit_usd": intent["daily_budget_usd"],
        "total_limit_usd": str(ceiling),
    }


def prepare_snapshot_retry(original, request, *, revision, run_id, approval_ref, approval_sha256):
    receipt = verify_receipt(original["receipt_path"], project_root=original["project_root"])
    with registry(original["project_root"]) as conn:
        return _proposal(
            conn,
            original,
            request,
            receipt,
            revision=revision,
            run_id=run_id,
            approval_ref=approval_ref,
            approval_sha256=approval_sha256,
        )


def claim_snapshot_retry(proposal, request, *, expected_sha256):
    require(
        hash64(expected_sha256) and digest(proposal) == expected_sha256,
        "RETRY_REVIEW_HASH_MISMATCH",
    )
    require(proposal.get("schema") == PROPOSAL, "RETRY_PROPOSAL_INVALID")
    receipt = verify_receipt(proposal["receipt_path"], project_root=proposal["project_root"])
    with registry(proposal["project_root"]) as conn:
        current = _proposal(
            conn,
            proposal["original"],
            request,
            receipt,
            revision=proposal["revision"],
            run_id=proposal["run_id"],
            approval_ref=proposal["approval_ref"],
            approval_sha256=proposal["approval_sha256"],
        )
        require(current == proposal, "RETRY_REVIEW_STALE")
        binding = _signed(
            {
                **proposal,
                "schema": SCHEMA,
                "parent_id": uuid4().hex,
                "original_parent_id": proposal["original"]["parent_id"],
                "reviewed_proposal_sha256": expected_sha256,
            }
        )
        encoded = json.dumps(binding, sort_keys=True)
        try:
            conn.execute(
                "INSERT INTO claims VALUES(?,'once',?,?,NULL,'claimed')",
                (binding["registry_scope"], binding["parent_id"], expected_sha256),
            )
            conn.execute(
                "INSERT INTO feature_parents VALUES(?,?,?,'claimed')",
                (binding["parent_id"], binding["registry_scope"], encoded),
            )
            conn.execute(
                "INSERT INTO feature_children VALUES(?,?,?,?,'claimed',NULL)",
                (binding["run_id"], binding["parent_id"], binding["original"]["slot_id"], encoded),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("RETRY_ALREADY_CLAIMED") from None
    return binding


def _registered(conn, binding):
    for table, column, value in (
        ("feature_children", "run_id", binding["run_id"]),
        ("feature_parents", "parent_id", binding["parent_id"]),
    ):
        row = conn.execute(f"SELECT * FROM {table} WHERE {column}=?", (value,)).fetchone()
        require(
            row is not None and row["state"] == "claimed" and json.loads(row["payload"]) == binding,
            "RETRY_NOT_ACTIVE",
        )
    claim = conn.execute("SELECT * FROM claims WHERE run_id=?", (binding["parent_id"],)).fetchone()
    require(
        claim is not None
        and claim["state"] == "claimed"
        and claim["task_scope"] == binding["registry_scope"]
        and claim["preparation_sha"] == binding["reviewed_proposal_sha256"],
        "RETRY_NOT_ACTIVE",
    )


def verify_snapshot_retry(binding, request, *, run_id, dispatch_attempt=None):
    _checked_document(binding, SCHEMA)
    require(run_id == binding["run_id"], "RETRY_RUN_CHANGED")
    root = Path(binding["project_root"])
    proposal = {
        key: value
        for key, value in binding.items()
        if key
        not in {
            "schema",
            "binding_sha256",
            "parent_id",
            "original_parent_id",
            "reviewed_proposal_sha256",
        }
    }
    proposal["schema"] = PROPOSAL
    require(digest(proposal) == binding["reviewed_proposal_sha256"], "RETRY_REVIEW_CHANGED")
    require(binding["ledger_day"] == current_utc_day(), "RETRY_DAY_CHANGED")
    receipt = verify_receipt(binding["receipt_path"], project_root=root)
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "RETRY_RECEIPT_CHANGED")
    require(_code(root) == binding["code_sha256"], "RETRY_CODE_CHANGED")
    intent = snapshot_intent(request, daily_budget_usd=binding["daily_limit_usd"])
    require(intent == binding["intent"], "RETRY_INPUT_CHANGED")
    require(
        money(binding["run_limit_usd"]) == money(intent["budget_usd"])
        and 0
        < money(binding["run_limit_usd"])
        <= min(money("0.30"), money(receipt["task_run_caps_usd"]["F3b_snapshot"]))
        and money(binding["daily_limit_usd"]) == money(receipt["amounts"]["daily_limit_usd"])
        and money(binding["total_limit_usd"]) <= money(receipt["amounts"]["approved_net_usd"])
        and money(binding["scope_cap_usd"])
        <= min(money("1"), money(receipt["feature_scope_caps_usd"]["F3b"])),
        "RETRY_CAP_CHANGED",
    )
    with registry(root) as conn:
        _registered(conn, binding)
        require(
            _original(conn, binding["original"]) == binding["original_registry"],
            "RETRY_HISTORY_CHANGED",
        )
        _quiet_claims(conn, run_id)
        state = _budget_state(receipt)
        if dispatch_attempt is None:
            _quiet_pool(state, allowed_run=run_id)
        else:
            pending = [a for a in state["attempts"] if a["id"] not in state["resolved_attempt_ids"]]
            require(
                len(pending) == 1
                and pending[0]["id"] == dispatch_attempt
                and pending[0]["run_id"] == run_id
                and pending[0]["dispatched"] == 0
                and not pending[0]["settled"],
                "RETRY_DISPATCH_RESERVATION_CHANGED",
            )
            require(
                all(
                    not r["halt_reason"] and (k == run_id or r["status"] == "closed")
                    for k, r in state["runs"].items()
                ),
                "RETRY_POOL_NOT_QUIET",
            )
        run = state["runs"].get(run_id)
        if run:
            require(
                run["status"] == "open"
                and run["budget_mode"] == "strict_reservation"
                and run["day"] == binding["ledger_day"]
                and money(run["limit_usd"]) == money(binding["run_limit_usd"]),
                "RETRY_RUN_LIMIT_CHANGED",
            )
        cost = _scope_cost(conn, state, binding["original_parent_id"])
        require(
            cost["charged"] <= money(binding["scope_cap_usd"])
            and state["charged"] <= money(binding["total_limit_usd"]),
            "RETRY_SCOPE_OR_POOL_EXHAUSTED",
        )
    return VerifiedChildBinding(
        receipt,
        run_id,
        binding["run_limit_usd"],
        binding["daily_limit_usd"],
        binding["total_limit_usd"],
    )


def snapshot_retry_budget_factory(binding):
    def factory(run_id, request, profile):
        checked = verify_snapshot_retry(binding, request, run_id=run_id)
        expected_profile = read_live_profile(checked.receipt["profile_path"]).model_copy(
            update={"run_budget_mode": "strict_reservation"}
        )
        require(
            profile.model_dump(mode="json") == expected_profile.model_dump(mode="json"),
            "RETRY_PROFILE_CHANGED",
        )

        class RetryLedger(BudgetLedger):
            def open_run(self, actual_run_id, limit_usd, *, budget_mode="strict_reservation"):
                require(
                    actual_run_id == run_id
                    and money(limit_usd) == money(binding["run_limit_usd"])
                    and budget_mode == "strict_reservation",
                    "RETRY_RUN_LIMIT_CHANGED",
                )
                verify_snapshot_retry(binding, request, run_id=run_id)
                return super().open_run(actual_run_id, limit_usd, budget_mode=budget_mode)

            def reserve(self, actual_run_id, *args, **kwargs):
                require(actual_run_id == run_id, "RETRY_RUN_CHANGED")
                verify_snapshot_retry(binding, request, run_id=run_id)
                return super().reserve(actual_run_id, *args, **kwargs)

            def mark_dispatched(self, actual_run_id, attempt_id):
                require(actual_run_id == run_id, "RETRY_RUN_CHANGED")
                verify_snapshot_retry(binding, request, run_id=run_id, dispatch_attempt=attempt_id)
                return super().mark_dispatched(actual_run_id, attempt_id)

        return RetryLedger(
            checked.database.path,
            require_existing=True,
            expected_identity=checked.database.file_identity,
            daily_limit=checked.daily_limit_usd,
            total_limit=checked.total_limit_usd,
        )

    return factory


def finish_snapshot_retry(binding, *, execution_terminal, cleanup_verified):
    _checked_document(binding, SCHEMA)
    receipt = verify_receipt(binding["receipt_path"], project_root=binding["project_root"])
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "RETRY_RECEIPT_CHANGED")
    with registry(binding["project_root"]) as conn:
        _registered(conn, binding)
        state = _budget_state(receipt)
        own = _cost_summary(
            state, [a for a in state["attempts"] if a["run_id"] == binding["run_id"]]
        )
        group = _scope_cost(conn, state, binding["original_parent_id"])
        settled = (
            execution_terminal is True
            and cleanup_verified is True
            and own["resolved"]
            and state["resolved"]
            and all(
                r["status"] == "closed" and not r["halt_reason"] for r in state["runs"].values()
            )
            and own["charged"] <= money(binding["run_limit_usd"])
            and group["charged"] <= money(binding["scope_cap_usd"])
            and state["charged"] <= money(binding["total_limit_usd"])
        )
        result = {
            "status": "settled" if settled else "blocked",
            "actual_usd": str(own["actual"]) if own["actual"] is not None else None,
            "charged_usd": str(own["charged"]),
            "cost_resolved": own["resolved"],
            "scope_charged_usd": str(group["charged"]),
            "cost_basis": "exact"
            if own["known"]
            else "conservative_bound"
            if own["resolved"]
            else "unresolved",
        }
        conn.execute(
            "UPDATE feature_children SET state=?,settlement=? WHERE run_id=?",
            (result["status"], json.dumps(result, sort_keys=True), binding["run_id"]),
        )
        parent_status = "completed" if settled else "blocked"
        conn.execute(
            "UPDATE feature_parents SET state=? WHERE parent_id=?",
            (parent_status, binding["parent_id"]),
        )
        conn.execute(
            "UPDATE claims SET state=? WHERE run_id=?", (parent_status, binding["parent_id"])
        )
    return result
