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
