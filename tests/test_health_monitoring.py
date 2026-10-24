"""Offline HTTP-adapter and persistent notification-state tests; no live recipients."""

import json
import logging
import os
import socket
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from headroom import monitoring
from headroom.monitoring import (
    MonitorStateError,
    NotificationConfigError,
    check,
    read_webhook_config,
)

URL = "https://receiver.example.invalid/private-webhook-canary"
TOKEN = "offline-webhook-token-canary"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real network is forbidden in health notification tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def private_config(tmp_path, *, idempotent=False, mode=0o600):
    path = tmp_path / ".env"
    path.write_text(
        "HEADROOM_HEALTH_WEBHOOK_URL=" + URL + "\n"
        "HEADROOM_HEALTH_WEBHOOK_TOKEN=" + TOKEN + "\n"
        "HEADROOM_HEALTH_WEBHOOK_IDEMPOTENT=" + str(idempotent).lower() + "\n"
        "NEBIUS_API_KEY=unrelated-key-not-forwarded\n"
    )
    path.chmod(mode)
    return path


def health_transport(healthy=False):
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200 if healthy else 503,
            json={"status": "ok", "db": "ok", "queue": {"halted": False}},
        )
    )


def advance(tmp_path, now, *, healthy=False, notify=True, sender=None, config=None):
    return check(
        state_path=tmp_path / "health.json",
        now=now,
        notify=notify,
        env_file=config or tmp_path / ".env",
        health_transport=health_transport(healthy),
        webhook_transport=httpx.MockTransport(sender or (lambda request: httpx.Response(204))),
    )


