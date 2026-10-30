"""Stored captures use existing admission and isolated workers; no live inference."""

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from test_snapshot_routes import TOKEN, application, settings, wait_status

from headroom.api import snapshot_examples as examples
from headroom.api import snapshot_routes as routes


@pytest.fixture
def capture(tmp_path, monkeypatch):
    contents = {
        "snapshot.pickle": b"opaque snapshot",
        "traceback.txt": b"a traceback",
        "source.py": b"raise RuntimeError('never execute')",
    }
    directory = tmp_path / "captures" / "sample"
    directory.mkdir(parents=True)
    files = []
    for name, raw in contents.items():
        path = directory / name
        path.write_bytes(raw)
        files.append(
            (
                name,
                examples.CaptureFile(
                    str(path.relative_to(tmp_path)), len(raw), hashlib.sha256(raw).hexdigest()
                ),
            )
        )
    example = examples.SnapshotExample(
        "s2-capacity", "Stored test capture", "New analysis of stored data", tuple(files)
    )
    monkeypatch.setattr(examples, "EXAMPLES", (example,))
    return example, directory, contents


def post(client, body=None, **kwargs):
    kwargs.setdefault("headers", {"Authorization": "Bearer " + TOKEN})
    return client.post(
        "/api/snapshots/from-example", json=body or {"example_id": "s2-capacity"}, **kwargs
    )


def test_stored_capture_fresh_analysis_uses_private_copy_and_existing_worker(tmp_path, capture):
    example, directory, contents = capture
    app = application(settings(tmp_path))
    with TestClient(app) as client:
        listed = client.get("/api/snapshot-examples").json()["examples"]
        assert listed == [
            {
                "id": example.id,
                "label": example.label,
                "description": example.description,
                "snapshot_bytes": 15,
                "available": True,
                "reason": None,
            }
        ]
        assert str(tmp_path) not in json.dumps(listed) and "sha256" not in json.dumps(listed)
        first = post(client)
        assert first.status_code == 202, first.text
        identifier = first.json()["run_id"]
        result = wait_status(client, identifier)
        assert result["status"] == "completed"
        assert result["result"]["provenance"] == "offline_fixture"
        job = app.state.snapshots.root / identifier
        assert (job / "worker-observed.json").exists()
        for name, raw in contents.items():
            assert (directory / name).read_bytes() == raw
            assert (job / name).read_bytes() == raw
            assert os.stat(job / name).st_ino != os.stat(directory / name).st_ino
            assert os.stat(job / name).st_mode & 0o777 == 0o600
        stranger = TestClient(app)
        # Reuse the already running app without closing its lifespan. A different
        # browser cookie cannot read a paid analysis result.
        assert stranger.get(first.json()["run_url"]).status_code == 404
        stranger.close()
        second = post(client)
        assert second.status_code == 202
        assert second.json()["run_id"] != identifier
        wait_status(client, second.json()["run_id"])


@pytest.mark.parametrize(
    "body,headers,status",
    [
        (b'{"example_id":"s2-capacity"}', {}, 401),
        (b'{"example_id":"s2-capacity"}', {"Authorization": "Bearer wrong"}, 401),
        (b'{"example_id":"s2-capacity"}', {"Origin": "https://other.example"}, 403),
        (b'{"example_id":"s2-capacity"}', {"Content-Type": "text/plain"}, 415),
        (b'{"example_id":"s2-capacity","path":"/private"}', {}, 400),
        (b'{"example_id":"s2-capacity","example_id":"nanogpt"}', {}, 400),
        (b'{"example_id":true}', {}, 400),
        (b'{"example_id":"../../private"}', {}, 404),
        (b"{bad", {}, 400),
        (b" " * 1025, {}, 413),
    ],
)
def test_rejected_requests_never_reserve_or_dispatch(tmp_path, capture, body, headers, status):
    app = application(settings(tmp_path))
    with TestClient(app) as client:
        actual = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
        if status == 401 and not headers:
            actual.pop("Authorization")
        actual.update(headers)
        response = client.post("/api/snapshots/from-example", content=body, headers=actual)
        assert response.status_code == status, response.text
        with sqlite3.connect(app.state.snapshots.registry) as db:
            assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


