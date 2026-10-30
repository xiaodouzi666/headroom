"""Independent fixed-nine revisions inside the original F3/F48 allocation.

Old once claims, original twelve-cell records and receipt/profile/ledger remain
unchanged. Existing feature tables make pending retry claims visible to demo and
other feature admission before a budget run is opened.
"""

import json
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from headroom.acceptance import final48_repair as repair
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
    request_sha256,
    require,
    verify_receipt,
)
from headroom.acceptance.snapshot_retry import _quiet_claims, _registered
from headroom.budget import BudgetLedger, current_utc_day, money
from headroom.orchestrator import FixRequest
from headroom.runtime import read_live_profile

SCHEMA = "headroom.final48.f3-retry.v1"
PROPOSAL = "headroom.final48.f3-retry-proposal.v1"
PREFIX = "F3-retry:"
CELL_IDS = tuple("fixed9-" + name for name in repair.SCENARIOS)


def _original(conn, parent, receipt):
    _checked_document(parent, "headroom.final48.f3-parent.v1")
    row = conn.execute(
        "SELECT * FROM f3_parents WHERE parent_id=?", (parent["parent_id"],)
    ).fetchone()
    claim = conn.execute(
        "SELECT * FROM claims WHERE task_scope='F3' AND execution_key='once'"
    ).fetchone()
    children = list(
        conn.execute(
            "SELECT * FROM f3_children WHERE parent_id=? ORDER BY cell_id", (parent["parent_id"],)
        )
    )
    require(
        row is not None
        and claim is not None
        and row["state"] == claim["state"] == "completed"
        and claim["run_id"] == parent["parent_id"]
        and json.loads(row["payload"]) == parent
        and len(children) == 12
        and all(child["state"] == "settled" for child in children),
        "F3_RETRY_ORIGINAL_NOT_SETTLED",
    )
    require(
        parent["receipt_sha256"] == receipt["receipt_sha256"]
        and parent["preparation_sha256"] == receipt["task_pins"]["F3"]["preparation_sha256"]
        and digest(parent["cell_requests"]) == receipt["task_pins"]["F3"]["cell_requests_sha256"],
        "F3_RETRY_ORIGINAL_CHANGED",
    )
    return {"parent": dict(row), "claim": dict(claim), "children": [dict(c) for c in children]}


def _proposal(
    conn,
    original,
    original_prepared_path,
    prepared_path,
    preparation_sha,
    receipt,
    revision,
    approval_ref,
    approval_sha,
):
    require(
        re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", revision or "") is not None,
        "F3_RETRY_REVISION_REQUIRED",
    )
    require(
        isinstance(approval_ref, str) and 0 < len(approval_ref) <= 256 and hash64(approval_sha),
        "F3_RETRY_AUTHORIZATION_REQUIRED",
    )
    root = Path(original["project_root"])
    profile = read_live_profile(receipt["profile_path"])
    require(
        profile.run_budget_mode == "strict_reservation"
        and profile.diagnosis_request_policy == repair.CONTROLS["request_policy"],
        "F3_RETRY_REQUEST_POLICY_CHANGED",
    )
    old = _original(conn, original, receipt)
    prepared_path = repair.inside(root, prepared_path)
    prepared = repair.verify_preparation(prepared_path, expected_sha256=preparation_sha)
    require(Path(prepared["project_root"]) == root, "F3_RETRY_ROOT_CHANGED")
    original_prepared_path = repair.inside(root, original_prepared_path)
    old_pack = repair.read_json(original_prepared_path, max_bytes=repair.MAX_BYTES)
    old_sha = old_pack.pop("preparation_sha256", None)
    require(
        old_sha == original["preparation_sha256"] == repair.digest(old_pack),
        "F3_RETRY_ORIGINAL_PREPARATION_CHANGED",
    )
    require(
        all(
            prepared[key] == old_pack[key]
            for key in (
                "controls",
                "cells",
                "input_pins",
                "source_files",
                "calibration",
                "repository_identities",
            )
        ),
        "F3_RETRY_ORIGINAL_INPUTS_CHANGED",
    )
    requests = repair.bound_requests(
        prepared,
        profile_path=receipt["profile_path"],
        daily_limit_usd=receipt["amounts"]["daily_limit_usd"],
    )
    cells = [c for c in prepared["cells"] if c["result_group"] == "fixed_nine"]
    require(tuple(c["cell_id"] for c in cells) == CELL_IDS, "F3_RETRY_FIXED_NINE_CHANGED")
    bound = {name: requests[name] for name in CELL_IDS}
    require(
        all(
            request_sha256(request) == original["cell_requests"].get(name)
            and money(request.budget_usd) == money(".60")
            for name, request in bound.items()
        ),
        "F3_RETRY_ORIGINAL_WORKLOAD_CHANGED",
    )
    cap = min(
        money("4"), money(original["scope_limit_usd"]), money(receipt["task_run_caps_usd"]["F3"])
    )
    require(cap > 0, "F3_RETRY_SCOPE_UNAUTHORIZED")
    return {
        "schema": PROPOSAL,
        "project_root": str(root),
        "receipt_path": original["receipt_path"],
        "receipt_sha256": receipt["receipt_sha256"],
        "original_parent": original,
        "original_registry": old,
        "original_prepared_path": str(original_prepared_path),
        "prepared_path": str(prepared_path),
        "preparation_sha256": preparation_sha,
        "revision": revision,
        "approval_ref": approval_ref,
        "approval_sha256": approval_sha,
        "cell_ids": list(CELL_IDS),
        "requests": {name: request.model_dump(mode="json") for name, request in bound.items()},
        "scope_cap_usd": str(cap),
        "daily_limit_usd": receipt["amounts"]["daily_limit_usd"],
        "planned_cells": 9,
        "fixed_denominator": 9,
        "minimum_targets": 6,
        "additional_funding": False,
    }


