"""Pinned public repositories; fetch data only, never execute repository setup."""

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from headroom.lab.envs import HOST_ENV
from headroom.lab.runner import PROJECT_ROOT, PYTHON_COMMANDS, copy_source
from headroom.verify.policy import NANOGPT_HASHES, nanogpt_cli

NANOGPT_URL = "https://github.com/karpathy/nanoGPT.git"
NANOGPT_REF = "3adf61e154c3fe3fca428ad6bc3818b27a3b8291"
GIT_ENV = {
    **HOST_ENV,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_LFS_SKIP_SMUDGE": "1",
}
MAX_ARCHIVE = 256 * 1024 * 1024


@dataclass(frozen=True)
class PreparedRepository:
    source_root: Path
    script: Path
    script_args: tuple[str, ...]
    source_profile: str | None
    metadata: dict


def validate_repository(repo: str, ref: str) -> str:
    if not isinstance(repo, str) or not re.fullmatch(
        r"https://github[.]com/[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo
    ):
        raise ValueError(
            "Use a public HTTPS github.com repository URL without credentials or query"
        )
    if not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{40}", ref):
        raise ValueError("Repository ref must be an exact lowercase 40-character commit SHA")
    return repo if repo.endswith(".git") else repo + ".git"


def parse_python_command(command: str | list[str]) -> tuple[str, tuple[str, ...]]:
    parts = shlex.split(command) if isinstance(command, str) else list(command)
    if len(parts) < 2 or parts[0] not in {"python", "python3"}:
        raise ValueError("Repository command must be python relative_script.py followed by argv")
    path = PurePosixPath(parts[1])
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in parts[1]
        or not parts[1].endswith(".py")
        or parts[1].startswith("-")
        or any("\x00" in part or "\n" in part or "\r" in part for part in parts)
    ):
        raise ValueError("Invalid Python script or command argument")
    if any(part in {";", "&&", "||", "|", ">", ">>", "<"} for part in parts):
        raise ValueError("Shell operators are not repository arguments")
    return str(path), tuple(parts[2:])


@dataclass(frozen=True)
class WatchCommand:
    kind: str
    argv: tuple[str, ...]
    python_flags: tuple[str, ...] = ()
    script: str | None = None
    script_args: tuple[str, ...] = ()
    capture_expected: bool = True
    repair_supported: bool = False
    repair_reason: str | None = None


def parse_watch_command(command) -> WatchCommand:
    """Classify argv without executing code or changing interpreter semantics.

    The stricter repository parser remains unchanged. Arbitrary commands are
    observation-only and resolve solely inside the Docker image/source mounts.
    """
    from collections.abc import Sequence

    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
        raise TypeError("Watch expects argv, not a shell string")
    if (
        not command
        or len(command) > 256
        or any(not isinstance(arg, str) or "\x00" in arg for arg in command)
        or not command[0]
        or sum(len(arg.encode("utf-8")) for arg in command) > 65536
    ):
        raise ValueError("Watch argv must fit 256 entries and 64 KiB without NUL bytes")
    argv = tuple(command)
    if argv[0] not in PYTHON_COMMANDS:
        return WatchCommand("command", argv, repair_reason="COMMAND_REPAIR_UNSUPPORTED")
    flags, index, capture = [], 1, True
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            break
        if token == "-" or not token.startswith("-"):
            break
        if token in {"-c", "-m"} or token.startswith(("-c", "-m")):
            kind = "python_inline" if token.startswith("-c") else "python_module"
            return WatchCommand(
                kind,
                argv,
                tuple(flags),
                capture_expected=capture,
                repair_reason=kind.upper() + "_REPAIR_UNSUPPORTED",
            )
        flags.append(token)
        if token in {"-W", "-X", "--check-hash-based-pycs"}:
            index += 1
            if index < len(argv):
                flags.append(argv[index])
        elif token.startswith("-") and not token.startswith("--"):
            # These options suppress sitecustomize or ignore its PYTHONPATH.
            if any(letter in token[1:] for letter in "EIS"):
                capture = False
        index += 1
    if index >= len(argv) or argv[index] == "-":
        return WatchCommand(
            "python_stdin_or_option",
            argv,
            tuple(flags),
            capture_expected=capture,
            repair_reason="NO_SCRIPT_REPAIR_ENTRYPOINT",
        )
    script, arguments = argv[index], argv[index + 1 :]
    path = PurePosixPath(script)
    if path.is_absolute() or ".." in path.parts or "\\" in script or path.suffix != ".py":
        reason = "SCRIPT_OUTSIDE_REPAIR_SOURCE"
    elif len(arguments) > 100:
        reason = "REPAIR_ARGV_LIMIT"
    elif any(not flag.startswith("-") or any(c not in "uBs" for c in flag[1:]) for flag in flags):
        reason = "INTERPRETER_FLAGS_REQUIRE_REPLAY"
    else:
        reason = None
    # -u/-B/-s exactly match fixed Lab PYTHONUNBUFFERED/PYTHONDONTWRITEBYTECODE/
    # PYTHONNOUSERSITE. All other flags stay observable but cannot be dropped by fix.
    return WatchCommand(
        "python_script",
        argv,
        tuple(flags),
        str(path),
        tuple(arguments),
        capture,
        reason is None,
        reason,
    )


