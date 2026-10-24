"""Persistent, conservative dollar reservations; unknown charges never become zero."""

import sqlite3
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

_INITIALIZATION_TIMEOUT_SECONDS = 30.0
_INITIALIZATION_RETRY_SECONDS = 0.05


class BudgetExceeded(RuntimeError):
    pass


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
    """Reserve whole run limits across processes, then reserve each network attempt.

    An attempt records either a provider-bound reservation or an explicit local
    estimate, never an asserted actual charge. Unknown/pending charges block further
    dispatch across this ledger. An abandoned run retains its reservation for review.
    """

    def __init__(self, path, *, daily_limit="12", total_limit=None, day=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit = money(daily_limit)
        self.total_limit = None if total_limit is None else money(total_limit)
        self.day = day or datetime.now(UTC).date().isoformat()
        with self._transaction() as conn:
            # Each statement remains inside the same BEGIN IMMEDIATE migration transaction.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budget_runs (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, limit_usd TEXT NOT NULL,
                    status TEXT NOT NULL, halt_reason TEXT
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
            conn.execute("""UPDATE budget_runs SET halt_reason='provider_charge_unknown'
                WHERE halt_reason IS NULL AND id IN (
                    SELECT run_id FROM budget_attempts
                    WHERE settled=1 AND actual_usd IS NULL AND dispatched=1
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
            "AND (? IS NULL OR id != ?) LIMIT 1",
            (excluding, excluding),
        ).fetchone():
            raise BudgetExceeded("Pending or unknown provider charge blocks further calls")

    def open_run(self, run_id, run_limit):
        limit = money(run_limit)
        if not run_id or limit <= 0:
            raise ValueError("A run needs a nonempty ID and positive budget")
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM budget_runs WHERE id=?", (run_id,)).fetchone():
                raise ValueError("Run budget already exists; do not silently reset it")
            self._require_clear(conn)
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
                "INSERT INTO budget_runs VALUES (?,?,?,?,?)",
                (run_id, self.day, str(limit), "open", None),
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
            self._require_clear(conn)
            if self._charged(conn, run_id) + upper > money(run["limit_usd"]):
                raise BudgetExceeded("Run budget cannot reserve the next model attempt")
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
            run = conn.execute("SELECT status FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if run is None or run["status"] != "open":
                raise BudgetExceeded("Run budget is closed or missing before dispatch")
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
                "UPDATE budget_attempts SET charged_usd='0',actual_usd='0',settled=1 "
                "WHERE id=? AND run_id=? AND dispatched=0 AND settled=0",
                (attempt_id, run_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("A dispatched or settled attempt cannot be released")

    def settle(self, run_id, attempt_id, actual_usd, *, bound_invalid=False):
        actual = None if actual_usd is None else money(actual_usd)
        exceeded = False
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
                "UPDATE budget_attempts SET actual_usd=?,charged_usd=?,settled=1 WHERE id=?",
                (None if actual is None else str(actual), str(charge), attempt_id),
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
        if exceeded or bound_invalid:
            raise BudgetExceeded("Provider billing requires review; further calls stopped")

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
            return {
                "run_id": run_id,
                "limit_usd": run["limit_usd"],
                "conservative_charge_usd": str(charged),  # Legacy alias, not a provider guarantee.
                "reserved_or_actual_usd": str(charged),
                "contains_local_estimate": any(
                    row["admission_kind"] == "local_estimate" for row in attempts
                ),
                "known_charge_usd": str(known),
                "total_actual_usd": None if unknown else str(known),
                "unknown_attempts": unknown,
                "pending_attempts": sum(not row["settled"] for row in attempts),
                "remaining_usd": str(max(Decimal(0), money(run["limit_usd"]) - charged)),
                "status": run["status"],
                "halt_reason": run["halt_reason"],
                "billing_bound_unresolved": run["halt_reason"] is not None,
                "dispatch_blocked": bool(
                    unknown
                    or conn.execute(
                        "SELECT 1 FROM budget_runs WHERE halt_reason IS NOT NULL LIMIT 1"
                    ).fetchone()
                    or conn.execute(
                        "SELECT 1 FROM budget_attempts WHERE actual_usd IS NULL LIMIT 1"
                    ).fetchone()
                ),
            }
