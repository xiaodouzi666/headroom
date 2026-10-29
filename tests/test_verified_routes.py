"""Curated read-only publication and session-bound diagnosis access."""

import json
import shutil
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from test_api import completed_worker, wait_done
from test_api import settings as isolated_settings

from headroom.api.app import create_app
from headroom.lab.runner import PROJECT_ROOT


@pytest.fixture
def configured(tmp_path):
    settings = isolated_settings.__wrapped__(tmp_path)
    public = settings.project_root / "public-evidence"
    public.mkdir()
    shutil.copyfile(
        PROJECT_ROOT / "public-evidence/verified-runs.json", public / "verified-runs.json"
    )
    shutil.copytree(PROJECT_ROOT / "public-evidence/verified-assets", public / "verified-assets")
    return settings


def test_gallery_is_disabled_by_default_and_query_cannot_enable_it(configured, monkeypatch):
    from headroom.api import verified_routes

    monkeypatch.setattr(verified_routes, "load_verified", lambda *_: pytest.fail("must not read"))
    with TestClient(create_app(configured, worker=completed_worker)) as client:
        assert client.get("/api/config").json()["verified_runs_enabled"] is False
        assert client.get("/api/verified?enabled=true").status_code == 404
        assert client.get("/api/verified/" + "a" * 32 + "/download/patch").status_code == 404


def test_enabled_curated_catalog_and_downloads_match_exact_source_bytes(configured):
    settings = replace(configured, verified_runs_enabled=True)
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        response = client.get("/api/verified")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["publication_status"] == "published"
        assert len(data["runs"]) == 6
        assert sum(run["outcome"] == "target_met" for run in data["runs"]) == 4
        assert sum(run["outcome"] == "not_solved" for run in data["runs"]) == 2
        for run in data["runs"]:
            for asset in run["downloads"].values():
                downloaded = client.get(asset["url"])
                assert downloaded.status_code == 200
                assert (
                    downloaded.content
                    == (settings.project_root / "public-evidence" / asset["path"]).read_bytes()
                )
                assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert client.get("/api/runs").json()["runs"] == []
        assert client.get("/api/verified/" + "a" * 32 + "/download/patch").status_code == 404
        run_id = data["runs"][0]["run_id"]
        assert client.get(f"/api/verified/{run_id}/download/env").status_code == 404


@pytest.mark.parametrize("change", ["content", "symlink"])
def test_changed_or_redirected_artifact_fails_closed(configured, change):
    root = configured.project_root / "public-evidence"
    doc = json.loads((root / "verified-runs.json").read_text())
    asset = root / next(iter(doc["runs"][0]["downloads"].values()))["path"]
    original = asset.read_bytes()
    if change == "content":
        asset.write_bytes(original + b"changed")
    else:
        private = configured.project_root / "not-public.txt"
        private.write_bytes(original)
        asset.unlink()
        asset.symlink_to(private)
    with TestClient(
        create_app(replace(configured, verified_runs_enabled=True), worker=completed_worker)
    ) as client:
        response = client.get("/api/verified")
        assert response.status_code == 503
        assert str(configured.project_root) not in response.text


