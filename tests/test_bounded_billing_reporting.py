"""Offline bounded-cost reporting; no provider, GPU, or real ledger access."""

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from headroom.api.availability import read_local_budget
from headroom.api.evaluations import _public_row
from headroom.budget import BudgetLedger
from headroom.evaluation import (
    campaign_tables,
    load_manifest,
    result_row,
    run_fixture_campaign,
    summarize,
)
from headroom.orchestrator import _llm_phase
from headroom.report import build_report, render_markdown
from headroom.store.db import Store

BASIS = "verified_tariff_missing_cache_count"


def bounded_record(upper="0.00033378", **changes):
    return {
        "model": "offline-model",
        "role": "annotator",
        "outcome": "response",
        "settled": True,
        "admission_kind": "verified_provider_bound",
        "billing_status": "bounded",
        "cost_usd": None,
        "cost_upper_usd": upper,
        "cost_basis": BASIS,
        "cost": {"usd": None, "status": "upper_bound", "upper_usd": upper, "basis": BASIS},
        "usage": {"prompt_tokens": 3643, "completion_tokens": 480},
        **changes,
    }


def test_store_keeps_exact_unknown_and_certified_upper_separate(tmp_path):
    with_store = Store(tmp_path / "store.db")
    try:
        with_store.create_run("a")
        with_store.add_llm_call("a", {"model": "known", "cost_usd": "0.1"})
        saved = with_store.add_llm_call("a", bounded_record())
        assert saved["cost_status"] == "upper_bound" and saved["cost_usd"] is None
        usage = with_store.usage("a")
        assert usage["total_cost_usd"] is None and usage["complete"] is False
        assert usage["known_cost_usd"] == "0.1" and usage["unknown_cost_calls"] == 1
        assert usage["billing_complete"] is True and usage["bounded_cost_calls"] == 1
        assert usage["unresolved_cost_calls"] == 0
        assert Decimal(usage["conservative_total_usd"]) == Decimal("0.10033378")
        phase = _llm_phase(with_store, "a", 1)
        assert phase["cost_usd"] is None and phase["cost_upper_usd"] == "0.00033378"
        assert phase["cost_basis"] == "verified_upper_bound"
        with_store.add_llm_call(
            "a", {"model": "unreviewed", "cost_usd": None, "reservation_usd": "2"}
        )
        usage = with_store.usage("a")
        assert not usage["billing_complete"] and usage["conservative_total_usd"] is None
        assert usage["unresolved_cost_calls"] == 1
    finally:
        with_store.close()


@pytest.mark.parametrize("label", [None, "unresolved", "pending"])
def test_nested_candidate_bound_cannot_upgrade_runtime_rejection(tmp_path, label):
    store = Store(tmp_path / "store.db")
    try:
        store.create_run("a")
        row = bounded_record(billing_status=label)
        stored = store.add_llm_call("a", row)
        assert stored["cost_status"] == "unknown"
        usage = store.usage("a")
        assert usage["bounded_cost_calls"] == 0 and not usage["billing_complete"]
        assert usage["conservative_total_usd"] is None
    finally:
        store.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"admission_kind": "local_estimate"},
        {"cost_basis": "estimated"},
        {"cost_upper_usd": "-1"},
        {"cost_upper_usd": "NaN"},
        {"cost_upper_usd": True},
        {"settled": False},
        {"cost_usd": "0.001"},
    ],
)
def test_invalid_runtime_bound_is_not_accepted_as_billing_complete(tmp_path, changes):
    store = Store(tmp_path / "store.db")
    try:
        store.create_run("a")
        with pytest.raises((ValueError, TypeError)):
            store.add_llm_call("a", bounded_record(**changes))
        assert store.usage("a")["calls"] == 0
    finally:
        store.close()


@pytest.mark.parametrize(
    "upper,accepted,within",
    [
        ("0.59", True, True),
        ("0.6", True, True),
        ("0.6001", False, None),
    ],
)
def test_report_upper_can_prove_limit_but_cannot_prove_actual_overspend(upper, accepted, within):
    doc = build_report(
        {
            "status": "completed",
            "budget": {
                "run_budget_mode": "actual_usage",
                "limit_usd": "0.6",
                "total_actual_usd": None,
                "conservative_total_usd": upper,
                "billing_complete": True,
                "unknown_attempts": 1,
                "bounded_attempts": 1,
                "unresolved_attempts": 0,
                "pending_attempts": 0,
                "run_budget_exceeded": False,
            },
        },
        verification={"target_met": True, "after": {"status": "completed"}},
        usage={
            "complete": False,
            "total_cost_usd": None,
            "known_cost_usd": "0",
            "unknown_cost_calls": 1,
            "billing_complete": True,
            "bounded_cost_calls": 1,
            "unresolved_cost_calls": 0,
            "conservative_total_usd": upper,
        },
    )
    assert doc["summary"]["target_met"] is accepted
    assert doc["summary"]["cost_within_run_limit"] is within
    assert doc["verification"]["target_met"] is True
    assert doc["budget"]["actual_usd"] is None
    assert doc["budget"]["run_budget_exceeded"] is False
    markdown = render_markdown(doc)
    assert "Verified cost upper bound USD: " + upper in markdown
    assert "not a confirmed actual charge" in markdown