def test_default_never_reads_credentials_or_dispatches_alert(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled notifications must not read credentials")

    monkeypatch.setattr(monitoring, "read_webhook_config", forbidden)
    calls = []
    first = advance(tmp_path, 0, notify=False, sender=lambda request: calls.append(request))
    due = advance(tmp_path, 120, notify=False, sender=lambda request: calls.append(request))
    assert first["failure_since"] == due["failure_since"] == 0
    assert not first["alert_due"] and due["alert_due"]
    assert due["notification_status"] == "disabled"
    assert due["notification"]["attempts"] == 0 and calls == []


def test_threshold_real_sender_payload_and_success_dedup(tmp_path):
    private_config(tmp_path)
    requests = []

    def receiver(request):
        requests.append(request)
        assert request.method == "POST" and str(request.url) == URL
        assert request.headers["Authorization"] == "Bearer " + TOKEN
        body = json.loads(request.content)
        assert set(body) == {"event", "status", "incident_id", "failure_since", "observed_at"}
        assert body["status"] == "unhealthy" and body["failure_since"] == 10
        assert body["observed_at"] == 130
        assert request.headers["Idempotency-Key"] == "headroom-health-" + body["incident_id"]
        persisted = json.loads((tmp_path / "health.json").read_text())
        assert persisted["notification"]["delivery_state"] == "sending"
        assert persisted["notification"]["attempts"] == 1
        return httpx.Response(202, text="sensitive response body must not be persisted")

    advance(tmp_path, 10, sender=receiver)
    before = advance(tmp_path, 129.999, sender=receiver)
    sent = advance(tmp_path, 130, sender=receiver)
    again = advance(tmp_path, 160, sender=receiver)
    assert not before["alert_due"] and sent["alert_due"]
    assert sent["notification_sent"] and again["notification_sent"]
    assert sent["notification_status"] == "accepted" and len(requests) == 1
    assert sent["notification"]["last_http_status"] == 202
    serialized = json.dumps(sent) + (tmp_path / "health.json").read_text()
    assert URL not in serialized and TOKEN not in serialized and "unrelated-key" not in serialized
    assert "sensitive response body" not in serialized
    assert stat.S_IMODE((tmp_path / "health.json").stat().st_mode) == 0o600


def test_recovery_and_next_incident_reset_dedup(tmp_path):
    private_config(tmp_path)
    sent_ids = []

    def receiver(request):
        sent_ids.append(json.loads(request.content)["incident_id"])
        return httpx.Response(204)

    advance(tmp_path, 0, sender=receiver)
    advance(tmp_path, 120, sender=receiver)
    recovered = advance(tmp_path, 150, healthy=True, sender=receiver)
    assert recovered["failure_since"] is None and recovered["incident_id"] is None
    assert recovered["notification"]["attempts"] == 0
    advance(tmp_path, 180, sender=receiver)
    second = advance(tmp_path, 300, sender=receiver)
    assert second["notification_sent"] and len(set(sent_ids)) == 2


@pytest.mark.parametrize("kind", ["read_timeout", "write_error", "protocol_error", "500", "408"])
def test_unknown_delivery_is_not_retried_by_default(tmp_path, kind):
    private_config(tmp_path)
    calls = []

    def receiver(request):
        calls.append(request)
        if kind.isdigit():
            return httpx.Response(int(kind), text=URL + TOKEN)
        error = {
            "read_timeout": httpx.ReadTimeout,
            "write_error": httpx.WriteError,
            "protocol_error": httpx.RemoteProtocolError,
        }[kind]
        raise error(URL + TOKEN, request=request)

    advance(tmp_path, 0, sender=receiver)
    failed = advance(tmp_path, 120, sender=receiver)
    later = advance(tmp_path, 500, sender=receiver)
    assert failed["notification"]["delivery_state"] == "unknown"
    assert later["notification_status"] == "delivery_unknown"
    assert len(calls) == 1 and not later["notification_sent"]
    assert URL not in json.dumps(later) and TOKEN not in json.dumps(later)


@pytest.mark.parametrize("kind", ["connect_timeout", "connect_error", "pool_timeout", "429"])
def test_definite_non_delivery_retries_at_most_three_with_backoff(tmp_path, kind):
    private_config(tmp_path)
    calls = []

    def receiver(request):
        calls.append(request)
        if kind == "429":
            return httpx.Response(429)
        error = {
            "connect_timeout": httpx.ConnectTimeout,
            "connect_error": httpx.ConnectError,
            "pool_timeout": httpx.PoolTimeout,
        }[kind]
        raise error("fixture", request=request)

    advance(tmp_path, 0, sender=receiver)
    advance(tmp_path, 120, sender=receiver)
    waiting = advance(tmp_path, 179, sender=receiver)
    advance(tmp_path, 180, sender=receiver)
    advance(tmp_path, 299, sender=receiver)
    advance(tmp_path, 300, sender=receiver)
    exhausted = advance(tmp_path, 600, sender=receiver)
    assert waiting["notification_status"] == "retry_wait"
    assert exhausted["notification_status"] == "retry_exhausted"
    assert len(calls) == 3 and exhausted["notification"]["attempts"] == 3
    assert len({request.headers["Idempotency-Key"] for request in calls}) == 1


def test_explicit_receiver_idempotency_allows_bounded_unknown_retry(tmp_path):
    private_config(tmp_path, idempotent=True)
    calls = []

    def receiver(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("fixture", request=request)
        return httpx.Response(204)

    advance(tmp_path, 0, sender=receiver)
    advance(tmp_path, 120, sender=receiver)
    waiting = advance(tmp_path, 179, sender=receiver)
    success = advance(tmp_path, 180, sender=receiver)
    advance(tmp_path, 500, sender=receiver)
    assert waiting["notification_status"] == "retry_wait"
    assert success["notification_sent"] and len(calls) == 2
    assert calls[0].headers["Idempotency-Key"] == calls[1].headers["Idempotency-Key"]
    assert calls[0].content == calls[1].content
    assert json.loads(calls[1].content)["observed_at"] == 120


@pytest.mark.parametrize("status_code", [301, 302, 307, 308, 400, 401, 403, 404])
def test_redirects_and_permanent_rejections_do_not_follow_or_retry(tmp_path, status_code):
    private_config(tmp_path, idempotent=True)
    requests = []

    def receiver(request):
        requests.append(request)
        return httpx.Response(status_code, headers={"Location": "https://elsewhere.invalid/secret"})

    advance(tmp_path, 0, sender=receiver)
    result = advance(tmp_path, 120, sender=receiver)
    later = advance(tmp_path, 500, sender=receiver)
    assert result["notification"]["delivery_state"] == "rejected"
    assert later["notification_status"] == "rejected"
    assert len(requests) == 1


def test_process_interruption_leaves_claim_and_does_not_auto_replay(tmp_path):
    private_config(tmp_path)
    calls = []

    def interrupted(request):
        calls.append(request)
        raise KeyboardInterrupt

    advance(tmp_path, 0, sender=interrupted)
    with pytest.raises(KeyboardInterrupt):
        advance(tmp_path, 120, sender=interrupted)
    assert (
        json.loads((tmp_path / "health.json").read_text())["notification"]["delivery_state"]
        == "sending"
    )
    after_restart = advance(tmp_path, 500, sender=interrupted)
    assert after_restart["notification"]["delivery_state"] == "unknown"
    assert after_restart["notification"]["last_error_code"] == "interrupted_attempt"
    assert len(calls) == 1


def test_concurrent_check_does_not_dispatch_second_notification(tmp_path):
    private_config(tmp_path)
    advance(tmp_path, 0)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def receiver(request):
        calls.append(request)
        entered.set()
        assert release.wait(3)
        return httpx.Response(204)

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(advance, tmp_path, 120, sender=receiver)
        assert entered.wait(3)
        try:
            with pytest.raises(MonitorStateError, match="already_running"):
                advance(tmp_path, 120, sender=receiver)
        finally:
            release.set()
        assert first.result()["notification_sent"]
    assert len(calls) == 1
    assert advance(tmp_path, 150, sender=receiver)["notification_sent"]


def test_pre_dispatch_state_write_failure_prevents_send(tmp_path, monkeypatch):
    private_config(tmp_path)
    advance(tmp_path, 0)
    calls = []

    def fail(*args, **kwargs):
        raise OSError("synthetic storage failure")

    monkeypatch.setattr(monitoring, "_write_state", fail)
    with pytest.raises(OSError):
        advance(tmp_path, 120, sender=lambda request: calls.append(request))
    assert calls == []


def test_post_acceptance_state_failure_is_unknown_after_restart(tmp_path, monkeypatch):
    private_config(tmp_path)
    advance(tmp_path, 0)
    writes, calls = [], []
    original = monitoring._write_state

    def second_write_fails(path, value):
        writes.append(value["notification"]["delivery_state"])
        if len(writes) == 2:
            raise OSError("synthetic fsync failure")
        return original(path, value)

    def receiver(request):
        calls.append(request)
        return httpx.Response(204)

    with monkeypatch.context() as patcher:
        patcher.setattr(monitoring, "_write_state", second_write_fails)
        with pytest.raises(OSError):
            advance(tmp_path, 120, sender=receiver)
    result = advance(tmp_path, 500, sender=receiver)
    assert result["notification_status"] == "delivery_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "raw", ["not-json", "[]", '{"healthy":false}', '{"x":NaN}', '{"x":1,"x":2}']
)
def test_invalid_state_is_preserved_without_dispatch(tmp_path, raw):
    private_config(tmp_path)
    path = tmp_path / "health.json"
    path.write_text(raw)
    calls = []
    with pytest.raises(MonitorStateError):
        advance(tmp_path, 120, sender=lambda request: calls.append(request))
    assert path.read_text() == raw and calls == []


def test_legacy_failure_start_is_preserved(tmp_path):
    private_config(tmp_path)
    (tmp_path / "health.json").write_text(
        json.dumps(
            {
                "checked_at": 90,
                "healthy": False,
                "failure_since": 0,
                "alert_due": False,
                "notification_sent": False,
            }
        )
    )
    result = advance(tmp_path, 120)
    assert result["notification_sent"] and result["failure_since"] == 0
    assert result["schema_version"] == 1


def test_state_symlink_fifo_and_linked_directory_are_rejected(tmp_path):
    private_config(tmp_path)
    target = tmp_path / "original"
    target.write_text("unchanged")
    path = tmp_path / "health.json"
    path.symlink_to(target)
    with pytest.raises(MonitorStateError):
        advance(tmp_path, 0)
    assert target.read_text() == "unchanged"
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(MonitorStateError):
        advance(tmp_path, 0)
    path.unlink()
    linked = tmp_path / "linked"
    linked.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(MonitorStateError, match="directory_symlink"):
        check(state_path=linked / "health.json", health_transport=health_transport(), now=0)


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o400])
def test_config_requires_private_exact_0600(tmp_path, mode):
    path = private_config(tmp_path, mode=mode)
    with pytest.raises(NotificationConfigError):
        read_webhook_config(path)
    advance(tmp_path, 0)
    result = advance(tmp_path, 120)
    assert result["notification_status"] == "configuration_error"
    assert result["notification"]["attempts"] == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/hook",
        "https://user:pass@example.invalid/hook",
        "https://example.invalid:444/hook",
        "https://example.invalid/#fragment",
    ],
)
def test_invalid_destination_never_creates_sender(tmp_path, url):
    path = private_config(tmp_path)
    path.write_text("HEADROOM_HEALTH_WEBHOOK_URL=" + url + "\n")
    with pytest.raises(NotificationConfigError):
        read_webhook_config(path)


