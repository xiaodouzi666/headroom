#!/usr/bin/env python3
"""Evaluate the unchanged T1.2 criteria against saved real GPU captures."""

import ast
import datetime
import json
from pathlib import Path

from headroom.evidence import build_evidence

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "s1": ROOT / "runs/lab-acceptance/20261023T022523Z/48877b189d1040aba0cf39147f594f7f",
    "s2": ROOT / "runs/evidence-captures/20261023T023026Z/808e39dd7b224c47881165407dc55a9a",
    "s4": ROOT / "runs/evidence-captures/20261023T023026Z/3bfe803388964dda92f9206129367d8e",
    "s5": ROOT / "runs/evidence-captures/20261023T023026Z/3048a41430074b2ab5e5410e12be378c",
}


def main():
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    cases = {}
    analyses = {}
    for case, directory in RUNS.items():
        try:
            result = build_evidence(
                directory, budget=150000, output_dir=directory / f"evidence-{stamp}"
            )
            analysis = result["analysis"]
            analyses[case] = analysis
            cases[case] = {
                key: result.get(key)
                for key in (
                    "evidence_md",
                    "evidence_json",
                    "evidence_png",
                    "token_count",
                    "budget",
                    "source_token_count",
                )
            }
            cases[case].update(
                generated=all(
                    Path(result[key]).is_file()
                    for key in ("evidence_md", "evidence_json", "evidence_png")
                ),
                token_budget_passed=result["token_count"] <= 1.05 * result["budget"],
                source_budget_passed=result["source_token_count"] <= 0.3 * result["budget"],
                header=analysis["header"],
                category_bytes=analysis.get("category_bytes", {}),
                step_boundaries=len(analysis.get("step_boundaries", [])),
                oom_events=len(analysis.get("oom_events", [])),
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            cases[case] = {"generated": False, "error": f"{type(error).__name__}: {error}"}
        print(
            json.dumps(
                {
                    "case": case,
                    "generated": cases[case]["generated"],
                    "token_count": cases[case].get("token_count"),
                    "error": cases[case].get("error"),
                }
            ),
            flush=True,
        )
    s2 = analyses.get("s2", {})
    s2_peak = s2.get("header", {}).get("peak_allocated_bytes") or 0
    s2_state = s2.get("category_bytes", {}).get("optimizer_state", 0)
    ratio = s2_state / s2_peak if s2_peak else None
    tree = ast.parse((RUNS["s4"] / "source/train.py").read_text())
    retaining_lines = {
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "total_loss"
    }
    observed_frames = [
        frame
        for item in analyses.get("s4", {}).get("peak_composition", [])[:40]
        for frame in item.get("frames", [])
    ]
    runtime_retaining_line = any(
        frame.get("filename") == "/source/train.py" and frame.get("line") in retaining_lines
        for frame in observed_frames
    )
    s5_header = analyses.get("s5", {}).get("header", {})
    checks = {
        "all_four_evidence_artifacts": all(case.get("generated", False) for case in cases.values()),
        "all_token_counts_within_105_percent": all(
            case.get("token_budget_passed", False) for case in cases.values()
        ),
        "all_source_within_30_percent": all(
            case.get("source_budget_passed", False) for case in cases.values()
        ),
        "all_histories_reconstructed_and_validated": len(analyses) == 4
        and all(a.get("header", {}).get("history_complete") is True for a in analyses.values()),
        "s2_optimizer_state_at_least_40_percent_peak": ratio is not None and ratio >= 0.4,
        "s4_total_loss_assignment_is_actual_top_stack_frame": runtime_retaining_line,
        "s5_reserved_minus_allocated_at_least_1GB": (s5_header.get("cached_free_bytes") or 0)
        >= 1e9,
        "s5_fragmentation_indicator_high": s5_header.get("fragmentation_indicator") == "high",
        "s1_oom_marker_available": bool(analyses.get("s1", {}).get("oom_events")),
        "s4_oom_marker_available": bool(analyses.get("s4", {}).get("oom_events")),
    }
    report = {
        "task": "T1.2",
        "accepted": False,
        "original_acceptance_checks_passed": all(checks.values()),
        "original_thresholds_unchanged": True,
        "checks": checks,
        "s2_optimizer_state_fraction": ratio,
        "s4_static_retaining_lines": sorted(retaining_lines),
        "scope": "Actual snapshot acceptance clauses only; unit tests and visual inspection recorded separately. Static source clues are never counted as allocation frames.",
        "cases": cases,
    }
    target = ROOT / "reports" / f"evidence-acceptance-{stamp}.json"
    target.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps({"report": str(target), "checks": checks, "s2_optimizer_state_fraction": ratio}),
        flush=True,
    )
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
