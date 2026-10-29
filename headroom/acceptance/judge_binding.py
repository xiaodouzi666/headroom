"""Server-owned judge funding, separate from FINAL48 and anonymous demonstrations.

Hashes bind reviewed local files; they are integrity checks, not digital signatures.
The API authenticates a bearer holder before selecting this controller. No token is
stored here and possession is not proof of a person's judge identity. Filesystem
ownership is trusted, as in the existing ledger path validator.
"""

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from headroom.acceptance.allocation import (
    AllocationRefused,
    _budget_state,
    _cost_summary,
    _quiet_pool,
    digest,
    hash64,
    request_sha256,
    require,
    safe,
)
from headroom.acceptance.demo_binding import _source_record
from headroom.acceptance.judge_credit import read_judge_credit
from headroom.api.security import open_regular
from headroom.budget import BudgetLedger, money
from headroom.ledger_path import existing_file_identity, require_initialized_ledger
from headroom.orchestrator import Services, run_fix
from headroom.runtime import LiveProfile, read_live_profile

SCHEMA = "headroom.judge-access.run.v1"
CREDIT_SCHEMA = "headroom.judge-access.run.v2"
SCHEMAS = frozenset({SCHEMA, CREDIT_SCHEMA})
PLAN_SCHEMA = "headroom.judge-access.plan.v1"
RECEIPT_SCHEMA = "headroom.judge-access.receipt.v1"
EXPIRES_AT = "2026-12-15T20:00:00Z"
ADMISSION_BASIS = "existing_reviewed_local_estimate_with_margin"
AMOUNTS = {
    "gross_cap_usd": "8.00",
    "tax_factor": "1.21",
    "approved_net_usd": "6.61",
    "daily_limit_usd": "6.61",
    "run_limit_usd": "0.30",
}
LIMIT = 512 * 1024


def _now():
    return datetime.now(UTC)


def _paths(root):
    root = Path(root).resolve()
    return root, safe(root, root / ".cache/judge-access")


def _active(expires_at):
    require(expires_at == EXPIRES_AT, "JUDGE_EXPIRY_CHANGED")
    require(_now() < datetime.fromisoformat(EXPIRES_AT), "JUDGE_EXPIRED")


def _authorization(value):
    require(isinstance(value, dict), "JUDGE_AUTHORIZATION_REQUIRED")
    require(
        value.get("state") == "authorized"
        and value.get("scope") == "JUDGE_ACCESS"
        and value.get("approved_net_usd") == AMOUNTS["approved_net_usd"]
        and value.get("gross_cap_usd") == AMOUNTS["gross_cap_usd"]
        and isinstance(value.get("approval_message_ref"), str)
        and 0 < len(value["approval_message_ref"]) <= 512
        and hash64(value.get("statement_sha256")),
        "JUDGE_AUTHORIZATION_REQUIRED",
    )


