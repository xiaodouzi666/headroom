#!/usr/bin/env python3
"""Prepare F1 offline by default; opt-in execution still requires existing admission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from headroom.acceptance.final48_ablation import (
    DEFAULT_CAMPAIGN,
    F1Refused,
    execute_f1,
    prepare_f1,
)
from headroom.runtime import PROJECT_ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=PROJECT_ROOT / DEFAULT_CAMPAIGN)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-budget", type=int, default=150000)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--allocation-receipt", type=Path)
    parser.add_argument("--daily-limit-usd")
    parser.add_argument("--campaign-limit-usd", default="1.50")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if not all(
                (
                    args.live_authorized,
                    args.prepared,
                    args.profile,
                    args.daily_limit_usd,
                    args.allocation_receipt,
                )
            ):
                parser.error(
                    "Execution requires --live-authorized, --prepared, --profile, --daily-limit-usd and --allocation-receipt"
                )
            result = execute_f1(
                args.prepared,
                profile_path=args.profile,
                daily_limit_usd=args.daily_limit_usd,
                campaign_limit_usd=args.campaign_limit_usd,
                execute=True,
                live_authorized=True,
                allocation_receipt=args.allocation_receipt,
            )
            summary = {
                key: result[key]
                for key in (
                    "mode",
                    "provenance",
                    "planned_requests",
                    "completed_all_requests",
                    "within_budget",
                    "study_complete_within_budget",
                    "stop_reason",
                    "known_cost_usd",
                    "total_cost_usd",
                    "conditions",
                )
            }
            success = result["study_complete_within_budget"]
        else:
            if (
                args.live_authorized
                or args.prepared
                or args.profile
                or args.daily_limit_usd
                or args.allocation_receipt
            ):
                parser.error(
                    "Execution-only flags require --execute; preparation never reads credentials"
                )
            if args.output is None:
                parser.error("Preparation requires a new private --output path under runs/")
            result = prepare_f1(args.campaign, args.output, evidence_budget=args.evidence_budget)
            summary = {
                key: result[key]
                for key in (
                    "mode",
                    "provenance",
                    "inputs_ready",
                    "ready_requests",
                    "planned_requests",
                    "executed_requests",
                    "request_policy",
                    "preparation_sha256",
                )
            }
            success = result["inputs_ready"]
        print(json.dumps(summary, indent=2))
        return 0 if success else 1
    except (F1Refused, OSError, ValueError) as error:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": str(error) if isinstance(error, F1Refused) else type(error).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
