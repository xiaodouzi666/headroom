"""Lossless snapshot codec and bounded shared-decoding checks; CPU only."""

import copy
import json
import math
from dataclasses import replace

import pytest

from headroom.evidence_analysis import analyze_snapshot
from headroom.lab.snapshot_codec import (
    DEFAULT_LIMITS,
    FORMAT_KEY,
    MAX_SNAPSHOT_BYTES,
    FrozenStack,
    decode_snapshot,
    encode_snapshot,
    read_snapshot_artifact,
)


def frame(line=10, **extra):
    return {"name": "forward", "filename": "/source/train.py", "line": line, **extra}


def native():
    stack = [frame(), frame(20, metadata={"flags": [True, None, -0.0], "frames": {"stack": 9}})]
    return {
        "segments": [
            {
                "device": 0,
                "address": 0,
                "total_size": 2048,
                "blocks": [
                    {"address": 0, "size": 1024, "state": "inactive", "frames": stack},
                    {"address": 1024, "size": 1024, "state": "active_allocated", "frames": stack},
                ],
            }
        ],
        "device_traces": [
            [
                {"action": "segment_alloc", "addr": 0, "size": 2048, "time_us": 1},
                {"action": "alloc", "addr": 0, "size": 1024, "frames": stack, "extra": "keep"},
                {"action": "alloc", "addr": 1024, "size": 1024, "frames": copy.deepcopy(stack)},
                {"action": "free_requested", "addr": 0, "size": 1024},
                {"action": "free_completed", "addr": 0, "size": 1024},
                {"action": "future_native_event", "frames": [], "stream": 7},
            ],
            [],
        ],
        "allocator_settings": {"expandable_segments": False, "max_split_size": -1},
        "future_native_field": {"frames": {"stack": 0}, "other": [1, 1.0, True, "汉字"]},
    }


def test_full_native_roundtrip_analysis_equivalence_and_shared_identity():
    original = native()
    unchanged = copy.deepcopy(original)
    document = encode_snapshot(original)
    restored = decode_snapshot(json.loads(json.dumps(document)))
    assert original == unchanged
    assert restored == original
    assert json.loads(json.dumps(restored)) == original
    assert document["stats"]["frame_count"] == 2
    assert document["stats"]["stack_count"] == 2
    assert document["stats"]["stack_references"] == 5
    stack = restored["device_traces"][0][1]["frames"]
    assert isinstance(stack, FrozenStack)
    assert stack is restored["device_traces"][0][2]["frames"]
    assert stack is restored["segments"][0]["blocks"][0]["frames"]
    assert math.copysign(1, stack[1]["metadata"]["flags"][2]) == -1
    result = {
        "env": {"device": "cuda", "torch": "2.5.1"},
        "peak_allocated_bytes": 2048,
        "peak_reserved_bytes": 2048,
        "step_records": [],
    }
    assert analyze_snapshot(restored, result) == analyze_snapshot(original, result)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda stack: stack.append({}),
        lambda stack: stack.__setitem__(0, {}),
        lambda stack: stack.reverse(),
        lambda stack: stack.__iadd__([{}]),
        lambda stack: stack[0].update({"line": 999}),
        lambda stack: stack[0].__setitem__("line", 999),
        lambda stack: stack[1]["metadata"]["flags"].pop(),
        lambda stack: stack[1]["metadata"].clear(),
    ],
)
def test_shared_stacks_and_nested_frame_values_are_read_only(mutation):
    value = decode_snapshot(encode_snapshot(native()))
    stack = value["device_traces"][0][1]["frames"]
    with pytest.raises(TypeError, match="immutable"):
        mutation(stack)
    assert copy.deepcopy(stack) is stack
    assert value == native()


@pytest.mark.parametrize(
    "frames",
    [None, 1, True, "literal", {"stack": 0}, {"literal": [1]}, [1, {"frames": []}], []],
)
def test_every_frames_field_is_tagged_without_native_marker_collision(frames):
    value = {"frames": frames, FORMAT_KEY: "native field also preserved"}
    assert decode_snapshot(encode_snapshot(value)) == value


