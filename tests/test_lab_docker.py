"""Fast checks of source, environment, artifact and cleanup trust boundaries."""

import json
import subprocess

import pytest

from headroom.lab import docker
from headroom.lab.envs import container_environment, validate_allocator
from headroom.lab.runner import (
    copy_source,
    merge_gpu_observations,
    read_artifact_json,
    read_capture,
)


def test_container_environment_does_not_inherit_secrets(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "canary-not-a-real-key")
    monkeypatch.setenv("DOCKER_HOST", "tcp://untrusted.invalid")
    environment = container_environment(device="cpu", max_steps=2, max_seconds=10, seed=1)
    assert "NEBIUS_API_KEY" not in environment
    assert "DOCKER_HOST" not in environment
    assert environment["CUDA_VISIBLE_DEVICES"] == ""


@pytest.mark.parametrize(
    "value",
    [
        "unknown:1",
        "expandable_segments:True;echo",
        "max_split_size_mb:-1",
        "backend:evil",
        "garbage_collection_threshold:1.0",
        "backend:native,backend:native",
    ],
)
def test_allocator_options_reject_unknown_or_invalid_values(value):
    with pytest.raises(ValueError):
        validate_allocator(value)


def test_source_copy_excludes_credentials_symlinks_and_runs(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "train.py").write_text("print('fixture')\n")
    (source / ".env").write_text("not-a-real-key")
    (source / "private.key").write_text("not-a-real-key")
    outside = tmp_path / "outside"
    outside.write_text("outside-canary")
    (source / "linked.py").symlink_to(outside)
    (source / ".venv").mkdir()
    (source / ".venv" / "private.txt").write_text("ignored")
    run_root = source / "test-output"
    run_root.mkdir()
    manifest = copy_source(source, tmp_path / "copied", (run_root,))
    assert list(manifest["files"]) == ["train.py"]
    assert len(manifest["files"]["train.py"]["sha256"]) == 64
    assert not (tmp_path / "copied" / ".env").exists()
    assert not (tmp_path / "copied" / "linked.py").exists()


def test_artifact_json_refuses_symlink_and_large_files(tmp_path):
    regular = tmp_path / "regular.json"
    regular.write_text('{"fixture": true}')
    link = tmp_path / "linked.json"
    link.symlink_to(regular)
    with pytest.raises(OSError):
        read_artifact_json(link)
    with pytest.raises(ValueError):
        read_artifact_json(regular, max_bytes=4)
    assert read_artifact_json(regular) == {"fixture": True}


def test_artifact_json_refuses_nan(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"metric": NaN}')
    with pytest.raises(ValueError):
        read_artifact_json(path)


def test_capture_rejects_bare_success_claim(tmp_path):
    path = tmp_path / "result.json"
    path.write_text(json.dumps({"status": "completed"}))
    with pytest.raises(ValueError):
        read_capture(path)


def test_docker_arguments_mount_only_required_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")
    verified_id = "sha256:" + "a" * 64
    monkeypatch.setattr(
        docker, "require_runtime_image", lambda *args, **kwargs: {"image_id": verified_id}
    )
    for name in ("headroom", "source", "artifacts"):
        (tmp_path / name).mkdir()
    command = docker.create_arguments(
        name="headroom-test",
        project_root=tmp_path,
        source=tmp_path / "source",
        output=tmp_path / "artifacts",
        environment={"PYTHONPATH": "/runtime"},
        command=["/opt/venv/bin/python", "train.py"],
        device="cpu",
    )
    mounts = [command[index + 1] for index, value in enumerate(command) if value == "--mount"]
    assert command[-2:] == [verified_id, "train.py"]
    assert len(mounts) == 3
    assert not any("destination=/opt/venv" in mount or ".venv" in mount for mount in mounts)
    assert not any(f"source={tmp_path}," in mount for mount in mounts)
    assert sum(mount.endswith(",readonly") for mount in mounts) == 2
    assert "--gpus" not in command
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command


def test_cleanup_continues_after_independent_failures(monkeypatch):
    calls = []
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")

    def run(arguments, **kwargs):
        operation = arguments[1]
        calls.append(operation)
        if operation == "stop":
            raise subprocess.TimeoutExpired(arguments, 8)
        if operation == "kill":
            raise OSError("injected failure")
        if operation == "inspect":
            return subprocess.CompletedProcess(
                arguments, 1, "[]\n", "error: no such object: headroom-test\n"
            )
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(docker.subprocess, "run", run)
    result = docker.cleanup_container("headroom-test")
    assert calls == ["stop", "kill", "rm", "inspect"]
    assert result["cleanup_verified"]


@pytest.mark.parametrize(
    "captured,after_available,expected_shared,expected_complete",
    [
        (True, True, True, True),
        (False, True, False, True),
        (False, False, None, False),
        (True, False, True, False),
        (None, True, None, False),
    ],
)
def test_gpu_sampling_preserves_capture_and_unknown_state(
    captured, after_available, expected_shared, expected_complete
):
    before = {"available": True, "processes": []}
    after = {"available": after_available, "processes": []}
    result = merge_gpu_observations("cuda", before, after, captured)
    assert result["shared_gpu"] is expected_shared
    assert result["gpu_observation_complete"] is expected_complete


def test_gpu_sampling_preserves_host_positive_evidence():
    before = {"available": True, "processes": [{"pid": "42"}]}
    after = {"available": False, "processes": []}
    result = merge_gpu_observations("cuda", before, after, False)
    assert result["shared_gpu"] is True
    assert result["gpu_observation_complete"] is False


@pytest.mark.parametrize(
    "returncode,stdout,stderr,absent",
    [
        (1, "[]\n", "error: no such object: headroom-test\n", True),
        (1, "[]\n", "Error response from daemon: No such container: headroom-test\n", True),
        (1, "", "Cannot connect to the Docker daemon", False),
        (1, "[]\n", "error: no such object: other-container\n", False),
        (0, '[{"Name":"/headroom-test"}]', "", False),
    ],
)
def test_cleanup_inspect_accepts_actual_docker29_absence_output(
    monkeypatch, returncode, stdout, stderr, absent
):
    monkeypatch.setattr(docker, "docker_binary", lambda: "/usr/bin/docker")

    def run(arguments, **kwargs):
        if arguments[1] == "inspect":
            assert arguments[2:4] == ["--type", "container"]
            return subprocess.CompletedProcess(arguments, returncode, stdout, stderr)
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(docker.subprocess, "run", run)
    result = docker.cleanup_container("headroom-test")
    assert result["cleanup_verified"] is absent
    assert result["cleanup_inspect"] == {
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }
