"""Offline availability checks: no credentials, network, CUDA or ledger mutations."""

import json
import socket
import sqlite3
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from headroom.api import availability
from headroom.api.app import ApiSettings, create_app
from headroom.config import OFFICIAL_BASE_URLS


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("External network is forbidden in availability tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def ledger(path, runs=(), attempts=()):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE budget_runs (id TEXT, day TEXT, limit_usd TEXT, status TEXT, halt_reason TEXT)"
        )
        connection.execute(
            "CREATE TABLE budget_attempts (run_id TEXT, charged_usd TEXT, actual_usd TEXT, settled INTEGER)"
        )
        connection.executemany("INSERT INTO budget_runs VALUES (?,?,?,?,?)", runs)
        connection.executemany("INSERT INTO budget_attempts VALUES (?,?,?,?)", attempts)


def read_budget(path, total="10", daily="4"):
    return availability.read_local_budget(
        path, total_limit=total, daily_limit=daily, day="2026-10-24"
    )


@pytest.mark.parametrize("pids,expected", [("", "available"), ("1234\n5678\n", "busy")])
def test_gpu_reads_metadata_only_and_redacts_processes(monkeypatch, pids, expected):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="22000, 24576\n" if len(calls) == 1 else pids)

    monkeypatch.setattr(subprocess, "run", run)
    result = availability.probe_gpu()
    assert result["status"] == expected
    assert result["available"] is (not bool(pids))
    assert result["checked_at"]
    assert result["devices"] == [{"free_mib": 22000, "total_mib": 24576}]
    assert "1234" not in json.dumps(result) and "5678" not in json.dumps(result)
    assert all(
        command[0] == "nvidia-smi" and kwargs["timeout"] == 1 and "shell" not in kwargs
        for command, kwargs in calls
    )


@pytest.mark.parametrize(
    "error,expected",
    [
        (FileNotFoundError("private path"), "unavailable"),
        (subprocess.TimeoutExpired("private command", 1), "unknown"),
        (subprocess.CalledProcessError(1, "private command"), "unknown"),
    ],
)
def test_gpu_errors_do_not_claim_availability_or_expose_diagnostics(monkeypatch, error, expected):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(subprocess, "run", fail)
    result = availability.probe_gpu()
    assert result["status"] == expected and result["busy"] is None
    assert result["available"] is not True
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("output", ["", "bad, data", "2, 1", "-1, 20", "1, 2, 3"])
def test_gpu_invalid_metadata_is_unknown(monkeypatch, output):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=output))
    assert availability.probe_gpu()["status"] == "unknown"


@pytest.mark.parametrize(
    "status,expected",
    [
        (200, "reachable"),
        (401, "reachable"),
        (403, "reachable"),
        (503, "degraded"),
        (302, "degraded"),
    ],
)
def test_provider_headers_only_without_authentication(monkeypatch, status, expected):
    real_client = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            status, headers={"location": "https://example.invalid/private"}, text="PRIVATE RESPONSE"
        )

    def client(**kwargs):
        assert kwargs == {"timeout": 2, "follow_redirects": False, "trust_env": False}
        return real_client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", client)
    result = availability.probe_provider(OFFICIAL_BASE_URLS[0])
    assert len(requests) == 1
    assert requests[0].method == "GET" and str(requests[0].url) == OFFICIAL_BASE_URLS[0] + "models"
    assert "authorization" not in requests[0].headers
    assert not requests[0].content
    assert result["status"] == expected and result["reachable"] is True
    assert result["authentication_checked"] is False
    assert "PRIVATE" not in json.dumps(result)


def test_provider_network_failure_is_redacted(monkeypatch):
    real_client = httpx.Client

    def fail(request):
        raise httpx.ConnectError("secret diagnostic")

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(fail), **kw)
    )
    result = availability.probe_provider(OFFICIAL_BASE_URLS[1])
    assert result["reachable"] is False and result["authentication_checked"] is False
    assert "secret" not in json.dumps(result)


def test_provider_rejects_unreviewed_endpoint_before_client(monkeypatch):
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("unexpected client"))
    result = availability.probe_provider("https://example.invalid/")
    assert result["reachable"] is None and result["status"] == "unknown"


