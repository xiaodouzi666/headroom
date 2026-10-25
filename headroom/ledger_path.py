"""Explicit existing-ledger selection; no new funding or default-path change.

Checks reject symlinks and noncanonical paths before opening SQLite. They are
not an atomic nofollow open: a trusted operator can still replace a component
between Python validation and SQLite open. Execution qualification must bind the
canonical intended ledger and its history independently.
"""

import os
import sqlite3
import stat
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

BUDGET_DB_ENV = "HEADROOM_BUDGET_DB_PATH"
_REQUIRED_COLUMNS = {
    "budget_runs": {"id", "day", "limit_usd", "status", "halt_reason"},
    "budget_attempts": {"id", "run_id", "upper_usd", "charged_usd", "actual_usd", "settled"},
}


class LedgerPathError(ValueError):
    """Redacted refusal; never silently choose a different ledger."""


def validate_ledger_schema(connection):
    """Require existing core tables before any initialization/migration writes."""
    for table, required in _REQUIRED_COLUMNS.items():
        row = connection.execute("SELECT type FROM sqlite_schema WHERE name=?", (table,)).fetchone()
        if row is None or row[0] != "table":
            raise LedgerPathError("Shared budget database is not an initialized ledger")
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not required <= columns:
            raise LedgerPathError("Shared budget database is not an initialized ledger")


def validate_existing_ledger_path(value, *, expected_identity=None):
    """Validate canonical existing regular paths, without creating a database."""
    try:
        raw = os.fspath(value)
        if not isinstance(raw, str) or not raw or raw.strip() != raw:
            raise LedgerPathError("Shared budget database requires a canonical absolute path")
        path = Path(raw)
        if not path.is_absolute() or str(path) != raw:
            raise LedgerPathError("Shared budget database requires a canonical absolute path")
        for component in (*reversed(path.parents), path):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise LedgerPathError("Shared budget database paths cannot contain symlinks")
            if component != path and not stat.S_ISDIR(info.st_mode):
                raise LedgerPathError("Shared budget database parent must be a directory")
        if not stat.S_ISREG(path.lstat().st_mode) or path.resolve(strict=True) != path:
            raise LedgerPathError("Shared budget database must be an existing regular file")
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = path.with_name(path.name + suffix)
            try:
                info = sidecar.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode):
                raise LedgerPathError(
                    "Shared budget database sidecar must be regular and nonsymlink"
                )
        if expected_identity is not None and existing_file_identity(path) != expected_identity:
            raise LedgerPathError("Shared budget database file identity changed")
        return path
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, LedgerPathError):
            raise
        raise LedgerPathError("Shared budget database path is unavailable") from None


def existing_file_identity(path):
    try:
        info = Path(path).lstat()
        if not stat.S_ISREG(info.st_mode):
            raise LedgerPathError("Shared budget database is not a regular file")
        return info.st_dev, info.st_ino
    except OSError:
        raise LedgerPathError("Shared budget database identity is unavailable") from None


def require_initialized_ledger(path, *, expected_identity=None):
    path = validate_existing_ledger_path(path, expected_identity=expected_identity)
    identity = expected_identity if expected_identity is not None else existing_file_identity(path)
    try:
        with closing(
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
        ) as connection:
            validate_existing_ledger_path(path, expected_identity=identity)
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            validate_ledger_schema(connection)
    except sqlite3.Error:
        raise LedgerPathError("Shared budget database schema is unavailable") from None
    return path


@dataclass(frozen=True)
class BudgetDatabase:
    path: Path
    require_existing: bool = False
    file_identity: tuple[int, int] | None = None


def select_budget_database(project_root, *, environ=None, allowed_root=None):
    """Select once per runtime/service; the caller retains this immutable choice."""
    environment = os.environ if environ is None else environ
    if BUDGET_DB_ENV not in environment:
        return BudgetDatabase(Path(project_root) / ".cache/budget.db")
    path = validate_existing_ledger_path(environment[BUDGET_DB_ENV])
    if allowed_root is not None and not path.is_relative_to(Path(allowed_root).resolve()):
        raise LedgerPathError("Offline acceptance must use a fixture-owned ledger")
    identity = existing_file_identity(path)
    require_initialized_ledger(path, expected_identity=identity)
    return BudgetDatabase(path, require_existing=True, file_identity=identity)
