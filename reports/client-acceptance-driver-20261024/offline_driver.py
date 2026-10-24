"""Retained independent guards for offline acceptance tests and one real-capture preparation."""

import builtins
import hashlib
import io
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
mode = sys.argv[1]
denied_attempts = []


def deny_network(*args, **kwargs):
    denied_attempts.append("network")
    raise RuntimeError("External DNS/INET access forbidden by independent acceptance driver")


socket.getaddrinfo = deny_network
socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network


def guarded(original):
    def check(path, *args, **kwargs):
        if (
            isinstance(path, (str, bytes, os.PathLike))
            and Path(os.fsdecode(path)).absolute() == ROOT / ".env"
        ):
            denied_attempts.append("real_env")
            raise RuntimeError(
                "Real credential file access forbidden by independent acceptance driver"
            )
        return original(path, *args, **kwargs)

    return check


builtins.open = guarded(builtins.open)
io.open = guarded(io.open)
os.open = guarded(os.open)
started = time.monotonic()
if mode == "test":
    import pytest

    code = pytest.main(["-q", "tests/test_client_acceptance.py", "tests/test_runtime_budget.py"])
    receipt = {
        "mode": mode,
        "exit_code": code,
        "external_access_attempts": denied_attempts,
        "elapsed_seconds": time.monotonic() - started,
    }
    Path(__file__).with_name("offline-test-summary.json").write_text(
        json.dumps(receipt, indent=2) + "\n"
    )
    raise SystemExit(code)
if mode not in {"prepare", "verify"}:
    raise ValueError("Expected test, prepare or verify")
from headroom.acceptance.client import prepare_client_acceptance
from headroom.acceptance.common import read_json
from headroom.acceptance.long_evidence import verify_long_evidence

capture = (
    ROOT
    / "runs/evaluation/baselines/20261024T023317672107Z-69b2d798/lab/b4b14202cf304cf7838b07bb16649942"
)
output = ROOT / "runs/acceptance/client/20261024-offline-s2-v1"
document = (
    prepare_client_acceptance(output, capture=capture)
    if mode == "prepare"
    else read_json(output / "prepared.json")
)
row = document["cases"]["ultra_200k"]
verified = False
if row["status"] == "ready":
    text = verify_long_evidence(row, output / "ultra_200k")
    verified = hashlib.sha256(text.encode()).hexdigest() == row["files"]["evidence.txt"]["sha256"]
receipt = {
    "mode": "offline_" + mode + "_existing_real_capture",
    "output": str(output.relative_to(ROOT)),
    "capture": str(capture.relative_to(ROOT)),
    "case_status": row["status"],
    "accepted": False,
    "live_executed": False,
    "api_calls": 0,
    "gpu_tasks": 0,
    "external_access_attempts": denied_attempts,
    "source_revalidation_passed": verified,
    "elapsed_seconds": time.monotonic() - started,
    "prepared_manifest_sha256": hashlib.sha256((output / "prepared.json").read_bytes()).hexdigest(),
    "ultra": {
        key: row.get(key)
        for key in (
            "reason",
            "selected_snapshot",
            "record_count",
            "duplicate_records_omitted",
            "tokenizer",
            "evidence_content_tokens_local_estimate",
            "evidence_with_locators_tokens_local_estimate",
            "provider_prompt_tokens",
            "provider_token_bound",
        )
    },
}
Path(__file__).with_name(
    "real-capture-" + ("preparation" if mode == "prepare" else "revalidation") + ".json"
).write_text(json.dumps(receipt, indent=2) + "\n")
print(json.dumps(receipt, indent=2))
raise SystemExit(0 if verified else 2)