def _private_json(root, path):
    path = safe(root, Path(path))
    require(stat.S_IMODE(path.lstat().st_mode) == 0o600, "JUDGE_PRIVATE_FILE_REQUIRED")
    with open_regular(root, path.relative_to(root).as_posix(), LIMIT) as handle:
        raw = handle.read(LIMIT + 1)
    require(len(raw) <= LIMIT, "JUDGE_FILE_TOO_LARGE")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _write_new(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
    require(len(raw) <= LIMIT, "JUDGE_FILE_TOO_LARGE")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
    return hashlib.sha256(raw).hexdigest()


def prepare_judge_plan(profile_document, authorization, *, project_root):
    """Pure preparation: no files, ledger, credentials, network or funding activation."""
    root, _ = _paths(project_root)
    _authorization(authorization)
    _active(EXPIRES_AT)
    profile = LiveProfile.model_validate(profile_document)
    profile.runtime_config()
    require(
        profile.run_budget_mode == "strict_reservation"
        and money(profile.authorized_total_usd) == money(AMOUNTS["approved_net_usd"]),
        "JUDGE_PROFILE_LIMIT_CHANGED",
    )
    require(
        money(AMOUNTS["approved_net_usd"]) * money(AMOUNTS["tax_factor"])
        <= money(AMOUNTS["gross_cap_usd"]),
        "JUDGE_GROSS_CAP_EXCEEDED",
    )
    plan = {
        "schema": PLAN_SCHEMA,
        "project_root": str(root),
        "amounts": dict(AMOUNTS),
        "expires_at": EXPIRES_AT,
        "admission_basis": ADMISSION_BASIS,
        "gift_only": True,
        "no_topup": True,
        "authorization": json.loads(json.dumps(authorization)),
        "profile": profile.model_dump(mode="json"),
    }
    return plan | {"plan_sha256": digest(plan)}


def activate_judge_allocation(plan, *, project_root, expected_sha256):
    """Explicit one-time bootstrap; caller supplies the independently reviewed plan hash.

    Never retries/replaces an existing directory. A partial failure is retained for
    operator inspection. This does not invoke any model or read any credential.
    """
    root, directory = _paths(project_root)
    require(isinstance(plan, dict) and hash64(expected_sha256), "JUDGE_PLAN_REQUIRED")
    checked = prepare_judge_plan(plan.get("profile"), plan.get("authorization"), project_root=root)
    require(plan == checked and plan["plan_sha256"] == expected_sha256, "JUDGE_PLAN_CHANGED")
    require(not directory.exists(), "JUDGE_ALREADY_INITIALIZED")
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(mode=0o700, exist_ok=False)
    profile_path, ledger_path, claims_path = (
        directory / name for name in ("runtime-profile.json", "budget.db", "claims.db")
    )
    profile_sha = _write_new(profile_path, plan["profile"])
    read_live_profile(profile_path)  # Reads reviewed profile/evidence only, never .env.
    for path in (ledger_path, claims_path):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))
    BudgetLedger(
        ledger_path, total_limit=AMOUNTS["approved_net_usd"], daily_limit=AMOUNTS["daily_limit_usd"]
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "project_root": str(root),
        "allocation_id": uuid4().hex,
        "plan_sha256": expected_sha256,
        "amounts": dict(AMOUNTS),
        "expires_at": EXPIRES_AT,
        "admission_basis": ADMISSION_BASIS,
        "gift_only": True,
        "no_topup": True,
        "authorization": plan["authorization"],
        "profile_path": str(profile_path),
        "profile_sha256": profile_sha,
        "ledger_path": str(ledger_path),
        "ledger_identity": list(existing_file_identity(ledger_path)),
        "claims_path": str(claims_path),
        "claims_identity": list(existing_file_identity(claims_path)),
    }
    receipt["receipt_sha256"] = digest(receipt)
    for path in (ledger_path, claims_path):
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE judge_identity (singleton INTEGER PRIMARY KEY CHECK(singleton=1), receipt_sha TEXT NOT NULL, allocation_id TEXT NOT NULL)"
            )
            connection.execute(
                "INSERT INTO judge_identity VALUES (1,?,?)",
                (receipt["receipt_sha256"], receipt["allocation_id"]),
            )
            if path == claims_path:
                connection.execute(
                    "CREATE TABLE claims (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, settlement TEXT)"
                )
    _write_new(directory / "receipt.json", receipt)
    return receipt


def verify_judge_receipt(receipt_path, *, project_root, active=True):
    root, directory = _paths(project_root)
    require(Path(receipt_path) == directory / "receipt.json", "JUDGE_RECEIPT_PATH_CHANGED")
    receipt, _ = _private_json(root, receipt_path)
    require(
        isinstance(receipt, dict) and receipt.get("schema") == RECEIPT_SCHEMA,
        "JUDGE_RECEIPT_INVALID",
    )
    require(
        receipt.get("receipt_sha256")
        == digest({k: v for k, v in receipt.items() if k != "receipt_sha256"}),
        "JUDGE_RECEIPT_CHANGED",
    )
    require(
        receipt.get("project_root") == str(root)
        and receipt.get("amounts") == AMOUNTS
        and receipt.get("expires_at") == EXPIRES_AT
        and receipt.get("admission_basis") == ADMISSION_BASIS
        and receipt.get("gift_only") is True
        and receipt.get("no_topup") is True,
        "JUDGE_CONFIG_CHANGED",
    )
    _authorization(receipt.get("authorization"))
    if active:
        _active(receipt["expires_at"])
    require(
        receipt.get("profile_path") == str(directory / "runtime-profile.json"),
        "JUDGE_PROFILE_PATH_CHANGED",
    )
    _, profile_sha = _private_json(root, receipt["profile_path"])
    require(profile_sha == receipt["profile_sha256"], "JUDGE_PROFILE_CHANGED")
    profile = read_live_profile(receipt["profile_path"])
    require(
        profile.run_budget_mode == "strict_reservation"
        and money(profile.authorized_total_usd) == money(AMOUNTS["approved_net_usd"]),
        "JUDGE_PROFILE_LIMIT_CHANGED",
    )
    for prefix, filename in (("ledger", "budget.db"), ("claims", "claims.db")):
        path = safe(root, Path(receipt[prefix + "_path"]))
        require(path == directory / filename, "JUDGE_DATABASE_PATH_CHANGED")
        from headroom.ledger_path import validate_existing_ledger_path

        validate_existing_ledger_path(path, expected_identity=tuple(receipt[prefix + "_identity"]))
        require(stat.S_IMODE(path.stat().st_mode) == 0o600, "JUDGE_PRIVATE_FILE_REQUIRED")
        if prefix == "ledger":
            require_initialized_ledger(path, expected_identity=tuple(receipt["ledger_identity"]))
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            row = connection.execute(
                "SELECT receipt_sha,allocation_id FROM judge_identity WHERE singleton=1"
            ).fetchone()
            require(
                row == (receipt["receipt_sha256"], receipt["allocation_id"]),
                "JUDGE_DATABASE_BINDING_CHANGED",
            )
    return receipt


