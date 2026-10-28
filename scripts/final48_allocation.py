#!/usr/bin/env python3
"""Print a null-amount FINAL48 plan by default; activation is explicit and sends no requests."""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from headroom.acceptance.allocation import (
    AllocationRefused,
    activate_allocation,
    prepare_allocation_plan,
)
from headroom.acceptance.common import read_json, write_json
from headroom.runtime import PROJECT_ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--profile-input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.activate:
        if not all((args.plan, args.authorization, args.profile_input)):
            parser.error(
                "Activation needs reviewed plan, explicit amount authorization and profile input"
            )
        if args.output:
            parser.error("--output is only available for draft templates")
        try:
            receipt = activate_allocation(
                read_json(args.plan),
                read_json(args.authorization),
                read_json(args.profile_input),
                project_root=PROJECT_ROOT,
            )
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
            print(
                json.dumps(
                    {
                        "state": "refused",
                        "reason": str(error)
                        if isinstance(error, AllocationRefused)
                        else type(error).__name__,
                    }
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "state": "active",
                    "allocation_id": receipt["allocation_id"],
                    "receipt_sha256": receipt["receipt_sha256"],
                }
            )
        )
    else:
        if args.plan or args.authorization or args.profile_input:
            parser.error("Activation inputs require --activate")
        result = prepare_allocation_plan()
        if args.output:
            if args.output.exists():
                parser.error("Output must be a new template file")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_json(args.output, result)
        else:
            print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
