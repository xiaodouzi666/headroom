"""One full-size original reference infrastructure check; never a repair result."""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    os.umask(0o077)
    from headroom.acceptance.final48_repair import verify_preparation
    from headroom.lab.runner import run_script

    prep = ROOT / "runs/final48-repair-preparation-20261030-r16/preparation.json"
    verify_preparation(
        prep, expected_sha256="c86a7b880ee1d0c8e6f8940399b9c7794b1e0c68baff99687120c7e40b744f39"
    )
    q = json.loads((ROOT / ".cache/repair-followup-20261030-v3/r16-proposal.json").read_text())[
        "requests"
    ]["fixed9-s4_loss_accumulation_graph"]
    assert q["script_args"] == [] and q["max_steps"] == 20 and q["seed"] == 1337
    ref = q["numerical_reference"]
    assert ref == {
        "strategy": "original_saved_tensor_offload",
        "cpu_saved_tensor_limit_bytes": 17179869184,
        "disk_saved_tensor_limit_bytes": 68719476736,
        "max_seconds": 480,
    }
    h = json.load(urllib.request.urlopen("http://127.0.0.1:8766/api/health", timeout=10))
    assert (
        not h["run_submissions"]["enabled"]
        and not h["queue"]["running"]
        and h["queue"]["pending"] == 0
        and h["queue"]["preparing"] == 0
    )
    gpu = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    assert not gpu.stdout.strip()
    before = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "headroom").rglob("*.py")
    }
    started = time.monotonic()
    result = run_script(
        q["script"],
        source_root=q["source_root"],
        script_args=q["script_args"],
        run_root=ROOT / "runs/research/full-reference-storage-20261030-v2",
        max_steps=20,
        max_seconds=480,
        seed=1337,
        device="cuda",
        reference_offload_bytes=ref["cpu_saved_tensor_limit_bytes"],
        reference_offload_disk_bytes=ref["disk_saved_tensor_limit_bytes"],
    )
    after = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "headroom").rglob("*.py")
    }
    report = {
        "at": datetime.now(UTC).isoformat(),
        "scope": "one full-size original workload saved-tensor storage infrastructure check; not an automatic repair or fixed-nine score",
        "elapsed_seconds": time.monotonic() - started,
        "source_pins_unchanged": before == after,
        "model_calls": 0,
        "fixed_nine_score_changed": False,
        "result": result,
    }
    out = ROOT / "reports/reference-scratch-20261030/full-reference-smoke-v2.json"
    assert not out.exists()
    out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "steps": result.get("steps"),
                "run_id": result.get("run_id"),
                "source_pins_unchanged": before == after,
                "cleanup_verified": result.get("cleanup_verified"),
                "host_scratch": result.get("reference_scratch"),
                "request_verified": result.get("reference_offload", {}).get("request_verified"),
                "reason": result.get("reason"),
            }
        )
    )
    assert before == after
    assert result.get("cleanup_verified") is True
    assert result.get("gpu_after", {}).get("processes") == []


if __name__ == "__main__":
    main()
