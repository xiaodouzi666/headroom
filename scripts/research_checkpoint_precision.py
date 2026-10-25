"""Preregister two tiny CUDA checkpoint-observer regressions; never model scores."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from headroom.lab.runner import read_artifact_json, run_script
from headroom.verify.compare import compare_runs
from headroom.verify.precision import observed_precision

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "headroom/lab/precision.py",
    "headroom/lab/hooks.py",
    "headroom/lab/runner.py",
    "headroom/lab/run_target.py",
    "headroom/verify/precision.py",
    "scripts/research_checkpoint_precision.py",
)
SOURCE = r"""
import argparse
import json
import threading

import torch
from torch.utils.checkpoint import checkpoint
from torch.overrides import _get_current_function_mode_stack

parser = argparse.ArgumentParser()
parser.add_argument("--bf16", action="store_true")
args = parser.parse_args()
torch.manual_seed(17)
events = []

class Model(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.weight = torch.nn.Parameter(torch.randn(32, 32, device="cuda"))
    def body(self, value):
        events.append({
            "graph_task": torch._C._current_graph_task_id(),
            "thread": threading.get_ident(),
            "mode_active": any(type(item).__name__ == "_PrecisionMode"
                               for item in _get_current_function_mode_stack()),
        })
        with torch.autocast("cuda", dtype=torch.bfloat16, enabled=args.bf16):
            return torch.nn.functional.linear(value, self.weight).float().sin()
    def forward(self, value):
        return checkpoint(self.body, value, use_reentrant=False)

model = Model()
optimizer = torch.optim.SGD(model.parameters(), lr=0.001)
inputs = torch.randn(8, 32, device="cuda")
try:
    for _ in range(20):
        optimizer.zero_grad(set_to_none=True)
        loss = model(inputs).square().mean()
        loss.backward()
        optimizer.step()
finally:
    forward = [item for item in events if item["graph_task"] == -1]
    recompute = [item for item in events if item["graph_task"] >= 0]
    print(json.dumps({
        "event": "checkpoint_precision_probe",
        "forward_calls": len(forward),
        "recompute_calls": len(recompute),
        "forward_mode_active": bool(forward) and all(item["mode_active"] for item in forward),
        "recompute_mode_active": bool(recompute) and all(item["mode_active"] for item in recompute),
        "different_recompute_thread": bool(forward) and any(
            item["thread"] != forward[0]["thread"] for item in recompute
        ),
    }), flush=True)
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes():
    return {name: sha(ROOT / name) for name in FILES}


def prepare(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / "source"
    source.mkdir()
    script = source / "train.py"
    script.write_text(SOURCE)
    plan = {
        "kind": "manual_checkpoint_precision_observer_regression",
        "counts_toward_model_acceptance": False,
        "maximum_gpu_runs": 2,
        "max_seconds_each": 60,
        "required_logical_updates": 20,
        "script": str(script),
        "script_sha256": sha(script),
        "measurement_source_hashes": hashes(),
        "conditions": [
            {"name": "fp32", "script_args": [], "expected_precision": "fp32"},
            {"name": "bf16", "script_args": ["--bf16"], "expected_precision": "bf16"},
        ],
        "requires_actual_worker_mode_before_function_body": True,
        "unknown_is_not_success": True,
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    return plan


def execute(output, name):
    output = Path(output).resolve(strict=True)
    plan = read_artifact_json(output / "plan.json")
    if (
        plan["measurement_source_hashes"] != hashes()
        or sha(plan["script"]) != plan["script_sha256"]
    ):
        raise ValueError("Registered source changed")
    condition = next(item for item in plan["conditions"] if item["name"] == name)
    with (output / (name + "-attempt.json")).open("x") as handle:
        json.dump({"status": "reserved"}, handle)
    result = run_script(
        plan["script"],
        script_args=condition["script_args"],
        source_root=Path(plan["script"]).parent,
        run_root=output / "runs",
        device="cuda",
        seed=1337,
        max_steps=20,
        max_seconds=60,
    )
    probe = None
    stdout = Path(result.get("stdout_path") or Path(result["run_dir"]) / "stdout.log")
    if stdout.exists():
        with stdout.open("r") as handle:
            for line in handle:
                if len(line) > 16384:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get("event") == "checkpoint_precision_probe":
                    probe = event
    precision = result.get("precision_observation", {})
    lifecycle = precision.get("operation_mode_lifecycle", {})
    recompute = precision.get("checkpoint_recompute", {})
    checks = {
        "completed_20_logical_updates": result.get("status") == "completed"
        and result.get("steps") == 20,
        "actual_expected_precision": observed_precision(result) == condition["expected_precision"],
        "cleanup_verified": result.get("cleanup_verified") is True,
        "exclusive_cuda_observed": result.get("gpu_observation_complete") is True
        and result.get("shared_gpu") is False,
        "actual_worker_observer_registered": precision.get("worker_observers", {}).get(
            "registered", 0
        )
        > 0,
        "recompute_contexts_closed": recompute.get("entered") == recompute.get("exited") == 20,
        "operation_modes_closed": type(lifecycle.get("entered")) is int
        and lifecycle["entered"] > 0
        and lifecycle["entered"] == lifecycle.get("exited"),
        "function_body_observed_before_execution": bool(probe)
        and probe.get("forward_calls") == probe.get("recompute_calls") == 20
        and probe.get("forward_mode_active") is True
        and probe.get("recompute_mode_active") is True
        and probe.get("different_recompute_thread") is True,
        "measurement_source_unchanged": plan["measurement_source_hashes"] == hashes(),
    }
    value = {
        "kind": plan["kind"],
        "counts_toward_model_acceptance": False,
        "condition": name,
        "passed": all(item is True for item in checks.values()),
        "checks": checks,
        "probe": probe,
        "run": result,
    }
    (output / (name + "-result.json")).write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n"
    )
    return value


def summarize(output):
    output = Path(output)
    fp32 = read_artifact_json(output / "fp32-result.json")
    bf16 = read_artifact_json(output / "bf16-result.json")
    report = compare_runs(fp32["run"], bf16["run"], target="reclaim")
    value = {
        "kind": "manual_checkpoint_precision_observer_regression",
        "counts_toward_model_acceptance": False,
        "passed": fp32["passed"]
        and bf16["passed"]
        and report.observed_precision_change
        and not report.checks["numerics_policy"],
        "conditions": {item["condition"]: item["checks"] for item in (fp32, bf16)},
        "bf16_not_misclassified_fp32": report.observed_precision_change,
        "default_policy_rejects_precision_change": not report.checks["numerics_policy"],
    }
    (output / "summary.json").write_text(json.dumps(value, indent=2) + "\n")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--condition", choices=("fp32", "bf16"))
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        value = prepare(args.output)
    elif args.summarize:
        value = summarize(args.output)
    elif args.condition:
        full = execute(args.output, args.condition)
        value = {key: full[key] for key in ("condition", "passed", "checks", "probe")}
        value["run_id"] = full["run"]["run_id"]
    else:
        parser.error("Select prepare, condition or summarize")
    print(json.dumps(value), flush=True)


if __name__ == "__main__":
    main()
