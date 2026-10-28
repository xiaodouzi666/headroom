"""Offline snapshot upload/queue/privacy tests; workers never call a provider or GPU."""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from headroom.api.snapshot_queue import RETENTION_SECONDS, SnapshotAdmissionError, SnapshotQueue
from headroom.api.snapshot_routes import VERIFICATION, public_result, register_snapshot_routes

TOKEN = "j" * 40
FUNNEL_HEADERS = {
    "tailscale-funnel-request": "?1",
    "x-forwarded-proto": "https",
    "x-forwarded-host": "demo.example",
    "x-forwarded-for": "203.0.113.9",
}


def bundle():
    diagnosis = {
        "root_causes": [
            {
                "id": "cause1",
                "title": "Saved activations",
                "category": "activations",
                "bytes_gb": 0.1,
                "evidence_refs": ["stk_0123456789abcdef"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "fix1",
                "type": "code",
                "title": "Checkpoint layers",
                "description": "Use activation checkpointing.",
                "expected_saving_gb": 0.05,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Recompute",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.0},
        "needs_more_info": False,
        "notes": [],
        "invocation_claims": [],
        "invocation_refs": [],
        "evidence_requests": [],
    }
    digest = hashlib.sha256(
        json.dumps(
            diagnosis, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()
    return {
        "kind": "snapshot_diagnosis",
        "provenance": "offline_fixture",
        "verification": dict(VERIFICATION),
        "diagnosis": diagnosis,
        "evidence": {
            "source": "uploaded_snapshot",
            "snapshot_sha256": "a" * 64,
            "analysis": {
                "peak_allocated_bytes": 1234,
                "peak_is_exact": True,
                "category_bytes": {"activations": 1234},
                "warnings": [],
            },
            "stacks": [
                {
                    "id": "stk_0123456789abcdef",
                    "peak_live_bytes": 1234,
                    "lifetime_allocated_bytes": 2468,
                    "frames": [{"filename": "train.py", "line": 10, "name": "forward"}],
                }
            ],
            "diagnosis_binding": {
                "snapshot_sha256": "a" * 64,
                "evidence_json_sha256": "b" * 64,
                "diagnosis_sha256": digest,
            },
        },
        "patch": {"status": "unverified", "diff": "--- a/train.py\n+++ b/train.py\n"},
        "cost_usd": 0.0,
        "error": None,
    }


def completed_worker(request, *, run_root, run_id):
    job = Path(run_root) / run_id
    assert request.snapshot == job / "snapshot.pickle"
    assert Decimal(request.budget_usd) <= Decimal("0.30")
    assert request.snapshot.read_bytes() == b"opaque snapshot"
    # Source is data, never imported/executed.
    if request.source:
        assert "raise" in request.source.read_text()
    (job / "public-report.json").write_text(json.dumps(bundle()))
    # These deliberately private raw files must never be used by download routes.
    for name in ("diagnosis.json", "diagnosis.md", "patch.diff"):
        (job / name).write_text("SECRET RAW FILE /home/private/traceback")
    (job / "worker-observed.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "budget": request.budget_usd,
                "traceback": request.traceback is not None,
                "source": request.source is not None,
            }
        )
    )
    return {"status": "completed"}


def failed_worker(request, *, run_root, run_id):
    raise RuntimeError("private raw exception /home/private/secret")


def waiting_worker(request, *, run_root, run_id):
    job = Path(run_root) / run_id
    (job / "started").write_text(str(os.getpid()))
    while not (job / "release").exists():
        time.sleep(0.02)
    return completed_worker(request, run_root=run_root, run_id=run_id)


def settings(tmp_path, **changes):
    value = {
        "project_root": tmp_path,
        "data_root": tmp_path / "runs/api",
        "deadline_seconds": 8.0,
        "public_run_budget": Decimal("0.30"),
        "runtime_profile": None,
        "run_submissions_enabled": True,
        "snapshot_submissions_enabled": True,
        "public_host": None,
        "trust_tailscale_funnel": False,
        "trust_cloudflared": False,
        "judge_token": TOKEN,
    }
    value.update(changes)
    return SimpleNamespace(**value)


def application(config, worker=completed_worker):
    manager = None

    @asynccontextmanager
    async def lifespan(_app):
        manager.start()
        try:
            yield
        finally:
            manager.close()

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def session(request: Request, call_next):
        cookie = request.cookies.get("session") or uuid4().hex
        request.state.owner = hashlib.sha256(cookie.encode()).hexdigest()
        response = await call_next(request)
        response.set_cookie("session", cookie)
        return response

    manager = register_snapshot_routes(app, config, worker=worker)
    app.state.snapshots = manager
    return app


def upload(client, *, headers=None, extras=False):
    files = {"snapshot": ("../../outside.pickle", b"opaque snapshot", "application/octet-stream")}
    if extras:
        files.update(
            {
                "traceback": ("traceback.txt", b"private traceback", "text/plain"),
                "source": ("source.py", b"raise RuntimeError('must never execute')", "text/plain"),
            }
        )
    return client.post("/api/snapshots", files=files, headers=headers)


def wait_status(client, identifier, terminal=True):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        response = client.get(f"/api/snapshots/{identifier}")
        assert response.status_code == 200, response.text
        value = response.json()
        if value["status"] in (
            {"completed", "failed", "timeout", "cancelled", "needs_human", "budget_exceeded"}
            if terminal
            else {"running"}
        ):
            return value
        time.sleep(0.02)
    pytest.fail("Offline snapshot worker did not reach expected state")


def test_upload_is_isolated_and_only_public_projection_can_be_downloaded(tmp_path):
    app = application(settings(tmp_path))
    with TestClient(app) as client:
        response = upload(client, extras=True)
        assert response.status_code == 202, response.text
        identifier = response.json()["run_id"]
        result = wait_status(client, identifier)
        assert result["status"] == "completed"
        assert set(result) == {
            "run_id",
            "status",
            "created_at",
            "expires_at",
            "result",
            "artifacts",
        }
        assert result["result"]["provenance"] == "offline_fixture"
        assert result["result"]["verification"] == VERIFICATION
        job = app.state.snapshots.root / identifier
        observed = json.loads((job / "worker-observed.json").read_text())
        assert observed["pid"] != os.getpid()
        assert observed["traceback"] is True and observed["source"] is True
        assert not (tmp_path / "outside.pickle").exists()
        assert (job / "snapshot.pickle").stat().st_mode & 0o777 == 0o600
        for kind, artifact in result["artifacts"].items():
            response = client.get(artifact["url"])
            assert response.status_code == 200
            assert "attachment;" in response.headers["content-disposition"]
            assert "SECRET RAW" not in response.text
            assert "/home/" not in response.text
            if kind == "diagnosis_json":
                assert response.json() == result["result"]
            elif kind == "diagnosis_markdown":
                assert "Not run" in response.text and "Offline test fixture" in response.text
        for name in ("snapshot.pickle", "source.py", "traceback.txt", "worker.log", "headroom.db"):
            assert client.get(f"/api/snapshots/{identifier}/download/{name}").status_code == 404
        with sqlite3.connect(app.state.snapshots.registry) as db:
            assert [row[1] for row in db.execute("pragma table_info(snapshots)")] == [
                "id",
                "owner",
                "ip",
                "created_at",
                "status",
            ]
            state = str(db.execute("select * from snapshots").fetchall())
            assert "private traceback" not in state and "raise RuntimeError" not in state


@pytest.mark.parametrize("disabled", ["snapshot_submissions_enabled", "run_submissions_enabled"])
def test_both_pause_flags_reject_before_body_access_or_admission(tmp_path, disabled, monkeypatch):
    app = application(settings(tmp_path, **{disabled: False}))
    with TestClient(app) as client:

        async def forbidden(_self):
            pytest.fail("Disabled uploads must not read request body")
            yield b""

        monkeypatch.setattr(Request, "stream", forbidden)
        response = client.post(
            "/api/snapshots", content=b"invalid body", headers={"Authorization": "Bearer " + TOKEN}
        )
        assert response.status_code == 503
        with sqlite3.connect(app.state.snapshots.registry) as db:
            assert db.execute("select count(*) from snapshots").fetchone()[0] == 0
        assert list(app.state.snapshots.root.iterdir()) == []


def test_judge_does_not_grant_cross_owner_read_access(tmp_path):
    app = application(settings(tmp_path))
    with TestClient(app) as client:
        identifier = upload(client).json()["run_id"]
        result = wait_status(client, identifier)
        client.cookies.clear()
        headers = {"Authorization": "Bearer " + TOKEN}
        assert client.get(f"/api/snapshots/{identifier}", headers=headers).status_code == 404
        assert (
            client.get(result["artifacts"]["diagnosis_json"]["url"], headers=headers).status_code
            == 404
        )


def test_anonymous_two_per_ip_survives_restart_and_judge_can_bypass_only_quota(tmp_path):
    config = settings(tmp_path)
    app = application(config)
    with TestClient(app) as client:
        for _ in range(2):
            response = upload(client)
            assert response.status_code == 202
            wait_status(client, response.json()["run_id"])
        client.cookies.clear()
        assert upload(client).status_code == 429
    with TestClient(application(config)) as client:
        assert upload(client).status_code == 429
        response = upload(client, headers={"Authorization": "Bearer " + TOKEN})
        assert response.status_code == 202
        wait_status(client, response.json()["run_id"])


def test_funnel_client_address_is_validated_before_admission(tmp_path):
    config = settings(tmp_path, public_host="demo.example", trust_tailscale_funnel=True)
    app = application(config)
    with TestClient(app, base_url="https://demo.example", client=("127.0.0.1", 50000)) as client:
        assert upload(client).status_code == 400
        response = upload(client, headers=FUNNEL_HEADERS)
        assert response.status_code == 202
        wait_status(client, response.json()["run_id"])
    with TestClient(
        application(config), base_url="https://demo.example", client=("203.0.113.4", 50000)
    ) as client:
        assert upload(client, headers=FUNNEL_HEADERS).status_code == 403


def test_queue_has_one_active_two_waiting_and_rejects_more(tmp_path):
    app = application(settings(tmp_path), worker=waiting_worker)
    headers = {"Authorization": "Bearer " + TOKEN}
    with TestClient(app) as client:
        ids = []
        for _ in range(3):
            response = upload(client, headers=headers)
            assert response.status_code == 202
            ids.append(response.json()["run_id"])
        wait_status(client, ids[0], terminal=False)
        assert upload(client, headers=headers).status_code == 429
        assert client.get(f"/api/snapshots/{ids[1]}").json()["status"] == "queued"
        assert client.get(f"/api/snapshots/{ids[2]}").json()["status"] == "queued"
        for identifier in ids:
            (app.state.snapshots.root / identifier / "release").touch()
            assert wait_status(client, identifier)["status"] == "completed"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"source": ("x.py", b"pass")}, 400),
        ({"snapshot": ("x", b"")}, 400),
        ({"snapshot": ("x", b"x"), "extra": ("x", b"x")}, 400),
        ({"snapshot": ("x", b"x"), "source": ("x", b"\xff")}, 400),
        ({"snapshot": ("x", b"x"), "traceback": ("x", b"x" * (256 * 1024 + 1))}, 413),
        ({"snapshot": ("x", b"x"), "source": ("x", b"x" * (1024 * 1024 + 1))}, 413),
    ],
)
def test_invalid_multipart_never_dispatches_worker(tmp_path, files, expected):
    app = application(settings(tmp_path), worker=failed_worker)
    with TestClient(app) as client:
        response = client.post("/api/snapshots", files=files)
        assert response.status_code == expected, response.text
        jobs = list(app.state.snapshots.root.iterdir())
        assert len(jobs) == 1
        assert not (jobs[0] / "worker.log").exists()


