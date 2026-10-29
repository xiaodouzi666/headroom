"""Trusted dual-pool routing with temporary stores and offline workers only."""

import hashlib
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_api import completed_worker, wait_done
from test_api import settings as isolated_settings
from test_judge_binding import pool as isolated_judge_pool
from test_public_access import EXAMPLE, HEADERS, public_client, public_settings
from test_public_launcher import launcher as isolated_launcher

from headroom.api import queue as queue_module
from headroom.api.app import create_app
from headroom.lab import storage_budget
from headroom.store.db import Store

TOKEN = "offline-judge-token-not-a-real-credential-1234"
AUTH = {**HEADERS, "Authorization": "Bearer " + TOKEN}


class NoObservation:
    def snapshot(self):
        return {
            "gpu": {"status": "available", "available": True, "busy": False},
            "token_factory": {"configured": True, "reachable": True},
            "local_budget": {"status": "exhausted", "remaining_usd": "PRIVATE-ACCOUNT-TOTAL"},
        }

    def close(self):
        pass


class Allocation:
    def __init__(self, root, kind, available=True):
        self.root, self.kind, self.available = root, kind, available
        self.receipt = {
            "profile_path": str(root / (kind + "-private-profile.json")),
            "ledger_path": str(root / (kind + "-private-ledger.db")),
            "amounts": {"daily_limit_usd": "6.61" if kind == "judge" else "0.30"},
        }
        self.started, self.finished = [], []
        self.daily_override = None

    @property
    def effective_daily_limit_usd(self):
        return self.daily_override or self.receipt["amounts"]["daily_limit_usd"]

    def begin(self, run_id, request, *, source_sha256):
        assert self.available
        assert source_sha256
        assert request.runtime_profile == self.receipt["profile_path"]
        assert request.daily_budget_usd == self.effective_daily_limit_usd
        assert request.budget_usd == "0.30"
        binding = {"kind": self.kind, "run_id": run_id}
        self.started.append(binding)
        return request, binding

    def finish(self, binding, *, execution_terminal, cleanup_verified):
        assert binding["kind"] == self.kind
        assert execution_terminal and cleanup_verified
        self.finished.append(binding)
        return {"status": "settled"}


@pytest.fixture
def judge_pool(tmp_path):
    return isolated_judge_pool.__wrapped__(tmp_path)


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    return isolated_launcher.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    settings = public_settings(isolated_settings.__wrapped__(tmp_path), judge_token=TOKEN)
    demo = Allocation(settings.project_root, "demo")
    judge = Allocation(settings.project_root, "judge")
    dispatched = []

    def bound(kind):
        def run(request, *, store, run_root, run_id, binding, worker):
            assert binding["kind"] == kind
            dispatched.append(kind)
            return worker(request, store=store, run_root=run_root, run_id=run_id)

        return run

    monkeypatch.setattr(queue_module, "_bound_worker", bound)
    app = create_app(
        settings,
        worker=completed_worker,
        availability_monitor=NoObservation(),
        demo_allocation=demo,
        judge_allocation=judge,
    )
    return app, demo, judge, dispatched


@pytest.mark.parametrize("payload", [EXAMPLE, {"script_text": "print('offline')"}])
def test_exhausted_anonymous_pool_does_not_block_valid_judge(setup, payload):
    app, demo, judge, dispatched = setup
    demo.available = False
    with public_client(app) as client:
        anonymous = client.get("/api/config").json()
        assert not anonymous["run_submissions"]["enabled"]
        assert anonymous["judge_scripts_available"]
        for path in ("/api/config", "/api/health", "/api/usage"):
            response = client.get(path, headers=AUTH)
            assert response.status_code == 200
            for hidden in (TOKEN, "6.61", "PRIVATE-ACCOUNT-TOTAL", str(judge.root)):
                assert hidden not in response.text
        assert (
            client.get("/api/health", headers=AUTH).json()["local_budget"]["status"] == "available"
        )
        response = client.post("/api/runs", json=payload, headers=AUTH)
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        wait_done(client, run_id)
        assert app.state.store.get_run(run_id)["api_funding_kind"] == "judge"
    assert not demo.started and not demo.finished
    assert judge.started == judge.finished and len(judge.started) == 1
    assert dispatched == ["judge"]


