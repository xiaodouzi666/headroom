"""Offline end-to-end accounting: a run stop line is not a per-request hard cap."""

import json
import shutil
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
from test_runtime_budget import fixture_runtime

from headroom.budget import BudgetExceeded, BudgetLedger, RunBudgetReached
from headroom.report import build_report, render_markdown
from headroom.runtime import LiveProfile, RuntimeNotReady, build_live_runtime
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Real DNS/INET is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def ledger(tmp_path, *, total="3", daily="3"):
    return BudgetLedger(tmp_path / "ledger.db", total_limit=total, daily_limit=daily)


def test_default_strict_still_rejects_full_ultra_bound(tmp_path):
    b = ledger(tmp_path)
    b.open_run("strict", "0.6")
    with pytest.raises(BudgetExceeded, match="Run budget"):
        b.reserve("strict", "no", "1.060576")
    assert b.snapshot("strict")["run_budget_mode"] == "strict_reservation"


@pytest.mark.parametrize("total,daily", [(None, "3"), ("0", "3"), ("3", "0")])
def test_actual_mode_requires_positive_global_and_daily_pools(tmp_path, total, daily):
    with pytest.raises(BudgetExceeded, match="pools"):
        ledger(tmp_path, total=total, daily=daily).open_run("a", "0.6", budget_mode="actual_usage")


def test_actual_mode_reserves_full_global_bound_then_releases_unused(tmp_path):
    b = ledger(tmp_path)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    b.reserve("a", "first", "1.060576")
    pending = b.snapshot("a")
    assert pending["reserved_or_actual_usd"] == "1.060576"
    assert pending["remaining_usd"] == "0.6"
    assert pending["dispatch_blocked"]
    b.settle("a", "first", "0.03")
    b.reserve("a", "second", "1.060576")
    b.settle("a", "second", "0.04")
    result = b.close_run("a")
    assert result["total_actual_usd"] == "0.07"
    assert not result["run_budget_reached"]


@pytest.mark.parametrize("total,daily", [("1", "3"), ("3", "1")])
def test_full_bound_must_fit_each_pool_before_dispatch(tmp_path, total, daily):
    b = ledger(tmp_path, total=total, daily=daily)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded, match="pool"):
        b.reserve("a", "too-large", "1.060576")
    assert b.snapshot("a")["pending_attempts"] == 0


def test_other_open_run_floor_is_not_spent_by_actual_mode(tmp_path):
    b = ledger(tmp_path, total="1.5")
    b.open_run("a", "0.6", budget_mode="actual_usage")
    b.open_run("b", "0.6")
    with pytest.raises(BudgetExceeded, match="Total"):
        b.reserve("a", "too-large", "1.060576")
    b.close_run("b")
    b.reserve("a", "allowed", "1.060576")


def test_actual_mode_cannot_reserve_estimate(tmp_path):
    b = ledger(tmp_path)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded, match="local estimates"):
        b.reserve("a", "estimate", "0.05", admission_kind="local_estimate")


@pytest.mark.parametrize("actual,exceeded", [("0.6", False), ("0.600001", True)])
def test_reaching_line_commits_actual_then_stops_only_that_run(tmp_path, actual, exceeded):
    b = ledger(tmp_path)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    b.open_run("b", "0.6", budget_mode="actual_usage")
    b.reserve("a", "one", "1.060576")
    with pytest.raises(RunBudgetReached) as error:
        b.settle("a", "one", actual)
    assert error.value.exceeded is exceeded
    state = b.close_run("a")
    assert state["run_budget_reached"] and state["run_budget_exceeded"] is exceeded
    assert state["total_actual_usd"] == actual and state["halt_reason"] is None
    b.reserve("b", "other", "1.060576")


def test_restarted_run_cannot_continue_after_actual_limit(tmp_path):
    b = ledger(tmp_path)
    b.open_run("a", "0.05", budget_mode="actual_usage")
    b.reserve("a", "one", "1.060576")
    with pytest.raises(RunBudgetReached):
        b.settle("a", "one", "0.05")
    with pytest.raises(RunBudgetReached):
        ledger(tmp_path).reserve("a", "again", "1.060576")


