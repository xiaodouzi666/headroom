"""Bounded, non-executing import of user-supplied CUDA allocator snapshots.

Untrusted bytes are decoded only in an isolated, resource-limited child. Pickle
accepts primitive data opcodes, never class/global/reducer/persistent/buffer
operations. The parent receives the existing JSON stack-table format and returns
its native snapshot shape (shared frame lists remain read-only).
"""

from __future__ import annotations

import io
import json
import math
import os
import pickle
import pickletools
import stat
import subprocess
import sys
from pathlib import Path

MAX_INPUT_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024
MAX_MEMORY_BYTES = 1024 * 1024 * 1024
MAX_CPU_SECONDS = 20
WORKER_TIMEOUT_SECONDS = 30
MAX_DEPTH = 128
MAX_OBJECTS = 2_000_000
MAX_EDGES = 8_000_000
MAX_EXPANDED_NODES = 64_000_000
MAX_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_SCALAR_BYTES = 65536
MAX_OPCODES = 8_000_000

# Only primitive containers/scalars and their memo references. In particular:
# no GLOBAL, STACK_GLOBAL, REDUCE, BUILD, INST, OBJ, NEWOBJ, extensions,
# persistent IDs, bytearrays, sets, or protocol-5 out-of-band buffers.
_ALLOWED_OPCODES = frozenset(
    [
        "PROTO",
        "FRAME",
        "STOP",
        "MARK",
        "NONE",
        "NEWTRUE",
        "NEWFALSE",
        "INT",
        "BININT",
        "BININT1",
        "BININT2",
        "LONG",
        "LONG1",
        "LONG4",
        "FLOAT",
        "BINFLOAT",
        "UNICODE",
        "BINUNICODE",
        "SHORT_BINUNICODE",
        "BINUNICODE8",
        "EMPTY_LIST",
        "LIST",
        "APPEND",
        "APPENDS",
        "EMPTY_DICT",
        "DICT",
        "SETITEM",
        "SETITEMS",
        "EMPTY_TUPLE",
        "TUPLE",
        "TUPLE1",
        "TUPLE2",
        "TUPLE3",
        "PUT",
        "BINPUT",
        "LONG_BINPUT",
        "MEMOIZE",
        "GET",
        "BINGET",
        "LONG_BINGET",
    ]
)
_INDEX_OPCODES = frozenset(["PUT", "BINPUT", "LONG_BINPUT", "GET", "BINGET", "LONG_BINGET"])
_MEMO_WRITES = frozenset(["PUT", "BINPUT", "LONG_BINPUT", "MEMOIZE"])


class SnapshotInputError(ValueError):
    """The input could not be imported within the snapshot safety contract."""


class _PrimitiveUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        raise SnapshotInputError("pickle_object_forbidden")

    def persistent_load(self, pid):
        raise SnapshotInputError("pickle_persistent_id_forbidden")


