"""Reviewed source formats and latest public selection, without any live invocation."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "gallery_publisher", ROOT / "scripts/publish_verified.py"
)
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


@pytest.mark.parametrize("kind", ["final48_summary", "browser_demo"])
def test_new_review_formats_bind_exact_original_report(kind):
    raw = b'{"preserved":"original report"}'
    path = "runs/example/report.json"
    row = {
        "run_id": "a" * 32,
        "scenario_id": "s3_eval_no_grad_missing",
        "target_met": False,
        "source_report": {"path": path, "sha256": hashlib.sha256(raw).hexdigest()},
    }
    audit = {"fixed_nine": {"rows": [row]}} if kind == "final48_summary" else row
    selection = {"run_id": "a" * 32, "audit_format": kind, "scenario_id": row["scenario_id"]}
    reviewed = publisher.reviewed_row(audit, selection, raw, path)
    assert reviewed["target"] is False
    assert reviewed["scenario_id"] == row["scenario_id"]
    altered = copy.deepcopy(audit)
    record = altered["fixed_nine"]["rows"][0] if kind == "final48_summary" else altered
    record["source_report"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="source report"):
        publisher.reviewed_row(altered, selection, raw, path)
    with pytest.raises(ValueError, match="source report"):
        publisher.reviewed_row(audit, selection, raw, "runs/other/report.json")


def test_unknown_review_format_is_not_inferred():
    with pytest.raises(ValueError, match="Unsupported"):
        publisher.reviewed_row({}, {"run_id": "a" * 32, "audit_format": "anything"}, b"{}", "x")


def test_latest_cards_and_exact_original_catalog_are_preserved():
    from headroom.api.verified import load_verified

    root = ROOT / "public-evidence"
    current = load_verified(root)
    old = load_verified(root, historical=True)
    new_rows = {row.scenario_id: row for row in current.runs}
    old_rows = {row.scenario_id: row for row in old.runs}
    assert new_rows["s4_loss_accumulation_graph"].run_id == "e8213706570e478f9845e49e24c2b54b"
    assert new_rows["s4_loss_accumulation_graph"].verification.compared_loss_count == 5
    assert new_rows["s4_loss_accumulation_graph"].after.optimizer_updates == 20
    s3 = new_rows["s3_eval_no_grad_missing"]
    assert s3.run_id == "d9926ee7bb624e7fb22540bbc4c92cdc"
    assert "Browser demo" in s3.title
    assert any("not part of a fixed-nine campaign" in text for text in s3.limitations)
    for name in set(new_rows) - {"s3_eval_no_grad_missing", "s4_loss_accumulation_graph"}:
        assert new_rows[name] == old_rows[name]
    receipt = json.loads((ROOT / "reports/verified-refresh-20261029/preparation.json").read_text())
    assert (
        hashlib.sha256((root / "verified-runs-history-v1.json").read_bytes()).hexdigest()
        == receipt["old_catalog_sha256"]
    )
