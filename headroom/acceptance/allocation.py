"""Explicit FINAL48 allocation binding. Drafts never initialize a ledger/profile."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
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
        "task_pins": {"F1": {"preparation_sha256": None, "scoring_policy_sha256": None}},
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
