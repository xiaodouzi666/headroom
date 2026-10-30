"""Bound target output in a tmpfs volume, held by a separate read-only keeper.

The target has no writable host mount. After its removal, only a bounded stream of
allowlisted regular capture files is published. No archive extraction API is used.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
from pathlib import Path, PurePosixPath
from uuid import uuid4

from headroom.lab.envs import HOST_ENV

MAX_BYTES = 512 * 1024 * 1024
MAX_INODES = 4096
EXPORT_SECONDS = 60
SCHEMA = "headroom.lab.artifact-store.v1"
LABEL = "org.headroom.artifact-store"
FILES = frozenset(
    {
        ".capture-owner.json",
        "capture-ready.json",
        "result.json",
        "memory_stats.json",
        "memory_summary.txt",
        "traceback.txt",
        "env.json",
        "snapshot.pickle",
        "snapshot.json",
        "reference-offload.json",
    }
)


class ArtifactStoreError(RuntimeError):
    def __init__(self, message, metadata=None):
        super().__init__(message)
        self.metadata = metadata


def _require(condition, reason):
    if not condition:
        raise ArtifactStoreError(reason)


def names(target_name):
    _require(
        isinstance(target_name, str) and re.fullmatch(r"headroom-lab-[a-f0-9]{32}", target_name),
        "ARTIFACT_TARGET_NAME_INVALID",
    )
    return {"volume": target_name + "-artifacts", "keeper": target_name + "-keeper"}


def _binary():
    from headroom.lab.docker import docker_binary

    return docker_binary()


def _run(arguments, *, timeout=15):
    return subprocess.run(
        [_binary(), *arguments],
        env=HOST_ENV,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _inspect(kind, name):
    command = (
        ["volume", "inspect", name]
        if kind == "volume"
        else ["inspect", "--type", "container", name]
    )
    result = _run(command)
    if result.returncode:
        message = result.stderr.lower()
        markers = (
            ("no such volume",) if kind == "volume" else ("no such container", "no such object")
        )
        if any(marker in message for marker in markers) and name.lower() in message:
            return None
        raise ArtifactStoreError("ARTIFACT_INSPECTION_UNAVAILABLE")
    try:
        values = json.loads(result.stdout)
        _require(
            isinstance(values, list) and len(values) == 1 and isinstance(values[0], dict),
            "ARTIFACT_INSPECTION_INVALID",
        )
        return values[0]
    except (ValueError, TypeError):
        raise ArtifactStoreError("ARTIFACT_INSPECTION_INVALID") from None


def _labels(metadata):
    return {
        LABEL: SCHEMA,
        LABEL + ".target": metadata["target"],
        LABEL + ".output": metadata["output_path"],
        LABEL + ".nonce": metadata["nonce"],
        LABEL + ".image": metadata["image_id"],
        LABEL + ".bytes": str(metadata["max_bytes"]),
        LABEL + ".inodes": str(metadata["max_inodes"]),
    }


def _options(metadata):
    return {
        "type": "tmpfs",
        "device": "tmpfs",
        "o": (
            f"size={metadata['max_bytes']},nr_inodes={metadata['max_inodes']},"
            f"uid={os.getuid()},gid={os.getgid()},mode=0700,nodev,nosuid,noexec"
        ),
    }


def _validate(metadata):
    _require(
        isinstance(metadata, dict) and metadata.get("schema") == SCHEMA, "ARTIFACT_METADATA_INVALID"
    )
    expected = names(metadata["target"])
    _require(
        all(metadata.get(key) == value for key, value in expected.items()), "ARTIFACT_NAMES_CHANGED"
    )
    _require(
        re.fullmatch(r"sha256:[a-f0-9]{64}", metadata.get("image_id", "")) is not None,
        "ARTIFACT_IMAGE_INVALID",
    )
    _require(
        re.fullmatch(r"[a-f0-9]{32}", metadata.get("nonce", "")) is not None,
        "ARTIFACT_NONCE_INVALID",
    )
    _require(
        type(metadata.get("max_bytes")) is int
        and 1024 * 1024 <= metadata["max_bytes"] <= MAX_BYTES,
        "ARTIFACT_BYTE_LIMIT_INVALID",
    )
    _require(
        type(metadata.get("max_inodes")) is int and 16 <= metadata["max_inodes"] <= MAX_INODES,
        "ARTIFACT_INODE_LIMIT_INVALID",
    )
    output = Path(metadata["output_path"])
    _require(
        output.is_absolute()
        and not output.is_symlink()
        and output.is_dir()
        and str(output.resolve()) == str(output),
        "ARTIFACT_OUTPUT_INVALID",
    )


def _volume(metadata):
    actual = _inspect("volume", metadata["volume"])
    if actual is None:
        return None
    _require(
        actual.get("Name") == metadata["volume"]
        and actual.get("Driver") == "local"
        and actual.get("Labels") == _labels(metadata)
        and actual.get("Options") == _options(metadata),
        "ARTIFACT_VOLUME_OWNERSHIP_CHANGED",
    )
    identity = {"CreatedAt": actual.get("CreatedAt"), "Mountpoint": actual.get("Mountpoint")}
    _require(
        all(isinstance(value, str) and value for value in identity.values()),
        "ARTIFACT_VOLUME_IDENTITY_INVALID",
    )
    if metadata.get("volume_identity") is not None:
        _require(metadata["volume_identity"] == identity, "ARTIFACT_VOLUME_IDENTITY_CHANGED")
    return actual


def _keeper(metadata, *, running=False):
    actual = _inspect("container", metadata["keeper"])
    if actual is None:
        return None
    ident = actual.get("Id", "")
    mounts = [item for item in actual.get("Mounts", []) if item.get("Destination") == "/out"]
    host = actual.get("HostConfig", {})
    environment = actual.get("Config", {}).get("Env", [])
    gpu_disabled = all(
        [entry for entry in environment if entry.startswith(key + "=")] == [key + "=" + value]
        for key, value in (("NVIDIA_VISIBLE_DEVICES", "void"), ("CUDA_VISIBLE_DEVICES", ""))
    )
    _require(
        re.fullmatch(r"[a-f0-9]{64}", ident) is not None
        and (metadata.get("keeper_id") is None or metadata["keeper_id"] == ident)
        and actual.get("Name") == "/" + metadata["keeper"]
        and actual.get("Image") == metadata["image_id"]
        and all(
            actual.get("Config", {}).get("Labels", {}).get(key) == value
            for key, value in _labels(metadata).items()
        )
        and host.get("NetworkMode") == "none"
        and not host.get("DeviceRequests")
        and gpu_disabled
        and host.get("ReadonlyRootfs") is True
        and len(mounts) == 1
        and mounts[0].get("Type") == "volume"
        and mounts[0].get("Name") == metadata["volume"]
        and mounts[0].get("RW") is False,
        "ARTIFACT_KEEPER_OWNERSHIP_CHANGED",
    )
    if running:
        _require(actual.get("State", {}).get("Running") is True, "ARTIFACT_KEEPER_NOT_RUNNING")
    return actual


def create_store(target_name, image_id, *, output_path, max_bytes=MAX_BYTES, max_inodes=MAX_INODES):
    metadata = {
        "schema": SCHEMA,
        "target": target_name,
        **names(target_name),
        "image_id": image_id,
        "output_path": str(Path(output_path).absolute()),
        "max_bytes": max_bytes,
        "max_inodes": max_inodes,
        "nonce": uuid4().hex,
        "keeper_id": None,
        "volume_identity": None,
    }
    _validate(metadata)
    _require(not any(Path(output_path).iterdir()), "ARTIFACT_OUTPUT_NOT_EMPTY")
    _require(
        _inspect("volume", metadata["volume"]) is None
        and _inspect("container", metadata["keeper"]) is None
        and _inspect("container", target_name) is None,
        "ARTIFACT_STORE_ALREADY_EXISTS",
    )
    labels = [
        value for key, val in _labels(metadata).items() for value in ("--label", f"{key}={val}")
    ]
    try:
        options = [
            value for key, val in _options(metadata).items() for value in ("--opt", f"{key}={val}")
        ]
        result = _run(
            ["volume", "create", "--driver", "local", *options, *labels, metadata["volume"]]
        )
        _require(result.returncode == 0, "ARTIFACT_VOLUME_CREATE_FAILED")
        volume = _volume(metadata)
        _require(volume is not None, "ARTIFACT_VOLUME_CREATE_FAILED")
        metadata["volume_identity"] = {key: volume[key] for key in ("CreatedAt", "Mountpoint")}
        result = _run(
            [
                "create",
                "--pull",
                "never",
                "--name",
                metadata["keeper"],
                "--network",
                "none",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--memory",
                "64m",
                "--cpus",
                "0.1",
                "--pids-limit",
                "16",
                "--log-driver",
                "none",
                "--env",
                "NVIDIA_VISIBLE_DEVICES=void",
                "--env",
                "CUDA_VISIBLE_DEVICES=",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                *labels,
                "--mount",
                f"type=volume,source={metadata['volume']},destination=/out,readonly",
                "--entrypoint",
                "/opt/venv/bin/python",
                image_id,
                "-I",
                "-S",
                "-c",
                "import time; time.sleep(86400)",
            ]
        )
        _require(result.returncode == 0, "ARTIFACT_KEEPER_CREATE_FAILED")
        keeper = _keeper(metadata)
        _require(keeper is not None, "ARTIFACT_KEEPER_CREATE_FAILED")
        metadata["keeper_id"] = keeper["Id"]
        _require(
            _run(["start", metadata["keeper_id"]]).returncode == 0, "ARTIFACT_KEEPER_START_FAILED"
        )
        _keeper(metadata, running=True)
        return metadata
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, ArtifactStoreError) as error:
        metadata["creation_cleanup"] = cleanup_store(metadata)
        raise ArtifactStoreError("ARTIFACT_STORE_CREATE_FAILED", metadata) from error


def discover_store(target_name, *, output_path):
    """Recover only this target's deterministic, host-labelled store; no target files."""
    found = names(target_name)
    volume = _inspect("volume", found["volume"])
    if volume is None:
        _require(_inspect("container", found["keeper"]) is None, "ARTIFACT_RECOVERY_PARTIAL")
        return None
    labels = volume.get("Labels", {})
    try:
        metadata = {
            "schema": SCHEMA,
            "target": target_name,
            **found,
            "output_path": str(Path(output_path).absolute()),
            "image_id": labels[LABEL + ".image"],
            "nonce": labels[LABEL + ".nonce"],
            "max_bytes": int(labels[LABEL + ".bytes"]),
            "max_inodes": int(labels[LABEL + ".inodes"]),
            "volume_identity": {key: volume[key] for key in ("CreatedAt", "Mountpoint")},
            "keeper_id": None,
        }
        _validate(metadata)
        _volume(metadata)
        keeper = _keeper(metadata)
        if keeper is not None:
            metadata["keeper_id"] = keeper["Id"]
        return metadata
    except (ValueError, TypeError, KeyError) as error:
        raise ArtifactStoreError("ARTIFACT_RECOVERY_INVALID") from error


