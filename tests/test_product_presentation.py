"""Product negotiation keeps old APIs and exact evidence intact; no live services."""

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from headroom.api.app import ApiSettings, create_app
from headroom.api.presentation import (
    product_evaluation,
    product_event,
    product_message,
    product_report,
    product_run,
)

PRODUCT = {"X-Headroom-View": "product-v1"}
RAW_REASON = "The provider ledger has an unknown charge; halt at reservation gate."
PATCH = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-x = '/home/a'\n+x = '/home/b'\n"
REPORT = {
    "diagnosis": {
        "root_causes": [{"title": "Investigates allocation", "evidence_refs": ["stk_a"]}]
    },
    "evidence": {"before": {"analysis": {"peak_allocated_bytes": 2048}}},
    "summary": {"target_met": False, "loss_equivalence": "changed"},
    "allocator": {"note": "A reserved-minus-allocated gap alone does not prove fragmentation."},
    "warnings": [RAW_REASON],
    "private_debug": "must not be projected",
    "rounds": [
        {
            "number": 1,
            "decision": "revert",
            "reason": "loss_tolerance_gate_failed",
            "diff": PATCH,
            "diff_status": "available",
            "verification": {
                "checks": {"loss_tolerance": False},
                "notes": [
                    (
                        "PLAN T1.9 permits repository OOM acceptance with loss_equivalence=n/a "
                        "when no reference is available; numerical equivalence remains unverified."
                    ),
                    "Observed loss values are not proof of parameter equality.",
                ],
            },
        }
    ],
}


def test_product_projection_does_not_mutate_evidence_or_cost_unknowns():
    original = json.dumps(REPORT, sort_keys=True)
    result = product_report(REPORT)
    assert json.dumps(REPORT, sort_keys=True) == original
    assert result["diagnosis"] == REPORT["diagnosis"]
    assert result["evidence"] == REPORT["evidence"]
    assert result["allocator"] == REPORT["allocator"]
    assert result["rounds"][0]["diff"] == PATCH
    assert result["rounds"][0]["reason"] == "The numerical comparison did not pass."
    assert result["rounds"][0]["verification"]["notes"] == [
        (
            "The original evaluation rules allowed this repository OOM run to pass without "
            "a numerical reference; numerical equivalence remains unverified (n/a)."
        ),
        "Observed loss values are not proof of parameter equality.",
    ]
    assert result["warnings"] == ["The provider has not supplied a complete usage total."]
    assert "private_debug" not in result
    assert product_message("target not met") != "The requested memory target was reached."
    bound = {
        "diagnosis": REPORT["diagnosis"],
        "diagnosis_binding": {"diagnosis_sha256": "a" * 64},
        "stacks": [],
    }
    assert product_run({"diagnosis_evidence": bound})["diagnosis_evidence"] == bound
    scientific_note = "The first five recorded scalars use the original reference."
    projected = product_report(
        {
            "verification": {
                "notes": [scientific_note],
                "checks": {
                    "numerical_acceptance": False,
                    "private_reason": RAW_REASON,
                },
            }
        }
    )
    assert projected["verification"]["notes"] == [scientific_note]
    assert projected["verification"]["checks"] == {"numerical_comparison": False}
    assert (
        product_message("arbitrary private exception")
        == "Additional details are available in the downloaded report."
    )
    event = product_event(
        {
            "kind": "diagnose.done",
            "sequence": 7,
            "data": {
                "reason": RAW_REASON,
                "cost_usd": None,
                "cost": {"usd": "0"},
                "reservation_usd": "12",
            },
        }
    )
    assert event["data"]["cost_usd"] is None
    assert "reservation_usd" not in event["data"]
    assert event["label"] == "Diagnosis completed"


def test_evaluation_view_preserves_fixed_nine_threshold_and_raw_document():
    source = {
        "rows": [{"acceptance_scope": "repository", "target_met": False}],
        "acceptance": {
            "fixed_denominator": 9,
            "minimum_targets": 6,
            "target_met_count": 2,
            "target_gate_met": False,
            "source_sha256": {"campaign": "a" * 64},
        },
    }
    result = product_evaluation(source)
    assert result["suite_result"]["fixed_denominator"] == 9
    assert result["suite_result"]["minimum_targets"] == 6
    assert result["suite_result"]["threshold_met"] is False
    assert result["suite_result"]["source_sha256"] == source["acceptance"]["source_sha256"]
    assert result["rows"][0]["comparison_scope"] == "repository"
    assert "acceptance" in source and "acceptance_scope" in source["rows"][0]


