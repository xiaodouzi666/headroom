"""API/CLI snapshot integration with real parsing and an offline model transport only."""

import copy
import importlib.util
import json
import os
import pickle
import socket
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from test_snapshot_diagnosis import OfflineRuntimeFactory, native_snapshot
from typer.testing import CliRunner

import headroom.snapshot_diagnosis as core
from headroom.api import availability
from headroom.api.app import COOKIE, ApiSettings, create_app
from headroom.api.snapshot_queue import SnapshotQueue
from headroom.api.snapshot_routes import public_result
from headroom.cli import app as cli_app
from headroom.snapshot_diagnosis import SnapshotDiagnosisRequest, SnapshotServices

DRAFT = (
    "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n"
    "-DATA = '/home/customer/old.bin'\n+DATA = '/home/customer/new.bin'\n"
)


def forbidden(*_args, **_kwargs):
    raise AssertionError("Integration tests must not access a live provider, ledger or GPU")


def ordinary_worker(*_args, **_kwargs):
    raise AssertionError("Snapshot upload must not dispatch the hardware repair queue")


class OfflineAvailability:
    """No host probing or account-path discovery belongs in snapshot integration tests."""

    def snapshot(self):
        return {
            "gpu": {"status": "unknown", "available": None, "busy": None},
            "token_factory": {"status": "unknown", "configured": False, "reachable": None},
            "local_budget": {"status": "unknown"},
        }

    def close(self):
        pass


def integrated_app(config):
    return create_app(
        config,
        worker=ordinary_worker,
        snapshot_worker=snapshot_worker,
        availability_monitor=OfflineAvailability(),
    )


def restrict_offline(monkeypatch):
    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, forbidden)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.setattr(core, "_live_runtime", forbidden)
    monkeypatch.setattr(core, "BudgetLedger", forbidden)


class IntegrationDraft:
    """Offline draft fixture; it reads source as text and never executes it."""

    def __init__(self, _router, **limits):
        assert limits == {"max_repairs": 0, "max_completion_tokens": 2000}

    def generate_and_apply(self, source_root, _step, **options):
        assert (Path(source_root) / "train.py").read_text()
        assert options["context"]["hardware_verification"] == "not_run"
        output = options["work_root"]
        output.mkdir(parents=True)
        path = output / "patch.diff"
        path.write_text(DRAFT)
        return SimpleNamespace(applied=True, patch_path=path)


def snapshot_worker(request, *, run_root, run_id):
    """Importable spawn target that traverses the real workflow with no live backend."""
    with pytest.MonkeyPatch.context() as patcher:
        restrict_offline(patcher)
        result = core.run_snapshot_diagnosis(
            SnapshotDiagnosisRequest(**vars(request)),
            run_root=run_root,
            run_id=run_id,
            services=SnapshotServices(
                runtime_factory=OfflineRuntimeFactory(), patch_factory=IntegrationDraft
            ),
        )
        (Path(run_root) / run_id / "private/integration-worker.json").write_text(
            json.dumps({"pid": os.getpid(), "offline_fixture": True})
        )
        return result


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch, tmp_path):
    restrict_offline(monkeypatch)
    monkeypatch.setattr(availability, "probe_gpu", forbidden)
    monkeypatch.setattr(availability, "probe_provider", forbidden)
    monkeypatch.setattr(availability, "select_budget_database", forbidden)
    for name in (
        "HEADROOM_PUBLIC_HOST",
        "HEADROOM_TRUST_CLOUDFLARED",
        "HEADROOM_TRUST_TAILSCALE_FUNNEL",
        "HEADROOM_RUNTIME_PROFILE",
        "HEADROOM_RUN_SUBMISSIONS_ENABLED",
        "HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED",
        "HEADROOM_VERIFIED_RUNS_ENABLED",
        "HEADROOM_JUDGE_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    budget = tmp_path / "MUST_NOT_CREATE_BUDGET.sqlite3"
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(budget))
    yield
    assert not budget.exists()


