#!/usr/bin/env python3
"""Audit one full request using existing local assets. No API or credential access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from headroom.llm.preflight import (
    TOKENIZER_REVISION,
    PreflightRefused,
    PromptAuditor,
    load_request,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", type=Path, help="Complete SDK kwargs or wire request JSON")
    parser.add_argument(
        "--asset-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / ".cache/tokenizers/nemotron-3-ultra"
        / TOKENIZER_REVISION,
        help="Existing hash-pinned tokenizer files; never downloaded automatically",
    )
    parser.add_argument("--output", type=Path, help="New report path; refuses to overwrite")
    args = parser.parse_args(argv)
    try:
        request = load_request(args.request)
        report = PromptAuditor(args.asset_dir).audit(request)
        rendered = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            sys.stdout.write(rendered)
    except PreflightRefused as error:
        print("Prompt audit refused: " + str(error), file=sys.stderr)
        return 2
    except OSError:
        print(
            "Prompt audit refused: report output is unavailable or already exists", file=sys.stderr
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
