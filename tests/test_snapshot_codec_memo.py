"""Per-call encoding memoization preserves values, limits and reference accounting."""

import copy
import json
from dataclasses import replace

import pytest

from headroom.lab import snapshot_codec as codec


def shared_capture():
    frame = {
        "filename": "/source/train.py",
        "name": "forward",
        "line": 7,
        "extra": {"typed": [True, 1, 1.0, -0.0, None], "frames": {"stack": 2}},
    }
    stack = [frame, frame]
    return {
        "segments": [],
        "device_traces": [
            [
                {"action": "alloc", "addr": i, "size": 4, "frames": stack if i % 2 else list(stack)}
                for i in range(200)
            ]
        ],
    }


def test_identity_memo_preserves_exact_envelope_for_shared_and_unshared_graphs(monkeypatch):
    source = shared_capture()
    original = copy.deepcopy(source)
    baseline_shape = json.loads(json.dumps(source))
    independent = codec.encode_snapshot(baseline_shape)
    calls = []
    native_key = codec._native_key

    def count(value, limits, depth=0, state=None):
        if depth == 0:
            calls.append(id(value))
        return native_key(value, limits, depth, state)

    monkeypatch.setattr(codec, "_native_key", count)
    encoded = codec.encode_snapshot(source)
    assert calls == [id(source["device_traces"][0][0]["frames"][0])]
    assert encoded == independent
    assert json.dumps(encoded) == json.dumps(independent)
    assert source == original
    assert codec.decode_snapshot(encoded) == source
    assert encoded["stats"]["expanded_frames"] == 400
    assert encoded["stats"]["stack_references"] == 200


@pytest.mark.parametrize(
    "field, cap",
    [
        ("max_references", 199),
        ("max_expanded_frames", 399),
        ("max_expanded_frame_nodes", 1),
        ("max_expanded_frame_bytes", 1),
    ],
)
def test_shared_cache_hits_still_enforce_every_expanded_limit(field, cap):
    value = shared_capture()
    before = copy.deepcopy(value)
    with pytest.raises(ValueError, match="exceeds codec limit"):
        codec.encode_snapshot(value, limits=replace(codec.DEFAULT_LIMITS, **{field: cap}))
    assert value == before


def test_cache_is_per_call_and_does_not_hide_changes_between_calls():
    value = shared_capture()
    first = codec.encode_snapshot(value)
    value["device_traces"][0][0]["frames"][0]["line"] = 99
    second = codec.encode_snapshot(value)
    assert first != second
    assert first["frame_table"][0]["line"] == 7
    assert second["frame_table"][0]["line"] == 99
    assert codec.decode_snapshot(second) == value


def test_identity_cache_capacity_is_only_optimization_not_new_rejection_gate():
    value = {
        "segments": [],
        "device_traces": [[{"frames": [{"name": "same"}]} for _ in range(200)]],
    }
    # Many different objects may have the same accepted value. A full cache must
    # fall back to value interning, without raising or bypassing actual limits.
    encoded = codec.encode_snapshot(
        value, limits=replace(codec.DEFAULT_LIMITS, max_frames=1, max_stacks=1)
    )
    assert encoded["stats"]["frame_count"] == encoded["stats"]["stack_count"] == 1
    assert encoded["stats"]["stack_references"] == 200
    assert codec.decode_snapshot(encoded) == value
