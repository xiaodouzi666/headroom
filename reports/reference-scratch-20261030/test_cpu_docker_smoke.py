"""One authorized CPU infrastructure run; not fixed-nine acceptance."""

import hashlib
import json
from pathlib import Path

from headroom.lab.runner import run_script

ROOT = Path("/home/xiaodouzi/workspace/headroom")
DIRECTORY = ROOT / "reports/reference-scratch-20261030"


def test_cpu_docker_reference_socket_lifetime_and_bounded_artifact_export(tmp_path):
    script = ROOT / "scenarios/s4_loss_accumulation_graph/train.py"
    result = run_script(
        script,
        script_args=["--tiny", "--steps", "3", "--device", "cpu", "--seed", "1337"],
        run_root=tmp_path / "lab",
        max_steps=3,
        max_seconds=45,
        seed=1337,
        device="cpu",
        reference_offload_bytes=8 * 1024**2,
        reference_offload_disk_bytes=16 * 1024**2,
    )
    record = {
        "scope": "authorized_tiny_CPU_Docker_infrastructure_only_not_acceptance",
        "script": str(script),
        "source_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        "result": result,
        "expected_spill": False,
        "reason": "CPU tensors do not enter CUDA saved-tensor spill; this checks socket/lifecycle/export only.",
        "provider_calls": 0,
        "fixed_nine_score_changed": False,
    }
    (DIRECTORY / "cpu-docker-smoke.json").write_text(json.dumps(record, indent=2) + "\n")
    assert result["status"] == "completed", result
    assert result["steps"] == 3
    assert result["reference_offload"]["request_verified"] is True
    assert result["reference_offload"]["disk"]["storage_backend"] == "host_broker"
    assert result["reference_scratch"]["cleanup_verified"] is True
    assert result["reference_scratch"]["peak_reserved_bytes"] == 0
    assert result["reference_scratch"]["live_reserved_bytes"] == 0
    assert result["reference_scratch"]["live_objects"] == 0
    assert result["execution"]["artifact_quota_bytes"] == 512 * 1024**2
    assert result["execution"]["artifact_export"]["export_verified"] is True
    assert result["execution"]["cleanup_verified"] is True
    assert result["execution"]["artifact_cleanup"]["cleanup_verified"] is True
    assert not Path(result["reference_scratch"]["socket_path"]).exists()