@pytest.mark.parametrize("first_judge", [False, True])
def test_judge_hourly_exemption_does_not_consume_anonymous_quota(setup, first_judge):
    app, demo, judge, dispatched = setup
    sequence = [AUTH, AUTH, HEADERS] if first_judge else [HEADERS, AUTH, AUTH]
    with public_client(app) as client:
        for headers in sequence:
            response = client.post("/api/runs", json=EXAMPLE, headers=headers)
            assert response.status_code == 202, response.text
            wait_done(client, response.json()["run_id"])
        client.cookies.clear()
        assert client.post("/api/runs", json=EXAMPLE, headers=HEADERS).status_code == 429
        assert app.state.queue.hourly_limit == 1 and app.state.queue.deadline == 480
        with sqlite3.connect(app.state.queue.admission_path) as connection:
            assert connection.execute("SELECT count(*) FROM admissions").fetchone()[0] == 3
            assert (
                connection.execute("SELECT count(*) FROM hourly_exempt_admissions").fetchone()[0]
                == 2
            )
    assert len(demo.started) == 1 and len(judge.started) == 2
    assert dispatched.count("demo") == 1 and dispatched.count("judge") == 2


def test_request_config_and_health_describe_verified_route_policy(setup):
    app, _, _, _ = setup
    with public_client(app) as client:
        for path in ("/api/config", "/api/health"):
            anonymous = client.get(path).json()["limits"]
            judge = client.get(path, headers=AUTH).json()["limits"]
            assert anonymous == {
                "runs_per_ip_per_hour": 1,
                "hourly_limit_applies": True,
                "max_waiting_runs": 2,
                "deadline_seconds": 480,
            }
            assert judge == {
                "runs_per_ip_per_hour": None,
                "hourly_limit_applies": False,
                "max_waiting_runs": 2,
                "deadline_seconds": 480,
            }


def test_judge_effective_daily_allowance_is_bound_only_by_server(setup):
    app, demo, judge, dispatched = setup
    judge.daily_override = "9.50"  # Synthetic effective extension, not authorization.
    original_profile = app.state.settings.runtime_profile
    original_day = app.state.settings.daily_budget_usd
    with public_client(app) as client:
        response = client.post("/api/runs", json=EXAMPLE, headers=AUTH)
        assert response.status_code == 202, response.text
        wait_done(client, response.json()["run_id"])
        assert app.state.settings.runtime_profile == original_profile
        assert app.state.settings.daily_budget_usd == original_day
    assert not demo.started and len(judge.started) == 1 and dispatched == ["judge"]


def test_invalid_effective_judge_allowance_fails_before_admission(setup, monkeypatch):
    app, demo, judge, dispatched = setup

    def unavailable(_):
        raise ValueError("Untrusted extension")

    monkeypatch.setattr(Allocation, "effective_daily_limit_usd", property(unavailable))
    with public_client(app) as client:
        response = client.post("/api/runs", json=EXAMPLE, headers=AUTH)
        assert response.status_code == 503
        with sqlite3.connect(app.state.queue.admission_path) as connection:
            assert connection.execute("SELECT count(*) FROM admissions").fetchone()[0] == 0
            assert (
                connection.execute("SELECT count(*) FROM hourly_exempt_admissions").fetchone()[0]
                == 0
            )
    assert not demo.started and not judge.started and not dispatched


@pytest.mark.parametrize("headers", [AUTH, HEADERS], ids=["judge", "anonymous"])
def test_full_public_storage_rejects_repeated_requests_without_persistence(
    setup, monkeypatch, headers
):
    app, demo, judge, dispatched = setup
    settings = app.state.settings
    with storage_budget.storage_admission(settings.run_root, aggregate=True):
        pass
    jobs_before = sorted(settings.run_root.rglob("*"))
    uploads = settings.data_root / "uploads"
    uploads_before = sorted(uploads.rglob("*"))
    database_before = app.state.queue.admission_path.read_bytes()
    monkeypatch.setattr(
        storage_budget, "stored_bytes", lambda root: storage_budget.MAX_STORAGE_BYTES
    )

    def no_admission(*args, **kwargs):
        pytest.fail("Full storage must be rejected before queue.submit")

    monkeypatch.setattr(app.state.queue, "submit", no_admission)
    with public_client(app) as client:
        for _ in range(5):
            response = client.post("/api/runs", json=EXAMPLE, headers=headers)
            assert response.status_code == 503
            assert response.headers["Retry-After"] == "60"
            assert "storage" in response.json()["detail"]
        with sqlite3.connect(app.state.queue.admission_path) as connection:
            assert connection.execute("SELECT count(*) FROM admissions").fetchone()[0] == 0
            assert (
                connection.execute("SELECT count(*) FROM hourly_exempt_admissions").fetchone()[0]
                == 0
            )
        assert app.state.store.list_runs() == []
        assert sorted(settings.run_root.rglob("*")) == jobs_before
        assert sorted(uploads.rglob("*")) == uploads_before
        assert app.state.queue.admission_path.read_bytes() == database_before
    assert not demo.started and not judge.started and not dispatched


