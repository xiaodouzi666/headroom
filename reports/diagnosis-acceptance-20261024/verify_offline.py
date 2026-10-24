"""Owned offline verification receipt: no DNS/INET, credentials, API, or GPU execution."""

import builtins
import contextlib
import hashlib
import io
import json
import os
import socket
from pathlib import Path

ROOT = Path("/home/xiaodouzi/workspace/headroom")
REPORT = ROOT / "reports/diagnosis-acceptance-20261024"
OWNED = (
    "headroom/acceptance/diagnosis.py",
    "scripts/check_diagnosis_acceptance.py",
    "tests/test_diagnosis_acceptance.py",
    "docs/DIAGNOSIS_ACCEPTANCE.md",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


before = {name: digest(ROOT / name) for name in OWNED}


def denied(*args, **kwargs):
    raise AssertionError("Real DNS/INET prohibited during offline acceptance verification")


socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
for module in (builtins, io):
    original = module.open

    def guarded(path, *args, _original=original, **kwargs):
        if isinstance(path, (str, Path)) and Path(path).name.startswith(".env"):
            raise AssertionError("Credential file access prohibited")
        return _original(path, *args, **kwargs)

    module.open = guarded
original_os_open = os.open


def guarded_os_open(path, *args, **kwargs):
    if isinstance(path, (str, Path)) and Path(path).name.startswith(".env"):
        raise AssertionError("Credential descriptor access prohibited")
    return original_os_open(path, *args, **kwargs)


os.open = guarded_os_open

import pytest

with (
    (REPORT / "pytest-final.log").open("w") as log,
    contextlib.redirect_stdout(log),
    contextlib.redirect_stderr(log),
):
    code = pytest.main(
        ["-q", "tests/test_diagnosis_acceptance.py", "tests/test_diagnose_schema.py", "--tb=short"]
    )
if code:
    raise SystemExit(code)

from headroom.acceptance.diagnosis import SCENARIO_IDS, prepare_diagnosis_acceptance

baseline = json.loads((ROOT / "reports/evaluation-baselines-20261024.json").read_text())
captures = {
    row["scenario_id"]: row["run_dir"]
    for row in baseline["rows"]
    if row["scenario_id"] in SCENARIO_IDS
}
prepared_dir = ROOT / "runs/acceptance/diagnosis-prepared-20261024-v2"
prepared = prepare_diagnosis_acceptance(captures, prepared_dir)
after = {name: digest(ROOT / name) for name in OWNED}
receipt = {
    "status": "offline_verified"
    if before == after and prepared["ready_count"] == 8
    else "incomplete",
    "live_accepted": False,
    "api_calls": 0,
    "new_gpu_runs": 0,
    "credential_reads": 0,
    "dns_inet_blocked": True,
    "env_file_access_blocked": True,
    "pytest_exit_code": int(code),
    "pytest_log": str(REPORT / "pytest-final.log"),
    "owned_sources_unchanged": before == after,
    "source_sha256": after,
    "preparation": str(prepared_dir / "preparation.json"),
    "preparation_sha256": digest(prepared_dir / "preparation.json"),
    "rows": [
        {
            key: row.get(key)
            for key in (
                "scenario_id",
                "status",
                "capture",
                "evidence_tokens",
                "required_saving_gb",
                "evidence_quality",
            )
        }
        | {
            "truth_status": row["truth"]["truth_status"],
            "scoreable_category": row["truth"]["scoreable_category"],
        }
        for row in prepared["rows"]
    ],
    "limits": "Prepared model requests only; no profile activation, budget alteration, key/API/GPU access.",
    "development_history": [
        "Initial 23 and expanded 25 tests passed.",
        "Required-reduction revision briefly failed 14/28 tests because revalidation omitted the new field; fixed without any live execution.",
        "Then 28 and 31 tests passed.",
        "Original real-capture preparation is preserved but superseded by v2.",
    ],
}
(REPORT / "receipt.json").write_text(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
print(
    json.dumps(
        {
            "status": receipt["status"],
            "ready_count": prepared["ready_count"],
            "accepted": False,
            "receipt": str(REPORT / "receipt.json"),
        }
    )
)
