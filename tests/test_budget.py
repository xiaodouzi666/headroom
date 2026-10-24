from concurrent.futures import ThreadPoolExecutor

import pytest

from headroom.budget import BudgetExceeded, BudgetLedger


def test_run_reservations_are_atomic_across_ledger_instances(tmp_path):
    path = tmp_path / "budget.db"
    BudgetLedger(path, daily_limit="0.1")

    def enter(i):
        try:
            BudgetLedger(path, daily_limit="0.1").open_run(str(i), "0.06")
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(enter, range(4))) == 1


def test_daily_budget_refuses_larger_run_before_any_attempt(tmp_path):
    b = BudgetLedger(tmp_path / "budget.db", daily_limit="0.1")
    with pytest.raises(BudgetExceeded):
        b.open_run("run", "0.6")


def test_unknown_charge_is_retained_after_close_and_reopen(tmp_path):
    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="0.1")
    b.open_run("run", "0.1")
    b.reserve("run", "attempt", "0.04")
    b.settle("run", "attempt", None)
    summary = b.close_run("run")
    assert summary["total_actual_usd"] is None
    assert summary["conservative_charge_usd"] == "0.04"
    b = BudgetLedger(path, daily_limit="0.1")
    with pytest.raises(BudgetExceeded):
        b.open_run("next", "0.07")
    with pytest.raises(BudgetExceeded):
        b.open_run("small", "0.06")


def test_attempt_gate_stops_before_next_request(tmp_path):
    b = BudgetLedger(tmp_path / "budget.db", daily_limit="1")
    b.open_run("run", "0.05")
    b.reserve("run", "one", "0.04")
    b.settle("run", "one", None)
    with pytest.raises(BudgetExceeded):
        b.reserve("run", "two", "0.02")
    assert b.snapshot("run")["unknown_attempts"] == 1


def test_exact_settlement_releases_unused_reservation(tmp_path):
    b = BudgetLedger(tmp_path / "budget.db", daily_limit="1")
    b.open_run("run", "0.05")
    b.reserve("run", "one", "0.04")
    b.settle("run", "one", "0.01")
    b.reserve("run", "two", "0.04")
    b.settle("run", "two", "0")
    assert b.close_run("run")["total_actual_usd"] == "0.01"
    with pytest.raises(ValueError):
        b.settle("run", "two", "0")


@pytest.mark.parametrize("actual,invalid", [("0.2", False), (None, True)])
def test_unresolved_provider_bound_stops_same_and_future_day(tmp_path, actual, invalid):
    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="1", day="2026-10-24")
    b.open_run("run", "0.5")
    b.reserve("run", "one", "0.1")
    with pytest.raises(BudgetExceeded):
        b.settle("run", "one", actual, bound_invalid=invalid)
    with pytest.raises(BudgetExceeded):
        b.reserve("run", "two", "0.1")
    b.close_run("run")
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path, daily_limit="1", day="2026-10-25").open_run("new", "0.1")


def test_crash_before_settlement_keeps_full_upper_bound(tmp_path):
    b = BudgetLedger(tmp_path / "budget.db", daily_limit="1")
    b.open_run("run", "0.5")
    b.reserve("run", "one", "0.2")
    state = BudgetLedger(tmp_path / "budget.db", daily_limit="1").snapshot("run")
    assert state["pending_attempts"] == 1 and state["conservative_charge_usd"] == "0.2"
    assert state["total_actual_usd"] is None


def test_total_authorization_does_not_reset_on_next_day(tmp_path):
    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="1", total_limit="0.1", day="2026-10-24")
    b.open_run("first", "0.06")
    b.reserve("first", "one", "0.06")
    b.settle("first", "one", "0.06")
    b.close_run("first")
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path, daily_limit="1", total_limit="0.1", day="2026-10-25").open_run(
            "second", "0.06"
        )


def test_budget_does_not_round_away_subcent_amount_beyond_decimal_default_precision(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.db", daily_limit="1")
    ledger.open_run("run", "0.1")
    ledger.reserve("run", "one", "0.09999999999999999999999999999")
    ledger.settle("run", "one", "0.09999999999999999999999999999")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("run", "two", "0.00000000000000000000000000002")
    assert ledger.snapshot("run")["total_actual_usd"] == "0.09999999999999999999999999999"


@pytest.mark.parametrize("kind", ["verified_provider_bound", "local_estimate"])
def test_pending_and_unknown_block_other_open_runs_and_restart(tmp_path, kind):
    path = tmp_path / "budget.db"
    a = BudgetLedger(path, daily_limit="2")
    b = BudgetLedger(path, daily_limit="2")
    a.open_run("a", "0.6")
    b.open_run("b", "0.6")
    a.reserve("a", "first", "0.04", admission_kind=kind)
    with pytest.raises(BudgetExceeded):
        b.reserve("b", "blocked", "0.01")
    with pytest.raises(BudgetExceeded):
        BudgetLedger(path, daily_limit="2").open_run("new", "0.1")
    a.settle("a", "first", None)
    with pytest.raises(BudgetExceeded):
        b.reserve("b", "still-blocked", "0.01")
    assert b.snapshot("b")["dispatch_blocked"]
    assert a.snapshot("a")["halt_reason"] == "provider_charge_unknown"


def test_competing_attempts_cannot_both_dispatch(tmp_path):
    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="2")
    for run in ("a", "b"):
        b.open_run(run, "0.6")

    def reserve(run):
        try:
            BudgetLedger(path, daily_limit="2").reserve(
                run, run, "0.04", admission_kind="local_estimate"
            )
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(reserve, ("a", "b"))) == 1


