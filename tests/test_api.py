"""In-process ASGI and supervised fake-worker checks; no GPU or model API."""

import json
import signal
import subprocess
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from headroom.api.app import ApiSettings, create_app
from headroom.api.queue import cleanup_owned_lab
from headroom.lab import docker
from headroom.lab.runner import PROJECT_ROOT


@pytest.fixture
def settings(tmp_path):
    return ApiSettings(
        project_root=PROJECT_ROOT,
        data_root=tmp_path / "api",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "jobs",
        web_dist=tmp_path / "dist",
        event_poll_seconds=0.01,
    )


def completed_worker(request, *, store, run_root, run_id):
    directory = Path(run_root) / run_id
    directory.mkdir(parents=True)
    (directory / "report.md").write_text("# Offline fixture\n")
    (directory / "report.json").write_text(
        json.dumps({"provenance": "offline_fixture", "target_met": False})
    )
    (directory / "patch.diff").write_text("offline fixture diff\n")
    store.add_event(run_id, "run.started", {"provenance": "offline_fixture"})
    store.add_event(run_id, "run.done", {"target_met": False})
    return {"status": "completed", "target_met": False}


def process_deadline_worker(request, *, store, run_root, run_id):
    """A real spawned process with no model/GPU call, deliberately ignoring TERM."""
    if "FAST" in Path(request.script).read_text():
        return completed_worker(request, store=store, run_root=run_root, run_id=run_id)
    directory = Path(run_root) / run_id
    directory.mkdir(parents=True)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (directory / "worker-started.txt").write_text("fake worker started; no network or GPU")
    time.sleep(30)


