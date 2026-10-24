"""T2.7 paired measurements with an independent container-enclosed subprocess.

The production arm uses Lab run_script. The reference arm shares only immutable
isolation construction, source/cache validation, clock and capture protocol; its
controller, scheduling, timeout handling and cleanup are separate implementations.
No model/client/credential imports or paid calls are used.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from headroom.lab import docker
from headroom.lab.deadline import NANOSECONDS, publish_deadline
from headroom.lab.envs import HOST_ENV, container_environment, validate_options
from headroom.lab.runner import (
    PROJECT_ROOT,
    _gpu_lock,
    copy_source,
    gpu_state,
    merge_gpu_observations,
    read_artifact_json,
    read_capture,
    run_script,
)
from headroom.lab.subprocess_reference import validate_request, write_json

PROTOCOL = "headroom.subprocess-reference.v1"
GPU_CASES = {
    "s1": (
        "scenarios/s1_batch_too_big/train.py",
        [],
        "oom",
        "668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28",
    ),
    "s3": (
        "scenarios/s3_eval_no_grad_missing/train.py",
        [],
        "completed",
        "7fedcae13989b309cc5a034e62284094829057654aebb2e716c3413dfb0fea67",
    ),
    "hf_trainer": (
        "repos/hf_trainer/train.py",
        [],
        "oom",
        "7d3a714264fc76371c1183da125ec0ffa550bc78c68bbe2acd7868870684923a",
    ),
}


def _command(argv, timeout):
    if timeout <= 0:
        raise subprocess.TimeoutExpired(argv, timeout)
    return subprocess.run(
        argv,
        env=HOST_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _inspect(name, timeout=5.0):
    observed = _command(
        [
            docker.docker_binary(),
            "inspect",
            "--type",
            "container",
            "--format",
            '{"state":{{json .State}},"image_id":{{json .Image}}}',
            name,
        ],
        timeout,
    )
    if observed.returncode:
        return {
            "inspection_error": observed.stderr[-2000:],
            "inspect_returncode": observed.returncode,
        }
    record = json.loads(observed.stdout)
    if not isinstance(record.get("state"), dict):
        raise TypeError("Reference container state unavailable")
    return record


def _cleanup(name):
    operations = []
    for action in (["kill", name], ["rm", "--force", name]):
        try:
            response = _command([docker.docker_binary(), *action], 8)
            operations.append({"operation": action[0], "returncode": response.returncode})
        except (OSError, subprocess.TimeoutExpired) as error:
            operations.append({"operation": action[0], "error_type": type(error).__name__})
    try:
        response = _command([docker.docker_binary(), "inspect", "--type", "container", name], 8)
        message = response.stderr.casefold()
        absent = (
            response.returncode != 0
            and name.casefold() in message
            and any(token in message for token in ("no such object:", "no such container:"))
        )
    except (OSError, subprocess.TimeoutExpired):
        absent = False
    return {"cleanup_verified": absent, "cleanup_operations": operations}


def _execute_reference(create_args, name, directory, control, max_seconds):
    """Separate host controller: no production docker.execute/start-attach loop."""
    result = {"timed_out": False, "state": None, "cleanup_verified": False}
    try:
        created = _command(create_args, 30)
        (directory / "container-create.log").write_text(created.stderr[-10000:])
        if created.returncode:
            result["error"] = "REFERENCE_CONTAINER_CREATE_FAILED"
            return result
        record = publish_deadline(control, max_seconds)
        result["deadline_control"] = record
        hard = record["hard_deadline_monotonic_ns"]

        def remaining():
            return max(0, (hard - time.monotonic_ns()) / NANOSECONDS)

        started = _command([docker.docker_binary(), "start", name], remaining())
        if started.returncode:
            result["error"] = "REFERENCE_CONTAINER_START_FAILED"
            return result
        while remaining() > 0:
            observed = _inspect(name, min(3.0, remaining()))
            result.update(observed)
            if remaining() <= 0:
                result["timed_out"] = True
                break
            state = observed.get("state")
            if state is None:
                result["error"] = "REFERENCE_CONTAINER_INSPECTION_FAILED"
                break
            if not state.get("Running"):
                break
            time.sleep(min(0.05, remaining()))
        else:
            result["timed_out"] = True
        if result["timed_out"]:
            _command([docker.docker_binary(), "kill", name], 3)
            result.update(_inspect(name, 3))
    except subprocess.TimeoutExpired:
        result.update(timed_out=True, error="REFERENCE_CONTROLLER_DEADLINE")
    except (OSError, ValueError, TypeError) as error:
        result.update(error="REFERENCE_CONTROLLER_ERROR", error_type=type(error).__name__)
    finally:
        result.update(_cleanup(name))
        write_json(directory / "execution.json", result)
    return result


def run_subprocess_reference(
    script,
    *,
    source_root=None,
    script_args=(),
    run_root,
    device="cpu",
    max_steps=20,
    max_seconds=120,
    seed=1337,
    allocator_conf=None,
    project_root=PROJECT_ROOT,
):
    """Only execute targets within the existing immutable, no-network Docker boundary."""
    validate_options(device, max_steps, max_seconds, seed)
    script = Path(script).resolve(strict=True)
    source = Path(source_root).resolve(strict=True) if source_root else script.parent
    if not script.is_file() or not script.is_relative_to(source):
        raise ValueError("Reference script is outside source")
    request = {
        "schema": PROTOCOL,
        "script": script.relative_to(source).as_posix(),
        "script_args": list(script_args),
        "device": device,
        "max_steps": max_steps,
        "max_seconds": max_seconds,
        "seed": seed,
        "allocator_conf": allocator_conf,
    }
    validate_request(request)
    root = Path(run_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    directory = root / run_id
    directory.mkdir(mode=0o700)
    artifacts = directory / "artifacts"
    artifacts.mkdir()
    control = directory / "control"
    control.mkdir(mode=0o700)
    name = "headroom-reference-" + run_id
    result = {
        "run_id": run_id,
        "run_dir": str(directory),
        "status": "error",
        "reason": "REFERENCE_PREPARATION_FAILED",
        "capture_complete": False,
        "cleanup_verified": True,
        "provenance": "independent_subprocess_component_measurement",
        "model_api_calls": 0,
        "cost_usd": "0",
    }
    manifest = {
        "schema": PROTOCOL,
        "request": request,
        "container_name": name,
        "source_root": str(source),
        "started_at": datetime.now(UTC).isoformat(),
        "isolation": "Docker envelope; independent Python subprocess controller",
    }
    try:
        source_record = copy_source(source, directory / "source", (root, directory))
        if request["script"] not in source_record["files"]:
            raise ValueError("Reference script excluded from bounded source copy")
        manifest["source"] = source_record
        write_json(control / "request.json", request)
        (control / "request.json").chmod(0o444)
        environment = container_environment(
            device=device,
            max_steps=max_steps,
            max_seconds=max_seconds,
            seed=seed,
            allocator_conf=allocator_conf,
            command_mode=False,
        )
        # The trusted controller is not a captured training process.
        assert "HEADROOM_CAPTURE" not in environment
        manifest["controller_environment"] = environment
        write_json(directory / "manifest.json", manifest)
        with _gpu_lock(device):
            before = gpu_state() if device == "cuda" else {"queried": False, "processes": []}
            result["gpu_before"] = before
            if device == "cuda" and (not before.get("available") or before["processes"]):
                result["reason"] = "GPU_BUSY_OR_UNAVAILABLE"
                return result
            argv = docker.create_arguments(
                name=name,
                project_root=Path(project_root),
                source=directory / "source",
                output=artifacts,
                environment=environment,
                command=["/opt/venv/bin/python", "-m", "headroom.lab.subprocess_reference"],
                device=device,
                control=control,
            )
            manifest["create_argv"] = argv
            write_json(directory / "manifest.json", manifest)
            execution = _execute_reference(argv, name, directory, control, max_seconds)
            result.update(
                execution=execution,
                cleanup_verified=execution["cleanup_verified"],
                image_id=execution.get("image_id"),
            )
            raw = read_capture(artifacts / "result.json")
            controller = read_artifact_json(artifacts / "controller-result.json", 65536)
            if (artifacts / "processes").exists() and any((artifacts / "processes").iterdir()):
                raise ValueError("Reference requires a single captured Python child")
            result.update(raw)
            # Host-owned metadata cannot be replaced by a target capture.
            result.update(
                run_id=run_id,
                run_dir=str(directory),
                cleanup_verified=execution["cleanup_verified"],
                image_id=execution.get("image_id"),
                controller=controller,
                execution=execution,
            )
            state = execution.get("state") or {}
            code = controller.get("returncode")
            valid_exit = (
                (
                    raw["status"] == "completed"
                    and (code == 0 or (code == 1 and raw.get("termination_reason") == "step_limit"))
                )
                or (raw["status"] == "oom" and code in {1, 42})
                or (raw["status"] == "timeout" and code in {1, 124})
            )
            matching_child = (
                controller.get("protocol") == "headroom.subprocess-controller.v1"
                and controller.get("child_pid") == raw.get("pid")
                and controller.get("controller_does_not_capture") is True
                and controller.get("deadline", {}).get("clock_verified") is True
            )
            if (
                execution.get("timed_out")
                or controller.get("timed_out")
                or raw["status"] == "timeout"
            ):
                result.update(status="timeout", reason="TIMEOUT")
            elif (
                execution.get("error")
                or not valid_exit
                or not matching_child
                or controller.get("group_cleanup_verified") is not True
                or state.get("Running") is not False
                or state.get("OOMKilled") is not False
                or state.get("ExitCode") != 0
                or raw.get("capture_complete") is not True
            ):
                result.update(status="error", reason="REFERENCE_CAPTURE_OR_EXIT_MISMATCH")
            else:
                result["reason"] = None
            after = gpu_state() if device == "cuda" else {"queried": False, "processes": []}
            result["gpu_after"] = after
            result.update(merge_gpu_observations(device, before, after, raw.get("shared_gpu")))
            result["gpu_clear_before_after"] = device == "cpu" or (
                before.get("available") is True
                and after.get("available") is True
                and not before["processes"]
                and not after["processes"]
            )
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(
            status="error",
            reason="REFERENCE_EXECUTION_UNAVAILABLE",
            error_type=type(error).__name__,
        )
        if result.get("execution", {}).get("timed_out"):
            result.update(status="timeout", reason="TIMEOUT")
    finally:
        if result.get("cleanup_verified") is not True:
            result.update(status="error", reason="REFERENCE_CLEANUP_UNVERIFIED")
        manifest["image_id"] = result.get("image_id")
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        write_json(directory / "manifest.json", manifest)
        write_json(directory / "result.json", result)
    return result


def compare_pair(
    production,
    reference,
    *,
    expected_status,
    max_steps,
    device,
    expected_script_sha256=None,
    script_relative="train.py",
):
    """Preserve raw status/peaks; CPU parity is never the CUDA T2.7 acceptance."""
    left = read_artifact_json(Path(production["run_dir"]) / "manifest.json")
    right = read_artifact_json(Path(reference["run_dir"]) / "manifest.json")
    left_files = left.get("source", {}).get("files")
    right_files = right.get("source", {}).get("files")

    def valid_files(files):
        return (
            isinstance(files, dict)
            and bool(files)
            and all(
                isinstance(name, str)
                and isinstance(value, dict)
                and isinstance(value.get("sha256"), str)
                and re.fullmatch(r"[a-f0-9]{64}", value["sha256"])
                and type(value.get("bytes")) is int
                and value["bytes"] >= 0
                for name, value in files.items()
            )
        )

    valid_sources = valid_files(left_files) and valid_files(right_files)
    pinned = (
        valid_sources
        and isinstance(expected_script_sha256, str)
        and re.fullmatch(r"[a-f0-9]{64}", expected_script_sha256) is not None
        and left_files.get(script_relative, {}).get("sha256") == expected_script_sha256
        and right_files.get(script_relative, {}).get("sha256") == expected_script_sha256
    )
    capture_keys = (
        "python",
        "torch",
        "cuda",
        "device",
        "seed",
        "max_steps",
        "max_seconds",
        "PYTORCH_CUDA_ALLOC_CONF",
        "CUDA_VISIBLE_DEVICES",
        "seeded",
        "deterministic_algorithms",
        "CUBLAS_WORKSPACE_CONFIG",
    )
    checks = {
        "same_capture_configuration": all(
            key in production.get("env", {})
            and key in reference.get("env", {})
            and production["env"][key] == reference["env"][key]
            for key in capture_keys
        ),
        "same_source_hashes": bool(valid_sources and left_files == right_files),
        "original_script_pin": device == "cpu" or bool(pinned),
        "gpu_observations_complete": device == "cpu"
        or (
            production.get("gpu_observation_complete") is True
            and reference.get("gpu_observation_complete") is True
        ),
        "no_observed_gpu_sharing": device == "cpu"
        or (
            production.get("shared_gpu") is False
            and reference.get("shared_gpu") is False
            and reference.get("gpu_clear_before_after") is True
        ),
        "same_image": bool(production.get("image_id"))
        and production.get("image_id") == reference.get("image_id"),
        "same_status": production.get("status") == reference.get("status") == expected_status,
        "both_complete_captures": production.get("capture_complete") is True
        and reference.get("capture_complete") is True,
        "both_cleanup_verified": production.get("cleanup_verified") is True
        and reference.get("cleanup_verified") is True,
        "same_steps": production.get("steps") == reference.get("steps"),
        "completion_limit": expected_status != "completed"
        or (production.get("steps") == reference.get("steps") == max_steps),
        "same_loss_series": production.get("loss_series") == reference.get("loss_series"),
        "same_parameter_count": production.get("parameter_count")
        == reference.get("parameter_count")
        and production.get("parameter_count_complete") is True
        and reference.get("parameter_count_complete") is True,
    }
    a, b = production.get("peak_allocated_bytes"), reference.get("peak_allocated_bytes")
    delta = None
    if device == "cuda" and all(type(n) is int and n > 0 for n in (a, b)):
        delta = Decimal(abs(a - b)) * 100 / Decimal(a)
    checks["cuda_peak_delta_le_1_pct"] = delta is not None and delta <= 1
    return {
        "device": device,
        "expected_status": expected_status,
        "production_run_dir": production["run_dir"],
        "reference_run_dir": reference["run_dir"],
        "peak_allocated_bytes_production": a,
        "peak_allocated_bytes_reference": b,
        "peak_delta_pct": str(delta) if delta is not None else None,
        "checks": checks,
        "gpu_observation": {
            "production_complete": production.get("gpu_observation_complete"),
            "production_shared": production.get("shared_gpu"),
            "reference_complete": reference.get("gpu_observation_complete"),
            "reference_shared": reference.get("shared_gpu"),
            "reference_clear_before_after": reference.get("gpu_clear_before_after"),
            "note": "Point samples do not prove continuous GPU exclusivity; no throughput acceptance is claimed.",
        },
        "component_parity_pass": all(
            value for key, value in checks.items() if key != "cuda_peak_delta_le_1_pct"
        ),
        "t2_7_case_accepted": device == "cuda" and all(checks.values()),
        "cost_usd": "0",
        "model_api_calls": 0,
    }


def plan_cases(device="cuda"):
    if device != "cuda":
        raise ValueError("CLI acceptance plans are CUDA only; CPU fixtures are separate tests")
    cases = []
    for name, (relative, args, expected, expected_sha) in GPU_CASES.items():
        script = PROJECT_ROOT / relative
        actual_sha = hashlib.sha256(script.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise ValueError("Original T2.7 scenario source pin changed")
        cases.append(
            {
                "id": name,
                "script": relative,
                "script_args": args,
                "expected_status": expected,
                "source_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema": "headroom.t2.7-plan.v1",
        "cases": cases,
        "max_steps": 20,
        "seed": 1337,
        "device": "cuda",
        "peak_delta_pct_limit": 1,
        "model_api_calls": 0,
        "cost_usd": "0",
        "reference_scope": "independent subprocess enclosed by Docker; not a bare-host backend",
    }


def run_acceptance(output: Path, *, max_seconds=180):
    if (
        type(max_seconds) not in {int, float}
        or not math.isfinite(max_seconds)
        or not 0 < max_seconds <= 180
    ):
        raise ValueError("Per-arm execution limit must be in (0, 180]")
    plan = plan_cases()
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "plan": plan,
        "rows": [],
        "accepted": False,
        "started_at": datetime.now(UTC).isoformat(),
        "max_seconds_per_arm": max_seconds,
    }
    write_json(output / "report.json", report)
    try:
        for case in plan["cases"]:
            script = PROJECT_ROOT / case["script"]
            if hashlib.sha256(script.read_bytes()).hexdigest() != case["source_sha256"]:
                raise ValueError("Source changed after acceptance planning")
            first = run_script(
                script,
                script_args=case["script_args"],
                run_root=output / "production",
                device="cuda",
                max_steps=20,
                max_seconds=max_seconds,
                seed=1337,
            )
            if not first.get("cleanup_verified"):
                raise RuntimeError("Production cleanup unverified; no further targets may start")
            second = run_subprocess_reference(
                script,
                script_args=case["script_args"],
                run_root=output / "reference",
                device="cuda",
                max_steps=20,
                max_seconds=max_seconds,
                seed=1337,
            )
            row = compare_pair(
                first,
                second,
                expected_status=case["expected_status"],
                max_steps=20,
                device="cuda",
                expected_script_sha256=case["source_sha256"],
                script_relative=script.name,
            )
            report["rows"].append({"case_id": case["id"], **row})
            write_json(output / "report.json", report)
            if not second.get("cleanup_verified"):
                raise RuntimeError("Reference cleanup unverified; no further targets may start")
        report["accepted"] = len(report["rows"]) == 3 and all(
            row["t2_7_case_accepted"] for row in report["rows"]
        )
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        write_json(output / "report.json", report)
    return report
