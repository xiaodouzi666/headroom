#!/usr/bin/env python3
"""Read-only origin/Funnel checks. No model calls, notifications or raw health storage."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import ssl
import stat
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

TARGETS = {
    "origin": "http://127.0.0.1:8766/api/health",
    "public": "https://headroom.tail45186b.ts.net/api/health",
}
MAX_BYTES = 64 * 1024
REQUEST_SECONDS = 15
DEFAULT_STATE = Path(__file__).resolve().parents[1] / ".cache/funnel-health.json"
CODES = {
    "ok",
    "http_error",
    "redirect",
    "timeout",
    "tls_error",
    "transport_error",
    "invalid_json",
    "invalid_health",
    "response_too_large",
}
CHECK_KEYS = {
    "status",
    "http_status",
    "latency_ms",
    "slow",
    "last_success_at_utc",
    "consecutive_failures",
}
STATE_KEYS = {
    "schema_version",
    "checked_at_utc",
    "healthy",
    "last_success_at_utc",
    "consecutive_failures",
    "checks",
}


class StateError(ValueError):
    """A fixed error code only; never expose a path or underlying exception."""


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
    )


def _tls_error(error):
    visited = set()
    while error is not None and id(error) not in visited:
        if isinstance(error, ssl.SSLError):
            return True
        visited.add(id(error))
        error = error.__cause__ or error.__context__
    return False


async def _probe(url, *, transport=None):
    if url not in TARGETS.values():
        raise ValueError("Health target is not allowed")
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ValueError("Only an offline mock transport may be injected")
    started = time.monotonic()
    result = {"status": "transport_error", "http_status": None, "latency_ms": 0.0}

    async def request():
        async with (
            httpx.AsyncClient(
                verify=True,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(REQUEST_SECONDS, connect=10, pool=1),
                transport=transport,
            ) as client,
            client.stream("GET", url, headers={"Accept": "application/json"}) as response,
        ):
            result["http_status"] = response.status_code
            if 300 <= response.status_code < 400:
                result["status"] = "redirect"
                return
            if response.status_code != 200:
                result["status"] = "http_error"
                return
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw) + len(chunk) > MAX_BYTES:
                    result["status"] = "response_too_large"
                    return
                raw.extend(chunk)
            try:
                document = _json(raw)
            except (ValueError, UnicodeError, RecursionError):
                result["status"] = "invalid_json"
                return
            result["status"] = (
                "ok"
                if isinstance(document, dict) and document.get("status") == "ok"
                else "invalid_health"
            )

    try:
        # Total request deadline also bounds a peer that trickles response chunks.
        await asyncio.wait_for(request(), timeout=REQUEST_SECONDS)
    except (TimeoutError, httpx.TimeoutException):
        result["status"] = "timeout"
    except httpx.HTTPError as error:
        result["status"] = "tls_error" if _tls_error(error) else "transport_error"
    except ssl.SSLError:
        result["status"] = "tls_error"
    except OSError:
        result["status"] = "transport_error"
    result["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    result["slow"] = result["latency_ms"] > 3000
    return result


async def _probes(transport):
    values = await asyncio.gather(*(_probe(url, transport=transport) for url in TARGETS.values()))
    return dict(zip(TARGETS, values, strict=True))


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        return False
    try:
        return datetime.fromisoformat(value).utcoffset().total_seconds() == 0
    except (ValueError, AttributeError):
        return False


def _count(value):
    return type(value) is int and value >= 0


def _validate(value):
    if (
        not isinstance(value, dict)
        or set(value) != STATE_KEYS
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or not _timestamp(value["checked_at_utc"])
        or type(value["healthy"]) is not bool
        or not _count(value["consecutive_failures"])
        or (
            value["last_success_at_utc"] is not None
            and not _timestamp(value["last_success_at_utc"])
        )
        or not isinstance(value["checks"], dict)
        or set(value["checks"]) != set(TARGETS)
    ):
        raise StateError("invalid_state")
    for item in value["checks"].values():
        if (
            not isinstance(item, dict)
            or set(item) != CHECK_KEYS
            or item["status"] not in CODES
            or (
                item["http_status"] is not None
                and not (type(item["http_status"]) is int and 100 <= item["http_status"] <= 599)
            )
            or type(item["latency_ms"]) not in (int, float)
            or not 0 <= item["latency_ms"] < float("inf")
            or type(item["slow"]) is not bool
            or not _count(item["consecutive_failures"])
            or (
                item["last_success_at_utc"] is not None
                and not _timestamp(item["last_success_at_utc"])
            )
        ):
            raise StateError("invalid_state")
    return value


@contextmanager
def _state_directory(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise StateError("invalid_state_path")
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    lock = None
    try:
        for component in path.parts[1:-1]:
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        lock = os.open(
            path.name + ".lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=descriptor,
        )
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise StateError("invalid_state_lock")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield descriptor, path.name
    finally:
        if lock is not None:
            os.close(lock)
        os.close(descriptor)


def _read(descriptor, name):
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    except FileNotFoundError:
        return None
    with os.fdopen(handle, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise StateError("invalid_state_file")
        try:
            return _validate(_json(stream.read(MAX_BYTES + 1)))
        except (ValueError, UnicodeError, RecursionError, TypeError):
            raise StateError("invalid_state") from None


def _write(descriptor, name, value):
    temporary = "." + name + "." + uuid4().hex + ".tmp"
    handle = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=descriptor,
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write((json.dumps(value, allow_nan=False, sort_keys=True) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        try:
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise StateError("invalid_state_file")
        except FileNotFoundError:
            pass
        os.replace(temporary, name, src_dir_fd=descriptor, dst_dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        try:
            os.unlink(temporary, dir_fd=descriptor)
        except FileNotFoundError:
            pass


def check(*, state_path=DEFAULT_STATE, transport=None, now=None):
    """Run fixed GET checks and atomically retain only the safe status projection."""
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ValueError("Only an offline mock transport may be injected")
    now = now or datetime.now(UTC)
    stamp = now.astimezone(UTC).isoformat()
    with _state_directory(state_path) as (descriptor, name):
        previous = _read(descriptor, name)
        if previous and datetime.fromisoformat(previous["checked_at_utc"]) > now:
            raise StateError("clock_moved_backwards")
        checks = asyncio.run(_probes(transport))
        for layer, item in checks.items():
            old = previous["checks"][layer] if previous else {}
            okay = item["status"] == "ok"
            item["last_success_at_utc"] = stamp if okay else old.get("last_success_at_utc")
            item["consecutive_failures"] = 0 if okay else old.get("consecutive_failures", 0) + 1
        healthy = all(item["status"] == "ok" for item in checks.values())
        state = {
            "schema_version": 1,
            "checked_at_utc": stamp,
            "healthy": healthy,
            "last_success_at_utc": stamp
            if healthy
            else (previous.get("last_success_at_utc") if previous else None),
            "consecutive_failures": 0
            if healthy
            else (previous["consecutive_failures"] + 1 if previous else 1),
            "checks": checks,
        }
        _write(descriptor, name, _validate(state))
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()
    try:
        result = check(state_path=args.state)
    except (StateError, OSError):
        print(json.dumps({"monitor_status": "state_error", "code": "state_unavailable"}))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
