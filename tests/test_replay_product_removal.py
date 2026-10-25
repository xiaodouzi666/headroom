"""Replay product removal keeps ordinary owner-scoped run delivery."""

import pytest
import test_api as fixtures
from fastapi.testclient import TestClient
from test_api import (
    completed_worker,
    wait_done,
)
from typer.testing import CliRunner

from headroom import cli
from headroom.api.app import create_app
from headroom.execution import replay_argv


@pytest.fixture
def api_settings(tmp_path):
    return fixtures.settings.__wrapped__(tmp_path)


@pytest.mark.parametrize("legacy_public_flag", [False, True])
def test_owner_run_sse_and_downloads_survive_without_public_access(
    api_settings, legacy_public_flag
):
    app = create_app(api_settings, worker=completed_worker)
    with TestClient(app) as owner:
        run_id = owner.post("/api/runs", json={"script_text": "print('offline')"}).json()["run_id"]
        wait_done(owner, run_id)
        app.state.store.update_run(run_id, public_replay=legacy_public_flag)
        assert owner.get(f"/api/runs/{run_id}").status_code == 200
        events = owner.get(f"/api/runs/{run_id}/events").text
        assert "event: run.done" in events and "event: stream.end" in events
        for artifact in ("report.md", "report.json", "patch.diff"):
            assert owner.get(f"/api/runs/{run_id}/{artifact}").status_code == 200
        assert any(row["run_id"] == run_id for row in owner.get("/api/runs").json()["runs"])

        other = TestClient(app)
        try:
            other_run = other.post("/api/runs", json={"script_text": "print('other')"}).json()[
                "run_id"
            ]
            wait_done(other, other_run)
            for suffix in ("", "/events", "/report.md", "/report.json", "/patch.diff"):
                assert other.get(f"/api/runs/{run_id}{suffix}").status_code == 404
            assert all(row["run_id"] != run_id for row in other.get("/api/runs").json()["runs"])
        finally:
            other.close()
        fresh = TestClient(app)
        try:
            for suffix in ("", "/events", "/report.md", "/report.json", "/patch.diff"):
                assert fresh.get(f"/api/runs/{run_id}{suffix}").status_code == 404
        finally:
            fresh.close()
        assert owner.get(f"/api/runs/{run_id}/report.md").text == "# Offline fixture\n"
        assert owner.get("/api/replays").status_code == 404
        assert "/api/replays" not in owner.get("/openapi.json").json()["paths"]


def test_removed_cli_replay_does_not_open_store(monkeypatch):
    monkeypatch.setattr(cli, "_store", lambda: pytest.fail("Removed command must not open Store"))
    result = CliRunner().invoke(cli.app, ["replay", "a" * 32])
    assert result.exit_code == 2
    assert "No such command" in result.output
    assert "replay" not in CliRunner().invoke(cli.app, ["--help"]).output.lower()


def test_target_argv_replay_remains_a_runtime_mechanism():
    assert replay_argv(["python", "-u", "train.py", "--batch", "8"], ["--batch", "2"]) == [
        "python",
        "-u",
        "train.py",
        "--batch",
        "2",
    ]
