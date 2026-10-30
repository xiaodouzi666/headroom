"""Offline raw-byte parser and candidate timeout checks; no provider/GPU/HTTP upload."""

import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path.cwd() / "tests"))
from test_snapshot_routes import TOKEN, application, failed_worker, settings

from headroom.api import snapshot_routes as routes
from headroom.api.snapshot_queue import RETENTION_SECONDS


def test_actual_s2_bytes_parse_and_write_fast_without_unpickling(tmp_path):
    source = Path(os.environ["UPLOAD_BENCHMARK_INPUT"])
    expected = os.environ["UPLOAD_BENCHMARK_SHA"]
    assert source.stat().st_size == 10651527
    assert hashlib.sha256(source.read_bytes()).hexdigest() == expected
    records = []
    for chunk_bytes in (64 * 1024, 256 * 1024):
        destination = Path(os.environ.get("UPLOAD_BENCHMARK_DISK_ROOT", str(tmp_path))) / str(
            chunk_bytes
        )
        destination.mkdir(mode=0o700)
        boundary = "headroom-offline-snapshot-benchmark"
        parser = routes.SnapshotMultipart(destination, "multipart/form-data; boundary=" + boundary)
        started = time.perf_counter()
        try:
            parser.write(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="snapshot"; '
                    'filename="snapshot.pickle"\r\nContent-Type: application/octet-stream\r\n\r\n'
                ).encode()
            )
            with source.open("rb") as handle:
                while block := handle.read(chunk_bytes):
                    parser.write(block)
            parser.write(f"\r\n--{boundary}--\r\n".encode())
            parser.finish()
        finally:
            parser.close()
        elapsed = time.perf_counter() - started
        copied = destination / "snapshot.pickle"
        assert copied.stat().st_size == source.stat().st_size
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == expected
        records.append(
            {
                "chunk_bytes": chunk_bytes,
                "snapshot_bytes": copied.stat().st_size,
                "parse_and_write_seconds": elapsed,
                "bytes_per_second": copied.stat().st_size / elapsed,
                "output_sha256": expected,
                "temporary_output_device": destination.stat().st_dev,
            }
        )
    Path(os.environ["UPLOAD_BENCHMARK_RESULT"]).write_text(
        json.dumps(
            {
                "records": records,
                "no_unpickle_or_model_or_gpu": True,
                "kind": "direct streaming parser plus filesystem write, not network throughput",
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "judge,total_deadline,minimum,maximum",
    [(True, 480, 359, 360), (False, 480, 29, 30), (True, 0.5, 0, 0.5)],
)
def test_candidate_360_seconds_still_obeys_auth_and_total_deadline(
    tmp_path, monkeypatch, judge, total_deadline, minimum, maximum
):
    monkeypatch.setattr(routes, "AUTHENTICATED_UPLOAD_TIMEOUT_SECONDS", 360.0)
    observed = []
    original_timeout = asyncio.timeout

    @asynccontextmanager
    async def shortened(delay):
        observed.append(delay)
        async with original_timeout(0.01):
            yield

    async def slow(_request):
        await asyncio.sleep(0.05)
        yield b""

    app = application(settings(tmp_path, deadline_seconds=total_deadline), worker=failed_worker)
    with TestClient(app) as client:
        monkeypatch.setattr(routes.asyncio, "timeout", shortened)
        monkeypatch.setattr(Request, "stream", slow)
        headers = {"Content-Type": "multipart/form-data; boundary=z"}
        if judge:
            headers["Authorization"] = f"Bearer {TOKEN}"
        response = client.post("/api/snapshots", content=b"x", headers=headers)
        assert response.status_code == 408
        assert len(observed) == 1 and minimum < observed[0] <= maximum
        with sqlite3.connect(app.state.snapshots.registry) as connection:
            assert connection.execute("select status from snapshots").fetchall() == [("timeout",)]
        assert not any(app.state.snapshots.root.glob("*/worker.log"))


def test_timeout_releases_active_slot_but_partial_bytes_expire_at_existing_retention(
    tmp_path, monkeypatch
):
    app = application(settings(tmp_path, deadline_seconds=480), worker=failed_worker)
    monkeypatch.setattr(routes, "AUTHENTICATED_UPLOAD_TIMEOUT_SECONDS", 0.01)
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", "") == "/api/snapshots" and "POST" in r.methods
    )
    boundary = "offline-partial-upload"
    parts = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="snapshot"; '
            'filename="snapshot.pickle"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode(),
        b"x" * 65536,
    ]

    async def receive():
        if parts:
            return {"type": "http.request", "body": parts.pop(0), "more_body": True}
        await asyncio.sleep(0.05)
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "scheme": "http",
        "path": "/api/snapshots",
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1),
        "headers": [
            (b"host", b"testserver"),
            (b"authorization", f"Bearer {TOKEN}".encode()),
            (b"content-type", f"multipart/form-data; boundary={boundary}".encode()),
        ],
        "state": {"owner": "a" * 64},
    }
    with TestClient(app):
        with pytest.raises(HTTPException) as error:
            asyncio.run(endpoint(Request(scope, receive=receive)))
        assert error.value.status_code == 408
        manager = app.state.snapshots
        with sqlite3.connect(manager.registry) as connection:
            row = connection.execute("select id,status,created_at from snapshots").fetchone()
            assert row[1] == "timeout"
            assert (
                connection.execute(
                    "select count(*) from snapshots where status in ('receiving','queued','running')"
                ).fetchone()[0]
                == 0
            )
        partial = manager.root / row[0] / "snapshot.pickle"
        assert partial.stat().st_size == 65536
        assert not (partial.parent / "worker.log").exists()
        assert not (partial.parent / "private/calls.db").exists()
        monkeypatch.setattr(manager, "clock", lambda: row[2] + RETENTION_SECONDS - 1)
        manager.cleanup()
        assert partial.exists()
        monkeypatch.setattr(manager, "clock", lambda: row[2] + RETENTION_SECONDS + 1)
        manager.cleanup()
        assert not partial.parent.exists()
        with sqlite3.connect(manager.registry) as connection:
            assert connection.execute("select count(*) from snapshots").fetchone()[0] == 0
