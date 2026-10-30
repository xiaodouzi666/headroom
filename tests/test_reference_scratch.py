"""CPU/Unix-only storage isolation tests; no model, CUDA, Docker or large file."""

import concurrent.futures
import copy
import json
import os
import pickle
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_verify_offload_reference import (
    fake_tensor_torch as fake_tensor_torch,  # noqa: PLC0414
)
from test_verify_offload_reference import (
    measured,
    reference,
)

from headroom.lab import reference_scratch as scratch
from headroom.verify.offload import reference_proof
from headroom.verify.offload_disk import MAX_DISK_BYTES, RemoteDiskTensorStore


@pytest.fixture
def broker(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    store = scratch.ReferenceScratchBroker(tmp_path / "private", 128).start()
    try:
        yield store
    finally:
        store.close()


def client(broker):
    return scratch.ReferenceScratchClient(broker.socket_path, broker.max_bytes)


def raw_call(broker, header):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(broker.socket_path))
        scratch._send(connection, header)
        return scratch._receive_header(connection)


def test_protocol_round_trip_read_offsets_repeat_and_verified_delete(broker):
    remote = client(broker)
    identity = remote.create()
    assert len(identity) == 32 and "/" not in identity
    assert remote.append(identity, b"abcdef") == 6
    assert remote.finalize(identity) == 6
    assert remote.read(identity, 2, 2) == b"cd"
    assert remote.read(identity, 0, 128) == b"abcdef"
    assert remote.read(identity, 6, 128) == b""
    assert remote.delete(identity)
    assert broker.evidence()["live_reserved_bytes"] == 0
    assert broker.evidence()["peak_reserved_bytes"] == 6
    assert broker.evidence()["target_host_directory_access"] is False
    assert os.stat(broker.socket_path).st_mode & 0o777 == 0o600
    assert os.stat(broker.root).st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    "header",
    [
        {"op": "create", "path": "/tmp/outside"},
        {"op": "delete", "id": "../owner.json"},
        {"op": "read", "id": "a" * 32, "offset": 0, "size": 1},
        {"op": "exec", "value": "SECRET_UNTRUSTED"},
        {"op": "append", "id": "a" * 32, "size": scratch.MAX_CHUNK_BYTES + 1},
        {"op": "read", "id": "a" * 32, "offset": -1, "size": 1},
        {"op": "read", "id": "a" * 32, "offset": True, "size": 1},
        {"op": ["unhashable"]},
    ],
)
def test_arbitrary_paths_unknown_ids_bad_types_and_ops_are_fixed_rejections(broker, header):
    result = raw_call(broker, header)
    assert result["ok"] is False
    assert result["error"] == "request_rejected"
    assert "SECRET" not in json.dumps(result)
    assert broker.evidence()["live_reserved_bytes"] == 0


def test_oversized_header_is_rejected_before_receiving_arbitrary_payload(broker):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(broker.socket_path))
        connection.sendall(struct.pack("!I", scratch.MAX_HEADER_BYTES + 1))
        assert scratch._receive_header(connection)["ok"] is False


def test_finalize_prevents_more_writes_and_read_requires_finalize(broker):
    remote = client(broker)
    identity = remote.create()
    remote.append(identity, b"data")
    with pytest.raises(scratch.ReferenceScratchError):
        remote.read(identity, 0, 4)
    remote.finalize(identity)
    with pytest.raises(scratch.ReferenceScratchError):
        remote.append(identity, b"extra")
    with pytest.raises(scratch.ReferenceScratchError):
        remote.read(identity, 5, 1)
    assert remote.read(identity, 0, 4) == b"data"


def test_aggregate_quota_serializes_concurrent_append_admission(broker):
    remote = client(broker)
    identities = [remote.create(), remote.create()]

    def write(identity):
        try:
            remote.append(identity, b"x" * 80)
            return True
        except scratch.ReferenceScratchError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, identities))
    assert sum(outcomes) == 1
    assert broker.evidence()["live_reserved_bytes"] == 80
    assert sum(p.stat().st_size for p in (broker.root / "objects").iterdir()) == 80


