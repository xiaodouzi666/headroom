"""Small isolated storage fixtures; no disk filling, containers, model or GPU."""

import os
import socket
import subprocess
from types import SimpleNamespace

import pytest

from headroom.lab import storage_budget as storage


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network/process/GPU forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(subprocess, "run", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))


def test_default_storage_limits_are_explicit():
    assert storage.MAX_STORAGE_BYTES == 16 * 1024**3
    assert storage.MIN_FREE_BYTES == 8 * 1024**3
    assert storage.LAB_RESERVATION_BYTES == 1024**3


def test_scope_includes_all_public_jobs_uploads_and_submissions(tmp_path):
    public = tmp_path / "public-api"
    lab = public / "jobs" / ("a" * 32) / "lab"
    lab.mkdir(parents=True)
    for relative, body in [
        ("jobs/job.json", b"123"),
        ("uploads/snapshot.json", b"12345"),
        ("submissions/source.py", b"1234567"),
    ]:
        path = public / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(body)
    assert storage.storage_scope(lab) == public
    assert storage.storage_scope(public / "jobs") == public
    assert storage.stored_bytes(public) == 15
    with storage.storage_admission(lab, aggregate=True) as receipt:
        assert receipt["scope"] == str(public)
        assert receipt["retained_bytes"] == 15 + len(b"headroom.public-storage.v1\n")


def test_general_cli_scope_covers_sibling_runs(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    assert storage.storage_scope(root / ("b" * 32) / "lab") == root
    assert storage.storage_scope(root) == root


@pytest.mark.parametrize("used_delta,accepted", [(0, True), (1, False)])
def test_cumulative_limit_includes_full_export_reservation(
    tmp_path, monkeypatch, used_delta, accepted
):
    used = storage.MAX_STORAGE_BYTES - storage.LAB_RESERVATION_BYTES + used_delta
    monkeypatch.setattr(storage, "stored_bytes", lambda _: used)
    if accepted:
        with storage.storage_admission(tmp_path, aggregate=True) as receipt:
            assert (
                receipt["retained_bytes"] + receipt["reserved_bytes"]
                == receipt["storage_limit_bytes"]
            )
    else:
        with (
            pytest.raises(ValueError, match="STORAGE_CAPACITY"),
            storage.storage_admission(tmp_path, aggregate=True),
        ):
            pytest.fail("must refuse before writes")


@pytest.mark.parametrize("free_delta,accepted", [(0, True), (-1, False)])
def test_free_floor_remains_after_reservation(tmp_path, monkeypatch, free_delta, accepted):
    free = storage.MIN_FREE_BYTES + storage.LAB_RESERVATION_BYTES + free_delta
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=free))
    if accepted:
        with storage.storage_admission(tmp_path) as receipt:
            assert free - receipt["reserved_bytes"] == receipt["minimum_free_bytes"]
    else:
        with pytest.raises(ValueError, match="FREE_SPACE"), storage.storage_admission(tmp_path):
            pytest.fail("must refuse before writes")


@pytest.mark.parametrize("kind", ["file_link", "directory_link", "fifo"])
def test_retained_symlinks_and_special_files_are_rejected(tmp_path, kind):
    root = tmp_path / "retained"
    root.mkdir()
    if kind == "file_link":
        (tmp_path / "outside").write_bytes(b"secret-never-read")
        (root / "entry").symlink_to(tmp_path / "outside")
    elif kind == "directory_link":
        (root / "entry").symlink_to(tmp_path, target_is_directory=True)
    else:
        os.mkfifo(root / "entry")
    with (
        pytest.raises(ValueError, match="STORAGE_UNSAFE"),
        storage.storage_admission(root, aggregate=True),
    ):
        pytest.fail("unsafe tree must not be used")


