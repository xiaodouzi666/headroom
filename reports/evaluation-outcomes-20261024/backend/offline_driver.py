"""Independent no-network/no-real-env guard for focused evaluation outcome verification."""

import builtins
import hashlib
import io
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
blocked = []


def denied(*args, **kwargs):
    blocked.append("external_network")
    raise RuntimeError("External DNS/INET calls forbidden by independent outcome test guard")


socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied


def guard(original):
    def checked(path, *args, **kwargs):
        if (
            isinstance(path, (str, bytes, os.PathLike))
            and Path(os.fsdecode(path)).absolute() == ROOT / ".env"
        ):
            blocked.append("real_env")
            raise RuntimeError("Reading real .env is forbidden by independent guard")
        return original(path, *args, **kwargs)

    return checked


builtins.open = guard(builtins.open)
io.open = guard(io.open)
os.open = guard(os.open)
paths = [
    "headroom/evaluation.py",
    "headroom/api/evaluations.py",
    "tests/test_evaluation_outcomes.py",
]
before = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in paths}
started = time.monotonic()
import pytest

code = pytest.main(
    [
        "-q",
        "tests/test_evaluation_outcomes.py",
        "tests/test_evaluation.py",
        "tests/test_published_evaluations.py",
    ]
)
after = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in paths}
receipt = {
    "exit_code": code,
    "elapsed_seconds": time.monotonic() - started,
    "source_unchanged": before == after,
    "source_sha256": after,
    "blocked_external_attempts": blocked,
    "actual_api_calls": 0,
    "gpu_tasks": 0,
    "real_env_read": False,
    "live_profile_enabled": False,
}
Path(__file__).with_name("focused-summary.json").write_text(json.dumps(receipt, indent=2) + "\n")
raise SystemExit(code)
