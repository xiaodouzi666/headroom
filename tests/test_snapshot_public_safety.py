"""Public snapshot ingress/resource checks; explicit offline fixtures, no model/GPU."""

import asyncio
import ctypes
import importlib.util
import json
import multiprocessing
import os
import resource
import signal
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from test_snapshot_routes import TOKEN, settings

from headroom.api.snapshot_queue import (
    WORKER_FILE_BYTES,
    WORKER_MEMORY_BYTES,
    SnapshotQueue,
    _bounded_job,
    _child_entry,
)
from headroom.api.snapshot_routes import register_snapshot_routes


class OfflineAllocation:
    """Only the admission protocol is simulated; no live financial claim is made."""

    available = True

    def __init__(self, root):
        self.project_root = root.resolve()
        self.profile_path = str(root / "offline-profile.json")

    def claim(self, *_args):
        raise AssertionError("HTTP-only fixture must never claim or dispatch")


def hold_dispatch(self):
    self._stop.wait(20)


def public_app(tmp_path, monkeypatch, *, bound=True, enabled=True):
    monkeypatch.setattr(SnapshotQueue, "_dispatch_loop", hold_dispatch)
    config = settings(
        tmp_path,
        public_host="testserver",
        snapshot_submissions_enabled=enabled,
        run_root=tmp_path / "runs/public-api/jobs",
        deadline_seconds=2,
    )
    manager = None

    @asynccontextmanager
    async def lifespan(_):
        manager.start()
        yield
        manager.close()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def session(request: Request, call_next):
        request.state.owner = "a" * 64
        return await call_next(request)

    manager = register_snapshot_routes(
        app, config, public_allocation=OfflineAllocation(tmp_path) if bound else None
    )
    app.state.manager = manager
    return app


def post(client, *, headers=None, **kwargs):
    return client.post(
        "/api/snapshots",
        files={"snapshot": ("sample.pickle", b"primitive snapshot")},
        headers=headers,
        **kwargs,
    )


def rows(manager):
    with sqlite3.connect(manager.registry) as db:
        return db.execute("SELECT count(*) FROM snapshots").fetchone()[0]


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"Authorization": ""},
        {"Authorization": "Bearer wrong"},
        {"Authorization": "Basic ignored"},
        [("Authorization", f"Bearer {TOKEN}"), ("Authorization", f"Bearer {TOKEN}")],
    ],
)
def test_auth_rejection_before_body_admission_and_files(tmp_path, monkeypatch, headers):
    app = public_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = post(client, headers=headers)
        assert response.status_code == 401
        assert rows(app.state.manager) == 0
        assert list(app.state.manager.root.iterdir()) == []


