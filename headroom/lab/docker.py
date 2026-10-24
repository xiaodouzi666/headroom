"""Docker process management; target code never executes on the host."""

import json
import os
import selectors
import shutil
import subprocess
import time
from pathlib import Path

from headroom.lab.cache import validated_hf_cache
from headroom.lab.envs import HOST_ENV

IMAGE = "headroom-lab:py312-cu124"
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
) -> list[str]:
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
        (project_root / ".venv", "/opt/venv", True),
        (project_root / "headroom", "/runtime/headroom", True),
        (source, "/source", True),
        (output, "/out", False),
    ):
        if not host.is_dir():
            raise ValueError(f"required mount does not exist: {host}")
        mount = f"type=bind,source={host},destination={destination}"
        if readonly:
            mount += ",readonly"
        if "," in str(host) or "\n" in str(host):
            raise ValueError("mount paths cannot contain commas or newlines")
        args.extend(["--mount", mount])
    cache = validated_hf_cache(project_root)
    if cache is not None:
        if "," in str(cache) or "\n" in str(cache):
            raise ValueError("HF cache path cannot contain commas or newlines")
        args.extend(["--mount", f"type=bind,source={cache},destination=/hf-cache,readonly"])
    for key, value in sorted(environment.items()):
        args.extend(["--env", f"{key}={value}"])
    return [*args, IMAGE, *command[1:]]


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


def execute(*, create_args: list[str], name: str, run_dir: Path, max_seconds: float) -> dict:
    """Bound execution and log size, then remove the entire container process tree."""
    result = {"timed_out": False, "returncode": None}
    process = None
    try:
        created = subprocess.run(
            create_args, env=HOST_ENV, capture_output=True, text=True, timeout=30, check=False
        )
        (run_dir / "docker-create.log").write_text(created.stderr[-10000:])
        if created.returncode != 0:
            result.update(error="CONTAINER_CREATE_FAILED", returncode=created.returncode)
            return result
        process = subprocess.Popen(
            [docker_binary(), "start", "--attach", name],
            env=HOST_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        deadline = time.monotonic() + max_seconds
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
                if time.monotonic() >= deadline:
                    result["timed_out"] = True
                    process.kill()
                    break
                for key, _ in selector.select(
                    timeout=min(0.2, max(0, deadline - time.monotonic()))
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
    except (OSError, subprocess.SubprocessError) as error:
        result["error"] = f"CONTAINER_EXECUTION_FAILED: {error}"
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
        result.update(inspect_container(name))
        result.update(cleanup_container(name))
    return result
