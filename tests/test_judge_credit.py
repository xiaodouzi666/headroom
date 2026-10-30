"""Gift extension tests: synthetic private evidence and temporary ledgers only."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import httpx
import pytest
import test_judge_binding as fixtures
from test_judge_binding import begin, charge, controller

from headroom.acceptance import judge_binding as judge
from headroom.acceptance import judge_credit as credit
from headroom.acceptance.allocation import AllocationRefused, _budget_state
from headroom.budget import BudgetExceeded
from headroom.runtime import build_live_runtime, read_live_profile
from headroom.store.db import Store

offline = fixtures.offline
pool = fixtures.pool


def make_plan(pool, **updates):
    directory = pool["root"] / ".cache/credit-review"
    directory.mkdir(exist_ok=True)
    evidence = directory / "synthetic-evidence.json"
    if not evidence.exists():
        evidence.write_text('{"synthetic": true, "not_provider_evidence": true}\n')
        evidence.chmod(0o600)
    snapshot = {
        "observed_at": judge._now().isoformat(),
        "gift_balance_gross_usd": "50.00",
        "reserve_gross_usd": "8.00",
        "tax_factor": "1.21",
        "unreflected_charge_reserve_gross_usd": "0.00",
        "unreflected_charge_review": "Synthetic fixture only; no provider observation",
        "other_commitments": [
            {
                "allocation_id": "synthetic-other-allocation",
                "receipt_sha256": "b" * 64,
                "accounting_sha256": "c" * 64,
                "authorized_net_usd": "8.00",
                "charged_net_usd": "2.123456789",
                "remaining_net_usd": "5.876543211",
                "tax_factor": "1.21",
            }
        ],
        **credit.judge_accounting_snapshot(pool["receipt"]),
        "evidence": [
            {"path": str(evidence), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        ],
        "gift_only": True,
    }
    snapshot.update(updates)
    authorization = {
        "state": "authorized",
        "scope": credit.AUTHORIZATION_SCOPE,
        "approval_message_ref": "synthetic-not-real-authorization",
        "statement_sha256": "d" * 64,
        "credit_snapshot_sha256": judge.digest(snapshot),
        "gift_only": True,
        "no_topup": True,
        "no_overage": True,
        "preserve_reserve_gross_usd": snapshot["reserve_gross_usd"],
    }
    return credit.prepare_judge_credit(
        pool["receipt"], snapshot, authorization, project_root=pool["root"]
    )


def activate(pool, plan=None):
    plan = make_plan(pool) if plan is None else plan
    return credit.activate_judge_credit(
        plan, project_root=pool["root"], expected_sha256=plan["extension_sha256"]
    )


def extended_begin(pool, index=2):
    owner = controller(pool)
    request = pool["request"].model_copy(
        update={"daily_budget_usd": owner.effective_daily_limit_usd}
    )
    request, binding = owner.begin(f"{index:032x}", request, source_sha256=pool["sha"])
    ledger = judge.judge_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    return owner, request, binding, ledger


def test_one_extension_preserves_old_history_and_uses_cumulative_cap(pool):
    owner, _, old_binding, old_ledger = begin(pool)
    charge(old_binding, old_ledger)
    assert (
        owner.finish(old_binding, execution_terminal=True, cleanup_verified=True)["status"]
        == "settled"
    )
    old_state = _budget_state(pool["receipt"])
    with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
        old_claims = conn.execute("SELECT * FROM claims").fetchall()
        old_identity = conn.execute("SELECT * FROM judge_identity").fetchall()
    files = [pool["path"], Path(pool["receipt"]["profile_path"])]
    before = {path: path.read_bytes() for path in files}
    identities = {
        key: Path(pool["receipt"][key]).stat().st_ino for key in ("ledger_path", "claims_path")
    }
    plan = make_plan(pool)
    assert plan["amounts"]["future_gross_usd"] == "34.88938271469"
    assert plan["amounts"]["future_net_usd"] == "28.83"
    assert Decimal(plan["amounts"]["total_limit_usd"]) == Decimal("28.93")
    activate(pool, plan)
    assert _budget_state(pool["receipt"]) == old_state
    assert before == {path: path.read_bytes() for path in files}
    assert identities == {key: Path(pool["receipt"][key]).stat().st_ino for key in identities}
    with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
        assert conn.execute("SELECT * FROM claims").fetchall() == old_claims
        assert conn.execute("SELECT * FROM judge_identity").fetchall() == old_identity
    assert owner.receipt["amounts"]["approved_net_usd"] == "6.61"
    assert Decimal(owner.effective_daily_limit_usd) == Decimal("28.93")
    owner, _, binding, ledger = extended_begin(pool)
    assert binding["schema"] == judge.PERIOD_SCHEMA
    assert binding["credit_extension_sha256"] == plan["extension_sha256"]
    assert ledger.total_limit == ledger.daily_limit == Decimal("28.93")
    charge(binding, ledger)
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    with pytest.raises(AllocationRefused, match="ALREADY_EXTENDED"):
        activate(pool, plan)


def test_prepare_is_pure_and_authorization_covers_entire_snapshot(pool, monkeypatch):
    plan = make_plan(pool)

    def denied(*args, **kwargs):
        raise AssertionError("Pure preparation must not read files/DB")

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(sqlite3, "connect", denied)
    assert (
        credit.prepare_judge_credit(
            pool["receipt"],
            plan["credit_snapshot"],
            plan["authorization"],
            project_root=pool["root"],
        )
        == plan
    )
    snapshot = dict(plan["credit_snapshot"], gift_balance_gross_usd="99")
    with pytest.raises(AllocationRefused, match="AUTHORIZATION"):
        credit.prepare_judge_credit(
            pool["receipt"], snapshot, plan["authorization"], project_root=pool["root"]
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("gift_balance_gross_usd", "Infinity"),
        ("gift_balance_gross_usd", "NaN"),
        ("gift_balance_gross_usd", "-1"),
        ("gift_balance_gross_usd", 43.54),
        ("reserve_gross_usd", "7.99"),
        ("tax_factor", "1"),
        ("unreflected_charge_reserve_gross_usd", "-0.01"),
        ("unreflected_charge_review", ""),
        ("other_commitments", []),
        ("judge_charged_usd", "6.62"),
        ("gift_only", False),
        ("observed_at", "2026-10-29T00:00:00"),
    ],
)
def test_invalid_or_unsupported_credit_facts_fail_closed(pool, field, value):
    with pytest.raises((ValueError, ArithmeticError)):
        make_plan(pool, **{field: value})


def test_full_other_remaining_and_lag_reserve_are_deducted(pool):
    baseline = make_plan(pool)
    reduced = make_plan(pool, unreflected_charge_reserve_gross_usd="1.21")
    assert (
        Decimal(baseline["amounts"]["future_net_usd"])
        - Decimal(reduced["amounts"]["future_net_usd"])
        == 1
    )
    item = dict(baseline["credit_snapshot"]["other_commitments"][0], remaining_net_usd="0")
    with pytest.raises(AllocationRefused, match="COMMITMENT_AMOUNT"):
        make_plan(pool, other_commitments=[item])
    with pytest.raises(AllocationRefused, match="COMMITMENT_INVALID"):
        make_plan(pool, other_commitments=baseline["credit_snapshot"]["other_commitments"] * 2)


@pytest.mark.parametrize(
    "mode",
    [
        "wrong_hash",
        "tampered_total",
        "old_time",
        "future_time",
        "evidence_changed",
        "evidence_mode",
    ],
)
def test_explicit_activation_requires_exact_review_and_fresh_private_evidence(pool, mode):
    plan = make_plan(pool)
    expected = plan["extension_sha256"]
    if mode == "wrong_hash":
        expected = "0" * 64
    elif mode == "tampered_total":
        plan["amounts"]["total_limit_usd"] = "99"
        plan["extension_sha256"] = judge.digest(
            {k: v for k, v in plan.items() if k != "extension_sha256"}
        )
        expected = plan["extension_sha256"]
    elif mode.endswith("time"):
        offset = -3601 if mode == "old_time" else 1
        plan = make_plan(pool, observed_at=(judge._now() + timedelta(seconds=offset)).isoformat())
        expected = plan["extension_sha256"]
    elif mode == "evidence_changed":
        Path(plan["credit_snapshot"]["evidence"][0]["path"]).write_text("{}")
    else:
        Path(plan["credit_snapshot"]["evidence"][0]["path"]).chmod(0o644)
    with pytest.raises((ValueError, OSError)):
        credit.activate_judge_credit(plan, project_root=pool["root"], expected_sha256=expected)
    assert not (pool["path"].parent / credit.EXTENSION_FILENAME).exists()


def test_old_pending_must_settle_and_changed_accounting_needs_new_plan(pool):
    plan = make_plan(pool)
    owner, _, binding, ledger = begin(pool)
    with pytest.raises(AllocationRefused, match="UNSETTLED_CLAIM"):
        activate(pool, plan)
    charge(binding, ledger)
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    with pytest.raises(AllocationRefused, match="ACCOUNTING_CHANGED"):
        activate(pool, plan)
    activate(pool)
    assert judge._validate_binding(binding, pool["receipt"], binding["run_id"]) is None


@pytest.mark.parametrize("actual,cleanup", [(None, True), (".10", False), (".31", True)])
def test_unknown_unclean_and_overrun_cannot_be_refunded_by_extension(pool, actual, cleanup):
    plan = make_plan(pool)
    owner, _, binding, ledger = begin(pool)
    if actual == ".31":
        with pytest.raises(BudgetExceeded):
            charge(binding, ledger, actual)
        ledger.close_run(binding["run_id"])
    else:
        charge(binding, ledger, actual)
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=cleanup)["status"]
        == "blocked"
    )
    with pytest.raises(ValueError):
        activate(pool, plan)


def test_concurrent_activation_adds_exactly_one_extension(pool):
    plan = make_plan(pool)
    barrier = Barrier(2)

    def attempt(_):
        barrier.wait()
        try:
            activate(pool, plan)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(attempt, range(2))) == 1
    with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
        assert conn.execute("SELECT count(*) FROM judge_credit_extension").fetchone()[0] == 1


@pytest.mark.parametrize(
    "change", ["extension", "evidence", "registry", "delete_extension", "rehashed_binding"]
)
def test_every_reserve_revalidates_extension(pool, change):
    plan = activate(pool)
    _, _request, binding, ledger = extended_begin(pool)
    ledger.reserve(binding["run_id"], "first", ".01")
    ledger.settle(binding["run_id"], "first", ".01")
    path = pool["path"].parent / credit.EXTENSION_FILENAME
    if change == "extension":
        path.write_text("{}")
    elif change == "delete_extension":
        path.unlink()
    elif change == "evidence":
        Path(plan["credit_snapshot"]["evidence"][0]["path"]).write_text("{}")
    elif change == "registry":
        with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
            conn.execute("UPDATE judge_credit_extension SET extension_sha256=?", ("0" * 64,))
    else:
        binding["total_limit_usd"] = "99"
        binding["binding_sha256"] = judge.digest(
            {k: v for k, v in binding.items() if k != "binding_sha256"}
        )
        with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
            conn.execute(
                "UPDATE claims SET payload=? WHERE run_id=?",
                (json.dumps(binding), binding["run_id"]),
            )
    with pytest.raises((ValueError, OSError, KeyError)):
        ledger.reserve(binding["run_id"], "second", ".01")
    assert len(_budget_state(pool["receipt"])["attempts"]) == 1


def test_dispatch_rechecks_extension_and_expiry_but_settlement_after_expiry_is_allowed(
    pool, monkeypatch
):
    activate(pool)
    owner, _, binding, ledger = extended_begin(pool)
    ledger.reserve(binding["run_id"], "pending", ".01", dispatched=False)
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 23, 20, tzinfo=UTC))
    with pytest.raises(AllocationRefused, match="EXPIRED"):
        ledger.mark_dispatched(binding["run_id"], "pending")
    ledger.cancel_undispatched(binding["run_id"], "pending")
    ledger.close_run(binding["run_id"])
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not owner.available


def test_original_profile_is_retained_and_actual_sdk_mock_uses_extended_ledger(pool):
    for index in range(1, 23):
        old_owner, _, old_binding, old_ledger = begin(pool, index=index)
        charge(old_binding, old_ledger, ".30")
        assert (
            old_owner.finish(old_binding, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )
    activate(pool)
    owner, _, binding, ledger = extended_begin(pool, index=23)
    store = Store(pool["root"] / "store.fixture.db")
    store.create_run(binding["run_id"], status="running")
    observed = []

    def respond(request):
        body = json.loads(request.content)
        observed.append(body["model"])
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "model": body["model"],
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "fixture"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20000,
                    "completion_tokens": 2,
                    "total_tokens": 20002,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    profile = read_live_profile(pool["receipt"]["profile_path"])
    assert profile.authorized_total_usd == "6.61"
    assert ledger.total_limit == Decimal("35.43")
    bundle = build_live_runtime(
        binding["run_id"],
        profile=profile,
        budget=ledger,
        store=store,
        env_file=pool["credential"],
        transport=httpx.MockTransport(respond),
    )
    try:
        bundle.router.chat("patcher", [{"role": "user", "content": "offline"}], max_tokens=10)
    finally:
        bundle.close()
    ledger.close_run(binding["run_id"])
    assert len(observed) == 1
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert len(_budget_state(pool["receipt"])["attempts"]) == 23
    assert _budget_state(pool["receipt"])["charged"] == Decimal("6.620004")


def test_extension_keeps_single_run_cap_and_finite_total(pool):
    activate(pool)
    owner, _, binding, ledger = extended_begin(pool)
    with pytest.raises(BudgetExceeded):
        ledger.reserve(binding["run_id"], "over-run", ".31")
    assert not _budget_state(pool["receipt"])["attempts"]
    ledger.close_run(binding["run_id"])
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )


def test_partial_activation_never_falls_back_to_old_allowance(pool):
    plan = make_plan(pool)
    path = pool["path"].parent / credit.EXTENSION_FILENAME
    path.write_text(json.dumps(plan))
    path.chmod(0o600)
    assert not controller(pool).available
    with pytest.raises(AllocationRefused, match="PARTIAL_ACTIVATION"):
        controller(pool).begin("f" * 32, pool["request"], source_sha256=pool["sha"])


def test_spend_past_initial_cap_keeps_all_prior_charges(pool):
    for index in range(1, 23):
        owner, _, binding, ledger = begin(pool, index=index)
        charge(binding, ledger, ".30")
        assert (
            owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"]
            == "settled"
        )
    prior = _budget_state(pool["receipt"])
    assert prior["charged"] == Decimal("6.60")
    plan = activate(pool)
    assert Decimal(plan["amounts"]["total_limit_usd"]) == Decimal("35.43")
    owner, _, binding, ledger = extended_begin(pool, index=23)
    charge(binding, ledger, ".10")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    after = _budget_state(pool["receipt"])
    assert after["charged"] == Decimal("6.70")
    assert len(after["attempts"]) == 23
    assert all(row in after["attempts"] for row in prior["attempts"])


def test_dispatch_rejects_extension_changed_after_unsent_reservation(pool):
    activate(pool)
    _, _, binding, ledger = extended_begin(pool)
    ledger.reserve(binding["run_id"], "pending", ".01", dispatched=False)
    (pool["path"].parent / credit.EXTENSION_FILENAME).write_text("{}")
    with pytest.raises(ValueError):
        ledger.mark_dispatched(binding["run_id"], "pending")
    assert _budget_state(pool["receipt"])["attempts"][0]["dispatched"] == 0


@pytest.mark.parametrize("actual,cleanup", [(None, True), (".10", False)])
def test_extended_pool_retains_unknown_or_cleanup_failure(pool, actual, cleanup):
    activate(pool)
    owner, _, binding, ledger = extended_begin(pool)
    charge(binding, ledger, actual)
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=cleanup)
    assert result["status"] == "blocked"
    assert (
        result["actual_usd"] is None
        if actual is None
        else Decimal(result["actual_usd"]) == Decimal(actual)
    )
    assert not owner.available
    with pytest.raises(ValueError):
        extended_begin(pool, index=3)
