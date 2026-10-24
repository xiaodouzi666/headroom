"""Run the existing guarded full backend suite and record immutable source hashes."""

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
os.chdir(ROOT)
PREFIX = "full-regression-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def source_hashes():
    names = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    hashes = {}
    for name in sorted(set(names)):
        if not name or name.startswith(("docs/", "reports/", "runs/", ".cache/", ".env")):
            continue
        path = ROOT / name
        if path.is_symlink():
            hashes[name] = "symlink:" + os.readlink(path)
        elif path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


if __name__ == "__main__":
    before = source_hashes()
    before_path = OUTPUT / (PREFIX + "-sources-before.json")
    before_path.write_text(json.dumps(before, indent=2) + "\n")
    log_path = OUTPUT / (PREFIX + ".log")
    started = time.monotonic()
    with log_path.open("x") as output:
        child = subprocess.Popen(
            [sys.executable, ".cache/setup/run_full_guarded.py"],
            cwd=ROOT,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        print(
            json.dumps(
                {
                    "pid": child.pid,
                    "log": str(log_path.relative_to(ROOT)),
                    "source_count": len(before),
                    "prefix": PREFIX,
                }
            ),
            flush=True,
        )
        code = child.wait()
    after = source_hashes()
    after_path = OUTPUT / (PREFIX + "-sources-after.json")
    after_path.write_text(json.dumps(after, indent=2) + "\n")
    changes = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    result = {
        "exit_code": code,
        "elapsed_seconds": time.monotonic() - started,
        "source_count_before": len(before),
        "source_count_after": len(after),
        "source_unchanged": not changes,
        "changed_sources": changes,
        "source_scope": "All tracked and nonignored untracked files except docs/reports/runs/.cache/.env*",
        "source_hash_algorithm": "sha256; symlink targets recorded without following",
        "log": str(log_path.relative_to(ROOT)),
        "before": str(before_path.relative_to(ROOT)),
        "after": str(after_path.relative_to(ROOT)),
        "guard_driver": ".cache/setup/run_full_guarded.py",
        "guard_driver_sha256": hashlib.sha256(
            (ROOT / ".cache/setup/run_full_guarded.py").read_bytes()
        ).hexdigest(),
        "plan_sha256": hashlib.sha256((ROOT / "docs/PLAN.md").read_bytes()).hexdigest(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    receipt_path = OUTPUT / (PREFIX + "-receipt.json")
    receipt_path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    raise SystemExit(code if code else int(bool(changes)))
