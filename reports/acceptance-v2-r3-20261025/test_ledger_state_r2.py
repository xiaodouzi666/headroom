"""Synthetic-only checks for the proposed read-only lifetime/day split."""

import copy
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "r2_finance_draft", Path(__file__).with_name("ledger_state_r2.py")
)
draft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(draft)


class FixedDate(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 25, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(draft, "datetime", FixedDate)


def fixture(entries):
    runs, attempts = [], []
    for i, (day, charge, status) in enumerate(entries):
        run = f"run-{i}"
        runs.append({"id": run, "day": day, "status": "closed", "halt_reason": None})
        attempts.append(
            {
                "id": f"attempt-{i}",
                "run_id": run,
                "upper_usd": charge,
                "charged_usd": charge,
                "actual_usd": charge if status == "exact" else None,
                "settled": 1,
                "charge_status": status,
                "dispatched": 1,
                "admission_kind": "verified_provider_bound",
            }
        )

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def money(value):
        require(type(value) in (str, int), "money type")
        value = Decimal(value)
        require(value.is_finite() and value >= 0, "money value")
        return value

    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

    def sha_bytes(value):
        return hashlib.sha256(value).hexdigest()

    old = SimpleNamespace(
        POOL=Decimal("9.99964904"),
        CAMPAIGN_MAX=Decimal("5.4"),
        PER_RUN=Decimal("0.6"),
        require=require,
        money=money,
        canonical=canonical,
        sha_bytes=sha_bytes,
        ledger_rows=lambda: copy.deepcopy((runs, attempts)),
    )
    cap = {
        "ledger": {
            "projection_sha256": sha_bytes(canonical({"runs": runs, "attempts": attempts})),
            "runs": len(runs),
            "attempts": len(attempts),
            "conservative_charged_usd": str(
                sum((money(a["charged_usd"]) for a in attempts), Decimal(0))
            ),
            "known_actual_subtotal_usd": str(
                sum(
                    (money(a["actual_usd"]) for a in attempts if a["actual_usd"] is not None),
                    Decimal(0),
                )
            ),
        }
    }
    return old, cap, runs, attempts


def test_lifetime_partition_changes_without_changing_daily_or_old_globals():
    old, cap, runs, attempts = fixture([("2026-10-24", "8", "exact"), ("2026-10-25", "2", "exact")])
    before = copy.deepcopy((cap, runs, attempts))
    value = draft.ledger_state(old, cap)
    assert value["conservative_usd"] == "10"
    assert value["remaining_all_time_usd"] == "4.17775754"
    assert value["remaining_day_usd"] == "7.99964904"
    assert value["effective_campaign_usd"] == "4.17775754"
    assert value["all_time_limit_usd"] == "14.17775754"
    assert value["daily_limit_usd"] == "9.99964904"
    assert value["history_exclusions"] == []
    assert (cap, runs, attempts) == before
    assert old.POOL == Decimal("9.99964904") and old.CAMPAIGN_MAX == Decimal("5.4")
    assert draft.LIFETIME_POOL + Decimal("1.82224246") == Decimal(16)


def test_independent_daily_floor_still_refuses():
    old, cap, _, _ = fixture([("2026-10-25", "9.5", "exact")])
    with pytest.raises(ValueError, match="0.6 floor"):
        draft.ledger_state(old, cap)


def test_exact_daily_floor_is_available():
    old, cap, _, _ = fixture([("2026-10-25", "9.39964904", "exact")])
    value = draft.ledger_state(old, cap)
    assert value["effective_campaign_usd"] == "0.60000000"


def test_new_day_never_resets_lifetime():
    old, cap, _, _ = fixture([("2026-10-24", "13.6", "exact")])
    with pytest.raises(ValueError, match="0.6 floor"):
        draft.ledger_state(old, cap)


def test_reviewed_unknowns_are_retained_not_released_or_called_actual():
    old, cap, _, _ = fixture(
        [
            ("2026-10-24", "1.049344", "reviewed_retained"),
            ("2026-10-25", "0.01644864", "upper_bound"),
        ]
    )
    value = draft.ledger_state(old, cap)
    assert value["known_subtotal_usd"] == "0"
    assert value["actual_total_usd"] is None
    assert value["conservative_usd"] == "1.06579264"
    assert value["charge_status_counts"] == {"reviewed_retained": 1, "upper_bound": 1}


@pytest.mark.parametrize(
    "field,value",
    [
        ("settled", 0),
        ("charged_usd", "2"),
        ("actual_usd", "0.5"),
        ("charge_status", "unknown"),
        ("actual_usd", None),
    ],
)
def test_changed_or_unsettled_attempt_fails(field, value):
    old, cap, _, attempts = fixture([("2026-10-25", "1", "exact")])
    attempts[0][field] = value
    with pytest.raises(ValueError):
        draft.ledger_state(old, cap)


@pytest.mark.parametrize("field,value", [("status", "open"), ("halt_reason", "unknown charge")])
def test_open_or_halted_run_fails(field, value):
    old, cap, runs, _ = fixture([("2026-10-25", "1", "exact")])
    runs[0][field] = value
    with pytest.raises(ValueError, match="open or halted"):
        draft.ledger_state(old, cap)


@pytest.mark.parametrize(
    "field,value",
    [
        ("dispatched", 0),
        ("admission_kind", "local_estimate"),
        ("actual_usd", "0"),
    ],
)
def test_unknown_without_reviewed_bound_fails(field, value):
    old, cap, _, attempts = fixture([("2026-10-25", "1", "upper_bound")])
    attempts[0][field] = value
    with pytest.raises(ValueError, match="unknown prior charge"):
        draft.ledger_state(old, cap)


def test_unreviewed_new_attempt_and_same_total_metadata_drift_fail():
    old, cap, _, attempts = fixture([("2026-10-25", "1", "exact")])
    attempts[0]["id"] = "changed-id"
    with pytest.raises(ValueError, match="history changed"):
        draft.ledger_state(old, cap)
    attempts.append(dict(attempts[0], id="extra", charged_usd="0", actual_usd="0"))
    with pytest.raises(ValueError, match="history changed"):
        draft.ledger_state(old, cap)


def test_frozen_totals_cannot_disagree_with_full_projection():
    old, cap, _, _ = fixture([("2026-10-25", "1", "exact")])
    cap["ledger"]["known_actual_subtotal_usd"] = "0"
    with pytest.raises(ValueError, match="historical totals"):
        draft.ledger_state(old, cap)
