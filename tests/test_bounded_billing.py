"""Offline bounded-charge and explicit retention contracts; never live billing."""

import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import httpx
import pytest

from headroom.billing_review import execute_retention, prepare_retention
from headroom.budget import BudgetExceeded, BudgetLedger, RunBudgetReached
from headroom.config import candidate_models
from headroom.llm.cost import Pricing, Usage, calculate_cost
from headroom.runtime import LiveProfile, build_live_runtime
from headroom.store.db import Store

BASIS = "verified_tariff_missing_cache_count"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("Bounded billing tests cannot access DNS/INET")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def profile_data():
    return {
        "live_enabled": True,
        "credit_confirmed": True,
        "available_credit_usd": "2",
        "authorized_total_usd": "2",
        "verified_at": "offline fixture",
        "evidence": "offline fixture",
        "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
        "evidence_token_budget": 1000,
        "run_budget_mode": "actual_usage",
        "models": {
            role: {
                "model_id": model.model_id,
                "input_usd_per_million": "1",
                "output_usd_per_million": "2",
                "cached_input_usd_per_million": "0.25",
                "evidence": "offline fixture",
                "billing": {
                    "prompt_token_ceiling": 1000,
                    "max_prompt_utf8_bytes": 100000,
                    "max_completion_tokens": 4000,
                    "output_cap_field": "max_tokens",
                    "output_cap_includes_reasoning": True,
                    "verified": True,
                    "evidence": "offline fixture",
                },
            }
            for role, model in candidate_models().items()
        },
    }


def response(request, *, model=None, usage=None):
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "id": "offline-bounded",
            "object": "chat.completion",
            "created": 0,
            "model": model if model is not None else body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "{}"},
                }
            ],
            "usage": usage
            if usage is not None
            else {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        },
    )


def runtime(tmp_path, handler, *, run_limit="0.6", data=None):
    profile = LiveProfile.model_validate(data or profile_data())
    env = tmp_path / ".env-fixture"
    env.write_text("NEBIUS_API_KEY=offline-fixture\n")
    env.chmod(0o600)
    store = Store(tmp_path / "store.db")
    store.create_run("r")
    budget = BudgetLedger(tmp_path / "budget.db", total_limit="2", daily_limit="2")
    budget.open_run("r", run_limit, budget_mode="actual_usage")
    bundle = build_live_runtime(
        "r",
        profile=profile,
        budget=budget,
        store=store,
        env_file=env,
        transport=httpx.MockTransport(handler),
    )
    bundle.client._sleep = lambda _: None
    return bundle, budget, store


@pytest.mark.parametrize("cached,upper", [("0.012", "0.00033378"), ("0.12", "0.00055236")])
def test_missing_cache_has_explicit_upper_not_zero_or_actual(cached, upper):
    result = calculate_cost(
        Usage(3643, 480, 4123),
        Pricing("0.06", "0.24", cached, verified=True, source="fixture"),
    )
    assert result.usd is None and result.status == "upper_bound"
    assert result.upper_usd == Decimal(upper)
    assert result.basis == BASIS
    assert result.as_dict()["usd"] is None


def test_exact_cache_zero_stays_exact_and_unknown_price_stays_unknown():
    prices = Pricing("1", "2", "0.25", verified=True, source="fixture")
    cost = calculate_cost(Usage(10, 5, 15, cached_tokens=0), prices)
    assert cost.as_dict() == {"usd": "0.00002", "status": "known", "reason": None}
    assert calculate_cost(None, prices).status == "unknown"
    assert calculate_cost(Usage(10, 5, 15), Pricing("1", "2", "0.25")).status == "unknown"


