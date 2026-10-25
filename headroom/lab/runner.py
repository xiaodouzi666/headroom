"""Host-side Lab scheduling, source preparation, and bounded JSON result ingestion."""

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from headroom.execution import PYTHON_COMMANDS
from headroom.lab import docker
from headroom.lab.envs import HOST_ENV, container_environment, validate_options

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    ".cache",
    ".tools",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    "runs",
    ".ssh",
    ".aws",
    ".config",
    "secrets",
    "credentials",
}
EXCLUDED_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".sqlite", ".db", ".pickle"}
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_FILES = 5000


def _write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _excluded(name: str) -> bool:
    lower = name.lower()
    return (
        lower in EXCLUDED_DIRS
        or lower.startswith(".env")
        or lower
        in {
            "id_rsa",
            "id_ed25519",
            ".netrc",
            ".npmrc",
            "credentials.json",
            "secrets.json",
            "secrets.yaml",
            "secrets.yml",
            "token.json",
        }
        or Path(lower).suffix in EXCLUDED_SUFFIXES
    )


def copy_source(source_root: Path, destination: Path, excluded_roots: Sequence[Path] = ()) -> dict:
    """Copy bounded regular files only; no credentials, links, devices, or run recursion."""
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("source_root must be a directory")
    destination.mkdir(parents=True, exist_ok=False)
    ignored_roots = {path.resolve() for path in excluded_roots}
    manifest = {"files": {}, "skipped": [], "total_bytes": 0}
    for directory, dirs, files in os.walk(source_root, followlinks=False):
        current = Path(directory)
        retained = []
        for name in sorted(dirs):
            path = current / name
            if _excluded(name) or path.is_symlink() or path.resolve() in ignored_roots:
                manifest["skipped"].append(str(path.relative_to(source_root)))
            else:
                retained.append(name)
        dirs[:] = retained
        for name in sorted(files):
            path = current / name
            relative = path.relative_to(source_root)
            info = path.lstat()
            if _excluded(name) or not stat.S_ISREG(info.st_mode) or path.is_symlink():
                manifest["skipped"].append(str(relative))
                continue
            if not path.resolve().is_relative_to(source_root):
                raise ValueError("source file escapes source_root")
            if len(manifest["files"]) >= MAX_SOURCE_FILES:
                raise ValueError("source tree exceeds 5000 files")
            if manifest["total_bytes"] + info.st_size > MAX_SOURCE_BYTES:
                raise ValueError("source tree exceeds 256 MiB; select a narrower source root")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            size = 0
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as original, target.open("xb") as copied:
                if not stat.S_ISREG(os.fstat(original.fileno()).st_mode):
                    raise ValueError("source changed to a non-regular file")
                while chunk := original.read(1024 * 1024):
                    size += len(chunk)
                    if manifest["total_bytes"] + size > MAX_SOURCE_BYTES:
                        raise ValueError("source changed beyond copy size limit")
                    digest.update(chunk)
                    copied.write(chunk)
            target.chmod(0o555 if info.st_mode & 0o111 else 0o444)
            manifest["files"][str(relative)] = {"sha256": digest.hexdigest(), "bytes": size}
            manifest["total_bytes"] += size
    return manifest