def test_actual_unknown_closed_and_restarted_still_blocks_all_runs(tmp_path):
    b = ledger(tmp_path)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    b.open_run("b", "0.6")
    b.reserve("a", "one", "1.060576")
    b.settle("a", "one", None)
    b.close_run("a")
    with pytest.raises(BudgetExceeded, match="billing"):
        ledger(tmp_path).reserve("b", "another", "0.01")
    assert b.snapshot("a")["reserved_or_actual_usd"] == "1.060576"


def test_actual_mode_atomic_competing_instances(tmp_path):
    b = ledger(tmp_path)
    for run in ("a", "b"):
        b.open_run(run, "0.6", budget_mode="actual_usage")

    def attempt(run):
        try:
            ledger(tmp_path).reserve(run, run, "1.060576")
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(attempt, ("a", "b"))) == 1


def reviewed_fixture(tmp_path):
    profile = fixture_runtime(tmp_path, None, profile_only=True, prompt_ceiling=1048576)
    data = profile.model_dump()
    data.update(run_budget_mode="actual_usage", available_credit_usd="3", authorized_total_usd="3")
    data["models"]["ultra"]["billing"]["max_completion_tokens"] = 8192
    data["models"]["ultra"]["capabilities"] = {
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline fixture only",
    }
    data["models"]["super"]["capabilities"] = {
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline fixture only",
    }
    return LiveProfile.model_validate(data)


@pytest.mark.parametrize("actual_tokens,exceeded", [(599980, False), (600000, True)])
def test_real_router_records_response_even_when_settlement_stops_run(
    tmp_path, actual_tokens, exceeded
):
    profile = reviewed_fixture(tmp_path)
    calls = []

    def respond(request):
        calls.append(request)
        return response(request, actual_tokens)

    b = ledger(tmp_path)
    b.open_run("a", "0.6", budget_mode="actual_usage")
    store = Store(tmp_path / "store.db")
    store.create_run("a")
    bundle = build_live_runtime(
        "a",
        profile=profile,
        budget=b,
        store=store,
        env_file=tmp_path / ".env",
        transport=httpx.MockTransport(respond),
    )
    try:
        with pytest.raises(RunBudgetReached) as error:
            bundle.router.chat("diagnose", [{"role": "user", "content": "offline"}])
        assert error.value.exceeded is exceeded
        rows = store.llm_calls("a")
        assert len(rows) == len(calls) == 1
        assert rows[0]["outcome"] == "response" and rows[0]["settled"] is True
        assert store.usage("a")["total_cost_usd"] == b.snapshot("a")["total_actual_usd"]
        with pytest.raises(RunBudgetReached):
            bundle.router.chat("diagnose", [{"role": "user", "content": "no second call"}])
        assert len(calls) == 1
    finally:
        bundle.close()
        store.close()


def response(request, prompt_tokens):
    return httpx.Response(
        200,
        json={
            "id": "offline",
            "object": "chat.completion",
            "created": 0,
            "model": json.loads(request.content)["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "{}"},
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": 10,
                "total_tokens": prompt_tokens + 10,
            },
        },
    )


def test_profile_rejects_unverified_bound_and_mode_mismatch_before_key(tmp_path, monkeypatch):
    profile = reviewed_fixture(tmp_path)
    profile.models["ultra"].billing.verified = False
    with pytest.raises(RuntimeNotReady, match="strict provider"):
        profile.runtime_config()
    profile.models["ultra"].billing.verified = True
    b = ledger(tmp_path)
    b.open_run("a", "0.6")
    monkeypatch.setattr(
        "headroom.runtime.read_nebius_key",
        lambda *args: pytest.fail("Must reject before credential read"),
    )
    with pytest.raises(RuntimeNotReady, match="mode differs"):
        build_live_runtime("a", profile=profile, budget=b, store=None)


@pytest.mark.parametrize("cost,accepted", [("0.6", True), ("0.60002", False)])
def test_report_distinguishes_reached_from_exceeded_and_retains_candidate(cost, accepted):
    doc = build_report(
        {
            "status": "budget_exceeded",
            "target_met": True,
            "budget": {
                "run_budget_mode": "actual_usage",
                "limit_usd": "0.6",
                "total_actual_usd": cost,
                "run_budget_reached": True,
                "run_budget_exceeded": not accepted,
            },
        },
        verification={
            "target_met": True,
            "completed": True,
            "after": {"status": "completed", "peak_allocated_bytes": 100},
        },
    )
    assert doc["summary"]["target_met"] is accepted
    assert doc["summary"]["cost_within_run_limit"] is accepted
    assert doc["verification"]["target_met"] is True
    assert "not a hard maximum charge" in render_markdown(doc)


