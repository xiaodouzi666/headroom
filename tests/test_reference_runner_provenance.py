"""Host binding refuses a target's downgrade to local reference storage."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from headroom.lab import runner
from headroom.lab.reference_scratch_lifecycle import SOCKET_DESTINATION
from headroom.verify.offload import PROTOCOL, STRATEGY

SCRIPT = Path(__file__).resolve().parents[1] / "scenarios/s4_loss_accumulation_graph/train.py"


@pytest.mark.parametrize(
    "change,expected",
    [
        ("none", True),
        ("local", False),
        ("cpu", False),
        ("unbound", False),
        ("wrong_cap", False),
        ("dirty", False),
        ("live_bytes", False),
        ("live_objects", False),
    ],
)
def test_positive_disk_request_requires_actual_host_broker_branch(
    tmp_path, monkeypatch, change, expected
):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    evidence = {
        "protocol": PROTOCOL,
        "mode": STRATEGY,
        "source_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        "script_args": [],
        "max_saved_bytes": 1024,
        "max_disk_bytes": 2048,
        "backend": "disk",
        "disk": {"storage_backend": "host_broker"},
    }
    host = {
        "schema": "headroom.reference-scratch.v1",
        "request_verified": True,
        "max_bytes": 2048,
        "cleanup_verified": True,
        "live_reserved_bytes": 0,
        "live_objects": 0,
    }
    if change == "local":
        evidence["disk"]["storage_backend"] = "local"
    elif change == "cpu":
        evidence["backend"] = "cpu"
    elif change == "unbound":
        host["request_verified"] = False
    elif change == "wrong_cap":
        host["max_bytes"] = 2049
    elif change == "dirty":
        host["cleanup_verified"] = False
    elif change == "live_bytes":
        host["live_reserved_bytes"] = 1
    elif change == "live_objects":
        host["live_objects"] = 1
    (artifacts / "reference-offload.json").write_text(json.dumps(evidence))
    observed = {}

    def isolated_run(**kwargs):
        observed.update(kwargs)
        return {
            "run_dir": str(tmp_path),
            "target_artifact_dir": str(artifacts),
            "cleanup_verified": True,
            "reference_scratch": copy.deepcopy(host),
        }

    monkeypatch.setattr(runner, "_run", isolated_run)
    result = runner.run_script(
        SCRIPT, reference_offload_bytes=1024, reference_offload_disk_bytes=2048
    )
    assert result["reference_offload"]["request_verified"] is expected
    assert observed["reference_scratch_bytes"] == 2048
    command = observed["command"]
    assert command[command.index("--reference-offload-socket") + 1] == SOCKET_DESTINATION
