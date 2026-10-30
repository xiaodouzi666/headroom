"""Host-owned bounded byte storage for one numerical reference.

Only a private Unix socket is shared with the target. Object directories and
paths never cross the protocol, and the host never deserializes stored bytes.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import struct
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "headroom.reference-scratch.v1"
MAX_BYTES = 64 * 1024**3
MAX_OBJECTS = 4096
MAX_CHUNK_BYTES = 4 * 1024**2
MAX_HEADER_BYTES = 4096
HOST_RESERVE_BYTES = 1024**3
MAX_CONCURRENCY = 2
CONNECTION_SECONDS = 10
MAX_REQUESTS = 1_000_000
_ID = re.compile(r"[0-9a-f]{32}")


class ReferenceScratchError(RuntimeError):
    """A fixed protocol/admission error; no target-controlled text is echoed."""


def _require(condition, code):
    if not condition:
        raise ReferenceScratchError(code)


def _integer(value, maximum, *, minimum=0):
    return type(value) is int and minimum <= value <= maximum


def _read_exact(connection, count, *, deadline=None):
    chunks = bytearray()
    while len(chunks) < count:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "connection_deadline_exceeded")
            connection.settimeout(remaining)
        part = connection.recv(min(count - len(chunks), MAX_CHUNK_BYTES))
        _require(bool(part), "truncated_frame")
        chunks.extend(part)
    return bytes(chunks)


def _receive_header(connection, *, deadline=None):
    size = struct.unpack("!I", _read_exact(connection, 4, deadline=deadline))[0]
    _require(0 < size <= MAX_HEADER_BYTES, "invalid_header_size")
    try:
        value = json.loads(_read_exact(connection, size, deadline=deadline))
    except (UnicodeError, ValueError, RecursionError):
        raise ReferenceScratchError("invalid_header") from None
    _require(isinstance(value, dict), "invalid_header")
    return value


def _send(connection, header, data=b""):
    encoded = json.dumps(header, allow_nan=False, separators=(",", ":")).encode()
    _require(len(encoded) <= MAX_HEADER_BYTES, "response_header_too_large")
    connection.sendall(struct.pack("!I", len(encoded)) + encoded)
    if data:
        connection.sendall(data)


def _read_json_at(directory_fd, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        _require(
            stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 4096,
            "invalid_owner_record",
        )
        return json.load(handle)


def _write_json_at(directory_fd, name, data):
    encoded = (json.dumps(data, allow_nan=False, sort_keys=True) + "\n").encode()
    _require(len(encoded) <= 4096, "host_record_too_large")
    temporary = name + "." + secrets.token_hex(8) + ".tmp"
    fd = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _process_identity(pid):
    try:
        value = Path(f"/proc/{pid}/stat").read_text()
        return value.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


@dataclass
class _Object:
    identity: tuple[int, int]
    reserved: int = 0
    size: int = 0
    finalized: bool = False
    dirty: bool = False


class ReferenceScratchBroker:
    """One host service, one run quota; append admission is serialized before I/O."""

    def __init__(
        self, root, max_bytes, *, socket_path=None, max_objects=MAX_OBJECTS, peer_uid=None
    ):
        self._root_fd = self._objects_fd = None
        try:
            self._initialize(
                root,
                max_bytes,
                socket_path=socket_path,
                max_objects=max_objects,
                peer_uid=peer_uid,
            )
        except BaseException:
            for fd in (self._objects_fd, self._root_fd):
                if fd is not None:
                    os.close(fd)
            raise

    def _initialize(self, root, max_bytes, *, socket_path, max_objects, peer_uid):
        _require(_integer(max_bytes, MAX_BYTES, minimum=1), "invalid_byte_limit")
        _require(_integer(max_objects, MAX_OBJECTS, minimum=1), "invalid_object_limit")
        self.root = Path(root).absolute()
        self.root.mkdir(mode=0o700, exist_ok=True)
        self._root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        root_info = os.fstat(self._root_fd)
        _require(
            root_info.st_uid == os.getuid() and not os.listdir(self._root_fd),
            "root_not_new_owned_empty_directory",
        )
        os.fchmod(self._root_fd, 0o700)
        _require(
            shutil.disk_usage(self.root).free >= max_bytes + HOST_RESERVE_BYTES,
            "insufficient_host_disk_reserve",
        )
        endpoint = Path(tempfile.mkdtemp(prefix="headroom-ref-")) if socket_path is None else None
        self.socket_path = (
            Path(socket_path).absolute() if socket_path is not None else endpoint / "rpc.sock"
        )
        _require(len(os.fsencode(self.socket_path)) <= 100, "socket_path_too_long")
        parent = self.socket_path.parent
        parent_info = parent.lstat()
        _require(
            stat.S_ISDIR(parent_info.st_mode)
            and parent_info.st_uid == os.getuid()
            and stat.S_IMODE(parent_info.st_mode) == 0o700,
            "socket_parent_not_private_owned_directory",
        )
        _require(
            not self.socket_path.exists() and not self.socket_path.is_symlink(), "socket_exists"
        )
        self.max_bytes, self.max_objects = max_bytes, max_objects
        self.peer_uid = os.getuid() if peer_uid is None else peer_uid
        _require(_integer(self.peer_uid, 2**32 - 1), "invalid_peer_uid")
        self.nonce = secrets.token_hex(16)
        self.owner = {
            "schema": SCHEMA,
            "nonce": self.nonce,
            "pid": os.getpid(),
            "process_identity": _process_identity(os.getpid()),
            "uid": os.getuid(),
            "root_identity": [root_info.st_dev, root_info.st_ino],
            "max_bytes": max_bytes,
            "max_objects": max_objects,
            "socket_path": str(self.socket_path),
            "socket_identity": None,
            "socket_directory_owned": endpoint is not None,
            "socket_parent_identity": [parent_info.st_dev, parent_info.st_ino],
        }
        _write_json_at(self._root_fd, "owner.json", self.owner)
        os.mkdir("objects", 0o700, dir_fd=self._root_fd)
        self._objects_fd = os.open(
            "objects", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self._root_fd
        )
        self.objects: dict[str, _Object] = {}
        self.reserved_bytes = self.peak_reserved_bytes = self.bytes_written = 0
        self.created_objects = self.deleted_objects = self.requests = 0
        self.failed_operations = 0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENCY)
        self._connections = set()
        self._workers = set()
        self._listener = None
        self._thread = None
        self._closed = False
        self.cleanup_verified = False

    def start(self):
        _require(self._listener is None and not self._closed, "broker_already_started_or_closed")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            info = self.socket_path.lstat()
            self.owner["socket_identity"] = [info.st_dev, info.st_ino]
            _write_json_at(self._root_fd, "owner.json", self.owner)
            listener.listen(MAX_CONCURRENCY)
            listener.settimeout(0.2)
            self._listener = listener
            self._thread = threading.Thread(target=self._accept, daemon=True)
            self._thread.start()
        except BaseException:
            listener.close()
            raise
        return self

    def _accept(self):
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            if not self._slots.acquire(blocking=False):
                connection.close()
                continue
            connection.settimeout(CONNECTION_SECONDS)
            worker = threading.Thread(target=self._serve, args=(connection,), daemon=True)
            with self._lock:
                self._connections.add(connection)
                self._workers.add(worker)
            worker.start()

    def _serve(self, connection):
        try:
            credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            _, uid, _ = struct.unpack("3i", credentials)
            _require(uid == self.peer_uid, "peer_uid_mismatch")
            deadline = time.monotonic() + CONNECTION_SECONDS
            header = _receive_header(connection, deadline=deadline)
            with self._lock:
                self.requests += 1
                _require(self.requests <= MAX_REQUESTS, "request_limit_exceeded")
            data = b""
            if header.get("op") == "append":
                _require(_integer(header.get("size"), MAX_CHUNK_BYTES), "invalid_chunk_size")
                data = _read_exact(connection, header["size"], deadline=deadline)
            reply, output = self._dispatch(header, data)
            connection.settimeout(max(0.001, deadline - time.monotonic()))
            _send(
                connection,
                {"schema": SCHEMA, "ok": True, "max_bytes": self.max_bytes, **reply},
                output,
            )
        except (OSError, ValueError, TypeError, ReferenceScratchError, struct.error):
            with self._lock:
                self.failed_operations += 1
            try:
                _send(
                    connection,
                    {
                        "schema": SCHEMA,
                        "ok": False,
                        "max_bytes": self.max_bytes,
                        "error": "request_rejected",
                    },
                )
            except (OSError, ReferenceScratchError):
                pass
        finally:
            connection.close()
            with self._lock:
                self._connections.discard(connection)
                self._workers.discard(threading.current_thread())
            self._slots.release()

    def _record(self, identity):
        _require(isinstance(identity, str) and _ID.fullmatch(identity), "invalid_object_identity")
        record = self.objects.get(identity)
        _require(record is not None, "unknown_object")
        return record

    def _open_object(self, identity, flags):
        fd = os.open(identity + ".bin", flags | os.O_NOFOLLOW, dir_fd=self._objects_fd)
        info = os.fstat(fd)
        record = self.objects[identity]
        if not (
            stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1
            and (info.st_dev, info.st_ino) == record.identity
            and info.st_uid == os.getuid()
        ):
            os.close(fd)
            raise ReferenceScratchError("object_identity_changed")
        return fd

    def _dispatch(self, header, data=b""):
        _require(not self._stop.is_set(), "broker_stopping")
        op = header.get("op")
        expected = {
            "create": {"op"},
            "append": {"op", "id", "size"},
            "finalize": {"op", "id"},
            "read": {"op", "id", "offset", "size"},
            "delete": {"op", "id"},
        }.get(op)
        _require(expected is not None and set(header) == expected, "invalid_operation_fields")
        with self._lock:
            if op == "create":
                _require(len(self.objects) < self.max_objects, "object_limit_exceeded")
                identity = secrets.token_hex(16)
                fd = os.open(
                    identity + ".bin",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=self._objects_fd,
                )
                try:
                    info = os.fstat(fd)
                    self.objects[identity] = _Object((info.st_dev, info.st_ino))
                    self.created_objects += 1
                finally:
                    os.close(fd)
                return {"id": identity}, b""
            identity = header.get("id")
            record = self._record(identity)
            if op == "append":
                size = header["size"]
                _require(
                    _integer(size, MAX_CHUNK_BYTES) and len(data) == size, "invalid_chunk_size"
                )
                _require(not record.finalized and not record.dirty, "object_not_appendable")
                _require(self.reserved_bytes + size <= self.max_bytes, "byte_limit_exceeded")
                _require(
                    shutil.disk_usage(self.root).free >= size + HOST_RESERVE_BYTES,
                    "host_disk_reserve_exhausted",
                )
                # Reserve the entire request before open/write. A partial or failed
                # write holds its full reservation until a verified unlink.
                record.reserved += size
                self.reserved_bytes += size
                self.peak_reserved_bytes = max(self.peak_reserved_bytes, self.reserved_bytes)
                try:
                    fd = self._open_object(identity, os.O_WRONLY | os.O_APPEND)
                    try:
                        _require(os.fstat(fd).st_size == record.size, "object_size_changed")
                        written = 0
                        while written < size:
                            count = os.write(fd, memoryview(data)[written:])
                            _require(count > 0, "short_object_write")
                            written += count
                            record.size += count
                            self.bytes_written += count
                    finally:
                        os.close(fd)
                except BaseException:
                    record.dirty = True
                    raise
                return {"size": record.size}, b""
            if op == "finalize":
                _require(not record.dirty and not record.finalized, "object_not_finalizable")
                fd = self._open_object(identity, os.O_RDONLY)
                try:
                    info = os.fstat(fd)
                    _require(info.st_size == record.size, "object_size_changed")
                    os.fsync(fd)
                except BaseException:
                    record.dirty = True
                    raise
                finally:
                    os.close(fd)
                record.finalized = True
                return {"size": record.size}, b""
            if op == "read":
                offset, size = header["offset"], header["size"]
                _require(
                    _integer(offset, self.max_bytes)
                    and _integer(size, MAX_CHUNK_BYTES)
                    and offset <= record.size,
                    "invalid_read_range",
                )
                _require(record.finalized and not record.dirty, "object_not_readable")
                fd = self._open_object(identity, os.O_RDONLY)
                try:
                    _require(os.fstat(fd).st_size == record.size, "object_size_changed")
                    output = os.pread(fd, min(size, record.size - offset), offset)
                finally:
                    os.close(fd)
                return {"size": len(output)}, output
            fd = self._open_object(identity, os.O_RDONLY)
            os.close(fd)
            os.unlink(identity + ".bin", dir_fd=self._objects_fd)
            try:
                os.stat(identity + ".bin", dir_fd=self._objects_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                record.dirty = True
                raise ReferenceScratchError("object_delete_unverified")
            self.reserved_bytes -= record.reserved
            del self.objects[identity]
            self.deleted_objects += 1
            return {"deleted": True}, b""

    def evidence(self):
        with self._lock:
            return {
                "schema": SCHEMA,
                "nonce": self.nonce,
                "root": str(self.root),
                "socket_path": str(self.socket_path),
                "owner_pid": self.owner["pid"],
                "owner_process_identity": self.owner["process_identity"],
                "max_bytes": self.max_bytes,
                "max_objects": self.max_objects,
                "live_reserved_bytes": self.reserved_bytes,
                "peak_reserved_bytes": self.peak_reserved_bytes,
                "bytes_written": self.bytes_written,
                "live_objects": len(self.objects),
                "created_objects": self.created_objects,
                "deleted_objects": self.deleted_objects,
                "requests": self.requests,
                "failed_operations": self.failed_operations,
                "cleanup_verified": self.cleanup_verified,
                "quota_enforcement": "host broker reserves bytes before every append",
                "target_host_directory_access": False,
            }

    def close(self):
        if self._closed:
            return self.evidence()
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        with self._lock:
            connections = list(self._connections)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        with self._lock:
            workers = list(self._workers)
        for worker in workers:
            worker.join(timeout=CONNECTION_SECONDS + 1)
        if any(worker.is_alive() for worker in workers):
            receipt = {**self.evidence(), "error": "broker_workers_not_stopped"}
            _write_json_at(self._root_fd, "receipt.json", receipt)
            return receipt
        with self._lock:
            for identity in tuple(self.objects):
                try:
                    fd = self._open_object(identity, os.O_RDONLY)
                    os.close(fd)
                    os.unlink(identity + ".bin", dir_fd=self._objects_fd)
                    try:
                        os.stat(identity + ".bin", dir_fd=self._objects_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        self.reserved_bytes -= self.objects[identity].reserved
                        del self.objects[identity]
                    else:
                        raise ReferenceScratchError("object_delete_unverified")
                except (OSError, ReferenceScratchError):
                    continue
            self.cleanup_verified = not self.objects and not os.listdir(self._objects_fd)
        try:
            _unlink_owned_socket(self.owner)
        except (OSError, ReferenceScratchError):
            self.cleanup_verified = False
        receipt = self.evidence()
        _write_json_at(self._root_fd, "receipt.json", receipt)
        os.close(self._objects_fd)
        os.close(self._root_fd)
        self._closed = True
        return receipt


def _unlink_owned_socket(owner):
    path = Path(owner["socket_path"])
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    _require(
        stat.S_ISSOCK(info.st_mode)
        and info.st_uid == owner["uid"]
        and [info.st_dev, info.st_ino] == owner["socket_identity"],
        "socket_identity_changed",
    )
    path.unlink()
    if owner.get("socket_directory_owned") is True:
        parent = path.parent
        info = parent.lstat()
        _require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == owner["uid"]
            and [info.st_dev, info.st_ino] == owner.get("socket_parent_identity"),
            "socket_parent_identity_changed",
        )
        parent.rmdir()
    return not path.exists()


def cleanup_owned_scratch(root, *, expected_nonce):
    """Supervisor recovery only after the recorded owner process has disappeared.

    Never recurse into a supplied path or follow a link. Unknown/replaced files
    cause a retained failure receipt; no unrelated files are deleted.
    """
    result = {"schema": SCHEMA, "cleanup_verified": False, "error": None}
    root_fd = objects_fd = None
    try:
        _require(isinstance(expected_nonce, str) and _ID.fullmatch(expected_nonce), "invalid_nonce")
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(root_fd)
        owner = _read_json_at(root_fd, "owner.json")
        _require(isinstance(owner, dict), "invalid_owner_record")
        _require(
            owner.get("schema") == SCHEMA
            and owner.get("nonce") == expected_nonce
            and owner.get("uid") == os.getuid() == info.st_uid
            and owner.get("root_identity") == [info.st_dev, info.st_ino]
            and _integer(owner.get("max_bytes"), MAX_BYTES, minimum=1)
            and _integer(owner.get("max_objects"), MAX_OBJECTS, minimum=1)
            and _integer(owner.get("pid"), 2**31 - 1, minimum=1),
            "owner_identity_changed",
        )
        try:
            os.kill(owner["pid"], 0)
        except ProcessLookupError:
            owner_alive = False
        except PermissionError:
            owner_alive = True
        else:
            active = _process_identity(owner["pid"])
            owner_alive = (
                active is None
                or owner.get("process_identity") is None
                or active == owner["process_identity"]
            )
        _require(not owner_alive, "owner_still_running")
        _require(
            set(os.listdir(root_fd)) <= {"owner.json", "receipt.json", "objects", "rpc.sock"},
            "unexpected_root_entry",
        )
        objects_fd = os.open(
            "objects", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd
        )
        names = os.listdir(objects_fd)
        _require(len(names) <= owner["max_objects"], "object_count_exceeded")
        for name in names:
            _require(re.fullmatch(r"[0-9a-f]{32}\.bin", name), "unexpected_object_entry")
            item = os.stat(name, dir_fd=objects_fd, follow_symlinks=False)
            _require(
                stat.S_ISREG(item.st_mode)
                and item.st_nlink == 1
                and item.st_uid == owner["uid"]
                and 0 <= item.st_size <= owner["max_bytes"],
                "object_identity_changed",
            )
        for name in names:
            os.unlink(name, dir_fd=objects_fd)
        _require(not os.listdir(objects_fd), "object_cleanup_unverified")
        _unlink_owned_socket(owner)
        result.update(
            nonce=expected_nonce,
            cleanup_verified=True,
            live_reserved_bytes=0,
            live_objects=0,
            recovered_after_owner_exit=True,
        )
        _write_json_at(root_fd, "receipt.json", result)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, ReferenceScratchError):
        result["error"] = "owned_scratch_cleanup_rejected"
    finally:
        if objects_fd is not None:
            os.close(objects_fd)
        if root_fd is not None:
            os.close(root_fd)
    return result


class ReferenceScratchClient:
    """The target can access only opaque IDs through a bounded Unix protocol."""

    def __init__(self, socket_path, max_bytes):
        _require(_integer(max_bytes, MAX_BYTES, minimum=1), "invalid_byte_limit")
        self.socket_path, self.max_bytes = str(socket_path), max_bytes
        _require(len(os.fsencode(self.socket_path)) <= 100, "socket_path_too_long")

    def _call(self, header, data=b""):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(CONNECTION_SECONDS)
            connection.connect(self.socket_path)
            deadline = time.monotonic() + CONNECTION_SECONDS
            _send(connection, header, data)
            reply = _receive_header(connection, deadline=deadline)
            _require(
                reply.get("schema") == SCHEMA
                and type(reply.get("max_bytes")) is int
                and reply.get("max_bytes") == self.max_bytes
                and reply.get("ok") is True,
                "broker_request_rejected",
            )
            output = b""
            if header["op"] == "read":
                size = reply.get("size")
                _require(_integer(size, header["size"]), "invalid_broker_read_size")
                output = _read_exact(connection, size, deadline=deadline)
            return reply, output

    def create(self):
        reply, _ = self._call({"op": "create"})
        identity = reply.get("id")
        _require(isinstance(identity, str) and _ID.fullmatch(identity), "invalid_broker_identity")
        return identity

    def append(self, identity, data):
        view = memoryview(data)
        for offset in range(0, len(view), MAX_CHUNK_BYTES):
            chunk = view[offset : offset + MAX_CHUNK_BYTES]
            self._call({"op": "append", "id": identity, "size": len(chunk)}, chunk)
        return len(view)

    def finalize(self, identity):
        reply, _ = self._call({"op": "finalize", "id": identity})
        _require(_integer(reply.get("size"), self.max_bytes), "invalid_broker_object_size")
        return reply["size"]

    def read(self, identity, offset, size):
        _require(_integer(size, MAX_CHUNK_BYTES), "invalid_read_size")
        _, output = self._call({"op": "read", "id": identity, "offset": offset, "size": size})
        return output

    def delete(self, identity):
        reply, _ = self._call({"op": "delete", "id": identity})
        _require(reply.get("deleted") is True, "broker_delete_unverified")
        return True


class ScratchReader(io.RawIOBase):
    """Seekable bounded-chunk reader; the host never unpickles a tensor."""

    def __init__(self, client, identity, size):
        self.client, self.identity, self.size, self.position = client, identity, size, 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=os.SEEK_SET):
        _require(type(offset) is int and whence in {0, 1, 2}, "invalid_seek")
        target = offset + (self.position if whence == 1 else self.size if whence == 2 else 0)
        _require(0 <= target <= self.size, "invalid_seek")
        self.position = target
        return target

    def readinto(self, buffer):
        view = memoryview(buffer).cast("B")
        wanted = min(len(view), self.size - self.position)
        done = 0
        while done < wanted:
            chunk = self.client.read(
                self.identity, self.position, min(wanted - done, MAX_CHUNK_BYTES)
            )
            _require(bool(chunk), "short_broker_read")
            view[done : done + len(chunk)] = chunk
            done += len(chunk)
            self.position += len(chunk)
        return done

    def read(self, size=-1):
        _require(type(size) is int and size >= -1, "invalid_read_size")
        count = self.size - self.position if size == -1 else min(size, self.size - self.position)
        output = bytearray(count)
        size = self.readinto(output)
        return bytes(output[:size])


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--max-bytes", type=int, required=True)
    parser.add_argument("--max-objects", type=int, default=MAX_OBJECTS)
    parser.add_argument("--max-seconds", type=float, default=600)
    args = parser.parse_args(argv)
    _require(0 < args.max_seconds <= 3600, "invalid_service_lifetime")
    broker = ReferenceScratchBroker(
        args.root, args.max_bytes, socket_path=args.socket, max_objects=args.max_objects
    )
    stopping = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stopping.set())
    try:
        broker.start()
        end = time.monotonic() + args.max_seconds
        while time.monotonic() < end and not stopping.wait(0.2):
            pass
    finally:
        broker.close()


if __name__ == "__main__":
    main()
