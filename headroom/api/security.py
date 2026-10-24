"""Bounded artifact reads that never follow a symbolic link or client host path."""

import os
import re
import stat
from pathlib import Path, PurePosixPath

RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
ARTIFACTS = {
    "cli.json": ("cli.json", "application/json"),
    "pareto.json": ("pareto.json", "application/json"),
    "pareto.md": ("pareto.md", "text/plain; charset=utf-8"),
    "annotations.json": ("annotations.json", "application/json"),
    "evidence-after.json": ("evidence/after/evidence.json", "application/json"),
    "report.md": ("report.md", "text/plain; charset=utf-8"),
    "report.json": ("report.json", "application/json"),
    "patch.diff": ("patch.diff", "text/plain; charset=utf-8"),
    "env.sh": ("env.sh", "text/plain; charset=utf-8"),
    "evidence.json": ("evidence/before/evidence.json", "application/json"),
    "evidence.md": ("evidence/before/evidence.md", "text/plain; charset=utf-8"),
    "timeline-before.png": ("evidence/before/timeline.png", "image/png"),
    "timeline-after.png": ("evidence/after/timeline.png", "image/png"),
}


def open_regular(root, relative, max_bytes=64 * 1024 * 1024):
    """Return an already-open regular file, traversing every component with NOFOLLOW."""
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("Invalid relative path")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        leaf = os.open(
            path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor
        )
        try:
            info = os.fstat(leaf)
            if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
                raise ValueError("Artifact is not a bounded regular file")
            return os.fdopen(leaf, "rb")
        except BaseException:
            os.close(leaf)
            raise
    finally:
        os.close(descriptor)


def job_directory(root, run_id):
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run identifier")
    root = Path(root)
    path = root / run_id
    if root.is_symlink() or path.is_symlink():
        raise ValueError("Run directories cannot be symbolic links")
    return path
