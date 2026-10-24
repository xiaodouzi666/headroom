"""Focused offline curation checks; the existing guard installs without its main."""

import contextlib
import hashlib
import json
import multiprocessing
import os
import socket
import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path("/home/xiaodouzi/workspace/headroom")
OUTPUT = ROOT / "reports/replay-ui-preparation-20261025"
GUARD = ROOT / "reports/super-patch-fix-20261025/integration_guarded.py"
sys.path.insert(0, str(GUARD.parent))
import integration_guarded as guard


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(channel=None):
    result = guard.guard_probe()
    attempts = {
        "os_open_real_env": lambda: os.open(ROOT / ".env", os.O_RDONLY),
        "os_open_real_profile": lambda: os.open(
            ROOT / ".cache/tokenfactory-runtime.json", os.O_RDONLY
        ),
        "production_store_sqlite": lambda: sqlite3.connect(
            (ROOT / "runs/headroom.db").as_uri() + "?mode=ro", uri=True
        ),
        "inet": lambda: socket.socket(socket.AF_INET).connect(("127.0.0.1", 8765)),
    }
    for name, action in attempts.items():
        try:
            action()
        except PermissionError:
            result[name] = "denied"
        else:
            raise AssertionError("Guard failed before pytest: " + name)
    if channel is not None:
        channel.send(result)
        channel.close()
    return result


def main():
    paths = ("headroom/replay_curation.py", "tests/test_repair_replay_curation.py")
    before = {name: digest(ROOT / name) for name in paths}
    guard_hash = digest(GUARD)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    log = OUTPUT / ("curation-focused-" + stamp + ".log")
    receipt = OUTPUT / ("curation-focused-" + stamp + "-receipt.json")
    start = time.monotonic()
    with (
        log.open("x") as handle,
        contextlib.redirect_stdout(handle),
        contextlib.redirect_stderr(handle),
    ):
        parent = probe()
        context = multiprocessing.get_context("spawn")
        incoming, outgoing = context.Pipe(duplex=False)
        process = context.Process(target=probe, args=(outgoing,))
        process.start()
        outgoing.close()
        if not incoming.poll(20):
            process.terminate()
            process.join(5)
            raise RuntimeError("Spawn guard self-check timed out")
        spawned = incoming.recv()
        incoming.close()
        process.join(10)
        if process.exitcode != 0 or spawned != parent:
            raise RuntimeError("Spawn guard self-check failed")
        print(json.dumps({"guard_parent": parent, "guard_spawn": spawned}), flush=True)
        import pytest

        code = int(pytest.main(["-q", "tests/test_repair_replay_curation.py"]))
    after = {name: digest(ROOT / name) for name in paths}
    data = {
        "scope": "Offline curation role/ownership/artifact/transaction tests only",
        "created_utc": datetime.now(UTC).isoformat(),
        "exit_code": code,
        "elapsed_seconds": time.monotonic() - start,
        "log": str(log.relative_to(ROOT)),
        "log_sha256": digest(log),
        "source_before": before,
        "source_after": after,
        "source_unchanged": before == after,
        "guard_path": str(GUARD.relative_to(ROOT)),
        "guard_sha256_before": guard_hash,
        "guard_sha256_after": digest(GUARD),
        "guard_parent": parent,
        "guard_spawn": spawned,
        "driver_sha256": digest(Path(__file__)),
        "real_api_calls": 0,
        "real_database_access": False,
        "real_profile_or_env_access": False,
        "gpu_runs": 0,
        "production_curation_executed": False,
        "fixture_asgi_requests_only": True,
    }
    with receipt.open("x") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"receipt": str(receipt.relative_to(ROOT)), **data}, indent=2))
    return code if code else int(before != after or guard_hash != digest(GUARD))


if __name__ == "__main__":
    raise SystemExit(main())
