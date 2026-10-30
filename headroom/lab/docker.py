"""Docker process management; target code never executes on the host."""

import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import time
from pathlib import Path

from headroom.lab import artifact_volume
from headroom.lab.cache import validated_hf_cache
from headroom.lab.deadline import NANOSECONDS, publish_deadline
from headroom.lab.envs import HOST_ENV
from headroom.lab.runtime_image import (
    IMAGE,  # noqa: F401 - compatibility export for callers
    require_runtime_image,
)
from headroom.lab.storage_budget import storage_admission

LOG_LIMIT = 8 * 1024 * 1024


def docker_binary() -> str:
    executable = shutil.which("docker", path=HOST_ENV["PATH"])
    if not executable:
        raise RuntimeError("Docker is required; host execution is not a fallback")
    return executable


def create_arguments(
    *,
    name: str,
    project_root: Path,
    source: Path,
    output: Path,
    environment: dict,
    command: list[str],
    device: str,
    control: Path | None = None,
    reference_scratch_socket: Path | None = None,
) -> list[str]:
    runtime = require_runtime_image(project_root, executable=docker_binary(), environment=HOST_ENV)
    args = [
        docker_binary(),
        "create",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "32g",
        "--cpus",
        "8",
        "--pids-limit",
        "256",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=1g",
        "--workdir",
        "/source",
        "--log-driver",
        "none",
        "--entrypoint",
        command[0],
    ]
    if device == "cuda":
        args.extend(["--gpus", "device=0"])
    for host, destination, readonly in (
        (project_root / "headroom", "/runtime/headroom", True),
        (source, "/source", True),
    ):
        if not host.is_dir():
            raise ValueError(f"required mount does not exist: {host}")
        mount = f"type=bind,source={host},destination={destination}"
        if readonly:
            mount += ",readonly"
        if "," in str(host) or "\n" in str(host):
            raise ValueError("mount paths cannot contain commas or newlines")
        args.extend(["--mount", mount])
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Artifact output must be a regular directory")
    volume = artifact_volume.names(name)["volume"]
    args.extend(["--mount", f"type=volume,source={volume},destination=/out"])
    if control is not None:
        if control.is_symlink() or not control.is_dir():
            raise ValueError("Deadline control must be a regular directory")
        if "," in str(control) or "\n" in str(control):
            raise ValueError("Deadline control mount path is invalid")
        args.extend(["--mount", f"type=bind,source={control},destination=/control,readonly"])
    if reference_scratch_socket is not None:
        from headroom.lab.reference_scratch_lifecycle import SOCKET_DESTINATION

        socket_path = Path(reference_scratch_socket)
        info = socket_path.lstat()
        if (
            not socket_path.is_absolute()
            or socket_path != socket_path.resolve()
            or not stat.S_ISSOCK(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or "," in str(socket_path)
            or "\n" in str(socket_path)
        ):
            raise ValueError("Reference scratch must be an owned private Unix socket")
        args.extend(
            ["--mount", f"type=bind,source={socket_path},destination={SOCKET_DESTINATION},readonly"]
        )
    cache = validated_hf_cache(project_root)
    if cache is not None:
        if "," in str(cache) or "\n" in str(cache):
            raise ValueError("HF cache path cannot contain commas or newlines")
        args.extend(["--mount", f"type=bind,source={cache},destination=/hf-cache,readonly"])
    for key, value in sorted(environment.items()):
        args.extend(["--env", f"{key}={value}"])
    return [*args, runtime["image_id"], *command[1:]]


def inspect_container(name: str) -> dict:
    try:
        inspected = subprocess.run(
            [
                docker_binary(),
                "inspect",
                "--format",
                '{"state":{{json .State}},"image_id":{{json .Image}}}',
                name,
            ],
            env=HOST_ENV,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if inspected.returncode == 0:
            return json.loads(inspected.stdout)
        return {"inspect_error": inspected.stderr[-2000:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"inspect_error": str(error)}


def cleanup_container(name: str) -> dict:
    """Attempt every cleanup step independently, then verify actual absence."""
    executable = docker_binary()
    attempts = []
    for arguments in (["stop", "--time", "2", name], ["kill", name], ["rm", "--force", name]):
        try:
            completed = subprocess.run(
                [executable, *arguments],
                env=HOST_ENV,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            attempts.append(
                {
                    "operation": arguments[0],
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-2000:],
                }
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            attempts.append({"operation": arguments[0], "error": str(error)})
    try:
        inspected = subprocess.run(
            [executable, "inspect", "--type", "container", name],
            env=HOST_ENV,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        inspection = {
            "returncode": inspected.returncode,
            "stdout": inspected.stdout[-2000:],
            "stderr": inspected.stderr[-2000:],
        }
        message = inspected.stderr.casefold()
        absent = (
            inspected.returncode != 0
            and any(marker in message for marker in ("no such object:", "no such container:"))
            and name.casefold() in message
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        absent = False
        inspection = {"error": str(error)}
    return {"cleanup_verified": absent, "cleanup_attempts": attempts, "cleanup_inspect": inspection}


def _owned_target(name, target_id, store, create_args):
    """Read immutable identity and mounts before removing a target we created."""
    details = artifact_volume._inspect("container", target_id)
    if details is None:
        return None
    source = None
    scratch_source = None
    from headroom.lab.reference_scratch_lifecycle import SOCKET_DESTINATION

    for index, argument in enumerate(create_args[:-1]):
        if argument == "--mount":
            fields = dict(
                part.split("=", 1) for part in create_args[index + 1].split(",") if "=" in part
            )
            if fields.get("destination") == "/source":
                source = fields.get("source")
            if fields.get("destination") == SOCKET_DESTINATION:
                scratch_source = fields.get("source")
    mounts = {entry.get("Destination"): entry for entry in details.get("Mounts", [])}
    if not (
        source is not None
        and details.get("Id") == target_id
        and details.get("Name") == "/" + name
        and details.get("Image") == store["image_id"]
        and mounts.get("/source", {}).get("Source") == source
        and mounts.get("/source", {}).get("RW") is False
        and mounts.get("/out", {}).get("Type") == "volume"
        and mounts.get("/out", {}).get("Name") == store["volume"]
        and mounts.get("/out", {}).get("RW") is True
        and (
            SOCKET_DESTINATION not in mounts
            if scratch_source is None
            else (
                mounts.get(SOCKET_DESTINATION, {}).get("Type") == "bind"
                and mounts.get(SOCKET_DESTINATION, {}).get("Source") == scratch_source
                and mounts.get(SOCKET_DESTINATION, {}).get("RW") is False
            )
        )
    ):
        raise ValueError("Target ownership changed; automatic cleanup refused")
    return details


def execute(
    *,
    create_args: list[str],
    name: str,
    run_dir: Path,
    max_seconds: float,
    control_dir: Path | None = None,
) -> dict:
    """Bound execution and log size, then remove the entire container process tree."""
    result = {"timed_out": False, "returncode": None}
    process = None
    store = None
    target_id = None
    output = run_dir / "artifacts"
    try:
        runtime = require_runtime_image(
            Path(__file__).resolve().parents[2], executable=docker_binary(), environment=HOST_ENV
        )
        if runtime["image_id"] not in create_args:
            raise ValueError("Target arguments do not use the verified runtime image")
        try:
            store = artifact_volume.create_store(name, runtime["image_id"], output_path=output)
        except artifact_volume.ArtifactStoreError as error:
            store = error.metadata
            raise
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["owned_artifact_store"] = store
        temporary = run_dir / "manifest.artifact-store.tmp"
        temporary.write_text(json.dumps(manifest, allow_nan=False) + "\n")
        temporary.replace(manifest_path)
        result["artifact_quota_bytes"] = store["max_bytes"]
        result["artifact_quota_inodes"] = store["max_inodes"]
        created = subprocess.run(
            create_args, env=HOST_ENV, capture_output=True, text=True, timeout=30, check=False
        )
        (run_dir / "docker-create.log").write_text(created.stderr[-10000:])
        if created.returncode != 0:
            result.update(error="CONTAINER_CREATE_FAILED", returncode=created.returncode)
            return result
        created_id = created.stdout.strip()
        if re.fullmatch(r"[0-9a-f]{64}", created_id) is None:
            raise ValueError("Created target identity is unavailable")
        target_id = created_id
        _owned_target(name, target_id, store, create_args)
        manifest["owned_target_id"] = target_id
        temporary.write_text(json.dumps(manifest, allow_nan=False) + "\n")
        temporary.replace(manifest_path)
        if control_dir is not None:
            control = publish_deadline(control_dir, max_seconds)
            result["deadline_control"] = control
            deadline_ns = control["hard_deadline_monotonic_ns"]
        else:
            deadline_ns = time.monotonic_ns() + int(max_seconds * NANOSECONDS)
        process = subprocess.Popen(
            [docker_binary(), "start", "--attach", target_id],
            env=HOST_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        saved = {"stdout": 0, "stderr": 0}
        with (
            selectors.DefaultSelector() as selector,
            (run_dir / "stdout.log").open("wb") as stdout,
            (run_dir / "stderr.log").open("wb") as stderr,
        ):
            streams = {"stdout": stdout, "stderr": stderr}
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                if time.monotonic_ns() >= deadline_ns:
                    result["timed_out"] = True
                    process.kill()
                    break
                for key, _ in selector.select(
                    timeout=min(0.2, max(0, (deadline_ns - time.monotonic_ns()) / NANOSECONDS))
                ):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    remaining = max(0, LOG_LIMIT - saved[key.data])
                    streams[key.data].write(data[:remaining])
                    saved[key.data] += min(len(data), remaining)
            result["returncode"] = process.wait(timeout=5)
            result["log_limit_bytes_per_stream"] = LOG_LIMIT
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["error"] = f"CONTAINER_EXECUTION_FAILED: {type(error).__name__}"
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        try:
            if target_id is not None:
                details = _owned_target(name, target_id, store, create_args)
                if details is not None:
                    result.update(state=details.get("State", {}), image_id=details.get("Image"))
                    target_cleanup = cleanup_container(target_id)
                else:
                    target_cleanup = {"cleanup_verified": True}
            else:
                # A rejected pre-existing target was never ours to stop/remove.
                target_cleanup = {
                    "cleanup_verified": artifact_volume._inspect("container", name) is None
                }
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            target_cleanup = {"cleanup_verified": False, "reason": "target_ownership_unverified"}
        result.update(target_cleanup)
        if store is not None:
            if target_cleanup.get("cleanup_verified"):
                try:
                    with storage_admission(run_dir.parent):
                        result["artifact_export"] = artifact_volume.export_store(store, output)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                    result["artifact_export"] = {
                        "export_verified": False,
                        "error": type(error).__name__,
                    }
                    result["error"] = "ARTIFACT_EXPORT_FAILED"
            else:
                result["artifact_export"] = {
                    "export_verified": False,
                    "reason": "target_cleanup_unverified",
                }
            artifact_cleanup = artifact_volume.cleanup_store(store)
            result["artifact_cleanup"] = artifact_cleanup
            result["cleanup_verified"] = bool(
                target_cleanup.get("cleanup_verified") and artifact_cleanup.get("cleanup_verified")
            )
        elif "error" in result:
            # Creation may have been interrupted before its metadata was returned.
            # Recovery must check the deterministic, labelled store before declaring cleanup.
            try:
                recovered = artifact_volume.discover_store(name, output_path=output)
                if recovered is not None:
                    result["artifact_cleanup"] = artifact_volume.cleanup_store(recovered)
                    result["cleanup_verified"] = bool(
                        target_cleanup.get("cleanup_verified")
                        and result["artifact_cleanup"].get("cleanup_verified")
                    )
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                result["cleanup_verified"] = False
    return result
