"""Bounded argv Watch, always using the isolated Docker Lab."""

import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from pathlib import Path

from headroom.execution import prepare_captured_command
from headroom.lab.envs import validate_options
from headroom.lab.runner import PROJECT_ROOT, read_artifact_json, run_argv
from headroom.orchestrator import FixRequest, run_fix
from headroom.repository import parse_watch_command, prepare_local_command

FIX_OPTIONS = {
    "target",
    "policy",
    "budget_usd",
    "daily_budget_usd",
    "runtime_profile",
    "max_rounds",
    "source_profile",
    "research_enabled",
    "allocator_conf",
}


def _command(command, source_root):
    parsed = parse_watch_command(command)
    source = Path(source_root).resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Watch source_root must be a directory")
    if parsed.repair_supported:
        try:
            prepared = prepare_local_command(source, command)
        except ValueError:
            parsed = replace(
                parsed, repair_supported=False, repair_reason="REPAIR_SOURCE_UNAVAILABLE_OR_LINKED"
            )
        else:
            parsed = replace(parsed, script=str(prepared.script.relative_to(source)))
    return source, parsed


def _cuda_oom(result, device):
    state = result.get("execution", {}).get("state", {})
    return (
        device == "cuda"
        and result.get("protocol") == "headroom.lab.v1"
        and result.get("status") == "oom"
        and result.get("termination_reason") == "oom"
        and result.get("capture_complete") is True
        and result.get("cleanup_verified") is True
        and isinstance(result.get("oom"), dict)
        and result.get("env", {}).get("device") == "cuda"
        and state.get("ExitCode") in {1, 42}
        and state.get("OOMKilled") is False
        and state.get("Running") is False
    )


def _exit_code(result):
    execution = result.get("execution", {})
    if execution.get("timed_out") or result.get("status") == "timeout":
        return 124
    code = execution.get("state", {}).get("ExitCode")
    return code if type(code) is int and 0 <= code <= 255 else 125


