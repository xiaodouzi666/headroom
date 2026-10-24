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
    for name in ("patch.diff", "env.sh", "cli.json", "manifest.json"):
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
            "manifest": "configurations/round-01/manifest.json",
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
    assert "[manifest](configurations/round-01/manifest.json)" in markdown
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


def test_real_round_artifacts_keep_reverted_diff_and_each_verification(tmp_path):
    import copy
    import hashlib

    before = {
        "status": "completed",
        "capture_complete": True,
        "peak_allocated_bytes": 10_000_000_000,
        "step_ms_median": 100,
    }
    kept = {
        "completed": True,
        "target_met": False,
        "loss_equivalence": "identical",
        "peak_before": 10.0,
        "peak_after": 8.0,
        "reduction_pct": 20.0,
        "step_ms_before": 100.0,
        "step_ms_after": 110.0,
        "throughput_regression_pct": 10.0,
        "max_loss_delta": 0.0,
        "checks": {"loss_tolerance": True},
        "notes": ["First candidate retained."],
        "after": {**before, "peak_allocated_bytes": 8_000_000_000, "step_ms_median": 110},
    }
    reverted = {
        **kept,
        "loss_equivalence": "changed",
        "peak_after": 6.0,
        "reduction_pct": 40.0,
        "max_loss_delta": 0.1,
        "checks": {"loss_tolerance": False},
        "notes": ["Second candidate failed numerical verification."],
        "after": {**before, "peak_allocated_bytes": 6_000_000_000},
    }
    diffs = [
        "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-VALUE = 1\n+VALUE = 2\n",
        "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-VALUE = 2\n+VALUE = 3\n",
    ]
    rounds = []
    for number, (decision, verified, diff) in enumerate(
        zip(("keep", "revert"), (kept, reverted), diffs, strict=True), 1
    ):
        relative = f"rounds/{number:02d}/patches/attempt-01/patch.diff"
        file = tmp_path / relative
        file.parent.mkdir(parents=True)
        file.write_text(diff)
        rounds.append(
            {
                "number": number,
                "decision": decision,
                "reason": decision + "_reason",
                "patch": relative,
                "verification": verified,
                "provenance": "offline_fixture",
            }
        )
    original = copy.deepcopy(rounds)
    doc = generate_report(
        tmp_path,
        {
            "run_id": "fixture",
            "status": "completed",
            "provenance": "offline_fixture",
            "baseline": before,
            "after": kept["after"],
            "target_met": False,
        },
        rounds=rounds,
        verification=kept,
    )
    assert rounds == original
    assert doc["measurements"]["after"]["peak_allocated_bytes"] == 8_000_000_000
    assert doc["summary"]["loss_equivalence"] == "identical"
    assert doc["summary"]["target_met"] is False
    for row, diff, expected in zip(doc["rounds"], diffs, (kept, reverted), strict=True):
        assert row["diff"] == diff
        assert row["diff_status"] == "available"
        assert row["diff_bytes"] == len(diff.encode())
        assert row["diff_sha256"] == hashlib.sha256(diff.encode()).hexdigest()
        assert row["diff_summary"] == "1 file(s), 1 added line(s), 1 removed line(s)."
        assert row["verification"] == expected
        assert row["display_verification"]["target_met"] is False
    assert doc["rounds"][1]["decision"] == "revert"
    assert doc["rounds"][1]["display_verification"]["peak_after"] == "6.000 GB"
    assert doc["rounds"][1]["display_verification"]["max_loss_delta"] == "0.100000"
    markdown = (tmp_path / "report.md").read_text()
    assert "[Round candidate patch](rounds/02/patches/attempt-01/patch.diff)" in markdown
    assert "+VALUE = 3" in markdown and "+VALUE = 2" in markdown
    assert "| loss\\_tolerance | False |" in markdown
    assert "Offline fixture only" in markdown
    assert not check_report_numbers(doc, markdown)
    assert json.loads((tmp_path / "report.json").read_text()) == doc


def test_round_without_verification_has_unknowns_not_final_kept_values(tmp_path):
    doc = generate_report(
        tmp_path,
        {"status": "baseline_only", "provenance": "saved_baseline"},
        rounds=[{"number": 1, "decision": "revert", "reason": "patch_failed"}],
        verification={"peak_before": 10.0, "peak_after": 8.0, "loss_equivalence": "identical"},
    )
    row = doc["rounds"][0]
    assert row["display_verification"]["peak_before"] == "unknown"
    assert row["display_verification"]["peak_after"] == "unknown"
    assert row["display_verification"]["completed"] is None
    assert row["display_verification"]["loss_equivalence"] == "unknown"
    assert row["provenance"] == "saved_baseline"
    assert row["diff_status"] == "unavailable"
    assert row["diff"] is None
    assert "baseline" in (tmp_path / "report.md").read_text()