def test_equal_python_numbers_retain_distinct_native_json_types():
    value = {
        "segments": [],
        "device_traces": [
            [{"frames": [{"v": 1}, {"v": 1.0}, {"v": True}, {"v": -0.0}, {"v": 0.0}]}]
        ],
    }
    document = encode_snapshot(value)
    assert document["stats"]["frame_count"] == 5
    restored = decode_snapshot(document)["device_traces"][0][0]["frames"]
    assert [type(row["v"]) for row in restored] == [int, float, bool, float, float]
    assert math.copysign(1, restored[3]["v"]) == -1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.update(version=2),
        lambda row: row.update(version=True),
        lambda row: row.update(extra=1),
        lambda row: row.update(frame_table={}),
        lambda row: row.update(stack_table={}),
        lambda row: row.update(snapshot=[]),
        lambda row: row["frame_table"].__setitem__(0, []),
        lambda row: row["stack_table"][0].__setitem__(0, -1),
        lambda row: row["stack_table"][0].__setitem__(0, True),
        lambda row: row["stack_table"][0].__setitem__(0, "0"),
        lambda row: row["stack_table"][0].__setitem__(0, 1000),
        lambda row: row["snapshot"]["device_traces"][0][1].__setitem__("frames", {"stack": -1}),
        lambda row: row["snapshot"]["device_traces"][0][1].__setitem__("frames", {"stack": True}),
        lambda row: row["snapshot"]["device_traces"][0][1].__setitem__("frames", {"stack": 1000}),
        lambda row: row["snapshot"]["device_traces"][0][1].__setitem__(
            "frames", {"stack": 0, "literal": []}
        ),
        lambda row: row["snapshot"]["device_traces"][0][1].__setitem__("frames", []),
        lambda row: row["stats"].__setitem__("expanded_frames", 0),
        lambda row: row["stats"].__setitem__("frame_count", True),
        lambda row: row["frame_table"][0].__setitem__("line", float("nan")),
    ],
)
def test_malformed_or_forged_encoding_is_rejected(mutate):
    document = encode_snapshot(native())
    mutate(document)
    with pytest.raises((TypeError, ValueError)):
        decode_snapshot(document)


@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("max_frames", 1),
        ("max_stacks", 1),
        ("max_stack_depth", 1),
        ("max_stack_entries", 1),
        ("max_references", 4),
        ("max_expanded_frames", 7),
        ("max_expanded_frame_nodes", 1),
        ("max_expanded_frame_bytes", 1),
        ("max_frame_nodes", 1),
        ("max_frame_bytes", 1),
        ("max_table_bytes", 1),
        ("max_payload_nodes", 1),
        ("max_depth", 3),
    ],
)
def test_resource_limits_refuse_instead_of_truncating(field, limit):
    original = native()
    document = encode_snapshot(original)
    limits = replace(DEFAULT_LIMITS, **{field: limit})
    with pytest.raises((ValueError, TypeError)):
        decode_snapshot(document, limits=limits)
    with pytest.raises((ValueError, TypeError)):
        encode_snapshot(original, limits=limits)
    assert original == native()


def test_tiny_reference_document_cannot_expand_without_accounting():
    value = {"device_traces": [[{"frames": [frame()] * 100} for _ in range(30)]], "segments": []}
    document = encode_snapshot(value)
    assert document["stats"]["frame_count"] == document["stats"]["stack_count"] == 1
    assert document["stats"]["expanded_frames"] == 3000
    assert len(json.dumps(document)) < 3000
    with pytest.raises(ValueError, match="expanded_frames"):
        decode_snapshot(document, limits=replace(DEFAULT_LIMITS, max_expanded_frames=2999))


def test_large_repeated_stack_is_compact_without_event_or_frame_loss():
    stack = [frame(i) for i in range(40)]
    value = {
        "segments": [],
        "device_traces": [
            [
                {"action": "alloc", "addr": i * 512, "size": 512, "frames": stack}
                for i in range(2000)
            ]
        ],
    }
    document = encode_snapshot(value)
    assert len(json.dumps(document)) < len(json.dumps(value)) // 10
    restored = decode_snapshot(document)
    assert len(restored["device_traces"][0]) == 2000
    assert restored == value
    assert len({id(event["frames"]) for event in restored["device_traces"][0]}) == 1


def test_loader_native_and_encoded_and_none(tmp_path):
    for index, data in enumerate([native(), encode_snapshot(native()), None]):
        path = tmp_path / f"snapshot-{index}.json"
        path.write_text(json.dumps(data))
        assert read_snapshot_artifact(path) == (native() if data is not None else None)
    assert encode_snapshot(None) is None
    assert decode_snapshot(None) is None
    old = native()
    assert decode_snapshot(old) is old


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '{"v":NaN}', '{"v":1e999}', "[" * 2000])
def test_loader_rejects_ambiguous_or_nonfinite_json(tmp_path, content):
    path = tmp_path / "snapshot.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        read_snapshot_artifact(path)


