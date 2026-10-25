"""Read-only revalidation of v2 calibration artifacts before model evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from headroom.acceptance.common import file_record, read_bytes, read_json
from headroom.acceptance.s2_calibration import CASES, LIMIT, classify_result
from headroom.acceptance.snapshot_compact import MAX_INPUT, MAX_OUTPUT, verified_json
from headroom.evaluation import load_manifest
from headroom.evidence_analysis import analyze_snapshot
from headroom.lab.runner import selected_capture_directory
from headroom.lab.snapshot_codec import decode_snapshot, read_snapshot_artifact

ROOT = Path(__file__).resolve().parents[2]


def _inside(path: str | Path, root: Path) -> Path:
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Calibration artifact escapes project root")
    return path


def _sha(path: Path, limit=32 * 1024 * 1024) -> str:
    return file_record(path, limit)["sha256"]


def audit_case(
    receipt_path: Path, pin: dict, allocator_conf: str | None, *, project_root=ROOT
) -> dict:
    """Recompute every measurement gate; receipt booleans are never sufficient."""
    receipt_path = _inside(receipt_path, project_root)
    receipt = read_json(receipt_path)
    case = receipt["case"]
    run_dir = _inside(receipt["run_dir"], project_root)
    result_path, manifest_path = run_dir / "result.json", run_dir / "manifest.json"
    result, manifest = read_json(result_path), read_json(manifest_path)
    artifacts = selected_capture_directory(run_dir, result, manifest)
    snapshot_path = artifacts / "snapshot.json"
    normalization = None
    if snapshot_path.stat().st_size > MAX_OUTPUT:
        normalization = read_json(receipt_path.parent / "normalizations" / (case + ".json"))
        if _inside(normalization["original_path"], project_root) != snapshot_path.resolve():
            raise ValueError("Normalization refers to another snapshot")
        _inside(normalization["normalized_path"], project_root)
        snapshot = decode_snapshot(verified_json(normalization))
    else:
        snapshot = read_snapshot_artifact(snapshot_path, MAX_OUTPUT)
    analysis = analyze_snapshot(snapshot, result)
    inventory = {}
    for line in read_bytes(run_dir / "stdout.log", 8 * 1024 * 1024).decode().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("event") in {"step", "completed"} and row.get("optimizer_inventory"):
            inventory = {
                **row["optimizer_inventory"],
                "observed_after_update": row.get("step", row.get("steps")),
            }
    measured = classify_result(case, result, analysis, inventory)
    source_path = _inside(pin["path"], project_root)
    copied_source = run_dir / "source/train.py"
    expected_command = [
        "/opt/venv/bin/python",
        "-m",
        "headroom.lab.run_target",
        "--script",
        "/source/train.py",
        "--output",
        "/out",
        "--max-steps",
        "20",
        "--max-seconds",
        "180",
        "--seed",
        "1337",
        "--device",
        "cuda",
        "--",
        "--seed",
        "1337",
    ]
    env = result.get("env", {})
    checks = {
        "receipt_case": case in CASES,
        "result_digest": receipt.get("result_sha256") == _sha(result_path),
        "source_pin": receipt.get("source_sha256") == pin["sha256"] == _sha(source_path),
        "copied_source": _sha(copied_source) == pin["sha256"],
        "manifest_source": manifest.get("source", {})
        .get("files", {})
        .get("train.py", {})
        .get("sha256")
        == pin["sha256"],
        "argv": manifest.get("command") == expected_command,
        "cuda_environment": manifest.get("device") == env.get("device") == "cuda",
        "torch_version": str(env.get("torch", "")).split("+", 1)[0] == "2.5.1",
        "seed": manifest.get("seed") == env.get("seed") == 1337,
        "limits": manifest.get("max_steps") == env.get("max_steps") == 20
        and manifest.get("max_seconds") == env.get("max_seconds") == 180,
        "allocator_environment": manifest.get("environment", {}).get("PYTORCH_CUDA_ALLOC_CONF")
        == allocator_conf
        and env.get("PYTORCH_CUDA_ALLOC_CONF") == allocator_conf,
        "image_recorded": isinstance(result.get("image_id"), str)
        and result["image_id"] == manifest.get("image_id")
        and result["image_id"].startswith("sha256:"),
        "inventory_receipt_matches": inventory == receipt.get("optimizer_inventory"),
        "parameter_inventory": type(result.get("parameter_count")) is int
        and result["parameter_count"] == inventory.get("initialized_parameter_numel"),
        "fp32_two_moment_bytes": type(inventory.get("initialized_parameter_numel")) is int
        and inventory.get("moment_tensor_bytes") == 8 * inventory["initialized_parameter_numel"],
        "measurement_recomputed": measured["passed"],
    }
    return {
        "case": case,
        "accepted": all(checks.values()),
        "checks": checks,
        "measurement": measured,
        "analysis_header": analysis.get("header"),
        "snapshot_normalization": normalization,
        "source_sha256": pin["sha256"],
        "allocator_conf": allocator_conf,
        "image_id": result.get("image_id"),
        "environment_sha256": hashlib.sha256(
            json.dumps(
                {
                    key: env.get(key)
                    for key in (
                        "torch",
                        "cuda",
                        "device",
                        "seed",
                        "max_steps",
                        "max_seconds",
                        "PYTORCH_CUDA_ALLOC_CONF",
                        "CUDA_VISIBLE_DEVICES",
                        "deterministic_algorithms",
                        "CUBLAS_WORKSPACE_CONFIG",
                        "gpu_name",
                        "gpu_total_memory_bytes",
                        "cudnn",
                    )
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest(),
        "artifacts": {
            label: {"path": str(path), "sha256": _sha(path, limit)}
            for label, path, limit in (
                ("receipt", receipt_path, 2 * 1024 * 1024),
                ("result", result_path, 32 * 1024 * 1024),
                ("manifest", manifest_path, 32 * 1024 * 1024),
                ("snapshot", snapshot_path, MAX_INPUT if normalization else MAX_OUTPUT),
                ("stdout", run_dir / "stdout.log", 8 * 1024 * 1024),
            )
        },
        "repair_score_eligible": False,
    }


def audit_calibration(manifest_path: Path, directory: Path, *, project_root=ROOT) -> dict:
    """No GPU/API/store writes. Missing or inconsistent artifacts fail closed."""
    output = {
        "schema": "headroom.s2-calibration-audit.v2",
        "accepted": False,
        "executed": False,
        "model_calls": 0,
        "repair_scores_awarded": 0,
        "cases": [],
        "errors": [],
    }
    try:
        directory = _inside(directory, project_root)
        plan_path = directory / "preregistration.json"
        plan = read_json(plan_path)
        manifest_path = _inside(manifest_path, project_root)
        manifest = load_manifest(manifest_path, project_root=project_root)
        case = next(row for row in manifest.scenarios if row.id == "s2_capacity_v2")
        source_path = project_root / case.script
        if (
            plan["schema"] != "headroom.s2-calibration.v2"
            or plan["fit_limit_bytes"] != LIMIT
            or plan["required_steps"] != 20
            or plan["max_seconds_per_run"] != 180
            or plan["classification_minimum_ratio"] != "0.40"
            or plan["seed"] != 1337
            or plan["max_runs"] != 4
            or plan["cases"] != list(CASES[1:])
            or case.target != "fit:22GB"
            or case.expected_baseline != "completed"
            or case.script_args != ["--seed", "1337"]
            or case.allocator_conf != plan["allocator_conf"]
            or plan["allocator_conf"] != "expandable_segments:True"
            or case.allocator_conf != "expandable_segments:True"
            or case.source_sha256 != _sha(source_path)
            or case.source_sha256 != plan["source_pins"]["capacity_baseline"]["sha256"]
        ):
            raise ValueError("Manifest or plan differs from approved capacity protocol")
        for key, relative in (
            ("historical_manifest_sha256", "eval/mvp_phase1.yaml"),
            ("historical_s2_sha256", "scenarios/s2_fp32_adamw_1b/train.py"),
        ):
            if plan[key] != _sha(project_root / relative):
                raise ValueError("Historical source/manifest changed")
        reference = plan["reused_classification_receipt"]
        classification_path = _inside(reference["path"], project_root)
        if _sha(classification_path) != reference["sha256"]:
            raise ValueError("Classification reference changed")
        classification_plan_path = classification_path.parent / "preregistration.json"
        classification_plan = read_json(classification_plan_path)
        classification_receipt = read_json(classification_path)
        if classification_receipt["preregistration_sha256"] != _sha(classification_plan_path):
            raise ValueError("Classification preregistration changed")
        pins = plan["source_pins"]
        output["cases"].append(
            audit_case(
                classification_path,
                pins["classification"],
                classification_plan.get("allocator_conf"),
                project_root=project_root,
            )
        )
        for label in CASES[1:]:
            receipt_path = directory / (label + ".json")
            if not receipt_path.exists():
                output["errors"].append(label + ": missing receipt")
                continue
            receipt = read_json(receipt_path)
            supplement_path = directory / (label + ".supplement.json")
            if supplement_path.exists():
                supplement = read_json(supplement_path)
                if (
                    supplement.get("original_failure_receipt_sha256") != _sha(receipt_path)
                    or supplement.get("supplement_reason") != "snapshot_indentation_normalization"
                    or supplement.get("run_dir") != receipt.get("run_dir")
                    or supplement.get("result_sha256") != receipt.get("result_sha256")
                ):
                    raise ValueError(label + ": invalid supplementary audit linkage")
                receipt_path, receipt = supplement_path, supplement
            if receipt["preregistration_sha256"] != _sha(plan_path):
                raise ValueError(label + ": preregistration digest mismatch")
            if receipt["case"] != label:
                raise ValueError(label + ": wrong case receipt")
            output["cases"].append(
                audit_case(
                    receipt_path,
                    pins[label],
                    plan["allocator_conf"],
                    project_root=project_root,
                )
            )
        capacity_images = {
            row["image_id"] for row in output["cases"] if row["case"] != "classification"
        }
        output["capacity_runtime_image_consistent"] = len(capacity_images) == 1
        capacity_environments = {
            row["environment_sha256"] for row in output["cases"] if row["case"] != "classification"
        }
        output["capacity_environment_consistent"] = len(capacity_environments) == 1
        output["accepted"] = (
            not output["errors"]
            and len(output["cases"]) == 5
            and all(row["accepted"] for row in output["cases"])
            and output["capacity_runtime_image_consistent"]
            and output["capacity_environment_consistent"]
        )
        output["manifest_sha256"] = _sha(manifest_path)
        output["preregistration_sha256"] = _sha(plan_path)
    except (OSError, ValueError, TypeError, KeyError, StopIteration) as error:
        output["errors"].append(type(error).__name__ + ": " + str(error))
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_calibration(args.manifest, args.directory), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