def test_diagnosis_evidence_is_loaded_only_after_session_ownership(configured, monkeypatch):
    from headroom.api import app as api

    calls = []
    envelope = {"diagnosis": {"root_causes": []}, "diagnosis_binding": {"round": 1}, "stacks": []}

    def load(path, **kwargs):
        calls.append((path, kwargs))
        return envelope

    monkeypatch.setattr(api, "load_initial_diagnosis", load)
    app = create_app(configured, worker=completed_worker)
    with TestClient(app) as owner:
        response = owner.post("/api/runs", json={"script_text": "pass"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        result = wait_done(owner, run_id)
        assert result["diagnosis_evidence"] == envelope
        assert calls[-1][0] == configured.run_root / run_id
        assert calls[-1][1]["database"] == configured.db_path
        before = len(calls)
        outsider = TestClient(app)
        try:
            assert outsider.get(f"/api/runs/{run_id}").status_code == 404
        finally:
            outsider.close()
        assert len(calls) == before


def test_unsafe_run_directory_hides_evidence_without_losing_owned_metadata(configured, monkeypatch):
    from headroom.api import app as api

    with TestClient(create_app(configured, worker=completed_worker)) as client:
        response = client.post("/api/runs", json={"script_text": "pass"})
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        wait_done(client, run_id)
        directory = configured.run_root / run_id
        saved = directory.with_name(run_id + "-retained")
        directory.rename(saved)
        directory.symlink_to(saved, target_is_directory=True)
        monkeypatch.setattr(
            api, "load_initial_diagnosis", lambda *_a, **_kw: pytest.fail("must not read")
        )
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        assert response.json()["diagnosis_evidence"] is None
        assert response.json()["artifacts"] == {}


@pytest.fixture
def archived_catalog(configured):
    public = configured.project_root / "public-evidence"
    shutil.copyfile(
        PROJECT_ROOT / "public-evidence/verified-runs-history-v1.json",
        public / "verified-runs-history-v1.json",
    )
    old = json.loads((public / "verified-runs-history-v1.json").read_text())
    current = json.loads((public / "verified-runs.json").read_text())
    current_ids = {row["run_id"] for row in current["runs"]}
    historical = next(row for row in old["runs"] if row["run_id"] not in current_ids)
    return configured, historical


@pytest.mark.parametrize("kind", ["patch", "report_json", "report_markdown"])
@pytest.mark.parametrize("scenario", ["s3_eval_no_grad_missing", "s4_loss_accumulation_graph"])
def test_previously_published_download_remains_available_without_extra_cards(
    archived_catalog, kind, scenario
):
    configured, _ = archived_catalog
    history = json.loads(
        (configured.project_root / "public-evidence/verified-runs-history-v1.json").read_text()
    )
    historical = next(row for row in history["runs"] if row["scenario_id"] == scenario)
    settings = replace(configured, verified_runs_enabled=True)
    with TestClient(create_app(settings, worker=completed_worker)) as client:
        shown = client.get("/api/verified").json()["runs"]
        assert len(shown) == 6
        assert historical["run_id"] not in {row["run_id"] for row in shown}
        response = client.get(f"/api/verified/{historical['run_id']}/download/{kind}")
        assert response.status_code == 200
        assert (
            response.content
            == (
                settings.project_root / "public-evidence" / historical["downloads"][kind]["path"]
            ).read_bytes()
        )


def test_history_does_not_expose_unknown_or_unpublished_loose_files(archived_catalog):
    configured, _ = archived_catalog
    unpublished = "b" * 32
    path = configured.project_root / "public-evidence/verified-assets" / unpublished / "patch.diff"
    path.parent.mkdir()
    path.write_text("unpublished")
    with TestClient(
        create_app(replace(configured, verified_runs_enabled=True), worker=completed_worker)
    ) as client:
        for run_id in [unpublished, "a" * 32]:
            assert client.get(f"/api/verified/{run_id}/download/patch").status_code == 404


@pytest.mark.parametrize("change", ["content", "symlink"])
def test_changed_historical_artifact_is_refused_without_breaking_current_gallery(
    archived_catalog, change
):
    configured, historical = archived_catalog
    public = configured.project_root / "public-evidence"
    path = public / historical["downloads"]["patch"]["path"]
    if change == "content":
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        target = configured.project_root / "private-not-public.diff"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
    with TestClient(
        create_app(replace(configured, verified_runs_enabled=True), worker=completed_worker)
    ) as client:
        assert client.get("/api/verified").status_code == 200
        response = client.get(f"/api/verified/{historical['run_id']}/download/patch")
        assert response.status_code == 503
        assert str(configured.project_root) not in response.text
