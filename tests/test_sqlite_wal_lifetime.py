"""Offline multi-process regression for active Store WAL ownership; no model/GPU."""

import hashlib
import json
import select
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from headroom.api.app import COOKIE, ApiSettings, create_app
from headroom.api.diagnosis_evidence import load_initial_diagnosis
from headroom.api.snapshot_queue import SnapshotQueue

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="POSIX SQLite WAL regression")

WORKER = """
import sys
from headroom.store.db import Store
store = Store(sys.argv[1])
store.update_run(sys.argv[2], status="failed", reason="Offline fixture")
print("ready", flush=True)
sys.stdin.readline()
store.close()
"""


def _offline_worker(*args, **kwargs):
    raise AssertionError("No queued worker, model or GPU should execute")


def _wait_ready(process):
    assert select.select([process.stdout], [], [], 10)[0], "worker startup timed out"
    assert process.stdout.readline() == "ready\n"


def test_get_evidence_and_download_preserve_wal_across_worker_close(tmp_path, monkeypatch):
    monkeypatch.delenv("HEADROOM_BUDGET_DB_PATH", raising=False)
    monkeypatch.delenv("HEADROOM_VERIFIED_RUNS_ENABLED", raising=False)
    project = tmp_path / "project"
    runs = project / "runs"
    settings = ApiSettings(
        project_root=project,
        db_path=runs / "public-api/headroom.db",
        run_root=runs / "public-api/jobs",
        data_root=runs / "public-api/submissions",
        web_dist=tmp_path / "dist",
        run_submissions_enabled=False,
        snapshot_submissions_enabled=False,
    )
    app = create_app(settings, worker=_offline_worker)
    token, run_id = "a" * 32, uuid4().hex
    directory = settings.run_root / run_id
    directory.mkdir(parents=True)
    (directory / "report.json").write_text(json.dumps({"provenance": "offline_fixture"}))
    process = None
    with TestClient(app) as client:
        client.cookies.set(COOKIE, token)
        store = app.state.store
        store.create_run(
            run_id,
            status="running",
            api_owner=hashlib.sha256(token.encode()).hexdigest(),
            api_worker_finished=False,
            run_dir=str(directory),
            provenance="offline_fixture",
        )
        process = subprocess.Popen(
            [sys.executable, "-c", WORKER, str(settings.db_path), run_id],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            _wait_ready(process)
            wal = Path(str(settings.db_path) + "-wal")
            inode = wal.stat().st_ino
            # Reaches the real diagnosis loader: both paths are under project/runs.
            for _ in range(2):
                response = client.get(f"/api/runs/{run_id}")
                assert response.status_code == 200
                assert response.json()["diagnosis_evidence"] is None
                assert client.get(f"/api/runs/{run_id}/report.json").json() == {
                    "provenance": "offline_fixture"
                }
            process.stdin.write("close\n")
            process.stdin.flush()
            assert process.wait(10) == 0, process.stderr.read()
            # An unrelated raw fd close used to release Store's POSIX locks;
            # the child then deleted this WAL while the parent still used it.
            assert wal.exists(), "worker removed a WAL still used by the parent Store"
            assert wal.stat().st_ino == inode
            store.update_run(run_id, api_worker_finished=True, api_cleanup_verified=True)
            for _ in range(3):
                response = client.get(f"/api/runs/{run_id}")
                assert response.status_code == 200
                assert response.json()["api_worker_finished"] is True
                assert response.json()["api_cleanup_verified"] is True
                assert client.get(f"/api/runs/{run_id}/report.json").status_code == 200
            with closing(sqlite3.connect(settings.db_path.as_uri() + "?mode=ro", uri=True)) as db:
                saved = json.loads(
                    db.execute("SELECT data_json FROM runs WHERE id=?", (run_id,)).fetchone()[0]
                )
                assert saved["api_worker_finished"] is True
                assert saved["api_cleanup_verified"] is True
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(10)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
    with closing(sqlite3.connect(settings.db_path.as_uri() + "?mode=ro", uri=True)) as db:
        saved = json.loads(
            db.execute("SELECT data_json FROM runs WHERE id=?", (run_id,)).fetchone()[0]
        )
        assert saved["api_worker_finished"] is True and saved["api_cleanup_verified"] is True


@pytest.mark.parametrize("kind", ["symlink", "directory", "oversize"])
def test_database_validation_rejects_nonregular_unbounded_without_raw_open(tmp_path, kind):
    project = tmp_path / "project"
    run_dir = project / "runs/jobs" / uuid4().hex
    run_dir.mkdir(parents=True)
    database = project / "runs/store.db"
    if kind == "directory":
        database.mkdir()
    elif kind == "symlink":
        target = project / "target"
        target.write_text("not a database")
        database.symlink_to(target)
    else:
        with database.open("wb") as handle:
            handle.truncate(1024 * 1024 * 1024 + 1)
    assert load_initial_diagnosis(run_dir, database=database, project_root=project) is None


LOCK_PROBE = """
import sqlite3, sys
db = sqlite3.connect(sys.argv[1], timeout=0)
try:
    db.execute("BEGIN EXCLUSIVE")
except sqlite3.OperationalError as error:
    assert "locked" in str(error)
    print("blocked")
else:
    print("acquired")
    db.rollback()
finally:
    db.close()
"""


def test_snapshot_registry_validation_preserves_other_sqlite_connection_lock(tmp_path):
    settings = ApiSettings(project_root=tmp_path, snapshot_submissions_enabled=False)
    queue = SnapshotQueue(settings)
    queue.registry.parent.mkdir(parents=True)
    with closing(sqlite3.connect(queue.registry)) as outer:
        outer.execute("CREATE TABLE sentinel (value INTEGER)")
        outer.execute("INSERT INTO sentinel VALUES (1)")
        outer.commit()
        outer.execute("BEGIN")
        assert outer.execute("SELECT value FROM sentinel").fetchone()[0] == 1
        with queue._connect(read_only=True) as reader:
            assert reader.execute("SELECT value FROM sentinel").fetchone()[0] == 1
        probe = subprocess.run(
            [sys.executable, "-c", LOCK_PROBE, str(queue.registry)],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        assert probe.stdout.strip() == "blocked", (
            "registry validation released another live SQLite connection's read lock"
        )
        outer.rollback()


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_snapshot_registry_still_rejects_unsafe_leaf(tmp_path, kind):
    queue = SnapshotQueue(ApiSettings(project_root=tmp_path))
    queue.registry.parent.mkdir(parents=True)
    if kind == "directory":
        queue.registry.mkdir()
    else:
        target = tmp_path / "target"
        target.write_bytes(b"")
        queue.registry.symlink_to(target)
    with pytest.raises(ValueError, match="Invalid snapshot registry"), queue._connect():
        pytest.fail("unsafe registry opened")