@pytest.mark.parametrize(
    "unsafe", ["missing", "file_symlink", "directory_symlink", "hardlink", "fifo", "changed"]
)
def test_unsafe_or_modified_capture_never_starts_worker(tmp_path, capture, unsafe):
    _example, directory, contents = capture
    original = directory / "snapshot.pickle"
    outside = tmp_path / "outside.pickle"
    if unsafe == "directory_symlink":
        moved = directory.with_name("moved")
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
    elif unsafe == "changed":
        original.write_bytes(b"x" * len(contents["snapshot.pickle"]))
    else:
        original.unlink()
        if unsafe == "file_symlink":
            outside.write_bytes(contents["snapshot.pickle"])
            original.symlink_to(outside)
        elif unsafe == "hardlink":
            outside.write_bytes(contents["snapshot.pickle"])
            os.link(outside, original)
        elif unsafe == "fifo":
            os.mkfifo(original)
    app = application(settings(tmp_path))
    with TestClient(app) as client:
        listed = client.get("/api/snapshot-examples").json()["examples"][0]
        assert listed["available"] is (unsafe == "changed")
        response = post(client)
        assert response.status_code == 409, response.text
        assert str(tmp_path) not in response.text
        with sqlite3.connect(app.state.snapshots.registry) as db:
            assert db.execute("SELECT status FROM snapshots").fetchall() == [("failed",)]
        assert not list(app.state.snapshots.root.rglob("worker-observed.json"))


def test_copy_deadline_cancellation_and_existing_destination_are_bounded(tmp_path, capture):
    example, directory, contents = capture
    target = tmp_path / "target"
    target.mkdir()
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(ValueError, match="cancelled"):
        examples.copy_example(
            tmp_path, target, example, cancelled=cancelled, deadline=time.time() + 10
        )
    assert (directory / "snapshot.pickle").read_bytes() == contents["snapshot.pickle"]
    (target / "snapshot.pickle").unlink()
    cancelled.clear()
    with pytest.raises(TimeoutError):
        examples.copy_example(tmp_path, target, example, cancelled=cancelled, deadline=0)
    (target / "snapshot.pickle").write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        examples.copy_example(
            tmp_path, target, example, cancelled=cancelled, deadline=time.time() + 10
        )
    assert (target / "snapshot.pickle").read_bytes() == b"preserve"


def test_cancelled_request_joins_copy_before_failure_and_never_queues(
    tmp_path, capture, monkeypatch
):
    started, finished = threading.Event(), threading.Event()

    def copying(_root, target, _example, *, cancelled, **_kwargs):
        (target / "partial").write_bytes(b"bounded")
        started.set()
        assert cancelled.wait(3)
        finished.set()
        raise ValueError("cancelled")

    monkeypatch.setattr(routes, "copy_example", copying)
    app = application(settings(tmp_path))
    endpoint = next(
        route.endpoint for route in app.routes if route.path == "/api/snapshots/from-example"
    )

    async def exercise():
        body = b'{"example_id":"s2-capacity"}'
        delivered = False

        async def receive():
            nonlocal delivered
            assert not delivered
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "scheme": "http",
                "server": ("testserver", 80),
                "path": "/api/snapshots/from-example",
                "query_string": b"",
                "client": ("127.0.0.1", 123),
                "headers": [
                    (b"authorization", ("Bearer " + TOKEN).encode()),
                    (b"content-type", b"application/json"),
                ],
                "state": {"owner": "a" * 64},
            },
            receive,
        )
        task = asyncio.create_task(endpoint(request))
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()

    manager = app.state.snapshots
    manager.start()
    try:
        asyncio.run(exercise())
        with sqlite3.connect(manager.registry) as db:
            assert db.execute("SELECT status FROM snapshots").fetchall() == [("failed",)]
        assert not list(manager.root.rglob("worker-observed.json"))
    finally:
        manager.close()


def test_copy_rejects_source_mutation_after_read(tmp_path, capture, monkeypatch):
    example, directory, contents = capture
    target = tmp_path / "target"
    target.mkdir()
    read = os.read
    changed = False

    def mutate_after_read(descriptor, size):
        nonlocal changed
        data = read(descriptor, size)
        if data and not changed:
            changed = True
            # Same content/size/hash, but mutation while reading still invalidates
            # the original file identity observation via ctime/mtime.
            (directory / "snapshot.pickle").write_bytes(contents["snapshot.pickle"])
        return data

    monkeypatch.setattr(examples.os, "read", mutate_after_read)
    with pytest.raises(ValueError, match="changed"):
        examples.copy_example(
            tmp_path, target, example, cancelled=threading.Event(), deadline=time.time() + 10
        )
    assert changed
