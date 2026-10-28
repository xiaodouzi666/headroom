#!/usr/bin/env python3
"""Prepare/verify F3 without execution; live execution requires explicit funding and pins."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from headroom.acceptance.final48_repair import (
    CALIBRATION,
    ROOT,
    F3Refused,
    cell_request_pins,
    digest,
    execute_f3,
    inside,
    prepare_f3,
    require,
    verify_preparation,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--calibration", default=CALIBRATION)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--bind-profile", type=Path)
    parser.add_argument("--daily-limit-usd")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--live-authorized", action="store_true")
    parser.add_argument("--allocation-receipt", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--scope-limit-usd", default="4")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            if (
                args.verify
                or args.bind_profile
                or args.daily_limit_usd
                or not all(
                    (
                        args.live_authorized,
                        args.prepared,
                        args.expected_sha256,
                        args.allocation_receipt,
                        args.profile,
                        args.output,
                    )
                )
            ):
                parser.error(
                    "Execution requires reviewed SHA, prepared pack, explicit authorization, receipt, profile and new output directory"
                )
            result = execute_f3(
                args.prepared,
                expected_sha256=args.expected_sha256,
                allocation_receipt=args.allocation_receipt,
                profile_path=args.profile,
                output_dir=args.output,
                execute=True,
                live_authorized=True,
                scope_limit_usd=args.scope_limit_usd,
            )
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in (
                            "status",
                            "stop_reason",
                            "executed_cells",
                            "remaining_unrun_cells",
                            "scope_spent_usd",
                            "scope_charged_usd",
                            "all_costs_known",
                            "all_costs_resolved",
                            "report_path",
                        )
                    },
                    indent=2,
                )
            )
            return 0 if result["status"] == "finished" else 1
        if (
            args.live_authorized
            or args.allocation_receipt
            or args.profile
            or args.scope_limit_usd != "4"
        ):
            parser.error(
                "Live-only flags require --execute; preparation never opens the allocation"
            )
        if args.verify:
            if not args.prepared or not args.expected_sha256 or args.output:
                parser.error(
                    "Verification requires --prepared and --expected-sha256 and never writes output"
                )
            result = verify_preparation(args.prepared, expected_sha256=args.expected_sha256)
        else:
            if args.prepared or args.expected_sha256:
                parser.error("Use --verify to check an existing prepared pack")
            result = prepare_f3(calibration_path=args.calibration)
            if args.output:
                output = inside(ROOT, args.output)
                require(
                    output.is_relative_to(ROOT / "runs") and output.suffix == ".json",
                    "NEW_PRIVATE_PREPARATION_JSON_REQUIRED",
                )
                output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with output.open("x", encoding="utf-8") as handle:
                    json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
                    handle.write("\n")
                output.chmod(0o600)
        summary = {
            k: result[k]
            for k in ("schema", "mode", "planned_cells", "executed_cells", "preparation_sha256")
        }
        summary["verified"] = args.verify
        if args.bind_profile or args.daily_limit_usd:
            if not (args.bind_profile and args.daily_limit_usd):
                parser.error(
                    "Request binding requires both --bind-profile and --daily-limit-usd; it creates no allocation"
                )
            pins = cell_request_pins(
                result, profile_path=args.bind_profile, daily_limit_usd=args.daily_limit_usd
            )
            summary["allocation_input_binding"] = {
                "preparation_sha256": result["preparation_sha256"],
                "cell_requests_sha256": digest(pins),
                "cell_requests": pins,
            }
        print(json.dumps(summary, indent=2))
        return 0
    except (F3Refused, OSError, ValueError, TypeError, KeyError) as error:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": str(error) if isinstance(error, F3Refused) else type(error).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