def test_missing_or_linked_secret_file_is_explicit_and_not_printed(tmp_path, capsys):
    advance(tmp_path, 0)
    missing = advance(tmp_path, 120)
    assert missing["notification_status"] == "configuration_error"
    target = tmp_path / "other"
    target.write_text("HEADROOM_HEALTH_WEBHOOK_URL=" + URL)
    target.chmod(0o600)
    (tmp_path / ".env").symlink_to(target)
    assert advance(tmp_path, 150)["notification"]["attempts"] == 0
    assert capsys.readouterr().out == ""


def test_only_requested_fields_use_private_config_and_ignore_ambient_env(tmp_path, monkeypatch):
    private_config(tmp_path)
    monkeypatch.setenv("HEADROOM_HEALTH_WEBHOOK_URL", "https://ambient.invalid/")
    monkeypatch.setenv("HTTP_PROXY", "http://private-proxy.invalid/")
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy.invalid/")
    config = read_webhook_config(tmp_path / ".env")
    assert config.url == URL and config.token == TOKEN
    assert URL not in repr(config) and TOKEN not in repr(config)


@pytest.mark.parametrize(
    "body",
    [
        {"status": "ok", "db": "bad", "queue": {"halted": False}},
        {"status": "ok", "db": "ok", "queue": {"halted": True}},
        {"status": "ok", "db": "ok"},
        [],
        {"status": "ok", "db": "ok", "queue": None},
    ],
)
def test_health_errors_are_failures_without_forwarding_body(tmp_path, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    result = check(state_path=tmp_path / "health.json", now=0, health_transport=transport)
    assert not result["healthy"]


def test_health_redirect_is_not_followed(tmp_path):
    requests = []

    def response(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": URL})

    result = check(
        state_path=tmp_path / "health.json",
        now=0,
        health_transport=httpx.MockTransport(response),
    )
    assert not result["healthy"] and len(requests) == 1


def test_backward_clock_is_explicit_and_does_not_send(tmp_path):
    private_config(tmp_path)
    advance(tmp_path, 100)
    with pytest.raises(MonitorStateError, match="clock_moved_backwards"):
        advance(tmp_path, 99)


def test_templates_remain_disabled_and_timer_has_bounded_accuracy():
    root = Path(__file__).resolve().parents[1]
    service = (root / "deploy/headroom-health.service").read_text()
    command = next(line for line in service.splitlines() if line.startswith("ExecStart="))
    assert "--notify" not in command and "TimeoutStartSec=20s" in service
    timer = (root / "deploy/headroom-health.timer").read_text()
    assert "OnUnitActiveSec=30" in timer and "AccuracySec=1s" in timer


def test_idempotent_receiver_replays_same_payload_after_lost_response(tmp_path):
    private_config(tmp_path, idempotent=True)
    received = {}

    def receiver(request):
        key = request.headers["Idempotency-Key"]
        if key not in received:
            received[key] = request.content
            raise httpx.ReadTimeout("Accepted upstream but response was lost", request=request)
        return httpx.Response(202 if received[key] == request.content else 409)

    advance(tmp_path, 0, sender=receiver)
    advance(tmp_path, 120, sender=receiver)
    recovered = advance(tmp_path, 180, sender=receiver)
    assert recovered["notification_sent"]
    assert recovered["notification"]["last_attempt_at"] == 180
    assert recovered["notification"]["payload"]["observed_at"] == 120
    assert len(received) == 1


def test_state_with_unrepresentable_time_is_preserved_without_send(tmp_path):
    raw = json.dumps(
        {
            "healthy": False,
            "checked_at": 10**400,
            "failure_since": 0,
            "notification_sent": False,
        }
    )
    (tmp_path / "health.json").write_text(raw)
    with pytest.raises(MonitorStateError):
        advance(tmp_path, 120)
    assert (tmp_path / "health.json").read_text() == raw


def test_private_webhook_url_never_reaches_info_logs_but_other_threads_do(tmp_path, caplog):
    private_config(tmp_path)
    logger = logging.getLogger("httpx")
    caplog.set_level(logging.INFO, logger="httpx")

    def receiver(request):
        with ThreadPoolExecutor(max_workers=1) as workers:
            workers.submit(logger.info, "other-thread-visible").result()
        return httpx.Response(204)

    advance(tmp_path, 0, sender=receiver)
    result = advance(tmp_path, 120, sender=receiver)
    logger.info("after-request-visible")
    assert result["notification_sent"]
    assert URL not in caplog.text and "private-webhook-canary" not in caplog.text
    assert TOKEN not in caplog.text
    assert "other-thread-visible" in caplog.text and "after-request-visible" in caplog.text