def test_real_sdk_bounded_response_can_continue_with_actual_still_null(tmp_path):
    requests = []

    def handler(request):
        requests.append(request)
        return response(request)

    bundle, budget, store = runtime(tmp_path, handler)
    try:
        first = bundle.router.chat("diagnose", [{"role": "user", "content": "x"}], max_tokens=20)
        bundle.router.chat("diagnose", [{"role": "user", "content": "y"}], max_tokens=20)
        assert len(requests) == 2 and first.cost.usd is None
        snapshot = budget.snapshot("r")
        assert snapshot["bounded_attempts"] == 2 and snapshot["unknown_attempts"] == 2
        assert snapshot["unresolved_attempts"] == 0 and snapshot["billing_complete"]
        assert snapshot["total_actual_usd"] is None
        assert Decimal(snapshot["conservative_total_usd"]) == Decimal("0.00004")
        assert not snapshot["dispatch_blocked"]
        calls = store.llm_calls("r")
        assert all(call["billing_status"] == "bounded" for call in calls)
        assert all(call["cost_usd"] is None for call in calls)
        with sqlite3.connect(budget.path) as conn:
            ledger_ids = {
                row[0] for row in conn.execute("SELECT id FROM budget_attempts WHERE run_id='r'")
            }
        assert {call["budget_attempt_id"] for call in calls} == ledger_ids
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize(
    "failure", ["identity", "invalid_usage", "prompt_bound", "output_bound", "http"]
)
def test_other_uncertainty_or_cap_failure_cannot_become_bounded(tmp_path, failure):
    requests = []

    def handler(request):
        requests.append(request)
        if failure == "http":
            return httpx.Response(429, json={"error": {"message": "fixture"}})
        if failure == "identity":
            return response(request, model="wrong-model")
        if failure == "invalid_usage":
            return response(
                request, usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 99}
            )
        if failure == "prompt_bound":
            return response(
                request, usage={"prompt_tokens": 1001, "completion_tokens": 5, "total_tokens": 1006}
            )
        return response(
            request, usage={"prompt_tokens": 10, "completion_tokens": 21, "total_tokens": 31}
        )

    bundle, budget, store = runtime(tmp_path, handler)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "x"}], max_tokens=20)
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "again"}], max_tokens=20)
        state = budget.snapshot("r")
        assert len(requests) == 1
        assert state["unresolved_attempts"] == 1 and not state["billing_complete"]
        assert state["dispatch_blocked"] and state["bounded_attempts"] == 0
    finally:
        bundle.close()
        store.close()


def test_conservative_stop_does_not_claim_actual_overspend(tmp_path):
    b = BudgetLedger(tmp_path / "b.db", total_limit="2", daily_limit="2")
    b.open_run("r", "0.1", budget_mode="actual_usage")
    b.reserve("r", "a", "0.3")
    with pytest.raises(RunBudgetReached) as caught:
        b.settle_upper_bound("r", "a", "0.11", basis=BASIS)
    assert caught.value.basis == "conservative_bound"
    state = b.snapshot("r")
    assert state["total_actual_usd"] is None and state["billing_complete"]
    assert state["run_budget_basis"] == "conservative_bound"
    with pytest.raises(RunBudgetReached):
        b.reserve("r", "b", "0.01")


def test_bounded_charge_survives_reopen_and_consumes_shared_pool(tmp_path):
    path = tmp_path / "b.db"
    b = BudgetLedger(path, total_limit="1", daily_limit="1")
    b.open_run("r", "0.5", budget_mode="actual_usage")
    b.reserve("r", "a", "0.4")
    b.settle_upper_bound("r", "a", "0.3", basis=BASIS)
    b.close_run("r")
    b = BudgetLedger(path, total_limit="1", daily_limit="1")
    assert b.snapshot("r")["billing_complete"]
    b.open_run("next", "0.5", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded):
        b.reserve("next", "large", "0.8")
    b.reserve("next", "small", "0.6")


def test_bound_above_reservation_keeps_halt_and_cannot_be_reviewed(tmp_path):
    b = BudgetLedger(tmp_path / "b.db", total_limit="2", daily_limit="2")
    b.open_run("r", "0.6", budget_mode="actual_usage")
    b.reserve("r", "a", "0.1")
    with pytest.raises(BudgetExceeded):
        b.settle_upper_bound("r", "a", "0.2", basis=BASIS)
    state = b.close_run("r")
    assert state["halt_reason"] == "provider_bound_exceeded"
    assert state["conservative_charge_usd"] == "0.2"
    assert not state["billing_complete"]


def history(tmp_path):
    data = profile_data()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(data))
    ledger_path, store_path = tmp_path / "budget.db", tmp_path / "store.db"
    b = BudgetLedger(ledger_path, total_limit="2", daily_limit="2")
    b.open_run("r", "0.6", budget_mode="actual_usage")
    b.reserve("r", "a", "0.00104")
    b.settle("r", "a", None)
    b.close_run("r")
    store = Store(store_path)
    store.create_run("r")
    model = data["models"]["nano"]["model_id"]
    store.add_llm_call(
        "r",
        {
            "model": model,
            "role": "annotate",
            "attempt": 1,
            "outcome": "response",
            "settled": True,
            "admission_kind": "verified_provider_bound",
            "provider_prompt_token_ceiling": 1000,
            "provider_cost_upper_usd": "0.00104",
            "reservation_usd": "0.00104",
            "output_cap_field": "max_tokens",
            "output_cap_tokens": 20,
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "cached_tokens": None,
                "reasoning_tokens": None,
            },
            "cost": {"usd": None, "status": "unknown", "reason": "missing_cached_token_usage"},
            "http_status": 200,
            "response_model": model,
        },
    )
    store.close()
    kwargs = {
        "ledger_path": ledger_path,
        "store_path": store_path,
        "profile_path": profile_path,
        "run_id": "r",
        "attempt_id": "a",
    }
    return b, kwargs


