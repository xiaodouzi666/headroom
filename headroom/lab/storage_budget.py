"""Application storage admission for Lab artifacts; never deletes existing runs.

The per-container tmpfs is the hard write boundary. This lock and bounded census
prevent serial public jobs from accumulating unlimited exports on the host.
The lock is held only during bounded host writes, never during GPU execution.
"""

import fcntl
import os
import re
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path

MAX_STORAGE_BYTES = 16 * 1024**3
MIN_FREE_BYTES = 8 * 1024**3
LAB_RESERVATION_BYTES = 1024**3
MAX_CENSUS_FILES = 200_000
PUBLIC_STORAGE_ROOT = Path(__file__).resolve().parents[2] / "runs/public-api"
PUBLIC_MARKER = ".headroom-public-storage"


def storage_scope(run_root):
    root = Path(run_root).resolve()
    if root.name == "lab" and re.fullmatch(r"[0-9a-f]{32}", root.parent.name):
        root = root.parent.parent
    if root.name == "jobs":
        return root.parent
    return root


def stored_bytes(root):
    """Count logical regular-file bytes without following links or special files."""
    total = count = 0
    pending = [Path(root)]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_CENSUS_FILES:
                    raise ValueError("LAB_STORAGE_CAPACITY: retained storage exceeds entry limit")
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    total += info.st_size
                    if total > MAX_STORAGE_BYTES:
                        raise ValueError(
                            "LAB_STORAGE_CAPACITY: retained artifacts exceed storage admission"
                        )
                else:
                    raise ValueError(
                        "LAB_STORAGE_UNSAFE: retained storage contains a link or special file"
                    )
    return total


@contextmanager
def storage_admission(run_root, *, aggregate=False):
    scope = storage_scope(run_root)
    scope.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        scope / ".headroom-storage.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("LAB_STORAGE_UNSAFE: invalid storage lock")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(
                "LAB_STORAGE_BUSY: another Lab execution holds storage admission"
            ) from error
        marker = scope / PUBLIC_MARKER
        public = aggregate is True or scope == PUBLIC_STORAGE_ROOT
        if public and not marker.exists() and not marker.is_symlink():
            marker_fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(marker_fd, "w") as handle:
                handle.write("headroom.public-storage.v1\n")
        if marker.exists() or marker.is_symlink():
            marker_fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(marker_fd, "rb") as handle:
                if (
                    not stat.S_ISREG(os.fstat(handle.fileno()).st_mode)
                    or handle.read(64) != b"headroom.public-storage.v1\n"
                ):
                    raise ValueError("LAB_STORAGE_UNSAFE: invalid public storage marker")
            public = True
        used = stored_bytes(scope) if public else None
        if public and used + LAB_RESERVATION_BYTES > MAX_STORAGE_BYTES:
            raise ValueError(
                "LAB_STORAGE_CAPACITY: retained artifacts leave insufficient export capacity"
            )
        if shutil.disk_usage(scope).free - LAB_RESERVATION_BYTES < MIN_FREE_BYTES:
            raise ValueError("LAB_STORAGE_FREE_SPACE: insufficient free disk after export reserve")
        yield {
            "scope": str(scope),
            "retained_bytes": used,
            "storage_limit_bytes": MAX_STORAGE_BYTES if public else None,
            "public_aggregate": public,
            "reserved_bytes": LAB_RESERVATION_BYTES,
            "minimum_free_bytes": MIN_FREE_BYTES,
        }
    finally:
        os.close(descriptor)