def test_public_storage_census_does_not_block_health_event_loop(setup, monkeypatch):
    app, _, _, dispatched = setup
    entered, release = threading.Event(), threading.Event()

    def slow_census(root):
        entered.set()
        assert release.wait(5)
        return storage_budget.MAX_STORAGE_BYTES

    monkeypatch.setattr(storage_budget, "stored_bytes", slow_census)
    with public_client(app) as client, ThreadPoolExecutor(max_workers=2) as pool:
        submission = pool.submit(client.post, "/api/runs", json=EXAMPLE, headers=AUTH)
        try:
            assert entered.wait(2)
            health = pool.submit(client.get, "/api/health").result(timeout=1)
            assert health.status_code == 200
        finally:
            release.set()
        assert submission.result(timeout=3).status_code == 503
        assert app.state.store.list_runs() == []
    assert not dispatched


def test_judge_hourly_exemption_keeps_global_queue_capacity(setup):
    app, _, _, _ = setup
    started, release = threading.Event(), threading.Event()

    def blocked(request, **kwargs):
        started.set()
        assert release.wait(10)
        return completed_worker(request, **kwargs)

    app.state.queue.worker = blocked
    with public_client(app) as client:
        try:
            first = client.post("/api/runs", json=EXAMPLE, headers=AUTH)
            assert first.status_code == 202
            assert started.wait(3)
            for _ in range(2):
                assert client.post("/api/runs", json=EXAMPLE, headers=AUTH).status_code == 202
            fourth = client.post("/api/runs", json=EXAMPLE, headers=AUTH)
            assert fourth.status_code == 429
            assert "capacity" in fourth.json()["detail"]
            assert app.state.queue.snapshot()["pending"] == 2
        finally:
            release.set()
        wait_done(client, first.json()["run_id"])


def test_legacy_admissions_are_preserved_and_not_retroactively_exempted(tmp_path, monkeypatch):
    configured = public_settings(isolated_settings.__wrapped__(tmp_path), judge_token=TOKEN)
    path = configured.data_root / "admissions.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    legacy = (
        "f" * 32,
        hashlib.sha256(HEADERS["X-Forwarded-For"].encode()).hexdigest(),
        time.time(),
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE admissions (run_id TEXT PRIMARY KEY, ip TEXT, created REAL)"
        )
        connection.execute("INSERT INTO admissions VALUES (?,?,?)", legacy)
    demo, judge = (
        Allocation(configured.project_root, "demo"),
        Allocation(configured.project_root, "judge"),
    )

    def bound(kind):
        def run(request, *, store, run_root, run_id, binding, worker):
            assert kind == binding["kind"]
            return worker(request, store=store, run_root=run_root, run_id=run_id)

        return run

    monkeypatch.setattr(queue_module, "_bound_worker", bound)
    app = create_app(
        configured,
        worker=completed_worker,
        availability_monitor=NoObservation(),
        demo_allocation=demo,
        judge_allocation=judge,
    )
    with public_client(app) as client:
        assert client.post("/api/runs", json=EXAMPLE, headers=HEADERS).status_code == 429
        response = client.post("/api/runs", json=EXAMPLE, headers=AUTH)
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        wait_done(client, run_id)
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute("SELECT * FROM admissions WHERE run_id=?", (legacy[0],)).fetchone()
            == legacy
        )
        assert connection.execute("SELECT run_id FROM hourly_exempt_admissions").fetchall() == [
            (run_id,)
        ]