def receipt(tmp_path, kwargs):
    value = prepare_retention(**kwargs)
    p = tmp_path / "review.json"
    p.write_text(json.dumps(value, indent=2) + "\n")
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def test_review_preparation_is_read_only_and_execution_retains_entire_upper(tmp_path):
    b, kwargs = history(tmp_path)
    before = b.snapshot("r")
    p, sha = receipt(tmp_path, kwargs)
    assert b.snapshot("r") == before
    result = execute_retention(
        p, expected_sha256=sha, reviewed_by="offline-reviewer", daily_limit="2"
    )
    assert result["total_actual_usd"] is None
    assert result["conservative_charge_usd"] == "0.00104"
    assert result["reviewed_retained_attempts"] == 1 and result["billing_complete"]
    assert result["halt_reason"] is None
    b = BudgetLedger(kwargs["ledger_path"], total_limit="2", daily_limit="2")
    b.open_run("next", "0.6", budget_mode="actual_usage")
    assert b.snapshot("r")["conservative_charge_usd"] == "0.00104"
    with sqlite3.connect(kwargs["store_path"]) as conn:
        assert conn.execute("SELECT cost_usd FROM llm_calls").fetchone()[0] is None
    with pytest.raises(ValueError):
        execute_retention(p, expected_sha256=sha, reviewed_by="offline-reviewer", daily_limit="2")


@pytest.mark.parametrize("mutation", ["receipt", "metadata", "profile", "attempt", "halt"])
def test_changed_review_evidence_never_unlocks_unknown(tmp_path, mutation):
    b, kwargs = history(tmp_path)
    p, sha = receipt(tmp_path, kwargs)
    if mutation == "receipt":
        p.write_text(p.read_text() + " ")
    elif mutation == "metadata":
        with sqlite3.connect(kwargs["store_path"]) as conn:
            conn.execute("UPDATE llm_calls SET model='wrong'")
    elif mutation == "profile":
        data = json.loads(kwargs["profile_path"].read_text())
        data["models"]["nano"]["input_usd_per_million"] = "2"
        kwargs["profile_path"].write_text(json.dumps(data))
    else:
        with sqlite3.connect(kwargs["ledger_path"]) as conn:
            if mutation == "attempt":
                conn.execute("UPDATE budget_attempts SET settled=0")
            else:
                conn.execute("UPDATE budget_runs SET halt_reason='provider_bound_unresolved'")
    with pytest.raises((ValueError, TypeError)):
        execute_retention(p, expected_sha256=sha, reviewed_by="offline-reviewer", daily_limit="2")
    assert b.snapshot("r")["dispatch_blocked"]


def test_concurrent_review_cannot_replay_or_release_reservation(tmp_path):
    b, kwargs = history(tmp_path)
    p, sha = receipt(tmp_path, kwargs)

    def apply(_):
        try:
            execute_retention(p, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
            return True
        except (ValueError, sqlite3.IntegrityError):
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(apply, range(2))) == 1
    assert b.snapshot("r")["conservative_charge_usd"] == "0.00104"


@pytest.mark.parametrize("failure", ["reservation_exceeded", "database_failure"])
def test_runtime_never_exports_bounded_before_settlement_commits(tmp_path, monkeypatch, failure):
    from headroom.llm.cost import Cost

    bundle, budget, store = runtime(tmp_path, response)
    try:
        if failure == "reservation_exceeded":
            monkeypatch.setattr(
                "headroom.llm.client.calculate_cost",
                lambda *args: Cost(
                    None, "upper_bound", "missing_cached_token_usage", Decimal("0.01"), BASIS
                ),
            )
        else:

            def fail(*args, **kwargs):
                raise sqlite3.OperationalError("offline database failure")

            monkeypatch.setattr(budget, "settle_upper_bound", fail)
        with pytest.raises((BudgetExceeded, sqlite3.OperationalError)):
            bundle.router.chat("diagnose", [{"role": "user", "content": "x"}], max_tokens=20)
        call = store.llm_calls("r")[0]
        assert call["billing_status"] == "unresolved"
        assert call.get("cost_upper_usd") is None
        snapshot = budget.snapshot("r")
        assert not snapshot["billing_complete"] and snapshot["dispatch_blocked"]
        assert snapshot["bounded_attempts"] == 0
        assert Decimal(snapshot["conservative_charge_usd"]) >= Decimal("0.00104")
    finally:
        bundle.close()
        store.close()