def test_product_detail_sse_and_download_contract(tmp_path):
    project = tmp_path / "project"
    (project / "scenarios").mkdir(parents=True)
    (project / "scenarios" / "INDEX.yaml").write_text('{"scenarios": []}')
    settings = ApiSettings(
        project_root=project,
        data_root=tmp_path / "api",
        db_path=tmp_path / "db.sqlite3",
        run_root=tmp_path / "jobs",
        web_dist=tmp_path / "dist",
        event_poll_seconds=0.001,
    )

    def worker(request, *, store, run_root, run_id):
        folder = Path(run_root) / run_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.json").write_text(json.dumps(REPORT))
        (folder / "patch.diff").write_text(PATCH)
        store.add_event(run_id, "diagnose.done", {"reason": RAW_REASON, "cost_usd": None})
        store.update_run(run_id, reason=RAW_REASON)
        return {"status": "needs_human", "reason": RAW_REASON}

    app = create_app(settings, worker=worker)
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"script_text": "print('offline fixture')"})
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        path = f"/api/runs/{run_id}"
        for _ in range(200):
            detail = client.get(path).json()
            if detail.get("api_worker_finished"):
                break
            time.sleep(0.01)
        assert detail["api_worker_finished"] is True
        assert detail["reason"] == RAW_REASON
        product = client.get(path, headers=PRODUCT).json()
        assert product["reason"] == "The provider has not supplied a complete usage total."
        raw_report = client.get(path + "/report.json")
        assert raw_report.content == json.dumps(REPORT).encode()
        assert raw_report.json() == REPORT
        projected = client.get(path + "/report.json", headers=PRODUCT)
        assert projected.json() == product_report(REPORT)
        assert projected.headers["vary"] == "X-Headroom-View"
        assert client.get(path + "/patch.diff", headers=PRODUCT).text == PATCH
        raw_stream = client.get(path + "/events").text
        stream = client.get(path + "/events?view=product-v1").text
        assert RAW_REASON in raw_stream and RAW_REASON not in stream
        assert "Diagnosis completed" in stream and "event: stream.end" in stream
        assert (
            "id: 1\n"
            not in client.get(path + "/events?view=product-v1", headers={"Last-Event-ID": "1"}).text
        )
        assert "halted" in client.get("/api/health").json()["queue"]
        assert "paused" in client.get("/api/health", headers=PRODUCT).json()["queue"]
        other = TestClient(app)
        assert other.get(path, headers=PRODUCT).status_code == 404
        assert other.get(path + "/report.json", headers=PRODUCT).status_code == 404
        other.close()


def test_scientific_precision_and_tier_fields_survive_product_view():
    scientific = {
        "numerics_changed": False,
        "parameter_count_before": 1024,
        "parameter_count_after": 1024,
        "precision_evidence": {"before": "fp32", "after": "fp32", "complete": True},
        "numerical_basis": "original_plan_full_backward_scalar_series",
        "numerical_requirement": "exact-loss20-v1",
        "numerical_requirement_evidence": {
            "protocol": "exact-loss20-v1",
            "met": False,
            "checks": {"recorded_loss20_bitwise_identical": False},
            "observed_precision_before": "fp32",
            "observed_precision_after": "fp32",
            "pairing": {"same_inputs": None, "same_effective_batch": True, "same_objective": True},
            "scope": "Twenty recorded scalars only",
            "limitations": ["Parameter and optimizer equality are not established."],
        },
        "checks": {"numerical_tier": False, "numerical_acceptance": False},
        "loss_equivalence": "within_tol",
        "target_met": False,
        "notes": ["Observed tolerance does not establish bitwise equality."],
    }
    result = product_report({"verification": scientific})["verification"]
    for name, value in scientific.items():
        if name != "checks":
            assert result[name] == value, name
    assert result["checks"] == {"numerical_tier": False, "numerical_comparison": False}