def _member_path(member):
    name = member.name
    while name.startswith("./"):
        name = name[2:]
    if name in ("", ".") and member.isdir():
        return None
    path = PurePosixPath(name)
    _require(
        not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in name
        and path.as_posix() == name.rstrip("/"),
        "ARTIFACT_ARCHIVE_PATH_INVALID",
    )
    parts = path.parts
    directory = parts == ("processes",) or (
        len(parts) == 2
        and parts[0] == "processes"
        and re.fullmatch(r"[0-9]+(?:-[0-9]+)?", parts[1])
    )
    file = (
        len(parts) == 1
        or (
            len(parts) == 3
            and parts[0] == "processes"
            and re.fullmatch(r"[0-9]+(?:-[0-9]+)?", parts[1])
        )
    ) and parts[-1] in FILES
    _require(
        (member.isdir() and directory)
        or (member.type in (tarfile.REGTYPE, tarfile.AREGTYPE) and file),
        "ARTIFACT_ARCHIVE_MEMBER_FORBIDDEN",
    )
    _require(
        not member.sparse and not any(key.startswith("GNU.sparse") for key in member.pax_headers),
        "ARTIFACT_SPARSE_FORBIDDEN",
    )
    return path


class _LimitedReader:
    def __init__(self, stream, limit):
        self.stream, self.limit, self.used = stream, limit, 0

    def read(self, size=-1):
        _require(size >= 0, "ARTIFACT_UNBOUNDED_READ")
        data = self.stream.read(min(size, self.limit - self.used + 1))
        self.used += len(data)
        _require(self.used <= self.limit, "ARTIFACT_ARCHIVE_TOO_LARGE")
        return data


