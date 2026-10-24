import io
import tarfile

import pytest

from headroom.repository import _extract, parse_python_command, validate_repository


@pytest.mark.parametrize(
    "repo",
    [
        "file:///tmp/a",
        "https://token@github.com/a/b",
        "https://github.com/a/b?token=a",
        "https://example.com/a/b",
        "https://github.com/a/b;touch",
        "git@github.com:a/b",
    ],
)
def test_only_public_https(repo):
    with pytest.raises(ValueError):
        validate_repository(repo, "a" * 40)


def test_exact_ref_and_command():
    assert validate_repository("https://github.com/a/b", "a" * 40).endswith("b.git")
    for ref in ["main", "-x", "A" * 40]:
        with pytest.raises(ValueError):
            validate_repository("https://github.com/a/b", ref)
    assert parse_python_command("python train.py --batch=2") == ("train.py", ("--batch=2",))
    for cmd in ["bash train.py", "python -c pass", "python ../train.py", "python train.py | cat"]:
        with pytest.raises(ValueError):
            parse_python_command(cmd)


@pytest.mark.parametrize(
    "name,kind",
    [
        ("../escape.py", tarfile.REGTYPE),
        ("/escape.py", tarfile.REGTYPE),
        ("link.py", tarfile.SYMTYPE),
        ("link.py", tarfile.LNKTYPE),
    ],
)
def test_archive_escape(tmp_path, name, kind):
    archive = tmp_path / "source.tar"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo(name)
        info.type = kind
        if kind != tarfile.REGTYPE:
            info.linkname = "/etc/passwd"
        tar.addfile(info)
    with pytest.raises(ValueError):
        _extract(archive, tmp_path / "source")
    assert not (tmp_path / "escape.py").exists()


def test_extract_does_not_execute_source(tmp_path):
    archive = tmp_path / "source.tar"
    data = b"raise RuntimeError('must not execute')"
    with tarfile.open(archive, "w") as tar:
        info = tarfile.TarInfo("train.py")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    _extract(archive, tmp_path / "source")
    assert (tmp_path / "source/train.py").read_bytes() == data


def test_git_commands_disable_cached_repo_hooks_and_bound_file_growth(tmp_path, monkeypatch):
    import subprocess

    from headroom import repository

    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "fixture", "")

    monkeypatch.setattr(repository.subprocess, "run", run)
    assert repository._git(tmp_path, "status", "--porcelain") == "fixture"
    args, options = calls[0]
    assert "prlimit" in args[0] and "--fsize=268435456" in args
    assert "core.fsmonitor=false" in args and "fetch.unpackLimit=0" in args
    assert options["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert options["env"]["HOME"] == "/nonexistent"
    assert "NEBIUS_API_KEY" not in options["env"]


def test_clean_install_publishes_fixed_hash_policy_baseline_without_network(tmp_path, monkeypatch):
    import hashlib

    from headroom import repository
    from headroom.lab.runner import PROJECT_ROOT
    from headroom.verify.policy import NANOGPT_HASHES

    baseline = PROJECT_ROOT / ".cache/upstream/nanoGPT"
    payloads = {name: (baseline / name).read_bytes() for name in NANOGPT_HASHES}
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(repository, "PROJECT_ROOT", project)

    def git(directory, *args):
        if args[0] == "archive":
            output = next(
                arg.removeprefix("--output=") for arg in args if arg.startswith("--output=")
            )
            with tarfile.open(output, "w") as tar:
                for name, payload in payloads.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    tar.addfile(info, io.BytesIO(payload))
        return repository.NANOGPT_REF if args[:2] == ("rev-parse", "FETCH_HEAD") else ""

    monkeypatch.setattr(repository, "_git", git)
    prepared = repository.prepare_repository(
        repository.NANOGPT_URL,
        repository.NANOGPT_REF,
        "python train.py --batch_size=32",
        destination=project / "prepared",
    )
    assert prepared.source_profile == "pinned_nanogpt"
    published = project / ".cache/reviewed/nanogpt" / repository.NANOGPT_REF
    for name, digest in NANOGPT_HASHES.items():
        assert hashlib.sha256((published / name).read_bytes()).hexdigest() == digest
    repository._publish_reviewed_nanogpt(prepared.source_root)  # idempotent; never overwrites
    victim = published / "train.py"
    victim.chmod(0o600)
    victim.write_text("changed baseline")
    with pytest.raises(ValueError, match="refusing replacement"):
        repository._publish_reviewed_nanogpt(prepared.source_root)
    assert victim.read_text() == "changed baseline"
