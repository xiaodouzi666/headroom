"""Explicitly shared server captures; clients select an ID, never a filesystem path."""

from __future__ import annotations

import hashlib
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from headroom.api.snapshot_queue import directory_fd


@dataclass(frozen=True)
class CaptureFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class SnapshotExample:
    id: str
    label: str
    description: str
    files: tuple[tuple[str, CaptureFile], ...]


_S2 = (
    "runs/final48-f3/execution-20261029-v1/jobs/6330dcf4e44b4accb09b73110dda0183/"
    "lab/3822a1d44c2543239ce69b3af38bbc38/"
)
_NANO = (
    "runs/evaluation/live/20261027T022818939585Z-151818b1/jobs/"
    "9445bf3c9fa040738f23a78ee582b724/lab/a71a8224483b48d2af346130506e4d5f/"
)
EXAMPLES = (
    SnapshotExample(
        "s2-capacity",
        "s2 — training memory capture",
        "Analyze a stored s2 capture with a new Nebius model request. No GPU workload is run.",
        (
            (
                "snapshot.pickle",
                CaptureFile(
                    _S2 + "artifacts/snapshot.pickle",
                    10651527,
                    "1a0f098618849cb774f6919104117956696862b8535e4cd00a3bccf4f800f2ca",
                ),
            ),
            (
                "traceback.txt",
                CaptureFile(
                    _S2 + "artifacts/traceback.txt",
                    878,
                    "70055c88e2a3e3d5e7043740e50fec1fa07c48e123ea626f5bd8e87a5087c68c",
                ),
            ),
            (
                "source.py",
                CaptureFile(
                    _S2 + "source/train.py",
                    6274,
                    "9565acfbcfc2f1eefd982c80be7ce943e09828578b9b44c3d70342bc82bf7f4c",
                ),
            ),
        ),
    ),
    SnapshotExample(
        "nanogpt",
        "nanoGPT — training memory capture",
        "Analyze a stored nanoGPT capture with a new Nebius model request. No GPU workload is run.",
        (
            (
                "snapshot.pickle",
                CaptureFile(
                    _NANO + "artifacts/snapshot.pickle",
                    590852,
                    "7731ac65c4c6635715e680e549daca2c187056ee4d36eaed7d41c3a7ee9d47b7",
                ),
            ),
            (
                "traceback.txt",
                CaptureFile(
                    _NANO + "artifacts/traceback.txt",
                    3452,
                    "ec19d8b9edd9e2629614429b9efa439ddba496f78c70e6485915bb6dfbb1d1fe",
                ),
            ),
            (
                "source.py",
                CaptureFile(
                    _NANO + "source/train.py",
                    14857,
                    "413bd97b40bb400a2a0d01230e2946f056c263ebac1b7281c2367d964a123085",
                ),
            ),
        ),
    ),
)
_LIMITS = {
    "snapshot.pickle": 50 * 1024 * 1024,
    "traceback.txt": 256 * 1024,
    "source.py": 1024 * 1024,
}


def get_example(identifier):
    return next((example for example in EXAMPLES if example.id == identifier), None)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def _source(root, item):
    path = Path(item.path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("Invalid stored capture")
    directory = directory_fd(Path(root) / path.parent)
    descriptor = None
    try:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != item.size:
            raise ValueError("Stored capture unavailable")
        yield descriptor, info
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory)


def list_examples(root):
    """Cheap metadata checks only; hashes are verified before any worker dispatch."""
    values = []
    for example in EXAMPLES:
        available = True
        try:
            for name, item in example.files:
                if name not in _LIMITS or not 0 < item.size <= _LIMITS[name]:
                    raise ValueError("Invalid stored capture")
                with _source(root, item):
                    pass
        except (OSError, ValueError):
            available = False
        values.append(
            {
                "id": example.id,
                "label": example.label,
                "description": example.description,
                "snapshot_bytes": next(
                    item.size for name, item in example.files if name == "snapshot.pickle"
                ),
                "available": available,
                "reason": None if available else "Stored capture unavailable",
            }
        )
    return values


def copy_example(root, target, example, *, cancelled: Event, deadline, clock=time.time):
    """Copy bounded pinned data through owned FDs; never import or execute a source."""
    directory = directory_fd(target)
    try:
        for name, item in example.files:
            if name not in _LIMITS or not 0 < item.size <= _LIMITS[name]:
                raise ValueError("Invalid stored capture")
            with _source(root, item) as (source, before):
                output = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )
                digest = hashlib.sha256()
                total = 0
                with os.fdopen(output, "wb") as stream:
                    while True:
                        if cancelled.is_set():
                            raise ValueError("Stored capture copy cancelled")
                        if clock() >= deadline:
                            raise TimeoutError("Stored capture deadline exceeded")
                        data = os.read(source, min(1024 * 1024, item.size + 1 - total))
                        if not data:
                            break
                        total += len(data)
                        if total > item.size:
                            raise ValueError("Stored capture changed")
                        digest.update(data)
                        stream.write(data)
                after = os.fstat(source)
                if (
                    total != item.size
                    or digest.hexdigest() != item.sha256
                    or after.st_nlink != 1
                    or _identity(before) != _identity(after)
                ):
                    raise ValueError("Stored capture changed")
    finally:
        os.close(directory)