@contextmanager
def _claims(receipt):
    path = Path(receipt["claims_path"])
    with closing(
        sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None, timeout=5)
    ) as connection:
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _clear_claims(connection, allowed_run=None):
    require(
        all(
            row["state"] == "settled" or row["run_id"] == allowed_run
            for row in connection.execute("SELECT run_id,state FROM claims")
        ),
        "JUDGE_UNSETTLED_CLAIM",
    )


def _ledger(receipt, binding, cls=BudgetLedger):
    return cls(
        Path(receipt["ledger_path"]),
        require_existing=True,
        expected_identity=tuple(receipt["ledger_identity"]),
        daily_limit=binding["daily_limit_usd"],
        total_limit=binding["total_limit_usd"],
    )


def _funding_limits(receipt, *, connection=None):
    extension = read_judge_credit(receipt, connection=connection)
    if extension is None:
        return {
            "total_limit_usd": AMOUNTS["approved_net_usd"],
            "daily_limit_usd": AMOUNTS["daily_limit_usd"],
            "run_limit_usd": AMOUNTS["run_limit_usd"],
            "credit_extension_sha256": None,
        }
    return {
        key: extension["amounts"][key]
        for key in ("total_limit_usd", "daily_limit_usd", "run_limit_usd")
    } | {"credit_extension_sha256": extension["extension_sha256"]}


