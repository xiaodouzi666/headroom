"""Offline contracts for importing hostile snapshot bytes; never GPU/model calls."""

import io
import json
import os
import pickle
import socket
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom import snapshot_input as reader
from headroom.evidence_analysis import analyze_snapshot
from headroom.lab.snapshot_codec import encode_snapshot
from headroom.snapshot_input import SnapshotInputError, read_snapshot_input


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Snapshot tests must not use the network")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)


def snapshot():
    frame = {"filename": "/untrusted/original/train.py", "line": 7, "name": "forward"}
    frames = [frame]
    return {
        "segments": [
            {
                "device": 0,
                "address": 4096,
                "total_size": 512,
                "blocks": [
                    {
                        "address": 4096,
                        "size": 512,
                        "state": "active_allocated",
                        "requested_size": 512,
                        "frames": frames,
                    }
                ],
            }
        ],
        "device_traces": [
            [
                {"action": "segment_alloc", "addr": 4096, "size": 512, "stream": 0},
                {"action": "alloc", "addr": 4096, "size": 512, "stream": 0, "frames": frames},
            ]
        ],
        "not_an_execution_result": {"peak_allocated_bytes": 999, "optimizer_updates": 20},
    }


def write(tmp_path, data, name="snapshot.pickle"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_native_pickle_protocols_preserve_data_without_invented_measurements(tmp_path, protocol):
    original = snapshot()
    result = read_snapshot_input(write(tmp_path, pickle.dumps(original, protocol=protocol)))
    assert set(result) == {"segments", "device_traces"}
    assert result == {key: original[key] for key in result}
    assert result["segments"][0]["blocks"][0]["frames"] is result["device_traces"][0][1]["frames"]
    analysis = analyze_snapshot(result, {})
    assert analysis["header"]["recorded_peak_allocated_bytes"] is None
    assert analysis["header"]["peak_is_exact"] is False
    assert analysis["step_boundaries"] == []


@pytest.mark.parametrize("encoded", [False, True])
def test_existing_native_and_stack_table_json_are_compatible(tmp_path, encoded):
    data = encode_snapshot(snapshot()) if encoded else snapshot()
    result = read_snapshot_input(write(tmp_path, json.dumps(data).encode(), "capture.json"))
    assert result["device_traces"] == snapshot()["device_traces"]
    assert set(result) == {"segments", "device_traces"}


def test_tuple_data_normalizes_to_lists(tmp_path):
    value = snapshot()
    value["device_traces"][0][1]["frames"] = ({"filename": "train.py", "line": 1, "name": "f"},)
    result = read_snapshot_input(write(tmp_path, pickle.dumps(value)))
    assert isinstance(result["device_traces"][0][1]["frames"], list)


def test_reduce_sentinel_never_executes(tmp_path):
    sentinel = tmp_path / "MUST_NOT_EXIST"

    class Evil:
        def __reduce__(self):
            return os.system, ("touch " + str(sentinel),)

    payload = pickle.dumps({"segments": [], "device_traces": [[]], "ignored": Evil()})
    assert not sentinel.exists()
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, payload))
    assert not sentinel.exists()


@pytest.mark.parametrize(
    "payload",
    [
        b"cos\nsystem\n.",
        b"\x80\x04\x8c\x02os\x8c\x06system\x93.",
        b"N)R.",
        b"N)b.",
        b"N)\x81.",
        b"N)}\x92.",
        b"Pignored\n.",
        b"NQ.",
        b"\x80\x05\x97.",
        b"N\x98.",
        b"\x82\x01.",
        b"\x83\x01\x00.",
        b"\x84\x01\x00\x00\x00.",
        b"\x80\x05\x96\x00\x00\x00\x00\x00\x00\x00\x00.",
    ],
)
def test_object_persistent_extension_and_buffer_opcodes_are_forbidden(tmp_path, payload):
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, payload))


@pytest.mark.parametrize("suffix", [b"trailing", pickle.dumps(None), b"\x00", b"\n"])
def test_pickle_trailing_bytes_and_second_objects_are_rejected(tmp_path, suffix):
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, pickle.dumps(snapshot()) + suffix))


