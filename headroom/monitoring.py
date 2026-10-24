"""Local health sampling and explicitly enabled, idempotency-aware webhook alerts."""

import fcntl
import io
import json
import logging
import math
import os
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HEALTH_URLS = {"http://127.0.0.1:8000/api/health", "http://localhost:8000/api/health"}
FAILURE_SECONDS = 120
MAX_ATTEMPTS = 3
RETRY_SECONDS = (60, 120)
STATE_BYTES = 64 * 1024


class MonitorStateError(ValueError):
    """Fixed code only: never include credentials or provider exception messages."""


class NotificationConfigError(ValueError):
    """A missing/invalid explicitly configured private destination."""


@dataclass(frozen=True)
class WebhookConfig:
    url: str = field(repr=False)
    token: str | None = field(default=None, repr=False)
    idempotent: bool = False


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_key")
        value[key] = item
    return value


def _decode(data):
    return json.loads(
        data,
        object_pairs_hook=_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")),
    )


def read_webhook_config(path=PROJECT_ROOT / ".env"):
    """Only called after explicit --notify and a due incident; never import ambient keys."""
    path = Path(path)
    if path.name != ".env":
        raise NotificationConfigError("private_dotenv_required")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()
                or info.st_size > STATE_BYTES
            ):
                raise NotificationConfigError("private_dotenv_mode_or_type_invalid")
            raw = handle.read(STATE_BYTES + 1)
        if len(raw) > STATE_BYTES:
            raise NotificationConfigError("private_dotenv_too_large")
        values = dotenv_values(stream=io.StringIO(raw.decode()), interpolate=False)
    except (OSError, UnicodeError, ValueError) as error:
        if isinstance(error, NotificationConfigError):
            raise
        raise NotificationConfigError("private_dotenv_unavailable") from None
    url = values.get("HEADROOM_HEALTH_WEBHOOK_URL") or ""
    token = values.get("HEADROOM_HEALTH_WEBHOOK_TOKEN") or None
    idempotent = (values.get("HEADROOM_HEALTH_WEBHOOK_IDEMPOTENT") or "false").lower()
    try:
        parsed = urlsplit(url)
        valid_url = (
            0 < len(url) <= 4096
            and parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and parsed.port in (None, 443)
            and not any(ord(char) <= 32 or ord(char) == 127 for char in url)
            and "\\" not in url
        )
        httpx.URL(url)
    except (ValueError, httpx.InvalidURL):
        valid_url = False
    if not valid_url:
        raise NotificationConfigError("https_webhook_required")
    if token is not None and (
        len(token) > 8192 or any(ord(char) <= 32 or ord(char) >= 127 for char in token)
    ):
        raise NotificationConfigError("invalid_webhook_token")
    if idempotent not in {"true", "false"}:
        raise NotificationConfigError("invalid_idempotency_contract")
    return WebhookConfig(url, token, idempotent == "true")


def _transport(value):
    if value is not None and not isinstance(value, httpx.MockTransport):
        raise ValueError("Only offline MockTransport injection is supported")
    return value


def probe_health(url, *, transport=None):
    if url not in HEALTH_URLS:
        raise ValueError("Only the local production health endpoint is supported")
    try:
        with (
            httpx.Client(
                transport=_transport(transport),
                trust_env=False,
                follow_redirects=False,
                timeout=5,
            ) as client,
            client.stream("GET", url, headers={"Accept": "application/json"}) as response,
        ):
            if response.status_code != 200:
                return False
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > STATE_BYTES:
                    return False
        data = _decode(body)
        return (
            isinstance(data, dict)
            and data.get("status") == "ok"
            and data.get("db") == "ok"
            and isinstance(data.get("queue"), dict)
            and data["queue"].get("halted") is False
        )
    except (httpx.HTTPError, ValueError, OSError):
        return False


@contextmanager
def _private_http_logging():
    # HTTPX logs the normalized URL at INFO. Suppress only this sending thread's
    # library records during the private request; other threads/loggers stay intact.
    owner = threading.get_ident()
    logger = logging.getLogger("httpx")

    def allow(record):
        return record.thread != owner

    logger.addFilter(allow)
    try:
        yield
    finally:
        logger.removeFilter(allow)


