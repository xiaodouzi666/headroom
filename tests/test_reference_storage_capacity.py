"""CPU-only regression checks for the reference/artifact capacity conflict.

These preserve current fail-closed boundaries; they do not certify a new disk
scratch backend or a successful original-workload numerical reference.
"""

import io
from types import SimpleNamespace

import pytest

from headroom.lab import artifact_volume
from headroom.verify import offload, offload_disk


def fake_torch(monkeypatch):
    import sys

    graph = SimpleNamespace(
        save_on_cpu=lambda **kw: SimpleNamespace(pack_hook=lambda x: x, unpack_hook=lambda x: x),
        saved_tensors_hooks=lambda *args: SimpleNamespace(),
    )
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(__version__="2.5.1", autograd=SimpleNamespace(graph=graph)),
    )


def test_zero_disk_spill_never_requests_free_disk_or_constructs_disk_store(tmp_path, monkeypatch):
    fake_torch(monkeypatch)
    script = tmp_path / "entry.py"
    script.write_text("pass\n")
    monkeypatch.setattr(offload, "source_contract", lambda _: {"supported": True})
    monkeypatch.setattr(
        offload_disk.shutil,
        "disk_usage",
        lambda *_: pytest.fail("CPU-only offload must not inspect disk reserve"),
    )
    monkeypatch.setattr(
        offload,
        "DiskTensorStore",
        lambda *_: pytest.fail("zero spill must not allocate a disk store"),
    )
    context = offload.SavedTensorOffload(script, [], tmp_path, 1024, 0)
    assert context.disk is None
    assert context.data["backend"] == "cpu"
    assert context.data["max_disk_bytes"] == 0


@pytest.mark.parametrize(
    "free",
    [0, 512 * 1024**2, offload_disk.MAX_DISK_BYTES + 1024**3 - 1],
)
def test_positive_spill_keeps_full_explicit_limit_plus_reserve_guard(tmp_path, monkeypatch, free):
    keep = tmp_path / "existing"
    keep.write_text("preserve existing data")
    monkeypatch.setattr(offload_disk.shutil, "disk_usage", lambda _: SimpleNamespace(free=free))
    monkeypatch.setattr(
        offload_disk.tempfile,
        "mkdtemp",
        lambda *args, **kwargs: pytest.fail("must reject before any scratch directory"),
    )
    with pytest.raises(RuntimeError, match="1 GiB reserve"):
        offload_disk.DiskTensorStore(tmp_path, offload_disk.MAX_DISK_BYTES, 1024)
    assert keep.read_text() == "preserve existing data"


def test_positive_spill_guard_accepts_exact_boundary_without_increasing_limit(
    tmp_path, monkeypatch
):
    explicit_limit = 16
    monkeypatch.setattr(
        offload_disk.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=explicit_limit + 1024**3),
    )
    store = offload_disk.DiskTensorStore(tmp_path, explicit_limit, 1024)
    assert store.limit == explicit_limit
    assert store.live_bytes == 0
    store.close()
    assert store.cleanup_verified


def test_serialized_writer_cannot_expand_the_explicit_aggregate_disk_budget():
    store = SimpleNamespace(limit=11, live_bytes=0, peak_bytes=0, files={"one": 0}, failure=None)
    output = io.BytesIO()
    writer = offload_disk._BudgetWriter(output, store, "one")
    assert writer.write(b"HEAD") == 4
    assert writer.write(b"1234567") == 7
    with pytest.raises(RuntimeError, match="disk byte budget"):
        writer.write(b"8")
    assert output.getvalue() == b"HEAD1234567"
    assert store.live_bytes == store.peak_bytes == store.limit == 11


def test_public_artifact_volume_limit_stays_512_mib_and_rejects_reference_sized_volume(tmp_path):
    metadata = {
        "schema": artifact_volume.SCHEMA,
        "target": "headroom-lab-" + "a" * 32,
        **artifact_volume.names("headroom-lab-" + "a" * 32),
        "image_id": "sha256:" + "b" * 64,
        "nonce": "c" * 32,
        "output_path": str(tmp_path),
        "max_bytes": artifact_volume.MAX_BYTES,
        "max_inodes": artifact_volume.MAX_INODES,
    }
    assert artifact_volume.MAX_BYTES == 512 * 1024**2
    artifact_volume._validate(metadata)
    metadata["max_bytes"] += 1
    with pytest.raises(artifact_volume.ArtifactStoreError, match="BYTE_LIMIT"):
        artifact_volume._validate(metadata)
    metadata["max_bytes"] = offload_disk.MAX_DISK_BYTES
    with pytest.raises(artifact_volume.ArtifactStoreError, match="BYTE_LIMIT"):
        artifact_volume._validate(metadata)
