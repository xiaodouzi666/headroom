"""Portable image contract and build context checks; no Docker, network or credentials."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom.lab.runtime_image import (
    CONTRACT,
    CONTRACT_LABEL,
    IMAGE,
    LOCK_LABEL,
    lock_digest,
    require_runtime_image,
    validate_runtime_image,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "headroom_build_image", ROOT / "scripts/build_lab_image.py"
)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
REQUIREMENTS = (
    "--index-url https://pypi.org/simple\nfixture-package==1.0 \\\n    --hash=sha256:"
    + "a" * 64
    + "\n"
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Image contract tests must not contact the network")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "uv.lock").write_text("version=1\n")
    (tmp_path / "lab-image").mkdir()
    for name in ("Dockerfile", "verify_runtime.py"):
        (tmp_path / "lab-image" / name).write_bytes((ROOT / "lab-image" / name).read_bytes())
    # Deliberately incompatible/missing host venv: build preparation never touches it.
    (tmp_path / ".venv").symlink_to(tmp_path / "missing-conda-env", target_is_directory=True)
    (tmp_path / ".env").write_text("fixture-secret-must-not-enter-context")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/private.txt").write_text("fixture-private-run")
    return tmp_path


def export(command, **kwargs):
    assert "--frozen" in command and "--offline" in command
    assert "--no-dev" in command and "--no-emit-project" in command
    assert set(kwargs["env"]) == {
        "PATH",
        "HOME",
        "LANG",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "UV_PYTHON_DOWNLOADS",
        "TMPDIR",
    }
    assert kwargs["env"]["UV_PYTHON_DOWNLOADS"] == "never"
    return SimpleNamespace(returncode=0, stdout=REQUIREMENTS)


def test_context_is_exact_allowlist_and_retained_without_host_venv(project):
    folder, manifest = builder.prepare_context(project, uv="fake-uv", run=export)
    assert folder.is_relative_to(project / ".cache/lab-build")
    assert {p.name for p in folder.iterdir()} == builder.CONTEXT_FILES
    assert manifest["uv_lock_sha256"] == lock_digest(project)
    assert manifest["locked_package_lines"] == 1
    assert (folder / "context.json").is_file()
    contents = b"\n".join(p.read_bytes() for p in folder.iterdir())
    assert b"fixture-secret" not in contents and b"fixture-private-run" not in contents
    assert (folder / ".dockerignore").read_text().startswith("*\n")
    assert "!context.json" not in (folder / ".dockerignore").read_text()
    assert "--require-hashes" in (folder / "Dockerfile").read_text()
    assert "--only-binary=:all:" in (folder / "Dockerfile").read_text()


@pytest.mark.parametrize(
    "requirements",
    [
        "fixture>=1\n",
        "fixture==1\n",
        "-e /host/project\n",
        "-r /host/.env\n",
        "--extra-index-url https://unreviewed.invalid/private\n" + REQUIREMENTS,
        "fixture @ file:///host/private.whl --hash=sha256:" + "a" * 64,
    ],
)
def test_unlocked_or_unreviewed_export_never_becomes_context(project, requirements):
    def invalid(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=requirements)

    with pytest.raises(ValueError):
        builder.prepare_context(project, run=invalid)
    assert not (project / ".cache/lab-build").exists()


def test_marker_and_multiple_hashes_are_preserved():
    requirements = (
        'fixture==1.2 ; python_full_version < "3.13" \\\n --hash=sha256:'
        + "a" * 64
        + " \\\n --hash=sha256:"
        + "b" * 64
        + "\n"
    )
    assert builder.validate_requirements(requirements) == 1


def test_changed_lock_during_export_stops_build(project):
    def changed(*args, **kwargs):
        (project / "uv.lock").write_text("version=2\n")
        return SimpleNamespace(returncode=0, stdout=REQUIREMENTS)

    with pytest.raises(RuntimeError, match="changed"):
        builder.prepare_context(project, run=changed)
    assert not (project / ".cache/lab-build").exists()


def test_symlink_build_input_is_not_copied(project):
    path = project / "lab-image/Dockerfile"
    path.unlink()
    path.symlink_to(project / ".env")
    with pytest.raises(ValueError, match="regular"):
        builder.prepare_context(project, run=export)
    assert not any(p.name == "Dockerfile" for p in (project / ".cache/lab-build").glob("*/*"))


def inspection(digest):
    return {"id": "sha256:" + "b" * 64, "labels": {CONTRACT_LABEL: CONTRACT, LOCK_LABEL: digest}}


def test_runtime_preflight_inspects_metadata_without_launch_or_pull(project, monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[:3] == ["docker-fixture", "image", "inspect"]
        assert IMAGE in command and "run" not in command and "pull" not in command
        return SimpleNamespace(returncode=0, stdout=json.dumps(inspection(lock_digest(project))))

    monkeypatch.setattr("headroom.lab.runtime_image.subprocess.run", run)
    result = require_runtime_image(
        project, executable="docker-fixture", environment={"PATH": "/bin"}
    )
    assert result["runtime_contract"] == CONTRACT and len(calls) == 1


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"id": "sha256:" + "b" * 64, "labels": {}},
        inspection("old-lock"),
        {**inspection("a" * 64), "id": "bad-image-id"},
    ],
)
def test_missing_old_or_stale_image_contract_is_actionable(document):
    with pytest.raises(RuntimeError):
        validate_runtime_image(document, "a" * 64)


@pytest.mark.parametrize("outcome", ["missing", "invalid_json", "timeout"])
def test_inspection_errors_do_not_pull_or_echo_raw_docker_output(project, monkeypatch, outcome):
    def run(*args, **kwargs):
        if outcome == "timeout":
            raise subprocess.TimeoutExpired("fixture", 15)
        return SimpleNamespace(
            returncode=1 if outcome == "missing" else 0, stdout="fixture-sensitive-output"
        )

    monkeypatch.setattr("headroom.lab.runtime_image.subprocess.run", run)
    with pytest.raises(RuntimeError) as caught:
        require_runtime_image(project, executable="docker-fixture", environment={})
    assert "build_lab_image.sh" in str(caught.value)
    assert "sensitive" not in str(caught.value)


def test_build_wrapper_uses_synced_project_python_without_dotenv_or_system_python(tmp_path):
    uv = tmp_path / "uv"
    uv.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n")
    uv.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text("#!/bin/sh\nexit 99\n")
    python.chmod(0o755)
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/build_lab_image.sh"), "--prepare-only"],
        env={"PATH": str(tmp_path) + ":/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        "run",
        "--no-env-file",
        "--frozen",
        "--no-sync",
        "--offline",
        "python",
        "scripts/build_lab_image.py",
        "--prepare-only",
    ]
