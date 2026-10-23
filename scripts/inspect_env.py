#!/usr/bin/env python3
"""Read-only environment preflight; retain command outputs and exit status."""

import datetime
import json
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
checks = [
    ("GPU", ["nvidia-smi"]),
    ("OS", ["lsb_release", "-a"]),
    ("Disk", ["df", "-h", str(root)]),
    ("Memory", ["free", "-g"]),
    ("Python", ["python3", "--version"]),
    (
        "Tools",
        ["bash", "-c", "command -v uv; command -v docker; command -v git; command -v gitleaks"],
    ),
    ("Docker", ["docker", "info"]),
    (
        "Docker GPU",
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "--network",
            "none",
            "nvidia/cuda:12.4.1-base-ubuntu22.04",
            "nvidia-smi",
        ],
    ),
    ("Sudo", ["sudo", "-n", "true"]),
    (
        "Network",
        ["curl", "-sSI", "--connect-timeout", "15", "--max-time", "30", "https://huggingface.co"],
    ),
]
results = []
for name, cmd in checks:
    try:
        p = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=180)
        row = {
            "name": name,
            "command": cmd,
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        row = {
            "name": name,
            "command": cmd,
            "exit_code": 124 if isinstance(exc, subprocess.TimeoutExpired) else 127,
            "stdout": "",
            "stderr": str(exc),
        }
    results.append(row)
    print(name, row["exit_code"], flush=True)
free = shutil.disk_usage(root).free / (1024**3)
by = {r["name"]: r for r in results}
conclusion = {
    "DOCKER_GPU": "ok" if by["Docker GPU"]["exit_code"] == 0 else "unavailable",
    "NET": "ok" if by["Network"]["exit_code"] == 0 else "unavailable",
    "DISK_FREE_GB": round(free, 2),
}
lines = [
    "# Environment preflight",
    "",
    datetime.datetime.now(datetime.UTC).isoformat(),
    "",
    "```json",
    json.dumps(conclusion, indent=2),
    "```",
    "",
]
for r in results:
    lines.extend(
        [
            "## " + r["name"],
            "",
            "Command: `" + " ".join(r["command"]) + "`",
            "",
            "Exit: " + str(r["exit_code"]),
            "",
            "```text",
            r["stdout"] + r["stderr"],
            "```",
            "",
        ]
    )
(root / "docs/ENV.md").write_text("\n".join(lines))
(root / "reports/env-preflight.json").write_text(
    json.dumps({"conclusion": conclusion, "checks": results}, indent=2)
)
print(json.dumps(conclusion), flush=True)
