"""Temporary judge pools only; no real credentials, databases, network or GPU."""

import builtins
import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Barrier
from urllib.parse import unquote, urlparse

import httpx
import pytest
from test_diagnosis_acceptance import profile

from headroom.acceptance import judge_binding as judge
from headroom.acceptance.allocation import AllocationRefused, _budget_state
from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.orchestrator import FixRequest
from headroom.runtime import build_live_runtime, read_live_profile
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    root = Path(__file__).resolve().parents[1]

    def denied(*args, **kwargs):
        raise AssertionError("Network/provider/GPU dispatch forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    for module in (builtins, io, os):
        original = module.open

        def guarded(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                raw = Path(os.fsdecode(path))
                if not raw.is_absolute() and kwargs.get("dir_fd") is not None:
                    raw = Path(os.readlink(f"/proc/self/fd/{kwargs['dir_fd']}")) / raw
                target = raw.resolve()
                if (
                    target.name.startswith(".env")
                    or target.is_relative_to(root / ".cache")
                    or target.is_relative_to(root / "runs")
                ):
                    raise AssertionError("Production file/credential access forbidden")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)
    connect = sqlite3.connect

    def guarded_db(path, *args, **kwargs):
        value = str(path)
        target = Path(
            unquote(urlparse(value).path) if value.startswith("file:") else value
        ).resolve()
        if target.is_relative_to(root / ".cache") or target.is_relative_to(root / "runs"):
            raise AssertionError("Production database access forbidden")
        return connect(path, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_db)
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 10, 29, tzinfo=UTC))


@pytest.fixture
def pool(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    profile_path, credential = profile(root)
    document = json.loads(profile_path.read_text())
    document.update(authorized_total_usd="6.61", available_credit_usd="10")
    authorization = {
        "state": "authorized",
        "scope": "JUDGE_ACCESS",
        "approved_net_usd": "6.61",
        "gross_cap_usd": "8.00",
        "approval_message_ref": "offline-fixture-not-authorization",
        "statement_sha256": "a" * 64,
    }
    plan = judge.prepare_judge_plan(document, authorization, project_root=root)
    assert not (root / ".cache").exists()
    receipt = judge.activate_judge_allocation(
        plan, project_root=root, expected_sha256=plan["plan_sha256"]
    )
    source = root / "input"
    source.mkdir()
    script = source / "train.py"
    script.write_text("raise AssertionError('must never execute fixture source')\n")
    request = FixRequest(
        script=str(script),
        source_root=str(source),
        runtime_profile=receipt["profile_path"],
        daily_budget_usd="6.61",
        budget_usd=".30",
    )
    return {
        "root": root,
        "path": root / ".cache/judge-access/receipt.json",
        "receipt": receipt,
        "plan": plan,
        "request": request,
        "source": script,
        "sha": hashlib.sha256(script.read_bytes()).hexdigest(),
        "credential": credential,
    }


def controller(pool):
    return judge.JudgeAllocation(pool["path"], project_root=pool["root"])


def begin(pool, index=1):
    owner = controller(pool)
    request, binding = owner.begin(f"{index:032x}", pool["request"], source_sha256=pool["sha"])
    ledger = judge.judge_budget_factory(binding, request)(
        binding["run_id"], request, read_live_profile(pool["receipt"]["profile_path"])
    )
    ledger.open_run(binding["run_id"], request.budget_usd)
    return owner, request, binding, ledger


def charge(binding, ledger, actual=".10"):
    ledger.reserve(binding["run_id"], "attempt-" + binding["run_id"], ".30")
    ledger.settle(binding["run_id"], "attempt-" + binding["run_id"], actual)
    ledger.close_run(binding["run_id"])


def test_independent_pool_ignores_old_env_and_preserves_original_files(pool, monkeypatch):
    old = pool["root"] / ".cache/final48-allocation"
    old.mkdir()
    for name in ("receipt.json", "runtime-profile.json", "budget.db"):
        (old / name).write_bytes(b"ORIGINAL DO NOT OPEN")
    before = {p.name: p.read_bytes() for p in old.iterdir()}
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(old / "budget.db"))
    owner, _request, binding, ledger = begin(pool)
    assert str(ledger.path) == pool["receipt"]["ledger_path"]
    assert ledger.total_limit == ledger.daily_limit == Decimal("6.61")
    assert pool["receipt"]["admission_basis"] == "existing_reviewed_local_estimate_with_margin"
    assert Decimal(binding["run_limit_usd"]) == Decimal(".30")
    charge(binding, ledger)
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert before == {p.name: p.read_bytes() for p in old.iterdir()}
    assert os.environ["HEADROOM_BUDGET_DB_PATH"] == str(old / "budget.db")
    assert controller(pool).available
    with pytest.raises(AllocationRefused):
        owner.begin(binding["run_id"], pool["request"], source_sha256=pool["sha"])