@pytest.mark.parametrize("daily,expected_calls", [("3", 1), ("0.1", 0)])
def test_original_small_run_and_daily_guards_write_real_partial_report(
    tmp_path, monkeypatch, daily, expected_calls
):
    from headroom import orchestrator
    from headroom.orchestrator import FixRequest, Services, run_fix

    project = tmp_path / "project"
    project.mkdir()
    profile = reviewed_fixture(project)
    path = project / "profile.json"
    path.write_text(profile.model_dump_json())
    source = project / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text("VALUE = 1\n")
    monkeypatch.setattr(orchestrator, "PROJECT_ROOT", project)
    if daily == "3":
        monkeypatch.setenv("HEADROOM_RUN_BUDGET_USD", "0.05")
    else:
        monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "0.1")
    calls = []

    def runtime(run_id, **kwargs):
        kwargs.update(
            env_file=project / ".env",
            transport=httpx.MockTransport(
                lambda request: calls.append(request) or response(request, 50000)
            ),
        )
        return build_live_runtime(run_id, **kwargs)

    monkeypatch.setattr(orchestrator, "build_live_runtime", runtime)

    def baseline(script, **kwargs):
        directory = Path(kwargs["run_root"]) / "fixture"
        directory.mkdir(parents=True)
        shutil.copytree(source, directory / "source")
        return {
            "run_id": "fixture",
            "run_dir": str(directory),
            "status": "oom",
            "peak_alloc_gb": 2.0,
            "env": {"seed": 1337},
            "loss_series": [],
        }

    def evidence(run, *, output_dir, **kwargs):
        output_dir.mkdir(parents=True)
        analysis = {"stack_catalog": {"stk_fixture": []}}
        (output_dir / "evidence.json").write_text(json.dumps({"analysis": analysis}))
        (output_dir / "evidence.md").write_text("Offline fixture stk_fixture.")
        return {
            "analysis": analysis,
            "token_count": 10,
            "evidence_json": str(output_dir / "evidence.json"),
            "evidence_md": str(output_dir / "evidence.md"),
        }

    store = Store(project / "store.db")
    try:
        result = run_fix(
            FixRequest(script=str(script), runtime_profile=str(path), research_enabled=False),
            store=store,
            run_root=project / "jobs",
            services=Services(baseline=baseline, evidence=evidence, provenance="offline_fixture"),
        )
        assert result["status"] == "budget_exceeded"
        assert result["target_met"] is False
        assert len(calls) == expected_calls
        assert "budget.exceeded" in [event["kind"] for event in store.events(result["run_id"])]
        assert Path(result["report_md"]).is_file()
        if expected_calls:
            doc = json.loads(Path(result["report_json"]).read_text())
            assert doc["budget"]["actual_usd"] == "0.05002"
            assert result["budget"]["total_actual_usd"] == "0.05002"
            assert doc["summary"]["cost_within_run_limit"] is False
            assert store.usage(result["run_id"])["total_cost_usd"] == "0.05002"
            assert doc["usage"]["calls"] == 1
    finally:
        store.close()