def test_snapshot_limit_checked_during_stream_not_only_content_length(tmp_path, monkeypatch):
    from headroom.api import snapshot_routes

    monkeypatch.setitem(snapshot_routes.LIMITS, "snapshot", 16)
    app = application(settings(tmp_path), worker=failed_worker)
    with TestClient(app) as client:
        response = client.post("/api/snapshots", files={"snapshot": ("x", b"x" * 17)})
        assert response.status_code == 413
        assert not any(app.state.snapshots.root.glob("*/worker.log"))


def test_malformed_duplicate_truncated_and_oversized_headers_fail_closed(tmp_path):
    app = application(settings(tmp_path), worker=failed_worker)
    token = {"Authorization": "Bearer " + TOKEN}
    with TestClient(app) as client:
        duplicate = [("snapshot", ("one", b"x")), ("snapshot", ("two", b"y"))]
        assert client.post("/api/snapshots", files=duplicate, headers=token).status_code == 400
        for content in (
            b"invalid",
            b'--z\r\nContent-Disposition: form-data; name="snapshot"\r\n\r\nx',
            b'--z\r\nContent-Disposition: form-data; name="snapshot"; filename="' + b"x" * 9000,
        ):
            response = client.post(
                "/api/snapshots",
                content=content,
                headers={**token, "Content-Type": "multipart/form-data; boundary=z"},
            )
            assert response.status_code in {400, 413}
        assert not any(app.state.snapshots.root.glob("*/worker.log"))