class JudgeAllocation:
    def __init__(self, receipt_path, *, project_root):
        self.root = Path(project_root).resolve()
        self.receipt_path = Path(receipt_path)
        self.receipt = verify_judge_receipt(receipt_path, project_root=self.root, active=False)
        self._receipt_sha = self.receipt["receipt_sha256"]

    def _receipt(self, *, active=True):
        receipt = verify_judge_receipt(self.receipt_path, project_root=self.root, active=active)
        require(receipt["receipt_sha256"] == self._receipt_sha, "JUDGE_RECEIPT_CHANGED")
        return receipt

    @property
    def funding_limits(self):
        """Explicit effective funding; the original receipt is never rewritten."""
        return _funding_limits(self._receipt(active=False))

    @property
    def effective_daily_limit_usd(self):
        return self.funding_limits["daily_limit_usd"]

    @property
    def available(self):
        try:
            receipt = self._receipt()
            with _claims(receipt) as connection:
                _clear_claims(connection)
                limits = _funding_limits(receipt, connection=connection)
                state = _budget_state(receipt)
                _quiet_pool(state)
                return state["charged"] < money(limits["total_limit_usd"])
        except (OSError, ValueError, sqlite3.Error, ArithmeticError, KeyError):
            return False

    def begin(self, run_id, request, *, source_sha256):
        require(re.fullmatch(r"[a-f0-9]{32}", run_id) is not None, "JUDGE_RUN_INVALID")
        receipt = self._receipt()
        source = _source_record(request)
        require(source["sha256"] == source_sha256, "JUDGE_SOURCE_CHANGED")
        with _claims(receipt) as connection:
            _clear_claims(connection)
            limits = _funding_limits(receipt, connection=connection)
            require(
                request.runtime_profile == receipt["profile_path"]
                and money(request.daily_budget_usd) == money(limits["daily_limit_usd"])
                and 0 < money(request.budget_usd) <= money(limits["run_limit_usd"]),
                "JUDGE_REQUEST_CONFIG_CHANGED",
            )
            state = _budget_state(receipt)
            _quiet_pool(state)
            remaining = money(limits["total_limit_usd"]) - state["charged"]
            limit = min(money(request.budget_usd), remaining)
            require(limit > 0, "JUDGE_EXHAUSTED")
            request = request.model_copy(update={"budget_usd": str(limit)})
            binding = {
                "schema": CREDIT_SCHEMA if limits["credit_extension_sha256"] else SCHEMA,
                "project_root": str(self.root),
                "receipt_path": str(self.receipt_path),
                "receipt_sha256": receipt["receipt_sha256"],
                "run_id": run_id,
                "request_sha256": request_sha256(request),
                "source": source,
                "run_limit_usd": str(limit),
                "daily_limit_usd": limits["daily_limit_usd"],
                "total_limit_usd": limits["total_limit_usd"],
                "expires_at": EXPIRES_AT,
            }
            if limits["credit_extension_sha256"]:
                binding["credit_extension_sha256"] = limits["credit_extension_sha256"]
            binding["binding_sha256"] = digest(binding)
            try:
                connection.execute(
                    "INSERT INTO claims VALUES (?,?,'claimed',NULL)",
                    (run_id, json.dumps(binding, sort_keys=True)),
                )
            except sqlite3.IntegrityError:
                raise AllocationRefused("JUDGE_ALREADY_CLAIMED") from None
        return request, binding

    def finish(self, binding, *, execution_terminal, cleanup_verified):
        receipt = self._receipt(active=False)
        _validate_binding(binding, receipt, binding.get("run_id"))
        with _claims(receipt) as connection:
            _active_claim(connection, binding)
            state = _budget_state(receipt)
            run = state["runs"].get(binding["run_id"])
            own = [row for row in state["attempts"] if row["run_id"] == binding["run_id"]]
            cost = _cost_summary(state, own)
            settled = (
                execution_terminal is True
                and cleanup_verified is True
                and cost["resolved"]
                and state["resolved"]
                and all(
                    row["status"] == "closed" and not row["halt_reason"]
                    for row in state["runs"].values()
                )
                and (run is not None or not own)
                and cost["charged"] <= money(binding["run_limit_usd"])
                and state["charged"] <= money(binding["total_limit_usd"])
            )
            result = {
                "status": "settled" if settled else "blocked",
                "actual_usd": str(cost["actual"]) if cost["actual"] is not None else None,
                "charged_usd": str(cost["charged"]),
                "cost_resolved": cost["resolved"],
                "cost_basis": "exact"
                if cost["known"]
                else "conservative_bound"
                if cost["resolved"]
                else "unresolved",
            }
            connection.execute(
                "UPDATE claims SET state=?,settlement=? WHERE run_id=?",
                (result["status"], json.dumps(result), binding["run_id"]),
            )
        if not settled:
            ledger = _ledger(receipt, binding)
            if run is None:
                ledger.open_run(binding["run_id"], binding["run_limit_usd"])
            ledger.halt(binding["run_id"], "local_accounting_incomplete")
        return result


def _validate_binding(binding, receipt, run_id):
    require(
        binding.get("schema") in SCHEMAS
        and binding.get("run_id") == run_id
        and binding.get("binding_sha256")
        == digest({k: v for k, v in binding.items() if k != "binding_sha256"}),
        "JUDGE_BINDING_CHANGED",
    )
    if binding["schema"] == CREDIT_SCHEMA:
        limits = _funding_limits(receipt)
        require(
            limits["credit_extension_sha256"] is not None
            and binding.get("credit_extension_sha256") == limits["credit_extension_sha256"],
            "JUDGE_CREDIT_BINDING_CHANGED",
        )
    else:
        require("credit_extension_sha256" not in binding, "JUDGE_CREDIT_BINDING_CHANGED")
        limits = {
            "daily_limit_usd": AMOUNTS["daily_limit_usd"],
            "total_limit_usd": AMOUNTS["approved_net_usd"],
        }
    require(
        binding["receipt_sha256"] == receipt["receipt_sha256"]
        and binding["expires_at"] == EXPIRES_AT
        and binding["project_root"] == receipt["project_root"]
        and 0 < money(binding["run_limit_usd"]) <= money(AMOUNTS["run_limit_usd"])
        and money(binding["daily_limit_usd"]) == money(limits["daily_limit_usd"])
        and money(binding["total_limit_usd"]) == money(limits["total_limit_usd"]),
        "JUDGE_BINDING_LIMIT_CHANGED",
    )


