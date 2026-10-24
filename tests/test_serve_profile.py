"""Explicit startup profile routing without listeners, credentials, providers or GPU."""

import builtins
import io
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from headroom.api import app as api
from headroom.cli import app
from headroom.config import candidate_models


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("HEADROOM_RUNTIME_PROFILE", "HEADROOM_PUBLIC_HOST", "HEADROOM_TRUST_CLOUDFLARED"):
        monkeypatch.delenv(name, raising=False)

    def denied(*args, **kwargs):
        raise AssertionError("No external network, GPU or subprocess in startup profile tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    for module in (builtins, io):
        original = module.open

        def guarded(file, *args, _original=original, **kwargs):
            if isinstance(file, (str, bytes, Path)) and Path(os.fsdecode(file)).name.startswith(
                ".env"
            ):
                raise AssertionError("Startup must not read credential files")
            return _original(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)


def profile(path, *, enabled=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "live_enabled": enabled,
                "credit_confirmed": True,
                "available_credit_usd": "1",
                "authorized_total_usd": "1",
                "verified_at": "offline-fixture",
                "evidence": "offline-fixture, not provider verification",
                "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
                "evidence_token_budget": 1000,
                "models": {
                    role: {
                        "model_id": model.model_id,
                        "input_usd_per_million": "1",
                        "output_usd_per_million": "2",
                        "evidence": "offline fixture only",
                        "billing": {
                            "prompt_token_ceiling": 30000,
                            "max_prompt_utf8_bytes": 100000,
                            "max_completion_tokens": 8192,
                            "output_cap_field": "max_completion_tokens",
                            "output_cap_includes_reasoning": True,
                            "verified": True,
                            "evidence": "offline fixture only",
                        },
                    }
                    for role, model in candidate_models().items()
                },
            }
        )
    )
    return path


def test_settings_none_does_not_select_or_activate_a_profile(tmp_path):
    settings = api.ApiSettings(project_root=tmp_path)
    assert settings.runtime_profile is None
    assert not settings.runtime_configured
    assert not (tmp_path / ".cache").exists()


def test_settings_explicit_path_overrides_environment_without_reading_it(tmp_path, monkeypatch):
    monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", "missing-env-profile.json")
    assert api.ApiSettings(project_root=tmp_path).runtime_profile == "missing-env-profile.json"
    settings = api.ApiSettings(project_root=tmp_path, runtime_profile="chosen.json")
    assert settings.runtime_profile == "chosen.json"
    assert not settings.runtime_configured


@pytest.mark.parametrize("explicit", [False, True])
def test_cli_passes_profile_choice_without_starting_a_listener(tmp_path, monkeypatch, explicit):
    import uvicorn

    monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", "environment.json")
    captured = []
    sentinel = object()

    def factory(settings):
        captured.append(settings)
        return sentinel

    monkeypatch.setattr(api, "create_app", factory)
    calls = []
    monkeypatch.setattr(
        uvicorn, "run", lambda application, **kwargs: calls.append((application, kwargs))
    )
    args = ["serve", "--port", "8765"]
    if explicit:
        args += ["--runtime-profile", str(tmp_path / "explicit.json")]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert captured[0].runtime_profile == (
        str(tmp_path / "explicit.json") if explicit else "environment.json"
    )
    assert calls == [(sentinel, {"host": "127.0.0.1", "port": 8765, "proxy_headers": False})]
    assert not captured[0].runtime_configured


def test_module_main_uses_environment_path_and_keeps_loopback_proxy_boundary(tmp_path, monkeypatch):
    import uvicorn

    monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", "module.json")
    settings_type = api.ApiSettings
    monkeypatch.setattr(api, "ApiSettings", lambda: settings_type(project_root=tmp_path))
    calls = []
    monkeypatch.setattr(
        uvicorn, "run", lambda application, **kwargs: calls.append((application, kwargs))
    )
    api.main()
    application, kwargs = calls[0]
    try:
        assert application.state.settings.runtime_profile == "module.json"
        assert kwargs == {"host": "127.0.0.1", "port": 8000, "proxy_headers": False}
        assert not application.state.queue.thread.is_alive()
    finally:
        application.state.availability.close()
        application.state.store.close()


@pytest.mark.parametrize("source", ["explicit", "environment", "existing_default"])
def test_selected_profile_reaches_existing_health_validation(tmp_path, monkeypatch, source):
    selected = profile(
        tmp_path / ".cache/tokenfactory-runtime.json"
        if source == "existing_default"
        else tmp_path / "chosen.json"
    )
    if source == "environment":
        monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", str(selected))
    settings = api.ApiSettings(
        project_root=tmp_path, runtime_profile=str(selected) if source == "explicit" else None
    )
    original = selected.read_bytes()
    application = api.create_app(settings, worker=lambda **kwargs: None)
    with TestClient(application) as client:
        observed = client.get("/api/health").json()
        assert observed["token_factory"]["configured"] is True
        assert observed["token_factory"]["authentication_checked"] is False
        assert observed["token_factory"]["configuration_scope"] == "reviewed_runtime_profile"
        assert str(selected) not in json.dumps(observed)
        assert not settings.runtime_configured
    assert selected.read_bytes() == original


@pytest.mark.parametrize("kind", ["missing", "disabled", "malformed", "symlink"])
def test_explicit_profile_does_not_bypass_validation_or_fallback(tmp_path, monkeypatch, kind):
    profile(tmp_path / ".cache/tokenfactory-runtime.json")
    selected = tmp_path / "selected.json"
    if kind == "disabled":
        profile(selected, enabled=False)
    elif kind == "malformed":
        selected.write_text('{"private-marker":"must-not-echo"}')
    elif kind == "symlink":
        selected.symlink_to(tmp_path / ".cache/tokenfactory-runtime.json")
    monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", str(selected))
    application = api.create_app(
        api.ApiSettings(project_root=tmp_path), worker=lambda **kwargs: None
    )
    with TestClient(application) as client:
        observed = client.get("/api/health").json()
        assert observed["token_factory"]["configured"] is False
        assert observed["local_budget"]["reason"] == "runtime_profile_unavailable"
        assert "must-not-echo" not in json.dumps(observed)
        assert str(selected) not in json.dumps(observed)


@pytest.mark.parametrize("explicit", [False, True])
def test_startup_override_is_preserved_in_prepared_worker_request(tmp_path, monkeypatch, explicit):
    import time

    monkeypatch.setenv("HEADROOM_RUNTIME_PROFILE", "environment.json")
    settings = api.ApiSettings(
        project_root=tmp_path, runtime_profile="explicit.json" if explicit else None
    )
    request = api._prepare_submission(
        settings,
        api.Submission(script_text="print('offline')"),
        "print('offline')",
        "a" * 32,
        deadline=time.monotonic() + 5,
    )
    assert request.runtime_profile == ("explicit.json" if explicit else "environment.json")
    assert request.max_steps == 20 and request.max_seconds == 180
    assert request.budget_usd == "0.6"
