"""Phase-0 scripts share the self-contained Lab contract without launching a workload."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.lab.runtime_image import IMAGE

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    (tmp_path / "scenarios/s_fixture").mkdir(parents=True)
    (tmp_path / "scenarios/s_fixture/train.py").write_text("print(1)\n")
    (tmp_path / "scenarios/INDEX.yaml").write_text(json.dumps({"scenarios": [{"id": "s_fixture"}]}))
    (tmp_path / "repos").mkdir()
    (tmp_path / "repos/nanogpt.yaml").write_text(json.dumps({"id": "nanogpt"}))
    (tmp_path / "reports").mkdir()
    return tmp_path


def metadata():
    return {"image": IMAGE, "image_id": "sha256:" + "a" * 64, "uv_lock_sha256": "b" * 64}


def test_gpu_baseline_commands_do_not_mount_host_venv(project, monkeypatch):
    module = load("check_gpu_baselines")
    monkeypatch.setattr(module, "ROOT", project)
    args = module.docker_command({"id": "s_fixture"}, "offline-no-launch", metadata()["image_id"])
    assert metadata()["image_id"] in args
    assert not any(".venv" in arg or "dst=/opt/venv" in arg for arg in args)
    assert any("dst=/cases,readonly" in arg for arg in args)


def test_gpu_baseline_check_only_records_verified_image_without_dispatch(project, monkeypatch):
    module = load("check_gpu_baselines")
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(sys, "argv", ["baseline", "--case", "s_fixture", "--check-only"])
    monkeypatch.setattr(module, "gpu_state", lambda: {"ready": True, "reason": "fixture"})
    seen = []

    def check(root, **kwargs):
        seen.append(root)
        return metadata()

    monkeypatch.setattr(module, "require_runtime_image", check)
    monkeypatch.setattr(
        module, "run_case", lambda *a, **k: pytest.fail("Check-only must not launch")
    )
    assert module.main() == 0
    report = json.loads(next((project / "reports").glob("gpu-baseline-*.json")).read_text())
    assert seen == [project]
    assert report["runtime_image"] == metadata() and report["workloads_launched"] == 0
    assert report["image"] == metadata()["image_id"]


def test_cpu_smoke_uses_verified_digest_and_never_mounts_host_venv(project, monkeypatch):
    module = load("check_scenario_smoke")
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(
        sys, "argv", ["smoke", "--scenario", "s_fixture", "--report", "reports/fixture.json"]
    )
    monkeypatch.setattr(module, "require_runtime_image", lambda *a, **k: metadata())
    calls = []

    def fake(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="fixture", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake)
    assert module.main() == 0
    launch = calls[0]
    assert metadata()["image_id"] in launch and "--gpus" not in launch
    assert not any(".venv" in arg or "dst=/opt/venv" in arg for arg in launch)
    assert calls[1][:3] == ["docker", "rm", "-f"]
    assert json.loads((project / "reports/fixture.json").read_text())["runtime_image"] == metadata()


def test_cpu_smoke_missing_image_stops_before_container(project, monkeypatch):
    module = load("check_scenario_smoke")
    monkeypatch.setattr(module, "ROOT", project)
    monkeypatch.setattr(sys, "argv", ["smoke", "--scenario", "s_fixture"])

    def missing(*args, **kwargs):
        raise RuntimeError("Rebuild fixture image")

    monkeypatch.setattr(module, "require_runtime_image", missing)
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: pytest.fail("Must not launch"))
    with pytest.raises(RuntimeError, match="Rebuild"):
        module.main()
    assert not list((project / "reports").iterdir())
