"""Offline rendering checks, including retained real capture metadata when available."""

import json
from pathlib import Path

import pytest

from headroom.report import build_report, check_report_numbers, generate_report, render_markdown


def test_partial_report_has_sections_and_no_fabricated_results(tmp_path):
    doc = generate_report(
        tmp_path, {"run_id": "partial", "status": "needs_human", "target": "fit:22GB"}
    )
    markdown = (tmp_path / "report.md").read_text()
    assert markdown.count("\n## ") >= 7
    assert doc["measurements"]["after"]["peak_allocated_bytes"] is None
    assert doc["summary"]["target_met"] is None
    assert doc["display"]["peak_after"] == "unknown"
    assert "No repair round recorded" in markdown
    assert "No runtime research sources" in markdown
    assert not check_report_numbers(doc, markdown)
    assert json.loads((tmp_path / "report.json").read_text()) == doc


def test_measured_values_and_deltas_originate_in_json(tmp_path):
    before = {
        "peak_allocated_bytes": 10_000_000_000,
        "peak_reserved_bytes": 12_000_000_000,
        "capture_complete": True,
        "status": "completed",
        "step_ms_median": 100,
    }
    after = {
        "peak_allocated_bytes": 7_500_000_000,
        "peak_reserved_bytes": 8_000_000_000,
        "capture_complete": True,
        "status": "completed",
        "step_ms_median": 120,
    }
    doc = generate_report(
        tmp_path,
        {"run_id": "fixture", "status": "completed", "baseline": before},
        verification={
            "after": after,
            "target_met": True,
            "loss_equivalence": "n/a",
            "checks": {"completed": True},
        },
    )
    assert doc["display"]["peak_reduction"] == "25.000%"
    assert doc["display"]["step_time_change"] == "20.000%"
    assert doc["summary"]["loss_equivalence"] == "n/a"
    assert not check_report_numbers(doc, render_markdown(doc))
    assert check_report_numbers(doc, render_markdown(doc) + "\nSavings: 99.123 GB")


def test_incomplete_peak_is_not_used_for_savings():
    doc = build_report(
        {"baseline": {"peak_allocated_bytes": 10, "capture_complete": False}},
        verification={
            "after": {"status": "completed", "capture_complete": True, "peak_allocated_bytes": 5}
        },
    )
    assert doc["summary"]["peak_reduction_pct"] is None
    assert doc["measurements"]["before"]["peak_is_exact"] is False


def test_conflicting_capture_is_explicit_and_cannot_claim_reduction():
    doc = build_report(
        {"baseline": {"peak_allocated_bytes": 10, "capture_complete": True}},
        evidence={"analysis": {"header": {"peak_allocated_bytes": 20, "peak_is_exact": True}}},
    )
    assert doc["measurements"]["before"]["peak_is_exact"] is False
    assert "Conflicting" in doc["warnings"][0]


def test_target_claim_without_completed_after_remains_unverified():
    doc = build_report({"target_met": True, "status": "partial"})
    assert doc["summary"]["target_met"] is None


def test_safe_text_links_and_diff_escaping(tmp_path):
    evil = "<script>alert(1)</script> ![x](https://attacker.invalid)\n## Forged"
    for relative in ("before.png", "after.png", "patch.diff"):
        (tmp_path / relative).write_bytes(
            b"offline placeholder; renderer does not decode artifacts"
        )
    doc = generate_report(
        tmp_path,
        {"run_id": evil},
        diagnosis={
            "root_causes": [
                {"title": evil, "bytes_gb": 2.5, "confidence": 0.5, "evidence_refs": ["stk_real"]}
            ]
        },
        rounds=[{"number": 1, "diff": "</pre><script>bad</script>", "decision": "revert"}],
        sources=[{"title": evil, "url": "javascript:alert(1)"}],
        artifacts={"before_png": "before.png", "after_png": "after.png", "patch": "patch.diff"},
    )
    text = render_markdown(doc)
    assert "<script>" not in text
    assert "\n## Forged" not in text
    assert "![x](https://attacker.invalid)" not in text
    assert "javascript:alert" not in text
    assert "![Before timeline](before.png)" in text
    assert "[Patch diff](patch.diff)" in text
    assert not check_report_numbers(doc, text)


@pytest.mark.parametrize(
    "path",
    ["../secret", "/etc/passwd", "https://example.com/a", "a\\b", "javascript:bad", ".", "a\nfile"],
)
def test_unsafe_artifact_path_is_rejected(path):
    with pytest.raises(ValueError):
        build_report({}, artifacts={"patch": path})


def test_missing_or_outside_symlink_not_linked(tmp_path):
    output = tmp_path / "out"
    output.mkdir()
    external = tmp_path / "other"
    external.write_text("outside")
    (output / "linked").symlink_to(external)
    doc = generate_report(output, {}, artifacts={"patch": "linked", "before_png": "missing"})
    assert not doc["artifacts"]
    assert doc["unavailable_artifacts"] == ["patch", "before_png"]
    assert len(doc["warnings"]) == 2


