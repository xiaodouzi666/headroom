"""Read-only proposed runtime partition audit; never mutates the old helper.

Caller must separately bind the zero-sum external closure and the frozen cap.
No profile, ledger, funding allocation or dispatch is modified by this function.
"""

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, localcontext

LIFETIME_POOL = Decimal("14.17775754")
DAILY_POOL = Decimal("9.99964904")
CAMPAIGN_MAX = Decimal("5.4")
PER_RUN = Decimal("0.6")


def ledger_state(old, cap):
    require, money = old.require, old.money
    sha_bytes, canonical = old.sha_bytes, old.canonical
    runs, attempts = old.ledger_rows()
    require(runs and attempts, "existing shared ledger required")
    require(
        all(r["status"] == "closed" and not r["halt_reason"] for r in runs),
        "open or halted prior run",
    )
    require(all(r["settled"] == 1 for r in attempts), "pending prior attempt")
    for row in attempts:
        charge, upper = money(row["charged_usd"]), money(row["upper_usd"])
        require(charge <= upper, "provider bound violation")
        if row["charge_status"] == "exact":
            require(
                row["actual_usd"] is not None and money(row["actual_usd"]) == charge,
                "exact charge drift",
            )
        else:
            require(
                row["charge_status"] in {"upper_bound", "reviewed_retained"}
                and row["actual_usd"] is None
                and row["dispatched"] == 1
                and row["admission_kind"] == "verified_provider_bound",
                "unknown prior charge has no verified retained bound",
            )
    baseline = cap["ledger"]
    projection = sha_bytes(canonical({"runs": runs, "attempts": attempts}))
    require(
        projection == baseline["projection_sha256"]
        and len(runs) == baseline["runs"]
        and len(attempts) == baseline["attempts"],
        "history changed or extra unreviewed calls; no components excluded",
    )
    with localcontext() as context:
        context.prec = 256
        charged = sum((money(row["charged_usd"]) for row in attempts), Decimal(0))
        known = sum(
            (money(row["actual_usd"]) for row in attempts if row["actual_usd"] is not None),
            Decimal(0),
        )
        require(
            charged == money(baseline["conservative_charged_usd"])
            and known == money(baseline["known_actual_subtotal_usd"]),
            "historical totals changed",
        )
        today = datetime.now(UTC).date().isoformat()
        today_ids = {r["id"] for r in runs if r["day"] == today}
        today_charge = sum(
            (money(r["charged_usd"]) for r in attempts if r["run_id"] in today_ids), Decimal(0)
        )
        remaining, daily_remaining = LIFETIME_POOL - charged, DAILY_POOL - today_charge
        effective = min(CAMPAIGN_MAX, remaining, daily_remaining)
        require(effective >= PER_RUN, "balance cannot reserve the original next-case 0.6 floor")
    return {
        "utc_day": today,
        "settled_attempts": len(attempts),
        "closed_runs": len(runs),
        "projection_sha256": projection,
        "history_exclusions": [],
        "known_subtotal_usd": str(known),
        "actual_total_usd": None,
        "conservative_usd": str(charged),
        "remaining_all_time_usd": str(remaining),
        "remaining_day_usd": str(daily_remaining),
        "day_conservative_usd": str(today_charge),
        "effective_campaign_usd": str(effective),
        "campaign_max_usd": str(CAMPAIGN_MAX),
        "all_time_limit_usd": str(LIFETIME_POOL),
        "daily_limit_usd": str(DAILY_POOL),
        "charge_status_counts": dict(Counter(r["charge_status"] for r in attempts)),
        "no_pending_unresolved_halted": True,
        "utc_rollover_does_not_reset_all_time_pool": True,
        "next_case_requires_original_0_6_floor": True,
        "each_POST_requires_full_provider_bound": True,
    }
