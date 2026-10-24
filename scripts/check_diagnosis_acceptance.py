#!/usr/bin/env python3
"""Prepare T1.4 from eight chosen captures; live execution requires explicit flags."""

import argparse
import json
from pathlib import Path

from headroom.acceptance.common import read_json
from headroom.acceptance.diagnosis import (
    SCENARIO_IDS,
    DiagnosisAcceptanceRefused,
    execute_diagnosis_acceptance,
    prepare_diagnosis_acceptance,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--captures",
        type=Path,
        help="JSON object mapping the eight scenario IDs to capture directories",
    )
    parser.add_argument(
        "--from-baselines",
        type=Path,
        help="Existing baseline JSON report; select its eight synthetic IDs without running them",
    )
    parser.add_argument("--output", type=Path, help="New private preparation directory")
    parser.add_argument("--evidence-budget", type=int, default=150000)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--prepared", type=Path, help="Previously reviewed preparation.json")
    parser.add_argument("--runtime-profile", type=Path)
    parser.add_argument("--admission-cap-usd", default=None)
    parser.add_argument("--campaign-cap-usd", default=None)
    parser.add_argument("--daily-cap-usd", default=None)
    parser.add_argument(
        "--min-case-interval-seconds",
        type=float,
        default=0,
        help="Minimum start-to-start interval for independent cases, from 0 to 60 seconds",
    )
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if (
                not args.live_authorized
                or not args.prepared
                or not args.runtime_profile
                or not args.admission_cap_usd
                or not args.campaign_cap_usd
                or not args.daily_cap_usd
            ):
                raise DiagnosisAcceptanceRefused(
                    "EXPLICIT_PROFILE_PREPARATION_AND_AUTHORIZATION_REQUIRED"
                )
            if args.captures or args.from_baselines or args.output:
                raise DiagnosisAcceptanceRefused("EXECUTION_USES_ONLY_THE_REVIEWED_PREPARATION")
            report = execute_diagnosis_acceptance(
                args.prepared,
                profile_path=args.runtime_profile,
                run_limit_usd=args.admission_cap_usd,
                campaign_limit_usd=args.campaign_cap_usd,
                daily_limit_usd=args.daily_cap_usd,
                min_case_interval_seconds=args.min_case_interval_seconds,
                execute=True,
                live_authorized=True,
            )
            print(
                json.dumps(
                    {
                        "mode": "execute",
                        "accepted": report["accepted"],
                        "matches": report["first_cause_matches"],
                        "denominator": 8,
                        "stop_reason": report["stop_reason"],
                        "result": str(args.prepared.parent / "execution/result.json"),
                    }
                )
            )
            return 0 if report["accepted"] else 1
        if (
            args.live_authorized
            or args.prepared
            or args.runtime_profile
            or args.min_case_interval_seconds != 0
        ):
            raise DiagnosisAcceptanceRefused("PREPARATION_DOES_NOT_USE_LIVE_OPTIONS")
        if bool(args.captures) == bool(args.from_baselines) or not args.output:
            raise DiagnosisAcceptanceRefused("ONE_CAPTURE_INPUT_AND_NEW_OUTPUT_REQUIRED")
        if args.from_baselines:
            data = read_json(args.from_baselines)
            rows = [row for row in data["rows"] if row.get("scenario_id") in SCENARIO_IDS]
            if len({row["scenario_id"] for row in rows}) != len(rows):
                raise DiagnosisAcceptanceRefused("DUPLICATE_SCENARIO_ID")
            captures = {row["scenario_id"]: row["run_dir"] for row in rows}
        else:
            captures = read_json(args.captures)
        report = prepare_diagnosis_acceptance(
            captures, args.output, evidence_budget=args.evidence_budget
        )
        print(
            json.dumps(
                {
                    "mode": "prepare",
                    "accepted": False,
                    "ready_count": report["ready_count"],
                    "ready_for_execution": report["ready_for_execution"],
                    "preparation": str(args.output / "preparation.json"),
                    "rows": [
                        {key: row.get(key) for key in ("scenario_id", "status", "reason")}
                        for row in report["rows"]
                    ],
                }
            )
        )
        return 0 if report["ready_for_execution"] else 1
    except (OSError, ValueError, TypeError, KeyError) as error:
        reason = (
            str(error) if isinstance(error, DiagnosisAcceptanceRefused) else type(error).__name__
        )
        print(json.dumps({"accepted": False, "status": "refused", "reason": reason}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