def prepare_f3_retry(
    original_parent,
    prepared_path,
    *,
    original_prepared_path,
    expected_preparation_sha256,
    revision,
    approval_ref,
    approval_sha256,
):
    """Read and pin current code plus identical original workloads; no claims or budget runs."""
    receipt = verify_receipt(
        original_parent["receipt_path"], project_root=original_parent["project_root"]
    )
    with registry(original_parent["project_root"]) as conn:
        return _proposal(
            conn,
            original_parent,
            original_prepared_path,
            prepared_path,
            expected_preparation_sha256,
            receipt,
            revision,
            approval_ref,
            approval_sha256,
        )


def _reviewed(conn, proposal, receipt, expected_sha256):
    require(
        proposal.get("schema") == PROPOSAL
        and hash64(expected_sha256)
        and digest(proposal) == expected_sha256,
        "F3_RETRY_REVIEW_CHANGED",
    )
    current = _proposal(
        conn,
        proposal["original_parent"],
        proposal["original_prepared_path"],
        proposal["prepared_path"],
        proposal["preparation_sha256"],
        receipt,
        proposal["revision"],
        proposal["approval_ref"],
        proposal["approval_sha256"],
    )
    require(current == proposal, "F3_RETRY_INPUT_OR_CODE_CHANGED")


def _scope_cost(conn, state, original_parent_id):
    ids = {
        row["run_id"]
        for row in conn.execute(
            "SELECT run_id FROM f3_children WHERE parent_id=?", (original_parent_id,)
        )
    }
    parents = set()
    for row in conn.execute(
        "SELECT parent_id,payload FROM feature_parents WHERE scope LIKE ?", (PREFIX + "%",)
    ):
        doc = json.loads(row["payload"])
        require(
            doc.get("schema") == SCHEMA and doc.get("original_parent_id") == original_parent_id,
            "F3_RETRY_HISTORY_INVALID",
        )
        parents.add(row["parent_id"])
    ids.update(
        row["run_id"]
        for row in conn.execute("SELECT run_id,parent_id FROM feature_children")
        if row["parent_id"] in parents
    )
    return _cost_summary(state, [a for a in state["attempts"] if a["run_id"] in ids])


