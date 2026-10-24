"""Independent network/real credential guards; no provider or GPU execution."""

import builtins
import io
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
ATTEMPTS = []


def denied(*args, **kwargs):
    ATTEMPTS.append("network")
    raise RuntimeError("External network forbidden")


socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied


def guarded(original):
    def check(path, *args, **kwargs):
        if (
            isinstance(path, (str, bytes, os.PathLike))
            and Path(os.fsdecode(path)).resolve() == ROOT / ".env"
        ):
            ATTEMPTS.append("real_env")
            raise RuntimeError("Real credential file access forbidden")
        return original(path, *args, **kwargs)

    return check


builtins.open = guarded(builtins.open)
io.open = guarded(io.open)
os.open = guarded(os.open)


if __name__ == "__main__":
    import pytest

    started = time.monotonic()
    name, *tests = sys.argv[1:]
    code = pytest.main(["-q", *tests])
    receipt = {
        "exit_code": code,
        "tests": tests,
        "external_access_attempts": ATTEMPTS,
        "elapsed_seconds": time.monotonic() - started,
        "live_api_calls": 0,
        "gpu_tasks": 0,
    }
    Path(__file__).with_name(name + ".json").write_text(json.dumps(receipt, indent=2) + "\n")
    raise SystemExit(code)
