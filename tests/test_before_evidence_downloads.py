"""Before-evidence downloads follow the server's finally-selected original pair."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import completed_worker, wait_done
from test_orchestrator import search_run

from headroom.api.app import ApiSettings, create_app
from headroom.api.security import artifact_relative
from headroom.orchestrator import RunCancelled

BACKUP_ID = "a" * 32


@pytest.fixture
def settings(tmp_path):
    return ApiSettings(
        project_root=tmp_path,
        data_root=tmp_path / "api",
        db_path=tmp_path / "api-store.db",
        run_root=tmp_path / "jobs",
        web_dist=tmp_path / "dist",
        event_poll_seconds=0.01,
    )


@pytest.mark.parametrize("interrupted", [False, True])
def test_real_orchestrator_finally_locators_drive_recovered_pair_downloads(
    tmp_path, monkeypatch, settings, interrupted
):
    originals = {}

    def recover(bundle, annotations, *, provenance):
        recovered = {**bundle, "annotation_delivery": {"status": "not_attached"}}
        for key in ("evidence_json", "evidence_md"):
            canonical = Path(bundle[key])
            originals[canonical.suffix] = canonical.read_bytes()
            backup = canonical.with_name(
                canonical.stem + ".unannotated-" + BACKUP_ID + canonical.suffix
            )
            backup.write_bytes(originals[canonical.suffix])
            canonical.write_text(
                '{"wrong":"partially published"}'
                if canonical.suffix == ".json"
                else "wrong partial Markdown"
            )
            recovered[key] = str(backup)
        if interrupted:
            # Matches the publisher's shared-bundle synchronization before rethrow.
            bundle.update(recovered)
            raise RunCancelled("Synthetic publication cancellation")
        return recovered

    monkeypatch.setattr("headroom.orchestrator.annotate_evidence_bundle", recover)
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    result, source_store, calls, _, _ = search_run(
        pipeline,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
        max_rounds=1,
    )
    try:
        row = source_store.get_run(result["run_id"])
        expected = {
            name: f"evidence/before/evidence.unannotated-{BACKUP_ID}.{suffix}"
            for name, suffix in (("evidence.json", "json"), ("evidence.md", "md"))
        }
        assert row["before_evidence_paths"] == expected
        report = json.loads(Path(result["report_json"]).read_text())
        assert report["run"]["before_evidence_paths"] == expected
        for name, key in (("evidence.json", "evidence_json"), ("evidence.md", "evidence_md")):
            assert (
                Path(report["evidence"]["before"][key]).relative_to(result["run_dir"]).as_posix()
                == expected[name]
            )
        if interrupted:
            assert result["status"] == "timeout" and calls == []
        else:
            assert result["target_met"]

        settings.run_root = Path(result["run_dir"]).parent
        app = create_app(settings, worker=completed_worker)
        with TestClient(app) as client:
            bootstrap = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
            wait_done(client, bootstrap)
            owner = app.state.store.get_run(bootstrap)["api_owner"]
            app.state.store.create_run(result["run_id"], {**row, "api_owner": owner})
            url = f"/api/runs/{result['run_id']}"
            links = client.get(url).json()["artifacts"]
            for name in expected:
                assert client.get(links[name]).content == originals[Path(name).suffix]
    finally:
        source_store.close()


@pytest.mark.parametrize("recorded", [False, True])
def test_legacy_and_recorded_canonical_downloads_unchanged(settings, recorded):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        wait_done(client, run_id)
        folder = settings.run_root / run_id / "evidence/before"
        folder.mkdir(parents=True)
        (folder / "evidence.json").write_text('{"canonical":true}')
        (folder / "evidence.md").write_text("canonical Markdown")
        if recorded:
            app.state.store.update_run(
                run_id,
                before_evidence_paths={
                    "evidence.json": "evidence/before/evidence.json",
                    "evidence.md": "evidence/before/evidence.md",
                },
            )
        url = f"/api/runs/{run_id}"
        assert client.get(url + "/evidence.json").json() == {"canonical": True}
        assert client.get(url + "/evidence.md").text == "canonical Markdown"


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        [],
        {"evidence.json": None},
        {"evidence.json": "/tmp/evidence.json"},
        {"evidence.json": "evidence/before/../before/evidence.json"},
        {"evidence.json": "evidence/before/evidence.md"},
        {"evidence.json": "evidence/before/evidence.unannotated-bad.json"},
        {"evidence.json": "evidence/after/evidence.json"},
    ],
)
def test_explicit_invalid_before_locator_never_falls_back(metadata):
    with pytest.raises(ValueError, match="before evidence"):
        artifact_relative({"before_evidence_paths": metadata}, "evidence.json")


@pytest.mark.parametrize("damage", ["missing", "leaf_link", "ancestor_link"])
def test_download_rejects_missing_or_linked_backup_without_canonical_fallback(
    settings, tmp_path, damage
):
    app = create_app(settings, worker=completed_worker)
    with TestClient(app) as client:
        run_id = client.post("/api/runs", json={"script_text": "pass"}).json()["run_id"]
        wait_done(client, run_id)
        folder = settings.run_root / run_id / "evidence/before"
        folder.mkdir(parents=True)
        (folder / "evidence.json").write_text('{"stale":"canonical"}')
        name = f"evidence.unannotated-{BACKUP_ID}.json"
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / name).write_text('{"outside":true}')
        if damage == "leaf_link":
            (folder / name).symlink_to(outside / name)
        elif damage == "ancestor_link":
            folder.rename(folder.with_name("original"))
            folder.symlink_to(outside, target_is_directory=True)
        app.state.store.update_run(
            run_id, before_evidence_paths={"evidence.json": f"evidence/before/{name}"}
        )
        url = f"/api/runs/{run_id}"
        assert client.get(url + "/evidence.json").status_code == 404
        assert client.get(url + "/evidence.md").status_code == 404
        assert "evidence.json" not in client.get(url).json()["artifacts"]