def _codec():
    # Direct worker execution uses -I -S: import this one trusted sibling module
    # without adding the upload directory/current directory to the import path.
    import importlib.util

    name = "_headroom_snapshot_input_codec"
    module = sys.modules.get(name)
    if module is None:
        location = Path(__file__).parent / "lab" / "snapshot_codec.py"
        spec = importlib.util.spec_from_file_location(name, location)
        if spec is None or spec.loader is None:
            raise SnapshotInputError("snapshot_codec_unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


def _codec_limits():
    return _codec().CodecLimits(
        max_payload_nodes=MAX_EXPANDED_NODES,
        max_expanded_frame_nodes=MAX_EXPANDED_NODES,
        max_expanded_frame_bytes=MAX_EXPANDED_BYTES,
        max_depth=MAX_DEPTH,
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotInputError("duplicate_json_key")
        result[key] = value
    return result


def _integer(value):
    if len(value.lstrip("-")) > 78:
        raise SnapshotInputError("integer_out_of_range")
    return int(value)


def _float(value):
    number = float(value)
    if not math.isfinite(number):
        raise SnapshotInputError("nonfinite_number")
    return number


def _reject_constant(_value):
    raise SnapshotInputError("nonfinite_number")


def _json_loads(data):
    return json.loads(
        data,
        object_pairs_hook=_unique_object,
        parse_int=_integer,
        parse_float=_float,
        parse_constant=_reject_constant,
    )


def _decode_pickle(data):
    operations = memo_writes = 0
    stopped = False
    try:
        for opcode, argument, position in pickletools.genops(data):
            operations += 1
            if operations > MAX_OPCODES:
                raise SnapshotInputError("pickle_opcode_limit")
            if opcode.name not in _ALLOWED_OPCODES:
                raise SnapshotInputError("pickle_opcode_forbidden")
            if opcode.name in _INDEX_OPCODES and (
                type(argument) is not int or not 0 <= argument < MAX_OBJECTS
            ):
                raise SnapshotInputError("pickle_memo_limit")
            if opcode.name in _MEMO_WRITES:
                memo_writes += 1
                if memo_writes > MAX_OBJECTS:
                    raise SnapshotInputError("pickle_memo_limit")
            if opcode.name == "PROTO" and not 0 <= argument <= pickle.HIGHEST_PROTOCOL:
                raise SnapshotInputError("pickle_protocol_unsupported")
            if opcode.name == "FRAME" and not 0 <= argument <= len(data):
                raise SnapshotInputError("pickle_frame_limit")
            if opcode.name == "STOP":
                stopped = True
                if position != len(data) - 1:
                    raise SnapshotInputError("pickle_trailing_data")
        if not stopped:
            raise SnapshotInputError("pickle_stop_missing")
        stream = io.BytesIO(data)
        result = _PrimitiveUnpickler(stream).load()
        if stream.tell() != len(data):
            raise SnapshotInputError("pickle_trailing_data")
        return result
    except SnapshotInputError:
        raise
    except (ValueError, TypeError, EOFError, pickle.UnpicklingError, OverflowError) as error:
        raise SnapshotInputError("invalid_pickle") from error


def _native_graph(value):
    """Validate the whole input graph before selecting fields; preserve safe sharing.

    An iterative postorder walk rejects cycles, measures maximum path depth and
    expanded cost even for memo-shared DAGs, and normalizes tuples to native lists.
    """
    if type(value) is not dict:
        raise SnapshotInputError("snapshot_object_required")
    active, complete = set(), {}
    stack = [(value, False)]
    objects = edges = 0
    while stack:
        item, finishing = stack.pop()
        kind = type(item)
        if kind not in (dict, list, tuple):
            continue
        identity = id(item)
        if identity in complete:
            continue
        if not finishing:
            if identity in active:
                raise SnapshotInputError("snapshot_cycle")
            objects += 1
            if objects > MAX_OBJECTS:
                raise SnapshotInputError("snapshot_object_limit")
            active.add(identity)
            if len(active) > MAX_DEPTH:
                raise SnapshotInputError("snapshot_depth_limit")
            children = list(item.values()) if kind is dict else item
            edges += len(children) + (len(item) if kind is dict else 0)
            if edges > MAX_EDGES:
                raise SnapshotInputError("snapshot_edge_limit")
            if kind is dict and any(type(key) is not str for key in item):
                raise SnapshotInputError("snapshot_keys_must_be_strings")
            stack.append((item, True))
            stack.extend((child, False) for child in reversed(children))
            continue
        children = list(item.values()) if kind is dict else item
        normalized = []
        depth, expanded_nodes, expanded_bytes = 1, 1, 2
        for child in children:
            child_kind = type(child)
            if child_kind in (dict, list, tuple):
                converted, child_depth, nodes, size = complete[id(child)]
            elif child_kind in (type(None), bool, int, float, str):
                converted, child_depth, nodes = child, 0, 1
                if child_kind is int and child.bit_length() > 256:
                    raise SnapshotInputError("integer_out_of_range")
                if child_kind is float and not math.isfinite(child):
                    raise SnapshotInputError("nonfinite_number")
                size = len(child.encode("utf-8")) if child_kind is str else 32
                if size > MAX_SCALAR_BYTES:
                    raise SnapshotInputError("snapshot_scalar_limit")
            else:
                raise SnapshotInputError("snapshot_type_forbidden")
            normalized.append(converted)
            depth = max(depth, child_depth + 1)
            expanded_nodes += nodes
            expanded_bytes += size
            if depth > MAX_DEPTH:
                raise SnapshotInputError("snapshot_depth_limit")
            if expanded_nodes > MAX_EXPANDED_NODES:
                raise SnapshotInputError("snapshot_expanded_nodes_limit")
            if expanded_bytes > MAX_EXPANDED_BYTES:
                raise SnapshotInputError("snapshot_expanded_bytes_limit")
        if kind is dict:
            key_bytes = sum(len(key.encode("utf-8")) for key in item)
            if any(len(key.encode("utf-8")) > MAX_SCALAR_BYTES for key in item):
                raise SnapshotInputError("snapshot_scalar_limit")
            expanded_nodes += len(item)
            expanded_bytes += key_bytes
            converted = dict(zip(item, normalized, strict=True))
        else:
            converted = normalized
        if expanded_nodes > MAX_EXPANDED_NODES:
            raise SnapshotInputError("snapshot_expanded_nodes_limit")
        if expanded_bytes > MAX_EXPANDED_BYTES:
            raise SnapshotInputError("snapshot_expanded_bytes_limit")
        complete[identity] = (converted, depth, expanded_nodes, expanded_bytes)
        active.remove(identity)
    result = complete[id(value)][0]
    if type(result.get("segments")) is not list or type(result.get("device_traces")) is not list:
        raise SnapshotInputError("snapshot_fields_required")
    if any(type(segment) is not dict for segment in result["segments"]):
        raise SnapshotInputError("invalid_segments")
    if any(
        type(trace) is not list or any(type(event) is not dict for event in trace)
        for trace in result["device_traces"]
    ):
        raise SnapshotInputError("invalid_device_traces")
    return {key: result[key] for key in ("segments", "device_traces")}


def _decode_input(data):
    stripped = data.lstrip()
    if stripped.startswith((b"{", b"[")):
        document = _json_loads(data)
        codec = _codec()
        # Decode the existing JSON envelope in the child. Convert its shared,
        # immutable frame wrappers through the same native encoder before IPC.
        decoded = codec.decode_snapshot(document, limits=_codec_limits())
        if decoded is not document:
            # The trusted codec returns dict/list subclasses for shared frames.
            # JSON-native input itself cannot create arbitrary subclasses.
            decoded = _plain_codec_graph(decoded)
        return _native_graph(decoded)
    return _native_graph(_decode_pickle(data))


def _plain_codec_graph(value):
    copies = {}

    def walk(item):
        if isinstance(item, (dict, list, tuple)):
            identity = id(item)
            if identity in copies:
                return copies[identity]
            if isinstance(item, dict):
                result = {}
                copies[identity] = result
                result.update((key, walk(child)) for key, child in item.items())
            else:
                result = []
                copies[identity] = result
                result.extend(walk(child) for child in item)
            return result
        return item

    return walk(value)


def _open_input(path, max_bytes):
    path = Path(path)
    if ".." in path.parts:
        raise SnapshotInputError("snapshot_path_forbidden")
    if not path.is_absolute():
        path = Path.cwd() / path
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
    finally:
        os.close(descriptor)
    try:
        info = os.fstat(leaf)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
            raise SnapshotInputError("snapshot_file_size_or_type")
        return leaf
    except BaseException:
        os.close(leaf)
        raise


def read_snapshot_input(path: Path, *, max_bytes=MAX_INPUT_BYTES) -> dict:
    """Read a <=50 MiB snapshot without executing code or opening frame paths.

    Linux resource limits are required. Unsupported platforms fail closed.
    No credentials, GPU, model service, or source script is touched.
    """
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_INPUT_BYTES:
        raise SnapshotInputError("invalid_snapshot_size_limit")
    descriptor = None
    try:
        descriptor = _open_input(path, max_bytes)
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(Path(__file__).resolve()),
                "--worker",
                str(descriptor),
                str(max_bytes),
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            pass_fds=(descriptor,),
            env={"LANG": "C.UTF-8"},
            timeout=WORKER_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            raise SnapshotInputError("snapshot_worker_rejected")
        if not result.stdout or len(result.stdout) > MAX_OUTPUT_BYTES:
            raise SnapshotInputError("snapshot_output_limit")
        document = _json_loads(result.stdout)
        codec = _codec()
        if not isinstance(document, dict) or document.get(codec.FORMAT_KEY) != codec.FORMAT:
            raise SnapshotInputError("invalid_snapshot_worker_output")
        native = codec.decode_snapshot(document, limits=_codec_limits())
        if type(native) is not dict or set(native) != {"segments", "device_traces"}:
            raise SnapshotInputError("invalid_snapshot_worker_output")
        return native
    except SnapshotInputError:
        raise
    except (
        OSError,
        MemoryError,
        ValueError,
        TypeError,
        EOFError,
        OverflowError,
        RecursionError,
        subprocess.SubprocessError,
    ) as error:
        raise SnapshotInputError("snapshot_import_failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _worker_main(descriptor, max_bytes):
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_SECONDS, MAX_CPU_SECONDS + 1))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
            raise SnapshotInputError("snapshot_file_size_or_type")
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SnapshotInputError("snapshot_input_limit")
    native = _decode_input(data)
    document = _codec().encode_snapshot(native, limits=_codec_limits())
    encoded = json.dumps(document, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    output = encoded.encode("ascii")
    if len(output) > MAX_OUTPUT_BYTES:
        raise SnapshotInputError("snapshot_output_limit")
    sys.stdout.buffer.write(output)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 4 or sys.argv[1] != "--worker":
            raise SnapshotInputError("invalid_worker_invocation")
        descriptor, maximum = int(sys.argv[2]), int(sys.argv[3])
        if not 0 < maximum <= MAX_INPUT_BYTES:
            raise SnapshotInputError("invalid_snapshot_size_limit")
        _worker_main(descriptor, maximum)
    except SnapshotInputError as error:
        sys.stderr.write(str(error) + "\n")
        raise SystemExit(2) from None
    except Exception:  # noqa: BLE001 - no user-controlled content in worker diagnostics
        sys.stderr.write("snapshot_worker_rejected\n")
        raise SystemExit(2) from None