def _export_tar(stream, output, *, max_bytes, max_inodes):
    seen, count, total = set(), 0, 0
    reader = _LimitedReader(stream, max_bytes + max_inodes * 4096 + 1024 * 1024)
    with tarfile.open(fileobj=reader, mode="r|") as archive:
        for member in archive:
            count += 1
            _require(count <= max_inodes, "ARTIFACT_ARCHIVE_TOO_MANY_FILES")
            path = _member_path(member)
            if path is None:
                continue
            _require(str(path) not in seen, "ARTIFACT_ARCHIVE_DUPLICATE")
            seen.add(str(path))
            destination = output / path
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            _require(
                0 <= member.size <= max_bytes and total + member.size <= max_bytes,
                "ARTIFACT_ARCHIVE_TOO_LARGE",
            )
            if path.name == "reference-offload.json":
                _require(member.size <= 64 * 1024, "REFERENCE_METADATA_TOO_LARGE")
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            with os.fdopen(descriptor, "wb") as handle, archive.extractfile(member) as source:
                remaining = member.size
                while remaining:
                    data = source.read(min(65536, remaining))
                    _require(bool(data), "ARTIFACT_ARCHIVE_TRUNCATED")
                    handle.write(data)
                    remaining -= len(data)
            total += member.size
    return {"files": len(seen), "bytes": total, "export_verified": True}


