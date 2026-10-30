"""Trusted FINAL48 public-demo binding; HTTP input never selects funding.

Metadata extends the existing allocation registry, not the budget database.
The ordinary live runtime retains open_run/close_run and provider settlement.
"""

import hashlib
import json
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

from headroom.acceptance.allocation import (
    AllocationRefused,
    _budget_state,
    _cost_summary,
    _quiet_pool,
    registry,
    request_sha256,
    require,
    verify_receipt,
)
from headroom.api.security import open_regular
from headroom.budget import BudgetLedger, money
from headroom.orchestrator import Services, run_fix

CAP = Decimal("0.30")
LEGACY_SCHEMA = "headroom.final48.demo-run.v1"
SCHEMA = "headroom.final48.demo-run.v2"


def _source_record(request):
    require(not request.repository_mode, "DEMO_REPOSITORY_FORBIDDEN")
    root = Path(request.source_root)
    script = Path(request.script)
    require(
        root.is_absolute()
        and root == root.resolve()
        and script == root / "train.py"
        and not root.is_symlink(),
        "DEMO_SOURCE_PATH_CHANGED",
    )
    with open_regular(root, "train.py", 1024 * 1024) as handle:
        content = handle.read()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


class DemoAllocation:
    """Server-owned per-run allowance inside the original shared allocation.

    An explicit scope_limit_usd retains the old v1 aggregate mode. Default v2
    claims leave legacy scope rows and all existing run payloads untouched.
    """

    def __init__(self, receipt_path, *, project_root, run_limit_usd="0.30", scope_limit_usd=None):
        self.root = Path(project_root).resolve()
        self.receipt_path = Path(receipt_path)
        self.legacy_scope = scope_limit_usd is not None
        require(
            not self.legacy_scope or money(run_limit_usd) == CAP,
            "DEMO_LIMIT_MODE_CONFLICT",
        )
        self.cap = money(scope_limit_usd if self.legacy_scope else run_limit_usd)
        require(0 < self.cap <= CAP, "DEMO_SCOPE_LIMIT_INVALID")
        self.receipt = self._receipt()
        with registry(self.root) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS f2_demo_scope("
                "allocation_id TEXT PRIMARY KEY, receipt_sha TEXT NOT NULL, cap TEXT NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS f2_demo_runs("
                "run_id TEXT PRIMARY KEY, allocation_id TEXT NOT NULL, payload TEXT NOT NULL,"
                "state TEXT NOT NULL, settlement TEXT)"
            )
            if self.legacy_scope:
                conn.execute(
                    "INSERT OR IGNORE INTO f2_demo_scope VALUES(?,?,?)",
                    (self.receipt["allocation_id"], self.receipt["receipt_sha256"], str(self.cap)),
                )
                row = conn.execute(
                    "SELECT receipt_sha,cap FROM f2_demo_scope WHERE allocation_id=?",
                    (self.receipt["allocation_id"],),
                ).fetchone()
                require(
                    tuple(row) == (self.receipt["receipt_sha256"], str(self.cap)),
                    "DEMO_SCOPE_CHANGED",
                )

    def _receipt(self):
        receipt = verify_receipt(self.receipt_path, project_root=self.root)
        cap = receipt["task_run_caps_usd"].get("F2_demo")
        require(
            "F2_demo" in receipt["task_scopes"] and cap is not None and self.cap <= money(cap),
            "DEMO_SCOPE_NOT_AUTHORIZED",
        )
        if hasattr(self, "receipt"):
            require(receipt == self.receipt, "DEMO_RECEIPT_CHANGED")
        return receipt

    def _remaining(self, conn, receipt, state, *, allowed_run=None):
        rows = list(
            conn.execute(
                "SELECT run_id,state FROM f2_demo_runs WHERE allocation_id=?",
                (receipt["allocation_id"],),
            )
        )
        require(
            all(r["state"] == "settled" or r["run_id"] == allowed_run for r in rows),
            "DEMO_PREVIOUS_RUN_UNSETTLED",
        )
        for table in ("feature_children", "f3_children"):
            require(
                conn.execute(f"SELECT 1 FROM {table} WHERE state!='settled' LIMIT 1").fetchone()
                is None,
                "DEMO_OTHER_RUN_UNSETTLED",
            )
        ids = {r["run_id"] for r in rows}
        own = [a for a in state["attempts"] if a["run_id"] in ids]
        cost = _cost_summary(state, own)
        require(cost["resolved"], "DEMO_COST_UNKNOWN")
        remaining = (
            money(receipt["amounts"]["approved_net_usd"])
            - state["charged"]
            - state.get("encumbered", money("0"))
        )
        if self.legacy_scope:
            spent = cost["charged"]
            require(spent <= self.cap, "DEMO_SCOPE_EXCEEDED")
            return min(self.cap - spent, remaining)
        return remaining

    @property
    def available(self):
        try:
            receipt = self._receipt()
            state = _budget_state(receipt)
            _quiet_pool(state)
            with registry(self.root) as conn:
                return self._remaining(conn, receipt, state) > 0
        except (OSError, ValueError, sqlite3.Error, ArithmeticError):
            return False

    def begin(self, run_id, request, *, source_sha256):
        """Bind a new run within its per-run cap and the remaining shared pool."""
        require(re.fullmatch(r"[a-f0-9]{32}", run_id) is not None, "DEMO_RUN_INVALID")
        receipt = self._receipt()
        require(
            request.runtime_profile == receipt["profile_path"]
            and money(request.daily_budget_usd) == money(receipt["amounts"]["daily_limit_usd"])
            and 0 < money(request.budget_usd) <= CAP,
            "DEMO_REQUEST_CONFIGURATION_CHANGED",
        )
        source = _source_record(request)
        require(source["sha256"] == source_sha256, "DEMO_UPLOAD_CHANGED")
        with registry(self.root) as conn:
            state = _budget_state(receipt)
            _quiet_pool(state)
            remaining = self._remaining(conn, receipt, state)
            limit = min(remaining, self.cap, money(request.budget_usd))
            require(limit > 0, "DEMO_SCOPE_EXHAUSTED")
            request = request.model_copy(update={"budget_usd": str(limit)})
            binding = {
                "schema": LEGACY_SCHEMA if self.legacy_scope else SCHEMA,
                "project_root": str(self.root),
                "receipt_path": str(self.receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
                "run_id": run_id,
                ("scope_limit_usd" if self.legacy_scope else "run_cap_usd"): str(self.cap),
                "run_limit_usd": str(limit),
                "daily_limit_usd": receipt["amounts"]["daily_limit_usd"],
                "total_limit_usd": receipt["amounts"]["approved_net_usd"],
                "request_sha256": request_sha256(request),
                "source": source,
            }
            try:
                conn.execute(
                    "INSERT INTO claims VALUES('F2_demo',?,?,?,NULL,'claimed')",
                    (run_id, run_id, binding["request_sha256"]),
                )
                conn.execute(
                    "INSERT INTO f2_demo_runs VALUES(?,?,?,'claimed',NULL)",
                    (run_id, receipt["allocation_id"], json.dumps(binding, sort_keys=True)),
                )
            except sqlite3.IntegrityError:
                raise AllocationRefused("DEMO_RUN_ALREADY_CLAIMED") from None
        return request, binding

    def finish(self, binding, *, execution_terminal, cleanup_verified):
        receipt = self._receipt()
        _validate_binding_limits(binding, receipt)
        with registry(self.root) as conn:
            row = conn.execute(
                "SELECT payload,state FROM f2_demo_runs WHERE run_id=?", (binding["run_id"],)
            ).fetchone()
            require(
                row and json.loads(row["payload"]) == binding and row["state"] == "claimed",
                "DEMO_CLAIM_CHANGED",
            )
            state = _budget_state(receipt)
            run = state["runs"].get(binding["run_id"])
            own = [a for a in state["attempts"] if a["run_id"] == binding["run_id"]]
            cost = _cost_summary(state, own)
            known, actual = cost["known"], cost["actual"]
            settled = (
                execution_terminal is True
                and cleanup_verified is True
                and cost["resolved"]
                and state["resolved"]
                and all(
                    r["status"] == "closed" and not r["halt_reason"] for r in state["runs"].values()
                )
                and (run is not None or not own)
                and cost["charged"] <= money(binding["run_limit_usd"])
                and state["charged"] <= money(binding["total_limit_usd"])
            )
            result = {
                "status": "settled" if settled else "blocked",
                "actual_usd": str(actual) if actual is not None else None,
                "charged_usd": str(cost["charged"]),
                "cost_resolved": cost["resolved"],
                "cost_basis": "exact"
                if known
                else "conservative_bound"
                if cost["resolved"]
                else "unresolved",
            }
            conn.execute(
                "UPDATE f2_demo_runs SET state=?,settlement=? WHERE run_id=?",
                (result["status"], json.dumps(result), binding["run_id"]),
            )
            conn.execute(
                "UPDATE claims SET state=? WHERE run_id=?", (result["status"], binding["run_id"])
            )
        if not settled:
            # Other task scopes also see the ordinary ledger stop, including a
            # worker killed before opening its budget. Never infer zero charge.
            ledger = _ledger(receipt, binding)
            if run is None:
                ledger.open_run(binding["run_id"], binding["run_limit_usd"])
            ledger.halt(binding["run_id"], "local_accounting_incomplete")
        return result


def _ledger(receipt, binding, cls=BudgetLedger):
    return cls(
        Path(receipt["ledger_path"]),
        require_existing=True,
        expected_identity=tuple(receipt["ledger_identity"]),
        daily_limit=binding["daily_limit_usd"],
        total_limit=binding["total_limit_usd"],
    )


def _validate_binding_limits(binding, receipt, request=None):
    schema = binding.get("schema")
    require(schema in (LEGACY_SCHEMA, SCHEMA), "DEMO_BINDING_INVALID")
    cap_field = "scope_limit_usd" if schema == LEGACY_SCHEMA else "run_cap_usd"
    require(cap_field in binding, "DEMO_BINDING_INVALID")
    cap = money(binding[cap_field])
    authorized_cap = receipt["task_run_caps_usd"].get("F2_demo")
    require(
        authorized_cap is not None
        and "F2_demo" in receipt["task_scopes"]
        and 0 < money(binding["run_limit_usd"]) <= cap <= min(CAP, money(authorized_cap))
        and money(binding["daily_limit_usd"]) == money(receipt["amounts"]["daily_limit_usd"])
        and money(binding["total_limit_usd"]) == money(receipt["amounts"]["approved_net_usd"])
        and binding["receipt_sha256"] == receipt["receipt_sha256"],
        "DEMO_BINDING_LIMIT_CHANGED",
    )
    if request is not None:
        require(
            money(request.budget_usd) == money(binding["run_limit_usd"])
            and money(request.daily_budget_usd) == money(binding["daily_limit_usd"])
            and request.runtime_profile == receipt["profile_path"],
            "DEMO_REQUEST_CONFIGURATION_CHANGED",
        )


def verify_demo_binding(binding, request, run_id):
    require(binding.get("schema") in (LEGACY_SCHEMA, SCHEMA), "DEMO_BINDING_INVALID")
    require(binding["run_id"] == run_id, "DEMO_RUN_CHANGED")
    receipt = verify_receipt(binding["receipt_path"], project_root=binding["project_root"])
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "DEMO_RECEIPT_CHANGED")
    _validate_binding_limits(binding, receipt, request)
    require(
        request_sha256(request) == binding["request_sha256"]
        and _source_record(request) == binding["source"],
        "DEMO_INPUT_CHANGED",
    )
    with registry(binding["project_root"]) as conn:
        row = conn.execute(
            "SELECT payload,state FROM f2_demo_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        claim = conn.execute("SELECT state FROM claims WHERE run_id=?", (run_id,)).fetchone()
        require(
            row
            and json.loads(row["payload"]) == binding
            and row["state"] == "claimed"
            and claim
            and claim["state"] == "claimed",
            "DEMO_CLAIM_NOT_ACTIVE",
        )
        if binding["schema"] == LEGACY_SCHEMA:
            scope = conn.execute(
                "SELECT cap,receipt_sha FROM f2_demo_scope WHERE allocation_id=?",
                (receipt["allocation_id"],),
            ).fetchone()
            require(
                scope and tuple(scope) == (binding["scope_limit_usd"], binding["receipt_sha256"]),
                "DEMO_SCOPE_CHANGED",
            )
    state = _budget_state(receipt)
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    require(
        run is None
        or (
            money(run["limit_usd"]) == money(binding["run_limit_usd"])
            and run["budget_mode"] == "strict_reservation"
        ),
        "DEMO_RUN_LIMIT_CHANGED",
    )
    return receipt


def demo_budget_factory(binding, original_request):
    class BoundLedger(BudgetLedger):
        def open_run(self, run_id, run_limit, *, budget_mode="strict_reservation"):
            require(
                run_id == binding["run_id"]
                and money(run_limit) == money(binding["run_limit_usd"])
                and budget_mode == "strict_reservation",
                "DEMO_RUN_LIMIT_CHANGED",
            )
            verify_demo_binding(binding, original_request, run_id)
            return super().open_run(run_id, run_limit, budget_mode=budget_mode)

        def reserve(self, run_id, *args, **kwargs):
            require(run_id == binding["run_id"], "DEMO_RUN_CHANGED")
            verify_demo_binding(binding, original_request, run_id)
            return super().reserve(run_id, *args, **kwargs)

    def factory(run_id, request, profile):
        receipt = verify_demo_binding(binding, request, run_id)
        require(
            profile.run_budget_mode == "strict_reservation"
            and money(profile.authorized_total_usd) == money(binding["total_limit_usd"]),
            "DEMO_PROFILE_LIMIT_CHANGED",
        )
        return _ledger(receipt, binding, BoundLedger)

    return factory


def run_bound_demo(request, *, store, run_root, run_id, binding, worker=None):
    """Normal live branch; an optional worker is only an injected offline test seam."""
    verify_demo_binding(binding, request, run_id)
    services = Services(budget_factory=demo_budget_factory(binding, request))
    return (worker or run_fix)(
        request, store=store, run_root=run_root, run_id=run_id, services=services
    )
