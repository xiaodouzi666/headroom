"""Pre-model calibration of versioned s2 fixtures; controls are never repair scores."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CASES = ("classification", "capacity_baseline", "optimizer_only", "checkpoint_only", "combined")
LIMIT = 22_000_000_000
REQUIRED_STEPS = 20


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def control_source(source: str, *, optimizer: bool, checkpoint: bool) -> str:
    """Exact anchored controls for calibration, never model-generated candidates."""
    if optimizer:
        before = "lr=1e-4, foreach=True)"
        if source.count(before) != 1:
            raise ValueError("Optimizer control anchor is not unique")
        source = source.replace(before, "lr=1e-4, foreach=False)")
    if checkpoint:
        before = "            hidden = block(hidden)"
        if source.count(before) != 1 or source.count("from torch import nn\n") != 1:
            raise ValueError("Checkpoint control anchor is not unique")
        source = source.replace(
            "from torch import nn\n",
            "from torch import nn\nfrom torch.utils.checkpoint import checkpoint\n",
        )
        source = source.replace(
            before, "            hidden = checkpoint(block, hidden, use_reentrant=False)"
        )
    return source


def prepare(
    directory: Path,
    *,
    project_root: Path = ROOT,
    allocator_conf: str | None = None,
    classification_receipt: Path | None = None,
) -> dict:
    """Create once, before GPU execution. Source and gates are immutable thereafter."""
    if allocator_conf not in {None, "expandable_segments:True"}:
        raise ValueError("Unsupported preregistered allocator configuration")
    reused = None
    if classification_receipt is not None:
        previous = json.loads(classification_receipt.read_text())
        pin = digest(project_root / "scenarios/s2_optimizer_classification_v2/train.py")
        result_path = Path(previous["run_dir"]) / "result.json"
        result = json.loads(result_path.read_text())
        classification = classify_result(
            "classification",
            result,
            {
                "header": previous["analysis_header"],
                "category_bytes": {"optimizer_state": previous["optimizer_state_category_bytes"]},
            },
            previous["optimizer_inventory"],
        )
        if (
            not classification["passed"]
            or previous.get("source_sha256") != pin
            or previous["result_sha256"] != digest(result_path)
        ):
            raise ValueError("Independent classification receipt is not valid")
        reused = {
            "path": str(classification_receipt.resolve()),
            "sha256": digest(classification_receipt),
        }
    directory.mkdir(parents=True, exist_ok=False)
    source_paths = {
        "classification": project_root / "scenarios/s2_optimizer_classification_v2/train.py",
        "capacity_baseline": project_root / "scenarios/s2_capacity_v2/train.py",
    }
    baseline = source_paths["capacity_baseline"].read_text()
    for case, optimizer, checkpoint in (
        ("optimizer_only", True, False),
        ("checkpoint_only", False, True),
        ("combined", True, True),
    ):
        folder = directory / "unscored_controls" / case
        folder.mkdir(parents=True)
        source_paths[case] = folder / "train.py"
        changed = control_source(baseline, optimizer=optimizer, checkpoint=checkpoint)
        source_paths[case].write_text(changed)
        (folder / "control.diff").write_text(
            "".join(
                difflib.unified_diff(
                    baseline.splitlines(keepends=True),
                    changed.splitlines(keepends=True),
                    fromfile="capacity_baseline/train.py",
                    tofile=case + "/train.py",
                )
            )
        )
    plan = {
        "schema": "headroom.s2-calibration.v2",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "preregistered",
        "model_calls": 0,
        "repair_score_eligible": False,
        "max_runs": 4 if reused else 5,
        "cases": list(CASES[1:] if reused else CASES),
        "allocator_conf": allocator_conf,
        "reused_classification_receipt": reused,
        "required_steps": REQUIRED_STEPS,
        "max_seconds_per_run": 180,
        "seed": 1337,
        "fit_limit_bytes": LIMIT,
        "classification_minimum_ratio": "0.40",
        "source_pins": {
            case: {"path": str(path), "sha256": digest(path)} for case, path in source_paths.items()
        },
        "runner_sha256": digest(Path(__file__)),
        "historical_manifest_sha256": digest(project_root / "eval/mvp_phase1.yaml"),
        "historical_s2_sha256": digest(project_root / "scenarios/s2_fp32_adamw_1b/train.py"),
        "gates": {
            "all": "completed, exactly 20 optimizer updates, complete capture, isolated GPU, exact replayed/native peak; valid initialized fp32 moment tensors",
            "classification": "peak optimizer-state category equals measured CUDA moment bytes and >=40% of native peak",
            "capacity_baseline": "native peak >22,000,000,000 bytes",
            "optimizer_only": "native peak >22,000,000,000 bytes",
            "checkpoint_only": "native peak >22,000,000,000 bytes",
            "combined": "native peak <=22,000,000,000 bytes",
        },
        "failure_policy": "Stop at first failed gate. Preserve failures. No threshold changes or replacement after model attempts.",
    }
    write_json(directory / "preregistration.json", plan)
    return plan


def classify_result(case: str, result: dict, analysis: dict, inventory: dict) -> dict:
    if case not in CASES:
        raise ValueError("Unknown calibration case")
    header = analysis.get("header", {})
    peak = header.get("recorded_peak_allocated_bytes")
    state = analysis.get("category_bytes", {}).get("optimizer_state")
    valid_peak = type(peak) is int and peak > 0
    checks = {
        "completed": result.get("status") == "completed",
        "twenty_updates": result.get("steps") == REQUIRED_STEPS,
        "capture_complete": result.get("capture_complete") is True,
        "cleanup_verified": result.get("cleanup_verified") is True,
        "exclusive_gpu": result.get("shared_gpu") is False,
        "exact_peak": header.get("history_complete") is True
        and header.get("peak_is_exact") is True
        and valid_peak
        and header.get("peak_allocated_bytes") == peak,
        "all_states_initialized": inventory.get("all_parameter_states_initialized") is True
        and type(inventory.get("parameters_total")) is int
        and inventory["parameters_total"] > 0
        and inventory.get("parameters_initialized") == inventory["parameters_total"],
        "valid_moment_layout": inventory.get("moment_layout_valid") is True,
        "late_state_observation": type(inventory.get("observed_after_update")) is int
        and REQUIRED_STEPS - 1 <= inventory["observed_after_update"] <= REQUIRED_STEPS,
        "cuda_moments_measured": type(inventory.get("cuda_moment_tensor_bytes")) is int
        and inventory["cuda_moment_tensor_bytes"] > 0
        and inventory["cuda_moment_tensor_bytes"] == inventory.get("moment_tensor_bytes"),
    }
    if case == "classification":
        checks["state_category_matches_tensors"] = type(state) is int and state == inventory.get(
            "cuda_moment_tensor_bytes"
        )
        checks["state_fraction_at_least_40pct"] = (
            valid_peak and type(state) is int and 5 * state >= 2 * peak
        )
    else:
        checks["capacity_gate"] = valid_peak and (
            peak <= LIMIT if case == "combined" else peak > LIMIT
        )
    return {
        "case": case,
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, value in checks.items() if not value],
        "native_peak_bytes": peak,
        "optimizer_state_category_bytes": state,
        "optimizer_inventory": inventory,
        "model_generated": False,
        "repair_score_eligible": False,
    }


def execute_case(directory: Path, case: str, *, project_root: Path = ROOT) -> dict:
    """One authorized Lab execution; no API, retries, or automatic continuation."""
    from headroom.evidence_analysis import analyze_snapshot
    from headroom.lab.runner import gpu_state, run_script
    from headroom.lab.snapshot_codec import read_snapshot_artifact

    plan = json.loads((directory / "preregistration.json").read_text())
    if case not in plan.get("cases", CASES) or plan["schema"] != "headroom.s2-calibration.v2":
        raise ValueError("Invalid calibration plan/case")
    if plan["runner_sha256"] != digest(Path(__file__)):
        raise ValueError("Calibration runner changed after preregistration")
    for label, pin in plan["source_pins"].items():
        if digest(Path(pin["path"])) != pin["sha256"]:
            raise ValueError("Pinned source changed: " + label)
    for key, path in (
        ("historical_manifest_sha256", "eval/mvp_phase1.yaml"),
        ("historical_s2_sha256", "scenarios/s2_fp32_adamw_1b/train.py"),
    ):
        if digest(project_root / path) != plan[key]:
            raise ValueError("Historical fixture/manifest changed")
    reused = plan.get("reused_classification_receipt")
    if reused and digest(Path(reused["path"])) != reused["sha256"]:
        raise ValueError("Reused classification receipt changed")
    selected = plan.get("cases", list(CASES))
    for prior in selected[: selected.index(case)]:
        prior_path = directory / (prior + ".json")
        if not prior_path.exists() or json.loads(prior_path.read_text()).get("passed") is not True:
            raise ValueError("Previous calibration has not passed: " + prior)
    receipt_path = directory / (case + ".json")
    with receipt_path.open("x") as handle:
        json.dump({"case": case, "status": "started", "passed": False}, handle)
    before = gpu_state()
    if before.get("available") is not True or before.get("processes"):
        raise RuntimeError("GPU is not available exclusively")
    source = Path(plan["source_pins"][case]["path"])
    result = run_script(
        source,
        source_root=source.parent,
        script_args=["--seed", "1337"],
        run_root=directory / "lab",
        max_steps=REQUIRED_STEPS,
        max_seconds=180,
        seed=1337,
        device="cuda",
        allocator_conf=plan.get("allocator_conf"),
    )
    run_dir = Path(result["run_dir"])
    analysis, inventory, error = {}, {}, None
    try:
        artifacts = Path(result["target_artifact_dir"])
        snapshot = read_snapshot_artifact(artifacts / "snapshot.json")
        analysis = analyze_snapshot(snapshot, result)
        for line in (run_dir / "stdout.log").read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") in {"step", "completed"} and row.get("optimizer_inventory"):
                inventory = {
                    **row["optimizer_inventory"],
                    "observed_after_update": row.get("step", row.get("steps")),
                }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        error = type(exc).__name__ + ": " + str(exc)
    receipt = classify_result(case, result, analysis, inventory)
    receipt.update(
        run_dir=str(run_dir),
        result_sha256=digest(run_dir / "result.json"),
        preregistration_sha256=digest(directory / "preregistration.json"),
        source_sha256=plan["source_pins"][case]["sha256"],
        allocator_conf=plan.get("allocator_conf"),
        status=result.get("status"),
        steps=result.get("steps"),
        finished_at=datetime.now(UTC).isoformat(),
        analysis_error=error,
        analysis_header=analysis.get("header"),
        source_inventory_note="Measured initialized tensor inventory; classification remains the existing allocator-origin classifier.",
    )
    write_json(receipt_path, receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "execute-case"))
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--allocator-conf", choices=("expandable_segments:True",))
    parser.add_argument("--classification-receipt", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        value = prepare(
            args.directory,
            allocator_conf=args.allocator_conf,
            classification_receipt=args.classification_receipt,
        )
        print(json.dumps({"status": value["status"], "directory": str(args.directory)}))
    else:
        if args.case is None:
            parser.error("--case is required")
        print(json.dumps(execute_case(args.directory, args.case), allow_nan=False))


if __name__ == "__main__":
    main()
