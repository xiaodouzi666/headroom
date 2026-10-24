#!/usr/bin/env python3
"""Validate preserved real repairs; --execute explicitly curates only the selected IDs."""

import argparse
import json
import sqlite3

from headroom.replay_curation import CurationRefused, curate_repair_replays


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        action="append",
        required=True,
        help="Existing real repair ID; repeat explicitly",
    )
    parser.add_argument(
        "--execute", action="store_true", help="Copy approved display assets and set curation flags"
    )
    args = parser.parse_args(argv)
    try:
        result = curate_repair_replays(args.run_id, execute=args.execute)
    except (CurationRefused, OSError, ValueError, sqlite3.Error) as error:
        print(
            json.dumps(
                {
                    "executed": False,
                    "reason": str(error)
                    if isinstance(error, CurationRefused)
                    else type(error).__name__,
                }
            )
        )
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