@pytest.mark.parametrize("bound,enabled", [(False, True), (True, False)])
def test_missing_public_binding_or_switch_rejects(tmp_path, monkeypatch, bound, enabled):
    app = public_app(tmp_path, monkeypatch, bound=bound, enabled=enabled)
    with TestClient(app) as client:
        assert post(client, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 503
        assert rows(app.state.manager) == 0


def test_public_upload_scope_shared_storage_and_no_http_funding(tmp_path, monkeypatch):
    app = public_app(tmp_path, monkeypatch)
    auth = {"Authorization": f"Bearer {TOKEN}"}
    with TestClient(app) as client:
        response = post(client, headers=auth)
        assert response.status_code == 202
        manager = app.state.manager
        assert manager.root == tmp_path / "runs/public-api/snapshots"
        assert manager.registry.parent == tmp_path / "runs/public-api"
        assert (manager.storage_root / ".headroom-public-storage").is_file()
        run_id = response.json()["run_id"]
        assert (manager.root / run_id / "snapshot.pickle").read_bytes() == b"primitive snapshot"
        response = post(client, headers=auth, data={"funding": "demo", "budget_usd": "900"})
        assert response.status_code == 400
        assert not (tmp_path / ".cache").exists()


def test_storage_full_rejects_before_persistent_admission(tmp_path, monkeypatch):
    import headroom.lab.storage_budget as storage

    app = public_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        manager = app.state.manager
        # Small synthetic threshold, not a disk-filling test.
        monkeypatch.setattr(storage, "MAX_STORAGE_BYTES", 1024)
        monkeypatch.setattr(storage, "LAB_RESERVATION_BYTES", 1024)
        before = manager.registry.read_bytes()
        for _ in range(4):
            assert post(client, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 503
        assert rows(manager) == 0
        assert manager.registry.read_bytes() == before
        assert list(manager.root.iterdir()) == []


def test_capacity_shared_by_receiving_and_waiting_and_judge_no_hourly(tmp_path, monkeypatch):
    app = public_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for _ in range(3):
            assert post(client, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 202
        assert post(client, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 429
        assert rows(app.state.manager) == 3


def test_slow_body_timeout_and_cancel_release_receiving_capacity(tmp_path, monkeypatch):
    import headroom.api.snapshot_routes as routes

    app = public_app(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, "UPLOAD_TIMEOUT_SECONDS", 0.01)
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", "") == "/api/snapshots" and "POST" in r.methods
    )
    with TestClient(app):
        boundary = "offline-boundary"

        async def receive():
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
        request = Request(scope, receive=receive)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as error:
            asyncio.run(endpoint(request))
        assert error.value.status_code == 408
        with app.state.manager._connect() as db:
            assert db.execute("SELECT status FROM snapshots").fetchone()[0] == "timeout"


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo", "bytes", "entries"])
def test_worker_output_rejects_unsafe_or_excessive_files(tmp_path, monkeypatch, kind):
    import headroom.api.snapshot_queue as queue

    job = tmp_path / "job"
    job.mkdir()
    if kind == "symlink":
        (job / "escape").symlink_to(tmp_path)
    elif kind == "hardlink":
        (job / "original").write_text("x")
        os.link(job / "original", job / "linked")
    elif kind == "fifo":
        os.mkfifo(job / "fifo")
    elif kind == "bytes":
        monkeypatch.setattr(queue, "WORKER_OUTPUT_BYTES", 1)
        (job / "bounded").write_bytes(b"xx")
    else:
        monkeypatch.setattr(queue, "WORKER_ENTRIES", 1)
        (job / "one").mkdir()
        (job / "two").mkdir()
    with pytest.raises(ValueError):
        _bounded_job(job)


def limited_worker(request, *, run_root, run_id):
    job = Path(run_root) / run_id
    probe = job / "sparse-limit-probe"
    limited = False
    with probe.open("wb") as handle:
        try:
            os.ftruncate(handle.fileno(), WORKER_FILE_BYTES + 1)
        except OSError:
            limited = True
    probe.unlink()
    from transformers.utils import is_flax_available, is_tf_available, is_torch_available

    (job / "limits.json").write_text(
        json.dumps(
            {
                "fsize": resource.getrlimit(resource.RLIMIT_FSIZE),
                "as": resource.getrlimit(resource.RLIMIT_AS),
                "cpu": resource.getrlimit(resource.RLIMIT_CPU),
                "cuda": os.environ["CUDA_VISIBLE_DEVICES"],
                "no_new_privs": ctypes.CDLL(None).prctl(39, 0, 0, 0, 0),
                "framework_env": {
                    name: os.environ.get(name) for name in ("USE_TORCH", "USE_TF", "USE_FLAX")
                },
                "framework_available": [
                    is_torch_available(),
                    is_tf_available(),
                    is_flax_available(),
                ],
                "file_limit_enforced": limited,
            }
        )
    )
    return {"status": "completed"}


def test_real_cpu_spawn_file_limit_and_no_cuda_visibility(tmp_path):
    run_id = "1" * 32
    (tmp_path / run_id).mkdir()
    ctx = multiprocessing.get_context("spawn")
    receiver, sender = ctx.Pipe()
    process = ctx.Process(
        target=_child_entry,
        args=(
            limited_worker,
            {"budget_usd": ".30", "runtime_profile": None},
            str(tmp_path),
            run_id,
            sender,
            os.getpid(),
            None,
            str(tmp_path),
            True,
        ),
    )
    ready = False
    try:
        process.start()
        sender.close()
        assert receiver.poll(15)
        assert receiver.recv() == "ready"
        ready = True
        receiver.send("proceed")
        assert receiver.poll(15)
        assert receiver.recv() == "completed"
        result = json.loads((tmp_path / run_id / "limits.json").read_text())
        assert result["fsize"] == [WORKER_FILE_BYTES] * 2
        assert result["as"] == [WORKER_MEMORY_BYTES] * 2
        assert result["cpu"] == [60, 60]
        assert result["cuda"] == ""
        assert result["no_new_privs"] == 1
        assert result["framework_env"] == dict.fromkeys(("USE_TORCH", "USE_TF", "USE_FLAX"), "0")
        assert result["framework_available"] == [False, False, False]
        assert result["file_limit_enforced"]
    finally:
        if process.pid:
            if ready:
                os.killpg(process.pid, signal.SIGKILL)
            elif process.is_alive():
                process.kill()
            process.join(3)
        receiver.close()
        sender.close()
    assert not process.is_alive()


@pytest.mark.parametrize("value", ["true", "invalid"])
def test_public_launcher_refuses_snapshot_without_reviewed_pool(tmp_path, monkeypatch, value):
    path = Path(__file__).resolve().parents[1] / "scripts/serve_public.py"
    spec = importlib.util.spec_from_file_location("offline_snapshot_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.setattr(launcher, "__file__", str(tmp_path / "scripts/serve_public.py"))
    monkeypatch.setenv("HEADROOM_PUBLIC_HOST", "testserver")
    monkeypatch.setenv("HEADROOM_RUN_SUBMISSIONS_ENABLED", "false")
    monkeypatch.setenv("HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED", value)
    monkeypatch.delenv("HEADROOM_TRUST_CLOUDFLARED", raising=False)
    with pytest.raises(SystemExit):
        launcher.main()
    assert not (tmp_path / "runs").exists()


def test_config_advertises_required_token_without_hiding_enabled_form(tmp_path, monkeypatch):
    from test_snapshot_integration import OfflineAvailability, ordinary_worker

    from headroom.api.app import ApiSettings, create_app

    monkeypatch.setattr(SnapshotQueue, "_dispatch_loop", hold_dispatch)
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios/INDEX.yaml").write_text('{"scenarios":[]}')
    config = ApiSettings(
        project_root=tmp_path,
        public_host="testserver",
        judge_token=TOKEN,
        snapshot_submissions_enabled=True,
        run_submissions_enabled=True,
        verified_runs_enabled=False,
        run_root=tmp_path / "runs/public-api/jobs",
    )
    app = create_app(
        config,
        worker=ordinary_worker,
        availability_monitor=OfflineAvailability(),
        snapshot_public_allocation=OfflineAllocation(tmp_path),
    )
    with TestClient(app) as client:
        response = client.get("/api/config")
        assert response.status_code == 200
        snapshot = response.json()["snapshot_submissions"]
        assert snapshot["enabled"] is True
        assert snapshot["requires_judge_token"] is True
        assert snapshot["runs_per_ip_per_hour"] is None
        assert post(client).status_code == 401


def test_public_upload_cancel_and_disconnect_mark_terminal(tmp_path, monkeypatch):
    app = public_app(tmp_path, monkeypatch)
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", "") == "/api/snapshots" and "POST" in r.methods
    )
    with TestClient(app):
        from fastapi import HTTPException

        for cancelled in (False, True):

            async def receive(cancelled=cancelled):
                if cancelled:
                    raise asyncio.CancelledError()
                return {"type": "http.disconnect"}

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
                    (b"content-type", b"multipart/form-data; boundary=offline"),
                ],
                "state": {"owner": "a" * 64},
            }
            request = Request(scope, receive=receive)
            with pytest.raises(asyncio.CancelledError if cancelled else HTTPException):
                asyncio.run(endpoint(request))
        with app.state.manager._connect() as db:
            assert [row[0] for row in db.execute("SELECT status FROM snapshots")] == ["failed"] * 2


def test_cancellation_during_storage_census_does_not_leak_receiving_slot(tmp_path, monkeypatch):
    app = public_app(tmp_path, monkeypatch)
    endpoint = next(
        r.endpoint
        for r in app.routes
        if getattr(r, "path", "") == "/api/snapshots" and "POST" in r.methods
    )
    manager = app.state.manager
    original = manager.reserve

    def delayed(*args, **kwargs):
        time.sleep(0.03)
        return original(*args, **kwargs)

    monkeypatch.setattr(manager, "reserve", delayed)

    async def cancelled_request():
        request = Request(
            {
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
                    (b"content-type", b"multipart/form-data; boundary=offline"),
                ],
                "state": {"owner": "a" * 64},
            }
        )
        task = asyncio.create_task(endpoint(request))
        await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with TestClient(app):
        asyncio.run(cancelled_request())
        with manager._connect() as db:
            assert db.execute("SELECT status FROM snapshots").fetchone()[0] == "failed"