def claim_f3_retry(proposal, *, cell_id, run_id, expected_sha256):
    """Admit one full .60 allowance, not a guarantee that all nine fit."""
    require(cell_id in CELL_IDS, "F3_RETRY_FIXED_NINE_ONLY")
    require(re.fullmatch(r"[a-f0-9]{32}", run_id or "") is not None, "F3_RETRY_RUN_INVALID")
    receipt = verify_receipt(proposal["receipt_path"], project_root=proposal["project_root"])
    with registry(proposal["project_root"]) as conn:
        _reviewed(conn, proposal, receipt, expected_sha256)
        _quiet_claims(conn)
        state = _budget_state(receipt)
        _quiet_pool(state)
        require(run_id not in state["runs"], "F3_RETRY_RUN_EXISTS")
        key = PREFIX + proposal["revision"] + ":" + cell_id
        require(
            conn.execute("SELECT 1 FROM feature_parents WHERE scope=?", (key,)).fetchone() is None,
            "F3_RETRY_CELL_ALREADY_CLAIMED",
        )
        cost = _scope_cost(conn, state, proposal["original_parent"]["parent_id"])
        require(cost["resolved"], "F3_RETRY_COST_UNRESOLVED")
        remaining = money(proposal["scope_cap_usd"]) - cost["charged"]
        ceiling = min(money(receipt["amounts"]["approved_net_usd"]), state["charged"] + remaining)
        require(state["charged"] + money(".60") <= ceiling, "F3_RETRY_SCOPE_OR_POOL_EXHAUSTED")
        binding = _signed(
            {
                "schema": SCHEMA,
                "project_root": proposal["project_root"],
                "receipt_path": proposal["receipt_path"],
                "receipt_sha256": receipt["receipt_sha256"],
                "original_parent_id": proposal["original_parent"]["parent_id"],
                "parent_id": uuid4().hex,
                "registry_scope": key,
                "run_id": run_id,
                "cell_id": cell_id,
                "proposal": proposal,
                "reviewed_proposal_sha256": expected_sha256,
                "queued_request_sha256": request_sha256(
                    FixRequest.model_validate(proposal["requests"][cell_id])
                ),
                "ledger_day": current_utc_day(),
                "run_limit_usd": "0.60",
                "daily_limit_usd": proposal["daily_limit_usd"],
                "total_limit_usd": str(ceiling),
                "scope_cap_usd": proposal["scope_cap_usd"],
            }
        )
        encoded = json.dumps(binding, sort_keys=True)
        try:
            conn.execute(
                "INSERT INTO claims VALUES(?,'once',?,?,NULL,'claimed')",
                (key, binding["parent_id"], expected_sha256),
            )
            conn.execute(
                "INSERT INTO feature_parents VALUES(?,?,?,'claimed')",
                (binding["parent_id"], key, encoded),
            )
            conn.execute(
                "INSERT INTO feature_children VALUES(?,?,?,?,'claimed',NULL)",
                (run_id, binding["parent_id"], cell_id, encoded),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("F3_RETRY_CELL_ALREADY_CLAIMED") from None
    return binding


def verify_f3_retry(binding, request, *, run_id, dispatch_attempt=None):
    _checked_document(binding, SCHEMA)
    require(run_id == binding["run_id"], "F3_RETRY_RUN_CHANGED")
    require(binding["ledger_day"] == current_utc_day(), "F3_RETRY_DAY_CHANGED")
    receipt = verify_receipt(binding["receipt_path"], project_root=binding["project_root"])
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "F3_RETRY_RECEIPT_CHANGED")
    require(
        request_sha256(request)
        == binding["queued_request_sha256"]
        == request_sha256(
            FixRequest.model_validate(binding["proposal"]["requests"][binding["cell_id"]])
        ),
        "F3_RETRY_REQUEST_CHANGED",
    )
    require(
        money(binding["run_limit_usd"]) == money(request.budget_usd) == money(".60")
        and money(binding["daily_limit_usd"])
        == money(request.daily_budget_usd)
        == money(receipt["amounts"]["daily_limit_usd"])
        and money(binding["total_limit_usd"]) <= money(receipt["amounts"]["approved_net_usd"]),
        "F3_RETRY_CAP_CHANGED",
    )
    with registry(binding["project_root"]) as conn:
        _registered(conn, binding)
        _reviewed(conn, binding["proposal"], receipt, binding["reviewed_proposal_sha256"])
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
                "F3_RETRY_DISPATCH_RESERVATION_CHANGED",
            )
            require(
                all(
                    not r["halt_reason"] and (k == run_id or r["status"] == "closed")
                    for k, r in state["runs"].items()
                ),
                "F3_RETRY_POOL_NOT_QUIET",
            )
        run = state["runs"].get(run_id)
        if run:
            require(
                run["status"] == "open"
                and run["budget_mode"] == "strict_reservation"
                and run["day"] == binding["ledger_day"]
                and money(run["limit_usd"]) == money(binding["run_limit_usd"]),
                "F3_RETRY_LEDGER_RUN_CHANGED",
            )
        cost = _scope_cost(conn, state, binding["original_parent_id"])
        require(
            cost["charged"] <= money(binding["scope_cap_usd"])
            and state["charged"] <= money(binding["total_limit_usd"]),
            "F3_RETRY_SCOPE_OR_POOL_EXHAUSTED",
        )
    return VerifiedChildBinding(
        receipt,
        run_id,
        binding["run_limit_usd"],
        binding["daily_limit_usd"],
        binding["total_limit_usd"],
    )