def _git(directory: Path, *args: str) -> str:
    limiter = shutil.which("prlimit", path=HOST_ENV["PATH"])
    if limiter is None:
        raise ValueError("Bounded repository preparation requires Linux prlimit")
    result = subprocess.run(
        [
            limiter,
            "--fsize=" + str(MAX_ARCHIVE),
            "--",
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "fetch.unpackLimit=0",
            "-c",
            "credential.helper=",
            "-c",
            "protocol.file.allow=never",
            "-c",
            "protocol.ext.allow=never",
            "-c",
            "http.followRedirects=false",
            "-C",
            str(directory),
            *args,
        ],
        env=GIT_ENV,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError("Pinned repository Git operation failed (details withheld)")
    return result.stdout.strip()


def _extract(archive: Path, output: Path) -> None:
    output.mkdir(mode=0o700)
    total, names = 0, set()
    with tarfile.open(archive, "r:") as tar:
        for index, member in enumerate(tar):
            path = PurePosixPath(member.name)
            if (
                index >= 5000
                or path.is_absolute()
                or ".." in path.parts
                or "\\" in member.name
                or member.name in names
                or not (member.isfile() or member.isdir())
            ):
                raise ValueError("Repository archive contains unsupported paths or entries")
            names.add(member.name)
            total += member.size
            if total > MAX_ARCHIVE:
                raise ValueError("Repository source exceeds 256 MiB")
            destination = output.joinpath(*path.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                raise ValueError("Repository archive has an unreadable member")
            with source, destination.open("xb") as handle:
                remaining = member.size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Truncated repository archive")
                    handle.write(chunk)
                    remaining -= len(chunk)
            destination.chmod(0o600)


def _nanogpt_data(source: Path) -> dict:
    import numpy as np

    output = source / "data/headroom_synthetic"
    output.mkdir(parents=True, exist_ok=True)
    rng, hashes = np.random.default_rng(1337), {}
    for split in ("train", "val"):
        data = rng.integers(0, 50304, size=262144, dtype=np.uint16).tobytes()
        path = output / (split + ".bin")
        if path.exists() and path.read_bytes() != data:
            raise ValueError("Existing synthetic data differs; refusing replacement")
        path.write_bytes(data)
        hashes[split] = hashlib.sha256(data).hexdigest()
    return {"kind": "synthetic_uint16", "seed": 1337, "sha256": hashes}


def _publish_reviewed_nanogpt(extracted: Path) -> None:
    """Publish only three fixed-hash baseline files for the non-executable policy profile."""
    payloads = {}
    for name, expected in NANOGPT_HASHES.items():
        path = extracted / name
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024 * 1024:
                raise ValueError("Pinned baseline file is not a bounded regular file")
            payload = handle.read(2 * 1024 * 1024 + 1)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError("Pinned baseline file does not match its reviewed hash")
        payloads[name] = payload
    cache = PROJECT_ROOT
    for part in (".cache", "reviewed", "nanogpt"):
        cache = cache / part
        if cache.is_symlink():
            raise ValueError("Reviewed baseline cache cannot follow symbolic links")
        cache.mkdir(exist_ok=True, mode=0o700)
    descriptor = os.open(cache / ".publish.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        destination = cache / NANOGPT_REF
        if destination.is_symlink():
            raise ValueError("Reviewed baseline cache cannot be a symbolic link")
        if destination.exists():
            for name, payload in payloads.items():
                path = destination / name
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as handle:
                    if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                        raise ValueError("Existing baseline cache is not regular")
                    existing = handle.read(2 * 1024 * 1024 + 1)
                if existing != payload:
                    raise ValueError("Existing reviewed baseline differs; refusing replacement")
            return
        temporary = cache / (".staging-" + uuid4().hex)
        temporary.mkdir(mode=0o700)
        for name, payload in payloads.items():
            path = temporary / name
            path.write_bytes(payload)
            path.chmod(0o444)
        temporary.rename(destination)


def prepare_repository(
    repo: str, ref: str, command: str | list[str], *, destination: Path | None = None
) -> PreparedRepository:
    repo = validate_repository(repo, ref)
    entrypoint, arguments = parse_python_command(command)
    pinned = repo == NANOGPT_URL and ref == NANOGPT_REF
    if pinned:
        if entrypoint != "train.py":
            raise ValueError("Pinned nanoGPT profile requires train.py")
        nanogpt_cli(list(arguments))
    parent = Path(destination or PROJECT_ROOT / ".cache/repositories" / uuid4().hex).resolve()
    if parent.exists():
        raise ValueError("Repository destination must be new; existing artifacts are preserved")
    parent.mkdir(parents=True, mode=0o700)
    checkout = PROJECT_ROOT / ".cache/upstream/nanoGPT"
    use_cache = False
    if pinned and checkout.is_dir() and not checkout.is_symlink():
        try:
            use_cache = (
                _git(checkout, "rev-parse", "HEAD") == ref
                and _git(checkout, "remote", "get-url", "origin") == repo
                and not _git(checkout, "status", "--porcelain")
            )
        except (ValueError, subprocess.SubprocessError):
            use_cache = False
    if not use_cache:
        checkout = parent / "git"
        checkout.mkdir()
        _git(checkout, "init", "--bare")
        _git(checkout, "fetch", "--depth=1", "--no-tags", "--no-recurse-submodules", repo, ref)
        if _git(checkout, "rev-parse", "FETCH_HEAD") != ref:
            raise ValueError("Fetched source differs from requested pin")
    archive = parent / "source.tar"
    _git(checkout, "archive", "--format=tar", "--output=" + str(archive), ref)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError("Repository archive exceeds 256 MiB")
    extracted = parent / "extracted"
    _extract(archive, extracted)
    if (extracted / ".gitmodules").exists():
        raise ValueError("Submodules require separately reviewed pins and are unsupported")
    source = parent / "source"
    if pinned:
        _publish_reviewed_nanogpt(extracted)
        minimal = parent / "reviewed-input"
        minimal.mkdir(mode=0o700)
        for name in ("train.py", "model.py", "configurator.py"):
            shutil.copyfile(extracted / name, minimal / name)
        manifest = copy_source(minimal, source)
    else:
        manifest = copy_source(extracted, source)
    data, rewrites = None, []
    if pinned:
        data = _nanogpt_data(source)
        converted = []
        for argument in arguments:
            if argument == "--dataset=/input":
                argument = "--dataset=headroom_synthetic"
                rewrites.append("Historical /input mapped to copied data/headroom_synthetic")
            converted.append(argument)
        if not any(arg.startswith("--dataset=") for arg in converted):
            converted.append("--dataset=headroom_synthetic")
        arguments = tuple(converted)
    script = source / entrypoint
    if not script.is_file() or script.is_symlink() or not script.resolve().is_relative_to(source):
        raise ValueError("Repository entrypoint is missing or excluded")
    metadata = {
        "repository": repo,
        "ref": ref,
        "entrypoint": entrypoint,
        "script_args": list(arguments),
        "source_manifest": manifest,
        "dataset": data,
        "argument_rewrites": rewrites,
        "code_executed": False,
    }
    (parent / "repository.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return PreparedRepository(
        source, script, arguments, "pinned_nanogpt" if pinned else None, metadata
    )