def test_loader_does_not_raise_file_gate_or_follow_symlinks(tmp_path):
    path = tmp_path / "snapshot.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="512 MiB"):
        read_snapshot_artifact(path, MAX_SNAPSHOT_BYTES + 1)
    with pytest.raises(ValueError, match="size limit"):
        read_snapshot_artifact(path, 1)
    linked = tmp_path / "linked.json"
    linked.symlink_to(path)
    with pytest.raises(OSError):
        read_snapshot_artifact(linked)
    oversized = tmp_path / "old-oversized.json"
    with oversized.open("wb") as handle:
        handle.truncate(MAX_SNAPSHOT_BYTES + 1)
    with pytest.raises(ValueError, match="size limit"):
        read_snapshot_artifact(oversized)
    assert oversized.stat().st_size == MAX_SNAPSHOT_BYTES + 1


def test_frame_budget_is_checked_before_building_oversized_key_or_json():
    frame_value = {"nested": ["x" * 128] * 1000}
    with pytest.raises(ValueError, match="Frame"):
        encode_snapshot({"frames": [frame_value]})


def test_public_reinitialization_does_not_mutate_shared_values():
    value = decode_snapshot(encode_snapshot(native()))
    stack = value["device_traces"][0][1]["frames"]
    stack.__init__([])
    stack[0].__init__({"line": 999})
    stack[1]["metadata"]["flags"].__init__([])
    assert value == native()


def test_legacy_native_unknown_marker_field_is_preserved(tmp_path):
    value = native()
    value[FORMAT_KEY] = "stack-frames"
    path = tmp_path / "native.json"
    path.write_text(json.dumps(value))
    assert read_snapshot_artifact(path) == value
    assert decode_snapshot(value) is value


def test_shared_stack_analysis_serializes_each_immutable_stack_only_once(monkeypatch):
    import headroom.evidence_analysis as analysis

    value = decode_snapshot(encode_snapshot(native()))
    seen = []
    original = analysis.json.dumps

    def counting(item, *args, **kwargs):
        if isinstance(item, FrozenStack):
            seen.append(id(item))
        return original(item, *args, **kwargs)

    monkeypatch.setattr(analysis.json, "dumps", counting)
    analyze_snapshot(value, {"env": {"device": "cuda"}, "peak_allocated_bytes": 2048})
    assert seen
    assert len(seen) == len(set(seen))


def test_real_evidence_and_long_evidence_consume_both_formats_equivalently(tmp_path, monkeypatch):
    import hashlib
    from pathlib import Path

    import headroom.timeline_plot as timeline
    from headroom.acceptance.long_evidence import prepare_long_evidence
    from headroom.evidence import build_evidence

    monkeypatch.setattr(
        timeline, "render_timeline", lambda _, path, **kwargs: Path(path).write_bytes(b"CPU-test")
    )
    bundles = []
    long_packages = []
    for kind, snapshot in [("native", native()), ("encoded", encode_snapshot(native()))]:
        root = tmp_path / kind
        (root / "source").mkdir(parents=True)
        (root / "artifacts").mkdir()
        source = "VALUE = 1\n"
        (root / "source/train.py").write_text(source)
        result = {
            "run_id": "same-capture",
            "status": "completed",
            "capture_complete": True,
            "cleanup_verified": True,
            "env": {"device": "cuda"},
            "peak_allocated_bytes": 2048,
            "peak_reserved_bytes": 2048,
            "step_records": [],
        }
        manifest = {
            "device": "cuda",
            "command": ["python", "-m", "headroom.lab.run_target", "--script", "/source/train.py"],
            "source": {
                "files": {"train.py": {"sha256": hashlib.sha256(source.encode()).hexdigest()}}
            },
        }
        for relative, value in [
            ("result.json", result),
            ("manifest.json", manifest),
            ("artifacts/result.json", result),
            ("artifacts/snapshot.json", snapshot),
        ]:
            (root / relative).write_text(json.dumps(value))
        bundle = build_evidence(root, output_dir=tmp_path / (kind + "-evidence"))
        bundles.append(json.loads(Path(bundle["evidence_json"]).read_text())["analysis"])
        output = tmp_path / (kind + "-long")
        package = prepare_long_evidence(root, output)
        assert package["status"] == "pending"
        assert "decoded-native" in package["record_pointer_basis"]
        long_packages.append(
            ((output / "records.json").read_text(), (output / "evidence.txt").read_text())
        )
    assert bundles[0] == bundles[1]
    assert long_packages[0] == long_packages[1]
