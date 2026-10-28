"""Published evaluation projection and offline table rendering; no execution."""

import json
import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from headroom.api.evaluations import register_evaluations
from headroom.evaluation import CONDITIONS, campaign_tables, render_campaign


@pytest.fixture(autouse=True)
def no_execution(monkeypatch):
    def denied(*a, **kw):
        pytest.fail("No network, credentials or campaign execution")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr("headroom.runtime.read_nebius_key", denied)
    monkeypatch.setattr("headroom.evaluation.run_campaign", denied)


def campaign(provenance="live"):
    return {
        "mode": "campaign",
        "provenance": provenance,
        "status": "finished",
        "rows": [
            {
                "scenario_id": "s1",
                "group": "synthetic",
                "condition": condition,
                "policy_name": "strict",
                "policy": {"allow_numerics_change": False},
                "status": "completed",
                "provenance": "live",
                "run_id": str(index + 1) * 32,
                "source_sha256": "a" * 64,
                "truth_status": "authored",
                "ground_truth": "activations",
                "first_cause_matches": condition != "traceback_ultra",
                "target_met": index != 1,
                "peak_before_bytes": 10_000_000_000,
                "peak_after_bytes": 7_000_000_000,
                "peak_reduction_pct": 30,
                "step_time_change_pct": 10,
                "throughput_change_pct": None,
                "loss_equivalence": "within_tol",
                "rounds": 2,
                "cost_usd": ".1",
                "wall_seconds": 20,
                "condition_audit_dir": "/private/home/key",
                "report_json": "/private/account/report.json",
                "reason": "/private/diagnostic",
            }
            for index, condition in enumerate(CONDITIONS)
        ],
        "summary": {"target_met_rate": 1},
        "ablation": {"paired_scored_count": 999},
    }


def publish(root, document, identifier="reviewed"):
    (root / "published-evaluations").mkdir()
    (root / "public-evaluations.json").write_text(
        json.dumps(
            {
                "version": 1,
                "campaigns": [{"id": identifier, "title": "Reviewed campaign"}],
            }
        )
    )
    (root / "published-evaluations" / (identifier + ".json")).write_text(json.dumps(document))


def client(root):
    app = FastAPI()
    register_evaluations(app, root)
    return TestClient(app)


def test_unpublished_is_pending_and_does_not_scan_or_create_files(tmp_path):
    (tmp_path / "private-campaign.json").write_text(json.dumps(campaign()))
    before = sorted(p.name for p in tmp_path.iterdir())
    with client(tmp_path) as api:
        assert api.get("/api/evaluations").json() == {"status": "pending", "evaluations": []}
        assert api.get("/api/evaluations/reviewed").status_code == 404
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_public_projection_recomputes_scores_without_private_paths(tmp_path):
    publish(tmp_path, campaign())
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    with client(tmp_path) as api:
        listing = api.get("/api/evaluations").json()
        assert listing["evaluations"][0]["id"] == "reviewed"
        result = api.get("/api/evaluations/reviewed")
        assert result.status_code == 200
        data = result.json()
        assert data["summary"]["target_met_rate"] == pytest.approx(2 / 3)
        assert data["ablation"]["paired_scored_count"] == 1
        assert data["ablation"]["ultra_full_minus_traceback"] == 1
        assert data["rows"][0]["throughput_change_pct"] is None
        assert "/private" not in result.text
        assert "condition_audit_dir" not in result.text and "report_json" not in result.text
        assert api.get("/api/evaluations/not-listed").status_code == 404
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_fixture_document_cannot_elevate_its_rows_to_live(tmp_path):
    document = campaign("offline_fixture")
    publish(tmp_path, document)
    with client(tmp_path) as api:
        data = api.get("/api/evaluations/reviewed").json()
        assert data["summary"]["status"] == "pending"
        assert data["summary"]["attempted_live_runs"] == 0
        assert data["summary"]["offline_fixture_rows_excluded"] == 3
        assert all(row["provenance"] == "offline_fixture" for row in data["rows"])
        assert data["ablation"]["paired_scored_count"] == 0
    markdown = render_campaign(document)
    assert "No live evaluation scores" in markdown
    assert "| full_ultra | 0 | 0 | unknown |" in markdown


def test_partial_campaign_keeps_unknown_denominators_and_unpaired_groups(tmp_path):
    document = campaign()
    document["rows"][1]["target_met"] = None
    document["rows"][1]["cost_usd"] = None
    document["rows"][2]["source_sha256"] = "b" * 64
    publish(tmp_path, document)
    with client(tmp_path) as api:
        data = api.get("/api/evaluations/reviewed").json()
        assert data["summary"]["target_met_rate"] is None
        assert data["summary"]["target_unknown_runs"] == 1
        assert data["summary"]["total_cost_usd"] is None
        assert data["ablation"]["paired_scored_count"] == 0
        assert data["ablation"]["excluded"][0]["reason"] == "source_hash_not_comparable"
        assert any("No comparable" in line for line in data["conclusions"])
    markdown = render_campaign(document)
    assert "unknown target outcomes" in markdown and "source\\_hash\\_not\\_comparable" in markdown
    assert "percentage points" not in markdown


