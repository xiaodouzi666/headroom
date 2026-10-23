#!/usr/bin/env python3
"""Record T0.3 CUDA/snapshot/identity/secret-handling acceptance checks."""

import datetime
import json
import os
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
checks = [
    (
        "CUDA",
        [
            ".venv/bin/python",
            "-c",
            "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name())",
        ],
    ),
    (
        "Memory snapshot",
        [
            ".venv/bin/python",
            "-c",
            "import torch; torch.cuda.memory._record_memory_history(); x=torch.randn(1024,1024,device='cuda'); s=torch.cuda.memory._snapshot(); print(len(s['segments'])>0, 'device_traces' in s)",
        ],
    ),
    ("Git author name", ["git", "config", "user.name"]),
    ("Git author email", ["git", "config", "user.email"]),
    ("Secret ignore", ["git", "check-ignore", ".env"]),
    ("Gitleaks history", [".tools/bin/gitleaks", "detect", "--redact", "--no-banner"]),
]
rows = []
for name, cmd in checks:
    p = subprocess.run(
        cmd,
        check=False,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=120,
        env={
            k: v
            for k, v in os.environ.items()
            if k not in {"NEBIUS_API_KEY", "TAVILY_API_KEY", "HF_TOKEN"}
        },
    )
    rows.append(
        {
            "check": name,
            "command": cmd,
            "exit_code": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    )
    print(name, p.returncode, p.stdout.strip(), flush=True)
mode = oct((root / ".env").stat().st_mode & 0o777)
result = {"at": datetime.datetime.now(datetime.UTC).isoformat(), "env_mode": mode, "checks": rows}
(root / "reports/toolchain-checks.json").write_text(json.dumps(result, indent=2))
raise SystemExit(0 if all(r["exit_code"] == 0 for r in rows) and mode == "0o600" else 1)