def configuration(tmp_path, **flags):
    project = tmp_path / "project"
    (project / "scenarios").mkdir(parents=True, exist_ok=True)
    (project / "scenarios/INDEX.yaml").write_text('{"scenarios":[]}')
    return ApiSettings(
        project_root=project,
        snapshot_submissions_enabled=flags.get("snapshot_submissions_enabled", True),
        run_submissions_enabled=flags.get("run_submissions_enabled", True),
        verified_runs_enabled=False,
        deadline_seconds=20,
        event_poll_seconds=0.01,
    )


def make_upload(tmp_path):
    snapshot = tmp_path / "capture.pickle"
    snapshot.write_bytes(pickle.dumps(native_snapshot(), protocol=pickle.HIGHEST_PROTOCOL))
    sentinel = tmp_path / "SOURCE_MUST_NOT_EXECUTE"
    source = tmp_path / "user.py"
    source.write_text(
        "from pathlib import Path\nPath(" + repr(str(sentinel)) + ").write_text('executed')\n"
    )
    return snapshot, source, sentinel


def wait_result(client, run_id):
    until = time.monotonic() + 15
    while time.monotonic() < until:
        response = client.get(f"/api/snapshots/{run_id}")
        assert response.status_code == 200
        document = response.json()
        if document["status"] not in {"receiving", "queued", "running"}:
            return document
        time.sleep(0.025)
    pytest.fail("Offline integration worker exceeded the test deadline")