def wait_done(client, run_id, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = client.get(f"/api/runs/{run_id}").json()
        if row.get("api_worker_finished"):
            return row
        time.sleep(0.02)
    raise AssertionError("Worker did not finish within test deadline")


def test_upload_socket_rejected_and_health_is_honest(settings):
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok" and health["token_factory"]["reachable"] is None
        assert not health["token_factory"]["configured"]
        denied = client.post("/api/runs", json={"script_text": "import socket\n"})
        assert denied.status_code == 400 and "rejected" in denied.text
        assert client.get("/api/runs").json()["runs"] == []


def test_run_artifacts_sessions_examples_usage_and_terminal_sse(settings):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        assert len(client.get("/api/examples").json()["examples"]) == 8
        accepted = client.post("/api/runs", json={"script_text": "print('fixture')\n"})
        assert accepted.status_code == 202, accepted.text
        run_id = accepted.json()["run_id"]
        final = wait_done(client, run_id)
        assert final["status"] == "completed" and final["target_met"] is False
        assert client.get(final["artifacts"]["report.md"]).text == "# Offline fixture\n"
        assert (
            client.get(f"/api/runs/{run_id}/report.json").json()["provenance"] == "offline_fixture"
        )
        assert client.get(f"/api/runs/{run_id}/.env").status_code == 404
        events = client.get(f"/api/runs/{run_id}/events").text
        assert "event: run.queued" in events and "event: run.done" in events
        assert "event: stream.end" in events
        resumed = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": "2"}).text
        assert "id: 1\n" not in resumed and "id: 2\n" not in resumed and "id: 3\n" in resumed
        other = TestClient(app)
        assert other.get(f"/api/runs/{run_id}").status_code == 404
        assert other.get(f"/api/runs/{run_id}/report.md").status_code == 404
        other.close()
        assert client.get("/api/usage").json()["scope"] == "current_session"
        assert client.get("/api/replays").json()["replays"] == []


def test_sse_includes_events_added_after_stream_started(settings):
    started = threading.Event()
    release = threading.Event()

    def worker(request, *, store, run_root, run_id):
        store.add_event(run_id, "run.started", {})
        started.set()
        release.wait(2)
        store.add_event(run_id, "verify.done", {"target_met": False})
        return {"status": "needs_human"}

    with TestClient(create_app(settings, worker=worker)) as client:
        run_id = client.post("/api/runs", json={"script_text": "print('test')"}).json()["run_id"]
        assert started.wait(2)
        timer = threading.Timer(0.1, release.set)
        timer.start()
        response = client.get(f"/api/runs/{run_id}/events")
        timer.join()
        assert "event: verify.done" in response.text
        assert '"status": "needs_human"' in response.text
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "content-encoding" not in response.headers


def test_single_worker_second_queued_and_third_same_ip_limited(settings):
    gate = threading.Event()
    started = threading.Event()
    calls = []

    def worker(request, *, store, run_root, run_id):
        calls.append(run_id)
        started.set()
        gate.wait(2)
        return {"status": "needs_human"}

    with TestClient(create_app(settings, worker=worker)) as client:
        first = client.post("/api/runs", json={"script_text": "print(1)"}).json()["run_id"]
        assert started.wait(2)
        second = client.post("/api/runs", json={"script_text": "print(2)"})
        assert second.status_code == 202
        second_id = second.json()["run_id"]
        assert client.get(f"/api/runs/{second_id}").json()["status"] == "queued"
        assert calls == [first]
        third = client.post(
            "/api/runs",
            json={"script_text": "print(3)"},
            headers={"X-Forwarded-For": "203.0.113.123"},
        )
        assert third.status_code == 429
        gate.set()
        wait_done(client, second_id)
        assert calls == [first, second_id]


def test_global_capacity_includes_active_and_pending(settings):
    gate = threading.Event()

    def worker(*args, **kwargs):
        gate.wait(2)
        return {"status": "needs_human"}

    app = create_app(settings, worker=worker)
    with TestClient(app, client=("ip-one", 1)) as client:
        peers = [TestClient(app, client=(f"ip-{i}", i)) for i in range(2, 5)]
        assert client.post("/api/runs", json={"script_text": "print(1)"}).status_code == 202
        for peer in peers[:2]:
            assert peer.post("/api/runs", json={"script_text": "print(1)"}).status_code == 202
        assert peers[2].post("/api/runs", json={"script_text": "print(1)"}).status_code == 429
        queue = client.get("/api/health").json()["queue"]
        assert queue["pending"] + bool(queue["running"]) == 3
        gate.set()
        for peer in peers:
            peer.close()


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"script_text": "print(1)", "script": "/etc/passwd"}, 400),
        ({"repo": "https://example.invalid/repo", "ref": "main", "cmd": "python train.py"}, 400),
        ({"script_text": "print(1)", "example_id": "s1_batch_too_big"}, 400),
        ({"script_text": "a" * (1024 * 1024 + 1)}, 413),
        ({"script_text": "print(1)", "budget": "NaN"}, 400),
    ],
)
def test_request_boundaries(settings, payload, status):
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        assert client.post("/api/runs", json=payload).status_code == status


def test_artifacts_never_follow_leaf_or_parent_symlinks(settings, tmp_path):
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        run_id = client.post("/api/runs", json={"script_text": "print(1)"}).json()["run_id"]
        wait_done(client, run_id)
        secret = tmp_path / "outside.txt"
        secret.write_text("outside-content")
        directory = settings.run_root / run_id
        (directory / "env.sh").symlink_to(secret)
        (directory / "evidence").symlink_to(tmp_path)
        assert client.get(f"/api/runs/{run_id}/env.sh").status_code == 404
        assert client.get(f"/api/runs/{run_id}/evidence.json").status_code == 404
        assert "env.sh" not in client.get(f"/api/runs/{run_id}").json()["artifacts"]


def test_curated_replay_sse_terminates_without_private_session_access(settings):
    app = create_app(settings, worker=completed_worker)
    run_id = uuid4().hex
    app.state.store.create_run(run_id, status="completed", public_replay=True, target_met=False)
    app.state.store.add_event(run_id, "run.done", {"target_met": False})
    with TestClient(app) as client:
        assert client.get("/api/replays").json()["count"] == 1
        assert "event: stream.end" in client.get(f"/api/runs/{run_id}/events").text