@pytest.mark.parametrize(
    "fault", ["overrun", "missing_usage", "http_429", "network", "pending", "bound_invalid"]
)
def test_kept_success_then_unverified_cost_is_not_run_success(tmp_path, monkeypatch, fault):
    import test_orchestrator as fixtures

    from headroom import orchestrator
    from headroom.orchestrator import RunCancelled

    profile = reviewed_fixture(tmp_path)
    monkeypatch.setattr(orchestrator, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(orchestrator, "read_live_profile", lambda *args: profile)
    real_services = fixtures.Services
    factory = {}
    count = []

    def services(**kwargs):
        factory["make"] = kwargs.pop("runtime_factory")
        return real_services(**kwargs)

    monkeypatch.setattr(fixtures, "Services", services)

    def runtime(run_id, **kwargs):
        fixture = factory["make"](
            run_id, kwargs["store"], Path(kwargs["store"].get_run(run_id)["run_dir"])
        )
        original_settle = kwargs["budget"].settle

        def settle(*args, **values):
            if len(count) == 3 and fault == "pending":
                raise RunCancelled("Offline interruption before ledger settlement")
            return original_settle(*args, **values)

        kwargs["budget"].settle = settle

        def respond(request):
            result = fixture.client._transport.handle_request(request)
            payload = result.json()
            count.append(request)
            if len(count) == 3:
                if fault == "overrun":
                    payload["usage"] = {
                        "prompt_tokens": 600000,
                        "completion_tokens": 10,
                        "total_tokens": 600010,
                    }
                elif fault == "missing_usage":
                    payload.pop("usage")
                elif fault == "http_429":
                    return httpx.Response(429, json={"error": {"message": "offline fixture"}})
                elif fault == "network":
                    raise httpx.ConnectError("offline fixture", request=request)
                elif fault == "bound_invalid":
                    payload["usage"] = {
                        "prompt_tokens": 10,
                        "completion_tokens": 8193,
                        "total_tokens": 8203,
                    }
            return httpx.Response(200, json=payload)

        bundle = build_live_runtime(
            run_id, **kwargs, env_file=tmp_path / ".env", transport=httpx.MockTransport(respond)
        )
        bundle.client._sleep = lambda _: None
        return bundle

    monkeypatch.setattr(orchestrator, "build_live_runtime", runtime)
    result, store, _, verifies, _ = fixtures.search_run(
        tmp_path,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
        search_mode="bounded_pareto",
    )
    try:
        assert len(count) == 3 and len(verifies) == 1
        assert result["status"] in {"budget_exceeded", "failed", "timeout"}
        assert result["target_met"] is False
        assert result["kept"]["round"] == 1
        assert "+VALUE = 2" in Path(result["run_dir"], "patch.diff").read_text()
        assert result["report"]["summary"]["target_met"] is False
        assert result["report"]["verification"]["target_met"] is True
        assert len(store.llm_calls(result["run_id"])) == 3
        if fault == "overrun":
            assert result["budget"]["total_actual_usd"] == "0.60008"
            assert result["report"]["summary"]["cost_within_run_limit"] is False
            assert store.usage(result["run_id"])["total_cost_usd"] == "0.60008"
        else:
            b = BudgetLedger(tmp_path / ".cache/budget.db", daily_limit="3", total_limit="3")
            assert b.snapshot(result["run_id"])["dispatch_blocked"]
            with pytest.raises(BudgetExceeded):
                b.open_run("another-run", "0.1")
            if fault == "bound_invalid":
                assert result["budget"]["billing_bound_unresolved"]
                assert result["report"]["summary"]["cost_within_run_limit"] is True
            else:
                assert result["budget"]["total_actual_usd"] is None
                assert result["report"]["summary"]["cost_within_run_limit"] is None
            if fault == "pending":
                assert result["budget"]["pending_attempts"] == 1
    finally:
        store.close()


def test_actual_profile_cannot_mix_local_estimate(tmp_path):
    profile = reviewed_fixture(tmp_path).model_dump()
    profile["models"]["ultra"]["billing"] = {
        "mode": "local_estimate",
        "tokenizer_assets_dir": str(tmp_path),
        "token_multiplier": "1.5",
        "additive_tokens": 100,
        "max_prompt_utf8_bytes": 10000,
        "max_completion_tokens": 4000,
        "output_cap_field": "max_completion_tokens",
        "output_cap_includes_reasoning": True,
        "output_cap_verified": True,
        "output_cap_evidence": "offline fixture",
        "risk_acknowledged": True,
        "evidence": "offline fixture",
    }
    with pytest.raises(RuntimeNotReady, match="strict provider"):
        LiveProfile.model_validate(profile).runtime_config()


def test_shared_strict_pool_cannot_be_bypassed_by_other_profile_after_restart(tmp_path):
    b = ledger(tmp_path)
    b.open_run("legacy", "0.6")
    b.open_run("actual", "0.6", budget_mode="actual_usage")
    b.close_run("actual")
    other = ledger(tmp_path)
    assert other.snapshot("legacy")["shared_pool_requires_provider_bounds"]
    with pytest.raises(BudgetExceeded, match="local estimates"):
        other.reserve("legacy", "estimate", "0.01", admission_kind="local_estimate")
    with pytest.raises(BudgetExceeded, match="pools"):
        ledger(tmp_path, total=None).reserve("legacy", "unfunded", "0.01")
    other.reserve("legacy", "verified", "0.01")
    other.settle("legacy", "verified", "0.001")


def test_estimate_settled_before_strict_pool_activation_remains_real_cost(tmp_path):
    b = ledger(tmp_path)
    b.open_run("legacy", "0.6")
    b.reserve("legacy", "old-estimate", "0.01", admission_kind="local_estimate")
    b.settle("legacy", "old-estimate", "0.005")
    b.close_run("legacy")
    b.open_run("actual", "0.6", budget_mode="actual_usage")
    assert b.snapshot("legacy")["total_actual_usd"] == "0.005"
    b.reserve("actual", "strict", "1.060576")


@pytest.mark.parametrize(
    "state",
    [
        {"total_actual_usd": None, "unknown_attempts": 1},
        {"total_actual_usd": None, "pending_attempts": 1},
        {"total_actual_usd": "0.1", "billing_bound_unresolved": True},
        {"total_actual_usd": None},
    ],
)
def test_standalone_report_unknown_run_cost_cannot_keep_overall_success(state):
    doc = build_report(
        {
            "status": "failed",
            "target_met": True,
            "budget": {
                "run_budget_mode": "actual_usage",
                "limit_usd": "0.6",
                **state,
            },
        },
        verification={"target_met": True, "after": {"status": "completed"}},
    )
    assert doc["summary"]["target_met"] is False
    assert doc["verification"]["target_met"] is True


@pytest.mark.parametrize("mode", ["strict_reservation", "actual_usage"])
def test_old_run_and_long_lived_ledger_cannot_dispatch_in_new_utc_day(tmp_path, monkeypatch, mode):
    today = ["2026-01-01"]
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: today[0])
    old = ledger(tmp_path, daily="1")
    old.open_run("old", "0.6", budget_mode=mode)
    today[0] = "2026-01-02"
    current = ledger(tmp_path, daily="1")
    current.open_run("new", "0.6", budget_mode=mode)
    for book in (old, current):
        with pytest.raises(BudgetExceeded, match="UTC day expired"):
            book.reserve("old", "refused-old", "0.4")
    with pytest.raises(BudgetExceeded, match="UTC day expired"):
        old.reserve("new", "refused-stale-ledger", "0.4")
    current.reserve("new", "allowed", "0.4")
    current.settle("new", "allowed", "0.3")
    assert current.snapshot("new")["total_actual_usd"] == "0.3"
    assert old.snapshot("old")["pending_attempts"] == 0