def test_partial_write_holds_full_reservation_until_verified_unlink(broker, monkeypatch):
    identity = client(broker).create()
    original_write = os.write
    calls = []

    def partial_then_fail(fd, data):
        calls.append(1)
        if len(calls) == 1:
            return original_write(fd, data[:2])
        raise OSError("synthetic partial failure")

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", partial_then_fail)
        with pytest.raises(OSError):
            broker._dispatch({"op": "append", "id": identity, "size": 5}, b"12345")
    assert broker.evidence()["live_reserved_bytes"] == 5
    assert broker.objects[identity].size == 2 and broker.objects[identity].dirty
    with pytest.raises(scratch.ReferenceScratchError):
        broker._dispatch({"op": "finalize", "id": identity})
    broker._dispatch({"op": "delete", "id": identity})
    assert broker.evidence()["live_reserved_bytes"] == 0


def test_failed_unlink_does_not_refund_or_remove_object_identity(broker, monkeypatch):
    remote = client(broker)
    identity = remote.create()
    remote.append(identity, b"x" * 100)
    original_unlink = os.unlink

    def no_object_unlink(path, *args, **kwargs):
        if str(path).endswith(".bin"):
            raise OSError("synthetic unlink failure")
        return original_unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", no_object_unlink)
        with pytest.raises(scratch.ReferenceScratchError):
            remote.delete(identity)
        assert broker.evidence()["live_reserved_bytes"] == 100
        other = remote.create()
        with pytest.raises(scratch.ReferenceScratchError):
            remote.append(other, b"y" * 29)
    remote.delete(identity)
    assert broker.evidence()["live_reserved_bytes"] == 0


def test_symlink_or_replacement_cannot_expose_host_file_or_refund_quota(broker, tmp_path):
    remote = client(broker)
    identity = remote.create()
    remote.append(identity, b"owned")
    remote.finalize(identity)
    path = broker.root / "objects" / (identity + ".bin")
    original = tmp_path / "saved-owned-object"
    path.rename(original)
    outside = tmp_path / "private-secret"
    outside.write_text("HOST_SECRET_CANARY")
    path.symlink_to(outside)
    try:
        with pytest.raises(scratch.ReferenceScratchError):
            remote.read(identity, 0, 128)
        with pytest.raises(scratch.ReferenceScratchError):
            remote.delete(identity)
        assert broker.evidence()["live_reserved_bytes"] == 5
        assert outside.read_text() == "HOST_SECRET_CANARY"
    finally:
        path.unlink()
        original.rename(path)


def test_host_never_deserializes_target_bytes(broker, monkeypatch):
    monkeypatch.setattr(pickle, "loads", lambda *_: pytest.fail("host unpickle forbidden"))
    remote = client(broker)
    identity = remote.create()
    hostile = b"cos\nsystem\n(S'not executed'\ntR."
    remote.append(identity, hostile)
    remote.finalize(identity)
    assert remote.read(identity, 0, len(hostile)) == hostile


def test_wrong_peer_uid_and_capacity_mismatch_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(
        tmp_path / "wrong-peer", 128, peer_uid=os.getuid() + 1
    ).start()
    try:
        with pytest.raises((scratch.ReferenceScratchError, OSError)):
            client(broker).create()
    finally:
        assert broker.close()["cleanup_verified"]
    broker = scratch.ReferenceScratchBroker(tmp_path / "wrong-cap", 128).start()
    try:
        with pytest.raises(scratch.ReferenceScratchError):
            scratch.ReferenceScratchClient(broker.socket_path, 127).create()
    finally:
        assert broker.close()["cleanup_verified"]