def f3_retry_budget_factory(binding, queued_request):
    """Use the normal runtime with the original database and reviewed whole profile."""

    def factory(run_id, request, profile):
        checked = verify_f3_retry(binding, queued_request, run_id=run_id)
        expected = read_live_profile(checked.receipt["profile_path"])
        require(
            profile.model_dump(mode="json") == expected.model_dump(mode="json"),
            "F3_RETRY_PROFILE_CHANGED",
        )
        require(
            str(request.runtime_profile) == checked.receipt["profile_path"]
            and money(request.budget_usd) == money(binding["run_limit_usd"])
            and money(request.daily_budget_usd) == money(binding["daily_limit_usd"])
            and profile.run_budget_mode == "strict_reservation",
            "F3_RETRY_RUNTIME_CHANGED",
        )

        class RetryLedger(BudgetLedger):
            def open_run(self, actual_run_id, limit_usd, *, budget_mode="strict_reservation"):
                require(
                    actual_run_id == run_id
                    and money(limit_usd) == money(binding["run_limit_usd"])
                    and budget_mode == "strict_reservation",
                    "F3_RETRY_LEDGER_RUN_CHANGED",
                )
                verify_f3_retry(binding, queued_request, run_id=run_id)
                return super().open_run(actual_run_id, limit_usd, budget_mode=budget_mode)

            def reserve(self, actual_run_id, *args, **kwargs):
                require(actual_run_id == run_id, "F3_RETRY_RUN_CHANGED")
                verify_f3_retry(binding, queued_request, run_id=run_id)
                return super().reserve(actual_run_id, *args, **kwargs)

            def mark_dispatched(self, actual_run_id, attempt_id):
                require(actual_run_id == run_id, "F3_RETRY_RUN_CHANGED")
                verify_f3_retry(binding, queued_request, run_id=run_id, dispatch_attempt=attempt_id)
                return super().mark_dispatched(actual_run_id, attempt_id)

        return RetryLedger(
            checked.database.path,
            require_existing=True,
            expected_identity=checked.database.file_identity,
            daily_limit=checked.daily_limit_usd,
            total_limit=checked.total_limit_usd,
        )

    return factory


def finish_f3_retry(binding, *, execution_terminal, cleanup_verified):
    """Retain uncertainty; only terminal execution and verified cleanup settle a claim."""
    _checked_document(binding, SCHEMA)
    receipt = verify_receipt(binding["receipt_path"], project_root=binding["project_root"])
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "F3_RETRY_RECEIPT_CHANGED")
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
        status = "completed" if settled else "blocked"
        conn.execute(
            "UPDATE feature_parents SET state=? WHERE parent_id=?", (status, binding["parent_id"])
        )
        conn.execute("UPDATE claims SET state=? WHERE run_id=?", (status, binding["parent_id"]))
    return result


def f3_retry_accounting(proposal):
    receipt = verify_receipt(proposal["receipt_path"], project_root=proposal["project_root"])
    with registry(proposal["project_root"]) as conn:
        _reviewed(conn, proposal, receipt, digest(proposal))
        state = _budget_state(receipt)
        cost = _scope_cost(conn, state, proposal["original_parent"]["parent_id"])
        return {
            "scope_cap_usd": proposal["scope_cap_usd"],
            "scope_charged_usd": str(cost["charged"]),
            "scope_actual_usd": str(cost["actual"]) if cost["actual"] is not None else None,
            "scope_remaining_usd": str(money(proposal["scope_cap_usd"]) - cost["charged"]),
            "pool_charged_usd": str(state["charged"]),
            "pool_remaining_usd": str(
                money(receipt["amounts"]["approved_net_usd"]) - state["charged"]
            ),
            "all_costs_resolved": cost["resolved"] and state["resolved"],
        }