def test_restricted_unpickler_also_denies_classes_and_persistent_ids():
    decoder = reader._PrimitiveUnpickler(io.BytesIO(b""))
    with pytest.raises(SnapshotInputError):
        decoder.find_class("os", "system")
    with pytest.raises(SnapshotInputError):
        decoder.persistent_load("ignored")


@pytest.mark.parametrize(
    "payload",
    [
        b"N" + b"r" + struct.pack("<I", 0xFFFFFFFF) + b".",
        b"\x80\x04\x95" + struct.pack("<Q", 1 << 63) + b"N.",
        b"\x80\xffN.",
        b"\x80\x04}",
        b"not a snapshot",
        b"",
    ],
)
def test_malformed_pickle_and_huge_memo_or_frame_are_rejected(tmp_path, payload):
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, payload))


@pytest.mark.parametrize(
    "extra",
    [
        float("nan"),
        float("inf"),
        b"bytes",
        {1, 2},
        1 << 300,
        "x" * 65537,
    ],
)
def test_unsupported_scalars_are_rejected_even_in_ignored_fields(tmp_path, extra):
    value = snapshot()
    value["ignored"] = extra
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, pickle.dumps(value)))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"segments":[],"segments":[],"device_traces":[[]]}',
        b'{"segments":[],"device_traces":[[]],"ignored":NaN}',
        b'{"segments":[],"device_traces":[[]],"ignored":1e9999}',
        b'{"segments":[],"device_traces":[[]]} {}',
        b'{"segments":[]}',
        b'{"segments":{},"device_traces":[[]]}',
        b'{"segments":[1],"device_traces":[[]]}',
        b'{"segments":[],"device_traces":[[1]]}',
    ],
)
def test_ambiguous_or_non_native_json_is_rejected(tmp_path, payload):
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, payload, "capture.json"))


def test_cycles_and_deep_graphs_are_rejected(tmp_path):
    cycle = []
    cycle.append(cycle)
    deep = []
    for _ in range(reader.MAX_DEPTH + 1):
        deep = [deep]
    for number, extra in enumerate((cycle, deep)):
        value = snapshot()
        value["ignored"] = extra
        with pytest.raises(SnapshotInputError):
            read_snapshot_input(write(tmp_path, pickle.dumps(value), f"bad-{number}.pickle"))


def test_small_shared_dag_cannot_evade_expansion_limits(tmp_path):
    shared = [0]
    for _ in range(27):
        shared = [shared, shared]
    payload = pickle.dumps({"segments": [], "device_traces": [[]], "ignored": shared})
    assert len(payload) < 1000
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(write(tmp_path, payload))


def test_graph_object_edge_and_depth_limits_are_counted(monkeypatch):
    monkeypatch.setattr(reader, "MAX_OBJECTS", 2)
    with pytest.raises(SnapshotInputError, match="object_limit"):
        reader._native_graph({"segments": [], "device_traces": [[]]})
    monkeypatch.setattr(reader, "MAX_OBJECTS", 100)
    monkeypatch.setattr(reader, "MAX_EDGES", 1)
    with pytest.raises(SnapshotInputError, match="edge_limit"):
        reader._native_graph({"segments": [], "device_traces": [[]]})


@pytest.mark.parametrize("kind", ["leaf_symlink", "parent_symlink", "fifo", "directory", "large"])
def test_nonregular_symlink_and_oversize_inputs_fail_before_worker(tmp_path, monkeypatch, kind):
    real = write(tmp_path, pickle.dumps(snapshot()), "real.pickle")
    path = tmp_path / "input"
    if kind == "leaf_symlink":
        path.symlink_to(real)
    elif kind == "parent_symlink":
        (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
        path = tmp_path / "link" / real.name
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        with path.open("wb") as handle:
            handle.truncate(reader.MAX_INPUT_BYTES + 1)
    monkeypatch.setattr(reader.subprocess, "run", lambda *_a, **_k: pytest.fail("must not spawn"))
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(path)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, reader.MAX_INPUT_BYTES + 1])
def test_size_limit_cannot_be_raised_or_disabled(tmp_path, limit):
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(tmp_path / "missing", max_bytes=limit)