@pytest.mark.parametrize(
    "kind", ["missing", "outside", "symlink", "directory", "non_utf8", "oversized"]
)
def test_round_patch_unavailable_never_reads_or_links_invalid_artifact(tmp_path, monkeypatch, kind):
    from headroom import report

    output = tmp_path / "out"
    output.mkdir()
    path = "rounds/01/patch.diff"
    local = output / path
    local.parent.mkdir(parents=True)
    outside = tmp_path / "private.diff"
    outside.write_text("private-canary-441")
    if kind == "outside":
        path = "../private.diff"
    elif kind == "symlink":
        local.symlink_to(outside)
    elif kind == "directory":
        local.mkdir()
    elif kind == "non_utf8":
        local.write_bytes(b"\xff")
    elif kind == "oversized":
        monkeypatch.setattr(report, "MAX_ROUND_DIFF_BYTES", 4)
        local.write_bytes(b"12345")
    doc = generate_report(
        output,
        {"provenance": "offline_fixture"},
        rounds=[{"number": 1, "decision": "revert", "patch": path, "diff": "stale-inline-diff"}],
    )
    row = doc["rounds"][0]
    assert row["diff_status"] == "unavailable"
    assert row["diff"] is None
    assert row["patch"] is None
    assert row["diff_sha256"] is None
    rendered = (output / "report.md").read_text()
    assert "private-canary-441" not in rendered
    assert "stale-inline-diff" not in rendered
    assert "[Round candidate patch]" not in rendered
    assert (
        "unavailable" in row["diff_summary"]
        or "invalid" in row["diff_summary"]
        or "missing" in row["diff_summary"]
    )


def test_round_patch_rejects_symlinked_parent_directory(tmp_path):
    output, outside = tmp_path / "output", tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    (outside / "patch.diff").write_text("outside-canary")
    (output / "rounds").symlink_to(outside, target_is_directory=True)
    doc = generate_report(output, {}, rounds=[{"number": 1, "patch": "rounds/patch.diff"}])
    assert doc["rounds"][0]["diff_status"] == "unavailable"
    assert "outside-canary" not in (output / "report.md").read_text()


@pytest.mark.parametrize("diff", ["", "failed patch text </pre><script>bad</script> 5.000 GB"])
def test_empty_or_unparseable_round_patch_is_retained_as_actual_evidence(tmp_path, diff):
    (tmp_path / "patch.diff").write_text(diff)
    doc = generate_report(
        tmp_path,
        {},
        rounds=[
            {"number": 1, "decision": "revert", "reason": "apply_failed", "patch": "patch.diff"}
        ],
    )
    row = doc["rounds"][0]
    assert row["diff_status"] == "available"
    assert row["diff"] == diff
    assert row["diff_bytes"] == len(diff.encode())
    rendered = (tmp_path / "report.md").read_text()
    assert "<script>" not in rendered
    assert not check_report_numbers(doc, rendered)


def test_round_build_only_does_not_claim_file_read_or_accept_provided_available_status():
    doc = build_report(
        {"provenance": "offline_fixture"},
        rounds=[
            {
                "number": 1,
                "patch": "rounds/01/patch.diff",
                "diff": "untrusted",
                "diff_status": "available",
                "diff_sha256": "invented",
            }
        ],
    )
    row = doc["rounds"][0]
    assert row["diff_status"] == "not_loaded"
    assert row["diff"] is None and row["diff_sha256"] is None


def test_round_information_request_and_exhausted_supplement_remain_visible(tmp_path):
    doc = generate_report(
        tmp_path,
        {"status": "needs_human", "provenance": "offline_fixture"},
        rounds=[
            {
                "number": 1,
                "decision": "revert",
                "reason": "diagnosis_needs_more_info",
                "requested_information": [
                    "Capture optimizer step",
                    "<script>untrusted text</script>",
                ],
                "supplement_request": "Expected saving does not cover the requested reduction.",
            }
        ],
    )
    text = (tmp_path / "report.md").read_text()
    assert "Capture optimizer step" in text
    assert "Required planning supplement" in text
    assert "Expected saving does not cover" in text
    assert "<script>" not in text
    assert doc["rounds"][0]["requested_information"][0] == "Capture optimizer step"
    assert doc["rounds"][0]["display_verification"]["completed"] is None


def test_loss_summary_exposes_original_comparison_basis_and_limit():
    from headroom.report import build_report, render_markdown

    report = build_report(
        {"target": "reclaim", "status": "completed"},
        verification={
            "loss_equivalence": "identical",
            "numerical_basis": "original_plan_full_backward_scalar_series",
            "target_met": True,
        },
    )
    rendered = render_markdown(report)
    assert report["summary"]["numerical_basis"] == "original_plan_full_backward_scalar_series"
    assert "Observed full backward-loss sequence" in rendered
    assert "does not prove identical inputs" in rendered


