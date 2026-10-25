"""Candidate and small-batch reference runs always use the existing Docker Lab."""

import ast
import json
import os
import stat
from pathlib import Path

import yaml

from headroom.lab.runner import read_artifact_json, run_script
from headroom.verify.checkpoint import STRATEGY as CHECKPOINT_STRATEGY
from headroom.verify.checkpoint import attest_reference, prepare_reference
from headroom.verify.compare import compare_runs
from headroom.verify.offload import (
    LEGACY_STRATEGY,
    MAX_SAVED_BYTES,
    STRATEGY,
    bind_original_baseline,
    validate_limit,
)
from headroom.verify.pairing import derive_pairing, source_contract

_ALLOWED_BATCH_FLAGS = {"--batch", "--batch_size", "--batch-size"}


def load_result(path):
    result = read_artifact_json(path)
    if not isinstance(result, dict):
        raise TypeError("Lab result must be a JSON object")
    return result


def _config(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise ValueError("headroom.yaml must be a regular file of at most 16 KiB")
        result = yaml.safe_load(handle.read(16385))
    if not isinstance(result, dict):
        raise TypeError("headroom.yaml must contain a mapping")
    return result


def discover_batch(script, script_args=()):
    """Inspect argparse/config without executing the user script or importing it."""
    script = Path(script).resolve(strict=True)
    found = {}
    try:
        tree = ast.parse(script.read_text())
    except (ValueError, SyntaxError, UnicodeError):
        return {"found": False, "reason": "Script cannot be inspected as Python"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        flags = [
            v.value
            for v in node.args
            if isinstance(v, ast.Constant) and v.value in _ALLOWED_BATCH_FLAGS
        ]
        if len(flags) != 1:
            continue
        default = next(
            (
                kw.value.value
                for kw in node.keywords
                if kw.arg == "default" and isinstance(kw.value, ast.Constant)
            ),
            None,
        )
        found[flags[0]] = default if type(default) is int and default > 0 else None
    config_path = script.parent / "headroom.yaml"
    if config_path.exists() or config_path.is_symlink():
        try:
            cfg = _config(config_path)
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            return {"found": False, "reason": "headroom.yaml is invalid or unsafe"}
        batch = cfg.get("batch")
        flag = batch.get("arg") if isinstance(batch, dict) else cfg.get("batch_arg")
        value = batch.get("value") if isinstance(batch, dict) else batch
        if flag is not None:
            if flag not in _ALLOWED_BATCH_FLAGS or (
                value is not None and (type(value) is not int or value < 1)
            ):
                return {"found": False, "reason": "Invalid explicit batch argument configuration"}
            found = {flag: value}
    if len(found) != 1:
        return {"found": False, "reason": "No single discoverable batch argument"}
    flag, default = next(iter(found.items()))
    values = []
    args = list(script_args)
    for i, arg in enumerate(args):
        if arg == flag:
            if i + 1 >= len(args):
                return {"found": False, "reason": "Batch argument has no value"}
            values.append(args[i + 1])
        elif arg.startswith(flag + "="):
            values.append(arg.partition("=")[2])
    if len(values) > 1:
        return {"found": False, "reason": "Duplicate batch arguments are ambiguous"}
    if values:
        try:
            default = int(values[0])
        except ValueError:
            return {"found": False, "reason": "Batch argument is not an integer"}
        if default < 1:
            return {"found": False, "reason": "Batch argument must be positive"}
    return {
        "found": True,
        "flag": flag,
        "original_batch": default,
        "source": "headroom.yaml/argparse static inspection",
        "reference_batch": 1,
    }


def batch_arguments(args, flag, value):
    """Replace a batch argument while preserving its last explicit argv syntax."""
    result = []
    equals_style = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == flag:
            equals_style = False
            index += 2
            continue
        if arg.startswith(flag + "="):
            equals_style = True
            index += 1
            continue
        result.append(arg)
        index += 1
    return [*result, f"{flag}={value}"] if equals_style else [*result, flag, str(value)]


def verify_script(
    baseline,
    candidate_script,
    *,
    baseline_script=None,
    script_args=(),
    execution_argv=None,
    execution_entrypoint=None,
    baseline_execution_argv=None,
    baseline_args=None,
    candidate_source_root=None,
    baseline_source_root=None,
    run_root=None,
    target="fix-oom",
    policy=None,
    pairing=None,
    reference=None,
    device="cuda",
    seed=None,
    max_seconds=120,
    required_steps=20,
    allocator_conf=None,
    baseline_allocator_conf=None,
    max_reference_attempts=4,
    reference_strategy=LEGACY_STRATEGY,
    reference_offload_bytes=MAX_SAVED_BYTES,
    reference_offload_disk_bytes=0,
    reference_max_seconds=None,
    **comparison_options,
):
    """Return candidate/reference evidence and VerifyReport; never changes source.

    max_reference_attempts bounds execution, not acceptance: exhaustion leaves
    reference unavailable. Every attempted reference is retained in the report.
    """
    if reference_strategy not in {LEGACY_STRATEGY, STRATEGY, CHECKPOINT_STRATEGY}:
        raise ValueError("Unknown numerical reference strategy")
    if reference_strategy == STRATEGY:
        validate_limit(reference_offload_bytes)
        from headroom.verify.offload_disk import validate_disk_limit

        validate_disk_limit(reference_offload_disk_bytes)
        if reference_max_seconds is not None and (
            type(reference_max_seconds) not in (int, float) or not 0 < reference_max_seconds <= 480
        ):
            raise ValueError("Reference wall-clock budget must be positive and at most 480 seconds")
        if reference is not None:
            raise ValueError("Original-workload offload must execute its own bound reference")
    if reference_strategy == CHECKPOINT_STRATEGY:
        if reference is not None:
            raise ValueError("Checkpoint reference must execute its own baseline-derived source")
        if required_steps != 20 or type(required_steps) is not int:
            raise ValueError("Checkpoint reference requires 20 complete logical updates")
        if reference_offload_bytes != MAX_SAVED_BYTES or reference_offload_disk_bytes != 0:
            raise ValueError("Checkpoint reference does not use saved-tensor offload settings")
        reference_budget = max_seconds if reference_max_seconds is None else reference_max_seconds
        if type(reference_budget) not in (int, float) or not 0 < reference_budget <= 480:
            raise ValueError("Reference wall-clock budget must be positive and at most 480 seconds")
    if type(max_reference_attempts) is not int or max_reference_attempts < 1:
        raise ValueError("max_reference_attempts must be a positive integer")
    seed = baseline.get("env", {}).get("seed") if seed is None else seed
    if type(seed) is not int:
        raise ValueError("Verification requires an explicit or recorded baseline seed")
    command_options = {"execution_argv": execution_argv} if execution_argv is not None else {}
    if execution_entrypoint is not None:
        command_options["execution_entrypoint"] = execution_entrypoint
    original_command = (
        execution_argv if baseline_execution_argv is None else baseline_execution_argv
    )
    baseline_command_options = (
        {"execution_argv": original_command} if original_command is not None else {}
    )
    if execution_entrypoint is not None:
        baseline_command_options["execution_entrypoint"] = execution_entrypoint
    candidate = run_script(
        candidate_script,
        script_args=script_args,
        source_root=candidate_source_root,
        run_root=run_root,
        max_steps=required_steps,
        max_seconds=max_seconds,
        seed=seed,
        device=device,
        allocator_conf=allocator_conf,
        **command_options,
    )
    discovery = {
        "found": False,
        "reason": "Baseline did not OOM or reference already supplied",
        "attempts": [],
    }
    if baseline.get("status") == "oom" and reference is None:
        if baseline_script is None:
            discovery["reason"] = (
                "Original baseline script is required for the small-batch reference"
            )
        elif candidate.get("status") == "completed":
            if baseline_args is None:
                try:
                    if execution_entrypoint is not None:
                        baseline_args = list(execution_entrypoint["script_args"])
                    elif original_command is not None:
                        from headroom.execution import parse_command

                        baseline_args = list(parse_command(original_command).script_args)
                    else:
                        manifest_path = Path(baseline.get("run_dir", "")) / "manifest.json"
                        manifest = read_artifact_json(manifest_path)
                        command = manifest["command"]
                        baseline_args = (
                            command[command.index("--") + 1 :] if "--" in command else []
                        )
                except (OSError, ValueError, TypeError, KeyError):
                    baseline_args = None
            if baseline_args is None:
                discovery = {
                    "found": False,
                    "reason": "Original baseline argv unavailable; supply baseline_args",
                    "attempts": [],
                }
                reference_args = []
            else:
                reference_args = list(baseline_args)
                discovery = {**discover_batch(baseline_script, reference_args), "attempts": []}
            if reference_strategy == STRATEGY:
                binding = bind_original_baseline(baseline, baseline_script, reference_args)
                supported = (
                    binding["valid"]
                    and baseline_args is not None
                    and not baseline_command_options
                    and source_contract(Path(baseline_script)).get("supported") is True
                    and source_contract(Path(candidate_script)).get("supported") is True
                )
                discovery = {
                    "found": False,
                    "strategy": STRATEGY,
                    "attempts": [],
                    "reason": "Original-workload offload requires reviewed standalone sources and original argv",
                    "baseline_binding": binding,
                }
                if supported:
                    reference = run_script(
                        baseline_script,
                        script_args=reference_args,
                        source_root=baseline_source_root,
                        run_root=run_root,
                        max_steps=required_steps,
                        max_seconds=max_seconds
                        if reference_max_seconds is None
                        else reference_max_seconds,
                        seed=seed,
                        device=device,
                        allocator_conf=baseline_allocator_conf,
                        reference_offload_bytes=reference_offload_bytes,
                        reference_offload_disk_bytes=reference_offload_disk_bytes,
                    )
                    reference["original_baseline_binding"] = binding
                    if reference.get("run_dir"):
                        with (Path(reference["run_dir"]) / "result.json").open("w") as handle:
                            json.dump(reference, handle, indent=2, allow_nan=False)
                            handle.write("\n")
                    discovery.update(
                        found=True,
                        reason="Original argv/batch saved-tensor offload reference",
                        original_args=reference_args,
                        max_saved_bytes=reference_offload_bytes,
                        max_disk_bytes=reference_offload_disk_bytes,
                        attempts=[
                            {
                                "run_dir": reference.get("run_dir"),
                                "status": reference.get("status"),
                                "strategy": STRATEGY,
                            }
                        ],
                    )
            elif reference_strategy == CHECKPOINT_STRATEGY:
                discovery = {
                    "found": False,
                    "strategy": CHECKPOINT_STRATEGY,
                    "attempts": [],
                    "reason": "Checkpoint reference requires bound original standalone s1 source and argv",
                }
                original_contract = source_contract(Path(baseline_script))
                candidate_contract = source_contract(Path(candidate_script))
                supported = (
                    baseline_args is not None
                    and not baseline_command_options
                    and original_contract.get("supported") is True
                    and original_contract.get("profile") == "s1"
                    and original_contract.get("checkpointed") is False
                    and candidate_contract.get("supported") is True
                    and candidate_contract.get("profile") == "s1"
                )
                if supported:
                    try:
                        transformed_script, receipt = prepare_reference(
                            baseline,
                            baseline_script,
                            reference_args,
                            Path(candidate["run_dir"]) / "checkpoint-reference-source",
                            reference_budget,
                        )
                    except (OSError, ValueError, TypeError, KeyError) as error:
                        discovery["reason"] = "Checkpoint reference preparation failed: " + str(
                            error
                        )
                    else:
                        reference = run_script(
                            transformed_script,
                            script_args=reference_args,
                            source_root=transformed_script.parent,
                            run_root=run_root,
                            max_steps=required_steps,
                            max_seconds=reference_budget,
                            seed=seed,
                            device=device,
                            allocator_conf=baseline_allocator_conf,
                        )
                        reference = attest_reference(
                            reference,
                            receipt,
                            baseline_script,
                            transformed_script,
                        )
                        discovery.update(
                            found=True,
                            reason="Baseline-derived transformed checkpoint reference; original argv and workload",
                            source_kind="baseline_derived_transformed_reference",
                            transformation=reference["reference_checkpoint"],
                            original_args=reference_args,
                            attempts=[
                                {
                                    "run_dir": reference.get("run_dir"),
                                    "status": reference.get("status"),
                                    "strategy": CHECKPOINT_STRATEGY,
                                }
                            ],
                        )
            elif discovery["found"]:
                upper = discovery["original_batch"] or max_reference_attempts
                upper = min(upper, max_reference_attempts)
                for batch in range(1, upper + 1):
                    observed = run_script(
                        baseline_script,
                        script_args=batch_arguments(reference_args, discovery["flag"], batch),
                        source_root=baseline_source_root,
                        run_root=run_root,
                        max_steps=required_steps,
                        max_seconds=max_seconds,
                        seed=seed,
                        device=device,
                        allocator_conf=baseline_allocator_conf,
                        **baseline_command_options,
                    )
                    discovery["attempts"].append(
                        {
                            "batch": batch,
                            "run_dir": observed.get("run_dir"),
                            "status": observed.get("status"),
                        }
                    )
                    if (
                        observed.get("status") == "completed"
                        and observed.get("steps") == required_steps
                    ):
                        reference = observed
                        discovery["reference_batch"] = batch
                        break
                    if observed.get("status") in {"oom", "timeout"} or observed.get("reason") in {
                        "GPU_BUSY",
                        "GPU_UNAVAILABLE",
                    }:
                        break
        else:
            discovery["reason"] = (
                "Candidate did not complete; small-batch reference was not executed"
            )
    pairing_evidence = derive_pairing(
        reference if baseline.get("status") == "oom" else baseline, candidate, required_steps
    )
    if pairing is None:
        pairing = pairing_evidence["checks"]
    else:
        pairing_evidence = {
            **pairing_evidence,
            "source": "explicit caller-supplied pairing (not automatic runtime proof)",
            "checks": dict(pairing),
        }
    report = compare_runs(
        baseline,
        candidate,
        target=target,
        policy=policy,
        reference=reference,
        pairing=pairing,
        required_steps=required_steps,
        reference_strategy=reference_strategy,
        **comparison_options,
    )
    report.notes.append(
        "Pairing: "
        + pairing_evidence["source"]
        + "; "
        + ("; ".join(pairing_evidence["reasons"]) or "all three pairing checks matched")
    )
    report.notes.append(
        "Reference discovery: " + discovery.get("reason", discovery.get("source", "provided"))
    )
    if baseline.get("status") == "oom" and reference is None:
        report.notes.append(
            "Explicit original-workload reference unavailable; no legacy fallback is performed."
            if reference_strategy != LEGACY_STRATEGY
            else "Small-batch reference unavailable; loss equivalence is n/a under the original no-reference rule."
        )
    payload = {
        "report": report.model_dump(),
        "reference_discovery": discovery,
        "pairing_evidence": pairing_evidence,
        "candidate_run_dir": candidate.get("run_dir"),
        "reference_run_dir": reference.get("run_dir") if reference else None,
    }
    if candidate.get("run_dir"):
        destination = Path(candidate["run_dir"]) / "verification.json"
        with destination.open("x") as handle:
            json.dump(payload, handle, indent=2, allow_nan=False)
            handle.write("\n")
    return {
        "report": report,
        "candidate": candidate,
        "reference": reference,
        "reference_discovery": discovery,
        "pairing_evidence": pairing_evidence,
    }
