"""Baseline-derived transformed references for the pinned s1 workload.

This does not execute the original source byte for byte. A fixed, reviewed
non-reentrant checkpoint transformation preserves its workload; runtime pairing
must still prove actual inputs, initialization, and complete logical updates.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
from pathlib import Path

from headroom.verify.offload import bind_original_baseline
from headroom.verify.pairing import CONTRACTS, derive_pairing, source_contract
from headroom.verify.precision import observed_precision

STRATEGY = "original_workload_checkpoint"
PROTOCOL = "headroom.reference_checkpoint.v1"
TRANSFORM = "s1_non_reentrant_blocks.v1"


def _source(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
            raise ValueError("Checkpoint reference source must be a regular file within 128 KiB")
        return handle.read(131073)


def _sha(source):
    return hashlib.sha256(source).hexdigest()


def reviewed_block_callsite_nodes(tree):
    """Return only the original call already recognized by this reviewed transform."""
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and ast.unparse(node) == "hidden = block(hidden)"
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one reviewed block invocation")
    return matches


def transform_source(source):
    """Only the caller-verified original s1 program may reach this transformation."""
    tree = ast.parse(source)
    matches = reviewed_block_callsite_nodes(tree)
    matches[0].value = ast.Call(
        func=ast.Name(id="checkpoint", ctx=ast.Load()),
        args=[ast.Name(id="block", ctx=ast.Load()), ast.Name(id="hidden", ctx=ast.Load())],
        keywords=[
            ast.keyword(arg="use_reentrant", value=ast.Constant(False)),
            ast.keyword(arg="preserve_rng_state", value=ast.Constant(True)),
        ],
    )
    tree.body.insert(
        1,
        ast.ImportFrom(
            module="torch.utils.checkpoint",
            names=[ast.alias(name="checkpoint")],
            level=0,
        ),
    )
    ast.fix_missing_locations(tree)
    return (ast.unparse(tree) + "\n").encode()


def prepare_reference(baseline, original_script, original_args, directory, max_seconds):
    """Derive a separate source only from the actual original baseline binding."""
    if type(max_seconds) not in (int, float) or not 0 < max_seconds <= 480:
        raise ValueError("Checkpoint reference wall-clock limit must be within 480 seconds")
    binding = bind_original_baseline(baseline, original_script, original_args)
    contract = source_contract(Path(original_script))
    if not (
        binding.get("valid") is True
        and contract.get("supported") is True
        and contract.get("profile") == "s1"
        and contract.get("checkpointed") is False
    ):
        raise ValueError("Checkpoint reference requires the bound original, unmodified s1 workload")
    original = _source(original_script)
    if _sha(original) != binding["source_sha256"]:
        raise ValueError("Original source changed after baseline binding")
    transformed = transform_source(original)
    directory = Path(directory)
    directory.mkdir(mode=0o700, exist_ok=False)
    script = directory / "train.py"
    with script.open("xb") as handle:
        handle.write(transformed)
    derived_contract = source_contract(script)
    if not (
        derived_contract.get("profile") == "s1"
        and derived_contract.get("supported") is True
        and derived_contract.get("checkpointed") is True
    ):
        raise ValueError("Transformed reference failed the reviewed source contract")
    receipt = {
        "protocol": PROTOCOL,
        "mode": STRATEGY,
        "transform_version": TRANSFORM,
        "source_kind": "baseline_derived_transformed_reference",
        "original_source_sha256": _sha(original),
        "transformed_source_sha256": _sha(transformed),
        "script_args": list(original_args),
        "max_seconds": max_seconds,
        "required_steps": 20,
        "performance_comparable": False,
        "use_reentrant": False,
        "preserve_rng_state": True,
        "original_baseline_binding": binding,
    }
    (directory / "transformation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return script, receipt


def attest_reference(reference, receipt, original_script, transformed_script):
    """Check actual preserved wrapper argv/source, never just an in-memory request."""
    from headroom.lab.runner import read_artifact_json, selected_capture_directory

    value = {**receipt, "request_verified": False, "failure": None}
    try:
        directory = Path(reference["run_dir"])
        manifest = read_artifact_json(directory / "manifest.json")
        selected_capture_directory(directory, reference, manifest)
        command = manifest["command"]
        prefix = command[: command.index("--")] if "--" in command else command
        actual_args = command[command.index("--") + 1 :] if "--" in command else []
        original, transformed = _source(original_script), _source(transformed_script)
        capture = reference.get("pairing_capture", {}).get("source_contract", {})
        matched = (
            "headroom.lab.run_target" in prefix
            and prefix[prefix.index("--max-steps") + 1] == str(receipt["required_steps"])
            and float(prefix[prefix.index("--max-seconds") + 1]) == receipt["max_seconds"]
            and actual_args == receipt["script_args"]
            and _sha(original) == receipt["original_source_sha256"]
            and _sha(transformed) == receipt["transformed_source_sha256"]
            and transform_source(original) == transformed
            and capture.get("source_sha256") == receipt["transformed_source_sha256"]
            and capture.get("profile") == "s1"
            and capture.get("checkpointed") is True
        )
        value["request_verified"] = matched
        if not matched:
            value["failure"] = "checkpoint_reference_execution_mismatch"
    except (OSError, ValueError, TypeError, KeyError, IndexError, SyntaxError) as error:
        value["failure"] = "checkpoint_reference_attestation_failed: " + str(error)
    reference["reference_checkpoint"] = value
    reference["original_baseline_binding"] = receipt["original_baseline_binding"]
    if reference.get("run_dir"):
        (Path(reference["run_dir"]) / "reference-checkpoint.json").write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n"
        )
        (Path(reference["run_dir"]) / "result.json").write_text(
            json.dumps(reference, indent=2, allow_nan=False) + "\n"
        )
    return reference


def reference_proof(reference, candidate, required_steps=20, *, baseline=None):
    reference, candidate, baseline = reference or {}, candidate or {}, baseline or {}
    evidence = reference.get("reference_checkpoint", {})
    binding = reference.get("original_baseline_binding", {})
    capture = reference.get("pairing_capture", {})
    original_capture = baseline.get("pairing_capture", {})
    original_contract = original_capture.get("source_contract", {})
    contract = capture.get("source_contract", {})
    pairing = derive_pairing(reference, candidate, required_steps)
    environments = [item.get("env", {}) for item in (baseline, reference, candidate)]
    env = environments[1]
    before_precision = observed_precision(baseline)
    checks = {
        "original_reference_precision": (
            before_precision in {"fp32", "bf16"}
            and observed_precision(reference) == before_precision
        ),
        "original_baseline_bound": (
            binding.get("valid") is True
            and bool(baseline.get("run_id"))
            and binding.get("baseline_run_id") == baseline.get("run_id")
            and binding.get("source_sha256") == evidence.get("original_source_sha256")
            and binding.get("original_args") == evidence.get("script_args")
            and original_contract.get("source_sha256") == evidence.get("original_source_sha256")
            and original_contract.get("supported") is True
            and original_contract.get("profile") == "s1"
            and original_contract.get("checkpointed") is False
            and original_contract.get("contract_sha256") == CONTRACTS["s1"]["digest"]
            and bool(original_capture.get("tensors"))
            and original_capture.get("tensors") == capture.get("tensors")
            and bool(original_capture.get("initial_parameters"))
            and original_capture.get("initial_parameters") == capture.get("initial_parameters")
        ),
        "fixed_transformation_verified": (
            evidence.get("protocol") == PROTOCOL
            and evidence.get("mode") == STRATEGY
            and evidence.get("transform_version") == TRANSFORM
            and evidence.get("source_kind") == "baseline_derived_transformed_reference"
            and evidence.get("request_verified") is True
            and evidence.get("failure") is None
            and evidence.get("performance_comparable") is False
            and evidence.get("use_reentrant") is False
            and evidence.get("preserve_rng_state") is True
            and evidence.get("required_steps") == required_steps == 20
            and type(evidence.get("max_seconds")) in (int, float)
            and 0 < evidence["max_seconds"] <= 480
            and bool(evidence.get("transformed_source_sha256"))
            and evidence.get("transformed_source_sha256") == contract.get("source_sha256")
            and evidence.get("original_source_sha256") != evidence.get("transformed_source_sha256")
            and contract.get("checkpointed") is True
            and contract.get("profile") == "s1"
            and contract.get("contract_sha256") == CONTRACTS["s1"]["digest"]
        ),
        "checkpoint_recomputation_observed": (
            type(capture.get("checkpoint_recomputation_root_forwards")) is int
            and capture["checkpoint_recomputation_root_forwards"] >= required_steps
        ),
        "same_runtime": (
            env.get("device") == "cuda"
            and str(env.get("torch")).split("+")[0] == "2.5.1"
            and bool(env.get("cuda"))
            and bool(env.get("gpu_name"))
            and bool(reference.get("image_id"))
            and all(
                all(
                    other.get(key) == env.get(key)
                    for key in (
                        "device",
                        "torch",
                        "cuda",
                        "gpu_name",
                        "PYTORCH_CUDA_ALLOC_CONF",
                    )
                )
                for other in environments
            )
            and baseline.get("image_id") == reference.get("image_id") == candidate.get("image_id")
        ),
        "complete_reference": (
            reference.get("protocol") == "headroom.lab.v1"
            and reference.get("capture_complete") is True
            and reference.get("cleanup_verified") is True
            and reference.get("status") == "completed"
            and reference.get("steps") == required_steps
            and reference.get("shared_gpu") is False
            and reference.get("gpu_observation_complete") is True
        ),
        **pairing["checks"],
    }
    return {"valid": all(value is True for value in checks.values()), "checks": checks}