def test_spawn_worker_deadline_kills_ignoring_process_and_preserves_partial_report(settings):
    settings.deadline_seconds = 4
    settings.shutdown_grace_seconds = 0.2
    app = create_app(settings, worker=process_deadline_worker, worker_mode="process")
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "print('slow')"}).json()["run_id"]
        row = wait_done(client, run_id, timeout=12)
        assert row["status"] == "timeout" and row["api_cleanup_verified"] is True
        assert (settings.run_root / run_id / "worker-started.txt").is_file()
        assert client.get(f"/api/runs/{run_id}/report.json").status_code == 200
        assert not app.state.queue.snapshot()["halted"]
        next_id = client.post("/api/runs", json={"script_text": "print('FAST')"}).json()["run_id"]
        assert wait_done(client, next_id)["status"] == "completed"


def test_cleanup_requires_owned_manifest_and_exact_container_mounts(tmp_path, monkeypatch):
    run_id, lab_id = uuid4().hex, uuid4().hex
    directory = tmp_path / run_id / "lab" / lab_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps({"image": docker.IMAGE, "command": ["python"]})
    )
    name = "headroom-lab-" + lab_id
    cleaned = []
    details = {
        "Name": "/" + name,
        "Id": "c" * 64,
        "Mounts": [
            {"Destination": "/source", "Source": str(directory / "source")},
            {"Destination": "/out", "Source": str(directory / "artifacts")},
        ],
    }
    monkeypatch.setattr(docker, "docker_binary", lambda: "docker")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, json.dumps([details]), ""),
    )
    monkeypatch.setattr(
        docker, "cleanup_container", lambda n: cleaned.append(n) or {"cleanup_verified": True}
    )
    assert cleanup_owned_lab(tmp_path, run_id) is True
    assert cleaned == ["c" * 64]
    cleaned.clear()
    details["Mounts"][0]["Source"] = "/unrelated/source"
    assert cleanup_owned_lab(tmp_path, run_id) is False
    assert not cleaned


def test_static_build_is_served_without_exposing_parent_paths(settings, tmp_path):
    settings.web_dist.mkdir()
    (settings.web_dist / "index.html").write_text("<main>local fixture</main>")
    (tmp_path / "outside.js").write_text("secret")
    (settings.web_dist / "bad.js").symlink_to(tmp_path / "outside.js")
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        assert "local fixture" in client.get("/").text
        assert "local fixture" in client.get("/runs/id").text
        assert client.get("/bad.js").status_code == 404
        assert client.get("/api/missing").status_code == 404


def test_unverified_cleanup_halts_queue_and_does_not_start_next_job(settings, monkeypatch):
    from headroom.api import queue as queue_module

    monkeypatch.setattr(queue_module, "cleanup_owned_lab", lambda *args: False)
    settings.deadline_seconds = 4
    app = create_app(settings, worker=process_deadline_worker, worker_mode="process")
    with TestClient(app) as client:
        first = client.post("/api/runs", json={"script_text": "print('FAST')"}).json()["run_id"]
        second = client.post("/api/runs", json={"script_text": "print('FAST')"}).json()["run_id"]
        deadline = time.monotonic() + 8
        while not app.state.queue.snapshot()["halted"] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert app.state.queue.snapshot()["halted"]
        first_row = client.get(f"/api/runs/{first}").json()
        assert first_row["status"] == "needs_human" and not first_row["api_cleanup_verified"]
        assert client.get(f"/api/runs/{second}").json()["status"] == "queued"
        assert not (settings.run_root / second).exists()
        assert "event: stream.end" in client.get(f"/api/runs/{first}/events").text


def test_server_shutdown_cancels_the_owned_process_and_finishes_partial_report(settings):
    from headroom.store.db import Store

    settings.deadline_seconds = 30
    settings.shutdown_grace_seconds = 0.2
    app = create_app(settings, worker=process_deadline_worker, worker_mode="process")
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "print('slow')"}).json()["run_id"]
        marker = settings.run_root / run_id / "worker-started.txt"
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
    assert not app.state.queue.thread.is_alive()
    store = Store(settings.db_path)
    try:
        row = store.get_run(run_id)
        assert row["status"] == "cancelled" and row["api_cleanup_verified"]
        assert (settings.run_root / run_id / "report.json").is_file()
    finally:
        store.close()