def test_create_app_native_upload_queue_core_owner_download_chain(tmp_path):
    configured = configuration(tmp_path)
    capture, source, sentinel = make_upload(tmp_path)
    original_source = source.read_bytes()
    app = integrated_app(configured)
    with TestClient(app) as client:
        assert client.get("/api/config").json()["snapshot_submissions"] == {
            "enabled": True,
            "reason": None,
            "max_bytes": 50 * 1024 * 1024,
            "runs_per_ip_per_hour": 2,
            "retention_hours": 24,
        }
        health = client.get("/api/health").json()
        assert health["token_factory"]["reachable"] is None
        assert health["gpu"]["available"] is None
        response = client.post(
            "/api/snapshots",
            files={
                "snapshot": ("capture.pickle", capture.read_bytes(), "application/octet-stream"),
                "traceback": ("oom.txt", b"CUDA out of memory", "text/plain"),
                "source": ("user.py", original_source, "text/plain"),
            },
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        row = wait_result(client, run_id)
        assert row["status"] == "completed", row
        result = row["result"]
        assert result["provenance"] == "offline_fixture"
        assert result["verification"]["status"] == "not_run"
        assert result["diagnosis"]["root_causes"]
        assert result["patch"] == {"status": "unverified", "diff": DRAFT}
        assert result["cost_usd"] is None
        assert (
            datetime.fromisoformat(row["expires_at"]) - datetime.fromisoformat(row["created_at"])
        ).total_seconds() == 24 * 3600
        job = configured.project_root / "runs/uploads" / run_id
        observed = json.loads((job / "private/integration-worker.json").read_text())
        assert observed["pid"] != os.getpid() and observed["offline_fixture"]
        assert (job / "private/offline-wire.json").is_file()
        assert (job / "private/calls.db").is_file()
        assert not sentinel.exists() and source.read_bytes() == original_source
        assert client.get("/api/runs").json()["runs"] == []
        downloads = row["artifacts"]
        assert set(downloads) == {"diagnosis_json", "diagnosis_markdown", "patch"}
        assert client.get(downloads["diagnosis_json"]["url"]).json() == result
        markdown = client.get(downloads["diagnosis_markdown"]["url"])
        assert "Not run" in markdown.text and "Offline test fixture" in markdown.text
        patch = client.get(downloads["patch"]["url"])
        assert patch.content == DRAFT.encode()  # Literal source data paths must not be rewritten.
        assert patch.headers["content-disposition"].startswith("attachment;")
        for private_name in ("snapshot.pickle", "source.py", "traceback.txt", "calls.db"):
            assert client.get(f"/api/snapshots/{run_id}/download/{private_name}").status_code == 404

        unsafe = copy.deepcopy(result)
        unsafe["patch"]["diff"] += "+ API_KEY = 'sk-" + "x" * 32 + "'\n"
        with pytest.raises(ValueError, match="Private text"):
            public_result(json.dumps(unsafe))
        unsafe["patch"]["diff"] = "+ AUTH = 'Bearer test-private-credential'\n"
        with pytest.raises(ValueError, match="Private text"):
            public_result(json.dumps(unsafe))

        owner_cookie = client.cookies.get(COOKIE)
        client.cookies.clear()
        assert client.get(f"/api/snapshots/{run_id}").status_code == 404
        assert client.get(downloads["patch"]["url"]).status_code == 404
        client.cookies.clear()
        client.cookies.set(COOKIE, owner_cookie)
        assert client.get(f"/api/snapshots/{run_id}").status_code == 200


@pytest.mark.parametrize("flag", ["snapshot_submissions_enabled", "run_submissions_enabled"])
def test_create_app_pause_flags_close_admission_before_body_and_keep_retention(
    tmp_path, monkeypatch, flag
):
    app = integrated_app(configuration(tmp_path, **{flag: False}))
    with TestClient(app) as client:
        config = client.get("/api/config").json()
        assert config["snapshot_submissions"]["enabled"] is False
        assert (
            config["snapshot_submissions"]["reason"] == "Snapshot analysis is temporarily paused."
        )
        assert app.state.snapshots.submissions_available is False
        assert app.state.snapshots.thread is None
        assert app.state.snapshots.expiry_thread.is_alive()

        async def unreadable(_request):
            pytest.fail("Pause flags must be checked before body access")
            yield b""

        monkeypatch.setattr(Request, "stream", unreadable)
        response = client.post("/api/snapshots", content=b"not a multipart body")
        assert response.status_code == 503
        assert list(app.state.snapshots.root.iterdir()) == []


@pytest.mark.parametrize("owner_process_jobs", [False, True])
def test_snapshot_config_disables_admission_when_another_manager_owns_lock(
    tmp_path, monkeypatch, owner_process_jobs
):
    configured = configuration(tmp_path)
    manager = SnapshotQueue(configured, worker=snapshot_worker)
    assert manager.start(process_jobs=owner_process_jobs) is True
    try:
        app = integrated_app(configured)
        with TestClient(app) as client:
            assert manager.submissions_available is owner_process_jobs
            assert app.state.snapshots.submissions_available is False
            assert app.state.snapshots.thread is None
            assert client.get("/api/config").json()["snapshot_submissions"] == {
                "enabled": False,
                "reason": "Snapshot analysis is temporarily unavailable.",
                "max_bytes": 50 * 1024 * 1024,
                "runs_per_ip_per_hour": 2,
                "retention_hours": 24,
            }

            async def unreadable(_request):
                pytest.fail("Unavailable manager must reject before body access")
                yield b""

            monkeypatch.setattr(Request, "stream", unreadable)
            response = client.post("/api/snapshots", content=b"not a multipart body")
            assert response.status_code == 503
            assert response.json()["detail"] == "Snapshot service is unavailable"
            assert list(manager.root.iterdir()) == []
    finally:
        manager.close()


def test_snapshot_config_tracks_dispatcher_start_and_shutdown(tmp_path):
    app = integrated_app(configuration(tmp_path))
    assert app.state.snapshots.submissions_available is False
    with TestClient(app) as client:
        assert app.state.snapshots.submissions_available is True
        assert client.get("/api/config").json()["snapshot_submissions"]["enabled"] is True
        app.state.snapshots.close()
        assert app.state.snapshots.submissions_available is False
        config = client.get("/api/config").json()["snapshot_submissions"]
        assert config["enabled"] is False
        assert config["reason"] == "Snapshot analysis is temporarily unavailable."


def test_cli_native_snapshot_and_source_use_offline_core_without_hardware(tmp_path, monkeypatch):
    capture, source, sentinel = make_upload(tmp_path)
    output = tmp_path / "cli-project/runs/uploads"
    actual = core.run_snapshot_diagnosis
    seen = []

    def injected(request, *, run_root):
        assert isinstance(request, SnapshotDiagnosisRequest)
        assert run_root == output
        result = actual(
            request,
            run_root=run_root,
            services=SnapshotServices(
                runtime_factory=OfflineRuntimeFactory(), patch_factory=IntegrationDraft
            ),
        )
        seen.append(result)
        return result

    monkeypatch.setattr(core, "run_snapshot_diagnosis", injected)
    outcome = CliRunner().invoke(
        cli_app,
        [
            "diagnose",
            "--snapshot",
            str(capture),
            "--source",
            str(source),
            "--budget",
            "0.30",
            "--run-root",
            str(output),
        ],
    )
    assert outcome.exit_code == 0, outcome.output
    summary = json.loads(outcome.stdout)
    assert summary["status"] == "completed"
    assert summary["provenance"] == "offline_fixture"
    assert summary["verification"]["status"] == "not_run"
    assert summary["cost_usd"] is None
    assert not sentinel.exists()
    assert len(seen) == 1
    job = output / summary["run_id"]
    document = json.loads((job / "diagnosis.json").read_text())
    assert document == seen[0]
    assert (
        public_result(json.dumps(document), identifier=summary["run_id"], status="completed")[
            "patch"
        ]["diff"]
        == DRAFT
    )
    assert Path(summary["diagnosis_json"]) == job / "diagnosis.json"
    assert (job / "patch.diff").read_bytes() == DRAFT.encode()
    assert (job / "private/offline-wire.json").is_file()


def test_public_launcher_keeps_snapshot_disabled_by_default(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/serve_public.py"
    spec = importlib.util.spec_from_file_location("snapshot_public_launcher_integration", source)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    project = tmp_path / "public-project"
    monkeypatch.setattr(launcher, "__file__", str(project / "scripts/serve_public.py"))
    publications = {
        "public-evaluations.json": {
            "version": 1,
            "campaigns": [{"id": "offline-fixture", "title": "Offline launcher fixture"}],
        },
        "published-evaluations/offline-fixture.json": {
            "mode": "campaign",
            "provenance": "offline_fixture",
            "status": "finished",
            "rows": [],
        },
    }
    for name, document in publications.items():
        path = project / "public-evidence" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))
    (project / "scenarios").mkdir()
    (project / "scenarios/INDEX.yaml").write_text('{"scenarios":[]}')
    monkeypatch.setenv("HEADROOM_PUBLIC_HOST", "headroom.example")
    monkeypatch.delenv("HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED", raising=False)
    observed = {}

    def build(config):
        observed["settings"] = config
        return integrated_app(config)

    def inspect(app, **options):
        assert options == {
            "host": "127.0.0.1",
            "port": 8766,
            "proxy_headers": False,
            "limit_concurrency": 64,
            "backlog": 64,
            "timeout_keep_alive": 5,
        }
        with TestClient(app) as client:
            config = client.get("/api/config").json()
            assert config["snapshot_submissions"]["enabled"] is False
            assert client.post("/api/snapshots", content=b"invalid").status_code == 503
            assert app.state.snapshots.thread is None
            assert app.state.snapshots.expiry_thread.is_alive()
        observed["inspected"] = True

    monkeypatch.setattr(launcher, "create_app", build)
    monkeypatch.setattr(launcher.uvicorn, "run", inspect)
    launcher.main()
    assert observed["inspected"]
    assert observed["settings"].project_root == project
    assert observed["settings"].snapshot_submissions_enabled is False
    assert observed["settings"].run_submissions_enabled is False
