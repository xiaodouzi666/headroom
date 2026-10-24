#!/usr/bin/env python3
"""Bounded local health check; records failures, never sends a notification by default."""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def check(url="http://127.0.0.1:8000/api/health", *, state_path=Path("runs/health.json")):
    if url not in {"http://127.0.0.1:8000/api/health", "http://localhost:8000/api/health"}:
        raise ValueError("Only the local production health endpoint is supported")
    now = time.time()
    previous = {}
    if state_path.is_file() and not state_path.is_symlink():
        previous = json.loads(state_path.read_text())
    try:
        with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=5) as response:
            body = response.read(1024 * 1024)
            data = json.loads(body)
        healthy = (
            data.get("status") == "ok"
            and data.get("db") == "ok"
            and not data.get("queue", {}).get("halted")
        )
    except (OSError, ValueError):
        healthy = False
    failure_since = None if healthy else previous.get("failure_since") or now
    state = {
        "checked_at": now,
        "healthy": healthy,
        "failure_since": failure_since,
        "alert_due": failure_since is not None and now - failure_since >= 120,
        "notification_sent": False,
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(state_path)
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("runs/health.json"))
    args = parser.parse_args()
    result = check(state_path=args.state)
    print(json.dumps(result))
    raise SystemExit(2 if result["alert_due"] else (0 if result["healthy"] else 1))


if __name__ == "__main__":
    main()