def test_invalid_token_and_http_funding_fields_never_admit_or_fallback(setup):
    app, demo, judge, dispatched = setup
    with public_client(app) as client:
        for authorization in (
            "",
            "Bearer wrong",
            "Basic wrong",
            "Bearer ",
            "Bearer " + TOKEN + "x",
        ):
            headers = {**HEADERS, "Authorization": authorization}
            assert client.post("/api/runs", json=EXAMPLE, headers=headers).status_code == 401
            assert client.get("/api/config", headers=headers).status_code == 401
            assert client.get("/api/health", headers=headers).status_code == 401
        duplicate = [
            *HEADERS.items(),
            ("Authorization", "Bearer " + TOKEN),
            ("Authorization", "Bearer wrong"),
        ]
        assert client.post("/api/runs", json=EXAMPLE, headers=duplicate).status_code == 401
        for field in (
            "funding_kind",
            "hourly_limit_applies",
            "hourly_exempt",
            "daily_budget_usd",
            "budget_usd",
            "pool",
            "runtime_profile",
            "profile_path",
            "binding",
            "worker",
        ):
            assert (
                client.post("/api/runs", json={**EXAMPLE, field: "judge"}, headers=AUTH).status_code
                == 400
            )
        with sqlite3.connect(app.state.queue.admission_path) as connection:
            assert connection.execute("SELECT count(*) FROM admissions").fetchone()[0] == 0
        assert app.state.store.list_runs() == []
    assert not demo.started and not judge.started and not dispatched


def test_unavailable_judge_pool_cannot_fallback_to_healthy_demo(setup):
    app, demo, judge, dispatched = setup
    judge.available = False
    with public_client(app) as client:
        assert client.get("/api/config").json()["run_submissions"]["enabled"]
        assert not client.get("/api/config", headers=AUTH).json()["run_submissions"]["enabled"]
        assert (
            client.get("/api/health", headers=AUTH).json()["local_budget"]["status"]
            == "unavailable"
        )
        assert client.post("/api/runs", json=EXAMPLE, headers=AUTH).status_code == 503
        assert app.state.store.list_runs() == []
    assert not demo.started and not judge.started and not dispatched


@pytest.mark.parametrize("kind", ["demo", "judge"])
def test_process_entry_dispatches_the_trusted_binding_kind(tmp_path, monkeypatch, kind):
    from headroom.acceptance import demo_binding, judge_binding
    from headroom.orchestrator import FixRequest

    run_id = "a" * 32
    database = tmp_path / "store.db"
    store = Store(database)
    store.create_run(run_id, status="running")
    store.close()
    observed = []

    def bound(request, *, store, run_root, run_id, binding, worker):
        observed.append(binding["kind"])
        return {"status": "completed", "target_met": False}

    def wrong(*args, **kwargs):
        raise AssertionError("Wrong funding wrapper dispatched")

    monkeypatch.setattr(demo_binding, "run_bound_demo", bound if kind == "demo" else wrong)
    monkeypatch.setattr(judge_binding, "run_bound_judge", bound if kind == "judge" else wrong)
    source = tmp_path / "train.py"
    source.write_text("pass")
    request = FixRequest(script=str(source)).model_dump()
    queue_module._process_entry(
        wrong,
        request,
        str(database),
        str(tmp_path),
        run_id,
        time.monotonic() + 10,
        {"kind": kind},
        kind,
    )
    assert observed == [kind]
    store = Store(database)
    assert store.get_run(run_id)["status"] == "completed"
    store.close()


