"""Host-side Lab scheduling, source preparation, and bounded JSON result ingestion."""

import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

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


def read_capture(path: Path) -> dict:
    """Validate the hook protocol, without treating target-written JSON as authenticated."""
    result = read_artifact_json(path)
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
    root = Path(run_root).resolve() if run_root is not None else PROJECT_ROOT / "runs"
    root.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    directory = root / run_id
    directory.mkdir(mode=0o700)
    artifacts = directory / "artifacts"
    artifacts.mkdir()
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
                )
                execution = docker.execute(
                    create_args=args, name=name, run_dir=directory, max_seconds=max_seconds
                )
                try:
                    capture = read_capture(artifacts / "result.json")
                except (OSError, ValueError, RecursionError) as error:
                    capture = {
                        "status": "error",
                        "reason": "CAPTURE_RESULT_MISSING_OR_INVALID",
                        "capture_error": str(error),
                    }
                captured_shared = capture.get("shared_gpu")
                result = {
                    **capture,
                    **metadata,
                    "execution": execution,
                    "cleanup_verified": execution["cleanup_verified"],
                    "gpu_before": before,
                }
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
                if execution["timed_out"] or capture.get("status") == "timeout":
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
    source_root: str | Path | None = None,
    run_root: str | Path | None = None,
    max_steps: int = 20,
    max_seconds: float = 120,
    seed: int = 1337,
    device: str = "cuda",
    allocator_conf: str | None = None,
) -> dict:
    script = Path(script).resolve(strict=True)
    source = Path(source_root).resolve(strict=True) if source_root is not None else script.parent
    if not script.is_file() or not script.is_relative_to(source):
        raise ValueError("script must be a file inside source_root")
    relative = script.relative_to(source)
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
    if script_args:
        command.extend(["--", *script_args])
    return _run(
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
