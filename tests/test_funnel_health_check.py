"""Offline checks for the fixed origin/Funnel monitor; no real network or notifications."""

import asyncio
import json
import os
import ssl
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from scripts import check_funnel as monitor

NOW = datetime(2026, 10, 29, tzinfo=UTC)


def okay(_request):
    return httpx.Response(200, json={"status": "ok", "private_finances": "never persist"})


def test_both_layers_success_is_private_atomic_and_fixed_get(tmp_path, monkeypatch):
    seen = []
    original = httpx.AsyncClient

    class ObservedClient(original):
        def __init__(self, **kwargs):
            assert kwargs["verify"] is True
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False
            super().__init__(**kwargs)

    monkeypatch.setattr(monitor.httpx, "AsyncClient", ObservedClient)

    def transport(request):
        assert request.method == "GET"
        assert "authorization" not in request.headers
        seen.append(str(request.url))
        return okay(request)

    path = tmp_path / ".cache/funnel-health.json"
    result = monitor.check(state_path=path, transport=httpx.MockTransport(transport), now=NOW)
    assert sorted(seen) == sorted(monitor.TARGETS.values())
    assert result["healthy"] is True
    assert result["consecutive_failures"] == 0
    assert result["last_success_at_utc"] == NOW.isoformat()
    assert set(result["checks"]) == {"origin", "public"}
    assert all(item["status"] == "ok" for item in result["checks"].values())
    assert json.loads(path.read_text()) == result
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert "private_finances" not in path.read_text()
    assert "never persist" not in path.read_text()
    assert "http://" not in path.read_text()
    assert not list(path.parent.glob("*.tmp"))


def test_public_failure_preserves_last_success_and_separate_origin_state(tmp_path):
    path = tmp_path / "state.json"
    monitor.check(state_path=path, transport=httpx.MockTransport(okay), now=NOW)

    def transport(request):
        if request.url.host == "127.0.0.1":
            return okay(request)
        return httpx.Response(503, text="private provider error")

    for number in (1, 2):
        result = monitor.check(
            state_path=path,
            transport=httpx.MockTransport(transport),
            now=NOW + timedelta(minutes=number * 5),
        )
        assert result["healthy"] is False
        assert result["last_success_at_utc"] == NOW.isoformat()
        assert result["consecutive_failures"] == number
        assert result["checks"]["origin"]["consecutive_failures"] == 0
        assert result["checks"]["public"]["consecutive_failures"] == number
        assert result["checks"]["public"]["last_success_at_utc"] == NOW.isoformat()
        assert result["checks"]["public"]["http_status"] == 503
        assert result["checks"]["public"]["status"] == "http_error"
        assert "private provider" not in json.dumps(result)
    recovered = monitor.check(
        state_path=path, transport=httpx.MockTransport(okay), now=NOW + timedelta(minutes=15)
    )
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_success_at_utc"] != NOW.isoformat()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ("timeout", "timeout"),
        ("tls", "tls_error"),
        ("connection", "transport_error"),
        ("redirect", "redirect"),
        ("html", "invalid_json"),
        ("bad_status", "invalid_health"),
        ("array", "invalid_health"),
        ("duplicate", "invalid_json"),
        ("too_large", "response_too_large"),
    ],
)
def test_failure_codes_never_include_raw_errors_or_response(tmp_path, case, expected):
    seen = []

    def transport(request):
        seen.append(request)
        if case == "timeout":
            raise httpx.ReadTimeout("secret raw timeout")
        if case == "tls":
            try:
                raise ssl.SSLCertVerificationError("private certificate path")
            except ssl.SSLError as cause:
                raise httpx.ConnectError("secret tls detail") from cause
        if case == "connection":
            raise httpx.ConnectError("private IP and exception")
        if case == "redirect":
            return httpx.Response(302, headers={"Location": "https://private.invalid/"})
        if case == "html":
            return httpx.Response(200, text="<html>secret source</html>")
        if case == "bad_status":
            return httpx.Response(200, json={"status": "failed", "secret": "private"})
        if case == "array":
            return httpx.Response(200, json=[{"status": "ok"}])
        if case == "duplicate":
            return httpx.Response(200, content=b'{"status":"failed","status":"ok"}')
        return httpx.Response(200, content=b"x" * (monitor.MAX_BYTES + 1))

    result = monitor.check(
        state_path=tmp_path / "state.json",
        transport=httpx.MockTransport(transport),
        now=NOW,
    )
    assert len(seen) == 2
    assert all(item["status"] == expected for item in result["checks"].values())
    rendered = json.dumps(result)
    assert "secret" not in rendered and "private" not in rendered
    assert result["last_success_at_utc"] is None


