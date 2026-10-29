"""Trusted dual-pool routing with temporary stores and offline workers only."""

import sqlite3
import time

import pytest
from test_api import completed_worker, wait_done
from test_api import settings as isolated_settings
from test_judge_binding import pool as isolated_judge_pool
from test_public_access import EXAMPLE, HEADERS, public_client, public_settings
from test_public_launcher import launcher as isolated_launcher

from headroom.api import queue as queue_module
from headroom.api.app import create_app
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

    def begin(self, run_id, request, *, source_sha256):
        assert self.available
        assert source_sha256
        assert request.runtime_profile == self.receipt["profile_path"]
        assert request.daily_budget_usd == self.receipt["amounts"]["daily_limit_usd"]
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
def test_both_pools_share_one_persistent_ip_limit(setup, first_judge):
    app, demo, judge, dispatched = setup
    first, second = (AUTH, HEADERS) if first_judge else (HEADERS, AUTH)
    with public_client(app) as client:
        response = client.post("/api/runs", json=EXAMPLE, headers=first)
        assert response.status_code == 202
        wait_done(client, response.json()["run_id"])
        client.cookies.clear()
        assert client.post("/api/runs", json=EXAMPLE, headers=second).status_code == 429
        assert app.state.queue.hourly_limit == 1 and app.state.queue.deadline == 480
    assert len(demo.started) + len(judge.started) == 1
    assert dispatched == ["judge" if first_judge else "demo"]


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
