"""One preregistered checkpoint-reference resource control; never model acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from headroom.lab.runner import read_artifact_json, run_script
from headroom.verify.checkpoint import (
    PROTOCOL,
    STRATEGY,
    TRANSFORM,
    attest_reference,
    reference_proof,
    transform_source,
)
from headroom.verify.offload import bind_original_baseline
from headroom.verify.pairing import source_contract
from headroom.verify.precision import observed_precision

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "headroom/lab/precision.py",
    "headroom/lab/snapshot_codec.py",
    "headroom/evidence_analysis.py",
    "headroom/verify/checkpoint.py",
    "headroom/verify/pairing.py",
    "headroom/verify/precision.py",
    "headroom/lab/runner.py",
    "headroom/lab/run_target.py",
    "headroom/lab/hooks.py",
    "scripts/research_checkpoint_reference.py",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes():
    return {name: digest(ROOT / name) for name in FILES}


def prepare(original_script, baseline_result, output):
    original_script = Path(original_script).resolve(strict=True)
    baseline_result = Path(baseline_result).resolve(strict=True)
    output = Path(output).resolve()
    baseline = read_artifact_json(baseline_result)
    manifest = read_artifact_json(Path(baseline["run_dir"]) / "manifest.json")
    command = manifest["command"]
    args = command[command.index("--") + 1 :] if "--" in command else []
    contract = source_contract(original_script)
    original_hash = digest(original_script)
    if not (
        baseline.get("status") == "oom"
        and baseline.get("capture_complete") is True
        and baseline.get("cleanup_verified") is True
        and "headroom.lab.run_target" in command
        and baseline.get("pairing_capture", {}).get("source_contract", {}).get("source_sha256")
        == original_hash
        and contract.get("profile") == "s1"
        and contract.get("checkpointed") is False
        and contract.get("supported") is True
    ):
        raise ValueError("Resource control requires preserved real original s1 OOM source/argv")
    output.mkdir(parents=True, exist_ok=False)
    source_dir = output / "reference-source"
    source_dir.mkdir()
    transformed_script = source_dir / "train.py"
    transformed_script.write_bytes(transform_source(original_script.read_bytes()))
    binding = bind_original_baseline(baseline, original_script, args)
    receipt = {
        "protocol": PROTOCOL,
        "mode": STRATEGY,
        "transform_version": TRANSFORM,
        "source_kind": "baseline_derived_transformed_reference",
        "original_source_sha256": original_hash,
        "transformed_source_sha256": digest(transformed_script),
        "script_args": args,
        "max_seconds": 480,
        "required_steps": 20,
        "performance_comparable": False,
        "use_reentrant": False,
        "preserve_rng_state": True,
        "original_baseline_binding": binding,
    }
    plan = {
        "kind": "manual_checkpoint_reference_resource_feasibility",
        "counts_toward_model_acceptance": False,
        "maximum_gpu_runs": 1,
        "runs_original_baseline": False,
        "runs_model": False,
        "max_seconds": 480,
        "required_logical_updates": 20,
        "required_precision": "fp32",
        "snapshot_reader_limit_bytes": 512 * 1024**2,
        "original_script": str(original_script),
        "baseline_result": str(baseline_result),
        "baseline_result_sha256": digest(baseline_result),
        "reference_script": str(transformed_script),
        "seed": baseline["env"]["seed"],
        "device": "cuda",
        "allocator_conf": baseline["env"].get("PYTORCH_CUDA_ALLOC_CONF"),
        "measurement_source_hashes": hashes(),
        "transformation": receipt,
        "baseline_pairing_gap": (
            "Historical baseline has no observed input/initial-parameter fingerprints; "
            "resource feasibility cannot establish original-baseline pairing. "
            "Full proof remains false; formal acceptance needs its own fresh baseline."
        ),
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def execute(output):
    output = Path(output).resolve(strict=True)
    plan = read_artifact_json(output / "plan.json")
    if hashes() != plan["measurement_source_hashes"]:
        raise ValueError("Measurement source changed after registration; do not run")
    if digest(plan["baseline_result"]) != plan["baseline_result_sha256"]:
        raise ValueError("Historical baseline evidence changed")
    receipt = plan["transformation"]
    if digest(plan["original_script"]) != receipt["original_source_sha256"]:
        raise ValueError("Original source changed")
    if digest(plan["reference_script"]) != receipt["transformed_source_sha256"]:
        raise ValueError("Transformed reference source changed")
    with (output / "attempt.json").open("x") as handle:
        json.dump({"status": "reserved", "maximum_gpu_runs": 1}, handle)
    reference = run_script(
        plan["reference_script"],
        script_args=receipt["script_args"],
        source_root=Path(plan["reference_script"]).parent,
        run_root=output / "runs",
        device="cuda",
        seed=plan["seed"],
        max_steps=20,
        max_seconds=480,
        allocator_conf=plan["allocator_conf"],
    )
    reference = attest_reference(
        reference,
        receipt,
        plan["original_script"],
        plan["reference_script"],
    )
    baseline = read_artifact_json(plan["baseline_result"])
    proof = reference_proof(reference, {}, baseline=baseline)
    unchanged = hashes() == plan["measurement_source_hashes"]
    checks = {
        "completed_20_logical_updates": reference.get("status") == "completed"
        and reference.get("steps") == 20,
        "capture_complete": reference.get("capture_complete") is True,
        "cleanup_verified": reference.get("cleanup_verified") is True,
        "exclusive_cuda_observed": (
            reference.get("env", {}).get("device") == "cuda"
            and reference.get("gpu_observation_complete") is True
            and reference.get("shared_gpu") is False
        ),
        "measured_cuda_peak": (
            type(reference.get("peak_allocated_bytes")) is int
            and reference["peak_allocated_bytes"] > 0
        ),
        "within_480_wall_seconds": type(reference.get("wall_seconds")) in (float, int)
        and reference["wall_seconds"] <= 480,
        "actual_fp32": observed_precision(reference) == "fp32",
        "finite_20_backward_scalars": (
            isinstance(reference.get("loss_series"), list)
            and len(reference["loss_series"]) == 20
            and all(
                type(value) in (int, float) and math.isfinite(value)
                for value in reference["loss_series"]
            )
        ),
        "reviewed_runtime_and_image": (
            str(reference.get("env", {}).get("torch")).split("+")[0] == "2.5.1"
            and reference.get("image_id") == baseline.get("image_id")
            and bool(reference.get("image_id"))
        ),
        "actual_source_argv_transformation": reference["reference_checkpoint"]["request_verified"],
        "actual_pairing_capture_complete": reference.get("pairing_capture", {}).get("complete")
        is True,
        "source_unchanged": unchanged,
    }
    snapshot_observation = {"limit_bytes": 512 * 1024**2, "readable": False}
    try:
        from headroom.evidence_analysis import analyze_snapshot
        from headroom.lab.snapshot_codec import read_snapshot_artifact

        snapshot_path = Path(reference["target_artifact_dir"]) / "snapshot.json"
        snapshot_observation["path"] = str(snapshot_path)
        snapshot_observation["actual_bytes"] = snapshot_path.stat().st_size
        snapshot = read_snapshot_artifact(snapshot_path)
        if not (
            isinstance(snapshot, dict)
            and isinstance(snapshot.get("segments"), list)
            and isinstance(snapshot.get("device_traces"), list)
            and snapshot["segments"]
            and any(snapshot["device_traces"])
        ):
            raise ValueError("Snapshot loader did not produce complete native trace structures")
        snapshot_observation["segments"] = len(snapshot["segments"])
        snapshot_observation["device_trace_events"] = sum(
            len(events) for events in snapshot["device_traces"]
        )
        analysis = analyze_snapshot(snapshot, reference)
        snapshot_observation.update(
            readable=True,
            analysis_keys=sorted(analysis),
            metrics=analysis.get("metrics", {}),
        )
    except (OSError, ValueError, TypeError, KeyError) as error:
        snapshot_observation["error"] = type(error).__name__ + ": " + str(error)
    checks["snapshot_analysis_at_original_limit"] = snapshot_observation["readable"]
    result = {
        "kind": plan["kind"],
        "counts_toward_model_acceptance": False,
        "resource_feasible": all(value is True for value in checks.values()),
        "resource_checks": checks,
        "original_baseline_pairing_proven": False,
        "candidate_run_present": False,
        "full_reference_proof": proof,
        "snapshot_reader": snapshot_observation,
        "baseline_pairing_gap": plan["baseline_pairing_gap"],
        "reference": reference,
    }
    (output / "calibration.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (output / "attempt.json").write_text(
        json.dumps(
            {
                "status": "finished",
                "reference_run_id": reference.get("run_id"),
                "resource_feasible": result["resource_feasible"],
            },
            indent=2,
        )
        + "\n"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--baseline-result", type=Path)
    args = parser.parse_args()
    value = (
        prepare(args.prepare, args.baseline_result, args.output)
        if args.prepare
        else execute(args.output)
    )
    print(
        json.dumps(
            value
            if args.prepare
            else {
                "resource_feasible": value["resource_feasible"],
                "resource_checks": value["resource_checks"],
                "original_baseline_pairing_proven": False,
                "run_id": value["reference"].get("run_id"),
                "status": value["reference"].get("status"),
                "steps": value["reference"].get("steps"),
                "wall_seconds": value["reference"].get("wall_seconds"),
                "peak_allocated_bytes": value["reference"].get("peak_allocated_bytes"),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
