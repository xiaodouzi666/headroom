"""Product defaults are tested with temporary stores and a fake worker only."""

import hashlib
import json
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from headroom.api.app import ApiSettings, Submission, _catalog, _example_defaults, create_app
from headroom.api.example_presets import EXAMPLE_PRESETS
from headroom.lab.runner import PROJECT_ROOT

OLD = "s2_fp32_adamw_1b"
CAPACITY = "s2_capacity_v2"


@pytest.fixture
def settings(tmp_path):
    project = tmp_path / "project"
    scenarios = project / "scenarios"
    scenarios.mkdir(parents=True)
    index = (PROJECT_ROOT / "scenarios/INDEX.yaml").read_bytes()
    (scenarios / "INDEX.yaml").write_bytes(index)
    scripts = [row["script"] for row in json.loads(index)["scenarios"]]
    scripts.append(f"scenarios/{CAPACITY}/train.py")
    for script in scripts:
        destination = project / script
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((PROJECT_ROOT / script).read_bytes())
    return ApiSettings(
        project_root=project,
        data_root=tmp_path / "api",
        db_path=tmp_path / "store.db",
        run_root=tmp_path / "jobs",
        web_dist=tmp_path / "dist",
        event_poll_seconds=0.01,
    )


def test_catalog_preserves_legacy_ids_and_exposes_only_approved_capacity(settings):
    catalog = _catalog(settings)
    legacy = json.loads((settings.project_root / "scenarios/INDEX.yaml").read_text())
    assert list(catalog) == [row["id"] for row in legacy["scenarios"]] + [CAPACITY]
    assert "s2_optimizer_classification_v2" not in catalog
    for name, expected in EXAMPLE_PRESETS.items():
        row = catalog[name]
        assert row["source_sha256"] == expected["source_sha256"]
        assert hashlib.sha256(row["script_text"].encode()).hexdigest() == row["source_sha256"]
        assert row["recommended"] == expected["recommended"]
        assert row["baseline_note"]
    assert catalog[OLD]["recommended"] == {"target": "reclaim", "allocator_conf": None}
    assert catalog[CAPACITY]["recommended"] == {
        "target": "fit:22GB",
        "allocator_conf": "expandable_segments:True",
    }


@pytest.mark.parametrize("name", [OLD, CAPACITY])
def test_changed_source_cannot_keep_a_calibrated_preset(settings, name):
    path = settings.project_root / "scenarios" / name / "train.py"
    path.write_text(path.read_text() + "\n# drift\n")
    assert name not in _catalog(settings)


def test_missing_capacity_source_keeps_legacy_catalog(settings):
    (settings.project_root / f"scenarios/{CAPACITY}/train.py").unlink()
    assert len(_catalog(settings)) == 8
    assert OLD in _catalog(settings)


@pytest.mark.parametrize(
    "extra,target,allocator",
    [
        ({}, "fit:22GB", "expandable_segments:True"),
        ({"target": "fix-oom"}, "fix-oom", "expandable_segments:True"),
        ({"target": "fit:20GB"}, "fit:20GB", "expandable_segments:True"),
        ({"allocator_conf": None}, "fit:22GB", None),
        ({"allocator_conf": "max_split_size_mb:128"}, "fit:22GB", "max_split_size_mb:128"),
        ({"target": "reclaim", "allocator_conf": None}, "reclaim", None),
    ],
)
def test_api_defaults_and_explicit_overrides_reach_same_request_and_store(
    settings, extra, target, allocator
):
    captured = []
    called = threading.Event()

    def worker(request, *, store, run_root, run_id):
        captured.append(request)
        called.set()
        return {"status": "completed", "target_met": False}

    app = create_app(settings, worker=worker)
    with TestClient(app) as client:
        accepted = client.post("/api/runs", json={"example_id": CAPACITY, **extra})
        assert accepted.status_code == 202, accepted.text
        assert called.wait(2)
        request = captured[0]
        row = app.state.store.get_run(accepted.json()["run_id"])
        assert request.target == row["target"] == target
        assert request.allocator_conf == row["allocator_conf"] == allocator
        assert not request.policy.allow_numerics_change
        assert request.numerical_reference.strategy == "legacy_small_batch"
        assert Path(request.script).read_text() == _catalog(settings)[CAPACITY]["script_text"]


def test_defaults_do_not_mutate_request_or_accept_unapproved_fields(settings):
    submission = Submission(example_id=OLD)
    example = _catalog(settings)[OLD]
    example["recommended"]["policy"] = {"allow_numerics_change": True}
    resolved = _example_defaults(submission, example)
    assert resolved.target == "reclaim"
    assert submission.target == "fix-oom"
    assert not resolved.policy.allow_numerics_change
    assert resolved.allocator_conf is None


def test_invalid_preset_cannot_bypass_validation():
    with pytest.raises(ValueError):
        _example_defaults(
            Submission(example_id=CAPACITY),
            {"recommended": {"target": "fit:22GB", "allocator_conf": "unknown_allocator:true"}},
        )
    with pytest.raises(ValueError):
        _example_defaults(Submission(example_id=CAPACITY), {"recommended": {"target": "made-up"}})


def test_upload_keeps_ordinary_defaults_without_example_environment(settings):
    captured = []
    called = threading.Event()

    def worker(request, **kwargs):
        captured.append(request)
        called.set()
        return {"status": "completed", "target_met": False}

    with TestClient(create_app(settings, worker=worker)) as client:
        response = client.post("/api/runs", json={"script_text": "print('offline')"})
        assert response.status_code == 202
        assert called.wait(2)
        assert captured[0].target == "fix-oom"
        assert captured[0].allocator_conf is None
