"""Synthetic pools only; inherited guard forbids network, GPU and production files."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import httpx
import pytest
import test_judge_binding as fixtures
from test_judge_credit import activate

from headroom.acceptance import judge_binding as judge
from headroom.acceptance.allocation import AllocationRefused, _budget_state
from headroom.acceptance.snapshot_binding import (
    current_snapshot_budget_factory,
    snapshot_feature_context,
)
from headroom.acceptance.snapshot_public_binding import (
    PROTOCOL,
    SnapshotPublicAllocation,
    snapshot_public_budget_factory,
    verify_snapshot_public_binding,
)
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.runtime import build_live_runtime, read_live_profile
from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest
from headroom.store.db import Store

offline = fixtures.offline
pool = fixtures.pool


@pytest.fixture
def upload(pool):
    directory = pool["root"] / "uploads"
    directory.mkdir()
    files = {}
    for kind, content in {
        "snapshot": '{"segments":[],"device_traces":[]}',
        "traceback": "synthetic capture",
        "source": "x = 1\n",
    }.items():
        path = directory / kind
        path.write_text(content)
        files[kind] = path
    return SnapshotDiagnosisRequest(**files, runtime_profile=pool["receipt"]["profile_path"])


def owner(pool):
    return SnapshotPublicAllocation(fixtures.controller(pool), project_root=pool["root"])


def begin(pool, upload, number=1):
    allocation = owner(pool)
    binding = allocation.claim(upload, f"{number:032x}")
    request = upload.model_copy(update={"budget_usd": binding["run_limit_usd"]})
    ledger = snapshot_public_budget_factory(binding, project_root=pool["root"])(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    return allocation, request, binding, ledger


def finish(allocation, binding, ledger):
    ledger.close_run(binding["run_id"])
    return allocation.finish(binding, execution_terminal=True, cleanup_verified=True)


def test_snapshot_is_native_intent_and_normal_judge_claims_are_mutually_exclusive(pool, upload):
    allocation, request, binding, ledger = begin(pool, upload)
    assert binding["snapshot_protocol"] == PROTOCOL
    assert binding["kind"] == "snapshot_diagnosis"
    assert binding["schema"] == judge.PERIOD_SCHEMA
    assert not isinstance(request, type(pool["request"]))
    assert (
        binding["snapshot_intent"]["payload"]["inputs"]["snapshot"]["sha256"]
        == hashlib.sha256(upload.snapshot.read_bytes()).hexdigest()
    )
    assert not fixtures.controller(pool).available
    with pytest.raises(AllocationRefused, match="UNSETTLED_CLAIM"):
        fixtures.controller(pool).begin("2" * 32, pool["request"], source_sha256=pool["sha"])
    assert finish(allocation, binding, ledger)["status"] == "settled"
    _, _, ordinary, ordinary_ledger = fixtures.begin(pool, 2)
    assert not owner(pool).available
    with pytest.raises(AllocationRefused, match="UNSETTLED_CLAIM"):
        owner(pool).claim(upload, "3" * 32)
    ordinary_ledger.close_run(ordinary["run_id"])
    fixtures.controller(pool).finish(ordinary, execution_terminal=True, cleanup_verified=True)


def test_snapshot_and_repair_claims_race_on_same_registry(pool, upload):
    barrier = Barrier(2)

    def claim(kind):
        barrier.wait()
        try:
            if kind == "snapshot":
                return owner(pool).claim(upload, "1" * 32)
            return fixtures.controller(pool).begin(
                "2" * 32, pool["request"], source_sha256=pool["sha"]
            )[1]
        except AllocationRefused:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(claim, ["snapshot", "repair"]))
    assert sum(result is not None for result in results) == 1


@pytest.mark.parametrize("stage", ["reserve", "dispatch"])
@pytest.mark.parametrize("field", ["snapshot", "traceback", "source"])
def test_every_input_rehashed_before_reserve_and_actual_dispatch(pool, upload, stage, field):
    _, _, binding, ledger = begin(pool, upload)
    if stage == "dispatch":
        ledger.reserve(binding["run_id"], "pending", ".01", dispatched=False)
    getattr(upload, field).write_text("changed bytes")
    with pytest.raises(AllocationRefused, match="INPUT_CHANGED"):
        if stage == "reserve":
            ledger.reserve(binding["run_id"], "pending", ".01", dispatched=False)
        else:
            ledger.mark_dispatched(binding["run_id"], "pending")
    assert all(row["dispatched"] == 0 for row in _budget_state(pool["receipt"])["attempts"])


@pytest.mark.parametrize(
    "change",
    ["profile", "receipt", "claim", "ledger", "expiry", "extension", "run_mode", "run_limit"],
)
def test_dispatch_rechecks_funding_identity_expiry_and_claim(pool, upload, monkeypatch, change):
    if change == "extension":
        activate(pool)
    _, _, binding, ledger = begin(pool, upload)
    ledger.reserve(binding["run_id"], "pending", ".01", dispatched=False)
    if change == "profile":
        Path(pool["receipt"]["profile_path"]).write_text("{}")
    elif change == "receipt":
        pool["path"].write_text("{}")
    elif change == "claim":
        with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
            connection.execute("UPDATE claims SET state='settled'")
    elif change == "ledger":
        path = Path(pool["receipt"]["ledger_path"])
        other = path.with_suffix(".replacement")
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        other.replace(path)
    elif change in {"run_mode", "run_limit"}:
        column, value = (
            ("budget_mode", "actual_usage") if change == "run_mode" else ("limit_usd", ".31")
        )
        with ledger._transaction() as connection:
            connection.execute(f"UPDATE budget_runs SET {column}=?", (value,))
    elif change == "expiry":
        monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 23, 20, tzinfo=UTC))
    else:
        (pool["path"].parent / "credit-extension.json").write_text("{}")
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        ledger.mark_dispatched(binding["run_id"], "pending")


@pytest.mark.parametrize(
    "field,value",
    [
        ("snapshot_protocol", "untrusted"),
        ("kind", "fix"),
        ("total_limit_usd", "999"),
        ("daily_limit_usd", "999"),
        ("run_limit_usd", ".31"),
    ],
)
def test_rehashed_claim_cannot_choose_protocol_or_funding(pool, upload, field, value):
    allocation = owner(pool)
    binding = allocation.claim(upload, "1" * 32)
    binding[field] = value
    binding["binding_sha256"] = judge.digest(
        {key: item for key, item in binding.items() if key != "binding_sha256"}
    )
    with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
        connection.execute("UPDATE claims SET payload=?", (json.dumps(binding),))
    with pytest.raises(AllocationRefused):
        verify_snapshot_public_binding(binding, upload, binding["run_id"])


def test_receipt_profile_mismatch_and_symlink_never_claim(pool, upload):
    wrong = upload.model_copy(update={"runtime_profile": pool["root"] / "wrong.json"})
    with pytest.raises(AllocationRefused, match="PROFILE_CHANGED"):
        owner(pool).claim(wrong, "1" * 32)
    target = upload.snapshot.with_suffix(".original")
    upload.snapshot.rename(target)
    upload.snapshot.symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        owner(pool).claim(upload, "1" * 32)
    with sqlite3.connect(pool["receipt"]["claims_path"]) as connection:
        assert connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0] == 0


def test_remainder_is_narrowed_and_queue_must_use_exact_effective_cap(pool, upload):
    ledger = BudgetLedger(pool["receipt"]["ledger_path"], total_limit="6.61", daily_limit="6.61")
    ledger.open_run("prior", "6.60")
    ledger.reserve("prior", "prior-charge", "6.60")
    ledger.settle("prior", "prior-charge", "6.60")
    ledger.close_run("prior")
    allocation = owner(pool)
    binding = allocation.claim(upload, "1" * 32)
    assert Decimal(binding["run_limit_usd"]) == Decimal(".01")
    with pytest.raises(AllocationRefused, match="INPUT_CHANGED"):
        verify_snapshot_public_binding(binding, upload, binding["run_id"])
    request = upload.model_copy(update={"budget_usd": binding["run_limit_usd"]})
    bounded = snapshot_public_budget_factory(binding)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    bounded.open_run(binding["run_id"], request.budget_usd)
    with pytest.raises(BudgetExceeded):
        bounded.reserve(binding["run_id"], "over", ".02")
    bounded.reserve(binding["run_id"], "last", ".01")
    bounded.settle(binding["run_id"], "last", ".01")
    assert finish(allocation, binding, bounded)["status"] == "settled"
    assert not owner(pool).available


@pytest.mark.parametrize("actual,cleanup", [(None, True), (".01", False)])
def test_unknown_or_unclean_snapshot_blocks_ordinary_judge_jobs(pool, upload, actual, cleanup):
    allocation, _, binding, ledger = begin(pool, upload)
    ledger.reserve(binding["run_id"], "call", ".02")
    ledger.settle(binding["run_id"], "call", actual)
    ledger.close_run(binding["run_id"])
    result = allocation.finish(binding, execution_terminal=True, cleanup_verified=cleanup)
    assert result["status"] == "blocked"
    if actual is None:
        assert result["actual_usd"] is None
    assert not allocation.available and not fixtures.controller(pool).available


def test_pending_exception_is_not_a_blanket_unknown_exemption(pool, upload):
    _, request, binding, ledger = begin(pool, upload)
    ledger.reserve(binding["run_id"], "unsent", ".01", dispatched=False)
    with pytest.raises(AllocationRefused, match="PENDING_ATTEMPT_CHANGED"):
        verify_snapshot_public_binding(
            binding, request, binding["run_id"], pending_attempt_id="other"
        )
    with ledger._transaction() as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(budget_attempts)")]
        row = dict(connection.execute("SELECT * FROM budget_attempts WHERE id='unsent'").fetchone())
        row.update(id="other-unknown", dispatched=1)
        connection.execute(
            f"INSERT INTO budget_attempts ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [row[name] for name in columns],
        )
    with pytest.raises(AllocationRefused):
        ledger.mark_dispatched(binding["run_id"], "unsent")


def test_context_uses_real_runtime_factory_above_old_profile_cap(pool, upload, monkeypatch):
    plan = activate(pool)
    limit = plan["amounts"]["total_limit_usd"]
    prior = BudgetLedger(pool["receipt"]["ledger_path"], total_limit=limit, daily_limit=limit)
    prior.open_run("prior", "6.70")
    prior.reserve("prior", "prior-charge", "6.70")
    prior.settle("prior", "prior-charge", "6.70")
    prior.close_run("prior")
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(pool["root"] / "must-not-select.db"))
    allocation = owner(pool)
    binding = allocation.claim(upload, "1" * 32)
    request = upload.model_copy(update={"budget_usd": binding["run_limit_usd"]})
    profile = read_live_profile(pool["receipt"]["profile_path"])
    assert profile.authorized_total_usd == "6.61"
    with snapshot_feature_context(binding, project_root=pool["root"]):
        ledger = current_snapshot_budget_factory()(binding["run_id"], request, profile)
    assert ledger.path == Path(pool["receipt"]["ledger_path"])
    assert ledger.total_limit == Decimal(limit) > Decimal("6.70")
    ledger.open_run(binding["run_id"], request.budget_usd)
    store = Store(pool["root"] / "sdk.fixture.db")
    store.create_run(binding["run_id"], status="running")
    observed = []

    def respond(wire):
        body = json.loads(wire.content)
        observed.append(body)
        return httpx.Response(
            200,
            json={
                "id": "synthetic",
                "model": body["model"],
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "offline"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            },
        )

    bundle = build_live_runtime(
        binding["run_id"],
        profile=profile,
        budget=ledger,
        store=store,
        env_file=pool["credential"],
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    try:
        bundle.client.complete("patcher", [{"role": "user", "content": "synthetic"}], max_tokens=20)
    finally:
        bundle.close()
        store.close()
    assert len(observed) == 1
    assert finish(allocation, binding, ledger)["status"] == "settled"
    assert _budget_state(pool["receipt"])["charged"] > Decimal("6.70")


def test_settlement_does_not_require_deleted_input_or_unexpired_period(pool, upload, monkeypatch):
    allocation, _, binding, ledger = begin(pool, upload)
    ledger.reserve(binding["run_id"], "call", ".02")
    ledger.settle_upper_bound(
        binding["run_id"], "call", ".01", basis="verified_tariff_missing_cache_count"
    )
    ledger.close_run(binding["run_id"])
    upload.snapshot.unlink()
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 24, tzinfo=UTC))
    result = allocation.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["actual_usd"] is None
    assert Decimal(result["charged_usd"]) == Decimal(".01")