def test_storage_lock_refuses_symlink_and_does_not_modify_target(tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"do not touch")
    root = tmp_path / "root"
    root.mkdir()
    (root / ".headroom-storage.lock").symlink_to(outside)
    with pytest.raises(OSError), storage.storage_admission(root):
        pytest.fail("symlink lock accepted")
    assert outside.read_bytes() == b"do not touch"


def test_second_lock_is_rejected_until_first_context_exits(tmp_path):
    with (
        storage.storage_admission(tmp_path),
        pytest.raises(ValueError, match="STORAGE_BUSY"),
        storage.storage_admission(tmp_path),
    ):
        pytest.fail("simultaneous host export admitted")
    with storage.storage_admission(tmp_path):
        pass


def test_failed_admission_releases_lock_and_preserves_old_files(tmp_path, monkeypatch):
    old = tmp_path / "result.json"
    old.write_bytes(b"retained evidence")
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="FREE_SPACE"), storage.storage_admission(tmp_path):
        pass
    assert old.read_bytes() == b"retained evidence"
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=100 * 1024**3))
    with storage.storage_admission(tmp_path):
        pass


@pytest.mark.parametrize("kind", ["files", "directories"])
def test_census_is_bounded_even_for_zero_byte_entries(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(storage, "MAX_CENSUS_FILES", 4)
    for index in range(5):
        path = tmp_path / str(index)
        path.mkdir() if kind == "directories" else path.touch()
    with pytest.raises(ValueError, match="STORAGE_CAPACITY"):
        storage.stored_bytes(tmp_path)


def test_logical_file_bytes_not_allocated_blocks_control_census(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "MAX_STORAGE_BYTES", 1024)
    with (tmp_path / "sparse").open("wb") as handle:
        handle.seek(1024)
        handle.write(b"x")
    with pytest.raises(ValueError, match="STORAGE_CAPACITY"):
        storage.stored_bytes(tmp_path)


def test_public_marker_preserves_aggregate_cap_on_later_default_call(tmp_path, monkeypatch):
    with storage.storage_admission(tmp_path, aggregate=True):
        pass
    monkeypatch.setattr(storage, "stored_bytes", lambda _: storage.MAX_STORAGE_BYTES)
    with pytest.raises(ValueError, match="STORAGE_CAPACITY"), storage.storage_admission(tmp_path):
        pytest.fail("omitting flag must not bypass established public quota")


def test_private_cli_does_not_reject_old_history_but_keeps_free_floor(tmp_path, monkeypatch):
    def forbidden_census(_):
        raise AssertionError("Private CLI history must not use new public aggregate cap")

    monkeypatch.setattr(storage, "stored_bytes", forbidden_census)
    with storage.storage_admission(tmp_path):
        pass
    monkeypatch.setattr(storage.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError, match="FREE_SPACE"), storage.storage_admission(tmp_path):
        pytest.fail("private CLI still reserves free space")


@pytest.mark.parametrize("kind", ["symlink", "fifo", "invalid"])
def test_marker_cannot_be_replaced_with_unsafe_or_invalid_entry(tmp_path, kind):
    marker = tmp_path / storage.PUBLIC_MARKER
    if kind == "symlink":
        marker.symlink_to(tmp_path / "outside")
    elif kind == "fifo":
        os.mkfifo(marker)
    else:
        marker.write_bytes(b"invalid")
    with pytest.raises((ValueError, OSError)), storage.storage_admission(tmp_path):
        pytest.fail("invalid marker must not disable public quota")


def test_canonical_public_root_keeps_cap_even_if_marker_is_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "PUBLIC_STORAGE_ROOT", tmp_path)
    with storage.storage_admission(tmp_path):
        pass
    (tmp_path / storage.PUBLIC_MARKER).unlink()
    monkeypatch.setattr(storage, "stored_bytes", lambda _: storage.MAX_STORAGE_BYTES)
    with pytest.raises(ValueError, match="STORAGE_CAPACITY"), storage.storage_admission(tmp_path):
        pytest.fail("canonical public root cannot disable quota by deleting marker")