def test_plan_and_activation_cannot_replace_or_increase_reviewed_config(pool):
    with pytest.raises(AllocationRefused, match="ALREADY_INITIALIZED"):
        judge.activate_judge_allocation(
            pool["plan"], project_root=pool["root"], expected_sha256=pool["plan"]["plan_sha256"]
        )
    plan = dict(pool["plan"], amounts=dict(judge.AMOUNTS, approved_net_usd="100"))
    with pytest.raises(AllocationRefused, match="PLAN_CHANGED"):
        judge.activate_judge_allocation(
            plan, project_root=pool["root"], expected_sha256=pool["plan"]["plan_sha256"]
        )
    plan = dict(pool["plan"], admission_basis="verified_provider_bound")
    with pytest.raises(AllocationRefused, match="PLAN_CHANGED"):
        judge.activate_judge_allocation(
            plan, project_root=pool["root"], expected_sha256=pool["plan"]["plan_sha256"]
        )
    assert Decimal(judge.AMOUNTS["approved_net_usd"]) * Decimal(
        judge.AMOUNTS["tax_factor"]
    ) <= Decimal(judge.AMOUNTS["gross_cap_usd"])


@pytest.mark.parametrize(
    "field,value",
    [("runtime_profile", "/tmp/other.json"), ("daily_budget_usd", "7"), ("budget_usd", ".31")],
)
def test_request_cannot_select_another_profile_or_raise_caps(pool, field, value):
    request = pool["request"].model_copy(update={field: value})
    with pytest.raises(AllocationRefused):
        controller(pool).begin("1" * 32, request, source_sha256=pool["sha"])
    assert not _budget_state(pool["receipt"])["attempts"]


@pytest.mark.parametrize(
    "change",
    [
        "receipt",
        "profile",
        "source",
        "request",
        "claim",
        "run_limit",
        "budget_mode",
        "db_identity",
        "claims_identity",
        "expiry",
    ],
)
def test_every_reserve_revalidates_binding(pool, monkeypatch, change):
    _, request, binding, ledger = begin(pool)
    ledger.reserve(binding["run_id"], "first", ".01")
    ledger.settle(binding["run_id"], "first", ".01")
    if change == "receipt":
        pool["path"].write_text("{}")
    elif change == "profile":
        Path(pool["receipt"]["profile_path"]).write_text("{}")
    elif change == "source":
        pool["source"].write_text("changed = True\n")
    elif change == "request":
        request.target = "reclaim"
    elif change == "claim":
        with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
            conn.execute("UPDATE claims SET state='settled'")
    elif change in {"run_limit", "budget_mode"}:
        field, value = (
            ("limit_usd", ".31") if change == "run_limit" else ("budget_mode", "actual_usage")
        )
        with ledger._transaction() as conn:
            conn.execute(f"UPDATE budget_runs SET {field}=?", (value,))
    elif change in {"db_identity", "claims_identity"}:
        path = Path(pool["receipt"]["ledger_path" if change == "db_identity" else "claims_path"])
        replacement = path.with_suffix(".replacement")
        replacement.write_bytes(path.read_bytes())
        replacement.chmod(0o600)
        replacement.replace(path)
    else:
        monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 15, 20, tzinfo=UTC))
    with pytest.raises((ValueError, OSError, sqlite3.Error)):
        ledger.reserve(binding["run_id"], "second", ".01")


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_limit_usd", ".31"),
        ("daily_limit_usd", "7"),
        ("total_limit_usd", "7"),
        ("expires_at", "2027-12-15T20:00:00Z"),
        ("schema", "http-selected"),
    ],
)
def test_rehashed_binding_and_claim_cannot_exceed_receipt(pool, field, value):
    owner = controller(pool)
    request, binding = owner.begin("1" * 32, pool["request"], source_sha256=pool["sha"])
    binding[field] = value
    binding["binding_sha256"] = judge.digest(
        {k: v for k, v in binding.items() if k != "binding_sha256"}
    )
    with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
        conn.execute("UPDATE claims SET payload=?", (json.dumps(binding),))
    with pytest.raises(ValueError):
        judge.verify_judge_binding(binding, request, binding["run_id"])