def test_estimated_admission_warning_does_not_replace_actual_or_unknown_cost():
    usage = {
        "calls": 1,
        "known_cost_usd": "0.02",
        "total_cost_usd": None,
        "unknown_cost_calls": 1,
        "complete": False,
        "admission_counts": {"verified_provider_bound": 0, "local_estimate": 1, "unknown": 0},
    }
    doc = build_report({"run_id": "fixture"}, usage=usage)
    text = render_markdown(doc)
    assert "not a provider billing upper bound or an actual charge" in text
    assert doc["usage"]["total_cost_usd"] is None
    assert doc["usage"]["known_cost_usd"] == "0.02"


@pytest.mark.parametrize("status", ["completed", "budget_exceeded", "failed", "needs_human"])
def test_search_termination_preserves_selected_verified_target(status):
    search = {
        "mode": "bounded_pareto",
        "baseline_target_met": False,
        "first_target_met_round": 1,
        "stop_reason": "budget_exceeded" if status == "budget_exceeded" else "max_rounds_reached",
        "rounds_executed": 3,
    }
    doc = build_report(
        {"status": status, "search": search},
        verification={"after": {"status": "completed"}, "target_met": True},
        artifacts={"patch": "tiers/round-1/patch.diff"},
    )
    assert doc["status"] == status
    assert doc["summary"]["target_met"] is True
    assert doc["search"] == search
    assert doc["artifacts"]["patch"] == "tiers/round-1/patch.diff"
    markdown = render_markdown(doc)
    assert "target met: True" in markdown
    assert "Rounds executed: 3; first verified target round: 1." in markdown
    assert "A later exploration stop does not invalidate it" in markdown


def test_search_history_and_malformed_metadata_are_not_inferred():
    historical = build_report({"status": "completed", "target_met": True})
    assert historical["search"] == {}
    assert "Search mode: not recorded." in render_markdown(historical)
    doc = build_report(
        {
            "search": {
                "mode": "invented",
                "rounds_executed": True,
                "first_target_met_round": 0,
                "baseline_target_met": "yes",
                "stop_reason": "<script>bad</script>",
            }
        }
    )
    assert doc["search"]["mode"] is None
    assert doc["search"]["rounds_executed"] is None
    assert doc["search"]["first_target_met_round"] is None
    assert doc["search"]["baseline_target_met"] is None
    assert "<script>" not in render_markdown(doc)


@pytest.mark.parametrize("mode", [[], {}, 1, True, None])
def test_invalid_search_mode_does_not_break_historical_rendering(mode):
    doc = build_report({"search": {"mode": mode}})
    assert doc["search"]["mode"] is None
    assert "Search mode: unknown." in render_markdown(doc)


def test_cli_only_selection_preserves_original_effective_args_and_all_downloads(tmp_path):
    tier = tmp_path / "configurations/round-02"
    tier.mkdir(parents=True)
    artifacts = {}
    for key, name, content in (
        ("patch", "patch.diff", ""),
        ("env", "env.sh", ""),
        ("cli", "cli.json", '{"original":["--batch=8"],"effective":["--batch=1"]}'),
        ("manifest", "manifest.json", '{"round":2}'),
    ):
        (tier / name).write_text(content)
        artifacts[key] = str((tier / name).relative_to(tmp_path))
    run = {
        "request": {"script": "/captured/train.py", "script_args": ["--batch=8"]},
        "kept": {"round": 2, "effective_cli": ["--batch=1"], "artifacts": artifacts},
    }
    doc = generate_report(tmp_path, run)
    selected = doc["selected_configuration"]
    assert selected["original"]["script_args"] == ["--batch=8"]
    assert selected["effective"]["script_args"] == ["--batch=1"]
    assert selected["original"]["execution_argv"] is None
    assert selected["effective"]["execution_argv"] is None
    assert selected["artifacts"] == artifacts
    assert selected["wrapper_replay"] is None
    markdown = render_markdown(doc)
    assert "empty diff can represent a CLI-only" in markdown
    assert "source diff does not include CLI arguments or environment changes" in markdown
    assert "[Selected manifest](configurations/round-02/manifest.json)" in markdown
    assert "[Selected cli](configurations/round-02/cli.json)" in markdown
    assert "--batch=8" in markdown and "--batch=1" in markdown
    assert check_report_numbers(doc, markdown) == []