def test_slow_success_is_not_down(monkeypatch):
    readings = iter([10.0, 18.3])
    monkeypatch.setattr(monitor, "time", SimpleNamespace(monotonic=lambda: next(readings)))
    result = asyncio.run(
        monitor._probe(monitor.TARGETS["public"], transport=httpx.MockTransport(okay))
    )
    assert result["status"] == "ok"
    assert result["latency_ms"] == 8300
    assert result["slow"] is True


def test_total_deadline_cancels_mock_that_never_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "REQUEST_SECONDS", 0.02)

    async def slow(_request):
        await asyncio.sleep(1)
        return httpx.Response(200, json={"status": "ok"})

    result = monitor.check(
        state_path=tmp_path / "state.json", transport=httpx.MockTransport(slow), now=NOW
    )
    assert all(item["status"] == "timeout" for item in result["checks"].values())


@pytest.mark.parametrize("kind", ["state", "parent", "lock"])
def test_symlink_state_paths_are_refused_before_requests(tmp_path, kind):
    outside = tmp_path / "outside"
    outside.mkdir()
    untouched = outside / "state.json"
    untouched.write_text("do not modify")
    path = tmp_path / "state.json"
    if kind == "state":
        path.symlink_to(untouched)
    elif kind == "parent":
        link = tmp_path / "linked"
        link.symlink_to(outside, target_is_directory=True)
        path = link / "state.json"
    else:
        path.with_name(path.name + ".lock").symlink_to(untouched)

    def forbidden(_request):
        pytest.fail("State protection must reject before any GET")

    with pytest.raises((OSError, monitor.StateError)):
        monitor.check(state_path=path, transport=httpx.MockTransport(forbidden), now=NOW)
    assert untouched.read_text() == "do not modify"


@pytest.mark.parametrize("contents", [b"not JSON", b'{"private":"never copy"}', b"x" * 65537])
def test_malformed_or_oversized_existing_state_is_preserved(tmp_path, contents):
    path = tmp_path / "state.json"
    path.write_bytes(contents)

    def forbidden(_request):
        pytest.fail("Invalid state must be rejected before any GET")

    with pytest.raises(monitor.StateError):
        monitor.check(state_path=path, transport=httpx.MockTransport(forbidden), now=NOW)
    assert path.read_bytes() == contents


def test_fifo_state_is_refused_without_blocking(tmp_path):
    path = tmp_path / "state.json"
    os.mkfifo(path)
    with pytest.raises(monitor.StateError):
        monitor.check(state_path=path, transport=httpx.MockTransport(okay), now=NOW)


def test_failed_atomic_replace_preserves_previous_state_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monitor.check(state_path=path, transport=httpx.MockTransport(okay), now=NOW)
    original = path.read_bytes()

    def fail(*_args, **_kwargs):
        raise OSError("private filesystem failure")

    monkeypatch.setattr(monitor.os, "replace", fail)
    with pytest.raises(OSError):
        monitor.check(
            state_path=path, transport=httpx.MockTransport(okay), now=NOW + timedelta(minutes=5)
        )
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_lock_refuses_overlap_and_clock_rollback_preserves_state(tmp_path):
    path = tmp_path / "state.json"
    monitor.check(state_path=path, transport=httpx.MockTransport(okay), now=NOW)
    original = path.read_bytes()
    with monitor._state_directory(path), pytest.raises(OSError):
        monitor.check(state_path=path, transport=httpx.MockTransport(okay), now=NOW)
    with pytest.raises(monitor.StateError, match="clock_moved_backwards"):
        monitor.check(
            state_path=path, transport=httpx.MockTransport(okay), now=NOW - timedelta(seconds=1)
        )
    assert path.read_bytes() == original


def test_target_and_transport_are_not_configurable(tmp_path):
    with pytest.raises(ValueError, match="target"):
        asyncio.run(monitor._probe("https://example.com/"))
    with pytest.raises(ValueError, match="offline"):
        monitor.check(state_path=tmp_path / "state.json", transport=object(), now=NOW)
