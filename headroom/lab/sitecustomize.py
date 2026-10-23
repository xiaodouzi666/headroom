"""Opt-in command capture; expose this directory on the sandbox PYTHONPATH."""

import json
import os
import sys
import traceback
from pathlib import Path

if os.environ.get("HEADROOM_CAPTURE") == "1":
    try:
        from headroom.lab.hooks import install_from_environment

        install_from_environment()
    except BaseException as exc:  # noqa: BLE001 - includes controlled BaseException exits
        # Python normally prints and ignores sitecustomize import errors. Fail
        # closed here, so a target cannot run without requested instrumentation.
        details = {
            "protocol": "headroom.lab.v1",
            "status": "error",
            "capture_complete": False,
            "termination_reason": "capture_bootstrap_error",
            "pid": os.getpid(),
            "steps": 0,
            "loss_series": [],
            "step_records": [],
            "env": {},
            "peak_allocated_bytes": None,
            "peak_reserved_bytes": None,
            "peak_alloc_gb": None,
            "peak_reserved_gb": None,
            "snapshot": {"available": False, "trace_count": None},
            "snapshot_trace_count": None,
            "oom": None,
            "errors": [{"stage": "sitecustomize", "type": type(exc).__name__, "message": str(exc)}],
        }
        try:
            base = Path(os.environ.get("HEADROOM_OUTPUT_DIR", "/out"))
            base.mkdir(parents=True, exist_ok=True)
            error_path = base / f"capture-bootstrap-error-{os.getpid()}.json"
            error_path.write_text(json.dumps(details, indent=2) + "\n")
            # Never replace a result produced by an earlier/primary process.
            try:
                with (base / "result.json").open("x") as target:
                    json.dump(details, target, indent=2)
            except FileExistsError:
                pass
        except BaseException as write_error:  # noqa: BLE001 - startup must fail closed
            print(f"Capture error artifact unavailable: {write_error}", file=sys.stderr)
        traceback.print_exception(exc, file=sys.stderr)
        sys.stderr.flush()
        sys.stdout.flush()
        os._exit(78)