def test_caller_can_tighten_input_limit(tmp_path):
    path = write(tmp_path, pickle.dumps(snapshot()))
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(path, max_bytes=1)


def test_isolated_worker_has_no_credentials_or_current_directory_imports(tmp_path, monkeypatch):
    path = write(tmp_path, pickle.dumps(snapshot()))
    original = reader.subprocess.run
    calls = []

    def inspect(args, **kwargs):
        calls.append((args, kwargs))
        return original(args, **kwargs)

    monkeypatch.setenv("NEBIUS_API_KEY", "offline-sentinel")
    monkeypatch.setenv("TAVILY_API_KEY", "offline-sentinel")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    monkeypatch.setattr(reader.subprocess, "run", inspect)
    read_snapshot_input(path)
    args, kwargs = calls[0]
    assert args[:3] == [sys.executable, "-I", "-S"]
    assert kwargs["env"] == {"LANG": "C.UTF-8"}
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["timeout"] == reader.WORKER_TIMEOUT_SECONDS
    assert kwargs["pass_fds"] and not kwargs.get("shell")


@pytest.mark.parametrize("failure", ["timeout", "killed", "invalid_output", "oversize_output"])
def test_worker_failure_is_fail_closed_and_input_descriptor_is_closed(
    tmp_path, monkeypatch, failure
):
    path = write(tmp_path, pickle.dumps(snapshot()))
    seen = []

    def fail(args, **kwargs):
        seen.extend(kwargs["pass_fds"])
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 1)
        if failure == "killed":
            return SimpleNamespace(returncode=-9, stdout=b"", stderr=b"")
        if failure == "oversize_output":
            return SimpleNamespace(returncode=0, stdout=b"x" * 101, stderr=b"")
        return SimpleNamespace(
            returncode=0, stdout=b'{"segments":[],"device_traces":[[]]}', stderr=b""
        )

    monkeypatch.setattr(reader, "MAX_OUTPUT_BYTES", 100)
    monkeypatch.setattr(reader.subprocess, "run", fail)
    with pytest.raises(SnapshotInputError):
        read_snapshot_input(path)
    with pytest.raises(OSError):
        os.fstat(seen[0])


def test_worker_limits_are_installed_before_decoding(monkeypatch, tmp_path):
    import resource

    calls = []
    monkeypatch.setattr(resource, "setrlimit", lambda kind, limits: calls.append((kind, limits)))

    def refuse(_data):
        assert calls == [
            (resource.RLIMIT_AS, (reader.MAX_MEMORY_BYTES, reader.MAX_MEMORY_BYTES)),
            (resource.RLIMIT_CPU, (reader.MAX_CPU_SECONDS, reader.MAX_CPU_SECONDS + 1)),
            (resource.RLIMIT_CORE, (0, 0)),
        ]
        raise SnapshotInputError("test_stop_before_parse")

    monkeypatch.setattr(reader, "_decode_input", refuse)
    path = write(tmp_path, b"x")
    with pytest.raises(SnapshotInputError, match="test_stop_before_parse"):
        reader._worker_main(os.open(path, os.O_RDONLY), reader.MAX_INPUT_BYTES)


def test_frame_filenames_are_data_and_never_read(tmp_path, monkeypatch):
    secret = tmp_path / "secret.py"
    secret.write_text("DO_NOT_READ")
    value = snapshot()
    value["device_traces"][0][1]["frames"][0]["filename"] = str(secret)
    original = Path.read_text

    def forbid(path, *args, **kwargs):
        if path == secret:
            pytest.fail("frame path must not be read")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid)
    result = read_snapshot_input(write(tmp_path, pickle.dumps(value)))
    assert result["device_traces"][0][1]["frames"][0]["filename"] == str(secret)
