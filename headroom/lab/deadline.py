"""One host deadline shared with a read-only control mount in the Lab."""

from __future__ import annotations

import json
import math
import os
import stat
import time
from pathlib import Path

CONTROL_DIR = Path("/control")
PROTOCOL = "headroom.deadline.v1"
MAX_CONTROL_BYTES = 8192
NANOSECONDS = 1_000_000_000


class DeadlineUnavailable(ValueError):
    """The host's deadline or shared monotonic clock could not be verified."""


def clock_identity() -> dict:
    try:
        namespace = os.stat("/proc/self/ns/time")
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        if not boot_id or len(boot_id) > 80:
            raise ValueError
        offsets = {}
        for line in Path("/proc/self/timens_offsets").read_text().splitlines():
            kind, seconds, nanoseconds = line.split()
            if kind in offsets:
                raise ValueError
            offsets[kind] = {"seconds": int(seconds), "nanoseconds": int(nanoseconds)}
        if "monotonic" not in offsets or not 0 <= offsets["monotonic"]["nanoseconds"] < NANOSECONDS:
            raise ValueError
        return {
            "clock": "CLOCK_MONOTONIC",
            "boot_id": boot_id,
            "monotonic_offset": offsets["monotonic"],
            "time_namespace_device": namespace.st_dev,
            "time_namespace_inode": namespace.st_ino,
        }
    except (OSError, ValueError):
        raise DeadlineUnavailable("Shared Linux monotonic clock identity unavailable") from None


def same_monotonic_clock(host: dict, observed: dict) -> bool:
    # Docker can create a distinct time namespace with an identical offset.
    # Namespace inode alone does not determine whether monotonic values differ.
    if not isinstance(host, dict) or not isinstance(observed, dict):
        return False
    for identity in (host, observed):
        offset = identity.get("monotonic_offset")
        if (
            identity.get("clock") != "CLOCK_MONOTONIC"
            or not isinstance(identity.get("boot_id"), str)
            or not identity["boot_id"]
            or not isinstance(offset, dict)
            or type(offset.get("seconds")) is not int
            or type(offset.get("nanoseconds")) is not int
            or not 0 <= offset["nanoseconds"] < NANOSECONDS
        ):
            return False
    return (
        host["boot_id"] == observed["boot_id"]
        and host["monotonic_offset"] == observed["monotonic_offset"]
    )


def publish_deadline(control: Path, max_seconds: float) -> dict:
    """Publish immediately before container start; the hard duration is unchanged."""
    if type(max_seconds) not in (int, float) or not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError("Deadline duration must be positive and finite")
    control = Path(control)
    if control.is_symlink() or not control.is_dir():
        raise DeadlineUnavailable("Deadline control directory is unavailable")
    started = time.monotonic_ns()
    duration = int(max_seconds * NANOSECONDS)
    reserve = int(min(5.0, max_seconds * 0.1) * NANOSECONDS)
    record = {
        "protocol": PROTOCOL,
        "clock_identity": clock_identity(),
        "started_monotonic_ns": started,
        "hard_deadline_monotonic_ns": started + duration,
        "capture_deadline_monotonic_ns": started + duration - reserve,
        "max_seconds": max_seconds,
        "capture_reserve_seconds": reserve / NANOSECONDS,
    }
    temporary = control / "deadline.json.tmp"
    temporary.write_text(json.dumps(record, allow_nan=False) + "\n")
    temporary.chmod(0o444)
    temporary.replace(control / "deadline.json")
    return record


def configured_control() -> Path | None:
    """No target-writable alternative to the fixed read-only mount is accepted."""
    configured = os.environ.get("HEADROOM_CONTROL_DIR")
    if configured is not None and configured != str(CONTROL_DIR):
        raise DeadlineUnavailable("Deadline control path differs from the fixed Lab mount")
    if configured is not None or CONTROL_DIR.exists():
        return CONTROL_DIR
    return None  # Direct in-process instrumentation, outside the Docker production path.


def capture_window(control: Path, max_seconds: float) -> tuple[float, dict]:
    control = Path(control)
    try:
        if control.is_symlink() or not control.is_dir():
            raise ValueError
        fd = os.open(control / "deadline.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_CONTROL_BYTES:
                raise ValueError
            raw = source.read(MAX_CONTROL_BYTES + 1)
        if len(raw) > MAX_CONTROL_BYTES:
            raise ValueError
        record = json.loads(raw)
        observed_clock = clock_identity()
        if (
            type(record) is not dict
            or record.get("protocol") != PROTOCOL
            or not same_monotonic_clock(record.get("clock_identity"), observed_clock)
            or record.get("max_seconds") != max_seconds
        ):
            raise ValueError
        keys = (
            "started_monotonic_ns",
            "hard_deadline_monotonic_ns",
            "capture_deadline_monotonic_ns",
        )
        if any(type(record.get(key)) is not int or record[key] <= 0 for key in keys):
            raise ValueError
        started, hard, soft = (record[key] for key in keys)
        reserve = int(min(5.0, max_seconds * 0.1) * NANOSECONDS)
        if hard - started != int(max_seconds * NANOSECONDS) or hard - soft != reserve:
            raise ValueError
        if record.get("capture_reserve_seconds") != reserve / NANOSECONDS:
            raise ValueError
        now = time.monotonic_ns()
        if now < started:
            raise ValueError
    except (OSError, ValueError, TypeError, RecursionError):
        raise DeadlineUnavailable(
            "Host deadline record or shared monotonic clock mismatch"
        ) from None
    remaining = max(0.0, (soft - now) / NANOSECONDS)
    return remaining, {
        "basis": "verified_host_monotonic_deadline",
        "clock_verified": True,
        "observed_clock_identity": observed_clock,
        **record,
        "observed_monotonic_ns": now,
        "remaining_capture_seconds": remaining,
        "expired_before_target": remaining == 0,
    }
