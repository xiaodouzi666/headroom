"""Updated official judging period; synthetic pools and inherited offline guard only."""

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import test_judge_binding as fixtures
from test_judge_credit import activate, extended_begin

from headroom.acceptance import judge_binding as judge
from headroom.acceptance.allocation import AllocationRefused, _budget_state
from headroom.runtime import read_live_profile

offline = fixtures.offline
pool = fixtures.pool


def _preserved_files(pool):
    directory = pool["path"].parent
    return {path: path.read_bytes() for path in directory.iterdir() if path.suffix == ".json"}


def _legacy_binding(pool, binding):
    """Build an authentic prior schema in this temporary fixture, never production."""
    old = dict(binding)
    old.pop("judging_period_policy")
    old["schema"] = judge.CREDIT_SCHEMA if "credit_extension_sha256" in old else judge.SCHEMA
    old["expires_at"] = judge.EXPIRES_AT
    old["binding_sha256"] = judge.digest(
        {key: value for key, value in old.items() if key != "binding_sha256"}
    )
    with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
        connection.execute(
            "UPDATE claims SET payload=? WHERE run_id=?",
            (json.dumps(old, sort_keys=True), old["run_id"]),
        )
    return old


@pytest.mark.parametrize("extended", [False, True])
def test_updated_period_uses_same_funding_and_immutable_files(pool, monkeypatch, extended):
    if extended:
        activate(pool)
    owner = fixtures.controller(pool)
    before = _preserved_files(pool)
    identities = {
        name: Path(pool["receipt"][name]).stat().st_ino for name in ("ledger_path", "claims_path")
    }
    limits = owner.funding_limits
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 16, tzinfo=UTC))
    assert owner.available
    assert owner.effective_expires_at == "2026-12-23T20:00:00Z"
    assert owner.receipt["expires_at"] == "2026-12-15T20:00:00Z"
    request = pool["request"].model_copy(update={"daily_budget_usd": limits["daily_limit_usd"]})
    request, binding = owner.begin("1" * 32, request, source_sha256=pool["sha"])
    assert binding["schema"] == judge.PERIOD_SCHEMA
    assert binding["judging_period_policy"] == judge.JUDGING_PERIOD_POLICY
    assert binding["expires_at"] == judge.EFFECTIVE_EXPIRES_AT
    assert binding["daily_limit_usd"] == limits["daily_limit_usd"]
    assert binding["total_limit_usd"] == limits["total_limit_usd"]
    assert Decimal(binding["run_limit_usd"]) == Decimal(".30")
    ledger = judge.judge_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    ledger.reserve(binding["run_id"], "offline", ".02", dispatched=False)
    ledger.mark_dispatched(binding["run_id"], "offline")
    ledger.settle(binding["run_id"], "offline", ".01")
    ledger.close_run(binding["run_id"])
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert _preserved_files(pool) == before
    assert {name: Path(pool["receipt"][name]).stat().st_ino for name in identities} == identities
    assert _budget_state(pool["receipt"])["charged"] == Decimal(".01")


@pytest.mark.parametrize("extended", [False, True])
def test_legacy_binding_retains_dispatch_deadline_and_settles_after_new_end(
    pool, monkeypatch, extended
):
    if extended:
        activate(pool)
    owner = fixtures.controller(pool)
    request = pool["request"].model_copy(
        update={"daily_budget_usd": owner.effective_daily_limit_usd}
    )
    request, binding = owner.begin("1" * 32, request, source_sha256=pool["sha"])
    binding = _legacy_binding(pool, binding)
    before = _preserved_files(pool)
    ledger = judge.judge_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    ledger.reserve(binding["run_id"], "prior", ".01")
    ledger.settle(binding["run_id"], "prior", ".01")
    ledger.reserve(binding["run_id"], "unsent", ".01", dispatched=False)
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 15, 20, tzinfo=UTC))
    with pytest.raises(AllocationRefused, match="JUDGE_EXPIRED"):
        ledger.mark_dispatched(binding["run_id"], "unsent")
    ledger.cancel_undispatched(binding["run_id"], "unsent")
    with pytest.raises(AllocationRefused, match="JUDGE_EXPIRED"):
        ledger.reserve(binding["run_id"], "late", ".01")
    ledger.close_run(binding["run_id"])
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 24, tzinfo=UTC))
    assert not owner.available
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert _preserved_files(pool) == before
    with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
        stored = connection.execute("SELECT payload FROM claims").fetchone()[0]
    assert json.loads(stored) == binding


@pytest.mark.parametrize(
    "field,value",
    [
        ("expires_at", "2026-12-15T20:00:00Z"),
        ("expires_at", "2026-12-24T20:00:00Z"),
        ("judging_period_policy", "caller-selected"),
        ("schema", judge.SCHEMA),
    ],
)
def test_rehashed_period_tampering_is_rejected_even_in_claim(pool, field, value):
    owner = fixtures.controller(pool)
    request, binding = owner.begin("1" * 32, pool["request"], source_sha256=pool["sha"])
    binding[field] = value
    binding["binding_sha256"] = judge.digest(
        {key: val for key, val in binding.items() if key != "binding_sha256"}
    )
    with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
        connection.execute("UPDATE claims SET payload=?", (json.dumps(binding),))
    with pytest.raises(AllocationRefused):
        judge.verify_judge_binding(binding, request, binding["run_id"])


def test_new_credit_binding_stops_at_exact_official_end(pool, monkeypatch):
    activate(pool)
    owner, request, binding, ledger = extended_begin(pool)
    ledger.reserve(binding["run_id"], "unsent", ".01", dispatched=False)
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 23, 20, tzinfo=UTC))
    with pytest.raises(AllocationRefused, match="JUDGE_EXPIRED"):
        ledger.mark_dispatched(binding["run_id"], "unsent")
    ledger.cancel_undispatched(binding["run_id"], "unsent")
    ledger.close_run(binding["run_id"])
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not owner.available
    with pytest.raises(AllocationRefused, match="JUDGE_EXPIRED"):
        owner.begin("3" * 32, request, source_sha256=pool["sha"])