def test_standalone_report_rejects_unreviewed_upper_even_with_valid_candidate():
    doc = build_report(
        {
            "budget": {
                "run_budget_mode": "actual_usage",
                "limit_usd": "0.6",
                "total_actual_usd": None,
                "conservative_total_usd": "0.01",
                "billing_complete": False,
                "unknown_attempts": 1,
            }
        },
        verification={"target_met": True, "after": {"status": "completed"}},
    )
    assert doc["summary"]["target_met"] is False
    assert doc["summary"]["cost_within_run_limit"] is None


def test_read_only_availability_recognizes_covered_unknown_without_mutation(tmp_path):
    path = tmp_path / "ledger.db"
    ledger = BudgetLedger(path, total_limit="3", daily_limit="3")
    ledger.open_run("a", "0.6", budget_mode="actual_usage")
    ledger.reserve("a", "attempt", "1")
    ledger.settle_upper_bound("a", "attempt", "0.01", basis=BASIS)
    ledger.close_run("a")
    before = path.read_bytes()
    status = read_local_budget(path, daily_limit="3", total_limit="3")
    assert status["status"] == "available" and not status["dispatch_blocked"]
    assert status["total_actual_usd"] is None and status["unknown_attempts"] == 1
    assert status["bounded_attempts"] == 1 and status["unresolved_attempts"] == 0
    assert status["billing_complete"] and status["conservative_total_usd"] == "0.01"
    assert path.read_bytes() == before


@pytest.mark.parametrize("upper,expect_second", [("0.1", True), ("0.61", False)])
def test_campaign_uses_only_certified_charge_and_keeps_actual_unknown(
    tmp_path, upper, expect_second
):
    from test_evaluation import manifest

    path = manifest(tmp_path, count=2)
    seen = []

    def run(request, *, store, run_root, run_id, services):
        seen.append(run_id)
        store.create_run(run_id)
        store.add_llm_call(run_id, bounded_record(upper))
        return {
            "run_id": run_id,
            "status": "completed",
            "report": {"summary": {"target_met": True}},
        }

    document = run_fixture_campaign(
        path,
        project_root=tmp_path,
        output_root=tmp_path / "out",
        campaign_budget_usd="1.2",
        runner=run,
        services_factory=lambda *a: None,
    )
    assert len(seen) == (2 if expect_second else 1)
    first = document["rows"][0]
    assert first["cost_usd"] is None and first["cost_upper_usd"] == upper
    assert first["billing_complete"] and first["cost_basis"] == "verified_upper_bound"
    assert document["summary"]["attempted_live_runs"] == 0
    if not expect_second:
        assert first["target_met"] is False
        assert document["halt_reason"] == "cost_upper_bound_does_not_certify_run_limit"
        assert document["rows"][1]["status"] == "pending"


def test_bounded_summary_and_public_projection_do_not_fill_actual_or_average():
    row = {
        "scenario_id": "s1",
        "group": "synthetic",
        "condition": "full_ultra",
        "provenance": "live",
        "status": "completed",
        "target_met": True,
        "cost_usd": None,
        "cost_upper_usd": "0.00033378",
        "billing_complete": True,
        "cost_basis": "verified_upper_bound",
    }
    public = _public_row(row, "live")
    summary = summarize([public])
    assert summary["total_cost_usd"] is None and summary["known_cost_usd"] == "0"
    assert summary["unknown_cost_runs"] == 1 and summary["bounded_cost_runs"] == 1
    assert summary["billing_complete"] and summary["conservative_total_usd"] == "0.00033378"
    assert summary["measured_metrics"]["cost_usd"]["measured_count"] == 0
    result = campaign_tables({"mode": "campaign", "provenance": "live", "rows": [public]})
    assert result["rows"][0]["cost_usd"] is None
    refused = _public_row({**row, "billing_complete": False}, "live")
    assert refused["cost_upper_usd"] is None
    assert summarize([refused])["conservative_total_usd"] is None


