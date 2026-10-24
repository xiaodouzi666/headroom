"""Apply the full-suite guards to the focused API isolation regression, including spawn."""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
GUARD = ROOT / ".cache/setup/run_full_guarded.py"
namespace = {"__name__": "headroom_offline_guards"}
exec(compile(GUARD.read_text(), str(GUARD), "exec"), namespace)  # noqa: S102 - reviewed fixed local guard; also installed in spawn children.
os.open = namespace["safe_open"](os.open)


if __name__ == "__main__":
    import pytest

    started = time.monotonic()
    code = pytest.main(
        ["-q", "tests/test_api.py", "tests/test_api_deadline.py", "tests/test_availability.py"]
    )
    Path(__file__).with_name("api-isolation-receipt.json").write_text(
        json.dumps(
            {
                "exit_code": code,
                "elapsed_seconds": time.monotonic() - started,
                "test_source_sha256": hashlib.sha256(
                    (ROOT / "tests/test_api.py").read_bytes()
                ).hexdigest(),
                "guard_driver_sha256": hashlib.sha256(GUARD.read_bytes()).hexdigest(),
                "scope": "API fixtures use temporary project root and copy only public example catalogue/scripts",
                "production_health_changed": False,
                "real_profile_modified": False,
                "previous_full_status": "interrupted_for_confirmed_live_failure_fix",
                "previous_full_summary": "1 failed, 719 passed; configured=false fixture relied on real profile absence",
            },
            indent=2,
        )
        + "\n"
    )
    raise SystemExit(code)
