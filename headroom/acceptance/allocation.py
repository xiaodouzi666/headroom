"""Explicit FINAL48 allocation binding. Drafts never initialize a ledger/profile."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from headroom.acceptance.common import file_record, read_json, write_json
from headroom.budget import BudgetLedger, money
from headroom.ledger_path import (
    BUDGET_DB_ENV,
    BudgetDatabase,
    existing_file_identity,
    require_initialized_ledger,
    validate_existing_ledger_path,
)
from headroom.runtime import LiveProfile

SCOPES = ("F1", "F2_demo", "F3", "F3b_snapshot", "F3b_watch", "F5")
PLAN_SCHEMA = "headroom.final48.allocation-plan.v1"
RECEIPT_SCHEMA = "headroom.final48.allocation-receipt.v1"
AMOUNTS = (
    "approved_net_usd",
    "available_gift_usd",
    "review_reserve_usd",
    "tax_reserve_usd",
    "daily_limit_usd",
)
LIMIT = 512 * 1024


class AllocationRefused(ValueError):
    """Fixed refusal codes only; private amounts and paths are not error text."""


def require(condition, code):
    if not condition:
        raise AllocationRefused(code)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def hash64(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def prepare_allocation_plan():
    return {
        "schema": PLAN_SCHEMA,
        "state": "draft",
        "allocation_name": "FINAL48",
        "amounts": {name: None for name in AMOUNTS},
        "balance_evidence_sha256": None,
        "task_scopes": list(SCOPES),
        "task_run_caps_usd": {name: None for name in SCOPES},
        "feature_scope_caps_usd": {"F3b": None, "F5": None},
        "task_pins": {
            "F1": {"preparation_sha256": None, "scoring_policy_sha256": None},
            "F3": {"preparation_sha256": None, "cell_requests_sha256": None},
            "F3b": {"preparation_sha256": None, "slot_intents_sha256": None},
            "F5": {"preparation_sha256": None, "slot_intents_sha256": None},
        },
        "gift_only": True,
        "no_topup": True,
        "run_budget_mode": "strict_reservation",
        "admission_basis": "explicit_local_estimate_with_margin",
        "historical_unknown_policy": "preserve_read_only_history_not_a_new_pool_blocker",
    }


def paths(root):
    root = Path(root).resolve()
    directory = root / ".cache/final48-allocation"
    return root, directory, root / ".cache/final48-allocation-registry.sqlite3"


def safe(root, path):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve(), "NONCANONICAL_ALLOCATION_PATH")
    require(path.is_relative_to(root), "ALLOCATION_OUTSIDE_PROJECT")
    for part in (path, *path.parents):
        if part == root:
            break
        require(not part.is_symlink(), "LINKED_ALLOCATION_PATH")
    return path


@contextmanager
def registry(root, *, create=False):
    root, _, path = paths(root)
    safe(root, path)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
    require(path.exists() and stat.S_ISREG(path.lstat().st_mode), "ALLOCATION_REGISTRY_MISSING")
    validate_existing_ledger_path(path)
    conn = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        if create:
            conn.execute("""CREATE TABLE IF NOT EXISTS allocations(
                allocation_id TEXT PRIMARY KEY, name TEXT UNIQUE, approval_ref TEXT UNIQUE,
                approval_sha TEXT NOT NULL, receipt_sha TEXT NOT NULL, state TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS claims(
                task_scope TEXT NOT NULL, execution_key TEXT NOT NULL, run_id TEXT UNIQUE NOT NULL,
                preparation_sha TEXT, scoring_sha TEXT, state TEXT NOT NULL,
                PRIMARY KEY(task_scope,execution_key))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS f3_parents(
                parent_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS f3_children(
                run_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, cell_id TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL, settlement TEXT,
                UNIQUE(parent_id,cell_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS feature_parents(
                parent_id TEXT PRIMARY KEY, scope TEXT UNIQUE NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS feature_children(
                run_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, slot_id TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL, settlement TEXT,
                UNIQUE(parent_id,slot_id))""")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def historical_snapshot(root):
    """Logical SQLite read snapshot, including WAL; never instantiate old BudgetLedger."""
    path = root / ".cache/budget.db"
    require(path.exists(), "HISTORICAL_LEDGER_REQUIRED")
    validate_existing_ledger_path(path)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        data = {}
        for table in ("budget_runs", "budget_attempts", "budget_retention_reviews"):
            if conn.execute(
                "SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)
            ).fetchone():
                columns = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
                data[table] = sorted(
                    [
                        dict(zip(columns, row, strict=True))
                        for row in conn.execute(f"SELECT * FROM {table}")
                    ],
                    key=lambda row: json.dumps(row, sort_keys=True),
                )
        unknown = sum(row.get("actual_usd") is None for row in data.get("budget_attempts", []))
    return {
        "logical_sha256": digest(data),
        "unknown_attempts": unknown,
        "policy": "preserved_not_deducted_or_used_as_new_pool_blocker",
    }


def activate_allocation(plan, authorization, profile_document, *, project_root):
    """Only explicit human amount authorization may activate; this sends no requests."""
    root, directory, _ = paths(project_root)
    safe(root, directory)
    require(
        plan.get("schema") == PLAN_SCHEMA and plan.get("state") == "draft",
        "ALLOCATION_PLAN_REQUIRED",
    )
    require(plan.get("task_scopes") == list(SCOPES), "FINAL48_SHARED_SCOPES_REQUIRED")
    require(
        plan.get("run_budget_mode") == "strict_reservation"
        and plan.get("admission_basis") == "explicit_local_estimate_with_margin",
        "ALLOCATION_PROTOCOL_CHANGED",
    )
    require(plan.get("gift_only") is True and plan.get("no_topup") is True, "GIFT_ONLY_REQUIRED")
    require(
        authorization.get("state") == "authorized" and authorization.get("scope") == "FINAL48",
        "AMOUNT_AUTHORIZATION_REQUIRED",
    )
    require(
        isinstance(authorization.get("approval_message_ref"), str)
        and 0 < len(authorization["approval_message_ref"]) <= 512
        and hash64(authorization.get("statement_sha256")),
        "HUMAN_AUTHORIZATION_REFERENCE_REQUIRED",
    )
    require(
        all(isinstance(plan.get("amounts", {}).get(k), str) for k in AMOUNTS),
        "UNFILLED_AMOUNT_TEMPLATE",
    )
    amounts = {k: money(plan["amounts"][k]) for k in AMOUNTS}
    approved = amounts["approved_net_usd"]
    require(
        approved > 0 and money(authorization.get("approved_net_usd")) == approved,
        "APPROVED_AMOUNT_MISMATCH",
    )
    require(
        all(v >= 0 for v in amounts.values()) and 0 < amounts["daily_limit_usd"] <= approved,
        "INVALID_ALLOCATION_LIMITS",
    )
    require(
        approved
        <= amounts["available_gift_usd"]
        - amounts["review_reserve_usd"]
        - amounts["tax_reserve_usd"],
        "GIFT_RESERVE_EXCEEDED",
    )
    require(hash64(plan.get("balance_evidence_sha256")), "BALANCE_EVIDENCE_REQUIRED")
    caps = plan.get("task_run_caps_usd", {})
    require(
        set(caps) == set(SCOPES)
        and all(
            v is None or isinstance(v, str) and 0 < money(v) <= approved for v in caps.values()
        ),
        "TASK_CAPS_INVALID",
    )
    require(caps["F1"] is not None and money(caps["F1"]) <= Decimal("1.50"), "F1_CAP_EXCEEDED")
    pins = plan.get("task_pins", {}).get("F1", {})
    require(
        hash64(pins.get("preparation_sha256")) and hash64(pins.get("scoring_policy_sha256")),
        "F1_REVIEWED_INPUT_REQUIRED",
    )
    if caps["F3"] is not None:
        f3_pins = plan.get("task_pins", {}).get("F3", {})
        require(
            money(caps["F3"]) <= Decimal(4)
            and hash64(f3_pins.get("preparation_sha256"))
            and hash64(f3_pins.get("cell_requests_sha256")),
            "F3_REVIEWED_INPUT_REQUIRED",
        )
    from headroom.acceptance.feature_allocation import validate_feature_plan

    feature_caps = validate_feature_plan(plan, approved=approved)
    profile = LiveProfile.model_validate(profile_document)
    profile.runtime_config()
    require(
        profile.run_budget_mode == "strict_reservation"
        and money(profile.authorized_total_usd) == approved
        and money(profile.available_credit_usd) == amounts["available_gift_usd"],
        "PROFILE_ALLOCATION_MISMATCH",
    )
    require(not directory.exists(), "FINAL48_ALLOCATION_ALREADY_EXISTS")
    history = historical_snapshot(root)
    approval_sha = digest(authorization)
    allocation_id = uuid4().hex
    with registry(root, create=True) as conn:
        require(
            conn.execute(
                "SELECT 1 FROM allocations WHERE name='FINAL48' OR approval_ref=?",
                (authorization["approval_message_ref"],),
            ).fetchone()
            is None,
            "ALLOCATION_ALREADY_ACTIVATED",
        )
        directory.mkdir(mode=0o700, exist_ok=False)
        profile_path = directory / "runtime-profile.json"
        write_json(profile_path, profile_document)
        profile_sha = file_record(profile_path, LIMIT)["sha256"]
        ledger_path = directory / "budget.db"
        fd = os.open(ledger_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        BudgetLedger(
            ledger_path, total_limit=str(approved), daily_limit=str(amounts["daily_limit_usd"])
        )
        identity = existing_file_identity(ledger_path)
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "state": "active",
            "allocation_id": allocation_id,
            "allocation_name": "FINAL48",
            "project_root": str(root),
            "plan_sha256": digest(plan),
            "authorization": authorization,
            "authorization_sha256": approval_sha,
            "amounts": plan["amounts"],
            "balance_evidence_sha256": plan["balance_evidence_sha256"],
            "ledger_path": str(ledger_path),
            "ledger_identity": list(identity),
            "profile_path": str(profile_path),
            "profile_sha256": profile_sha,
            "task_scopes": list(SCOPES),
            "task_run_caps_usd": caps,
            "feature_scope_caps_usd": feature_caps,
            "task_pins": plan["task_pins"],
            "run_budget_mode": "strict_reservation",
            "gift_only": True,
            "no_topup": True,
            "admission_basis": plan["admission_basis"],
            "historical_ledger": history,
        }
        receipt["receipt_sha256"] = digest(receipt)
        with sqlite3.connect(ledger_path) as budget:
            budget.execute("""CREATE TABLE allocation_identity(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), allocation_id TEXT NOT NULL,
                receipt_sha TEXT NOT NULL, profile_sha TEXT NOT NULL, total_limit_usd TEXT NOT NULL,
                daily_limit_usd TEXT NOT NULL)""")
            budget.execute(
                "INSERT INTO allocation_identity VALUES(1,?,?,?,?,?)",
                (
                    allocation_id,
                    receipt["receipt_sha256"],
                    profile_sha,
                    str(approved),
                    str(amounts["daily_limit_usd"]),
                ),
            )
        write_json(directory / "receipt.json", receipt)
        conn.execute(
            "INSERT INTO allocations VALUES(?,?,?,?,?,?)",
            (
                allocation_id,
                "FINAL48",
                authorization["approval_message_ref"],
                approval_sha,
                receipt["receipt_sha256"],
                "active",
            ),
        )
    return receipt


def verify_receipt(receipt_path, *, project_root, environ=None):
    root, directory, _ = paths(project_root)
    path = safe(root, Path(receipt_path))
    require(path == directory / "receipt.json", "CANONICAL_RECEIPT_REQUIRED")
    receipt = read_json(path, max_bytes=LIMIT)
    claimed = receipt.get("receipt_sha256")
    require(
        claimed == digest({k: v for k, v in receipt.items() if k != "receipt_sha256"}),
        "ALLOCATION_RECEIPT_CHANGED",
    )
    require(
        receipt.get("schema") == RECEIPT_SCHEMA
        and receipt.get("state") == "active"
        and receipt.get("project_root") == str(root),
        "ACTIVE_ALLOCATION_REQUIRED",
    )
    ledger = safe(root, Path(receipt["ledger_path"]))
    profile = safe(root, Path(receipt["profile_path"]))
    require(
        ledger == directory / "budget.db" and profile == directory / "runtime-profile.json",
        "ALLOCATION_PATH_MISMATCH",
    )
    identity = tuple(receipt["ledger_identity"])
    require_initialized_ledger(ledger, expected_identity=identity)
    env = os.environ if environ is None else environ
    require(
        BUDGET_DB_ENV not in env or env[BUDGET_DB_ENV] == str(ledger), "ENVIRONMENT_LEDGER_CONFLICT"
    )
    require(
        file_record(profile, LIMIT)["sha256"] == receipt["profile_sha256"],
        "ALLOCATION_PROFILE_CHANGED",
    )
    with registry(root) as conn:
        row = conn.execute(
            "SELECT * FROM allocations WHERE allocation_id=?", (receipt["allocation_id"],)
        ).fetchone()
        require(
            row is not None
            and row["state"] == "active"
            and row["receipt_sha"] == claimed
            and row["approval_sha"] == receipt["authorization_sha256"],
            "UNREGISTERED_ALLOCATION",
        )
    with sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT allocation_id,receipt_sha,profile_sha,total_limit_usd,daily_limit_usd FROM allocation_identity WHERE singleton=1"
        ).fetchone()
        require(
            row
            == (
                receipt["allocation_id"],
                claimed,
                receipt["profile_sha256"],
                str(money(receipt["amounts"]["approved_net_usd"])),
                str(money(receipt["amounts"]["daily_limit_usd"])),
            ),
            "ALLOCATION_DB_IDENTITY_CHANGED",
        )
    return receipt


@dataclass(frozen=True)
class AllocationBinding:
    receipt_path: Path
    project_root: Path
    receipt: dict
    run_id: str

    @property
    def database(self):
        return BudgetDatabase(
            Path(self.receipt["ledger_path"]), True, tuple(self.receipt["ledger_identity"])
        )

    def revalidate(self):
        current = verify_receipt(self.receipt_path, project_root=self.project_root)
        require(current == self.receipt, "ALLOCATION_BINDING_CHANGED")
        with registry(self.project_root) as conn:
            row = conn.execute("SELECT state FROM claims WHERE run_id=?", (self.run_id,)).fetchone()
            require(row is not None and row["state"] == "claimed", "ALLOCATION_CLAIM_NOT_ACTIVE")


def verify_and_claim_allocation(
    receipt_path,
    *,
    project_root,
    task_scope,
    execution_key,
    profile_path,
    run_limit_usd,
    daily_limit_usd,
    preparation_sha256=None,
    scoring_policy_sha256=None,
):
    require(task_scope != "F3", "F3_PARENT_CHILD_BINDING_REQUIRED")
    require(
        task_scope not in {"F3b_snapshot", "F3b_watch", "F5"},
        "FEATURE_PARENT_CHILD_BINDING_REQUIRED",
    )
    receipt = verify_receipt(receipt_path, project_root=project_root)
    require(
        task_scope in SCOPES and task_scope in receipt["task_scopes"], "TASK_SCOPE_NOT_AUTHORIZED"
    )
    cap = receipt["task_run_caps_usd"].get(task_scope)
    require(
        cap is not None
        and 0 < money(run_limit_usd) <= money(cap)
        and 0 < money(daily_limit_usd) <= money(receipt["amounts"]["daily_limit_usd"]),
        "TASK_LIMIT_EXCEEDED",
    )
    require(str(Path(profile_path).resolve()) == receipt["profile_path"], "TASK_PROFILE_MISMATCH")
    if task_scope == "F1":
        pins = receipt["task_pins"]["F1"]
        require(
            preparation_sha256 == pins["preparation_sha256"]
            and scoring_policy_sha256 == pins["scoring_policy_sha256"],
            "F1_INPUT_BINDING_CHANGED",
        )
        execution_key = "once"
    require(
        isinstance(execution_key, str) and 0 < len(execution_key) <= 256, "EXECUTION_KEY_REQUIRED"
    )
    run_id = uuid4().hex
    with registry(project_root) as conn:
        try:
            conn.execute(
                "INSERT INTO claims VALUES(?,?,?,?,?,?)",
                (
                    task_scope,
                    execution_key,
                    run_id,
                    preparation_sha256,
                    scoring_policy_sha256,
                    "claimed",
                ),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("ALLOCATION_EXECUTION_ALREADY_CLAIMED") from None
    return AllocationBinding(Path(receipt_path), Path(project_root).resolve(), receipt, run_id)


def finish_claim(binding, *, status):
    with registry(binding.project_root) as conn:
        conn.execute("UPDATE claims SET state=? WHERE run_id=?", (status, binding.run_id))


# F3 uses one immutable parent ceiling and ordinary child run IDs in the same ledger.
# This is an estimate-backed admission limit, not a guarantee about provider billing.
def request_sha256(request):
    return digest(_request_document(request))


def _request_document(request):
    # The queue historically persists mode="python"; validate both forms through the
    # same schema before hashing, so 25 vs 25.0 cannot change a legitimate binding.
    from headroom.orchestrator import FixRequest

    document = request.model_dump(mode="json") if hasattr(request, "model_dump") else request
    require(isinstance(document, dict), "F3_REQUEST_REQUIRED")
    try:
        return FixRequest.model_validate(document).model_dump(mode="json")
    except ValueError:
        raise AllocationRefused("F3_REQUEST_REQUIRED") from None


def _signed(document):
    return document | {"binding_sha256": digest(document)}


def _checked_document(document, schema):
    require(isinstance(document, dict) and document.get("schema") == schema, "F3_BINDING_INVALID")
    require(
        document.get("binding_sha256")
        == digest({key: value for key, value in document.items() if key != "binding_sha256"}),
        "F3_BINDING_CHANGED",
    )


def _attempt_resolved(row, reviewed=()):
    """A finalized tariff bound is safe to reserve against, never an exact charge."""
    if not row["settled"]:
        return False
    if row["actual_usd"] is not None:
        return money(row["actual_usd"]) == money(row["charged_usd"])
    if (
        row["dispatched"] != 1
        or row["admission_kind"] != "verified_provider_bound"
        or not 0 <= money(row["charged_usd"]) <= money(row["upper_usd"])
    ):
        return False
    if row.get("charge_status") == "upper_bound":
        return row.get("charge_basis") == "verified_tariff_missing_cache_count"
    return (
        row.get("charge_status") == "reviewed_retained"
        and row.get("charge_basis") == "manual_full_reservation_retained"
        and money(row["charged_usd"]) == money(row["upper_usd"])
        and (row.get("review_sha256"), row["id"], row["run_id"]) in reviewed
    )


def _cost_summary(state, attempts):
    """Keep exact actuals distinct from the conservative amount charged to caps."""
    known = all(row["settled"] and row["actual_usd"] is not None for row in attempts)
    return {
        "known": known,
        "resolved": all(row["id"] in state["resolved_attempt_ids"] for row in attempts),
        "actual": sum((money(row["actual_usd"]) for row in attempts), Decimal(0))
        if known
        else None,
        "charged": sum((money(row["charged_usd"]) for row in attempts), Decimal(0)),
    }


def _budget_state(receipt):
    """Read only the new pool; old historical unknown charges are deliberately excluded."""
    path = Path(receipt["ledger_path"])
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        runs = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM budget_runs")}
        attempts = [dict(row) for row in conn.execute("SELECT * FROM budget_attempts")]
        reviewed = {
            tuple(row)
            for row in conn.execute(
                "SELECT receipt_sha256,attempt_id,run_id FROM budget_retention_reviews"
            )
        }
    known = all(row["settled"] and row["actual_usd"] is not None for row in attempts)
    resolved_ids = {row["id"] for row in attempts if _attempt_resolved(row, reviewed)}
    total = sum((money(row["charged_usd"]) for row in attempts), Decimal(0))
    return {
        "runs": runs,
        "attempts": attempts,
        "known": known,
        "charged": total,
        "resolved": len(resolved_ids) == len(attempts),
        "resolved_attempt_ids": resolved_ids,
    }


def _quiet_pool(state, *, allowed_run=None):
    require(state["resolved"], "F3_NEW_POOL_UNSETTLED")
    require(
        all(not row["halt_reason"] for row in state["runs"].values()),
        "F3_NEW_POOL_HALTED",
    )
    require(
        all(key == allowed_run or row["status"] == "closed" for key, row in state["runs"].items()),
        "F3_NEW_POOL_RUN_ACTIVE",
    )


def _parent_record(parent, *, active=True, environ=None):
    _checked_document(parent, "headroom.final48.f3-parent.v1")
    receipt = verify_receipt(
        parent["receipt_path"], project_root=parent["project_root"], environ=environ
    )
    require(receipt["receipt_sha256"] == parent["receipt_sha256"], "F3_RECEIPT_CHANGED")
    with registry(parent["project_root"]) as conn:
        row = conn.execute(
            "SELECT * FROM f3_parents WHERE parent_id=?", (parent["parent_id"],)
        ).fetchone()
        claim = conn.execute(
            "SELECT * FROM claims WHERE task_scope='F3' AND execution_key='once'"
        ).fetchone()
        require(
            row is not None
            and json.loads(row["payload"]) == parent
            and claim is not None
            and claim["run_id"] == parent["parent_id"],
            "F3_PARENT_NOT_REGISTERED",
        )
        if active:
            require(
                row["state"] == "claimed" and claim["state"] == "claimed", "F3_PARENT_NOT_ACTIVE"
            )
    return receipt


def claim_f3_parent(
    receipt_path, *, project_root, preparation_sha256, cell_requests, scope_limit_usd="4"
):
    """Claim the fixed 12-cell campaign exactly once; no model calls or budget run created."""
    receipt = verify_receipt(receipt_path, project_root=project_root)
    cap = receipt["task_run_caps_usd"].get("F3")
    pins = receipt.get("task_pins", {}).get("F3", {})
    require(
        cap is not None and 0 < money(scope_limit_usd) <= min(money(cap), Decimal(4)),
        "F3_SCOPE_LIMIT_EXCEEDED",
    )
    require(
        isinstance(cell_requests, dict)
        and len(cell_requests) == 12
        and all(
            isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key) and hash64(value)
            for key, value in cell_requests.items()
        ),
        "F3_TWELVE_CELL_INPUTS_REQUIRED",
    )
    require(
        hash64(preparation_sha256)
        and preparation_sha256 == pins.get("preparation_sha256")
        and digest(cell_requests) == pins.get("cell_requests_sha256"),
        "F3_INPUT_BINDING_CHANGED",
    )
    with registry(project_root) as conn:
        state = _budget_state(receipt)
        _quiet_pool(state)
        ceiling = min(
            money(receipt["amounts"]["approved_net_usd"]),
            state["charged"] + money(scope_limit_usd),
        )
        require(ceiling > state["charged"], "F3_SCOPE_EXHAUSTED")
        parent_id = uuid4().hex
        parent = _signed(
            {
                "schema": "headroom.final48.f3-parent.v1",
                "parent_id": parent_id,
                "project_root": str(Path(project_root).resolve()),
                "receipt_path": str(Path(receipt_path)),
                "receipt_sha256": receipt["receipt_sha256"],
                "allocation_id": receipt["allocation_id"],
                "profile_path": receipt["profile_path"],
                "daily_limit_usd": receipt["amounts"]["daily_limit_usd"],
                "preparation_sha256": preparation_sha256,
                "cell_requests": dict(cell_requests),
                "cell_requests_sha256": digest(cell_requests),
                "scope_limit_usd": str(money(scope_limit_usd)),
                "prior_charged_usd": str(state["charged"]),
                "total_limit_usd": str(ceiling),
            }
        )
        try:
            conn.execute(
                "INSERT INTO claims VALUES('F3','once',?,?,NULL,'claimed')",
                (parent_id, preparation_sha256),
            )
            conn.execute(
                "INSERT INTO f3_parents VALUES(?,?,'claimed')",
                (parent_id, json.dumps(parent, sort_keys=True)),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("ALLOCATION_EXECUTION_ALREADY_CLAIMED") from None
    return parent


def claim_f3_child(parent, *, cell_id, request, run_id):
    """Serialize child admission. The queued request, including profile/path, is pinned."""
    receipt = _parent_record(parent)
    document = _request_document(request)
    request_hash = request_sha256(request)
    require(
        parent["cell_requests"].get(cell_id) == request_hash,
        "F3_CHILD_REQUEST_CHANGED",
    )
    require(
        isinstance(run_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", run_id),
        "F3_CHILD_RUN_ID_INVALID",
    )
    require(
        str(document.get("runtime_profile")) == receipt["profile_path"],
        "F3_CHILD_PROFILE_CHANGED",
    )
    requested_cap = money(document.get("budget_usd"))
    require(0 < requested_cap <= Decimal("0.60"), "F3_CHILD_CAP_EXCEEDED")
    daily = money(document.get("daily_budget_usd"))
    require(
        0 < daily <= money(receipt["amounts"]["daily_limit_usd"]),
        "F3_CHILD_DAILY_LIMIT_EXCEEDED",
    )
    with registry(parent["project_root"]) as conn:
        current = conn.execute(
            "SELECT state FROM f3_parents WHERE parent_id=?", (parent["parent_id"],)
        ).fetchone()
        require(current and current["state"] == "claimed", "F3_PARENT_NOT_ACTIVE")
        require(
            conn.execute(
                "SELECT 1 FROM f3_children WHERE parent_id=? AND state!='settled'",
                (parent["parent_id"],),
            ).fetchone()
            is None,
            "F3_PREVIOUS_CHILD_UNSETTLED",
        )
        state = _budget_state(receipt)
        _quiet_pool(state)
        require(run_id not in state["runs"], "F3_CHILD_RUN_ALREADY_EXISTS")
        remaining = money(parent["total_limit_usd"]) - state["charged"]
        require(remaining >= requested_cap, "F3_SCOPE_EXHAUSTED")
        binding = _signed(
            {
                "schema": "headroom.final48.f3-child.v1",
                "parent_id": parent["parent_id"],
                "parent_binding_sha256": parent["binding_sha256"],
                "preparation_sha256": parent["preparation_sha256"],
                "cell_id": cell_id,
                "run_id": run_id,
                "queued_request_sha256": request_hash,
                "project_root": parent["project_root"],
                "receipt_path": parent["receipt_path"],
                "receipt_sha256": parent["receipt_sha256"],
                "run_limit_usd": str(requested_cap),
                "daily_limit_usd": str(daily),
                "total_limit_usd": parent["total_limit_usd"],
            }
        )
        try:
            conn.execute(
                "INSERT INTO f3_children VALUES(?,?,?,?,'claimed',NULL)",
                (run_id, parent["parent_id"], cell_id, json.dumps(binding, sort_keys=True)),
            )
        except sqlite3.IntegrityError:
            raise AllocationRefused("F3_CHILD_ALREADY_CLAIMED") from None
    return binding


@dataclass(frozen=True)
class VerifiedChildBinding:
    receipt: dict
    run_id: str
    run_limit_usd: str
    daily_limit_usd: str
    total_limit_usd: str

    @property
    def database(self):
        return BudgetDatabase(
            Path(self.receipt["ledger_path"]), True, tuple(self.receipt["ledger_identity"])
        )


def _child_record(binding, *, active=True, environ=None):
    _checked_document(binding, "headroom.final48.f3-child.v1")
    receipt = verify_receipt(
        binding["receipt_path"], project_root=binding["project_root"], environ=environ
    )
    require(receipt["receipt_sha256"] == binding["receipt_sha256"], "F3_RECEIPT_CHANGED")
    with registry(binding["project_root"]) as conn:
        child = conn.execute(
            "SELECT * FROM f3_children WHERE run_id=?", (binding["run_id"],)
        ).fetchone()
        parent = conn.execute(
            "SELECT * FROM f3_parents WHERE parent_id=?", (binding["parent_id"],)
        ).fetchone()
        require(
            child is not None and json.loads(child["payload"]) == binding and parent is not None,
            "F3_CHILD_NOT_REGISTERED",
        )
        parent_document = json.loads(parent["payload"])
        require(
            parent_document["binding_sha256"] == binding["parent_binding_sha256"],
            "F3_PARENT_BINDING_CHANGED",
        )
        if active:
            require(
                child["state"] == "claimed" and parent["state"] == "claimed", "F3_CHILD_NOT_ACTIVE"
            )
    return receipt, parent_document


def verify_child_binding(binding, *, request, run_id, project_root=None, environ=None):
    """Read-only verification for supervisor, worker and CLI using the original queued request."""
    receipt, _ = _child_record(binding, environ=environ)
    require(run_id == binding["run_id"], "F3_CHILD_RUN_CHANGED")
    require(
        project_root is None or str(Path(project_root).resolve()) == binding["project_root"],
        "F3_CHILD_PROJECT_CHANGED",
    )
    require(request_sha256(request) == binding["queued_request_sha256"], "F3_CHILD_REQUEST_CHANGED")
    state = _budget_state(receipt)
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    if run:
        require(
            run["status"] == "open"
            and run["budget_mode"] == "strict_reservation"
            and money(run["limit_usd"]) <= money(binding["run_limit_usd"]),
            "F3_CHILD_LEDGER_LIMIT_CHANGED",
        )
    require(state["charged"] < money(binding["total_limit_usd"]), "F3_SCOPE_EXHAUSTED")
    return VerifiedChildBinding(
        receipt,
        run_id,
        binding["run_limit_usd"],
        binding["daily_limit_usd"],
        binding["total_limit_usd"],
    )


def f3_accounting(parent):
    receipt = _parent_record(parent, active=False)
    state = _budget_state(receipt)
    with registry(parent["project_root"]) as conn:
        children = [
            dict(row)
            for row in conn.execute(
                "SELECT run_id,cell_id,state,settlement FROM f3_children WHERE parent_id=?",
                (parent["parent_id"],),
            )
        ]
    child_ids = {row["run_id"] for row in children}
    own = [row for row in state["attempts"] if row["run_id"] in child_ids]
    cost = _cost_summary(state, own)
    known, actual = cost["known"], cost["actual"]
    blocked = (
        not cost["resolved"]
        or not state["resolved"]
        or any(row["halt_reason"] for row in state["runs"].values())
        or any(row["state"] == "blocked" for row in children)
        or state["charged"] > money(parent["total_limit_usd"])
    )
    return {
        "status": "blocked"
        if blocked
        else "settled"
        if len(children) == 12 and all(row["state"] == "settled" for row in children)
        else "active",
        "parent_id": parent["parent_id"],
        "scope_spent_usd": str(actual) if actual is not None else None,
        "scope_charged_usd": str(cost["charged"]),
        "all_costs_resolved": cost["resolved"] and state["resolved"],
        "scope_limit_usd": parent["scope_limit_usd"],
        "total_limit_usd": parent["total_limit_usd"],
        "new_pool_charged_usd": str(state["charged"]),
        "all_costs_known": known and state["known"],
        "children": children,
    }


def finish_f3_child(binding, *, execution_terminal, cleanup_verified):
    """Only finalized known/bounded costs and confirmed cleanup permit continuation."""
    receipt, parent = _child_record(binding)
    with registry(binding["project_root"]) as conn:
        row = conn.execute(
            "SELECT state FROM f3_children WHERE run_id=?", (binding["run_id"],)
        ).fetchone()
        require(row and row["state"] == "claimed", "F3_CHILD_NOT_ACTIVE")
        state = _budget_state(receipt)
        run = state["runs"].get(binding["run_id"])
        own = [r for r in state["attempts"] if r["run_id"] == binding["run_id"]]
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
            "UPDATE f3_children SET state=?,settlement=? WHERE run_id=?",
            (result["status"], json.dumps(result, sort_keys=True), binding["run_id"]),
        )
    return result | {"scope_spent_usd": f3_accounting(parent)["scope_spent_usd"]}


def finish_f3_parent(parent, *, status):
    _parent_record(parent)
    require(status in {"completed", "failed", "blocked", "stopped"}, "F3_PARENT_STATUS_INVALID")
    with registry(parent["project_root"]) as conn:
        if status == "completed":
            children = conn.execute(
                "SELECT state FROM f3_children WHERE parent_id=?", (parent["parent_id"],)
            ).fetchall()
            require(
                len(children) == 12 and all(r["state"] == "settled" for r in children),
                "F3_NOT_COMPLETE",
            )
        conn.execute(
            "UPDATE f3_parents SET state=? WHERE parent_id=?", (status, parent["parent_id"])
        )
        conn.execute("UPDATE claims SET state=? WHERE run_id=?", (status, parent["parent_id"]))