def test_expiry_refuses_new_dispatch_but_allows_honest_final_settlement(pool, monkeypatch):
    owner, _, binding, ledger = begin(pool)
    charge(binding, ledger)
    monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 15, 20, tzinfo=UTC))
    assert not owner.available
    with pytest.raises(AllocationRefused, match="EXPIRED"):
        ledger.reserve(binding["run_id"], "late", ".01")
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    with pytest.raises(AllocationRefused, match="EXPIRED"):
        owner.begin("2" * 32, pool["request"], source_sha256=pool["sha"])


@pytest.mark.parametrize("actual,cleanup", [(None, True), (".1", False)])
def test_unknown_or_unclean_stops_pool_without_fallback(pool, actual, cleanup):
    owner, _, binding, ledger = begin(pool)
    charge(binding, ledger, actual)
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=cleanup)
    assert result["status"] == "blocked"
    assert (
        result["actual_usd"] is None
        if actual is None
        else Decimal(result["actual_usd"]) == Decimal(actual)
    )
    assert not controller(pool).available
    with pytest.raises(ValueError):
        controller(pool).begin("2" * 32, pool["request"], source_sha256=pool["sha"])


def test_full_pool_and_run_caps_are_enforced(pool):
    ledger = BudgetLedger(pool["receipt"]["ledger_path"], daily_limit="6.61", total_limit="6.61")
    ledger.open_run("prior", "6.60")
    ledger.reserve("prior", "prior-charge", "6.60")
    ledger.settle("prior", "prior-charge", "6.60")
    ledger.close_run("prior")
    owner, request, binding, bounded = begin(pool)
    assert Decimal(request.budget_usd) == Decimal(".01")
    with pytest.raises(BudgetExceeded):
        bounded.reserve(binding["run_id"], "too-much", ".02")
    bounded.reserve(binding["run_id"], "last", ".01")
    bounded.settle(binding["run_id"], "last", ".01")
    bounded.close_run(binding["run_id"])
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )
    assert not owner.available


def test_concurrent_claims_share_one_pool_and_do_not_double_admit(pool):
    barrier = Barrier(2)

    def attempt(index):
        barrier.wait()
        try:
            return controller(pool).begin(
                f"{index:032x}", pool["request"], source_sha256=pool["sha"]
            )[1]
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(attempt, [1, 2]))
    assert sum(item is not None for item in results) == 1


def test_bound_worker_uses_normal_services_budget_factory(pool):
    owner = controller(pool)
    request, binding = owner.begin("1" * 32, pool["request"], source_sha256=pool["sha"])
    calls = []

    def worker(request, *, store, run_root, run_id, services):
        assert services.runtime_factory is None
        ledger = services.budget_factory(
            run_id, request, read_live_profile(pool["receipt"]["profile_path"])
        )
        ledger.open_run(run_id, request.budget_usd)
        calls.append(str(ledger.path))
        ledger.close_run(run_id)
        return {"status": "needs_human", "target_met": False}

    result = judge.run_bound_judge(
        request,
        store=None,
        run_root=pool["root"] / "runs",
        run_id=binding["run_id"],
        binding=binding,
        worker=worker,
    )
    assert result["status"] == "needs_human" and calls == [pool["receipt"]["ledger_path"]]
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )


