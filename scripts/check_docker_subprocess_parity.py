#!/usr/bin/env python3
"""Inspect the zero-model-cost T2.7 plan; --execute explicitly runs six CUDA arms."""

import argparse
import json
from pathlib import Path

from headroom.acceptance.isolation import plan_cases, run_acceptance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-seconds", type=float, default=180)
    args = parser.parse_args(argv)
    if args.execute and args.output is None:
        parser.error("--execute requires a new --output directory")
    if not args.execute:
        print(json.dumps(plan_cases(), indent=2))
        return 0
    report = run_acceptance(args.output, max_seconds=args.max_seconds)
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