def test_real_saved_evidence_metadata_preserves_failed_gate_and_cache_caveat(tmp_path):
    fixture = Path("reports/evidence-acceptance-20261023T024929Z.json")
    if not fixture.is_file():
        pytest.skip("Retained GPU evidence metadata is available on the authoritative server")
    actual = json.loads(fixture.read_text())
    assert actual["accepted"] is False
    s2 = actual["cases"]["s2"]
    doc = generate_report(
        tmp_path / "s2",
        {"run_id": "saved-s2", "status": "baseline_only"},
        evidence={"analysis": {"header": s2["header"], "category_bytes": s2["category_bytes"]}},
    )
    optimizer = next(row for row in doc["peak_composition"] if row["category"] == "optimizer_state")
    assert optimizer["bytes"] == 8_593_604_608
    assert optimizer["percent_of_peak"] == "39.872%"
    assert doc["display"]["peak_before"] == "21.553 GB"
    assert doc["display"]["peak_after"] == "unknown"
    assert doc["summary"]["target_met"] is None
    s5 = actual["cases"]["s5"]
    cache = generate_report(
        tmp_path / "s5",
        {"status": "baseline_only"},
        evidence={"analysis": {"header": s5["header"]}},
    )
    assert cache["allocator"]["fragmentation_indicator"] == "high"
    assert cache["allocator"]["fragmentation_confirmed"] is False
    assert "alone does not prove" in render_markdown(cache)


def test_nonfinite_input_is_rejected():
    with pytest.raises(ValueError):
        build_report({"baseline": {"peak_allocated_bytes": float("nan")}})


def test_unknown_usage_cannot_be_rendered_as_zero_total():
    doc = build_report(
        {},
        usage={"calls": 1, "unknown_cost_calls": 1, "total_cost_usd": "0", "known_cost_usd": "0"},
    )
    assert doc["usage"]["total_cost_usd"] is None
    assert "total USD: unknown" in render_markdown(doc)


def test_malformed_source_url_is_omitted():
    doc = build_report({}, sources=[{"title": "bad URL", "url": "http://[invalid"}])
    assert "unsupported scheme" in render_markdown(doc)


def test_number_checker_cli_rejects_tampered_report(tmp_path, monkeypatch, capsys):
    from scripts.check_report_numbers import main

    generate_report(tmp_path, {"status": "partial"})
    monkeypatch.setattr("sys.argv", ["check_report_numbers.py", str(tmp_path)])
    assert main() == 0
    assert "PASS" in capsys.readouterr().out
    path = tmp_path / "report.md"
    path.write_text(path.read_text() + "\nInvented reduction: 98.765%\n")
    assert main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_pareto_display_numbers_and_relative_artifacts_are_auditable(tmp_path):
    from headroom.report import check_report_numbers, generate_report

    tier = tmp_path / "configurations/round-01"
    tier.mkdir(parents=True)
    for name in ("patch.diff", "env.sh", "cli.json"):
        (tier / name).write_text("offline fixture\n")
    point = {
        "round": 1,
        "peak_gb": 20.125,
        "step_ms": 110.5,
        "timing_trusted": True,
        "numerics": "identical",
        "artifacts": {
            "patch": "configurations/round-01/patch.diff",
            "env": "configurations/round-01/env.sh",
            "cli": "configurations/round-01/cli.json",
        },
        "provenance": "offline_fixture",
    }
    run = {
        "run_id": "fixture",
        "status": "completed",
        "target": "fit:22GB",
        "target_met": False,
        "pareto": {
            "points": [point],
            "frontier": [point],
            "limitations": ["Offline fixture only."],
        },
        "research": {"status": "skipped", "reason": "missing_credential"},
    }
    doc = generate_report(tmp_path, run)
    markdown = (tmp_path / "report.md").read_text()
    assert "20.125 GB" in markdown and "110.500 ms" in markdown
    assert "[patch](configurations/round-01/patch.diff)" in markdown
    assert "missing" in markdown and "credential" in markdown
    assert check_report_numbers(doc, markdown) == []


def test_pareto_does_not_turn_unknown_shared_timing_into_a_comparison(tmp_path):
    from headroom.report import generate_report

    point = {
        "round": 1,
        "peak_gb": 20,
        "step_ms": 1,
        "timing_trusted": False,
        "numerics": "n/a",
        "artifacts": {"patch": "../outside.diff"},
    }
    doc = generate_report(
        tmp_path,
        {
            "status": "completed",
            "target": "reclaim",
            "pareto": {"frontier": [point], "points": [point]},
        },
    )
    markdown = (tmp_path / "report.md").read_text()
    assert "unknown / shared timing" in markdown
    assert "1.000 ms" not in markdown and "../outside.diff" not in markdown
    assert doc["pareto"]["frontier"][0]["artifacts"] == {}