def test_live_object_limit_and_no_oversized_or_invalid_constructor(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(tmp_path / "one", 8, max_objects=1).start()
    try:
        remote = client(broker)
        identity = remote.create()
        with pytest.raises(scratch.ReferenceScratchError):
            remote.create()
        remote.delete(identity)
        assert remote.create()
    finally:
        assert broker.close()["cleanup_verified"]
    for value in (0, -1, True, scratch.MAX_BYTES + 1):
        with pytest.raises(scratch.ReferenceScratchError):
            scratch.ReferenceScratchBroker(tmp_path / "invalid", value)


def test_host_reserve_is_checked_before_admission_and_again_before_append(tmp_path, monkeypatch):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    with pytest.raises(scratch.ReferenceScratchError, match="reserve"):
        scratch.ReferenceScratchBroker(tmp_path / "insufficient", 128)
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(tmp_path / "enough", 128).start()
    try:
        remote = client(broker)
        identity = remote.create()
        monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
        with pytest.raises(scratch.ReferenceScratchError):
            remote.append(identity, b"one")
        assert broker.evidence()["live_reserved_bytes"] == 0
    finally:
        assert broker.close()["cleanup_verified"]


def test_close_terminates_stalled_bounded_connections_and_cleans_objects(broker):
    remote = client(broker)
    identity = remote.create()
    remote.append(identity, b"retained")
    stalled = []
    for _ in range(scratch.MAX_CONCURRENCY):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.connect(str(broker.socket_path))
        stalled.append(connection)
    end = time.monotonic() + 1
    while len(broker._connections) < scratch.MAX_CONCURRENCY and time.monotonic() < end:
        time.sleep(0.01)
    started = time.monotonic()
    result = broker.close()
    for connection in stalled:
        connection.close()
    assert time.monotonic() - started < 3
    assert result["cleanup_verified"] and result["live_reserved_bytes"] == 0
    assert not Path(result["socket_path"]).exists()
    assert not list((broker.root / "objects").iterdir())


def test_supervisor_refuses_alive_owner_and_unexpected_file_without_deleting(broker):
    receipt = scratch.cleanup_owned_scratch(broker.root, expected_nonce=broker.nonce)
    assert not receipt["cleanup_verified"]
    assert (broker.root / "owner.json").exists()
    receipt = scratch.cleanup_owned_scratch(broker.root, expected_nonce="f" * 32)
    assert not receipt["cleanup_verified"]


def test_remote_tensor_round_trip_repeated_unpack_and_serialization_cap(
    tmp_path, monkeypatch, fake_tensor_torch
):
    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(tmp_path / "tensor", 1024).start()
    try:
        store = RemoteDiskTensorStore(broker.socket_path, 1024, 1024)
        packed = store.pack(fake_tensor_torch())
        assert packed.size == 12 and store.peak_bytes == 12
        for _ in range(2):
            restored = store.unpack(packed)
            assert restored.raw == b"12345678" and restored.device == "cuda"
        assert broker.evidence()["live_objects"] == 1
        assert store.close()["verified"]
        assert store.evidence()["host_cleanup_proven"] is False
        assert broker.evidence()["live_reserved_bytes"] == 0
    finally:
        assert broker.close()["cleanup_verified"]
    broker = scratch.ReferenceScratchBroker(tmp_path / "tensor-cap", 11).start()
    try:
        store = RemoteDiskTensorStore(broker.socket_path, 11, 1024)
        with pytest.raises(scratch.ReferenceScratchError):
            store.pack(fake_tensor_torch())
        assert store.failure and broker.evidence()["peak_reserved_bytes"] <= 11
        store.close()
    finally:
        assert broker.close()["cleanup_verified"]


def remote_reference():
    ref = reference()
    ref["reference_offload"].update(
        backend="disk",
        max_disk_bytes=MAX_DISK_BYTES,
        peak_saved_bytes=0,
        disk={
            "storage_backend": "host_broker",
            "max_disk_bytes": MAX_DISK_BYTES,
            "peak_disk_bytes": 12,
            "live_disk_bytes": 0,
            "cleanup_verified": True,
            "failure": None,
            "peak_staging_tensor_bytes": 8,
            "disk_tensors_created": 1,
            "disk_tensors_unpacked": 2,
        },
    )
    ref["reference_spill_cleanup"] = {"verified": True}
    ref["reference_scratch"] = {
        "schema": scratch.SCHEMA,
        "nonce": "a" * 32,
        "max_bytes": MAX_DISK_BYTES,
        "request_verified": True,
        "cleanup_verified": True,
        "live_reserved_bytes": 0,
        "live_objects": 0,
        "peak_reserved_bytes": 12,
        "target_host_directory_access": False,
    }
    return ref


def test_target_cleanup_claim_alone_never_proves_host_service_quota():
    ref = remote_reference()
    assert reference_proof(ref, measured(), baseline=measured("oom"))["valid"]
    for mutation in (
        lambda r: r.pop("reference_scratch"),
        lambda r: r["reference_scratch"].update(cleanup_verified=False),
        lambda r: r["reference_scratch"].update(request_verified=False),
        lambda r: r["reference_scratch"].update(max_bytes=MAX_DISK_BYTES + 1),
        lambda r: r["reference_scratch"].update(live_reserved_bytes=1),
        lambda r: r["reference_scratch"].update(live_objects=1),
        lambda r: r["reference_scratch"].update(peak_reserved_bytes=MAX_DISK_BYTES + 1),
        lambda r: r["reference_scratch"].update(peak_reserved_bytes=11),
        lambda r: r["reference_scratch"].update(target_host_directory_access=True),
        lambda r: r.update(reference_scratch=["invalid"]),
    ):
        value = copy.deepcopy(ref)
        mutation(value)
        assert not reference_proof(value, measured(), baseline=measured("oom"))["valid"]


def test_cli_crash_recovery_only_removes_owned_bytes_after_process_exit(tmp_path):
    with tempfile.TemporaryDirectory(prefix="hr-rpc-test-") as endpoint:
        root, socket_path = tmp_path / "cli", Path(endpoint) / "rpc.sock"
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "headroom.lab.reference_scratch",
                "--root",
                str(root),
                "--socket",
                str(socket_path),
                "--max-bytes",
                "128",
                "--max-seconds",
                "30",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            end = time.monotonic() + 5
            while not socket_path.exists() and process.poll() is None and time.monotonic() < end:
                time.sleep(0.02)
            assert socket_path.exists()
            remote = scratch.ReferenceScratchClient(socket_path, 128)
            identity = remote.create()
            remote.append(identity, b"crash-retained-bytes")
            owner = json.loads((root / "owner.json").read_text())
            assert not scratch.cleanup_owned_scratch(root, expected_nonce=owner["nonce"])[
                "cleanup_verified"
            ]
            process.send_signal(signal.SIGKILL)
            process.wait(timeout=5)
            receipt = scratch.cleanup_owned_scratch(root, expected_nonce=owner["nonce"])
            assert receipt["cleanup_verified"] and receipt["live_reserved_bytes"] == 0
            assert not list((root / "objects").iterdir())
            assert not socket_path.exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stderr.close()


def test_real_cpu_torch_serialization_uses_bounded_seekable_client(tmp_path, monkeypatch):
    import torch

    monkeypatch.setattr(scratch.shutil, "disk_usage", lambda _: SimpleNamespace(free=10**12))
    broker = scratch.ReferenceScratchBroker(tmp_path / "torch-cpu", 16384).start()
    try:
        store = RemoteDiskTensorStore(broker.socket_path, 16384, 16384)
        original = torch.arange(12, dtype=torch.float32).reshape(3, 4)
        packed = store.pack(original)
        assert torch.equal(store.unpack(packed), original)
        assert torch.equal(store.unpack(packed), original)
        assert store.close()["verified"]
    finally:
        assert broker.close()["cleanup_verified"]


def test_absolute_connection_deadline_cannot_be_extended_by_drip_bytes(broker, monkeypatch):
    monkeypatch.setattr(scratch, "CONNECTION_SECONDS", 0.08)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        connection.connect(str(broker.socket_path))
        connection.sendall(bytes([0]))
        time.sleep(0.05)
        connection.sendall(bytes([0]))
        time.sleep(0.05)
        assert scratch._receive_header(connection)["ok"] is False


def test_unknown_process_identity_does_not_allow_cleanup_of_a_live_owner(broker, monkeypatch):
    monkeypatch.setattr(scratch, "_process_identity", lambda _: None)
    receipt = scratch.cleanup_owned_scratch(broker.root, expected_nonce=broker.nonce)
    assert not receipt["cleanup_verified"]
    assert (broker.root / "owner.json").exists()