def gpu_state() -> dict:
    executable = shutil.which("nvidia-smi", path=HOST_ENV["PATH"])
    if not executable:
        return {"available": False, "error": "nvidia-smi unavailable", "processes": []}
    try:
        processes = subprocess.run(
            [
                executable,
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            env=HOST_ENV,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        device = subprocess.run(
            [
                executable,
                "--query-gpu=index,name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            env=HOST_ENV,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        entries = []
        for line in processes.stdout.splitlines():
            if not line.strip():
                continue
            fields = [part.strip() for part in line.split(",", 2)]
            if len(fields) == 3:
                entries.append({"pid": fields[0], "name": fields[1], "used_memory_mib": fields[2]})
        return {
            "available": processes.returncode == 0 and device.returncode == 0,
            "processes": entries,
            "devices_csv": device.stdout.strip(),
            "error": (processes.stderr + device.stderr)[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "error": str(error), "processes": []}


@contextmanager
def _gpu_lock(device: str):
    if device != "cuda":
        yield
        return
    lock_path = PROJECT_ROOT / ".cache" / "headroom-gpu.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("GPU_BUSY: another Headroom GPU run holds the lock") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_artifact_json(path: str | Path, max_bytes: int = 32 * 1024 * 1024):
    """Read a bounded regular JSON leaf in a host-created artifact directory."""

    def reject_constant(value):
        raise ValueError(f"invalid JSON constant {value}")

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("artifact must be a regular JSON file within the size limit")
        data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("artifact exceeds size limit")
        return json.loads(data, parse_constant=reject_constant)


def read_capture(path: Path, *, max_bytes: int = 32 * 1024 * 1024) -> dict:
    """Validate the hook protocol, without treating target-written JSON as authenticated."""
    result = read_artifact_json(path, max_bytes)
    if not isinstance(result, dict) or result.get("status") not in {
        "completed",
        "oom",
        "error",
        "timeout",
    }:
        raise ValueError("capture result has an invalid status")
    if (
        result.get("protocol") != "headroom.lab.v1"
        or not isinstance(result.get("termination_reason"), str)
        or type(result.get("steps")) is not int
        or result["steps"] < 0
        or not isinstance(result.get("loss_series"), list)
        or not isinstance(result.get("env"), dict)
    ):
        raise ValueError("capture result does not match headroom.lab.v1")
    return result


MAX_CAPTURE_OWNERS = 64
MAX_CAPTURE_RESULT_BYTES = 4 * 1024 * 1024
MAX_CAPTURE_ROSTER_BYTES = 32 * 1024 * 1024


def capture_artifact_directory(run_dir: Path, relative: str) -> Path:
    """Resolve only original capture directories, rejecting linked ancestors."""
    if not isinstance(relative, str) or not re.fullmatch(
        r"artifacts(?:/processes/[0-9]+(?:-[0-9]+)?)?", relative
    ):
        raise ValueError("INVALID_CAPTURE_RELATIVE_PATH")
    root = Path(run_dir).resolve(strict=True)
    current = root
    for component in Path(relative).parts:
        current = current / component
        info = current.lstat()
        if not stat.S_ISDIR(info.st_mode) or current.is_symlink():
            raise ValueError("CAPTURE_DIRECTORY_LINK_OR_SPECIAL")
    return current


def _read_capture_roster(run_dir: Path, manifest: dict) -> tuple[list[dict], dict]:
    from headroom.execution import command_argv, observed_python_descriptor

    relatives = ["artifacts"]
    records, errors, total_bytes = [], [], 0
    try:
        base = capture_artifact_directory(run_dir, "artifacts")
        processes = base / "processes"
        if processes.exists() or processes.is_symlink():
            info = processes.lstat()
            if not stat.S_ISDIR(info.st_mode) or processes.is_symlink():
                raise ValueError("CAPTURE_PROCESS_DIRECTORY_INVALID")
            with os.scandir(processes) as children:
                for child in children:
                    if len(relatives) >= MAX_CAPTURE_OWNERS:
                        raise ValueError("CAPTURE_OWNER_LIMIT")
                    relative = "artifacts/processes/" + child.name
                    capture_artifact_directory(run_dir, relative)
                    relatives.append(relative)
        relatives.sort()
    except (OSError, ValueError) as error:
        errors.append(str(error))
    for relative in relatives:
        row = {
            "capture_relative": relative,
            "capture": None,
            "descriptor": None,
            "invocation_complete": False,
            "error": None,
        }
        try:
            directory = capture_artifact_directory(run_dir, relative)
            path = directory / "result.json"
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CAPTURE_RESULT_BYTES:
                raise ValueError("CAPTURE_RESULT_SIZE_OR_TYPE")
            total_bytes += info.st_size
            if total_bytes > MAX_CAPTURE_ROSTER_BYTES:
                raise ValueError("CAPTURE_ROSTER_SIZE_LIMIT")
            capture = read_capture(path, max_bytes=MAX_CAPTURE_RESULT_BYTES)
            row["capture"] = capture
            if capture.get("capture_complete") is not True:
                raise ValueError("CAPTURE_INCOMPLETE")
            pid = capture.get("pid")
            if type(pid) is not int or pid < 1:
                raise ValueError("CAPTURE_PID_INVALID")
            if relative == "artifacts":
                if capture.get("is_primary") is not True:
                    raise ValueError("CAPTURE_PRIMARY_UNCONFIRMED")
            elif (
                capture.get("is_primary") is not False
                or str(pid) != Path(relative).name.split("-")[0]
            ):
                raise ValueError("CAPTURE_OWNER_MISMATCH")
            entry = capture.get("execution_entrypoint") or {}
            if not isinstance(entry, dict):
                entry = {}
            row["entry"] = entry
            if (
                isinstance(entry, dict)
                and entry.get("pid") == pid
                and isinstance(entry.get("startup_cwd"), str)
                and entry["startup_cwd"].startswith("/")
            ):
                command_argv(entry.get("orig_argv"))
                row["invocation_complete"] = True
            try:
                row["descriptor"] = observed_python_descriptor(manifest["command"], entry, manifest)
            except (ValueError, TypeError, KeyError) as error:
                row["mapping_reason"] = str(error)
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            row["error"] = str(error)
        records.append(row)
    complete = not errors and bool(records) and all(row["error"] is None for row in records)
    single = (
        complete
        and len(records) == 1
        and records[0]["descriptor"] is not None
        and records[0]["invocation_complete"]
    )
    inventory = {
        "captured_process_count": len(records),
        "single_python_entrypoint": single,
        "complete": complete,
        "invocations_complete": all(row["invocation_complete"] for row in records),
        "errors": errors,
        "records": [
            {
                "capture_relative": row["capture_relative"],
                "pid": (row["capture"] or {}).get("pid"),
                "status": (row["capture"] or {}).get("status"),
                "termination_reason": (row["capture"] or {}).get("termination_reason"),
                "source_relative": (row["descriptor"] or {}).get("source_relative"),
                "startup_cwd": row.get("entry", {}).get("startup_cwd"),
                "orig_argv": row.get("entry", {}).get("orig_argv"),
                "error": row["error"],
                "mapping_reason": row.get("mapping_reason"),
            }
            for row in records
        ],
        "basis": "instrumented capture owners; not proof of absent uninstrumented processes",
    }
    return records, inventory


def _select_capture(records: list[dict], inventory: dict, expected=None, *, script_mode=False):
    from headroom.execution import same_capture_target, same_target_invocation

    selection = {
        "status": "unavailable",
        "matching_target_count": 0,
        "selected_capture_relative": None,
        "reason": None,
    }
    selected = None
    if not inventory["complete"]:
        selection["reason"] = "CAPTURE_ROSTER_INCOMPLETE"
    elif script_mode and len(records) == 1:
        selected = records[0]
        selection["status"] = "primary_script"
    elif not inventory["invocations_complete"]:
        selection["reason"] = "CAPTURE_INVOCATION_INCOMPLETE"
    elif expected is not None:
        matches = [
            row
            for row in records
            if same_target_invocation(expected, row["capture"].get("execution_entrypoint"))
        ]
        selection["matching_target_count"] = len(matches)
        if len(matches) != 1:
            selection.update(
                status="ambiguous" if matches else "unavailable",
                reason="CAPTURE_TARGET_DUPLICATE" if matches else "CAPTURE_TARGET_MISSING",
            )
        elif not same_capture_target(expected, matches[0]["descriptor"]):
            selection["reason"] = "CAPTURE_TARGET_IDENTITY_MISMATCH"
        else:
            selected = matches[0]
            selection["status"] = "matched_replay"
    elif len(records) == 1:
        if records[0]["descriptor"] is not None:
            selected = records[0]
            selection["status"] = "single"
        else:
            selection["reason"] = (
                records[0].get("mapping_reason") or "CAPTURE_ENTRYPOINT_INCOMPLETE"
            )
    else:
        ooms = [
            row
            for row in records
            if (
                row["capture"].get("status") == "oom"
                and row["capture"].get("termination_reason") == "oom"
                and row["capture"].get("env", {}).get("device") == "cuda"
                and isinstance(row["capture"].get("oom"), dict)
            )
        ]
        if len(ooms) != 1:
            selection.update(
                status="ambiguous" if ooms else "unavailable",
                reason="MULTIPLE_CUDA_OOM_TARGETS" if ooms else "NO_UNIQUE_CUDA_OOM_TARGET",
            )
        elif ooms[0]["descriptor"] is None:
            selection["reason"] = ooms[0].get("mapping_reason") or "CAPTURE_ENTRYPOINT_INCOMPLETE"
        else:
            descriptor = ooms[0]["descriptor"]
            matches = [
                row
                for row in records
                if same_target_invocation(descriptor, row["capture"].get("execution_entrypoint"))
            ]
            selection["matching_target_count"] = len(matches)
            if len(matches) != 1:
                selection.update(status="ambiguous", reason="CAPTURE_TARGET_DUPLICATE")
            else:
                selected = ooms[0]
                selection["status"] = "unique_oom"
    if selected is not None:
        other_failures = [
            row
            for row in records
            if row is not selected and row["capture"].get("status") != "completed"
        ]
        if other_failures:
            selected = None
            selection.update(status="unavailable", reason="NON_TARGET_CAPTURE_FAILED")
        else:
            selection.update(
                matching_target_count=1, selected_capture_relative=selected["capture_relative"]
            )
    inventory["selection"] = selection
    inventory["reason"] = selection["reason"]
    return selected, inventory


def selected_capture_directory(run_dir: Path, result: dict, manifest: dict) -> Path:
    """Bind selected metrics and source metadata to the same preserved capture."""
    result_relative = result.get("selected_capture_relative")
    manifest_relative = manifest.get("selected_capture_relative")
    if result_relative is None and manifest_relative is None:
        directory = capture_artifact_directory(run_dir, "artifacts")
        processes = directory / "processes"
        if (
            (result.get("execution_capture", {}).get("captured_process_count") or 0) > 1
            or (manifest.get("execution_capture", {}).get("captured_process_count") or 0) > 1
            or processes.is_symlink()
            or (
                processes.exists()
                and (not processes.is_dir() or next(processes.iterdir(), None) is not None)
            )
        ):
            raise ValueError("CAPTURE_SELECTION_REQUIRED_FOR_MULTIPLE_OWNERS")
        return directory  # legacy evidence without child captures
    if result_relative != manifest_relative or not isinstance(result_relative, str):
        raise ValueError("CAPTURE_SELECTION_MANIFEST_MISMATCH")
    selection = result.get("execution_capture", {}).get("selection", {})
    if (
        selection != manifest.get("execution_capture", {}).get("selection", {})
        or selection.get("status")
        not in {"primary_script", "single", "unique_oom", "matched_replay"}
        or selection.get("selected_capture_relative") != result_relative
        or selection.get("matching_target_count") != 1
    ):
        raise ValueError("CAPTURE_SELECTION_UNAVAILABLE_OR_MISMATCH")
    directory = capture_artifact_directory(run_dir, result_relative)
    capture = read_capture(directory / "result.json", max_bytes=MAX_CAPTURE_RESULT_BYTES)
    # Preserve the whole target evidence contract, including precision,
    # parameter counts and pairing. Only these host-level fields may differ.
    for key, value in capture.items():
        if key not in {"status", "reason", "shared_gpu"} and result.get(key) != value:
            raise ValueError("CAPTURE_SELECTION_RESULT_MISMATCH:" + key)
    if manifest.get("execution_entrypoint") != capture.get("execution_entrypoint"):
        raise ValueError("CAPTURE_SELECTION_ENTRYPOINT_MISMATCH")
    return directory


def merge_gpu_observations(
    device: str, before: dict, after: dict, captured_shared: bool | None = None
) -> dict:
    """Combine sampling evidence; negative samples do not prove continuous exclusivity."""
    if device == "cpu":
        return {
            "shared_gpu": False,
            "gpu_observation_complete": True,
            "gpu_observation_note": "CPU execution; GPU observation not applicable",
        }
    positive = bool(before.get("processes") or after.get("processes")) or captured_shared is True
    complete = (
        before.get("available") is True
        and after.get("available") is True
        and type(captured_shared) is bool
    )
    return {
        "shared_gpu": True if positive else (False if complete else None),
        "gpu_observation_complete": complete,
        "gpu_observation_note": (
            "Host before/after samples and the capture's sharing observation are combined; "
            "these samples do not establish continuous GPU exclusivity."
        ),
    }


def _run(
    *,
    source_root: Path,
    command: list[str],
    script_relative: Path | None,
    run_root: str | Path | None,
    max_steps: int,
    max_seconds: float,
    seed: int,
    device: str,
    allocator_conf: str | None,
    target_argv_override: dict | None = None,
    capture_target: dict | None = None,
) -> dict:
    validate_options(device, max_steps, max_seconds, seed)
    environment = container_environment(
        device=device,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        allocator_conf=allocator_conf,
        command_mode=script_relative is None,
    )
    if target_argv_override is not None:
        if script_relative is not None:
            raise ValueError("Target argv override requires sitecustomize command mode")
        environment["HEADROOM_TARGET_ARGV_OVERRIDE"] = json.dumps(target_argv_override)
    root = Path(run_root).resolve() if run_root is not None else PROJECT_ROOT / "runs"
    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    directory = root / run_id
    directory.mkdir(mode=0o700)
    artifacts = directory / "artifacts"
    artifacts.mkdir()
    control = directory / "control"
    control.mkdir(mode=0o700)
    name = f"headroom-lab-{run_id}"
    metadata = {
        "run_id": run_id,
        "run_dir": str(directory),
        "artifact_dir": str(artifacts),
        "container_name": name,
        "cleanup_verified": True,
        "shared_gpu": False if device == "cpu" else None,
        "gpu_observation_complete": device == "cpu",
        "started_at": datetime.now(UTC).isoformat(),
    }
    result = {"status": "error", "reason": "PREPARATION_FAILED", **metadata}
    captured_shared = None
    try:
        source = copy_source(source_root, directory / "source", (root, directory))
        if script_relative is not None and str(script_relative) not in source["files"]:
            raise ValueError("selected script was excluded from the source copy")
        _write_json(
            directory / "manifest.json",
            {
                "source_root": str(source_root),
                "source": source,
                "command": command,
                "target_argv_override": target_argv_override,
                "expected_capture_target": capture_target,
                "environment": environment,
                "image": docker.IMAGE,
                "device": device,
                "max_steps": max_steps,
                "max_seconds": max_seconds,
                "seed": seed,
            },
        )
        with _gpu_lock(device):
            before = gpu_state() if device == "cuda" else {"queried": False, "processes": []}
            _write_json(directory / "gpu-before.json", before)
            if device == "cuda" and (not before.get("available") or before["processes"]):
                result.update(
                    reason="GPU_BUSY" if before["processes"] else "GPU_UNAVAILABLE",
                    shared_gpu=bool(before["processes"]),
                    gpu_before=before,
                )
            else:
                args = docker.create_arguments(
                    name=name,
                    project_root=PROJECT_ROOT,
                    source=directory / "source",
                    output=artifacts,
                    environment=environment,
                    command=command,
                    device=device,
                    control=control,
                )
                execution = docker.execute(
                    create_args=args,
                    name=name,
                    run_dir=directory,
                    max_seconds=max_seconds,
                    control_dir=control,
                )
                manifest = read_artifact_json(directory / "manifest.json")
                records, inventory = _read_capture_roster(directory, manifest)
                selected, inventory = _select_capture(
                    records, inventory, capture_target, script_mode=script_relative is not None
                )
                inventory["observed_timeout_captures"] = [
                    row["capture_relative"]
                    for row in records
                    if (row["capture"] or {}).get("status") == "timeout"
                    and (row["capture"] or {}).get("termination_reason") == "timeout"
                ]
                primary = next(
                    (row["capture"] for row in records if row["capture_relative"] == "artifacts"),
                    None,
                )
                capture = dict(
                    (selected or {}).get("capture")
                    or primary
                    or {
                        "status": "error",
                        "reason": "CAPTURE_RESULT_MISSING_OR_INVALID",
                    }
                )
                selected_relative = selected["capture_relative"] if selected else "artifacts"
                capture.update(
                    execution_capture=inventory,
                    selected_capture_relative=selected_relative,
                )
                manifest.update(
                    image_id=execution.get("image_id"),
                    execution_entrypoint=capture.get("execution_entrypoint"),
                    execution_capture=inventory,
                    selected_capture_relative=selected_relative,
                )
                _write_json(directory / "manifest.json", manifest)
                captured_shared = capture.get("shared_gpu")
                result = {
                    **capture,
                    **metadata,
                    "execution": execution,
                    "cleanup_verified": execution["cleanup_verified"],
                    "gpu_before": before,
                    "target_artifact_dir": str(
                        capture_artifact_directory(directory, selected_relative)
                    ),
                }
                if selected is None and (capture_target is not None or len(records) > 1):
                    result.update(status="error", reason=inventory["reason"])
                elif not inventory["complete"]:
                    result.update(status="error", reason="CAPTURE_ROSTER_INCOMPLETE")
                state = execution.get("state", {})
                actual_exit = state.get("ExitCode")
                controlled_limit = (
                    script_relative is None
                    and capture.get("termination_reason") == "step_limit"
                    and actual_exit == 1
                )
                if (
                    state.get("OOMKilled")
                    or not state
                    or state.get("Running")
                    or (
                        capture.get("status") == "completed"
                        and actual_exit != 0
                        and not controlled_limit
                    )
                    or (capture.get("status") == "oom" and actual_exit not in {1, 42})
                ):
                    result.update(status="error", reason="CAPTURE_CONTAINER_STATE_MISMATCH")
                if (
                    capture.get("status") in {"completed", "oom"}
                    and capture.get("capture_complete") is not True
                ):
                    result.update(status="error", reason="CAPTURE_INCOMPLETE")
                result["image_id"] = execution.get("image_id")
                roster_timeout = (
                    inventory["complete"]
                    and bool(inventory["observed_timeout_captures"])
                    and all(row["capture"]["status"] in {"completed", "timeout"} for row in records)
                    and actual_exit in {1, 124}
                    and state.get("OOMKilled") is False
                    and state.get("Running") is False
                    and not execution.get("error")
                )
                if execution["timed_out"] or capture.get("status") == "timeout" or roster_timeout:
                    result.update(status="timeout", reason="TIMEOUT")
                elif execution.get("error"):
                    result.update(status="error", reason=execution["error"])
                if not execution["cleanup_verified"]:
                    result.update(status="error", reason="CONTAINER_CLEANUP_UNVERIFIED")
            after = gpu_state() if device == "cuda" else {"queried": False, "processes": []}
            _write_json(directory / "gpu-after.json", after)
            result["gpu_after"] = after
            result.update(merge_gpu_observations(device, before, after, captured_shared))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(
            status="error",
            reason="GPU_BUSY" if str(error).startswith("GPU_BUSY") else "PREPARATION_FAILED",
            error=str(error),
        )
    result["finished_at"] = datetime.now(UTC).isoformat()
    _write_json(directory / "result.json", result)
    return result


def run_script(
    script: str | Path,
    *,
    script_args: Sequence[str] = (),
    execution_argv: Sequence[str] | None = None,
    execution_entrypoint: dict | None = None,
    source_root: str | Path | None = None,
    run_root: str | Path | None = None,
    max_steps: int = 20,
    max_seconds: float = 120,
    seed: int = 1337,
    device: str = "cuda",
    allocator_conf: str | None = None,
    reference_offload_bytes: int | None = None,
    reference_offload_disk_bytes: int = 0,
) -> dict:
    script_args = () if script_args is None else script_args
    script = Path(script).resolve(strict=True)
    source = Path(source_root).resolve(strict=True) if source_root is not None else script.parent
    if not script.is_file() or not script.is_relative_to(source):
        raise ValueError("script must be a file inside source_root")
    relative = script.relative_to(source)
    if reference_offload_disk_bytes and reference_offload_bytes is None:
        raise ValueError("Disk reference requires an explicit CPU staging byte budget")
    if reference_offload_bytes is not None:
        from headroom.verify.offload import validate_limit
        from headroom.verify.offload_disk import validate_disk_limit
        from headroom.verify.pairing import source_contract

        validate_limit(reference_offload_bytes)
        validate_disk_limit(reference_offload_disk_bytes)
        if execution_argv is not None or execution_entrypoint is not None:
            raise ValueError("Reference offload supports standalone run_script only")
        if not source_contract(script).get("supported"):
            raise ValueError("Reference offload requires a reviewed standalone source contract")
    if execution_entrypoint is not None and execution_argv is None:
        raise ValueError("Captured entrypoint requires the original wrapper argv")
    if execution_argv is not None:
        from headroom.execution import (
            captured_wrapper_descriptor,
            prepare_local_command,
            replay_argv,
            same_wrapper_entrypoint,
        )

        prepared = prepare_local_command(
            source, execution_argv, execution_entrypoint=execution_entrypoint
        )
        if prepared.script.resolve() != script:
            raise ValueError("Execution argv must resolve to the supplied script")
        override = None
        if execution_entrypoint is not None:
            cwd = execution_entrypoint["startup_cwd_relative"]
            override = {
                "expected_startup_cwd": "/source" if cwd == "." else f"/source/{cwd}",
                "expected_orig_argv": execution_entrypoint["python_argv"],
                "original_target_args": execution_entrypoint["script_args"],
                "effective_target_args": list(script_args),
            }
        result = run_argv(
            source,
            replay_argv(execution_argv, script_args, execution_entrypoint=execution_entrypoint),
            run_root=run_root,
            max_steps=max_steps,
            max_seconds=max_seconds,
            seed=seed,
            device=device,
            allocator_conf=allocator_conf,
            **(
                {"target_argv_override": override, "capture_target": execution_entrypoint}
                if override is not None
                else {}
            ),
        )
        if execution_entrypoint is None and result.get("selected_capture_relative") not in {
            None,
            "artifacts",
        }:
            entry = result.get("execution_entrypoint") or {}
            sent = replay_argv(execution_argv, script_args)
            original = entry.get("orig_argv") or []
            if (
                original[1:] != sent[1:]
                or entry.get("startup_cwd") != "/source"
                or entry.get("main_file") != f"/source/{relative}"
            ):
                result.update(status="error", reason="CAPTURE_TARGET_REQUIRES_WATCH_MAPPING")
                _write_json(Path(result["run_dir"]) / "result.json", result)
        if execution_entrypoint is not None:
            try:
                manifest = read_artifact_json(Path(result["run_dir"]) / "manifest.json")
                actual = captured_wrapper_descriptor(execution_argv, result, manifest)
                applied = result.get("execution_entrypoint", {}).get("argv_override", {})
                matched = (
                    same_wrapper_entrypoint(execution_entrypoint, actual)
                    and actual["effective_script_args"] == list(script_args)
                    and applied.get("matched") is True
                    and applied.get("applied") is True
                )
                reason = None if matched else "WRAPPER_REPLAY_ENTRYPOINT_MISMATCH"
            except (OSError, ValueError, TypeError, KeyError) as error:
                matched, reason = False, str(error)
            result["execution_replay"] = {"matched": matched, "reason": reason}
            if not matched:
                result.update(status="error", reason="WRAPPER_REPLAY_ENTRYPOINT_MISMATCH")
            _write_json(Path(result["run_dir"]) / "result.json", result)
        return result
    command = [
        "/opt/venv/bin/python",
        "-m",
        "headroom.lab.run_target",
        "--script",
        f"/source/{relative}",
        "--output",
        "/out",
        "--max-steps",
        str(max_steps),
        "--max-seconds",
        str(max_seconds),
        "--seed",
        str(seed),
        "--device",
        device,
    ]
    if reference_offload_bytes is not None:
        command.extend(["--reference-offload-bytes", str(reference_offload_bytes)])
    if reference_offload_disk_bytes:
        command.extend(["--reference-offload-disk-bytes", str(reference_offload_disk_bytes)])
    if script_args:
        command.extend(["--", *script_args])
    result = _run(
        source_root=source,
        command=command,
        script_relative=relative,
        run_root=run_root,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        device=device,
        allocator_conf=allocator_conf,
    )
    if reference_offload_bytes is not None:
        import hashlib

        from headroom.verify.offload import PROTOCOL, STRATEGY
        from headroom.verify.offload_disk import cleanup_spill

        if reference_offload_disk_bytes:
            if result.get("cleanup_verified") is True:
                directory = Path(
                    result.get("target_artifact_dir") or Path(result["run_dir"]) / "artifacts"
                )
                result["reference_spill_cleanup"] = cleanup_spill(directory)
            else:
                result["reference_spill_cleanup"] = {
                    "verified": False,
                    "errors": ["Container stop not verified; no host cleanup attempted"],
                }
            _write_json(
                Path(result["run_dir"]) / "reference-spill-cleanup.json",
                result["reference_spill_cleanup"],
            )
        try:
            artifact = Path(result["target_artifact_dir"]) / "reference-offload.json"
            evidence = read_artifact_json(artifact)
            if not isinstance(evidence, dict):
                raise TypeError("Offload provenance must be a JSON object")
            verified = (
                evidence.get("protocol") == PROTOCOL
                and evidence.get("mode") == STRATEGY
                and evidence.get("source_sha256") == hashlib.sha256(script.read_bytes()).hexdigest()
                and evidence.get("script_args") == list(script_args)
                and evidence.get("max_saved_bytes") == reference_offload_bytes
                and evidence.get("max_disk_bytes", 0) == reference_offload_disk_bytes
            )
            result["reference_offload"] = {**evidence, "request_verified": verified}
        except (OSError, ValueError, TypeError, KeyError) as error:
            result["reference_offload"] = {
                "request_verified": False,
                "reason": "offload provenance unavailable: " + str(error),
            }
        _write_json(Path(result["run_dir"]) / "result.json", result)
    return result


def run_command(
    source_root: str | Path,
    command: Sequence[str],
    *,
    run_root: str | Path | None = None,
    max_steps: int = 20,
    max_seconds: float = 120,
    seed: int = 1337,
    device: str = "cuda",
    allocator_conf: str | None = None,
) -> dict:
    if (
        isinstance(command, str)
        or not command
        or command[0] not in {"python", "python3", "/opt/venv/bin/python"}
    ):
        raise ValueError("command must be Python argv, not a shell string")
    source = Path(source_root).resolve(strict=True)
    return _run(
        source_root=source,
        command=["/opt/venv/bin/python", *command[1:]],
        script_relative=None,
        run_root=run_root,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        device=device,
        allocator_conf=allocator_conf,
    )


def run_argv(
    source_root: str | Path,
    command: Sequence[str],
    *,
    run_root: str | Path | None = None,
    max_steps: int = 20,
    max_seconds: float = 120,
    seed: int = 1337,
    device: str = "cuda",
    allocator_conf: str | None = None,
    target_argv_override: dict | None = None,
    capture_target: dict | None = None,
) -> dict:
    """Observe arbitrary argv inside Docker; never interpret a host shell command.

    Python descendants can opt into the existing sitecustomize capture through
    the fixed environment. Other runtimes or -E/-I/-S may emit no capture; _run
    retains their actual container state and does not fabricate allocator data.
    Only commands installed in the image/venv or copied source can execute.
    """
    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
        raise TypeError("command must be an argv sequence, not a shell string")
    if (
        not command
        or len(command) > 256
        or not command[0]
        or any(not isinstance(arg, str) or "\x00" in arg for arg in command)
        or sum(len(arg.encode("utf-8")) for arg in command) > 65536
    ):
        raise ValueError("command requires nonempty argv within 256 entries and 64 KiB")
    argv = list(command)
    if argv[0] in PYTHON_COMMANDS:
        argv[0] = "/opt/venv/bin/python"
    return _run(
        source_root=Path(source_root).resolve(strict=True),
        command=argv,
        script_relative=None,
        run_root=run_root,
        max_steps=max_steps,
        max_seconds=max_seconds,
        seed=seed,
        device=device,
        allocator_conf=allocator_conf,
        target_argv_override=target_argv_override,
        capture_target=capture_target,
    )