def test_real_runtime_sdk_mock_uses_only_new_ledger(pool):
    owner, _request, binding, ledger = begin(pool)
    store = Store(pool["root"] / "store.fixture.db")
    store.create_run(binding["run_id"], status="running")
    observed = []

    def respond(request):
        body = json.loads(request.content)
        observed.append(body["model"])
        return httpx.Response(
            200,
            json={
                "id": "offline",
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
        profile=read_live_profile(pool["receipt"]["profile_path"]),
        budget=ledger,
        store=store,
        env_file=pool["credential"],
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    try:
        bundle.client.complete(
            "patcher", [{"role": "user", "content": "offline fixture"}], max_tokens=20
        )
    finally:
        bundle.close()
        store.close()
    ledger.close_run(binding["run_id"])
    state = _budget_state(pool["receipt"])
    assert len(observed) == len(state["attempts"]) == 1
    assert state["known"] and state["charged"] > 0
    assert (
        owner.finish(binding, execution_terminal=True, cleanup_verified=True)["status"] == "settled"
    )


def test_verified_conservative_charge_remains_distinct_from_actual(pool):
    owner, _, binding, ledger = begin(pool)
    ledger.reserve(binding["run_id"], "bounded", ".03")
    ledger.settle_upper_bound(
        binding["run_id"], "bounded", ".02", basis="verified_tariff_missing_cache_count"
    )
    ledger.close_run(binding["run_id"])
    result = owner.finish(binding, execution_terminal=True, cleanup_verified=True)
    assert result["status"] == "settled" and result["cost_resolved"] is True
    assert result["actual_usd"] is None and Decimal(result["charged_usd"]) == Decimal(".02")
    assert result["cost_basis"] == "conservative_bound" and controller(pool).available


@pytest.mark.parametrize("name", ["receipt.json", "runtime-profile.json", "budget.db", "claims.db"])
def test_symlinked_judge_files_are_rejected(pool, name):
    path = pool["path"].parent / name
    preserved = path.with_suffix(".preserved")
    path.rename(preserved)
    path.symlink_to(preserved)
    with pytest.raises(ValueError):
        controller(pool)


def test_missing_authorization_or_wrong_expected_hash_never_bootstraps(pool, tmp_path):
    other = tmp_path / "new-project"
    other.mkdir()
    with pytest.raises(ValueError):
        judge.prepare_judge_plan(pool["plan"]["profile"], {}, project_root=other)
    plan = judge.prepare_judge_plan(
        pool["plan"]["profile"], pool["plan"]["authorization"], project_root=other
    )
    with pytest.raises(ValueError, match="PLAN_CHANGED"):
        judge.activate_judge_allocation(plan, project_root=other, expected_sha256="0" * 64)
    assert not (other / ".cache").exists()


@pytest.mark.parametrize("change", ["expiry", "source", "profile", "claim"])
def test_dispatch_rechecks_after_reservation(pool, monkeypatch, change):
    _, _, binding, ledger = begin(pool)
    ledger.reserve(binding["run_id"], "unsent", ".01", dispatched=False)
    if change == "expiry":
        monkeypatch.setattr(judge, "_now", lambda: datetime(2026, 12, 15, 20, tzinfo=UTC))
    elif change == "source":
        pool["source"].write_text("changed = True\n")
    elif change == "profile":
        Path(pool["receipt"]["profile_path"]).write_text("{}")
    else:
        with sqlite3.connect(pool["receipt"]["claims_path"]) as conn:
            conn.execute("UPDATE claims SET state='settled'")
    with pytest.raises(ValueError):
        ledger.mark_dispatched(binding["run_id"], "unsent")
    state = _budget_state(pool["receipt"])
    assert state["attempts"][0]["dispatched"] == 0
    ledger.cancel_undispatched(binding["run_id"], "unsent")
    assert _budget_state(pool["receipt"])["charged"] == 0


def test_dispatch_pending_exception_is_exact_and_does_not_ignore_other_unknowns(pool):
    _, request, binding, ledger = begin(pool)
    ledger.reserve(binding["run_id"], "unsent", ".01", dispatched=False)
    with pytest.raises(ValueError):
        judge.verify_judge_binding(binding, request, binding["run_id"], pending_attempt_id="other")
    with ledger._transaction() as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(budget_attempts)")]
        row = dict(conn.execute("SELECT * FROM budget_attempts WHERE id='unsent'").fetchone())
        row.update(id="other-unknown", dispatched=1)
        conn.execute(
            f"INSERT INTO budget_attempts ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            [row[name] for name in columns],
        )
    with pytest.raises(ValueError):
        ledger.mark_dispatched(binding["run_id"], "unsent")
    assert _budget_state(pool["receipt"])["attempts"][0]["dispatched"] == 0
