#!/usr/bin/env python3
"""Collect the original T1.1 GPU checks without lowering a failing threshold."""

import datetime
import json
from pathlib import Path

from headroom.lab.runner import read_artifact_json, run_script

ROOT = Path(__file__).resolve().parents[1]


def main():
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = ROOT / "runs" / "lab-acceptance" / timestamp
    records = {}
    for name, scenario, args in (
        ("s1", "s1_batch_too_big", ["--seed", "1337"]),
        ("s3_a", "s3_eval_no_grad_missing", ["--batch", "1", "--steps", "100", "--seed", "1337"]),
        ("s3_b", "s3_eval_no_grad_missing", ["--batch", "1", "--steps", "100", "--seed", "1337"]),
    ):
        records[name] = run_script(
            ROOT / "scenarios" / scenario / "train.py",
            script_args=args,
            run_root=run_root,
            max_steps=20,
            max_seconds=120,
            seed=1337,
            device="cuda",
        )
        print(
            json.dumps(
                {
                    "case": name,
                    "status": records[name]["status"],
                    "run_dir": records[name]["run_dir"],
                }
            ),
            flush=True,
        )
    s1, a, b = records["s1"], records["s3_a"], records["s3_b"]
    artifacts = Path(s1["artifact_dir"])
    # JSON is exported inside the sandbox. Never load a target-produced pickle on the host.
    snapshot_file = artifacts / "snapshot.json"
    snapshot = (
        read_artifact_json(snapshot_file, max_bytes=128 * 1024 * 1024)
        if snapshot_file.exists()
        else {}
    )
    snapshot_export_valid = isinstance(snapshot, dict)
    if not snapshot_export_valid:
        snapshot = {}
    traces = snapshot.get("device_traces", [])
    count = len(traces[0]) if traces else 0
    oom = s1.get("oom") or {}
    checks = {
        "s1_cuda_oom": s1["status"] == "oom",
        "s1_snapshot_export_valid": snapshot_export_valid,
        "s1_snapshot_pickle_exists": (artifacts / "snapshot.pickle").exists(),
        "s1_device0_trace_events_gt_1000": count > 1000,
        "s1_positive_requested_gb": (oom.get("requested_gb") or 0) > 0,
        "s1_out_of_memory_traceback": "OutOfMemoryError" in oom.get("traceback", ""),
        "s3_completed_20_steps_a": a["status"] == "completed" and a.get("steps") == 20,
        "s3_completed_20_steps_b": b["status"] == "completed" and b.get("steps") == 20,
        "s3_at_least_20_losses_a": len(a.get("loss_series", [])) >= 20,
        "s3_at_least_20_losses_b": len(b.get("loss_series", [])) >= 20,
        "s3_first_5_losses_identical": len(a.get("loss_series", [])) >= 5
        and a["loss_series"][:5] == b.get("loss_series", [])[:5],
        "all_cleanup_verified": all(r.get("cleanup_verified", False) for r in records.values()),
        "all_gpu_runs_unshared": all(r.get("shared_gpu") is False for r in records.values()),
    }
    report = {
        "task": "T1.1",
        "scope": "GPU clauses only; tests/test_runner.py provides CPU Docker boundary/timeout checks",
        "gpu_checks_passed": all(checks.values()),
        "task_accepted": False,
        "original_thresholds_unchanged": True,
        "s1_device0_trace_event_count": count,
        "checks": checks,
        "runs": records,
    }
    path = ROOT / "reports" / f"lab-gpu-acceptance-{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"report": str(path), "checks": checks, "s1_trace_events": count}), flush=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
