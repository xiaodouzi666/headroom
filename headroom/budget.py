"""Persistent, conservative dollar reservations; unknown charges never become zero."""

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

from headroom.ledger_path import (
    LedgerPathError,
    existing_file_identity,
    require_initialized_ledger,
    validate_existing_ledger_path,
    validate_ledger_schema,
)

_INITIALIZATION_TIMEOUT_SECONDS = 30.0
_INITIALIZATION_RETRY_SECONDS = 0.05


class BudgetExceeded(RuntimeError):
    pass


class RunBudgetReached(BudgetExceeded):
    """Actual usage reached a run stop line; the shared billing bound remains valid."""

    def __init__(self, *, exceeded, basis="actual_usage"):
        self.exceeded = exceeded
        self.basis = basis
        if basis == "conservative_bound":
            RuntimeError.__init__(
                self, "Conservative run charge bound reached its limit; actual cost remains unknown"
            )
            return
        super().__init__(
            "Actual run cost exceeded its limit; further calls stopped"
            if exceeded
            else "Actual run cost reached its limit; further calls stopped"
        )


RUN_BUDGET_MODES = {"strict_reservation", "actual_usage"}


def current_utc_day():
    """Trusted dispatch clock; an accounting day argument cannot override current time."""
    return datetime.now(UTC).date().isoformat()


def money(value):
    if isinstance(value, (float, bool)):
        raise TypeError("Dollar values require Decimal or decimal strings")
    amount = Decimal(value)
    if not amount.is_finite() or amount < 0:
        raise ValueError("Dollar values must be finite and nonnegative")
    if len(amount.as_tuple().digits) > 80 or abs(amount.as_tuple().exponent) > 80:
        raise ValueError("Dollar precision exceeds supported bounds")
    return amount


