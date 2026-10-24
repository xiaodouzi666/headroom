"""Persistent, conservative dollar reservations; unknown charges never become zero."""

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path


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

    A caller must supply a verified maximum billable cost before an attempt. This
    ledger cannot prove provider pricing/token ceilings; unknown bounds must never
    be passed as zero. An abandoned open run retains its reservation until reviewed.
    """

    def __init__(self, path, *, daily_limit="12", total_limit=None, day=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit = money(daily_limit)
        self.total_limit = None if total_limit is None else money(total_limit)
        self.day = day or datetime.now(UTC).date().isoformat()
        with self._transaction() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS budget_runs (
                    id TEXT PRIMARY KEY, day TEXT NOT NULL, limit_usd TEXT NOT NULL,
                    status TEXT NOT NULL, halt_reason TEXT
                );
                CREATE TABLE IF NOT EXISTS budget_attempts (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES budget_runs(id),
                    upper_usd TEXT NOT NULL, charged_usd TEXT NOT NULL,
                    actual_usd TEXT, settled INTEGER NOT NULL DEFAULT 0
                );
            """)

    @contextmanager
    def _transaction(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            with localcontext() as context:
                # money accepts 80-digit coefficients with exponents in [-80,80].
                # 256 digits also preserve sums across their full magnitude span.
                context.prec = 256
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN IMMEDIATE")
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

    def open_run(self, run_id, run_limit):
        limit = money(run_limit)
        if not run_id or limit <= 0:
            raise ValueError("A run needs a nonempty ID and positive budget")
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM budget_runs WHERE id=?", (run_id,)).fetchone():
                raise ValueError("Run budget already exists; do not silently reset it")
            if conn.execute(
                "SELECT 1 FROM budget_runs WHERE halt_reason IS NOT NULL LIMIT 1"
            ).fetchone():
                raise BudgetExceeded("Unresolved provider billing requires review before new runs")
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

    def reserve(self, run_id, attempt_id, upper_usd):
        upper = money(upper_usd)
        with self._transaction() as conn:
            run = conn.execute("SELECT * FROM budget_runs WHERE id=?", (run_id,)).fetchone()
            if run is None:
                raise ValueError("Run budget was not opened")
            if run["status"] != "open" or run["halt_reason"]:
                raise BudgetExceeded("Run budget is closed or halted")
            if self._charged(conn, run_id) + upper > money(run["limit_usd"]):
                raise BudgetExceeded("Run budget cannot reserve the next model attempt")
            if conn.execute("SELECT 1 FROM budget_attempts WHERE id=?", (attempt_id,)).fetchone():
                raise ValueError("Attempt reservation already exists")
            conn.execute(
                "INSERT INTO budget_attempts VALUES (?,?,?,?,?,?)",
                (attempt_id, run_id, str(upper), str(upper), None, 0),
            )

    def settle(self, run_id, attempt_id, actual_usd, *, bound_invalid=False):
        actual = None if actual_usd is None else money(actual_usd)
        exceeded = False
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT * FROM budget_attempts WHERE id=? AND run_id=?", (attempt_id, run_id)
            ).fetchone()
            if row is None or row["settled"]:
                raise ValueError("Attempt is missing or already settled")
            upper = money(row["upper_usd"])
            charge = upper if actual is None else actual
            exceeded = actual is not None and actual > upper
            conn.execute(
                "UPDATE budget_attempts SET actual_usd=?,charged_usd=?,settled=1 WHERE id=?",
                (None if actual is None else str(actual), str(charge), attempt_id),
            )
            if exceeded or bound_invalid:
                conn.execute(
                    "UPDATE budget_runs SET halt_reason=? WHERE id=?",
                    (
                        "provider_bound_unresolved" if bound_invalid else "provider_bound_exceeded",
                        run_id,
                    ),
                )
        if exceeded or bound_invalid:
            raise BudgetExceeded("Provider billing bound is unresolved; further calls stopped")

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
                "conservative_charge_usd": str(charged),
                "known_charge_usd": str(known),
                "total_actual_usd": None if unknown else str(known),
                "unknown_attempts": unknown,
                "pending_attempts": sum(not row["settled"] for row in attempts),
                "remaining_usd": str(max(Decimal(0), money(run["limit_usd"]) - charged)),
                "status": run["status"],
                "halt_reason": run["halt_reason"],
                "billing_bound_unresolved": run["halt_reason"] is not None,
            }
