"""Known fee subtotals survive partial-run aggregation without becoming exact totals."""

import copy
import json
from decimal import Decimal, localcontext

import pytest

from headroom.api.evaluations import _public_row
from headroom.evaluation import Scenario, campaign_tables, result_row, summarize
from headroom.store.db import Store


def row(**changes):
    return {
        "scenario_id": "partial",
        "group": "synthetic",
        "condition": "full_ultra",
        "policy_name": "strict",
        "provenance": "live",
        "status": "budget_exceeded",
        "target_met": False,
        "cost_usd": None,
        "billing_complete": False,
        **changes,
    }


def test_mixed_known_and_unresolved_store_calls_reach_campaign_and_public_subtotals(tmp_path):
    store = Store(tmp_path / "store.db")
    try:
        store.create_run("a")
        store.add_llm_call("a", {"model": "known", "cost_usd": "0.1"})
        store.add_llm_call(
            "a",
            {
                "model": "unknown",
                "cost_usd": None,
                "outcome": "http_error",
                "http_status": 529,
                "reservation_usd": "0.08",
            },
        )
        usage = store.usage("a")
    finally:
        store.close()
    case = Scenario(
        id="partial",
        group="synthetic",
        script="train.py",
        source_root=".",
        target="reclaim",
        expected_baseline="completed",
    )
    normalized = result_row(
        case, "full_ultra", {"status": "budget_exceeded"}, usage, provenance="live"
    )
    assert normalized["known_cost_usd"] == "0.1"
    assert normalized["cost_usd"] is None
    assert normalized["cost_upper_usd"] is None
    assert normalized["billing_complete"] is False
    for candidate in (normalized, _public_row(normalized, "live")):
        summary = summarize([candidate])
        assert summary["known_cost_usd"] == "0.1"
        assert summary["total_cost_usd"] is None
        assert summary["unknown_cost_runs"] == 1
        assert summary["unresolved_cost_runs"] == 1
        assert summary["billing_complete"] is False
        assert summary["conservative_total_usd"] is None
        assert summary["measured_metrics"]["cost_usd"]["measured_count"] == 0
        assert summary["by_policy"]["default"]["known_cost_usd"] == "0.1"
        assert summary["by_policy"]["default"]["total_cost_usd"] is None


def test_legacy_partial_subtotal_and_exact_total_are_added_once_by_policy():
    rows = [
        row(usage={"known_cost_usd": "0.1", "total_cost_usd": None}),
        row(
            scenario_id="exact",
            policy_name="allow_precision",
            cost_usd="0.2",
            known_cost_usd="0.2",
            usage={"known_cost_usd": "0.2"},
            billing_complete=True,
        ),
    ]
    summary = summarize(rows)
    assert summary["known_cost_usd"] == "0.3"
    assert summary["total_cost_usd"] is None
    assert summary["by_policy"]["strict"]["known_cost_usd"] == "0.1"
    assert summary["by_policy"]["strict"]["total_cost_usd"] is None
    assert summary["by_policy"]["allow_precision"]["known_cost_usd"] == "0.2"
    assert summary["by_policy"]["allow_precision"]["total_cost_usd"] == "0.2"


def test_upper_bound_and_reservation_never_become_known_actual_charges():
    candidate = row(
        known_cost_usd="0.1",
        cost_upper_usd="0.18",
        cost_basis="verified_upper_bound",
        billing_complete=True,
        reservation_usd="20",
    )
    summary = summarize([candidate])
    assert summary["known_cost_usd"] == "0.1"
    assert summary["total_cost_usd"] is None
    assert summary["conservative_total_usd"] == "0.18"
    assert summary["bounded_cost_runs"] == 1
    assert summary["measured_metrics"]["cost_usd"]["mean"] is None


def test_exact_row_total_is_authoritative_without_duplicate_subtotal():
    candidate = row(
        cost_usd="0.2",
        known_cost_usd="99",
        usage={"known_cost_usd": "88"},
        billing_complete=True,
    )
    public = _public_row(candidate, "live")
    assert public["known_cost_usd"] == "0.2"
    assert summarize([candidate])["known_cost_usd"] == "0.2"
    assert summarize([public])["total_cost_usd"] == "0.2"


def test_pending_and_fixture_rows_do_not_inflate_known_subtotal():
    rows = [
        row(known_cost_usd="0.1"),
        row(scenario_id="fixture", provenance="offline_fixture", known_cost_usd="100"),
        row(scenario_id="pending", status="pending", known_cost_usd="100"),
        row(scenario_id="not_started", status="not_started", known_cost_usd="100"),
    ]
    summary = summarize(rows)
    assert summary["known_cost_usd"] == "0.1"
    assert summary["attempted_live_runs"] == 1
    assert summary["offline_fixture_rows_excluded"] == 1


@pytest.mark.parametrize(
    "value", ["NaN", "sNaN", "Infinity", "-Infinity", "-0.1", "1E81", "1E-81", True, 0.1, {}, None]
)
def test_invalid_partial_subtotal_is_not_published_or_promoted(value):
    candidate = row(known_cost_usd=value, usage={"known_cost_usd": "999"})
    public = _public_row(candidate, "live")
    assert public["known_cost_usd"] is None
    summary = summarize([public])
    # No known actual amount was accepted; the total and dispatch gate stay unresolved.
    assert summary["known_cost_usd"] == "0"
    assert summary["total_cost_usd"] is None
    assert summary["unknown_cost_runs"] == 1
    assert summary["billing_complete"] is False


def test_missing_partial_subtotal_remains_absent_not_a_known_zero_run():
    public = _public_row(row(), "live")
    assert public["known_cost_usd"] is None
    assert public["cost_usd"] is None
    assert public["billing_complete"] is False


def test_known_partial_subtotals_keep_full_decimal_span_without_rounding():
    values = ["9" * 80 + "E+80", "1E-80"]
    rows = [row(scenario_id=f"case_{i}", known_cost_usd=value) for i, value in enumerate(values)]
    with localcontext() as context:
        context.prec = 256
        expected = str(sum(map(Decimal, values), Decimal(0)))
    summary = summarize(rows)
    assert summary["known_cost_usd"] == expected
    assert summary["by_policy"]["strict"]["known_cost_usd"] == expected
    assert summary["total_cost_usd"] is None


def test_public_projection_reads_only_allowlisted_legacy_subtotal():
    original = row(
        usage={
            "known_cost_usd": "0.123",
            "total_cost_usd": None,
            "unknown_cost_calls": 1,
            "by_model": [{"private_path": "/private/home/report"}],
        },
        report_json="/private/home/report.json",
    )
    before = copy.deepcopy(original)
    public = _public_row(original, "live")
    assert public["known_cost_usd"] == "0.123"
    assert "usage" not in public
    assert "/private" not in json.dumps(public)
    assert original == before


def test_public_read_recomputes_legacy_partial_subtotal_without_rewriting_history(tmp_path):
    from test_published_evaluations import client, publish

    document = {
        "mode": "campaign",
        "provenance": "live",
        "status": "partial",
        "summary": {"known_cost_usd": "0"},
        "rows": [row(usage={"known_cost_usd": "0.125", "total_cost_usd": None})],
    }
    original = copy.deepcopy(document)
    publish(tmp_path, document)
    path = tmp_path / "published-evaluations/reviewed.json"
    before = path.read_bytes()
    with client(tmp_path) as api:
        detail = api.get("/api/evaluations/reviewed")
        assert detail.status_code == 200
        summary = detail.json()["summary"]
        assert summary["known_cost_usd"] == "0.125"
        assert summary["total_cost_usd"] is None
        listing = api.get("/api/evaluations").json()
        assert listing["evaluations"][0]["summary"]["known_cost_usd"] == "0.125"
    assert campaign_tables(document)["summary"]["known_cost_usd"] == "0.125"
    assert document == original
    assert path.read_bytes() == before