@pytest.mark.parametrize("mode", ["thread", "process"])
def test_real_judge_binding_api_dispatch_uses_only_judge_ledger(judge_pool, monkeypatch, mode):
    # sdk_worker uses explicit test-only injection; restore those assignments
    # after thread mode too so later cases do not inherit test-global patches.
    import socket

    from test_demo_api import done, sdk_worker

    from headroom import orchestrator
    from headroom.acceptance.judge_binding import JudgeAllocation
    from headroom.api.app import ApiSettings

    for module, names in (
        (socket, ("getaddrinfo",)),
        (socket.socket, ("connect", "connect_ex")),
        (orchestrator, ("build_live_runtime", "read_live_profile")),
    ):
        for name in names:
            monkeypatch.setattr(module, name, getattr(module, name))
    root = judge_pool["root"]
    demo = Allocation(root, "demo", available=False)
    judge = JudgeAllocation(judge_pool["path"], project_root=root)
    # Synthetic Lab creates no Docker container; this tests the real allocation,
    # SDK MockTransport and API worker dispatch/settlement path.
    monkeypatch.setattr(queue_module, "cleanup_owned_lab", lambda *args: True)
    settings = ApiSettings(
        project_root=root,
        public_host="demo.example",
        judge_token=TOKEN,
        data_root=root / "api",
        db_path=root / "api.db",
        run_root=root / "jobs",
        web_dist=root / "dist",
        run_submissions_enabled=True,
    )
    app = create_app(
        settings,
        worker=sdk_worker,
        worker_mode=mode,
        availability_monitor=NoObservation(),
        demo_allocation=demo,
        judge_allocation=judge,
    )
    with public_client(app) as client:
        response = client.post(
            "/api/runs",
            json={"script_text": "raise AssertionError('offline only')"},
            headers=AUTH,
        )
        assert response.status_code == 202, response.text
        run_id = response.json()["run_id"]
        final = done(client, run_id)
        assert final["status"] == "needs_human", final
        assert app.state.store.get_run(run_id)["api_funding_kind"] == "judge"
        assert (root / ("sdk-" + run_id + ".json")).is_file()
    with sqlite3.connect(judge_pool["receipt"]["ledger_path"]) as connection:
        assert connection.execute(
            "SELECT status,limit_usd FROM budget_runs WHERE id=?", (run_id,)
        ).fetchone() == ("closed", "0.30")
        assert (
            connection.execute(
                "SELECT count(*) FROM budget_attempts WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            == 1
        )
    assert not demo.started and not demo.finished
    assert not (root / "demo-private-ledger.db").exists()


@pytest.mark.parametrize("valid_judge", [False, True])
def test_launcher_explicit_judge_receipt_never_silently_falls_back(
    launcher, monkeypatch, valid_judge
):
    import json
    import os

    from headroom.acceptance import demo_binding, judge_binding

    module, root = launcher
    demo, judge = Allocation(root, "demo"), Allocation(root, "judge")
    monkeypatch.setenv("HEADROOM_PUBLIC_HOST", "demo.example")
    monkeypatch.setenv("HEADROOM_RUN_SUBMISSIONS_ENABLED", "true")
    monkeypatch.setenv("HEADROOM_PUBLIC_ALLOCATION_RECEIPT", str(root / "demo-receipt.json"))
    judge_path = root / ".cache/judge-access/receipt.json"
    monkeypatch.setenv("HEADROOM_JUDGE_ALLOCATION_RECEIPT", str(judge_path))
    monkeypatch.setenv("HEADROOM_JUDGE_TOKEN", TOKEN)
    monkeypatch.setenv("HEADROOM_BUDGET_DB_PATH", str(root / "previous.db"))
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "0.30")
    monkeypatch.setattr(demo_binding, "DemoAllocation", lambda *args, **kwargs: demo)

    def selected(path, *, project_root):
        assert path == str(judge_path) and project_root == root
        if not valid_judge:
            raise ValueError("invalid fixture receipt")
        return judge

    monkeypatch.setattr(judge_binding, "JudgeAllocation", selected)
    observed = []
    monkeypatch.setattr(
        module, "create_app", lambda settings, **kwargs: observed.append((settings, kwargs))
    )
    monkeypatch.setattr(module.uvicorn, "run", lambda *args, **kwargs: None)
    if not valid_judge:
        with pytest.raises(SystemExit, match="judge allocation"):
            module.main()
        assert not observed and not (root / "runs").exists()
        return
    entries = [{"id": "r7-20261029", "title": "Fixture"}]
    directory = root / "public-evidence"
    (directory / "published-evaluations").mkdir(parents=True)
    (directory / "public-evaluations.json").write_text(
        json.dumps({"version": 1, "campaigns": entries})
    )
    (directory / "published-evaluations/r7-20261029.json").write_text(
        json.dumps({"mode": "campaign", "provenance": "live", "rows": []})
    )
    module.main()
    settings, selected_allocations = observed[0]
    assert selected_allocations == {"demo_allocation": demo, "judge_allocation": judge}
    assert settings.snapshot_submissions_enabled is False
    assert os.environ["HEADROOM_BUDGET_DB_PATH"] == demo.receipt["ledger_path"]
    assert os.environ["HEADROOM_DAILY_BUDGET_USD"] == demo.receipt["amounts"]["daily_limit_usd"]


def test_judge_process_without_binding_never_uses_uncapped_worker(tmp_path):
    from headroom.orchestrator import FixRequest

    run_id = "b" * 32
    database = tmp_path / "store.db"
    store = Store(database)
    store.create_run(run_id, status="running")
    store.close()
    called = []

    def forbidden(*args, **kwargs):
        called.append(True)
        return {"status": "completed"}

    source = tmp_path / "train.py"
    source.write_text("pass")
    queue_module._process_entry(
        forbidden,
        FixRequest(script=str(source)).model_dump(),
        str(database),
        str(tmp_path),
        run_id,
        time.monotonic() + 10,
        None,
        "judge",
    )
    assert not called
    store = Store(database)
    assert store.get_run(run_id)["status"] == "failed"
    store.close()
