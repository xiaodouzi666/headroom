"""Public demo boundaries, tested with offline workers only."""

import secrets
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from test_api import completed_worker, wait_done
from test_api import settings as isolated_settings

from headroom.api.app import ApiSettings, create_app


@pytest.fixture
def settings(tmp_path):
    return isolated_settings.__wrapped__(tmp_path)


HEADERS = {
    "Tailscale-Funnel-Request": "?1",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-Host": "demo.example",
    "X-Forwarded-For": "203.0.113.7",
}
EXAMPLE = {"example_id": "s3_eval_no_grad_missing"}


def public_settings(settings, **kwargs):
    return replace(settings, public_host="demo.example", trust_tailscale_funnel=True, **kwargs)


def public_client(app, peer="127.0.0.1"):
    return TestClient(app, base_url="https://demo.example", client=(peer, 50000))


def test_public_example_has_fixed_allowance_deadline_and_persistent_ip_limit(settings):
    observed = []

    def worker(request, **kwargs):
        observed.append(request)
        return completed_worker(request, **kwargs)

    configured = public_settings(settings)
    app = create_app(configured, worker=worker)
    with public_client(app) as client:
        response = client.post("/api/runs", json={**EXAMPLE, "budget": "5"}, headers=HEADERS)
        assert response.status_code == 202, response.text
        run = wait_done(client, response.json()["run_id"])
        assert Decimal(observed[0].budget_usd) == Decimal("0.30")
        assert run["api_execution_limit_seconds"] <= 480
        assert app.state.queue.deadline == 480
        assert client.get("/api/config").json()["limits"] == {
            "runs_per_ip_per_hour": 1,
            "max_waiting_runs": 2,
            "deadline_seconds": 480,
        }
        # New cookies cannot evade the persisted IP quota.
        client.cookies.clear()
        assert client.post("/api/runs", json=EXAMPLE, headers=HEADERS).status_code == 429
    with public_client(create_app(configured, worker=worker)) as client:
        assert client.post("/api/runs", json=EXAMPLE, headers=HEADERS).status_code == 429
        other = {**HEADERS, "X-Forwarded-For": "203.0.113.8"}
        response = client.post("/api/runs", json=EXAMPLE, headers=other)
        assert response.status_code == 202
        wait_done(client, response.json()["run_id"])


def test_own_script_needs_token_but_token_never_appears_in_public_config(settings):
    key = secrets.token_urlsafe(32)
    configured = public_settings(settings, judge_token=key)
    with public_client(create_app(configured, worker=completed_worker)) as client:
        payload = {"script_text": "print('offline test')"}
        assert client.post("/api/runs", json=payload, headers=HEADERS).status_code == 401
        bad = {**HEADERS, "Authorization": "Bearer incorrect"}
        assert client.post("/api/runs", json=payload, headers=bad).status_code == 401
        cfg = client.get("/api/config")
        assert cfg.json()["judge_scripts_available"] is True
        assert key not in cfg.text and key not in repr(configured)
        response = client.post(
            "/api/runs", json=payload, headers={**HEADERS, "Authorization": "Bearer " + key}
        )
        assert response.status_code == 202, response.text
        wait_done(client, response.json()["run_id"])


def test_no_configured_judge_token_never_accepts_script_or_repo(settings):
    configured = public_settings(settings)
    with public_client(create_app(configured, worker=completed_worker)) as client:
        assert client.get("/api/config").json()["judge_scripts_available"] is False
        assert (
            client.post("/api/runs", json={"script_text": "pass"}, headers=HEADERS).status_code
            == 401
        )
        assert (
            client.post(
                "/api/runs",
                json={
                    "repo": "https://github.com/example/repo",
                    "ref": "a" * 40,
                    "cmd": "python x.py",
                },
                headers=HEADERS,
            ).status_code
            == 403
        )
        assert client.get("/api/runs").json()["runs"] == []


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {**HEADERS, "Tailscale-Funnel-Request": "true"},
        {**HEADERS, "X-Forwarded-Proto": "http"},
        {**HEADERS, "X-Forwarded-Host": "wrong.example"},
        {**HEADERS, "X-Forwarded-For": "203.0.113.1, 203.0.113.2"},
        {**HEADERS, "X-Forwarded-For": "unknown"},
        list(HEADERS.items()) + [("X-Forwarded-For", "203.0.113.9")],
    ],
)
def test_untrusted_or_ambiguous_forwarding_never_creates_a_run(settings, headers):
    with public_client(create_app(public_settings(settings), worker=completed_worker)) as client:
        assert client.post("/api/runs", json=EXAMPLE, headers=headers).status_code == 400
        assert client.get("/api/runs").json()["runs"] == []


def test_forwarded_headers_from_nonloopback_peer_are_rejected(settings):
    app = create_app(public_settings(settings), worker=completed_worker)
    with public_client(app, peer="203.0.113.99") as client:
        assert client.post("/api/runs", json=EXAMPLE, headers=HEADERS).status_code == 403
        assert client.get("/api/runs").json()["runs"] == []


def test_disabled_submission_cannot_be_bypassed_with_judge_token(settings):
    key = secrets.token_urlsafe(32)
    configured = public_settings(settings, judge_token=key, run_submissions_enabled=False)
    with public_client(create_app(configured, worker=completed_worker)) as client:
        response = client.post(
            "/api/runs",
            json={"script_text": "pass"},
            headers={**HEADERS, "Authorization": "Bearer " + key},
        )
        assert response.status_code == 503
        assert client.get("/api/runs").json()["runs"] == []


def test_public_settings_validate_transport_and_cost_scope(tmp_path):
    with pytest.raises(ValueError, match="public host"):
        ApiSettings(project_root=tmp_path, trust_tailscale_funnel=True)
    with pytest.raises(ValueError, match="another tunnel"):
        ApiSettings(
            project_root=tmp_path,
            public_host="demo.example",
            trust_tailscale_funnel=True,
            trust_cloudflared=True,
        )
    with pytest.raises(ValueError, match="at most 0.30"):
        ApiSettings(project_root=tmp_path, public_run_budget=Decimal("0.31"))
