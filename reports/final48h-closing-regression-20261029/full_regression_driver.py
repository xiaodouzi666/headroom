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
        if (
            not name
            or (
                name.lower().endswith(".md")
                and not name.startswith(("headroom/prompts/", "scenarios/", "tests/"))
            )
            or name.startswith(("docs/", "reports/", "runs/", ".cache/", ".env"))
        ):
            continue
        path = ROOT / name
        if path.is_symlink():
            hashes[name] = "symlink:" + os.readlink(path)
        elif path.is_file():
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


if __name__ == "__main__":
    before = source_hashes()
    plan_before = hashlib.sha256((ROOT / "docs/PLAN.md").read_bytes()).hexdigest()
    guard_before = hashlib.sha256(
        (ROOT / "reports/final48h-closing-regression-20261029/closing_guarded.py").read_bytes()
    ).hexdigest()
    if guard_before != "c437a337ea614dc776c6d48d26e996116d0cbffec17a44157bf5ac575f7eef53":
        raise RuntimeError("Pinned offline guard changed; refuse test launch")
    before_path = OUTPUT / (PREFIX + "-sources-before.json")
    before_path.write_text(
        json.dumps([{"path": k, "sha256": v} for k, v in before.items()], indent=2) + "\n"
    )
    log_path = OUTPUT / (PREFIX + ".log")
    started = time.monotonic()
    with log_path.open("x") as output:
        child = subprocess.Popen(
            [
                sys.executable,
                "reports/final48h-closing-regression-20261029/closing_guarded.py",
                *sys.argv[1:],
            ],
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
    after_path.write_text(
        json.dumps([{"path": k, "sha256": v} for k, v in after.items()], indent=2) + "\n"
    )
    changes = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    result = {
        "exit_code": code,
        "pytest_arguments": ["-q", *sys.argv[1:]],
        "suite": "full" if not sys.argv[1:] else "focused",
        "elapsed_seconds": time.monotonic() - started,
        "source_count_before": len(before),
        "source_count_after": len(after),
        "source_unchanged": not changes,
        "changed_sources": changes,
        "source_scope": "All tracked and nonignored untracked source files, including production prompts and scenario/test Markdown; excludes general docs/reports/runs/.cache/.env* and other Markdown; PLAN separately hashed",
        "source_hash_algorithm": "sha256; symlink targets recorded without following",
        "log": str(log_path.relative_to(ROOT)),
        "before": str(before_path.relative_to(ROOT)),
        "after": str(after_path.relative_to(ROOT)),
        "guard_driver": "reports/final48h-closing-regression-20261029/closing_guarded.py",
        "guard_driver_sha256_before": guard_before,
        "guard_driver_sha256": hashlib.sha256(
            (ROOT / "reports/final48h-closing-regression-20261029/closing_guarded.py").read_bytes()
        ).hexdigest(),
        "plan_sha256_before": plan_before,
        "plan_sha256": hashlib.sha256((ROOT / "docs/PLAN.md").read_bytes()).hexdigest(),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    }
    result["passed"] = code == 0 and not changes
    result["plan_unchanged"] = result["plan_sha256"] == plan_before
    result["guard_unchanged"] = result["guard_driver_sha256"] == guard_before
    receipt_path = OUTPUT / (PREFIX + "-receipt.json")
    receipt_path.write_text(json.dumps(result, indent=2) + "\n")
    try:
        print(json.dumps(result), flush=True)
    except BrokenPipeError:
        pass  # SSH loss must not prevent the saved receipt from completing.
    raise SystemExit(code if code else int(bool(changes) or not result["plan_unchanged"]))