def test_only_confirmed_unsent_attempt_can_be_released_and_closed_run_cannot_dispatch(tmp_path):
    b = BudgetLedger(tmp_path / "budget.db", daily_limit="2")
    b.open_run("a", "0.6")
    b.reserve("a", "unsent", "0.04", dispatched=False)
    b.close_run("a")
    with pytest.raises(BudgetExceeded):
        b.mark_dispatched("a", "unsent")
    b.cancel_undispatched("a", "unsent")
    assert b.snapshot("a")["total_actual_usd"] == "0"
    b.open_run("b", "0.6")
    b.reserve("b", "sent", "0.04", dispatched=False)
    b.mark_dispatched("b", "sent")
    with pytest.raises(ValueError):
        b.cancel_undispatched("b", "sent")
    assert b.snapshot("b")["total_actual_usd"] is None


def test_estimate_overrun_is_committed_before_global_halt(tmp_path):
    import sqlite3

    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="2")
    b.open_run("a", "0.6")
    b.open_run("b", "0.6")
    b.reserve("a", "estimated", "0.04", admission_kind="local_estimate")
    with pytest.raises(BudgetExceeded):
        b.settle("a", "estimated", "0.7")
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT actual_usd,charged_usd,settled FROM budget_attempts").fetchone()
        halt = conn.execute("SELECT halt_reason FROM budget_runs WHERE id='a'").fetchone()[0]
    assert row == ("0.7", "0.7", 1) and halt == "estimate_reservation_exceeded"
    with pytest.raises(BudgetExceeded):
        b.reserve("b", "later", "0.01")


def test_legacy_unknown_migration_preserves_charge_and_blocks(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE budget_runs (id TEXT PRIMARY KEY,day TEXT,limit_usd TEXT,status TEXT,halt_reason TEXT);
            CREATE TABLE budget_attempts (id TEXT PRIMARY KEY,run_id TEXT,upper_usd TEXT,charged_usd TEXT,actual_usd TEXT,settled INTEGER);
            INSERT INTO budget_runs VALUES ('old','2026-10-24','0.6','closed',NULL);
            INSERT INTO budget_attempts VALUES ('old-call','old','0.04','0.04',NULL,1);
        """)
    b = BudgetLedger(path, daily_limit="2")
    assert b.snapshot("old")["conservative_charge_usd"] == "0.04"
    assert b.snapshot("old")["halt_reason"] == "provider_charge_unknown"
    with pytest.raises(BudgetExceeded):
        b.open_run("later", "0.1")
    with sqlite3.connect(path) as conn:
        row = conn.execute("SELECT admission_kind,dispatched FROM budget_attempts").fetchone()
    assert row == ("verified_provider_bound", 1)


def _reserve_in_child(path, run, go, results):
    ledger = BudgetLedger(path, daily_limit="2")
    go.wait(10)
    try:
        ledger.reserve(run, run, "0.04", admission_kind="local_estimate")
        results.put(True)
    except BudgetExceeded:
        results.put(False)


def test_estimated_dispatch_exclusion_across_processes(tmp_path):
    import multiprocessing

    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="2")
    for run in ("a", "b"):
        b.open_run(run, "0.6")
    ctx = multiprocessing.get_context("spawn")
    go, results = ctx.Event(), ctx.Queue()
    workers = [
        ctx.Process(target=_reserve_in_child, args=(path, run, go, results)) for run in ("a", "b")
    ]
    try:
        for worker in workers:
            worker.start()
        go.set()
        assert sum(results.get(timeout=15) for _ in workers) == 1
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
        results.close()
        results.join_thread()


def _migrate_in_child(path, go, results):
    go.wait(10)
    ledger = BudgetLedger(path, daily_limit="2")
    results.put(ledger.snapshot("old")["known_charge_usd"])


@pytest.mark.parametrize("_iteration", range(4))
def test_legacy_migration_is_serialized_across_processes(tmp_path, _iteration):
    import multiprocessing
    import sqlite3

    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE budget_runs (id TEXT PRIMARY KEY,day TEXT,limit_usd TEXT,status TEXT,halt_reason TEXT);
            CREATE TABLE budget_attempts (id TEXT PRIMARY KEY,run_id TEXT,upper_usd TEXT,charged_usd TEXT,actual_usd TEXT,settled INTEGER);
            INSERT INTO budget_runs VALUES ('old','2026-10-24','0.6','closed',NULL);
            INSERT INTO budget_attempts VALUES ('old-call','old','0.04','0.01','0.01',1);
        """)
    ctx = multiprocessing.get_context("spawn")
    go, results = ctx.Event(), ctx.Queue()
    workers = [ctx.Process(target=_migrate_in_child, args=(path, go, results)) for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        go.set()
        assert [results.get(timeout=15) for _ in workers] == ["0.01", "0.01"]
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(5)
        results.close()
        results.join_thread()
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT admission_kind,dispatched FROM budget_attempts").fetchone() == (
            "verified_provider_bound",
            1,
        )