def send_webhook(config, payload, *, transport=None):
    """Exactly one HTTP attempt; no automatic HTTP retry, redirects or body logging."""
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": "headroom-health-" + payload["incident_id"],
    }
    if config.token:
        headers["Authorization"] = "Bearer " + config.token
    try:
        with (
            _private_http_logging(),
            httpx.Client(
                transport=_transport(transport),
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(5, connect=3, pool=1),
            ) as client,
            client.stream("POST", config.url, headers=headers, json=payload) as response,
        ):
            status_code = response.status_code
        if 200 <= status_code < 300:
            state, code = "accepted", None
        elif status_code == 429:
            state, code = "not_sent", "rate_limited"
        elif status_code == 408 or status_code >= 500:
            state, code = "unknown", "receiver_outcome_unknown"
        else:
            state, code = "rejected", "http_rejected"
        return {"delivery_state": state, "last_http_status": status_code, "last_error_code": code}
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        return {
            "delivery_state": "not_sent",
            "last_http_status": None,
            "last_error_code": "connection_not_established",
        }
    except httpx.HTTPError:
        return {
            "delivery_state": "unknown",
            "last_http_status": None,
            "last_error_code": "transport_outcome_unknown",
        }


def _empty_notification():
    return {
        "delivery_state": "not_attempted",
        "attempts": 0,
        "last_attempt_at": None,
        "next_attempt_at": None,
        "last_http_status": None,
        "last_error_code": None,
        "payload": None,
    }


def _validate(previous):
    if not isinstance(previous, dict):
        raise MonitorStateError("invalid_state")
    if not previous:
        return previous
    if (
        type(previous.get("healthy")) is not bool
        or not _number(previous.get("checked_at"))
        or (previous.get("failure_since") is not None and not _number(previous["failure_since"]))
        or type(previous.get("notification_sent")) is not bool
    ):
        raise MonitorStateError("invalid_state")
    if previous.get("schema_version") is None:
        # Legacy checker never dispatched notifications. Retain its continuous failure clock.
        if previous["notification_sent"] or (
            previous["healthy"] is False and previous.get("failure_since") is None
        ):
            raise MonitorStateError("invalid_legacy_state")
        previous["notification"] = _empty_notification()
        previous["incident_id"] = None if previous["healthy"] else uuid4().hex
        return previous
    item = previous.get("notification")
    incident = previous.get("incident_id")
    if (
        previous["schema_version"] != 1
        or not isinstance(item, dict)
        or set(item) != set(_empty_notification())
        or type(item.get("attempts")) is not int
        or not 0 <= item["attempts"] <= MAX_ATTEMPTS
        or item.get("delivery_state")
        not in {
            "not_attempted",
            "sending",
            "accepted",
            "unknown",
            "not_sent",
            "rejected",
        }
        or any(
            item.get(key) is not None and not _number(item[key])
            for key in (
                "last_attempt_at",
                "next_attempt_at",
            )
        )
        or previous["notification_sent"] != (item["delivery_state"] == "accepted")
        or (previous["healthy"] and (incident is not None or previous["failure_since"] is not None))
        or (
            not previous["healthy"]
            and (
                not isinstance(incident, str)
                or len(incident) != 32
                or any(char not in "0123456789abcdef" for char in incident)
                or previous["failure_since"] is None
            )
        )
        or (item["attempts"] == 0) != (item["delivery_state"] == "not_attempted")
        or (item["attempts"] > 0 and item.get("last_attempt_at") is None)
    ):
        raise MonitorStateError("invalid_state")
    payload = item["payload"]
    if item["attempts"] == 0:
        valid_payload = payload is None
    else:
        valid_payload = (
            isinstance(payload, dict)
            and set(payload) == {"event", "status", "incident_id", "failure_since", "observed_at"}
            and payload.get("event") == "headroom.health_failure"
            and payload.get("status") == "unhealthy"
            and payload.get("incident_id") == incident
            and payload.get("failure_since") == previous["failure_since"]
            and _number(payload.get("observed_at"))
            and previous["failure_since"] <= payload["observed_at"] <= previous["checked_at"]
        )
    if not valid_payload:
        raise MonitorStateError("invalid_state_payload")
    return previous


def _read_state(path):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {}
    except OSError:
        raise MonitorStateError("state_unavailable") from None
    try:
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > STATE_BYTES:
                raise MonitorStateError("invalid_state_file")
            raw = handle.read(STATE_BYTES + 1)
        if len(raw) > STATE_BYTES:
            raise MonitorStateError("invalid_state_file")
        return _validate(_decode(raw))
    except (ValueError, UnicodeError, OSError):
        raise MonitorStateError("invalid_state") from None