def test_budget_reservations_daily_limit_and_actuals_are_separate(tmp_path, monkeypatch):
    path = tmp_path / "budget.db"
    ledger(
        path,
        [
            ("old", "2026-10-23", "3", "closed", None),
            ("active", "2026-10-24", "2", "open", None),
            ("done", "2026-10-24", "1", "closed", None),
        ],
        [("old", "1", "1", 1), ("active", ".1", ".1", 1), ("done", ".25", ".25", 1)],
    )
    before, modified = path.read_bytes(), path.stat().st_mtime_ns
    monkeypatch.setattr(
        "headroom.budget.BudgetLedger", lambda *a, **k: pytest.fail("mutating ledger constructed")
    )
    result = read_budget(path)
    assert result["committed_usd"] == "3.25"
    assert result["remaining_usd"] == result["daily_remaining_usd"] == "1.75"
    assert result["authorized_remaining_usd"] == "6.75"
    assert result["known_charge_usd"] == result["total_actual_usd"] == "1.35"
    assert (
        result["account_balance"] is None and result["scope"] == "local_application_authorization"
    )
    assert path.read_bytes() == before and path.stat().st_mtime_ns == modified
    assert sorted(p.name for p in tmp_path.iterdir()) == ["budget.db"]


def test_missing_budget_does_not_create_directory_or_database(tmp_path):
    path = tmp_path / "absent" / "budget.db"
    result = read_budget(path, total=".10")
    assert result["remaining_usd"] == "0.10"
    assert result["ledger_initialized"] is False
    assert not path.parent.exists()


def test_unknown_usage_retains_conservative_reservation_and_pending_state(tmp_path):
    path = tmp_path / "budget.db"
    ledger(path, [("run", "2026-10-24", ".5", "open", None)], [("run", ".2", None, 0)])
    result = read_budget(path, total="1")
    assert result["unknown_attempts"] == result["pending_attempts"] == 1
    assert result["total_actual_usd"] is None
    assert result["committed_usd"] == "0.5" and result["remaining_usd"] == "0.5"
    assert result["status"] == "pending_charge" and result["dispatch_blocked"]
    assert result["settled_unknown_attempts"] == 0


@pytest.mark.parametrize(
    "halt,total,expected",
    [
        (None, ".5", "billing_review_required"),
        ("private billing detail", "10", "billing_review_required"),
    ],
)
def test_budget_exhaustion_and_unresolved_bound(tmp_path, halt, total, expected):
    path = tmp_path / "budget.db"
    ledger(path, [("run", "2026-10-24", ".5", "closed", halt)], [("run", ".5", None, 1)])
    result = read_budget(path, total=total)
    assert result["status"] == expected and result["total_actual_usd"] is None
    assert result["billing_bound_unresolved"] is (halt is not None)
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize(
    "kind", ["malformed", "symlink", "unknown-status", "orphan", "invalid-limit"]
)
def test_unreadable_or_inconsistent_budget_stays_unknown(tmp_path, kind):
    path = tmp_path / "budget.db"
    if kind == "malformed":
        path.write_text("not a database")
    elif kind == "symlink":
        target = tmp_path / "missing"
        path.symlink_to(target)
    elif kind == "unknown-status":
        ledger(path, [("r", "2026-10-24", "1", "bad", None)])
    elif kind == "orphan":
        ledger(path, attempts=[("missing", "1", "1", 1)])
    result = read_budget(path, total="-1" if kind == "invalid-limit" else "10")
    assert result["status"] == "unknown" and result["remaining_usd"] is None
    assert str(tmp_path) not in json.dumps(result)


def test_budget_reads_committed_wal_state_without_waiting_for_writer(tmp_path):
    path = tmp_path / "budget.db"
    ledger(path, [("r", "2026-10-24", "1", "open", None)])
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("UPDATE budget_runs SET limit_usd='2'")
        connection.commit()
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("UPDATE budget_runs SET limit_usd='3'")
        assert read_budget(path)["committed_usd"] == "2"
    finally:
        connection.rollback()
        connection.close()


def settings_for(path):
    return SimpleNamespace(project_root=path, runtime_profile=None, runtime_configured=False)


class ControlledSchedule:
    """Advance background cycles independently of simulated HTTP request time."""

    def __init__(self):
        self.now = 0
        self.ticks = __import__("queue").Queue()
        self.condition = threading.Condition()
        self.completed = 0

    def wait(self, stop, seconds):
        assert seconds == 5
        with self.condition:
            self.completed += 1
            self.condition.notify_all()
        while not stop.wait(0.01):
            try:
                self.ticks.get_nowait()
                return False
            except __import__("queue").Empty:
                pass
        return True

    def await_completed(self, count):
        with self.condition:
            assert self.condition.wait_for(lambda: self.completed >= count, timeout=2)

    def advance(self, second):
        self.now = second
        self.ticks.put(True)