def export_store(metadata, output_path):
    _validate(metadata)
    output = Path(output_path)
    _require(
        str(output.absolute()) == metadata["output_path"] and not any(output.iterdir()),
        "ARTIFACT_OUTPUT_CHANGED",
    )
    _require(_inspect("container", metadata["target"]) is None, "ARTIFACT_TARGET_STILL_EXISTS")
    _require(_volume(metadata) is not None, "ARTIFACT_VOLUME_MISSING")
    keeper = _keeper(metadata, running=True)
    _require(keeper is not None, "ARTIFACT_KEEPER_MISSING")
    staging = Path(tempfile.mkdtemp(prefix=".artifact-export-", dir=output.parent))
    process = None
    timer = None
    timed_out = threading.Event()

    def stop():
        timed_out.set()
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    try:
        process = subprocess.Popen(
            [_binary(), "cp", f"{keeper['Id']}:/out/.", "-"],
            env=HOST_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        timer = threading.Timer(EXPORT_SECONDS, stop)
        timer.daemon = True
        timer.start()
        result = _export_tar(
            process.stdout,
            staging,
            max_bytes=metadata["max_bytes"],
            max_inodes=metadata["max_inodes"],
        )
        _require(process.wait(timeout=5) == 0 and not timed_out.is_set(), "ARTIFACT_EXPORT_FAILED")
        _require(not any(output.iterdir()), "ARTIFACT_OUTPUT_CHANGED")
        os.replace(staging, output)
        return result
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        raise ArtifactStoreError("ARTIFACT_EXPORT_FAILED", metadata) from error
    finally:
        if timer is not None:
            timer.cancel()
        if process is not None:
            if process.poll() is None:
                stop()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            if process.stdout is not None:
                process.stdout.close()
        if staging.exists():
            shutil.rmtree(staging)


def cleanup_store(metadata):
    """Never remove an unrelated/replaced resource or a still-mounted target."""
    try:
        _validate(metadata)
        _require(_inspect("container", metadata["target"]) is None, "ARTIFACT_TARGET_STILL_EXISTS")
        volume = _volume(metadata)
        keeper = _keeper(metadata)
        if keeper is not None:
            _require(
                _run(["rm", "--force", keeper["Id"]]).returncode == 0,
                "ARTIFACT_KEEPER_REMOVE_FAILED",
            )
        _require(_inspect("container", metadata["keeper"]) is None, "ARTIFACT_KEEPER_REMAINS")
        if volume is not None:
            _require(
                _run(["volume", "rm", metadata["volume"]]).returncode == 0,
                "ARTIFACT_VOLUME_REMOVE_FAILED",
            )
        _require(_inspect("volume", metadata["volume"]) is None, "ARTIFACT_VOLUME_REMAINS")
        return {"cleanup_verified": True}
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, ArtifactStoreError) as error:
        return {"cleanup_verified": False, "error": type(error).__name__}