def accounting_worker(request, *, run_root, run_id):
    """Real bound ledger in a CPU child; no SDK/provider or GPU is invoked."""
    from headroom.acceptance.snapshot_binding import current_snapshot_budget_factory
    from headroom.runtime import read_live_profile
    from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest

    request = SnapshotDiagnosisRequest(**vars(request))
    factory = current_snapshot_budget_factory()
    assert factory is not None
    ledger = factory(run_id, request, read_live_profile(request.runtime_profile))
    ledger.open_run(run_id, request.budget_usd)
    ledger.reserve(run_id, "offline-attempt-" + run_id, ".02", dispatched=False)
    ledger.mark_dispatched(run_id, "offline-attempt-" + run_id)
    ledger.settle(run_id, "offline-attempt-" + run_id, ".01")
    ledger.close_run(run_id)
    directory = Path(run_root) / run_id / "private"
    directory.mkdir()
    (directory / "cleanup.json").write_text(
        json.dumps(
            {
                "schema": "headroom.snapshot-cleanup.v1",
                "run_id": run_id,
                "cleanup_verified": True,
            }
        )
    )
    return {"status": "completed"}


def unknown_accounting_worker(request, *, run_root, run_id):
    """Leave an unknown dispatched attempt in the temporary pool on purpose."""
    from headroom.acceptance.snapshot_binding import current_snapshot_budget_factory
    from headroom.runtime import read_live_profile
    from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest

    request = SnapshotDiagnosisRequest(**vars(request))
    ledger = current_snapshot_budget_factory()(
        run_id, request, read_live_profile(request.runtime_profile)
    )
    ledger.open_run(run_id, request.budget_usd)
    ledger.reserve(run_id, "offline-unknown", ".02", dispatched=False)
    ledger.mark_dispatched(run_id, "offline-unknown")
    # No zero-cost substitution or fabricated final accounting.
    return {"status": "failed"}