def test_monitor_nonblocking_cache_expiry_and_single_refresh(tmp_path):
    release, entered = threading.Event(), threading.Event()
    schedule = ControlledSchedule()
    calls = []

    def gpu():
        calls.append("gpu")
        entered.set()
        assert release.wait(2)
        return {
            "status": "busy",
            "available": False,
            "busy": True,
            "checked_at": availability.timestamp(),
        }

    def provider(endpoint):
        calls.append(endpoint)
        return {"status": "reachable", "reachable": True, "checked_at": availability.timestamp()}

    monitor = availability.AvailabilityMonitor(
        settings_for(tmp_path),
        gpu_probe=gpu,
        provider_probe=provider,
        profile_loader=lambda p: None,
        clock=lambda: schedule.now,
        waiter=schedule.wait,
    )
    try:
        first = monitor.snapshot()
        assert entered.wait(1)
        assert first["gpu"]["status"] == "unknown" and first["gpu"]["busy"] is None
        assert monitor.snapshot()["gpu"]["refreshing"] is True and calls == ["gpu"]
        release.set()
        schedule.await_completed(1)
        fresh = monitor.snapshot()
        assert fresh["gpu"]["status"] == "busy" and fresh["token_factory"]["reachable"] is True
        assert fresh["gpu"]["refreshing"] is False
        assert not fresh["token_factory"]["configured"]
        assert fresh["token_factory"]["authentication_checked"] is False
        assert len(calls) == 2
        entered.clear()
        release.clear()
        schedule.advance(5)
        assert entered.wait(1)
        assert monitor.snapshot()["gpu"]["status"] == "busy"
        schedule.now = 16
        stale = monitor.snapshot()
        assert stale["gpu"]["status"] == "unknown" and stale["gpu"]["busy"] is None
        assert stale["gpu"]["checked_at"] == fresh["gpu"]["checked_at"]
        assert stale["token_factory"]["reachable"] is None
        release.set()
        schedule.await_completed(2)
    finally:
        release.set()
        monitor.close()
    assert not monitor.thread.is_alive()
    schedule.advance(32)
    monitor.snapshot()
    assert len(calls) == 4