def test_timeout_kills_isolated_worker_and_exposes_no_raw_exception(tmp_path):
    app = application(settings(tmp_path, deadline_seconds=0.5), worker=waiting_worker)
    with TestClient(app) as client:
        response = upload(client)
        assert response.status_code == 202
        identifier = response.json()["run_id"]
        result = wait_status(client, identifier)
        assert result["status"] == "timeout"
        assert result["result"] is None and result["artifacts"] == {}
        pidfile = app.state.snapshots.root / identifier / "started"
        if pidfile.exists():
            with pytest.raises(ProcessLookupError):
                os.kill(int(pidfile.read_text()), 0)


def test_worker_failure_and_report_symlink_fail_closed(tmp_path):
    app = application(settings(tmp_path), worker=failed_worker)
    with TestClient(app) as client:
        identifier = upload(client).json()["run_id"]
        result = wait_status(client, identifier)
        assert result["status"] == "failed"
        assert "private raw exception" not in json.dumps(result)
        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps(bundle()))
        (app.state.snapshots.root / identifier / "public-report.json").symlink_to(outside)
        result = client.get(f"/api/snapshots/{identifier}").json()
        assert result["result"] is None and result["artifacts"] == {}


@pytest.mark.parametrize(
    "mutation", ["extra", "binding", "snapshot_binding", "path", "exception", "false_verified"]
)
def test_public_report_schema_rejects_leaks_and_unbound_evidence(mutation):
    value = bundle()
    if mutation == "extra":
        value["private_source"] = "never expose"
    elif mutation == "binding":
        value["diagnosis"]["root_causes"][0]["title"] = "Other diagnosis"
    elif mutation == "snapshot_binding":
        value["evidence"]["diagnosis_binding"]["snapshot_sha256"] = "c" * 64
    elif mutation == "path":
        value["evidence"]["stacks"][0]["frames"][0]["filename"] = "/home/private/train.py"
    elif mutation == "exception":
        value["error"] = "private raw exception /home/private"
    else:
        value["verification"]["status"] = "passed"
    with pytest.raises(ValueError):
        public_result(json.dumps(value).encode())


