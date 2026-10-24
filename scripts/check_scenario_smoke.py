#!/usr/bin/env python3
"""T0.6 CPU plumbing checks in Docker; never a GPU acceptance substitute."""

import argparse
import datetime
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from headroom.lab.runtime_image import IMAGE, require_runtime_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--report", default=None, help="Optional report path inside the project")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    root = ROOT
    cases = sorted((root / "scenarios").glob("s*/train.py"))
    if args.scenario:
        cases = [p for p in cases if p.parent.name in args.scenario]
    if not cases:
        parser.error("No scenario sources found")
    rows = []
    safe_env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN"}
    }
    runtime_image = require_runtime_image(root, executable="docker", environment=safe_env)
    for script in cases:
        name = "headroom-smoke-" + uuid.uuid4().hex[:12]
        command = [
            "docker",
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "2g",
            "--cpus",
            "2",
            "--user",
            "65534:65534",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m",
            "--tmpfs",
            "/work:rw,nosuid,nodev,size=64m",
            "--workdir",
            "/work",
            "--mount",
            f"type=bind,src={root / 'scenarios'},dst=/cases,readonly",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "OMP_NUM_THREADS=2",
            "--entrypoint",
            "/opt/venv/bin/python",
            runtime_image["image_id"],
            f"/cases/{script.parent.name}/train.py",
            "--tiny",
            "--device",
            "cpu",
            "--steps",
            "20",
        ]
        started = datetime.datetime.now(datetime.UTC)
        try:
            p = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=args.timeout,
                env=safe_env,
            )
            status = "passed" if p.returncode == 0 else "failed"
            stdout, stderr, exit_code = p.stdout, p.stderr, p.returncode
        except subprocess.TimeoutExpired as exc:
            status, exit_code = "timeout", 124
            stdout = (exc.stdout or b"").decode(errors="replace")
            stderr = (exc.stderr or b"").decode(errors="replace")
        finally:
            cleanup = subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
                env=safe_env,
            )
        rows.append(
            {
                "scenario": script.parent.name,
                "status": status,
                "command": command,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "cleanup_exit": cleanup.returncode,
                "wall_seconds": (datetime.datetime.now(datetime.UTC) - started).total_seconds(),
            }
        )
        print(script.parent.name, status, "exit", exit_code, flush=True)
        if exit_code:
            print(stderr[-2000:], flush=True)
    result = {
        "at": datetime.datetime.now(datetime.UTC).isoformat(),
        "scope": "tiny CPU plumbing only; full GPU calibration and T0.6 acceptance pending",
        "network": "none",
        "requested_image": IMAGE,
        "runtime_image": runtime_image,
        "source_read_only": True,
        "api_keys_mounted": False,
        "cases": rows,
    }
    report = root / (args.report or f"reports/scenario-cpu-smoke-{uuid.uuid4().hex[:12]}.json")
    report.resolve().relative_to(root)
    if report.exists():
        raise FileExistsError("Refusing to replace an existing run report")
    report.write_text(json.dumps(result, indent=2) + "\n")
    return (
        0
        if all(row["exit_code"] == 0 for row in rows)
        and len(cases) == (len(set(args.scenario)) if args.scenario else 8)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
