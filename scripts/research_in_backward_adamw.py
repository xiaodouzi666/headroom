"""Prepare/run explicit optimizer research controls, never model acceptance scores."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

from headroom.lab.runner import read_artifact_json, run_script
from headroom.verify.compare import compare_runs

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENT_FILES = (
    "headroom/optim/in_backward_adamw.py",
    "headroom/optim/control_capture.py",
    "headroom/lab/hooks.py",
    "headroom/lab/runner.py",
    "headroom/lab/run_target.py",
)


def hashes():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in MEASUREMENT_FILES
    }


def prepare(script, output):
    script, output = Path(script).resolve(strict=True), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = script.read_text()
    variants = {}
    for variant in ("baseline", "control"):
        tree = ast.parse(raw)
        run = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        index = next(i for i, node in enumerate(run.body) if isinstance(node, ast.For))
        setup = ast.parse(
            "_research_capture = TrainingControlCapture()\n"
            "_research_capture.snapshot('initial', model, optimizer, "
            "{'inputs': inputs, 'labels': labels})"
        ).body
        final = ast.parse(
            "_research_capture.snapshot('final', model, optimizer, "
            "{'inputs': inputs, 'labels': labels})"
        ).body
        run.body = (
            run.body[:index]
            + setup
            + [ast.Try(body=run.body[index:], handlers=[], orelse=[], finalbody=final)]
        )
        imports = ast.parse(
            "from headroom.optim.control_capture import TrainingControlCapture"
        ).body
        if variant == "control":
            matches = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call) and ast.unparse(node.func) == "torch.optim.AdamW"
            ]
            if len(matches) != 1:
                raise ValueError("Explicit control requires exactly one AdamW constructor")
            matches[0].func = ast.Name(id="AdamWInBackward", ctx=ast.Load())
            imports += ast.parse(
                "from headroom.optim.in_backward_adamw import AdamWInBackward"
            ).body
        insertion = (
            1
            if isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant)
            else 0
        )
        tree.body[insertion:insertion] = imports
        ast.fix_missing_locations(tree)
        directory = output / "sources" / variant
        directory.mkdir(parents=True)
        destination = directory / "train.py"
        destination.write_text(ast.unparse(tree) + "\n")
        variants[variant] = {
            "script": str(destination),
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    plan = {
        "protocol": "headroom.optimizer_research_plan.v1",
        "counts_toward_model_acceptance": False,
        "origin_script": str(script),
        "origin_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "measurement_source_hashes": hashes(),
        "variants": variants,
        "gates": {
            "required_logical_updates": 20,
            "mvp_reclaim_reduction_pct": 20,
            "default_reclaim_reduction_pct": 30,
            "max_throughput_regression_pct": 25,
            "fp32_loss_tolerance": 0.001,
            "model_parameters_and_training_semantics_unchanged": True,
        },
        "gpu_limit": {"maximum_runs": 4, "max_seconds_each": 180},
        "conditions": ["tiny-baseline", "tiny-control", "full-baseline", "full-control"],
        "helper_boundary": "Manual control uses runtime helpers; never supplied as a model patch or counted as model success.",
        "fingerprint_timing": "Initial/final snapshots outside loop; both variants use identical capture.",
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def execute(output, phase, variant, device):
    output = Path(output).resolve(strict=True)
    plan = read_artifact_json(output / "plan.json")
    if plan["measurement_source_hashes"] != hashes():
        raise ValueError("Research measurement/helper source changed after registration")
    entry = plan["variants"][variant]
    script = Path(entry["script"])
    if hashlib.sha256(script.read_bytes()).hexdigest() != entry["sha256"]:
        raise ValueError("Prepared control source changed")
    attempts = output / "attempts"
    attempts.mkdir(exist_ok=True)
    receipt = attempts / f"{device}-{phase}-{variant}.json"
    with receipt.open("x") as handle:
        json.dump(
            {"status": "reserved", "phase": phase, "variant": variant, "device": device}, handle
        )
    args = ["--device", device] + (["--tiny"] if phase == "tiny" else [])
    result = run_script(
        script,
        script_args=args,
        device=device,
        max_steps=20,
        max_seconds=180,
        seed=1337,
        run_root=output / "runs",
    )
    value = {
        "phase": phase,
        "variant": variant,
        "device": device,
        "run": result,
        "measurement_source_unchanged": plan["measurement_source_hashes"] == hashes(),
        "counts_toward_model_acceptance": False,
    }
    artifact = Path(result.get("target_artifact_dir", Path(result["run_dir"]) / "artifacts"))
    for moment in ("initial", "final"):
        path = artifact / ("control-" + moment + ".json")
        value[moment] = read_artifact_json(path) if path.exists() else None
    receipt.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "phase": phase,
                "variant": variant,
                "device": device,
                "status": result["status"],
                "steps": result.get("steps"),
                "run_dir": result["run_dir"],
                "peak_allocated_bytes": result.get("peak_allocated_bytes"),
                "step_ms_median": result.get("step_ms_median"),
                "initial_fingerprints": value["initial"] is not None,
                "final_fingerprints": value["final"] is not None,
            }
        ),
        flush=True,
    )
    return value


def summarize(output, phase, device):
    output = Path(output)
    records = [
        read_artifact_json(output / "attempts" / f"{device}-{phase}-{variant}.json")
        for variant in ("baseline", "control")
    ]
    left, right = records
    checks = {}
    for moment in ("initial", "final"):
        for key in ("inputs", "parameters", "optimizer_state", "parameter_groups"):
            checks[moment + "_" + key] = (
                left.get(moment) is not None
                and right.get(moment) is not None
                and left[moment][key] == right[moment][key]
            )
    summary = {
        "kind": "human_authored_optimizer_feasibility_control",
        "counts_toward_model_acceptance": False,
        "fingerprint_checks": checks,
        "source_unchanged": all(record["measurement_source_unchanged"] for record in records),
        "mvp_scalar_report": compare_runs(
            left["run"],
            right["run"],
            target="reclaim",
            reclaim_reduction_pct=20,
        ).model_dump(),
        "default_reclaim_report": compare_runs(
            left["run"],
            right["run"],
            target="reclaim",
            reclaim_reduction_pct=30,
        ).model_dump(),
        "notes": "Research snapshots prove this controlled pair only; generic production s7 pairing remains unsupported.",
    }
    (output / f"{device}-{phase}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", type=Path)
    parser.add_argument("--phase", choices=("tiny", "full"))
    parser.add_argument("--variant", choices=("baseline", "control"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        print(json.dumps(prepare(args.prepare, args.output)), flush=True)
    elif args.summarize:
        print(json.dumps(summarize(args.output, args.phase, args.device)), flush=True)
    elif args.phase and args.variant:
        execute(args.output, args.phase, args.variant, args.device)
    else:
        parser.error("Select prepare, explicit phase/variant execution, or summarize")


if __name__ == "__main__":
    main()
