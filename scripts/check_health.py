#!/usr/bin/env python3
"""Local health monitor; webhook notifications require an explicit --notify."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from headroom.monitoring import MonitorStateError, check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("runs/health.json"))
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Enable the explicitly configured private .env HTTPS webhook destination",
    )
    args = parser.parse_args()
    try:
        result = check(state_path=args.state, notify=args.notify)
    except (MonitorStateError, OSError) as error:
        result = {
            "monitor_status": "state_error",
            "reason": str(error) if isinstance(error, MonitorStateError) else "state_io_failed",
            "healthy": None,
            "alert_due": None,
            "notification_sent": None,
        }
        print(json.dumps(result))
        raise SystemExit(3) from None
    print(json.dumps(result))
    raise SystemExit(2 if result["alert_due"] else (0 if result["healthy"] else 1))


if __name__ == "__main__":
    main()
