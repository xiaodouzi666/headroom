"""CPU-only Docker canaries for false acceptance and timeout cleanup.

GPU telemetry is synthetic here. These tests never validate a GPU scenario and
never expose a GPU to the canary container.
"""

import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase0_gpu", ROOT / "scripts/check_gpu_baselines.py")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)


@pytest.fixture
def cpu_canary(monkeypatch):
    def idle_test_telemetry():
        return {
            "ready": True,
            "inspection_ok": True,
            "pids": [],
            "query_errors": "",
            "scope": "synthetic CPU canary telemetry, not GPU evidence",
        }

    monkeypatch.setattr(BASELINE, "gpu_state", idle_test_telemetry)

    def run(script, directory, *, accelerated_timeout=False):
        def cpu_command(case, name, image):
            return [
                "docker",
                "run",
                "--name",
                name,
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--pids-limit",
                "64",
                "--memory",
                "2g",
                "--cpus",
                "1",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=64m",
                "--mount",
                f"type=bind,src={ROOT / '.venv'},dst=/opt/venv,readonly",
                "--entrypoint",
                "/opt/venv/bin/python",
                image,
                "-c",
                script,
            ]

        monkeypatch.setattr(BASELINE, "docker_command", cpu_command)
        if accelerated_timeout:
            monkeypatch.setattr(
                BASELINE,
                "time",
                SimpleNamespace(monotonic=lambda: time.monotonic() * 30, sleep=time.sleep),
            )
        case = {
            "id": "cpu_canary",
            "expected_mode": "oom",
            "script": "scripts/check_gpu_baselines.py",
        }
        return BASELINE.run_case(case, directory, "headroom-lab:py312-cu124")

    return run


def test_cpu_oom_is_not_cuda_oom(cpu_canary, tmp_path):
    result = cpu_canary('import torch; raise torch.OutOfMemoryError("CPU out of memory")', tmp_path)
    assert result["status"] == "error_or_incomplete_evidence"
    assert not result["observed_check_passed"]
    assert result["cleanup_verified"]
    assert not result["t0_6_accepted"]


def test_timeout_removes_owned_container(cpu_canary, tmp_path):
    result = cpu_canary("import time; time.sleep(120)", tmp_path, accelerated_timeout=True)
    assert result["status"] == "timeout"
    assert not result["observed_check_passed"]
    assert result["cleanup_verified"]
    assert not result["t0_6_accepted"]