def _write_state(path, value):
    temporary = path.with_name("." + path.name + "." + uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked(path):
    parent = path.parent
    for current in (parent, *parent.parents):
        if current.is_symlink():
            raise MonitorStateError("state_directory_symlink")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_name(path.name + ".lock")
    try:
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise MonitorStateError("lock_unavailable") from None
    with os.fdopen(descriptor, "a+") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise MonitorStateError("invalid_lock_file")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MonitorStateError("check_already_running") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def check(
    url="http://127.0.0.1:8000/api/health",
    *,
    state_path=Path("runs/health.json"),
    notify=False,
    env_file=PROJECT_ROOT / ".env",
    now=None,
    health_transport=None,
    webhook_transport=None,
):
    """One locked sample; defaults never read a credential or send an alert."""
    _transport(health_transport)
    _transport(webhook_transport)
    if url not in HEALTH_URLS or type(notify) is not bool:
        raise ValueError("Invalid health-check configuration")
    now = time.time() if now is None else now
    if not _number(now):
        raise ValueError("Invalid observation time")
    path = Path(state_path).absolute()
    with _locked(path):
        previous = _read_state(path)
        if previous and now < previous["checked_at"]:
            raise MonitorStateError("clock_moved_backwards")
        healthy = probe_health(url, transport=health_transport)
        same_incident = previous and previous["healthy"] is False and not healthy
        failure_since = None if healthy else previous["failure_since"] if same_incident else now
        notification = dict(previous["notification"]) if same_incident else _empty_notification()
        state = {
            "schema_version": 1,
            "checked_at": now,
            "healthy": healthy,
            "failure_since": failure_since,
            "incident_id": previous["incident_id"]
            if same_incident
            else None
            if healthy
            else uuid4().hex,
            "alert_due": failure_since is not None and now - failure_since >= FAILURE_SECONDS,
            "notification_sent": notification["delivery_state"] == "accepted",
            "notification": notification,
            "notification_status": "healthy" if healthy else "waiting_threshold",
        }
        if notification["delivery_state"] == "sending":
            notification.update(delivery_state="unknown", last_error_code="interrupted_attempt")
        if state["alert_due"]:
            if state["notification_sent"]:
                state["notification_status"] = "accepted"
            elif not notify:
                state["notification_status"] = "disabled"
            else:
                _notify(state, path, env_file, now, webhook_transport)
        _write_state(path, state)
        return state


def _notify(state, path, env_file, now, transport):
    item = state["notification"]
    try:
        config = read_webhook_config(env_file)
    except NotificationConfigError as error:
        state.update(notification_status="configuration_error", configuration_error=str(error))
        return
    if item["attempts"] >= MAX_ATTEMPTS:
        state["notification_status"] = "retry_exhausted"
        return
    if item["delivery_state"] == "rejected":
        state["notification_status"] = "rejected"
        return
    if item["delivery_state"] == "unknown" and not config.idempotent:
        state["notification_status"] = "delivery_unknown"
        return
    if item["next_attempt_at"] is not None and now < item["next_attempt_at"]:
        state["notification_status"] = "retry_wait"
        return
    if item["payload"] is None:
        item["payload"] = {
            "event": "headroom.health_failure",
            "status": "unhealthy",
            "incident_id": state["incident_id"],
            "failure_since": state["failure_since"],
            "observed_at": now,
        }
    item.update(
        delivery_state="sending",
        attempts=item["attempts"] + 1,
        last_attempt_at=now,
        last_http_status=None,
        last_error_code=None,
    )
    item["next_attempt_at"] = (
        now + RETRY_SECONDS[item["attempts"] - 1] if item["attempts"] < MAX_ATTEMPTS else None
    )
    state["notification_status"] = "sending"
    _write_state(path, state)  # A crash after this point is uncertain, never silently replayed.
    item.update(send_webhook(config, item["payload"], transport=transport))
    state["notification_sent"] = item["delivery_state"] == "accepted"
    state["notification_status"] = item["delivery_state"]
    if item["delivery_state"] in {"accepted", "rejected"}:
        item["next_attempt_at"] = None
