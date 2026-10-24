"""Deterministic initialization retries; no transaction body may be replayed."""

import sqlite3
from types import SimpleNamespace

import pytest

import headroom.budget as module
from headroom.budget import BudgetLedger


def sqlite_error(code):
    error = sqlite3.OperationalError("fixture database error")
    error.sqlite_errorcode = code
    return error


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        assert delay > 0
        self.sleeps.append(delay)
        self.now += delay


class Connection:
    def __init__(self, *, error=None, stage="PRAGMA journal_mode=WAL", clock=None, wait=0):
        self.error, self.stage, self.clock, self.wait = error, stage, clock, wait
        self.in_transaction = False
        self.closed = False
        self.rollbacks = self.commits = 0
        self.busy_seconds = 0
        self.sql = []

    def execute(self, sql):
        self.sql.append(sql)
        if sql.startswith("PRAGMA busy_timeout="):
            self.busy_seconds = int(sql.split("=")[1]) / 1000
        if sql == "BEGIN IMMEDIATE":
            self.in_transaction = True
        if sql == self.stage and self.error is not None:
            if self.clock:
                self.clock.now += min(self.wait, self.busy_seconds)
            raise self.error
        return self

    def rollback(self):
        self.rollbacks += 1
        self.in_transaction = False

    def commit(self):
        self.commits += 1
        if self.stage == "commit" and self.error is not None:
            raise self.error
        self.in_transaction = False

    def close(self):
        self.closed = True


def harness(tmp_path, monkeypatch, connections, clock=None):
    clock = clock or Clock()
    monkeypatch.setattr(
        module, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
    )
    opened, timeouts = [], []

    def connect(path, *, timeout, isolation_level):
        assert all(conn.closed for conn in opened), "Retry must close the prior connection"
        assert timeout > 0 and isolation_level is None
        conn = connections[len(opened)]
        opened.append(conn)
        timeouts.append(timeout)
        return conn

    monkeypatch.setattr(module.sqlite3, "connect", connect)
    ledger = object.__new__(BudgetLedger)
    ledger.path = tmp_path / "fixture.db"
    return ledger, clock, opened, timeouts


@pytest.mark.parametrize("stage", ["PRAGMA journal_mode=WAL", "BEGIN IMMEDIATE"])
@pytest.mark.parametrize(
    "code", [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY | (2 << 8)]
)
def test_only_initialization_busy_or_locked_retries_on_fresh_connection(
    tmp_path, monkeypatch, stage, code
):
    first = Connection(error=sqlite_error(code), stage=stage)
    second = Connection()
    ledger, clock, opened, timeouts = harness(tmp_path, monkeypatch, [first, second])
    bodies = 0
    with ledger._transaction() as conn:
        bodies += 1
        assert conn is second and first.closed
    assert bodies == 1 and len(opened) == 2
    assert first.rollbacks == int(stage == "BEGIN IMMEDIATE")
    assert second.commits == 1 and second.closed
    assert clock.sleeps == [0.05] and timeouts[1] < timeouts[0]


@pytest.mark.parametrize(
    "error",
    [
        sqlite_error(sqlite3.SQLITE_ERROR),
        sqlite_error(sqlite3.SQLITE_CORRUPT),
        sqlite3.OperationalError("database is locked"),  # Message alone is insufficient evidence.
        KeyboardInterrupt(),
        SystemExit(3),
        ValueError("fixture argument error"),
    ],
)
def test_other_initialization_errors_and_interrupts_are_preserved(tmp_path, monkeypatch, error):
    failed = Connection(error=error)
    ledger, clock, opened, _ = harness(tmp_path, monkeypatch, [failed])
    with pytest.raises(type(error)) as caught, ledger._transaction():
        pytest.fail("Initialization failed; body must not run")
    assert caught.value is error
    assert len(opened) == 1 and failed.closed and clock.sleeps == []


@pytest.mark.parametrize("where", ["body", "commit"])
def test_busy_after_yield_is_never_retried(tmp_path, monkeypatch, where):
    error = sqlite_error(sqlite3.SQLITE_BUSY)
    conn = Connection(error=error, stage="commit") if where == "commit" else Connection()
    ledger, clock, opened, _ = harness(tmp_path, monkeypatch, [conn])
    bodies = 0
    with pytest.raises(sqlite3.OperationalError) as caught, ledger._transaction():
        bodies += 1
        if where == "body":
            raise error
    assert caught.value is error and bodies == 1 and len(opened) == 1
    assert conn.closed and conn.rollbacks == 1 and clock.sleeps == []


def test_retry_deadline_includes_sqlite_wait_and_closes_every_failed_connection(
    tmp_path, monkeypatch
):
    clock = Clock()
    error = sqlite_error(sqlite3.SQLITE_BUSY)
    connections = [Connection(error=error, clock=clock, wait=0.04) for _ in range(3)]
    ledger, _, opened, timeouts = harness(tmp_path, monkeypatch, connections, clock)
    monkeypatch.setattr(module, "_INITIALIZATION_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(module, "_INITIALIZATION_RETRY_SECONDS", 0.03)
    with pytest.raises(sqlite3.OperationalError) as caught, ledger._transaction():
        pytest.fail("Busy connection must never reach transaction body")
    assert caught.value is error and clock.now == pytest.approx(0.1)
    assert len(opened) <= 3 and all(conn.closed for conn in opened)
    assert timeouts[0] == pytest.approx(0.1) and timeouts[1] <= 0.03
    assert sum(clock.sleeps) <= 0.031


def test_successful_setup_still_checks_elapsed_initialization_deadline(tmp_path, monkeypatch):
    clock = Clock()
    conn = Connection()
    original = conn.execute

    def slow(sql):
        result = original(sql)
        if sql == "PRAGMA journal_mode=WAL":
            clock.now += 1
        return result

    conn.execute = slow
    ledger, _, opened, _ = harness(tmp_path, monkeypatch, [conn], clock)
    monkeypatch.setattr(module, "_INITIALIZATION_TIMEOUT_SECONDS", 0.1)
    with pytest.raises(TimeoutError), ledger._transaction():
        pytest.fail("Elapsed deadline must stop before the body")
    assert len(opened) == 1 and conn.closed and clock.sleeps == []
