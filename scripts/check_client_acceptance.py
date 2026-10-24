#!/usr/bin/env python3
"""Prepare by default; explicitly execute one T1.3 case only after separate authorization."""

import argparse
import json
from pathlib import Path

from headroom.acceptance.client import (
    CASES,
    execute_client_acceptance,
    prepare_client_acceptance,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--run-limit-usd")
    parser.add_argument("--daily-limit-usd")
    args = parser.parse_args()
    if args.execute:
        if not all(
            (
                args.prepared,
                args.case,
                args.live_authorized,
                args.profile,
                args.run_limit_usd,
                args.daily_limit_usd,
            )
        ):
            parser.error(
                "execute requires prepared, case, live-authorized, profile and explicit run/daily admission limits"
            )
        result = execute_client_acceptance(
            args.prepared,
            case=args.case,
            profile_path=args.profile,
            run_limit_usd=args.run_limit_usd,
            daily_limit_usd=args.daily_limit_usd,
            execute=True,
            live_authorized=True,
        )
        print(
            json.dumps(
                {key: result[key] for key in ("case", "status", "accepted", "checks_passed")}
            )
        )
        return 0 if result["accepted"] else 2
    if not args.output or any(
        (
            args.prepared,
            args.case,
            args.live_authorized,
            args.profile,
            args.run_limit_usd,
            args.daily_limit_usd,
        )
    ):
        parser.error("prepare requires output; only capture is optional, no runtime options")
    result = prepare_client_acceptance(args.output, capture=args.capture)
    print(
        json.dumps(
            {
                "accepted": False,
                "cases": {
                    key: {"status": row["status"], "reason": row.get("reason")}
                    for key, row in result["cases"].items()
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