@pytest.mark.parametrize("fault", [None, "cap_invalid"])
def test_real_runtime_mock_pipeline_retains_target_with_certified_unknown_cost(
    tmp_path, monkeypatch, fault
):
    import test_orchestrator as fixtures
    from test_actual_usage_budget import reviewed_fixture

    from headroom import orchestrator
    from headroom.runtime import LiveProfile, build_live_runtime

    data = reviewed_fixture(tmp_path).model_dump()
    for model in data["models"].values():
        model["cached_input_usd_per_million"] = "0.01"
    profile = LiveProfile.model_validate(data)
    monkeypatch.setattr(orchestrator, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(orchestrator, "read_live_profile", lambda *a: profile)
    original_services, factory, calls = fixtures.Services, {}, []

    def services(**kwargs):
        factory["make"] = kwargs.pop("runtime_factory")
        return original_services(**kwargs)

    monkeypatch.setattr(fixtures, "Services", services)

    def runtime(run_id, **kwargs):
        fixture = factory["make"](
            run_id, kwargs["store"], Path(kwargs["store"].get_run(run_id)["run_dir"])
        )

        def respond(request):
            calls.append(request)
            payload = fixture.client._transport.handle_request(request).json()
            payload["usage"].pop("prompt_tokens_details", None)
            if fault == "cap_invalid":
                payload["usage"] = {
                    "prompt_tokens": 10,
                    "completion_tokens": 8193,
                    "total_tokens": 8203,
                }
            return httpx.Response(200, json=payload)

        return build_live_runtime(
            run_id,
            **kwargs,
            env_file=tmp_path / ".env",
            transport=httpx.MockTransport(respond),
        )

    monkeypatch.setattr(orchestrator, "build_live_runtime", runtime)
    result, store, _, verifies, _ = fixtures.search_run(
        tmp_path,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
        search_mode="until_target",
    )
    try:
        if fault == "cap_invalid":
            assert len(calls) == 1 and len(verifies) == 0
            assert result["target_met"] is False
            usage = store.usage(result["run_id"])
            assert usage["bounded_cost_calls"] == 0 and not usage["billing_complete"]
            assert usage["conservative_total_usd"] is None
            record = store.llm_calls(result["run_id"])[0]
            assert record["cost"]["status"] == "upper_bound"
            assert record["billing_status"] == "unresolved"
            assert record["cost_status"] == "unknown"
            return
        assert len(calls) == 2 and len(verifies) == 1
        assert result["target_met"] is True and result["status"] == "completed"
        assert result["budget"]["billing_complete"]
        assert result["budget"]["total_actual_usd"] is None
        assert result["report"]["summary"]["target_met"] is True
        usage = store.usage(result["run_id"])
        assert usage["bounded_cost_calls"] == 2 and usage["total_cost_usd"] is None
        assert Decimal(usage["conservative_total_usd"]) == Decimal(
            result["budget"]["conservative_total_usd"]
        )
        from test_evaluation import manifest

        case_root = tmp_path / "manifest"
        case_root.mkdir()
        case = load_manifest(manifest(case_root), project_root=case_root).scenarios[0]
        # Fixture provenance is retained: this is not a real repair score.
        row = result_row(case, "full_ultra", result, usage, provenance="offline_fixture")
        assert row["cost_usd"] is None and row["cost_upper_usd"] is not None
        assert _public_row(row, "offline_fixture")["cost_usd"] is None
    finally:
        store.close()


def test_exact_amount_does_not_override_runtime_billing_rejection(tmp_path):
    from headroom.evaluation import _billing_fields, _conservative_cost

    store = Store(tmp_path / "store.db")
    try:
        store.create_run("a")
        store.add_llm_call(
            "a",
            {
                "model": "offline",
                "cost_usd": "0.01",
                "billing_status": "unresolved",
                "settled": True,
                "outcome": "response",
            },
        )
        usage = store.usage("a")
        assert usage["complete"] and usage["total_cost_usd"] == "0.01"
        assert usage["known_cost_usd"] == "0.01" and usage["unknown_cost_calls"] == 0
        assert usage["unresolved_cost_calls"] == 1 and not usage["billing_complete"]
        assert usage["conservative_total_usd"] is None
        assert _conservative_cost(usage) is None
        row = {
            "provenance": "live",
            "status": "failed",
            "cost_usd": "0.01",
            **_billing_fields(usage),
        }
        summary = summarize([row])
        assert summary["total_cost_usd"] == "0.01"
        assert not summary["billing_complete"] and summary["conservative_total_usd"] is None
    finally:
        store.close()