def watch_command(
    command: Sequence[str],
    *,
    source_root: str | Path,
    run_root: str | Path | None = None,
    device: str = "cuda",
    max_steps: int = 20,
    max_seconds: int = 120,
    seed: int = 1337,
    fix_options: Mapping | None = None,
    lab_runner=None,
    fix_runner=None,
) -> dict:
    """Observe once; invoke run_fix only after captured CUDA OOM and verified cleanup.

    lab_runner/fix_runner are trusted in-process test seams, never HTTP inputs.
    Non-OOM exit codes are the original command's Docker exit code, including
    nonzero SystemExit. Logs and reports are retained, not rewritten as success.
    """
    validate_options(device, max_steps, max_seconds, seed)
    source, parsed = _command(command, source_root)
    relative, arguments = parsed.script, parsed.script_args
    options = dict(fix_options or {})
    if set(options) - FIX_OPTIONS:
        raise ValueError("Unsupported Watch fix option")
    # Validate the complete request before spending time on the baseline; no API calls.
    request = FixRequest(
        script=str(source / relative) if parsed.repair_supported else str(source / "train.py"),
        source_root=str(source),
        script_args=list(arguments) if parsed.repair_supported else [],
        execution_argv=list(parsed.argv) if parsed.repair_supported else None,
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        **options,
    )
    directory = Path(run_root or PROJECT_ROOT / "runs/watch").resolve() / uuid.uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    lab_root = directory / "lab"
    result = (lab_runner or run_argv)(
        source,
        list(command),
        run_root=lab_root,
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        allocator_conf=request.allocator_conf,
    )
    exit_code = _exit_code(result)
    outcome = {
        "watch_id": directory.name,
        "run_dir": str(directory),
        "command": list(command),
        "command_details": asdict(parsed),
        "repair_supported": parsed.repair_supported,
        "repair_unavailable_reason": parsed.repair_reason,
        "capture_status": "complete" if result.get("capture_complete") is True else "unknown",
        "cuda_oom_confirmed": _cuda_oom(result, device),
        "watch_report_path": str(directory / "watch.md"),
        "status": "passthrough",
        "exit_code": exit_code,
        "original_exit_code": exit_code,
        "triggered": False,
        "lab": result,
        "fix": None,
        "report_path": None,
        "stdout_path": None,
        "stderr_path": None,
    }
    lab_directory = Path(result.get("run_dir", ""))
    valid_directory = (
        lab_directory.is_dir()
        and not lab_directory.is_symlink()
        and lab_directory.resolve().parent == lab_root.resolve()
    )
    if valid_directory:
        outcome.update(
            stdout_path=str(lab_directory / "stdout.log"),
            stderr_path=str(lab_directory / "stderr.log"),
        )
    wrapper = None
    inventory = result.get("execution_capture", {})
    has_multiple = (inventory.get("captured_process_count") or 0) > 1
    if (parsed.kind == "command" or has_multiple) and valid_directory:
        try:
            wrapper = prepare_captured_command(
                lab_directory / "source",
                command,
                result,
                read_artifact_json(lab_directory / "manifest.json"),
            )
        except (OSError, ValueError, TypeError, KeyError) as error:
            parsed = replace(parsed, repair_supported=False, repair_reason=str(error))
        else:
            parsed = replace(
                parsed,
                kind="captured_wrapper",
                script=str(wrapper.script.relative_to(wrapper.source_root)),
                script_args=wrapper.script_args,
                repair_supported=True,
                repair_reason=None,
            )
        outcome.update(
            command_details=asdict(parsed),
            repair_supported=parsed.repair_supported,
            repair_unavailable_reason=parsed.repair_reason,
            execution_entrypoint=wrapper.execution_entrypoint if wrapper else None,
        )
    if result.get("cleanup_verified") is not True:
        outcome.update(status="needs_human", exit_code=125, reason="CLEANUP_UNVERIFIED")
    elif _cuda_oom(result, device):
        # Replay exactly the source copy that failed, never a concurrently edited original.
        snapshot = lab_directory / "source"
        if not parsed.repair_supported:
            outcome.update(status="needs_human", reason=parsed.repair_reason)
        elif not valid_directory:
            outcome.update(status="needs_human", reason="CAPTURE_SOURCE_UNAVAILABLE")
        else:
            if wrapper is not None:
                request = request.model_copy(
                    update={
                        "script": str(wrapper.script),
                        "source_root": str(wrapper.source_root),
                        "script_args": list(wrapper.script_args),
                        "execution_argv": list(wrapper.execution_argv),
                        "execution_entrypoint": wrapper.execution_entrypoint,
                    }
                )
            else:
                _, snapshot_command = _command(list(command), snapshot)
                if not snapshot_command.repair_supported:
                    outcome.update(status="needs_human", reason="CAPTURE_SOURCE_UNAVAILABLE")
                    return _save_outcome(directory, outcome)
                request = request.model_copy(
                    update={
                        "script": str(snapshot / snapshot_command.script),
                        "source_root": str(snapshot),
                    }
                )
            outcome["triggered"] = True
            try:
                repaired = (fix_runner or run_fix)(request, run_root=directory / "fix")
            except Exception as error:  # noqa: BLE001 - persist safe partial Watch outcome
                outcome.update(
                    status="failed", reason="FIX_FAILED", error_type=type(error).__name__
                )
            else:
                outcome.update(
                    fix=repaired,
                    status=repaired.get("status", "failed"),
                    report_path=repaired.get("report_md"),
                )
                if repaired.get("status") == "completed" and repaired.get("target_met") is True:
                    outcome["exit_code"] = 0
    elif result.get("status") == "timeout":
        outcome["status"] = "timeout"
    elif result.get("termination_reason") == "step_limit":
        outcome["status"] = "capture_limit"
    elif result.get("reason"):
        outcome["reason"] = result["reason"]
    if outcome["status"] == "passthrough" and outcome["capture_status"] == "unknown":
        outcome.update(status="needs_human", reason=result.get("reason") or "CAPTURE_UNAVAILABLE")
    return _save_outcome(directory, outcome)


def _save_outcome(directory, outcome):
    result = outcome["lab"]
    exit_code = outcome["original_exit_code"]
    (directory / "watch.json").write_text(json.dumps(outcome, indent=2, allow_nan=False) + "\n")
    (directory / "watch.md").write_text(
        "# Headroom Watch\n\n"
        f"Status: {outcome['status']}\n\nReason: {outcome.get('reason', 'none')}.\n\n"
        f"Original exit: {exit_code}; Watch exit: "
        f"{outcome['exit_code']}. Repair triggered: {outcome['triggered']}.\n\n"
        f"Capture: {outcome['capture_status']}. Repair supported: {outcome['repair_supported']}.\n\n"
        f"Lab status: {result.get('status', 'unknown')}. Cleanup verified: "
        f"{result.get('cleanup_verified') is True}.\n\n"
        + (
            f"Repair report: {outcome['report_path']}\n"
            if outcome["report_path"]
            else "No completed repair is claimed. See watch.json and the preserved Lab logs.\n"
        )
    )
    outcome["watch_report_path"] = str(directory / "watch.md")
    return outcome
