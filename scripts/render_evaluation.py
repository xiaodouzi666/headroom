"""Render saved campaign JSON to stdout; never execute an evaluation."""

import argparse
import json
from pathlib import Path

from headroom.api.security import open_regular
from headroom.evaluation import render_campaign

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    try:
        with open_regular(args.campaign.parent, args.campaign.name, 2 * 1024 * 1024) as handle:
            document = json.load(handle)
        print(render_campaign(document), end="")
    except (OSError, ValueError, TypeError, UnicodeError):
        parser.error("Use a bounded regular campaign JSON file with explicit provenance")