def test_midnight_between_reservation_and_dispatch_keeps_unsent_state(tmp_path, monkeypatch):
    today = ["2026-01-01"]
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: today[0])
    old = ledger(tmp_path, daily="2")
    old.open_run("old", "0.6", budget_mode="actual_usage")
    old.reserve("old", "held", "1.060576", dispatched=False)
    today[0] = "2026-01-02"
    with pytest.raises(BudgetExceeded, match="UTC day expired"):
        old.mark_dispatched("old", "held")
    assert old.snapshot("old")["pending_attempts"] == 1
    old.cancel_undispatched("old", "held")
    assert old.close_run("old")["total_actual_usd"] == "0"
    current = ledger(tmp_path, daily="2")
    current.open_run("new", "0.6", budget_mode="actual_usage")
    current.reserve("new", "allowed", "1.060576")


def test_dispatched_request_can_settle_after_midnight_without_losing_bill(tmp_path, monkeypatch):
    today = ["2026-01-01"]
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: today[0])
    old = ledger(tmp_path, daily="2")
    old.open_run("old", "0.6", budget_mode="actual_usage")
    old.reserve("old", "sent", "1.060576")
    today[0] = "2026-01-02"
    old.settle("old", "sent", "0.2")
    assert old.close_run("old")["total_actual_usd"] == "0.2"
    current = ledger(tmp_path, daily="2")
    current.open_run("new", "0.6", budget_mode="actual_usage")
    current.reserve("new", "allowed", "1.060576")
    current.settle("new", "allowed", "0.1")
    assert current.snapshot("new")["total_actual_usd"] == "0.1"


def test_caller_day_label_cannot_override_trusted_utc_dispatch_clock(tmp_path, monkeypatch):
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-01-01")
    future = BudgetLedger(
        tmp_path / "ledger.db", daily_limit="3", total_limit="3", day="2026-01-02"
    )
    future.open_run("future", "0.6", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded, match="UTC day expired"):
        future.reserve("future", "refused", "1.060576")
