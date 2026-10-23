"""Execute one Python target inside the already isolated Lab container."""

from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

from headroom.lab.hooks import CaptureSession, CaptureSetupError, active_session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-seconds", type=float, default=120)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("script_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    target_args = args.script_args[1:] if args.script_args[:1] == ["--"] else args.script_args
    session = active_session() or CaptureSession(
        args.output, args.max_steps, args.max_seconds, args.seed, args.device
    )
    previous_argv, previous_path = sys.argv, sys.path.copy()
    setup_complete = False
    try:
        if (session.device, session.max_steps, session.max_seconds, session.seed) != (
            args.device,
            args.max_steps,
            args.max_seconds,
            args.seed,
        ):
            raise CaptureSetupError("Injected capture configuration differs from wrapper arguments")
        session.start()
        setup_complete = True
        script = args.script.resolve(strict=True)
        if not script.is_file():
            raise ValueError(f"Target is not a regular file: {script}")
        sys.argv = [str(script), *target_args]
        sys.path.insert(0, str(script.parent))
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        if exc.code is None or exc.code == 0:
            result = session.finish()
        else:
            result = session.finish("error", exc, "system_exit")
    except BaseException as exc:  # noqa: BLE001 - includes controlled BaseException exits
        reason = None if setup_complete else "setup_error"
        result = session.finish("error", exc, reason)
    else:
        result = session.finish()
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
    print(
        json.dumps(
            {
                "event": "lab.capture.finished",
                "status": result["status"],
                "termination_reason": result["termination_reason"],
                "steps": result["steps"],
                "output": str(session.output_dir),
            }
        ),
        flush=True,
    )
    return {"completed": 0, "oom": 42, "error": 1, "timeout": 124}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