def test_origin_and_host_controls_reject_cross_origin_submissions(settings):
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        assert (
            client.post(
                "/api/runs",
                json={"script_text": "print(1)"},
                headers={"Origin": "https://foreign.invalid"},
            ).status_code
            == 403
        )
        assert client.get("/api/health", headers={"Host": "foreign.invalid"}).status_code == 400


def test_restart_does_not_trust_terminal_status_without_supervisor_cleanup(settings):
    app = create_app(settings, worker=completed_worker)
    run_id = uuid4().hex
    app.state.store.create_run(
        run_id,
        status="completed",
        api_owner="previous-session",
        api_worker_finished=False,
        target_met=True,
    )
    with TestClient(app) as client:
        assert client.get("/api/health").json()["queue"]["halted"]
        assert client.post("/api/runs", json={"script_text": "print(1)"}).status_code == 503
        recovered = app.state.store.get_run(run_id)
        assert recovered["status"] == "needs_human" and not recovered["target_met"]


def test_repository_form_is_validated_before_any_fetch(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid repository must not fetch")

    monkeypatch.setattr("headroom.api.app.prepare_repository", forbidden)
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        for data in [
            {"repo": "file:///tmp/repo", "ref": "a" * 40, "cmd": "python train.py"},
            {"repo": "https://github.com/a/b", "ref": "main", "cmd": "python train.py"},
            {"repo": "https://github.com/a/b", "ref": "a" * 40, "cmd": "bash setup.sh"},
            {
                "repo": "https://github.com/a/b",
                "ref": "a" * 40,
                "cmd": "python train.py",
                "script_text": "pass",
            },
        ]:
            assert client.post("/api/runs", json=data).status_code == 400


def test_repository_prepared_source_enters_same_queue(settings, monkeypatch):
    from types import SimpleNamespace

    def prepared(repo, ref, command, *, destination, deadline):
        destination.mkdir(parents=True)
        script = destination / "train.py"
        script.write_text("print('repository offline fixture')")
        return SimpleNamespace(
            source_root=destination,
            script=script,
            script_args=(),
            source_profile=None,
            execution_argv=("python", "train.py"),
        )

    monkeypatch.setattr("headroom.api.app.prepare_repository", prepared)
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        response = client.post(
            "/api/runs",
            json={"repo": "https://github.com/a/b", "ref": "a" * 40, "cmd": "python train.py"},
        )
        assert response.status_code == 202, response.text
        assert wait_done(client, response.json()["run_id"])["status"] == "completed"


def test_public_tunnel_cookie_and_client_ip_rate_limit(settings):
    settings.public_host = "demo.example"
    settings.trust_cloudflared = True
    settings.allowed_hosts = (*settings.allowed_hosts, "demo.example")
    with TestClient(
        create_app(settings, worker=completed_worker),
        base_url="https://demo.example",
        client=("127.0.0.1", 50000),
    ) as client:
        assert "Secure" in client.get("/api/health").headers["set-cookie"]
        assert client.post("/api/runs", json={"script_text": "pass"}).status_code == 400
        for ip in ("203.0.113.1", "203.0.113.2"):
            for _ in range(2):
                r = client.post(
                    "/api/runs", json={"script_text": "pass"}, headers={"CF-Connecting-IP": ip}
                )
                assert r.status_code == 202, r.text
                wait_done(client, r.json()["run_id"])
            assert (
                client.post(
                    "/api/runs", json={"script_text": "pass"}, headers={"CF-Connecting-IP": ip}
                ).status_code
                == 429
            )


def test_slow_repository_preparation_does_not_hold_queue_lock(settings, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from headroom.api import app as api
    from headroom.repository import PreparedRepository

    entered, release = threading.Event(), threading.Event()

    def slow_prepare(repo, ref, command, *, destination, deadline):
        entered.set()
        assert release.wait(3)
        destination.mkdir(parents=True)
        script = destination / "train.py"
        script.write_text("pass")
        return PreparedRepository(destination, script, (), None, {})

    monkeypatch.setattr(api, "prepare_repository", slow_prepare)
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        submitted = pool.submit(
            client.post,
            "/api/runs",
            json={
                "repo": "https://github.com/example/repository",
                "ref": "a" * 40,
                "cmd": "python train.py",
            },
        )
        assert entered.wait(2)
        try:
            status = pool.submit(client.get, "/api/health").result(timeout=1)
            assert status.status_code == 200 and status.json()["queue"]["preparing"] == 1
            immediate = client.post("/api/runs", json={"script_text": "pass"})
            assert immediate.status_code == 202
            wait_done(client, immediate.json()["run_id"], timeout=2)
            assert client.post("/api/runs", json={"script_text": "pass"}).status_code == 429
        finally:
            release.set()
        assert submitted.result(timeout=3).status_code == 202


def test_failed_preparations_release_capacity_but_remain_rate_limited(settings, monkeypatch):
    from headroom.api import app as api

    def fail(*args, **kwargs):
        raise ValueError("private details not exposed")

    monkeypatch.setattr(api, "prepare_repository", fail)
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        payload = {
            "repo": "https://github.com/example/repository",
            "ref": "a" * 40,
            "cmd": "python train.py",
        }
        for _ in range(2):
            assert client.post("/api/runs", json=payload).status_code == 400
            assert client.get("/api/health").json()["queue"]["preparing"] == 0
        assert client.post("/api/runs", json=payload).status_code == 429
        assert client.get("/api/runs").json()["runs"] == []


def test_configuration_downloads_are_fixed_and_owner_scoped(settings, tmp_path):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        wait_done(client, run_id)
        directory = settings.run_root / run_id / "configurations/round-01"
        directory.mkdir(parents=True)
        (directory / "patch.diff").write_text("accepted patch fixture")
        (directory / "cli.json").write_text("[]")
        url = f"/api/runs/{run_id}/configurations/round-01/patch.diff"
        assert client.get(url).text == "accepted patch fixture"
        for suffix in (
            "round-00/patch.diff",
            "round-07/patch.diff",
            "round-01/.env",
            "round-01/%2E%2E%2Freport.md",
            "%2E%2E/patch.diff",
        ):
            assert client.get(f"/api/runs/{run_id}/configurations/{suffix}").status_code == 404
        other = TestClient(app)
        try:
            assert other.get(url).status_code == 404
        finally:
            other.close()
        (directory / "env.sh").symlink_to(directory / "patch.diff")
        assert client.get(url.replace("patch.diff", "env.sh")).status_code == 404
        (directory.parent / "round-02").symlink_to(directory, target_is_directory=True)
        assert client.get(url.replace("round-01", "round-02")).status_code == 404


def test_health_detects_reviewed_runtime_without_a_provider_request(settings, monkeypatch):
    from types import SimpleNamespace

    calls = []
    profile = SimpleNamespace(
        base_url="https://api.tokenfactory.us-central1.nebius.com/v1/",
        authorized_total_usd="1",
    )

    def load_profile(path):
        calls.append("profile")
        return profile

    monkeypatch.setattr("headroom.api.app.read_live_profile", load_profile)
    monkeypatch.setattr(
        "headroom.runtime.read_nebius_key", lambda *a: pytest.fail("health read key")
    )
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        result = client.get("/api/health").json()["token_factory"]
        assert result["configured"] is True and result["reachable"] is None
        assert result["authentication_checked"] is False
        assert result["configuration_scope"] == "reviewed_runtime_profile"
        assert calls and set(calls) == {"profile"}


def test_static_javascript_and_catalog_gzip_without_changing_payload(settings):
    settings.web_dist.mkdir(parents=True)
    (settings.web_dist / "assets").mkdir()
    payload = "const evidence = 'verified';\n" * 200
    (settings.web_dist / "assets/app.js").write_text(payload)
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        response = client.get("/assets/app.js", headers={"Accept-Encoding": "gzip"})
        assert response.status_code == 200
        assert response.headers["content-encoding"] == "gzip"
        assert response.text == payload
        catalog = client.get("/api/examples", headers={"Accept-Encoding": "gzip"})
        assert catalog.headers["content-encoding"] == "gzip"
        assert len(catalog.json()["examples"]) == 8
        plain = client.get("/assets/app.js", headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers
        assert plain.text == payload


@pytest.mark.parametrize("render_fails", [False, True])
def test_expired_queue_sse_waits_for_report_or_explicit_render_failure(
    settings, monkeypatch, render_fails
):
    from concurrent.futures import ThreadPoolExecutor

    from headroom.api import queue as module

    settings.deadline_seconds = 0.1
    worker_started, worker_release = threading.Event(), threading.Event()
    report_started, report_release = threading.Event(), threading.Event()
    original = module.generate_report

    def worker(*args, **kwargs):
        worker_started.set()
        worker_release.wait(5)
        return {"status": "needs_human"}

    def slow_report(*args, **kwargs):
        report_started.set()
        assert report_release.wait(5)
        if render_fails:
            raise RuntimeError("private render details must not escape")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "generate_report", slow_report)
    app = create_app(settings, worker=worker)
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = client.post("/api/runs", json={"script_text": "pass"})
        assert first.status_code == 202 and worker_started.wait(1)
        second = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        try:
            assert report_started.wait(2)
            row = client.get(f"/api/runs/{second}").json()
            assert row["status"] == "timeout" and row["api_report_pending"]
            assert not row["api_worker_finished"] and not row["api_report_ready"]
            streaming = pool.submit(client.get, f"/api/runs/{second}/events")
            time.sleep(0.35)
            assert not streaming.done(), "stream.end must wait for the final report state"
            report_release.set()
            assert "event: stream.end" in streaming.result(timeout=2).text
            final = client.get(f"/api/runs/{second}").json()
            assert final["api_worker_finished"] and not final["api_report_pending"]
            assert final["api_report_ready"] is (not render_fails)
            if render_fails:
                assert final["status"] == "needs_human"
                assert final["api_report_error"] == "partial_report_generation_failed"
                assert "private render" not in json.dumps(final)
            else:
                assert client.get(final["artifacts"]["report.json"]).status_code == 200
        finally:
            report_release.set()
            worker_release.set()


def test_repository_module_argv_survives_validation_preparation_and_queue(settings, monkeypatch):
    import shlex
    import socket

    from headroom.execution import prepare_local_command

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in repository argv integration test")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    captured = []

    def prepared(repo, ref, command, *, destination, deadline):
        from types import SimpleNamespace

        package = destination / "package"
        package.mkdir(parents=True)
        (package / "train.py").write_text("VALUE = 1\n")
        resolved = prepare_local_command(destination, command)
        return SimpleNamespace(
            source_root=resolved.source_root,
            script=resolved.script,
            script_args=resolved.script_args,
            source_profile=None,
            execution_argv=resolved.execution_argv,
        )

    def worker(request, **kwargs):
        captured.append(request)
        return completed_worker(request, **kwargs)

    monkeypatch.setattr("headroom.api.app.prepare_repository", prepared)
    command = 'python3 -u -W ignore -m package.train --label "two words"'
    with TestClient(create_app(settings, worker=worker)) as client:
        response = client.post(
            "/api/runs",
            json={"repo": "https://github.com/a/b", "ref": "a" * 40, "cmd": command},
        )
        assert response.status_code == 202, response.text
        assert wait_done(client, response.json()["run_id"])["status"] == "completed"
    assert len(captured) == 1
    assert captured[0].execution_argv == shlex.split(command)
    assert captured[0].script_args == ["--label", "two words"]
    assert captured[0].repository_mode is True
    assert captured[0].script.endswith("/package/train.py")


def test_selected_after_downloads_follow_real_orchestration_and_retained_round(settings, tmp_path):
    from test_orchestrator import search_run

    (tmp_path / "pipeline").mkdir()
    result, source_store, _, _, _ = search_run(
        tmp_path / "pipeline",
        [
            {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True},
            {"before": "VALUE = 2\n", "after": "VALUE = 3\n", "peak": 21, "target": True},
        ],
        max_rounds=2,
        search_mode="bounded_pareto",
    )
    try:
        real_row = source_store.get_run(result["run_id"])
        settings.run_root = Path(result["run_dir"]).parent
        app = create_app(settings, worker=completed_worker)
        with TestClient(app) as client:
            bootstrap = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
            wait_done(client, bootstrap)
            owner = app.state.store.get_run(bootstrap)["api_owner"]
            app.state.store.create_run(result["run_id"], {**real_row, "api_owner": owner})
            directory = Path(result["run_dir"])
            # HTTP tests use image byte markers; this is not a rendered GPU artifact.
            for number in (1, 2):
                (directory / f"rounds/{number:02d}/evidence/timeline.png").write_bytes(
                    f"fixture round {number}".encode()
                )
            old = directory / "evidence/after"
            old.mkdir(parents=True)
            (old / "timeline.png").write_bytes(b"stale legacy image")
            url = f"/api/runs/{result['run_id']}"
            links = client.get(url).json()["artifacts"]
            assert client.get(links["timeline-after.png"]).content == b"fixture round 1"
            expected = directory / "rounds/01/evidence/evidence.json"
            assert client.get(links["evidence-after.json"]).json() == json.loads(
                expected.read_text()
            )
            manifest = client.get(links["configuration.json"]).json()
            assert manifest["round"] == 1
            assert client.get(links["cli.json"]).json()["effective"] == []
            other = TestClient(app)
            try:
                assert other.get(links["timeline-after.png"]).status_code == 404
                assert other.get(links["configuration.json"]).status_code == 404
            finally:
                other.close()
            app.state.store.update_run(result["run_id"], after_evidence_status="unavailable")
            assert "timeline-after.png" not in client.get(url).json()["artifacts"]
            assert client.get(url + "/timeline-after.png").status_code == 404
            assert client.get(url + "/evidence-after.json").status_code == 404
            assert client.get(url + "/configuration.json").status_code == 200
    finally:
        source_store.close()


@pytest.mark.parametrize(
    "kept",
    [None, {}, {"round": True}, {"round": 0}, {"round": 7}, {"round": "../01"}, {"round": []}],
)
def test_invalid_selected_round_never_falls_back_to_historical_artifacts(settings, kept):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        wait_done(client, run_id)
        directory = settings.run_root / run_id / "evidence/after"
        directory.mkdir(parents=True)
        (directory / "timeline.png").write_bytes(b"must not expose stale evidence")
        app.state.store.update_run(run_id, kept=kept)
        url = f"/api/runs/{run_id}"
        assert "timeline-after.png" not in client.get(url).json()["artifacts"]
        assert client.get(url + "/timeline-after.png").status_code == 404
        assert client.get(url + "/configuration.json").status_code == 404


def test_selected_evidence_and_manifest_never_follow_symlinks(settings, tmp_path):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        wait_done(client, run_id)
        directory = settings.run_root / run_id
        folder = directory / "rounds/01/evidence"
        folder.mkdir(parents=True)
        outside = tmp_path / "outside.txt"
        outside.write_text("outside fixture")
        (folder / "timeline.png").symlink_to(outside)
        (directory / "configurations").mkdir()
        (directory / "configurations/round-01").symlink_to(tmp_path, target_is_directory=True)
        app.state.store.update_run(run_id, kept={"round": 1}, after_evidence_status="available")
        url = f"/api/runs/{run_id}"
        assert client.get(url + "/timeline-after.png").status_code == 404
        assert client.get(url + "/configuration.json").status_code == 404