def test_background_refresh_keeps_equal_interval_health_polls_fresh(tmp_path):
    schedule = ControlledSchedule()
    entered, release = threading.Event(), threading.Event()
    release.set()
    samples = []

    def gpu():
        entered.set()
        assert release.wait(2)
        samples.append(schedule.now)
        return {
            "status": "busy",
            "available": False,
            "busy": True,
            "checked_at": f"sample-{schedule.now}",
        }

    monitor = availability.AvailabilityMonitor(
        settings_for(tmp_path),
        gpu_probe=gpu,
        provider_probe=lambda endpoint: {"status": "reachable", "reachable": True},
        profile_loader=lambda p: None,
        clock=lambda: schedule.now,
        waiter=schedule.wait,
    )
    try:
        monitor.snapshot()  # Initial HTTP request starts one background monitor.
        schedule.await_completed(1)
        # Browser polls exactly every TTL, while background observations occur
        # between requests. Pause the new probe during each HTTP request to
        # verify that an older but still fresh busy observation stays usable.
        for second in range(5, 61, 5):
            entered.clear()
            if second % 15 == 0:
                release.clear()
            schedule.advance(second)
            assert entered.wait(1)
            if second % 15 == 0:
                observed = monitor.snapshot()
                assert observed["gpu"]["status"] == "busy"
                assert observed["gpu"]["busy"] is True and not observed["gpu"]["stale"]
                assert observed["gpu"]["refreshing"] is True
                assert observed["gpu"]["checked_at"] == f"sample-{second - 5}"
                assert observed["token_factory"]["reachable"] is True
                release.set()
            schedule.await_completed(second // 5 + 1)
        assert samples == list(range(0, 61, 5))
        # A genuinely stalled probe must still expire the last known result.
        release.clear()
        entered.clear()
        schedule.advance(65)
        assert entered.wait(1)
        schedule.now = 76
        expired = monitor.snapshot()
        assert expired["gpu"]["status"] == "unknown" and expired["gpu"]["busy"] is None
        assert expired["gpu"]["checked_at"] == "sample-60"
        assert expired["token_factory"]["reachable"] is None
    finally:
        release.set()
        monitor.close()
    assert not monitor.thread.is_alive()


def test_slow_provider_cannot_refresh_an_older_gpu_timestamp(tmp_path):
    entered, release = threading.Event(), threading.Event()
    schedule = ControlledSchedule()

    def provider(endpoint):
        entered.set()
        assert release.wait(2)
        return {"status": "reachable", "reachable": True, "checked_at": "provider-16"}

    monitor = availability.AvailabilityMonitor(
        settings_for(tmp_path),
        gpu_probe=lambda: {
            "status": "busy",
            "busy": True,
            "available": False,
            "checked_at": "gpu-0",
        },
        provider_probe=provider,
        profile_loader=lambda p: None,
        clock=lambda: schedule.now,
        waiter=schedule.wait,
    )
    try:
        monitor.snapshot()
        assert entered.wait(1)
        assert monitor.snapshot()["gpu"]["busy"] is True
        schedule.now = 16
        release.set()
        schedule.await_completed(1)
        observed = monitor.snapshot()
        assert observed["gpu"]["status"] == "unknown" and observed["gpu"]["busy"] is None
        assert observed["gpu"]["checked_at"] == "gpu-0"
        assert observed["token_factory"]["reachable"] is True
        assert not observed["token_factory"]["stale"]
    finally:
        release.set()
        monitor.close()


def test_monitor_shutdown_wakes_scheduled_wait_without_more_probes(tmp_path):
    done = threading.Event()
    calls = []

    def gpu():
        calls.append("gpu")
        return {"status": "available", "available": True, "busy": False}

    def provider(endpoint):
        calls.append("provider")
        done.set()
        return {"status": "reachable", "reachable": True}

    monitor = availability.AvailabilityMonitor(
        settings_for(tmp_path),
        gpu_probe=gpu,
        provider_probe=provider,
        profile_loader=lambda p: None,
    )
    monitor.snapshot()
    assert done.wait(1)
    monitor.close()
    assert not monitor.thread.is_alive()
    monitor.snapshot()
    assert calls == ["gpu", "provider"]


def test_monitor_configured_profile_reads_budget_without_secrets_or_probes(tmp_path, monkeypatch):
    def denied(*a, **kw):
        pytest.fail("credential read or external probe")

    monkeypatch.setattr("headroom.runtime.read_nebius_key", denied)
    profile = SimpleNamespace(base_url=OFFICIAL_BASE_URLS[0], authorized_total_usd="1")
    monitor = availability.AvailabilityMonitor(
        settings_for(tmp_path),
        enabled=False,
        gpu_probe=denied,
        provider_probe=denied,
        profile_loader=lambda p: profile,
    )
    result = monitor.snapshot()
    assert (
        result["token_factory"]["configured"] is True
        and result["token_factory"]["reachable"] is None
    )
    assert result["local_budget"]["remaining_usd"] == "1"
    assert not (tmp_path / ".cache").exists()
    monkeypatch.setenv("HEADROOM_DAILY_BUDGET_USD", "not-money")
    invalid = monitor.snapshot()["local_budget"]
    assert invalid["status"] == "unknown" and invalid["remaining_usd"] is None


def test_health_and_usage_share_safe_global_observations(tmp_path):
    class Monitor:
        closed = False

        def snapshot(self):
            return {
                "gpu": {
                    "status": "busy",
                    "busy": True,
                    "available": False,
                    "checked_at": "2026-10-24T00:00:00+00:00",
                },
                "token_factory": {
                    "configured": False,
                    "reachable": None,
                    "authentication_checked": False,
                },
                "local_budget": {
                    "status": "exhausted",
                    "scope": "local_application_authorization",
                    "remaining_usd": "0",
                    "account_balance": None,
                },
            }

        def close(self):
            self.closed = True

    monitor = Monitor()
    project = Path(__file__).resolve().parents[1]
    settings = ApiSettings(
        project_root=project,
        data_root=tmp_path / "api",
        db_path=tmp_path / "api.db",
        run_root=tmp_path / "runs",
        web_dist=tmp_path / "web",
    )
    with TestClient(
        create_app(
            settings, worker=lambda *a, **kw: pytest.fail("no job"), availability_monitor=monitor
        )
    ) as client:
        health, usage = client.get("/api/health").json(), client.get("/api/usage").json()
        assert health["gpu"]["busy"] is True
        assert usage["scope"] == "current_session"
        assert usage["local_budget"] == health["local_budget"]
        assert str(project) not in json.dumps(health)
    assert monitor.closed


def test_real_ledger_pending_status_recovers_after_settlement(tmp_path, monkeypatch):
    monkeypatch.setattr("headroom.budget.current_utc_day", lambda: "2026-10-24")
    from headroom.budget import BudgetLedger

    path = tmp_path / "budget.db"
    b = BudgetLedger(path, daily_limit="2", day="2026-10-24")
    b.open_run("run", "0.6")
    b.reserve("run", "call", "0.04", admission_kind="local_estimate")
    assert read_budget(path)["status"] == "pending_charge"
    b.settle("run", "call", "0.01")
    result = read_budget(path)
    assert result["status"] == "available" and result["dispatch_blocked"] is False
    assert result["total_actual_usd"] == "0.01"
