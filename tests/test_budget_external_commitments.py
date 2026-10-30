"""Donor encumbrances block reuse without becoming model runs or charges."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from headroom.budget import BudgetExceeded, BudgetLedger

RECEIPT = "a" * 64


def history(path):
    with sqlite3.connect(path) as conn:
        return {
            name: conn.execute(f"SELECT * FROM {name} ORDER BY id").fetchall()
            for name in ("budget_runs", "budget_attempts")
        }


@pytest.mark.parametrize(
    "hold,actual,total",
    [
        ("1.588313628", "0.411686372", "2"),
        ("3.612190772", "1.387809228", "5"),
    ],
)
def test_donors_cannot_spend_transferred_funds_and_actual_history_is_unchanged(
    tmp_path, hold, actual, total
):
    path = tmp_path / "donor.db"
    ledger = BudgetLedger(path, total_limit=total, daily_limit=total)
    ledger.open_run("old", total)
    ledger.reserve("old", "old-attempt", actual)
    ledger.settle("old", "old-attempt", actual)
    old_snapshot = ledger.close_run("old")
    old_history = history(path)
    record = ledger.encumber("approved-transfer", hold, RECEIPT)
    assert record["amount_usd"] == hold
    assert ledger.committed_hold_usd == Decimal(hold)
    assert history(path) == old_history
    assert ledger.snapshot("old") == old_snapshot
    assert ledger.snapshot("old")["total_actual_usd"] == actual
    with pytest.raises(BudgetExceeded):
        ledger.open_run("reuse", "0.000000001")
    reopened = BudgetLedger(path, total_limit=total, daily_limit=total, require_existing=True)
    assert reopened.committed_hold_usd == Decimal(hold)
    with pytest.raises(BudgetExceeded):
        reopened.open_run("reuse-after-reopen", "0.000000001")


@pytest.mark.parametrize("limit_kind", ["total", "daily"])
def test_reserve_counts_holds_beyond_an_actual_usage_run_floor(tmp_path, limit_kind):
    ledger = BudgetLedger(
        tmp_path / "ledger.db",
        total_limit="1" if limit_kind == "total" else "10",
        daily_limit="1" if limit_kind == "daily" else "10",
    )
    ledger.encumber("transfer", "0.6", RECEIPT)
    ledger.open_run("remaining", "0.1", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("remaining", "too-large", "0.5")
    assert ledger.snapshot("remaining")["pending_attempts"] == 0
    ledger.close_run("remaining")
    assert ledger.committed_hold_usd == Decimal("0.6")


def test_daily_hold_never_expires_or_releases_when_a_run_closes(tmp_path, monkeypatch):
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-10-30")
    path = tmp_path / "ledger.db"
    ledger = BudgetLedger(path, daily_limit="1", total_limit="10")
    ledger.encumber("transfer", "0.6", RECEIPT)
    ledger.open_run("small", "0.4")
    ledger.close_run("small")
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-10-31")
    tomorrow = BudgetLedger(path, daily_limit="1", total_limit="10")
    with pytest.raises(BudgetExceeded):
        tomorrow.open_run("new-day", "0.400000001")
    assert tomorrow.committed_hold_usd == Decimal("0.6")


@pytest.mark.parametrize("state", ["active", "pending", "unknown", "halted"])
def test_uncertain_or_active_donor_state_refuses_encumbrance(tmp_path, state):
    ledger = BudgetLedger(tmp_path / "ledger.db", daily_limit="2", total_limit="2")
    ledger.open_run("old", "0.5")
    if state in {"pending", "unknown"}:
        ledger.reserve("old", "attempt", "0.1")
        if state == "unknown":
            ledger.settle("old", "attempt", None)
    if state == "halted":
        ledger.halt("old", "local_accounting_incomplete")
    if state != "active":
        ledger.close_run("old")
    before = history(ledger.path)
    with pytest.raises(BudgetExceeded):
        ledger.encumber("transfer", "0.1", RECEIPT)
    assert ledger.committed_hold_usd == 0
    assert history(ledger.path) == before


def test_reviewed_conservative_bound_is_counted_without_inventing_actual(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.db", daily_limit="1", total_limit="1")
    ledger.open_run("old", "0.5")
    ledger.reserve("old", "attempt", "0.1")
    ledger.settle_upper_bound("old", "attempt", "0.08", basis="verified_tariff_missing_cache_count")
    before = ledger.close_run("old")
    ledger.encumber("transfer", "0.92", RECEIPT)
    assert ledger.snapshot("old") == before
    assert before["total_actual_usd"] is None
    assert before["conservative_total_usd"] == "0.08"
    with pytest.raises(BudgetExceeded):
        ledger.open_run("reuse", "0.0001")


def test_duplicate_receipts_and_sql_mutation_cannot_release_a_hold(tmp_path):
    ledger = BudgetLedger(tmp_path / "ledger.db", daily_limit="3", total_limit="3")
    record = ledger.encumber("transfer", "1", RECEIPT)
    for transfer, receipt in [("transfer", RECEIPT), ("transfer", "b" * 64), ("other", RECEIPT)]:
        with pytest.raises(ValueError):
            ledger.encumber(transfer, "0.5", receipt)
    for sql in [
        "UPDATE budget_external_commitments SET amount_usd='0'",
        "DELETE FROM budget_external_commitments",
    ]:
        with sqlite3.connect(ledger.path) as conn, pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)
    rows = ledger.external_commitments()
    assert rows == [record]
    rows[0]["amount_usd"] = "0"
    assert ledger.committed_hold_usd == Decimal(1)
    assert ledger.external_commitments() == [record]


def test_encumber_and_open_run_share_atomic_donor_admission(tmp_path):
    path = tmp_path / "ledger.db"
    BudgetLedger(path, daily_limit="1", total_limit="1")

    def enter(kind):
        ledger = BudgetLedger(path, daily_limit="1", total_limit="1")
        try:
            if kind == "hold":
                ledger.encumber("transfer", "0.6", RECEIPT)
            else:
                ledger.open_run("new", "0.6")
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(enter, ["hold", "run"])) == 1


def test_target_ledger_is_isolated_and_legacy_schema_migrates_without_rewriting_history(tmp_path):
    donor_path = tmp_path / "legacy.db"
    with sqlite3.connect(donor_path) as conn:
        conn.execute(
            "CREATE TABLE budget_runs (id TEXT PRIMARY KEY, day TEXT NOT NULL, limit_usd TEXT NOT NULL, status TEXT NOT NULL, halt_reason TEXT)"
        )
        conn.execute(
            "CREATE TABLE budget_attempts (id TEXT PRIMARY KEY, run_id TEXT NOT NULL, upper_usd TEXT NOT NULL, charged_usd TEXT NOT NULL, actual_usd TEXT, settled INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO budget_runs VALUES ('legacy','2026-10-29','0.5','closed',NULL)")
        conn.execute("INSERT INTO budget_attempts VALUES ('old','legacy','0.1','0.03','0.03',1)")
    donor = BudgetLedger(donor_path, daily_limit="2", total_limit="2", require_existing=True)
    before = history(donor_path)
    donor.encumber("transfer", "1.588313628", RECEIPT)
    donor_after = history(donor_path)
    assert donor_after == before
    assert donor.snapshot("legacy")["total_actual_usd"] == "0.03"
    target = BudgetLedger(
        tmp_path / "target.db", daily_limit="5.200504400", total_limit="5.200504400"
    )
    assert target.external_commitments() == []
    target.open_run("separate", "0.1")
    target.reserve("separate", "target-attempt", "0.1")
    target.settle("separate", "target-attempt", "0.02")
    target.close_run("separate")
    assert history(donor_path) == donor_after
    assert donor.committed_hold_usd == Decimal("1.588313628")


@pytest.mark.parametrize(
    "transfer,amount,receipt",
    [
        ("", "1", RECEIPT),
        ("bad identity", "1", RECEIPT),
        ("t", "0", RECEIPT),
        ("t", "-1", RECEIPT),
        ("t", "1", "not-a-hash"),
    ],
)
def test_invalid_commitment_has_no_side_effect(tmp_path, transfer, amount, receipt):
    ledger = BudgetLedger(tmp_path / "ledger.db", daily_limit="2", total_limit="2")
    with pytest.raises(ValueError):
        ledger.encumber(transfer, amount, receipt)
    assert ledger.external_commitments() == []


@pytest.mark.parametrize("total,daily", [(None, "1"), ("0", "1"), ("1", "0")])
def test_encumber_requires_finite_positive_authorized_pools(tmp_path, total, daily):
    ledger = BudgetLedger(tmp_path / "ledger.db", total_limit=total, daily_limit=daily)
    with pytest.raises(BudgetExceeded):
        ledger.encumber("transfer", "0.1", RECEIPT)
    assert ledger.external_commitments() == []


def test_old_ledger_day_cannot_bypass_current_day_commitment_check(tmp_path, monkeypatch):
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-10-30")
    ledger = BudgetLedger(tmp_path / "ledger.db", daily_limit="1", total_limit="1")
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-10-31")
    with pytest.raises(BudgetExceeded):
        ledger.encumber("transfer", "0.1", RECEIPT)
    assert ledger.external_commitments() == []