def test_retention_only_removes_expired_owned_subtrees_and_keeps_quota_metadata(tmp_path):
    clock = [100000.0]
    manager = SnapshotQueue(settings(tmp_path), worker=failed_worker, clock=lambda: clock[0])
    manager.start()
    try:
        identifier, _ = manager.reserve("a" * 64, "203.0.113.1")
        job = manager.root / identifier
        (job / "source.py").write_text("private source")
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep").write_text("untouched")
        (job / "linked").symlink_to(outside, target_is_directory=True)
        unrelated = manager.root / "unrelated"
        unrelated.mkdir()
        clock[0] += RETENTION_SECONDS
        manager.cleanup()
        assert not job.exists()
        assert (outside / "keep").read_text() == "untouched"
        assert unrelated.exists()
        assert manager.row_for_owner(identifier, "a" * 64) is None
        with sqlite3.connect(manager.registry) as db:
            assert db.execute("select count(*) from snapshots").fetchone()[0] == 0
    finally:
        manager.close()


def test_startup_marks_interrupted_work_failed_and_cleans_expired_inputs(tmp_path):
    clock = [100000.0]
    config = settings(tmp_path)
    first = SnapshotQueue(config, worker=failed_worker, clock=lambda: clock[0])
    first.start()
    identifier, _ = first.reserve("a" * 64, "203.0.113.1")
    first.close()
    with sqlite3.connect(first.registry) as db:
        db.execute("update snapshots set status='running'")
    second = SnapshotQueue(config, worker=failed_worker, clock=lambda: clock[0])
    second.start()
    assert second.row_for_owner(identifier, "a" * 64)["status"] == "failed"
    second.reserve("a" * 64, "203.0.113.1")
    with pytest.raises(SnapshotAdmissionError):
        second.reserve("a" * 64, "203.0.113.1")
    second.close()
    clock[0] += RETENTION_SECONDS
    third = SnapshotQueue(config, worker=failed_worker, clock=lambda: clock[0])
    third.start()
    try:
        assert not (third.root / identifier).exists()
    finally:
        third.close()


