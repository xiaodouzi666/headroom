"""Run current-source integration and bind results to unchanged source/test/prompt bytes."""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
GUARD = OUTPUT / "integration_guarded.py"
os.chdir(ROOT)
PREFIX = "integration-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources():
    names = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        text=True,
    ).split("\0")
    result = {}
    for name in sorted(set(names)):
        if not name or name.startswith(("docs/", "reports/", "runs/", ".cache/", ".env")):
            continue
        if name.endswith(".md") and not name.startswith(
            ("headroom/prompts/", "scenarios/", "tests/")
        ):
            continue
        path = ROOT / name
        if path.is_symlink():
            result[name] = "symlink:" + os.readlink(path)
        elif path.is_file():
            result[name] = digest(path)
    result["docs/PLAN.md"] = digest(ROOT / "docs/PLAN.md")
    return result


if __name__ == "__main__":
    before = sources()
    guard_before = digest(GUARD)
    before_path = OUTPUT / (PREFIX + "-sources-before.json")
    before_path.write_text(
        json.dumps([{"path": name, "sha256": value} for name, value in before.items()], indent=2)
        + "\n"
    )
    log = OUTPUT / (PREFIX + ".log")
    command = [sys.executable, str(GUARD)]
    started = time.monotonic()
    with log.open("x") as handle:
        child = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, cwd=ROOT)
        print(json.dumps({"pid": child.pid, "log": str(log), "prefix": PREFIX}), flush=True)
        code = child.wait()
    after = sources()
    after_path = OUTPUT / (PREFIX + "-sources-after.json")
    after_path.write_text(
        json.dumps([{"path": name, "sha256": value} for name, value in after.items()], indent=2)
        + "\n"
    )
    changes = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    receipt = {
        "scope": "Current production tree targeted integration, not previous or new full-suite acceptance",
        "command": command,
        "exit_code": code,
        "elapsed_seconds": time.monotonic() - started,
        "source_count": len(before),
        "source_unchanged": not changes,
        "changed_sources": changes,
        "before": str(before_path.relative_to(ROOT)),
        "after": str(after_path.relative_to(ROOT)),
        "before_sha256": digest(before_path),
        "after_sha256": digest(after_path),
        "log": str(log.relative_to(ROOT)),
        "log_sha256": digest(log),
        "guard": str(GUARD.relative_to(ROOT)),
        "guard_sha256_before": guard_before,
        "guard_sha256_after": digest(GUARD),
        "guard_unchanged": guard_before == digest(GUARD),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "real_provider_calls": 0,
        "gpu_jobs": 0,
        "real_env_profile_db_access": False,
        "cpu_docker_executed": True,
    }
    path = OUTPUT / (PREFIX + "-receipt.json")
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)
    raise SystemExit(code if code else int(bool(changes) or not receipt["guard_unchanged"]))