@pytest.fixture
def public_pool(tmp_path):
    # Reuse only the synthetic fixture body. The global test runner denies real
    # secrets/databases/network/GPU in this process and all spawned children.
    from test_judge_binding import pool as fixture

    return fixture.__wrapped__(tmp_path)


@pytest.mark.parametrize("unresolved", [False, True])
def test_real_http_spawn_snapshot_context_uses_existing_pool(public_pool, monkeypatch, unresolved):
    from headroom.acceptance import judge_binding as judge
    from headroom.acceptance.allocation import _budget_state
    from headroom.acceptance.snapshot_public_binding import SnapshotPublicAllocation

    owner = judge.JudgeAllocation(public_pool["path"], project_root=public_pool["root"])
    allocation = SnapshotPublicAllocation(owner, project_root=public_pool["root"])
    original_receipt = public_pool["path"].read_bytes()
    original_profile = Path(allocation.profile_path).read_bytes()
    forbidden_db = public_pool["root"] / "wrong-environment.db"
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(forbidden_db))
    config = settings(
        public_pool["root"],
        public_host="testserver",
        run_root=public_pool["root"] / "runs/public-api/jobs",
        deadline_seconds=20,
    )
    manager = None

    @asynccontextmanager
    async def lifespan(_):
        manager.start()
        yield
        manager.close()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def session(request: Request, call_next):
        request.state.owner = "a" * 64
        return await call_next(request)

    manager = register_snapshot_routes(
        app,
        config,
        public_allocation=allocation,
        worker=unknown_accounting_worker if unresolved else accounting_worker,
    )
    with TestClient(app) as client:
        for index in range(1 if unresolved else 2):
            response = post(client, headers={"Authorization": f"Bearer {TOKEN}"})
            assert response.status_code == 202, response.text
            identifier = response.json()["run_id"]
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                row = client.get(f"/api/snapshots/{identifier}").json()
                if row["status"] not in {"queued", "receiving", "running"}:
                    break
                time.sleep(0.02)
            assert row["status"] == ("failed" if unresolved else "completed"), row
        if unresolved:
            assert not allocation.available
            assert post(client, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 503
            assert manager._stop.is_set()
        else:
            from decimal import Decimal

            assert _budget_state(public_pool["receipt"])["charged"] == Decimal(".02")
            assert allocation.available
    assert public_pool["path"].read_bytes() == original_receipt
    assert Path(allocation.profile_path).read_bytes() == original_profile
    assert not forbidden_db.exists()


def test_launcher_explicit_enable_routes_only_to_existing_judge_pool(public_pool, monkeypatch):
    from types import SimpleNamespace

    from headroom.acceptance import demo_binding
    from headroom.acceptance.snapshot_public_binding import SnapshotPublicAllocation

    path = Path(__file__).resolve().parents[1] / "scripts/serve_public.py"
    spec = importlib.util.spec_from_file_location("offline_enabled_snapshot_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    root = public_pool["root"]
    monkeypatch.setattr(launcher, "__file__", str(root / "scripts/serve_public.py"))
    source = root / "public-evidence"
    source.mkdir()
    (source / "public-evaluations.json").write_text('{"version":1,"campaigns":[]}')
    monkeypatch.setattr(launcher, "_registry", lambda _root: [])
    old_db = str(root / "old-demo.db")
    demo = SimpleNamespace(
        root=root,
        receipt={
            "ledger_path": old_db,
            "amounts": {"daily_limit_usd": "6.43"},
            "profile_path": str(root / "old-demo-profile.json"),
        },
    )
    monkeypatch.setattr(demo_binding, "DemoAllocation", lambda *_args, **_kwargs: demo)
    for name, value in {
        "HEADROOM_PUBLIC_HOST": "testserver",
        "HEADROOM_RUN_SUBMISSIONS_ENABLED": "true",
        "HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED": "true",
        "HEADROOM_JUDGE_TOKEN": TOKEN,
        "HEADROOM_PUBLIC_ALLOCATION_RECEIPT": str(root / "old-demo-receipt.json"),
        "HEADROOM_JUDGE_ALLOCATION_RECEIPT": str(public_pool["path"]),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("HEADROOM_TRUST_CLOUDFLARED", raising=False)
    # Launcher deliberately changes process-local pool selection. Track both
    # names so this simulated startup cannot leak its temporary pool to F3b tests.
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(root / "pre-launch.db"))
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", ".01")
    observed = {}

    def application(config, **kwargs):
        observed.update(config=config, **kwargs)
        return object()

    monkeypatch.setattr(launcher, "create_app", application)
    monkeypatch.setattr(launcher.uvicorn, "run", lambda *_args, **_kwargs: None)
    before = public_pool["path"].read_bytes()
    launcher.main()
    assert observed["config"].snapshot_submissions_enabled is True
    assert observed["demo_allocation"] is demo
    allocation = observed["snapshot_public_allocation"]
    assert isinstance(allocation, SnapshotPublicAllocation)
    assert allocation.owner is observed["judge_allocation"]
    assert allocation.owner.receipt_path == public_pool["path"]
    assert os.environ["HEADROOM_BUDGET_DB_PATH"] == old_db
    assert not Path(old_db).exists()
    assert public_pool["path"].read_bytes() == before


def test_public_restart_retains_legacy_f3b_and_expires_only_new_owned_snapshots(tmp_path):
    old_id, new_id, expired_id = "a" * 32, "b" * 32, "c" * 32
    old = tmp_path / "runs/uploads" / old_id
    old.mkdir(parents=True)
    (old / "historical-evidence.json").write_text("ORIGINAL_F3B_HISTORY")
    os.utime(old, (0, 0))
    old_registry = tmp_path / ".cache/snapshot-admissions.sqlite3"
    old_registry.parent.mkdir()
    old_registry.write_bytes(b"ORIGINAL_LEGACY_REGISTRY_UNTOUCHED")
    config = settings(
        tmp_path, public_host="testserver", run_root=tmp_path / "runs/public-api/jobs"
    )
    manager = SnapshotQueue(config, clock=lambda: 100000.0)
    manager.start(process_jobs=False)
    for identifier in (new_id, expired_id):
        (manager.root / identifier).mkdir()
        (manager.root / identifier / "evidence.json").write_text("new public evidence")
    with manager._connect() as db:
        db.execute(
            "INSERT INTO snapshots VALUES(?,?,?,?,?)",
            (new_id, "a" * 64, "127.0.0.1", 99999.0, "completed"),
        )
        db.execute(
            "INSERT INTO snapshots VALUES(?,?,?,?,?)",
            (expired_id, "a" * 64, "127.0.0.1", 0.0, "completed"),
        )
    manager.close()
    # Simulate an interrupted prior process row, without touching live services.
    with sqlite3.connect(manager.registry) as db:
        db.execute("UPDATE snapshots SET status='running' WHERE id=?", (new_id,))
    restarted = SnapshotQueue(config, clock=lambda: 100000.0)
    restarted.start(process_jobs=False)
    try:
        assert (old / "historical-evidence.json").read_text() == "ORIGINAL_F3B_HISTORY"
        assert old_registry.read_bytes() == b"ORIGINAL_LEGACY_REGISTRY_UNTOUCHED"
        assert (restarted.root / new_id / "evidence.json").is_file()
        assert not (restarted.root / expired_id).exists()
        assert restarted.row_for_owner(new_id, "a" * 64)["status"] == "failed"
        assert restarted.row_for_owner(expired_id, "a" * 64) is None
    finally:
        restarted.close()