def test_upload_root_symlink_is_rejected_without_touching_destination(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/uploads").symlink_to(outside, target_is_directory=True)
    manager = SnapshotQueue(settings(tmp_path), worker=failed_worker)
    with pytest.raises(OSError):
        manager.start()
    assert list(outside.iterdir()) == []


def test_upload_timeout_and_disconnect_release_admission_without_dispatch(tmp_path, monkeypatch):
    import asyncio

    from starlette.requests import ClientDisconnect

    app = application(settings(tmp_path, deadline_seconds=0.03), worker=failed_worker)
    with TestClient(app) as client:

        async def slow(_self):
            await asyncio.sleep(1)
            yield b""

        monkeypatch.setattr(Request, "stream", slow)
        response = client.post(
            "/api/snapshots",
            content=b"x",
            headers={"Content-Type": "multipart/form-data; boundary=z"},
        )
        assert response.status_code == 408

        async def disconnected(_self):
            raise ClientDisconnect
            yield b""

        monkeypatch.setattr(Request, "stream", disconnected)
        response = client.post(
            "/api/snapshots",
            content=b"x",
            headers={"Content-Type": "multipart/form-data; boundary=z"},
        )
        assert response.status_code == 400
        with sqlite3.connect(app.state.snapshots.registry) as db:
            assert {row[0] for row in db.execute("select status from snapshots")} == {
                "timeout",
                "failed",
            }
        assert not any(app.state.snapshots.root.glob("*/worker.log"))


def test_declared_total_limit_and_bad_origin_reject_without_upload_directory(tmp_path):
    app = application(settings(tmp_path), worker=failed_worker)
    with TestClient(app) as client:
        response = client.post(
            "/api/snapshots", content=b"x", headers={"Content-Length": str(60 * 1024 * 1024)}
        )
        assert response.status_code == 413
        for origin in ("https://other.example", "https://["):
            assert upload(client, headers={"Origin": origin}).status_code == 403
        assert list(app.state.snapshots.root.iterdir()) == []


def test_diagnosis_absent_allows_unbound_evidence_but_cost_is_not_clipped():
    value = bundle()
    value["diagnosis"] = None
    value["evidence"]["diagnosis_binding"] = None
    value["error"] = "budget_exceeded"
    value["patch"] = {"status": "unavailable", "diff": None}
    value["cost_usd"] = 0.31
    parsed = public_result(json.dumps(value).encode())
    assert parsed["cost_usd"] == 0.31
    assert parsed["evidence"]["diagnosis_binding"] is None


def test_queue_wait_is_inside_total_deadline_and_does_not_reexecute_expired_jobs(tmp_path):
    app = application(settings(tmp_path, deadline_seconds=0.5), worker=waiting_worker)
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer " + TOKEN}
        ids = [upload(client, headers=headers).json()["run_id"] for _ in range(3)]
        for identifier in ids:
            assert wait_status(client, identifier)["status"] == "timeout"
        # Later jobs receive no fresh eight-minute execution window.
        assert not (app.state.snapshots.root / ids[-1] / "started").exists()


def test_retention_runs_with_jobs_disabled_and_other_instance_stays_read_only(tmp_path):
    config = settings(tmp_path)
    clock = [100000.0]
    first = SnapshotQueue(config, worker=failed_worker, clock=lambda: clock[0])
    assert first.start() is True
    assert first.start() is True
    identifier, _ = first.reserve("a" * 64, "203.0.113.1")
    first.fail_upload(identifier)
    other = SnapshotQueue(
        settings(tmp_path, data_root=tmp_path / "different/api"),
        worker=failed_worker,
        clock=lambda: clock[0],
    )
    assert other.registry == first.registry
    assert other.start() is False
    assert other.row_for_owner(identifier, "a" * 64)["status"] == "failed"
    with pytest.raises(SnapshotAdmissionError) as error:
        other.reserve("a" * 64, "203.0.113.1")
    assert error.value.status == 503
    other.close()
    assert first._started is True
    first.close()
    first.close()
    assert other.start(process_jobs=False) is True
    assert other.thread is None and other.expiry_thread.is_alive()
    with pytest.raises(SnapshotAdmissionError):
        other.reserve("a" * 64, "203.0.113.1")
    clock[0] += RETENTION_SECONDS
    other.cleanup()
    assert not (other.root / identifier).exists()
    assert other.row_for_owner(identifier, "a" * 64) is None
    other.close()


def test_core_transport_fields_are_checked_then_projected_out():
    value = {**bundle(), "run_id": "d" * 32, "status": "completed"}
    parsed = public_result(json.dumps(value).encode(), identifier="d" * 32, status="completed")
    assert "run_id" not in parsed and "status" not in parsed
    with pytest.raises(ValueError, match="identity"):
        public_result(json.dumps(value).encode(), identifier="e" * 32, status="completed")
    with pytest.raises(ValueError, match="identity"):
        public_result(json.dumps(value).encode(), identifier="d" * 32, status="timeout")


def test_unknown_measurements_and_absent_frames_remain_unknown():
    value = bundle()
    value["evidence"]["analysis"]["peak_allocated_bytes"] = None
    value["evidence"]["analysis"]["category_bytes"]["activations"] = None
    value["evidence"]["stacks"][0]["frames"][0]["line"] = None
    parsed = public_result(json.dumps(value).encode())
    assert parsed["evidence"]["analysis"]["peak_allocated_bytes"] is None
    assert parsed["evidence"]["stacks"][0]["frames"][0]["line"] is None
    value["evidence"]["stacks"][0]["frames"] = []
    assert public_result(json.dumps(value).encode())["evidence"]["stacks"][0]["frames"] == []


def crashed_parent_worker(request, *, run_root, run_id):
    import subprocess
    import sys

    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (Path(run_root) / run_id / "descendant.pid").write_text(str(child.pid))
    os._exit(1)


def test_worker_crash_stops_only_its_owned_descendant_session(tmp_path):
    app = application(settings(tmp_path), worker=crashed_parent_worker)
    with TestClient(app) as client:
        identifier = upload(client).json()["run_id"]
        assert wait_status(client, identifier)["status"] == "failed"
        child = int((app.state.snapshots.root / identifier / "descendant.pid").read_text())
        statfile = Path(f"/proc/{child}/stat")
        if statfile.exists():
            assert statfile.read_text().rsplit(")", 1)[1].split()[0] == "Z"
        assert not app.state.snapshots._stop.is_set()