def _active_claim(connection, binding):
    row = connection.execute(
        "SELECT payload,state FROM claims WHERE run_id=?", (binding["run_id"],)
    ).fetchone()
    require(
        row and row["state"] == "claimed" and json.loads(row["payload"]) == binding,
        "JUDGE_CLAIM_CHANGED",
    )


def verify_judge_binding(binding, request, run_id, *, pending_attempt_id=None):
    receipt = verify_judge_receipt(binding["receipt_path"], project_root=binding["project_root"])
    _validate_binding(binding, receipt, run_id)
    require(
        request_sha256(request) == binding["request_sha256"]
        and _source_record(request) == binding["source"]
        and request.runtime_profile == receipt["profile_path"]
        and money(request.daily_budget_usd) == money(binding["daily_limit_usd"])
        and money(request.budget_usd) == money(binding["run_limit_usd"]),
        "JUDGE_REQUEST_CHANGED",
    )
    with _claims(receipt) as connection:
        _active_claim(connection, binding)
        _clear_claims(connection, run_id)
    state = _budget_state(receipt)
    if pending_attempt_id is not None:
        pending = [row for row in state["attempts"] if row["id"] == pending_attempt_id]
        require(
            len(pending) == 1
            and pending[0]["run_id"] == run_id
            and pending[0]["dispatched"] == 0
            and pending[0]["settled"] == 0,
            "JUDGE_PENDING_ATTEMPT_CHANGED",
        )
        # Only this exact unsent reservation may be pending at the dispatch check.
        # The ledger transaction independently enforces the same exclusion.
        state["resolved"] = all(
            row["id"] == pending_attempt_id or row["id"] in state["resolved_attempt_ids"]
            for row in state["attempts"]
        )
    _quiet_pool(state, allowed_run=run_id)
    run = state["runs"].get(run_id)
    require(
        run is None
        or (
            money(run["limit_usd"]) == money(binding["run_limit_usd"])
            and run["budget_mode"] == "strict_reservation"
        ),
        "JUDGE_RUN_LIMIT_CHANGED",
    )
    return receipt


def judge_budget_factory(binding, original_request):
    class BoundLedger(BudgetLedger):
        def open_run(self, run_id, run_limit, *, budget_mode="strict_reservation"):
            require(
                run_id == binding["run_id"]
                and money(run_limit) == money(binding["run_limit_usd"])
                and budget_mode == "strict_reservation",
                "JUDGE_RUN_LIMIT_CHANGED",
            )
            verify_judge_binding(binding, original_request, run_id)
            return super().open_run(run_id, run_limit, budget_mode=budget_mode)

        def reserve(self, run_id, *args, **kwargs):
            require(run_id == binding["run_id"], "JUDGE_RUN_CHANGED")
            verify_judge_binding(binding, original_request, run_id)
            return super().reserve(run_id, *args, **kwargs)

        def mark_dispatched(self, run_id, attempt_id):
            require(run_id == binding["run_id"], "JUDGE_RUN_CHANGED")
            verify_judge_binding(binding, original_request, run_id, pending_attempt_id=attempt_id)
            return super().mark_dispatched(run_id, attempt_id)

    def factory(run_id, request, profile):
        receipt = verify_judge_binding(binding, request, run_id)
        require(
            profile.model_dump(mode="json")
            == read_live_profile(receipt["profile_path"]).model_dump(mode="json"),
            "JUDGE_PROFILE_CHANGED",
        )
        return _ledger(receipt, binding, BoundLedger)

    return factory


def run_bound_judge(request, *, store, run_root, run_id, binding, worker=None):
    verify_judge_binding(binding, request, run_id)
    services = Services(budget_factory=judge_budget_factory(binding, request))
    return (worker or run_fix)(
        request, store=store, run_root=run_root, run_id=run_id, services=services
    )