@pytest.mark.parametrize("kind", ["manifest", "symlink", "malformed-campaign"])
def test_invalid_publication_is_unavailable_without_diagnostics(tmp_path, kind):
    publish(tmp_path, campaign())
    if kind == "manifest":
        (tmp_path / "public-evaluations.json").write_text(
            '{"version":1,"campaigns":[{"id":"../private","title":"x"}]}'
        )
    elif kind == "symlink":
        path = tmp_path / "published-evaluations/reviewed.json"
        path.unlink()
        path.symlink_to(tmp_path / "private")
    else:
        (tmp_path / "published-evaluations/reviewed.json").write_text("not json")
    with client(tmp_path) as api:
        response = api.get("/api/evaluations")
        assert response.status_code == 503
        assert str(tmp_path) not in response.text


def test_rendered_tables_include_summary_pairs_and_measured_conclusions():
    markdown = render_campaign(campaign())
    assert r"Summary \(live only\)" in markdown
    assert "## Paired diagnosis ablation" in markdown
    assert "| full_ultra | 1 | 1 | 100.00% |" in markdown
    assert "| traceback_ultra | 0 | 1 | 0.00% |" in markdown
    assert "| s1 | strict | True | False | True |" in markdown
    assert "+100.00 percentage points" in markdown
    assert "statistical significance" in markdown
    assert "/private" not in markdown
    assert campaign_tables(campaign())["summary"]["total_cost_usd"] == "0.3"


def test_saved_renderer_rejects_non_campaign_and_unproven_provenance():
    for document in ({}, {"mode": "campaign", "rows": [], "provenance": "guessed"}):
        with pytest.raises(ValueError):
            render_campaign(document)


def test_duplicate_campaign_rows_cannot_inflate_live_summary(tmp_path):
    document = campaign()
    document["rows"].append(document["rows"][0].copy())
    with pytest.raises(ValueError, match="Duplicate"):
        render_campaign(document)
    publish(tmp_path, document)
    with client(tmp_path) as api:
        assert api.get("/api/evaluations/reviewed").status_code == 503


def test_offline_render_command_refuses_fifo_without_blocking(tmp_path, monkeypatch):
    import os
    import runpy
    import sys

    fifo = tmp_path / "campaign.json"
    os.mkfifo(fifo)
    monkeypatch.setattr(sys, "argv", ["render_evaluation.py", str(fifo)])
    with pytest.raises(SystemExit) as failure:
        runpy.run_path("scripts/render_evaluation.py", run_name="__main__")
    assert failure.value.code == 2


def test_report_decimal_percentages_survive_campaign_and_publication(tmp_path):
    """Exercise actual producers with synthetic in-memory measurements, never a workload."""
    from decimal import Decimal

    from headroom.evaluation import Scenario, result_row
    from headroom.report import generate_report

    before = {
        "status": "completed",
        "capture_complete": True,
        "peak_allocated_bytes": 10_000_000_000,
        "step_ms_median": 100,
    }
    after = {
        "status": "completed",
        "capture_complete": True,
        "peak_allocated_bytes": 7_500_000_000,
        "step_ms_median": 120,
    }
    generate_report(
        tmp_path / "producer",
        {"run_id": "a" * 32, "status": "completed", "baseline": before},
        verification={"after": after, "target_met": True, "loss_equivalence": "within_tol"},
    )
    report = json.loads((tmp_path / "producer/report.json").read_text())
    assert isinstance(report["summary"]["peak_reduction_pct"], str)
    assert isinstance(report["summary"]["step_time_change_pct"], str)
    case = Scenario(
        id="s1",
        group="synthetic",
        script="s1/train.py",
        source_root="s1",
        target="reclaim",
        expected_baseline="completed",
    )
    row = result_row(
        case,
        "full_ultra",
        {"report": report, "status": "completed", "run_id": "a" * 32},
        {"complete": True, "total_cost_usd": ".1"},
        provenance="live",
    )
    row.update(policy_name="default", policy={})
    publish(
        tmp_path, {"mode": "campaign", "provenance": "live", "status": "finished", "rows": [row]}
    )
    with client(tmp_path) as api:
        result = api.get("/api/evaluations/reviewed")
        assert result.status_code == 200
        public = result.json()
        for field, expected in (("peak_reduction_pct", "25"), ("step_time_change_pct", "20")):
            assert public["rows"][0][field] == report["summary"][field]
            metric = public["summary"]["measured_metrics"][field]
            assert Decimal(metric["mean"]) == Decimal(expected)
            assert metric["measured_count"] == 1 and metric["unknown_count"] == 0
        assert public["rows"][0]["throughput_change_pct"] is None
        listing = api.get("/api/evaluations").json()["evaluations"][0]["summary"]
        assert listing["measured_metrics"]["peak_reduction_pct"]["measured_count"] == 1


