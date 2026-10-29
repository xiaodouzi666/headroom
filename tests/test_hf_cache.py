"""Offline cache integrity and real Docker read-only mount, with CPU only."""

import hashlib
import json
import uuid

import pytest

from headroom.lab import docker
from headroom.lab.cache import validated_hf_cache
from headroom.lab.envs import container_environment
from headroom.lab.runner import PROJECT_ROOT


def make_cache(root):
    cache = root / ".cache/hf-reviewed"
    model = cache / "random-model"
    model.mkdir(parents=True)
    config = model / "config.json"
    config.write_text(json.dumps({"model_type": "gpt2", "n_layer": 1, "n_embd": 16, "n_head": 2}))
    (cache / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    "random-model/config.json": hashlib.sha256(config.read_bytes()).hexdigest()
                },
            }
        )
    )
    return cache


def test_cache_absent_means_no_mount_and_no_creation(tmp_path):
    assert validated_hf_cache(tmp_path) is None
    assert not (tmp_path / ".cache").exists()


def test_manifest_verified_cache_is_accepted_without_mutation(tmp_path):
    cache = make_cache(tmp_path)
    previous = {p: p.read_bytes() for p in cache.rglob("*") if p.is_file()}
    assert validated_hf_cache(tmp_path) == cache
    assert previous == {p: p.read_bytes() for p in previous}


@pytest.mark.parametrize("kind", ["token", "hash", "missing", "link", "dir-link", "pickle"])
def test_unreviewed_or_corrupted_cache_is_rejected(tmp_path, kind):
    cache = make_cache(tmp_path)
    config = cache / "random-model/config.json"
    if kind == "token":
        (cache / "token").write_text("test-canary-not-a-real-secret")
    elif kind == "hash":
        config.write_text("{}")
    elif kind == "missing":
        config.unlink()
    elif kind == "link":
        config.unlink()
        config.symlink_to(cache / "manifest.json")
    elif kind == "dir-link":
        (cache / "other").symlink_to(cache / "random-model", target_is_directory=True)
    else:
        (cache / "weights.pickle").write_bytes(b"not executable")
        (cache / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "files": {"weights.pickle": hashlib.sha256(b"not executable").hexdigest()},
                }
            )
        )
    with pytest.raises((ValueError, OSError)):
        validated_hf_cache(tmp_path)


def test_offline_environment_overrides_host_hf_paths_and_tokens(monkeypatch):
    monkeypatch.setenv("HF_HOME", "/home/user/private-cache")
    monkeypatch.setenv("HF_TOKEN", "test-canary")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    env = container_environment(device="cpu", max_steps=2, max_seconds=20, seed=17)
    assert env["HF_HOME"] == "/tmp/headroom-hf"
    assert env["HF_HUB_CACHE"].startswith("/tmp/") and env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == env["HF_DATASETS_OFFLINE"] == "1"
    assert "HF_TOKEN" not in env and "NEBIUS_API_KEY" not in env


def test_real_docker_reads_local_hf_config_and_cannot_modify_cache(tmp_path):
    # Dedicated synthetic project cache, not the user's HOME or a credential-bearing Hub cache.
    project = tmp_path / "project"
    project.mkdir()
    (project / "headroom").symlink_to(PROJECT_ROOT / "headroom", target_is_directory=True)
    (project / "uv.lock").write_bytes((PROJECT_ROOT / "uv.lock").read_bytes())
    assert not (project / ".venv").exists()
    make_cache(project)
    source, run_dir = (tmp_path / name for name in ("source", "run"))
    output = run_dir / "artifacts"
    for directory in (source, run_dir, output):
        directory.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({"image": docker.IMAGE, "command": ["python"]})
    )
    (source / "check.py").write_text("""import json, os
from pathlib import Path
from transformers import GPT2Config
assert os.environ["HF_HOME"] == "/tmp/headroom-hf"
assert os.environ["HF_HUB_OFFLINE"] == "1"
assert not any(os.environ.get(key) for key in ("HF_TOKEN", "NEBIUS_API_KEY", "TAVILY_API_KEY"))
config = GPT2Config.from_pretrained("/hf-cache/random-model", local_files_only=True)
assert config.n_layer == 1 and config.n_embd == 16
try:
    Path("/hf-cache/random-model/config.json").write_text("{}")
except OSError:
    readonly = True
else:
    readonly = False
assert readonly
Path(os.environ["HF_HOME"]).mkdir(parents=True, exist_ok=True)
Path(os.environ["HF_HOME"], "scratch").write_text("ephemeral")
try:
    GPT2Config.from_pretrained("headroom/not-downloaded", local_files_only=True)
except OSError:
    offline_miss = True
else:
    offline_miss = False
assert offline_miss
Path("/out/result.json").write_text(json.dumps({"readonly": readonly, "offline_miss": offline_miss}))
""")
    name = "headroom-lab-" + uuid.uuid4().hex
    args = docker.create_arguments(
        name=name,
        project_root=project,
        source=source,
        output=output,
        device="cpu",
        environment=container_environment(device="cpu", max_steps=2, max_seconds=30, seed=17),
        command=["/opt/venv/bin/python", "/source/check.py"],
    )
    assert any("destination=/hf-cache,readonly" in arg for arg in args)
    result = docker.execute(create_args=args, name=name, run_dir=run_dir, max_seconds=30)
    assert result["cleanup_verified"] and result["state"]["ExitCode"] == 0, result
    assert json.loads((output / "result.json").read_text()) == {
        "readonly": True,
        "offline_miss": True,
    }
    assert validated_hf_cache(project)


def test_mutable_host_hub_cache_is_never_selected_or_mounted(tmp_path, monkeypatch):
    monkeypatch.setattr(
        docker, "require_runtime_image", lambda *args, **kwargs: {"image_id": docker.IMAGE}
    )
    hub = tmp_path / ".cache/huggingface/hub"
    hub.mkdir(parents=True)
    (hub / "version.txt").write_text("1")
    (hub.parent / "token").write_text("offline-canary-not-a-real-token")
    previous = {path: path.read_bytes() for path in hub.parent.rglob("*") if path.is_file()}
    assert validated_hf_cache(tmp_path) is None
    for name in ("headroom", "source", "output"):
        (tmp_path / name).mkdir()
    args = docker.create_arguments(
        name="headroom-lab-" + "a" * 32,
        project_root=tmp_path,
        source=tmp_path / "source",
        output=tmp_path / "output",
        device="cpu",
        environment={},
        command=["/opt/venv/bin/python", "/source/train.py"],
    )
    assert not any("destination=/hf-cache" in value for value in args)
    assert previous == {path: path.read_bytes() for path in previous}
    assert not (tmp_path / ".cache/hf-reviewed").exists()


def test_existing_reviewed_directory_still_requires_its_own_manifest(tmp_path):
    hub = tmp_path / ".cache/huggingface/hub"
    hub.mkdir(parents=True)
    (hub / "version.txt").write_text("1")
    reviewed = tmp_path / ".cache/hf-reviewed"
    reviewed.mkdir()
    with pytest.raises(FileNotFoundError):
        validated_hf_cache(tmp_path)
    assert list(reviewed.iterdir()) == []


def test_validated_reviewed_cache_is_separate_from_host_hub_cache(tmp_path):
    hub = tmp_path / ".cache/huggingface/hub"
    hub.mkdir(parents=True)
    (hub / "version.txt").write_text("1")
    reviewed = make_cache(tmp_path)
    assert validated_hf_cache(tmp_path) == reviewed
    assert reviewed != hub.parent
    assert (hub / "version.txt").read_text() == "1"