def test_postcommit_run_stop_exports_bound_without_claiming_actual_cost(tmp_path):
    bundle, budget, store = runtime(tmp_path, response, run_limit="0.00001")
    try:
        with pytest.raises(RunBudgetReached) as caught:
            bundle.router.chat("diagnose", [{"role": "user", "content": "x"}], max_tokens=20)
        assert caught.value.basis == "conservative_bound"
        call = store.llm_calls("r")[0]
        assert call["billing_status"] == "bounded" and call["cost_usd"] is None
        assert call["cost_upper_usd"] == "0.00002"
        state = budget.snapshot("r")
        assert state["billing_complete"]
        assert state["remaining_basis"] == state["run_limit_basis"] == "conservative_bound"
    finally:
        bundle.close()
        store.close()


def test_review_cannot_clear_an_unrelated_unknown_or_cross_run(tmp_path):
    b, kwargs = history(tmp_path)
    p, sha = receipt(tmp_path, kwargs)
    altered = json.loads(p.read_text())
    altered["run_id"] = "unrelated"
    changed = tmp_path / "wrong-run.json"
    changed.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        execute_retention(
            changed,
            expected_sha256=hashlib.sha256(changed.read_bytes()).hexdigest(),
            reviewed_by="fixture",
            daily_limit="2",
        )
    with sqlite3.connect(kwargs["ledger_path"]) as conn:
        conn.execute(
            "INSERT INTO budget_runs(id,day,limit_usd,status,halt_reason,budget_mode) "
            "SELECT 'other',day,'0.6','closed','provider_charge_unknown',budget_mode FROM budget_runs WHERE id='r'"
        )
        conn.execute(
            "INSERT INTO budget_attempts(id,run_id,upper_usd,charged_usd,actual_usd,settled,"
            "admission_kind,dispatched,charge_status) "
            "VALUES ('other-a','other','0.2','0.2',NULL,1,'verified_provider_bound',1,'unknown')"
        )
    execute_retention(p, expected_sha256=sha, reviewed_by="fixture", daily_limit="2")
    assert b.snapshot("r")["billing_complete"]
    assert b.snapshot("r")["dispatch_blocked"]
    with pytest.raises(BudgetExceeded):
        b.open_run("new", "0.1", budget_mode="actual_usage")


def test_cli_default_only_prepares_and_execute_requires_explicit_review(
    tmp_path, monkeypatch, capsys
):
    from headroom.billing_review import main

    b, kwargs = history(tmp_path)
    before = b.snapshot("r")
    monkeypatch.setattr(
        "sys.argv",
        [
            "review",
            "--ledger",
            str(kwargs["ledger_path"]),
            "--store",
            str(kwargs["store_path"]),
            "--profile",
            str(kwargs["profile_path"]),
            "--run-id",
            "r",
            "--attempt-id",
            "a",
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["actual_usd"] is None
    assert b.snapshot("r") == before
    monkeypatch.setattr("sys.argv", ["review", "--execute"])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == 2
    assert b.snapshot("r") == before


def test_nano_budget_uses_committed_bound_not_old_full_reservation(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return response(request)

    bundle, budget, store = runtime(tmp_path, handler)
    try:
        for _ in range(3):
            bundle.router.chat("annotate", [{"role": "user", "content": "x"}], max_tokens=4000)
        assert len(calls) == 3
        assert Decimal(budget.snapshot("r")["conservative_total_usd"]) == Decimal("0.00006")
    finally:
        bundle.close()
        store.close()


def test_exact_charge_with_cap_violation_is_not_billing_complete(tmp_path):
    def handler(request):
        return response(
            request,
            usage={
                "prompt_tokens": 10,
                "completion_tokens": 21,
                "total_tokens": 31,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        )

    bundle, budget, store = runtime(tmp_path, handler)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "x"}], max_tokens=20)
        call = store.llm_calls("r")[0]
        assert call["cost_usd"] is not None
        assert call["billing_status"] == "unresolved"
        assert not budget.snapshot("r")["billing_complete"]
    finally:
        bundle.close()
        store.close()