@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        None,
        "NaN",
        "Infinity",
        "-Infinity",
        "1e31",
        "1e-81",
        "0." + "1" * 81,
        "25 percent",
        " 25 ",
        float("nan"),
        float("inf"),
        10**300,
    ],
)
def test_invalid_percentage_stays_unknown_without_hiding_other_measurements(tmp_path, invalid):
    document = campaign()
    document["rows"][0]["peak_reduction_pct"] = invalid
    publish(tmp_path, document)
    with client(tmp_path) as api:
        result = api.get("/api/evaluations/reviewed")
        assert result.status_code == 200
        data = result.json()
        assert data["rows"][0]["peak_reduction_pct"] is None
        metric = data["summary"]["measured_metrics"]["peak_reduction_pct"]
        assert metric["measured_count"] == 2 and metric["unknown_count"] == 1


@pytest.mark.parametrize("valid", ["-12.50", "0.0", "2.5e-3", "+20.125"])
def test_signed_finite_decimal_percentages_preserve_exact_text(tmp_path, valid):
    document = campaign()
    for name in ("peak_reduction_pct", "step_time_change_pct", "throughput_change_pct"):
        document["rows"][0][name] = valid
    publish(tmp_path, document)
    with client(tmp_path) as api:
        row = api.get("/api/evaluations/reviewed").json()["rows"][0]
        for name in ("peak_reduction_pct", "step_time_change_pct", "throughput_change_pct"):
            assert row[name] == valid


def test_public_projection_preserves_na_and_known_basis_without_private_strings(tmp_path):
    document = campaign()
    document["rows"][0].update(
        loss_equivalence="n/a",
        numerical_basis="repository_no_reference_exception",
        acceptance_scope="repository",
    )
    document["rows"][1].update(
        numerical_basis="/private/unknown-basis",
        acceptance_scope="/private/unknown-scope",
    )
    publish(tmp_path, document)
    with client(tmp_path) as api:
        response = api.get("/api/evaluations/reviewed")
        data = response.json()
    assert response.status_code == 200
    assert data["rows"][0]["loss_equivalence"] == "n/a"
    assert data["rows"][0]["numerical_basis"] == "repository_no_reference_exception"
    assert data["rows"][0]["acceptance_scope"] == "repository"
    assert data["rows"][1]["numerical_basis"] is None
    assert data["rows"][1]["acceptance_scope"] is None
    assert "/private" not in response.text


def test_reviewed_public_suites_keep_fixed_denominators_and_private_data_out():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "public-evidence"
    with client(root) as api:
        listing = api.get("/api/evaluations").json()["evaluations"]
        assert [item["id"] for item in listing] == ["r6-20261027", "r5-20261027"]
        for identifier, targets, causes, blocked in (
            ("r6-20261027", 2, 3, 5),
            ("r5-20261027", 3, 6, 0),
        ):
            response = api.get("/api/evaluations/" + identifier)
            assert response.status_code == 200
            data = response.json()
            assert len(data["rows"]) == 9
            assert len({row["run_id"] for row in data["rows"]}) == 9
            assert data["summary"]["target_met_count"] == targets
            assert data["summary"]["target_measured_denominator"] == 9
            assert data["summary"]["first_cause_correct"] == causes
            s4 = next(
                row for row in data["rows"] if row["scenario_id"] == "s4_loss_accumulation_graph"
            )
            assert s4["numerical_basis"] == "original_workload_offload_first_five_backward_scalars"
            assert s4["loss_equivalence"] == "identical"
            acceptance = data["acceptance"]
            assert acceptance["fixed_denominator"] == 9 and acceptance["minimum_targets"] == 6
            assert acceptance["target_met_count"] == targets
            assert acceptance["target_gate_met"] is False
            assert acceptance["stopped_before_diagnosis_and_patch"] == blocked
            for row in data["rows"]:
                if row["status"] == "budget_exceeded":
                    assert row["annotation_attempt_recorded"] is True
                    assert row["diagnosis_attempt_recorded"] is False
                    assert row["patch_attempt_recorded"] is False
                    assert row["target_met"] is False
                    assert row["first_cause_matches"] is None
            for marker in ("/home/", "/Users/", ".cache/", "NEBIUS_API_KEY", "TAVILY_API_KEY"):
                assert marker not in response.text
        r5 = api.get("/api/evaluations/r5-20261027").json()
        s6 = next(row for row in r5["rows"] if row["scenario_id"] == "s6_full_vocab_logits_fp32")
        assert s6["first_cause_matches"] is False  # Independent audit overrides raw campaign claim.


def test_fixed_suite_recomputes_claims_and_rejects_missing_slots(tmp_path):
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "public-evidence/published-evaluations/r6-20261027.json"
    )
    document = json.loads(source.read_text())
    document["acceptance"].update(target_met_count=9, target_gate_met=True)
    publish(tmp_path, document)
    with client(tmp_path) as api:
        result = api.get("/api/evaluations/reviewed").json()
        assert result["acceptance"]["target_met_count"] == 2
        assert result["acceptance"]["target_gate_met"] is False
        document["rows"].pop()
        (tmp_path / "published-evaluations/reviewed.json").write_text(json.dumps(document))
        assert api.get("/api/evaluations/reviewed").status_code == 503