class BudgetLedger:
    """Reserve open-run floors and each network attempt across processes.

    Strict run mode also bounds each reservation by the run limit. Actual-usage
    mode uses that limit as a settled-cost stop line while shared pools reserve
    the full provider bound.

    An attempt records either a provider-bound reservation or an explicit local
    estimate, never an asserted actual charge. Unknown/pending charges block further
    dispatch across this ledger. An abandoned run retains its reservation for review.
    """

    require_existing = False

    def __init__(
        self,
        path,
        *,
        daily_limit="12",
        total_limit=None,
        day=None,
        require_existing=False,
        expected_identity=None,
    ):
        self.require_existing = require_existing
        if expected_identity is not None and not require_existing:
            raise LedgerPathError("File identity requires existing-only budget selection")
        self.path = (
            require_initialized_ledger(path, expected_identity=expected_identity)
            if require_existing
            else Path(path)
        )
        self.expected_identity = (
            existing_file_identity(self.path)
            if require_existing and expected_identity is None
            else expected_identity
        )
        if not require_existing:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit = money(daily_limit)
        self.total_limit = None if total_limit is None else money(total_limit)
        self.day = day or current_utc_day()
        with self._transaction() as conn:
            # Each statement remains inside the same BEGIN IMMEDIATE migration transaction.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_runs (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, limit_usd TEXT NOT NULL,
                    status TEXT NOT NULL, halt_reason TEXT,
                    budget_mode TEXT NOT NULL DEFAULT 'strict_reservation'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_attempts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES budget_runs(id),
                    upper_usd TEXT NOT NULL, charged_usd TEXT NOT NULL,
                    actual_usd TEXT, settled INTEGER NOT NULL DEFAULT 0,
                    admission_kind TEXT NOT NULL DEFAULT 'verified_provider_bound',
                    dispatched INTEGER NOT NULL DEFAULT 1
                )
            """)
            run_columns = {row[1] for row in conn.execute("PRAGMA table_info(budget_runs)")}
            if "budget_mode" not in run_columns:
                conn.execute(
                    "ALTER TABLE budget_runs ADD COLUMN budget_mode TEXT "
                    "NOT NULL DEFAULT 'strict_reservation'"
                )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(budget_attempts)")}
            if "admission_kind" not in columns:
                conn.execute(
                    "ALTER TABLE budget_attempts ADD COLUMN admission_kind TEXT "
                    "NOT NULL DEFAULT 'verified_provider_bound'"
                )
            if "dispatched" not in columns:
                # Existing pending attempts may already have reached the provider.
                conn.execute(
                    "ALTER TABLE budget_attempts ADD COLUMN dispatched INTEGER NOT NULL DEFAULT 1"
                )
            for name, declaration in (
                ("charge_status", "TEXT NOT NULL DEFAULT 'pending'"),
                ("charge_basis", "TEXT"),
                ("review_sha256", "TEXT"),
            ):
                if name not in columns:
                    conn.execute(f"ALTER TABLE budget_attempts ADD COLUMN {name} {declaration}")
            conn.execute(
                "UPDATE budget_attempts SET charge_status='exact' WHERE actual_usd IS NOT NULL"
            )
            conn.execute("""UPDATE budget_attempts SET charge_status='unknown'
                WHERE charge_status='pending' AND settled=1 AND actual_usd IS NULL""")
            conn.execute("""CREATE TABLE IF NOT EXISTS budget_retention_reviews (
                receipt_sha256 TEXT PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL, reviewed_at TEXT NOT NULL, evidence_json TEXT NOT NULL
            )""")
            conn.execute("""UPDATE budget_runs SET halt_reason='provider_charge_unknown'
                WHERE halt_reason IS NULL AND id IN (
                    SELECT run_id FROM budget_attempts
                    WHERE settled=1 AND actual_usd IS NULL AND dispatched=1
                    AND charge_status NOT IN ('upper_bound','reviewed_retained')
                )""")

    def _begin_transaction(self):
        # WAL conversion can return BUSY immediately despite busy_timeout. Retry only
        # before handing a connection to a caller; never replay a transaction body.
        deadline = time.monotonic() + _INITIALIZATION_TIMEOUT_SECONDS
        while True:
            conn = None
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Budget database initialization deadline exceeded")
                if self.require_existing:
                    path = validate_existing_ledger_path(
                        self.path, expected_identity=self.expected_identity
                    )
                    conn = sqlite3.connect(
                        path.as_uri() + "?mode=rw",
                        uri=True,
                        timeout=remaining,
                        isolation_level=None,
                    )
                    validate_existing_ledger_path(
                        self.path, expected_identity=self.expected_identity
                    )
                    validate_ledger_schema(conn)
                else:
                    conn = sqlite3.connect(self.path, timeout=remaining, isolation_level=None)
                conn.row_factory = sqlite3.Row
                for statement in (
                    "PRAGMA journal_mode=WAL",
                    "PRAGMA foreign_keys=ON",
                    "BEGIN IMMEDIATE",
                ):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Budget database initialization deadline exceeded")
                    # Include SQLite's own lock waits in one overall deadline, rather
                    # than granting a new 30-second wait to every statement/attempt.
                    conn.execute(f"PRAGMA busy_timeout={max(0, int(remaining * 1000))}")
                    conn.execute(statement)
                if time.monotonic() > deadline:
                    raise TimeoutError("Budget database initialization deadline exceeded")
                return conn
            except BaseException as error:
                if conn is not None:
                    try:
                        if conn.in_transaction:
                            conn.rollback()
                    finally:
                        conn.close()
                code = getattr(error, "sqlite_errorcode", None)
                retryable = (
                    isinstance(error, sqlite3.OperationalError)
                    and isinstance(code, int)
                    and (code & 0xFF) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                )
                remaining = deadline - time.monotonic()
                if not retryable or remaining <= 0:
                    if self.require_existing and isinstance(error, sqlite3.Error):
                        raise LedgerPathError("Shared budget database is unavailable") from None
                    raise
                time.sleep(min(_INITIALIZATION_RETRY_SECONDS, remaining))

    @contextmanager
    def _transaction(self):
        conn = self._begin_transaction()
        try:
            with localcontext() as context:
                # money accepts 80-digit coefficients with exponents in [-80,80].
                # 256 digits also preserve sums across their full magnitude span.
                context.prec = 256
                yield conn
                if conn.in_transaction:
                    conn.commit()
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _charged(conn, run_id):
        return sum(
            (
                money(row[0])
                for row in conn.execute(
                    "SELECT charged_usd FROM budget_attempts WHERE run_id=?", (run_id,)
                )
            ),
            Decimal(0),
        )

    @staticmethod
    def _require_clear(conn, *, excluding=None):
        # Must run under the same write transaction as every new live commitment.
        if conn.execute(
            "SELECT 1 FROM budget_runs WHERE halt_reason IS NOT NULL LIMIT 1"
        ).fetchone():
            raise BudgetExceeded("Unresolved provider billing requires review before further calls")
        if conn.execute(
            "SELECT 1 FROM budget_attempts WHERE actual_usd IS NULL "
            "AND NOT (settled=1 AND dispatched=1 AND admission_kind='verified_provider_bound' "
            "AND charge_status IN ('upper_bound','reviewed_retained')) "
            "AND (? IS NULL OR id != ?) LIMIT 1",
            (excluding, excluding),
        ).fetchone():
            raise BudgetExceeded("Pending or unknown provider charge blocks further calls")

    @staticmethod
    def _strict_pool(conn):
        # Run history is durable: closing a run must not silently re-enable
        # estimates that could invalidate this shared pool's hard admission.
        return (
            conn.execute(
                "SELECT 1 FROM budget_runs WHERE budget_mode='actual_usage' LIMIT 1"
            ).fetchone()
            is not None
        )

    def _require_dispatch_day(self, run):
        today = current_utc_day()
        if self.day != today or run["day"] != today:
            raise BudgetExceeded("Run or ledger UTC day expired; start a new run before dispatch")

    def require_actual_pool(self):
        if self.total_limit is None or self.total_limit <= 0 or self.daily_limit <= 0:
            raise BudgetExceeded(
                "Actual-usage mode requires finite positive global and daily pools"
            )

    def _committed(self, conn, *, day=None, run_id=None, additional=Decimal(0)):
        """Open-run floors plus outstanding/actual charges, including a proposed attempt."""
        total = Decimal(0)
        for row in conn.execute("SELECT * FROM budget_runs"):
            if day is not None and row["day"] != day:
                continue
            used = self._charged(conn, row["id"])
            if row["id"] == run_id:
                used += additional
            total += max(money(row["limit_usd"]), used) if row["status"] == "open" else used
        return total

    def open_run(self, run_id, run_limit, *, budget_mode="strict_reservation"):
        limit = money(run_limit)
        if budget_mode not in RUN_BUDGET_MODES:
            raise ValueError("Unsupported run budget mode")
        if budget_mode == "actual_usage":
            self.require_actual_pool()
        if not run_id or limit <= 0:
            raise ValueError("A run needs a nonempty ID and positive budget")
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM budget_runs WHERE id=?", (run_id,)).fetchone():
                raise ValueError("Run budget already exists; do not silently reset it")
            self._require_clear(conn)
            if self._strict_pool(conn):
                self.require_actual_pool()
            total_committed = Decimal(0)
            for row in conn.execute("SELECT * FROM budget_runs"):
                used = self._charged(conn, row["id"])
                total_committed += (
                    max(money(row["limit_usd"]), used) if row["status"] == "open" else used
                )
            if self.total_limit is not None and total_committed + limit > self.total_limit:
                raise BudgetExceeded("Total authorized budget cannot reserve this run")
            committed = Decimal(0)
            for row in conn.execute("SELECT * FROM budget_runs WHERE day=?", (self.day,)):
                used = self._charged(conn, row["id"])
                committed += max(money(row["limit_usd"]), used) if row["status"] == "open" else used
            if committed + limit > self.daily_limit:
                raise BudgetExceeded("Daily budget cannot reserve this run")
            conn.execute(
                "INSERT INTO budget_runs (id,day,limit_usd,status,halt_reason,budget_mode) "
                "VALUES (?,?,?,?,?,?)",
                (run_id, self.day, str(limit), "open", None, budget_mode),
            )
        return self.snapshot(run_id)

    def reserve(
        self,
        run_id,
        attempt_id,
        upper_usd,
        *,
        admission_kind="verified_provider_bound",
        dispatched=True,
    ):
        # upper_usd is the legacy storage/argument name; estimates are not upper bounds.
        upper = money(upper_usd)
        if admission_kind not in {"verified_provider_bound", "local_estimate"}:
            raise ValueError("Unsupported admission kind")
        if type(dispatched) is not bool:
            raise TypeError("Dispatch state must be boolean")
        with self._transaction() as conn:
            run = conn.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Run budget was not opened")
            if run["status"] != "open" or run["halt_reason"]:
                raise BudgetExceeded("Run budget is closed or halted")
            self._require_dispatch_day(run)
            self._require_clear(conn)
            if self._strict_pool(conn):
                self.require_actual_pool()
                if admission_kind != "verified_provider_bound":
                    raise BudgetExceeded("Shared strict pool does not permit local estimates")
            charged = self._charged(conn, run_id)
            limit = money(run["limit_usd"])
            if run["budget_mode"] == "actual_usage":
                self.require_actual_pool()
                if admission_kind != "verified_provider_bound":
                    raise BudgetExceeded("Actual-usage mode requires a verified provider bound")
                # _require_clear established that every existing charge is settled and known.
                if charged >= limit:
                    bounded = (
                        conn.execute(
                            "SELECT 1 FROM budget_attempts WHERE run_id=? AND actual_usd IS NULL LIMIT 1",
                            (run_id,),
                        ).fetchone()
                        is not None
                    )
                    raise RunBudgetReached(
                        exceeded=charged > limit,
                        basis="conservative_bound" if bounded else "actual_usage",
                    )
            elif charged + upper > limit:
                raise BudgetExceeded("Run budget cannot reserve the next model attempt")
            if (
                self.total_limit is not None
                and self._committed(conn, run_id=run_id, additional=upper) > self.total_limit
            ):
                raise BudgetExceeded("Total authorized pool cannot reserve the next model attempt")
            if (
                self._committed(conn, day=run["day"], run_id=run_id, additional=upper)
                > self.daily_limit
            ):
                raise BudgetExceeded("Daily pool cannot reserve the next model attempt")
            if conn.execute("SELECT 1 FROM budget_attempts WHERE id=?", (attempt_id,)).fetchone():
                raise ValueError("Attempt reservation already exists")
            conn.execute(
                "INSERT INTO budget_attempts "
                "(id,run_id,upper_usd,charged_usd,actual_usd,settled,admission_kind,dispatched) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    attempt_id,
                    run_id,
                    str(upper),
                    str(upper),
                    None,
                    0,
                    admission_kind,
                    int(dispatched),
                ),
            )

    def mark_dispatched(self, run_id, attempt_id):
        with self._transaction() as conn:
            run = conn.execute(
                "SELECT status,day FROM budget_runs WHERE id=?", (run_id,)
            ).fetchone()
            if run is None or run["status"] != "open":
                raise BudgetExceeded("Run budget is closed or missing before dispatch")
            self._require_dispatch_day(run)
            self._require_clear(conn, excluding=attempt_id)
            cursor = conn.execute(
                "UPDATE budget_attempts SET dispatched=1 "
                "WHERE id=? AND run_id=? AND dispatched=0 AND settled=0",
                (attempt_id, run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("Attempt cannot be marked for dispatch")

    def cancel_undispatched(self, run_id, attempt_id):
        """Only a caller still before SDK dispatch may release its unsent reservation."""
        with self._transaction() as conn:
            cursor = conn.execute(
                "UPDATE budget_attempts SET charged_usd='0',actual_usd='0',settled=1,charge_status='exact' "
                "WHERE id=? AND run_id=? AND dispatched=0 AND settled=0",
                (attempt_id, run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("A dispatched or settled attempt cannot be released")

    def settle(self, run_id, attempt_id, actual_usd, *, bound_invalid=False):
        actual = None if actual_usd is None else money(actual_usd)
        exceeded = False
        run_reached = run_exceeded = conservative = False
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM budget_attempts WHERE id=? AND run_id=?", (attempt_id, run_id)
            ).fetchone()
            if row is None or row["settled"] or not row["dispatched"]:
                raise ValueError("Attempt is missing or already settled")
            upper = money(row["upper_usd"])
            charge = upper if actual is None else actual
            exceeded = actual is not None and actual > upper
            conn.execute(
                "UPDATE budget_attempts SET actual_usd=?,charged_usd=?,settled=1,charge_status=? WHERE id=?",
                (
                    None if actual is None else str(actual),
                    str(charge),
                    "unknown" if actual is None else "exact",
                    attempt_id,
                ),
            )
            if exceeded or bound_invalid or actual is None:
                conn.execute(
                    "UPDATE budget_runs SET halt_reason=? WHERE id=?",
                    (
                        "provider_bound_unresolved"
                        if bound_invalid
                        else "provider_charge_unknown"
                        if actual is None
                        else "estimate_reservation_exceeded"
                        if row["admission_kind"] == "local_estimate"
                        else "provider_bound_exceeded",
                        run_id,
                    ),
                )
            if actual is not None and not exceeded and not bound_invalid:
                run = conn.execute(
                    "SELECT limit_usd,budget_mode FROM budget_runs WHERE id=?", (run_id,)
                ).fetchone()
                if run["budget_mode"] == "actual_usage":
                    committed = self._charged(conn, run_id)
                    run_reached = committed >= money(run["limit_usd"])
                    run_exceeded = committed > money(run["limit_usd"])
                    conservative = (
                        conn.execute(
                            "SELECT 1 FROM budget_attempts WHERE run_id=? AND actual_usd IS NULL LIMIT 1",
                            (run_id,),
                        ).fetchone()
                        is not None
                    )
        if exceeded or bound_invalid:
            raise BudgetExceeded("Provider billing requires review; further calls stopped")
        if run_reached:
            # Raise after committing actual usage. This is a local run stop, not a
            # global billing incident; other runs may use the remaining strict pool.
            raise RunBudgetReached(
                exceeded=run_exceeded,
                basis="conservative_bound" if conservative else "actual_usage",
            )

    def settle_upper_bound(self, run_id, attempt_id, upper_usd, *, basis):
        """Settle a verified usage/tariff bound without inventing an actual charge."""
        bound = money(upper_usd)
        if basis != "verified_tariff_missing_cache_count":
            raise ValueError("Unsupported bounded settlement basis")
        invalid = reached = exceeded = False
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM budget_attempts WHERE id=? AND run_id=?", (attempt_id, run_id)
            ).fetchone()
            run = conn.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or run is None or row["settled"] or not row["dispatched"]:
                raise ValueError("Attempt is missing, unsent or already settled")
            if row["admission_kind"] != "verified_provider_bound":
                raise ValueError("Bounded settlement requires a strict provider reservation")
            invalid = bound > money(row["upper_usd"])
            conn.execute(
                "UPDATE budget_attempts SET charged_usd=?,settled=1,charge_status=?,charge_basis=? WHERE id=?",
                (
                    str(max(bound, money(row["upper_usd"])) if invalid else bound),
                    "unknown" if invalid else "upper_bound",
                    basis,
                    attempt_id,
                ),
            )
            if invalid:
                conn.execute(
                    "UPDATE budget_runs SET halt_reason='provider_bound_exceeded' WHERE id=?",
                    (run_id,),
                )
            elif run["budget_mode"] == "actual_usage":
                charged = self._charged(conn, run_id)
                reached = charged >= money(run["limit_usd"])
                exceeded = charged > money(run["limit_usd"])
        if invalid:
            raise BudgetExceeded("Verified usage bound exceeds reservation; review required")
        if reached:
            raise RunBudgetReached(exceeded=exceeded, basis="conservative_bound")

    def review_retained(self, run_id, attempt_id, *, expected_attempt, receipt_sha256, evidence):
        """Explicit review preserves the historical full reservation and unknown actual."""
        if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
            raise ValueError("Review receipt SHA256 is required")
        if not isinstance(evidence, dict) or evidence.get("reason") not in {
            "missing_cached_token_usage",
            "http_529_missing_usage_full_reservation",
        }:
            raise ValueError("Only narrowly verified retained-charge cases can be reviewed")
        http_review = evidence["reason"] == "http_529_missing_usage_full_reservation"
        required = {
            "id",
            "run_id",
            "upper_usd",
            "charged_usd",
            "actual_usd",
            "settled",
            "admission_kind",
            "dispatched",
        }
        if not isinstance(expected_attempt, dict) or set(expected_attempt) != required:
            raise ValueError("Complete original attempt identity is required")
        serialized = json.dumps(evidence, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM budget_attempts WHERE id=? AND run_id=?", (attempt_id, run_id)
            ).fetchone()
            run = conn.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if row is None or run is None:
                raise ValueError("Review target is missing")
            original = {key: row[key] for key in required}
            if json.dumps(original, sort_keys=True) != json.dumps(expected_attempt, sort_keys=True):
                raise ValueError("Review target changed or belongs to another run")
            expected_run = evidence.get("expected_run")
            if not isinstance(expected_run, dict) or set(expected_run) != {
                "id",
                "day",
                "limit_usd",
                "status",
                "halt_reason",
                "budget_mode",
            }:
                raise ValueError("Complete original run identity is required")
            if json.dumps({key: run[key] for key in expected_run}, sort_keys=True) != json.dumps(
                expected_run, sort_keys=True
            ):
                raise ValueError("Reviewed run changed")
            if http_review:
                # Recheck every sibling and every immutable call while holding the
                # ledger write lock. Legitimate dispatch cannot append another call:
                # it must first reserve under this same lock; this run is closed.
                if (
                    evidence.get("schema") != "headroom.http529-full-retention.v1"
                    or evidence.get("http_status") != 529
                    or evidence.get("actual_usd") is not None
                    or evidence.get("historical_result_reassessment") is not False
                    or money(evidence.get("retained_full_upper_usd")) != money(row["upper_usd"])
                ):
                    raise ValueError("HTTP retention evidence is not the narrow reviewed case")
                attempts = [
                    dict(item)
                    for item in conn.execute(
                        "SELECT * FROM budget_attempts WHERE run_id=? ORDER BY id", (run_id,)
                    )
                ]
                if json.dumps(attempts, sort_keys=True) != json.dumps(
                    evidence.get("expected_attempts"), sort_keys=True
                ):
                    raise ValueError("Reviewed run attempt set changed")
                store_uri = Path(evidence["store_path"]).resolve().as_uri() + "?mode=ro"
                with closing(sqlite3.connect(store_uri, uri=True)) as source:
                    source.row_factory = sqlite3.Row
                    source.execute("PRAGMA query_only=ON")
                    calls = []
                    for item in source.execute(
                        "SELECT * FROM llm_calls WHERE run_id=? ORDER BY id", (run_id,)
                    ):
                        calls.append(
                            {
                                **{
                                    key: item[key]
                                    for key in (
                                        "id",
                                        "run_id",
                                        "model",
                                        "role",
                                        "input_tokens",
                                        "output_tokens",
                                        "cost_usd",
                                        "created_at",
                                    )
                                },
                                "data_sha256": hashlib.sha256(
                                    item["data_json"].encode()
                                ).hexdigest(),
                            }
                        )
                if json.dumps(calls, sort_keys=True) != json.dumps(
                    evidence.get("expected_calls"), sort_keys=True
                ):
                    raise ValueError("Reviewed run call set changed")
                mapping = json.dumps(
                    {"attempts": attempts, "calls": calls},
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if hashlib.sha256(mapping.encode()).hexdigest() != evidence.get(
                    "run_mapping_sha256"
                ):
                    raise ValueError("Reviewed run mapping digest changed")
            if (
                run["status"] != "closed"
                or run["halt_reason"] != "provider_charge_unknown"
                or row["actual_usd"] is not None
                or not row["settled"]
                or not row["dispatched"]
                or row["admission_kind"] != "verified_provider_bound"
                or row["charge_status"] != "unknown"
                or money(row["charged_usd"]) != money(row["upper_usd"])
                or row["review_sha256"] is not None
            ):
                raise ValueError("Only a closed, settled strict unknown can retain its full bound")
            conn.execute(
                "INSERT INTO budget_retention_reviews VALUES (?,?,?,?,?)",
                (receipt_sha256, attempt_id, run_id, datetime.now(UTC).isoformat(), serialized),
            )
            conn.execute(
                "UPDATE budget_attempts SET charge_status='reviewed_retained',"
                "charge_basis='manual_full_reservation_retained',review_sha256=? WHERE id=?",
                (receipt_sha256, attempt_id),
            )
            unresolved = conn.execute(
                "SELECT 1 FROM budget_attempts WHERE run_id=? AND actual_usd IS NULL "
                "AND NOT (settled=1 AND dispatched=1 AND admission_kind='verified_provider_bound' "
                "AND charge_status IN ('upper_bound','reviewed_retained')) LIMIT 1",
                (run_id,),
            ).fetchone()
            if unresolved is None:
                conn.execute(
                    "UPDATE budget_runs SET halt_reason=NULL WHERE id=? AND halt_reason='provider_charge_unknown'",
                    (run_id,),
                )
        return self.snapshot(run_id)

    def halt(self, run_id, reason):
        if reason != "local_accounting_incomplete":
            raise ValueError("Unsupported local halt reason")
        with self._transaction() as conn:
            conn.execute(
                "UPDATE budget_runs SET halt_reason=COALESCE(halt_reason,?) WHERE id=?",
                (reason, run_id),
            )

    def close_run(self, run_id):
        with self._transaction() as conn:
            run = conn.execute("SELECT id FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Unknown run budget")
            conn.execute("UPDATE budget_runs SET status='closed' WHERE id=?", (run_id,))
        return self.snapshot(run_id)

    def snapshot(self, run_id):
        with self._transaction() as conn:
            run = conn.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Unknown run budget")
            attempts = list(conn.execute("SELECT * FROM budget_attempts WHERE run_id=?", (run_id,)))
            charged = self._charged(conn, run_id)
            known = sum(
                (money(row["actual_usd"]) for row in attempts if row["actual_usd"] is not None),
                Decimal(0),
            )
            unknown = sum(row["actual_usd"] is None for row in attempts)
            actual_mode = run["budget_mode"] == "actual_usage"
            bounded = sum(row["charge_status"] == "upper_bound" for row in attempts)
            reviewed = sum(row["charge_status"] == "reviewed_retained" for row in attempts)
            unresolved = sum(
                row["actual_usd"] is None
                and not (
                    row["settled"]
                    and row["dispatched"]
                    and row["admission_kind"] == "verified_provider_bound"
                    and row["charge_status"] in {"upper_bound", "reviewed_retained"}
                )
                for row in attempts
            )
            billing_complete = (
                not unresolved
                and not run["halt_reason"]
                and all(row["settled"] for row in attempts)
            )
            settled_bound = sum(
                (
                    money(row["charged_usd"])
                    for row in attempts
                    if row["actual_usd"] is None
                    and row["settled"]
                    and row["charge_status"] in {"upper_bound", "reviewed_retained"}
                ),
                Decimal(0),
            )
            stop_charge = known + settled_bound
            run_reached = actual_mode and stop_charge >= money(run["limit_usd"])
            run_exceeded = actual_mode and stop_charge > money(run["limit_usd"])
            run_basis = "conservative_bound" if bounded or reviewed else "actual_usage"
            return {
                "run_id": run_id,
                "limit_usd": run["limit_usd"],
                "run_budget_mode": run["budget_mode"],
                "shared_pool_requires_provider_bounds": self._strict_pool(conn),
                "run_limit_basis": run_basis if actual_mode else "attempt_reservations",
                "run_budget_basis": run_basis,
                "billing_complete": billing_complete,
                "conservative_total_usd": str(charged) if billing_complete else None,
                "bounded_attempts": bounded,
                "reviewed_retained_attempts": reviewed,
                "unresolved_attempts": unresolved,
                "run_budget_reached": run_reached,
                "run_budget_exceeded": run_exceeded,
                "remaining_basis": run_basis if actual_mode else "reserved_or_actual",
                "conservative_charge_usd": str(charged),  # Legacy alias, not a provider guarantee.
                "reserved_or_actual_usd": str(charged),
                "contains_local_estimate": any(
                    row["admission_kind"] == "local_estimate" for row in attempts
                ),
                "known_charge_usd": str(known),
                "total_actual_usd": None if unknown else str(known),
                "unknown_attempts": unknown,
                "pending_attempts": sum(not row["settled"] for row in attempts),
                "remaining_usd": str(
                    max(
                        Decimal(0),
                        money(run["limit_usd"]) - (stop_charge if actual_mode else charged),
                    )
                ),
                "status": run["status"],
                "halt_reason": run["halt_reason"],
                "billing_bound_unresolved": run["halt_reason"] is not None,
                "dispatch_blocked": bool(
                    unresolved
                    or run_reached
                    or conn.execute(
                        "SELECT 1 FROM budget_runs WHERE halt_reason IS NOT NULL LIMIT 1"
                    ).fetchone()
                    or conn.execute(
                        "SELECT 1 FROM budget_attempts WHERE actual_usd IS NULL AND NOT "
                        "(settled=1 AND dispatched=1 AND admission_kind='verified_provider_bound' "
                        "AND charge_status IN ('upper_bound','reviewed_retained')) LIMIT 1"
                    ).fetchone()
                ),
            }
