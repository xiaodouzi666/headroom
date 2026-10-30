"""Owned, byte-bounded temporary disk storage for numerical reference tensors."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import weakref
from pathlib import Path

DISK_PROTOCOL = "headroom.reference_tensor_disk.v1"
SPILL_PREFIX = "headroom-reference-spill-"
MAX_DISK_BYTES = 64 * 1024**3


def validate_disk_limit(value):
    if type(value) is not int or not 0 <= value <= MAX_DISK_BYTES:
        raise ValueError("reference offload disk limit must be 0..64 GiB")
    return value


def cleanup_spill(output):
    """Only remove owned new-run scratch directories, never follow links."""
    output = Path(output)
    receipt = {"verified": True, "directories": [], "errors": []}
    if not output.exists():
        return receipt
    for directory in output.glob(SPILL_PREFIX + "*"):
        try:
            info = directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("spill directory is not an owned regular directory")
            entries = list(directory.iterdir())
            if entries:
                marker = directory / "owner.json"
                fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd, "rb") as handle:
                    info = os.fstat(handle.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
                        raise ValueError("invalid spill owner marker")
                    owner = json.load(handle)
                if owner != {"protocol": DISK_PROTOCOL, "directory": directory.name}:
                    raise ValueError("spill owner marker mismatch")
            for entry in entries:
                info = entry.lstat()
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_uid != os.getuid()
                    or not (
                        entry.name == "owner.json"
                        or re.fullmatch(r"tensor-[0-9]{8}\.pt", entry.name)
                    )
                ):
                    raise ValueError("unexpected entry in owned spill directory")
            for entry in entries:
                entry.unlink()
            directory.rmdir()
            receipt["directories"].append(directory.name)
        except (OSError, ValueError, TypeError) as error:
            receipt["verified"] = False
            receipt["errors"].append(str(error))
    return receipt


class DiskTensor:
    def __init__(self, path, device, dtype, shape):
        self.path, self.device, self.dtype, self.shape = path, device, dtype, shape


class _BudgetWriter:
    def __init__(self, handle, store, name):
        self.handle, self.store, self.name = handle, store, name

    def write(self, data):
        if self.store.live_bytes + len(data) > self.store.limit:
            self.store.failure = "saved_tensor_disk_budget_exceeded"
            raise RuntimeError("Original-workload reference disk byte budget exceeded")
        size = self.handle.write(data)
        self.store.files[self.name] += size
        self.store.live_bytes += size
        self.store.peak_bytes = max(self.store.peak_bytes, self.store.live_bytes)
        return size

    def flush(self):
        return self.handle.flush()


class DiskTensorStore:
    """A packed object retains its file across repeated unpack calls."""

    def __init__(self, output, limit, cpu_limit):
        self.limit = validate_disk_limit(limit)
        self.cpu_limit = cpu_limit
        if not self.limit:
            raise ValueError("Disk tensor store requires a positive byte budget")
        if shutil.disk_usage(output).free < self.limit + 1024**3:
            raise RuntimeError(
                "Insufficient free disk for the bounded reference plus 1 GiB reserve"
            )
        self.directory = Path(tempfile.mkdtemp(prefix=SPILL_PREFIX, dir=output))
        (self.directory / "owner.json").write_text(
            json.dumps(
                {
                    "protocol": DISK_PROTOCOL,
                    "directory": self.directory.name,
                }
            )
        )
        self.files = {}
        self.live_bytes = self.peak_bytes = self.created = self.unpacked = 0
        self.peak_staging_bytes = 0
        self.failure = None
        self.cleanup_verified = False

    def release(self, name):
        size = self.files.pop(name, None)
        if size is not None:
            try:
                (self.directory / name).unlink(missing_ok=True)
                self.live_bytes -= size
            except OSError:
                self.failure = "disk_tensor_release_failed"

    def pack(self, tensor):
        import torch

        size = tensor.numel() * tensor.element_size()
        if size > self.cpu_limit // 2:
            self.failure = "single_tensor_staging_budget_exceeded"
            raise RuntimeError("Reference tensor exceeds half the CPU staging budget")
        if shutil.disk_usage(self.directory).free < size + 1024**3:
            self.failure = "disk_free_space_reserve_exhausted"
            raise RuntimeError("Reference disk free-space reserve exhausted")
        self.created += 1
        name = f"tensor-{self.created:08d}.pt"
        path = self.directory / name
        self.files[name] = 0
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as handle:
                # Copies are synchronous and lossless; CPU tensors are not retained.
                cpu = tensor.detach().cpu()
                self.peak_staging_bytes = max(self.peak_staging_bytes, size)
                torch.save(cpu, _BudgetWriter(handle, self, name))
            packed = DiskTensor(path, tensor.device, tensor.dtype, tuple(tensor.shape))
            weakref.finalize(packed, self.release, name)
            return packed
        except BaseException:
            self.release(name)
            if self.failure is None:
                self.failure = "disk_tensor_save_failed"
            raise

    def unpack(self, packed):
        import torch

        fd = os.open(packed.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as handle:
            tensor = torch.load(handle, map_location="cpu", weights_only=True)
        if (
            not isinstance(tensor, torch.Tensor)
            or tensor.dtype != packed.dtype
            or tuple(tensor.shape) != packed.shape
        ):
            self.failure = "disk_tensor_metadata_mismatch"
            raise RuntimeError("Reference saved tensor dtype or shape mismatch")
        self.unpacked += 1
        return tensor.to(packed.device)

    def close(self):
        for name in tuple(self.files):
            self.release(name)
        receipt = cleanup_spill(self.directory.parent)
        self.cleanup_verified = receipt["verified"] and not self.directory.exists()
        if not self.cleanup_verified:
            self.failure = "disk_tensor_cleanup_failed"
        return receipt

    def evidence(self):
        return {
            "protocol": DISK_PROTOCOL,
            "max_disk_bytes": self.limit,
            "peak_disk_bytes": self.peak_bytes,
            "live_disk_bytes": self.live_bytes,
            "disk_tensors_created": self.created,
            "disk_tensors_unpacked": self.unpacked,
            "peak_staging_tensor_bytes": self.peak_staging_bytes,
            "cleanup_verified": self.cleanup_verified,
            "failure": self.failure,
            "storage": "exclusive temporary directory under disk-backed /out",
            "lifetime": "packed object lifetime; never delete on first unpack",
        }


class RemoteDiskTensor(DiskTensor):
    """Only a broker-owned opaque identity is retained in the target process."""

    def __init__(self, identity, size, device, dtype, shape):
        self.identity, self.size = identity, size
        self.device, self.dtype, self.shape = device, dtype, shape


class _RemoteWriter:
    def __init__(self, store, identity):
        self.store, self.identity = store, identity

    def write(self, data):
        count = self.store.client.append(self.identity, data)
        self.store.files[self.identity] += count
        self.store.live_bytes += count
        self.store.peak_bytes = max(self.store.peak_bytes, self.store.live_bytes)
        return count

    def flush(self):
        return None


class RemoteDiskTensorStore:
    """Lossless tensor bytes sent to a host-owned service, never a host mount."""

    def __init__(self, socket_path, limit, cpu_limit):
        from headroom.lab.reference_scratch import ReferenceScratchClient

        self.limit = validate_disk_limit(limit)
        if not self.limit:
            raise ValueError("Remote disk tensor store requires a positive byte budget")
        if type(cpu_limit) is not int or not 1 <= cpu_limit <= 16 * 1024**3:
            raise ValueError("Remote tensor CPU staging limit must be 1..16 GiB")
        self.cpu_limit = cpu_limit
        self.client = ReferenceScratchClient(socket_path, self.limit)
        self.files = {}
        self.live_bytes = self.peak_bytes = self.created = self.unpacked = 0
        self.peak_staging_bytes = 0
        self.failure = None
        self.cleanup_verified = False

    def release(self, identity):
        if identity not in self.files:
            return
        try:
            self.client.delete(identity)
        except (OSError, RuntimeError, ValueError):
            self.failure = "broker_tensor_release_failed"
            return
        self.live_bytes -= self.files.pop(identity)

    def pack(self, tensor):
        import torch

        size = tensor.numel() * tensor.element_size()
        if size > self.cpu_limit // 2:
            self.failure = "single_tensor_staging_budget_exceeded"
            raise RuntimeError("Reference tensor exceeds half the CPU staging budget")
        identity = self.client.create()
        self.files[identity] = 0
        try:
            cpu = tensor.detach().cpu()
            self.peak_staging_bytes = max(self.peak_staging_bytes, size)
            torch.save(cpu, _RemoteWriter(self, identity))
            serialized_size = self.client.finalize(identity)
            if serialized_size != self.files[identity]:
                raise RuntimeError("Reference broker serialized byte count differs")
            self.created += 1
            packed = RemoteDiskTensor(
                identity, serialized_size, tensor.device, tensor.dtype, tuple(tensor.shape)
            )
            weakref.finalize(packed, self.release, identity)
            return packed
        except BaseException:
            self.release(identity)
            if self.failure is None:
                self.failure = "broker_tensor_save_failed"
            raise

    def unpack(self, packed):
        import torch

        from headroom.lab.reference_scratch import ScratchReader

        if not isinstance(packed, RemoteDiskTensor) or packed.identity not in self.files:
            self.failure = "broker_tensor_identity_unavailable"
            raise RuntimeError("Reference broker tensor identity unavailable")
        with ScratchReader(self.client, packed.identity, packed.size) as handle:
            tensor = torch.load(handle, map_location="cpu", weights_only=True)
        if (
            not isinstance(tensor, torch.Tensor)
            or tensor.dtype != packed.dtype
            or tuple(tensor.shape) != packed.shape
        ):
            self.failure = "disk_tensor_metadata_mismatch"
            raise RuntimeError("Reference saved tensor dtype or shape mismatch")
        self.unpacked += 1
        return tensor.to(packed.device)

    def close(self):
        for identity in tuple(self.files):
            self.release(identity)
        self.cleanup_verified = not self.files and self.live_bytes == 0
        return {"verified": self.cleanup_verified, "storage_backend": "host_broker"}

    def evidence(self):
        return {
            "protocol": DISK_PROTOCOL,
            "storage_backend": "host_broker",
            "max_disk_bytes": self.limit,
            "peak_disk_bytes": self.peak_bytes,
            "live_disk_bytes": self.live_bytes,
            "disk_tensors_created": self.created,
            "disk_tensors_unpacked": self.unpacked,
            "peak_staging_tensor_bytes": self.peak_staging_bytes,
            "cleanup_verified": self.cleanup_verified,
            "failure": self.failure,
            "storage": "host-owned bounded service; target receives only opaque IDs",
            "lifetime": "packed object lifetime; never delete on first unpack",
            "host_cleanup_proven": False,
        }
