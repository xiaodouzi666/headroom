#!/usr/bin/env python3
"""Check that rendered report GB/GiB/percentage figures have JSON provenance."""

import argparse
import json
from pathlib import Path

from headroom.report import check_report_numbers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Report directory, report.md, or report.json")
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args()
    base = args.path if args.path.is_dir() else args.path.parent
    markdown = args.path if args.path.suffix == ".md" else base / "report.md"
    json_path = args.json_path or (
        args.path if args.path.suffix == ".json" else base / "report.json"
    )
    try:
        document = json.loads(json_path.read_text())
        missing = check_report_numbers(document, markdown.read_text())
    except (OSError, ValueError, TypeError):
        print("FAIL: unable to read a valid report pair")
        return 1
    if missing:
        print("FAIL: report contains measurement figures absent from report.json")
        return 1
    print("PASS: all GB/GiB/percentage figures are present in report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
