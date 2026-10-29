"""Host preparation writes share the bounded public artifact census."""

import time
from pathlib import Path

import pytest
from test_api import settings as isolated_settings
from test_public_access import public_settings

from headroom.api.app import Submission, _prepare_submission
from headroom.lab import storage_budget


@pytest.fixture
def settings(tmp_path):
    return public_settings(isolated_settings.__wrapped__(tmp_path))


def test_prepare_counts_existing_uploads_in_shared_scope(settings, monkeypatch):
    old = settings.data_root / "uploads" / "old" / "train.py"
    old.parent.mkdir(parents=True)
    old.write_text("historical upload")
    settings.run_root.mkdir(parents=True)
    observed = []
    original = storage_budget.stored_bytes

    def census(root):
        assert old.is_relative_to(root)
        assert settings.run_root.is_relative_to(root)
        observed.append(root)
        return original(root)

    monkeypatch.setattr(storage_budget, "stored_bytes", census)
    request = _prepare_submission(
        settings,
        Submission(script_text="print(1)"),
        "print(1)",
        "a" * 32,
        deadline=time.monotonic() + 10,
    )
    assert len(observed) == 1
    assert Path(request.script).read_text() == "print(1)"
    assert old.read_text() == "historical upload"


def test_prepare_storage_capacity_fails_before_writing(settings, monkeypatch):
    monkeypatch.setattr(
        storage_budget, "stored_bytes", lambda root: storage_budget.MAX_STORAGE_BYTES
    )
    with pytest.raises(ValueError, match="LAB_STORAGE_CAPACITY"):
        _prepare_submission(
            settings,
            Submission(script_text="print(1)"),
            "print(1)",
            "b" * 32,
            deadline=time.monotonic() + 10,
        )
    assert not (settings.data_root / "uploads").exists()


def test_prepare_rejects_upload_root_outside_bounded_scope(settings):
    settings.run_root = settings.data_root.parent / "separate-scope" / "jobs"
    with pytest.raises(ValueError, match="must share"):
        _prepare_submission(
            settings,
            Submission(script_text="print(1)"),
            "print(1)",
            "c" * 32,
            deadline=time.monotonic() + 10,
        )
    assert not (settings.data_root / "uploads").exists()
