"""Public-origin startup contract, with no listener, GPU, provider or production state."""

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / "scripts/serve_public.py"
    spec = importlib.util.spec_from_file_location("headroom_public_launcher_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = tmp_path / "project"
    monkeypatch.setattr(module, "__file__", str(project / "scripts/serve_public.py"))
    for name in (
        "HEADROOM_PUBLIC_HOST",
        "HEADROOM_TRUST_CLOUDFLARED",
        "HEADROOM_RUN_SUBMISSIONS_ENABLED",
        "HEADROOM_RUNTIME_PROFILE",
        "HEADROOM_RUN_SUBMISSION_DISABLED_REASON",
    ):
        monkeypatch.delenv(name, raising=False)
    return module, project


def test_public_launcher_copies_only_curated_files_and_uses_isolated_state(launcher, monkeypatch):
    module, project = launcher
    monkeypatch.setenv("HEADROOM_PUBLIC_HOST", "headroom.example")
    monkeypatch.setenv("HEADROOM_VERIFIED_RUNS_ENABLED", "true")
    expected = {
        "public-evaluations.json": '{"version":1,"campaigns":[]}',
        "published-evaluations/r6-20261027.json": '{"fixture":"r6"}',
        "published-evaluations/r5-20261027.json": '{"fixture":"r5"}',
    }
    for relative, text in {**expected, "unpublished.json": "private evidence"}.items():
        path = project / "public-evidence" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    private = project / "runs/headroom.db"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"unchanged private state")
    observed = {}
    app = object()

    def create(settings):
        observed["settings"] = settings
        return app

    def run(application, **kwargs):
        observed["application"], observed["run"] = application, kwargs

    monkeypatch.setattr(module, "create_app", create)
    monkeypatch.setattr(module.uvicorn, "run", run)
    module.main()
    settings = observed["settings"]
    assert settings.project_root == project
    assert settings.data_root == project / "runs/public-api/submissions"
    assert settings.db_path == project / "runs/public-api/headroom.db"
    assert settings.run_root == project / "runs/public-api/jobs"
    assert settings.run_submissions_enabled is False
    assert settings.verified_runs_enabled is False
    assert settings.public_host == "headroom.example"
    assert settings.trust_cloudflared is False
    assert settings.trust_tailscale_funnel is True
    assert settings.deadline_seconds == 480
    assert observed["application"] is app
    assert observed["run"] == {"host": "127.0.0.1", "port": 8766, "proxy_headers": False}
    actual = {
        str(path.relative_to(settings.data_root)): path.read_text()
        for path in settings.data_root.rglob("*")
        if path.is_file()
    }
    assert actual == expected
    assert all(
        (settings.data_root / relative).stat().st_mode & 0o777 == 0o600 for relative in expected
    )
    assert private.read_bytes() == b"unchanged private state"
    assert not settings.db_path.exists() and not settings.run_root.exists()


@pytest.mark.parametrize(
    "environment, message",
    [
        ({}, "HEADROOM_PUBLIC_HOST"),
        (
            {"HEADROOM_PUBLIC_HOST": "demo.example", "HEADROOM_TRUST_CLOUDFLARED": "true"},
            "Cloudflare",
        ),
        (
            {"HEADROOM_PUBLIC_HOST": "demo.example", "HEADROOM_RUN_SUBMISSIONS_ENABLED": "true"},
            "read-only",
        ),
        (
            {"HEADROOM_PUBLIC_HOST": "demo.example", "HEADROOM_RUN_SUBMISSIONS_ENABLED": "FALSE"},
            "read-only",
        ),
    ],
)
def test_public_launcher_fails_closed_before_copy_or_listener(
    launcher, monkeypatch, environment, message
):
    module, project = launcher
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(module, "create_app", lambda *_: pytest.fail("must not construct app"))
    monkeypatch.setattr(module.uvicorn, "run", lambda *_, **__: pytest.fail("must not listen"))
    with pytest.raises(SystemExit, match=message):
        module.main()
    assert not project.exists()