def test_selected_wrapper_replay_is_explicit_escaped_and_does_not_use_last_round():
    injected = "</pre><script>alert(1)</script> [click](javascript:bad)"
    root = ["/bin/sh", "launch.sh", "--batch=8", injected]
    descriptor = {
        "kind": "captured_wrapper",
        "root_argv": root,
        "python_argv": ["python", "-m", "pkg.train", "--batch=8"],
        "script_args": ["--batch=8"],
        "source_relative": "pkg/train.py",
        "startup_cwd_relative": ".",
        "module": "pkg.train",
    }
    run = {
        "request": {"execution_argv": root, "script_args": ["--batch=8"]},
        "kept": {
            "round": 1,
            "execution_argv": root,
            "effective_cli": ["--batch=1"],
            "allocator_conf": "expandable_segments:True",
            "execution_entrypoint": descriptor,
        },
    }
    doc = build_report(run, rounds=[{"number": 2, "decision": "revert"}])
    selected = doc["selected_configuration"]
    assert selected["round"] == 1
    assert selected["original"]["execution_argv"] == root
    assert selected["effective"]["execution_argv"] == root
    assert selected["effective"]["script_args"] == ["--batch=1"]
    assert selected["effective"]["allocator_conf"] == "expandable_segments:True"
    assert selected["wrapper_replay"]["python_argv"] == descriptor["python_argv"]
    markdown = render_markdown(doc)
    assert "execution_entrypoint" in markdown
    assert "ordinary shell does not apply this override" in markdown
    assert "<script>" not in markdown
    assert "&lt;/pre&gt;&lt;script&gt;" in markdown
    assert "no invocation is inferred" in markdown


@pytest.mark.parametrize("kept", [None, {}, {"round": True}, {"round": 7}])
def test_historical_or_malformed_selection_does_not_invent_replay(kept):
    doc = build_report({"kept": kept})
    assert doc["selected_configuration"] == {}
    assert "No selected configuration recorded" in render_markdown(doc)


def test_missing_or_linked_selected_manifest_is_not_linked(tmp_path):
    tier = tmp_path / "configurations/round-01"
    tier.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (tier / "manifest.json").symlink_to(outside)
    doc = generate_report(
        tmp_path,
        {
            "kept": {
                "round": 1,
                "artifacts": {
                    "manifest": "configurations/round-01/manifest.json",
                    "cli": "configurations/round-01/cli.json",
                    "patch": "../bad.diff",
                },
            }
        },
    )
    assert doc["selected_configuration"]["artifacts"] == {}
    assert "Selected manifest" not in render_markdown(doc)


def test_report_renders_bound_nano_opinions_separate_from_heuristics():
    from headroom.annotate import annotation_fingerprint, bind_stack_annotations

    original = {
        "run_id": "captured-fixture",
        "analysis": {
            "peak_composition": [
                {"stack_id": "stk_a", "bytes": 100, "category": "activations", "frames": []}
            ],
            "category_bytes": {"activations": 100},
        },
    }
    annotations = {
        "status": "completed",
        "complete": True,
        "model": "nvidia/fixture-nano",
        "evidence_fingerprint": annotation_fingerprint(original),
        "annotations": [
            {
                "stack_id": "stk_a",
                "category": "optimizer_state",
                "label": "Could be optimizer state <script> | hypothesis",
            }
        ],
    }
    bound = bind_stack_annotations(original, annotations, provenance="offline_fixture")
    bound["annotation_delivery"]["prompt_stack_ids"] = ["stk_a"]
    run = {"run_id": "fixture", "provenance": "offline_fixture", "annotations": annotations}
    doc = build_report(run, evidence={"before": bound})
    plain = build_report(run, evidence={"before": original})
    markdown = render_markdown(doc)
    row = doc["stack_annotations"][0]
    assert row["heuristic_category"] == "activations" and row["category"] == "optimizer_state"
    assert row["provenance"] == "offline_fixture" and row["is_measurement"] is False
    assert doc["measurements"] == plain["measurements"]
    assert doc["peak_composition"] == plain["peak_composition"]
    assert "| Stack | Heuristic category | Nano model category" in markdown
    assert "optimizer state" in markdown and "<script>" not in markdown
    assert "eight-scenario accuracy or cost gate" in markdown
    assert "Prepared evidence prompt: 1 label(s)" in markdown
    assert not check_report_numbers(doc, markdown)


def test_completed_annotation_is_not_claimed_delivered_without_bound_evidence():
    doc = build_report(
        {
            "annotations": {
                "status": "completed",
                "annotations": [
                    {"stack_id": "old", "category": "params", "label": "Unbound historical opinion"}
                ],
            }
        },
        evidence={
            "before": {
                "annotation_delivery": {
                    "status": "not_attached",
                    "reason": "source_evidence_mismatch",
                }
            }
        },
    )
    markdown = render_markdown(doc)
    assert not doc["stack_annotations"]
    assert "not_attached" in markdown.replace(chr(92), "")
    assert "source_evidence_mismatch" in markdown.replace(chr(92), "")
    assert "No source-bound stack opinions" in markdown
    assert "Unbound historical opinion" not in markdown
