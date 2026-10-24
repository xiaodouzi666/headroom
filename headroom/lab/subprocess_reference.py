"""Independent subprocess supervisor, invoked only inside the Lab boundary container.

This controller never imports torch or production Lab scheduling. Only the child
gets sitecustomize capture. Docker is the outer isolation envelope, not the child
execution/controller implementation under test.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

from headroom.lab.deadline import NANOSECONDS, capture_window
from headroom.lab.envs import container_environment, validate_options

LOG_LIMIT = 8 * 1024 * 1024


class ControllerInterrupted(BaseException):
    pass


def read_json(path: Path, limit: int = 65536) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError("Reference control is not a bounded regular file")
        document = json.loads(handle.read(limit + 1))
    if not isinstance(document, dict):
        raise TypeError("Reference control must be an object")
    return document


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
    temporary.replace(path)


def validate_request(request: dict) -> dict:
    fields = {
        "schema",
        "script",
        "script_args",
        "device",
        "max_steps",
        "max_seconds",
        "seed",
        "allocator_conf",
    }
    if set(request) != fields or request.get("schema") != "headroom.subprocess-reference.v1":
        raise ValueError("Invalid reference request fields")
    script = request["script"]
    if (
        not isinstance(script, str)
        or not script
        or script.startswith("/")
        or any(p in {"", ".", ".."} or p.lower().startswith(".env") for p in script.split("/"))
        or not script.endswith(".py")
    ):
        raise ValueError("Reference script must be a relative Python source")
    args = request["script_args"]
    if (
        not isinstance(args, list)
        or len(args) > 128
        or any(not isinstance(a, str) or "\0" in a for a in args)
    ):
        raise ValueError("Invalid reference script arguments")
    if len(json.dumps(request).encode()) > 32768:
        raise ValueError("Reference request too large")
    if type(request["max_steps"]) is not int or type(request["seed"]) is not int:
        raise ValueError("Reference steps and seed must be integers")
    if type(request["max_seconds"]) not in (int, float) or not math.isfinite(
        request["max_seconds"]
    ):
        raise ValueError("Reference duration must be finite numeric seconds")
    validate_options(
        request["device"], request["max_steps"], request["max_seconds"], request["seed"]
    )
    environment = container_environment(
        device=request["device"],
        max_steps=request["max_steps"],
        max_seconds=request["max_seconds"],
        seed=request["seed"],
        allocator_conf=request["allocator_conf"],
        command_mode=True,
    )
    return environment


def require_boundary() -> None:
    if not Path("/.dockerenv").is_file():
        raise ValueError("Reference controller requires its Docker isolation envelope")
    mounts = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        if len(fields) > 6:
            mounts[fields[4]] = fields[5].split(",")
    for path in ("/", "/source", "/runtime/headroom", "/control"):
        if "ro" not in mounts.get(path, []):
            raise ValueError("Reference read-only boundary is missing")
    if "rw" not in mounts.get("/out", []):
        raise ValueError("Reference output boundary is missing")


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def _kill_group(pgid: int, which: int) -> None:
    try:
        os.killpg(pgid, which)
    except ProcessLookupError:
        pass


def _reap_orphans() -> None:
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid <= 0:
            break


def supervise(request: dict) -> dict:
    """Run one source-backed child; no command strings or host fallback."""
    require_boundary()
    environment = validate_request(request)
    script = Path("/source") / request["script"]
    if (
        script.is_symlink()
        or not script.is_file()
        or not script.resolve().is_relative_to("/source")
    ):
        raise ValueError("Reference source is missing or linked")
    _, deadline = capture_window(Path("/control"), request["max_seconds"])
    hard = deadline["hard_deadline_monotonic_ns"]
    result = {
        "protocol": "headroom.subprocess-controller.v1",
        "pid": os.getpid(),
        "child_pid": None,
        "returncode": None,
        "deadline": deadline,
        "timed_out": False,
        "group_cleanup_verified": False,
        "command": [sys.executable, str(script), *request["script_args"]],
        "environment": environment,
        "log_limit_bytes_per_stream": LOG_LIMIT,
        "controller_does_not_capture": True,
    }
    child = None
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(_signum, _frame):
        raise ControllerInterrupted("Container controller terminated")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        if time.monotonic_ns() >= hard:
            result.update(timed_out=True, reason="DEADLINE_EXPIRED_BEFORE_CHILD")
            return result
        child = subprocess.Popen(
            result["command"],
            cwd="/source",
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        result["child_pid"] = child.pid
        counts = {"stdout": 0, "stderr": 0}
        with (
            selectors.DefaultSelector() as selector,
            Path("/out/child-stdout.log").open("wb") as stdout,
            Path("/out/child-stderr.log").open("wb") as stderr,
        ):
            files = {"stdout": stdout, "stderr": stderr}
            selector.register(child.stdout, selectors.EVENT_READ, "stdout")
            selector.register(child.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = (hard - time.monotonic_ns()) / NANOSECONDS
                if remaining <= 0:
                    result["timed_out"] = True
                    _kill_group(child.pid, signal.SIGKILL)
                    break
                for key, _ in selector.select(min(0.1, remaining)):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    take = max(0, LOG_LIMIT - counts[key.data])
                    files[key.data].write(data[:take])
                    counts[key.data] += min(len(data), take)
            remaining = max(0, (hard - time.monotonic_ns()) / NANOSECONDS)
            try:
                result["returncode"] = child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                result["timed_out"] = True
                _kill_group(child.pid, signal.SIGKILL)
        result["saved_log_bytes"] = counts
    except ControllerInterrupted:
        result.update(reason="CONTROLLER_INTERRUPTED", timed_out=True)
    finally:
        if child is not None:
            # Never grant a new execution window during cleanup.
            _kill_group(child.pid, signal.SIGTERM)
            remaining = max(0, (hard - time.monotonic_ns()) / NANOSECONDS)
            try:
                child.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                pass
            _kill_group(child.pid, signal.SIGKILL)
            try:
                result["returncode"] = child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass
            for stream in (child.stdout, child.stderr):
                if stream:
                    stream.close()
            cleanup_until = min(hard, time.monotonic_ns() + 200_000_000)
            while True:
                _reap_orphans()
                if not _group_exists(child.pid):
                    result["group_cleanup_verified"] = True
                    break
                if time.monotonic_ns() >= cleanup_until:
                    break
                time.sleep(0.005)
        else:
            result["group_cleanup_verified"] = True
        signal.signal(signal.SIGTERM, previous)
        result["finished_monotonic_ns"] = time.monotonic_ns()
        write_json(Path("/out/controller-result.json"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--request", default="/control/request.json", choices=["/control/request.json"]
    )
    args = parser.parse_args()
    result = supervise(read_json(Path(args.request)))
    return 124 if result["timed_out"] else 0 if result["group_cleanup_verified"] else 70


if __name__ == "__main__":
    raise SystemExit(main())
