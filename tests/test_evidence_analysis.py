"""Allocator replay tests use small native-shaped JSON; no CUDA or pickle."""

from __future__ import annotations

import pytest

from headroom.evidence_analysis import analyze_snapshot, classify_stack

KIB = 1024
MIB = 1024 * KIB


def frame(name="forward", filename="/source/train.py", line=10):
    return {"name": name, "filename": filename, "line": line}


def event(action, address=None, size=None, frames=None, **extra):
    item = {"action": action, **extra}
    if address is not None:
        item["addr"] = address
    if size is not None:
        item["size"] = size
    if action == "alloc":
        item["frames"] = frames if frames is not None else [frame()]
    return item


def segment(address, blocks, device=0):
    result = {
        "device": device,
        "address": address,
        "total_size": sum(b[0] for b in blocks),
        "blocks": [],
    }
    for size, state in blocks:
        result["blocks"].append(
            {"address": address, "size": size, "state": state, "frames": [frame()]}
        )
        address += size
    return result


def analyze(events, segments, peak, reserved=None, *, settings=None, records=None, buckets=200):
    config = {
        "max_split_size": -1,
        "expandable_segments": False,
        "roundup_power2_divisions": {"1": 0},
    }
    config.update(settings or {})
    return analyze_snapshot(
        {"segments": segments, "device_traces": [events], "allocator_settings": config},
        {
            "env": {"device": "cuda", "torch": "2.5.1"},
            "peak_allocated_bytes": peak,
            "peak_reserved_bytes": reserved
            if reserved is not None
            else sum(s["total_size"] for s in segments),
            "step_records": records or [],
        },
        buckets=buckets,
    )


def test_peak_live_set_is_not_the_terminal_live_set():
    a, b = [frame(line=10)], [frame(line=20)]
    output = analyze(
        [
            event("segment_alloc", 0, 2048),
            event("alloc", 0, 1024, a),
            event("alloc", 1024, 1024, b),
            event("free_requested", 0, 1024),
            event("free_completed", 0, 1024),
        ],
        [segment(0, [(1024, "inactive"), (1024, "active_allocated")])],
        2048,
    )
    assert output["header"]["history_complete"]
    assert output["header"]["peak_allocated_bytes"] == 2048
    assert output["header"]["terminal_allocated_bytes"] == 1024
    assert {entry["frames"][0]["line"] for entry in output["peak_composition"]} == {10, 20}
    assert output["peak_event_index"] == 2


def test_requested_scalar_size_is_rounded_to_real_allocator_block():
    output = analyze(
        [event("segment_alloc", 0, 2 * MIB), event("alloc", 0, 4)],
        [segment(0, [(512, "active_allocated"), (2 * MIB - 512, "inactive")])],
        512,
    )
    assert output["header"]["peak_is_exact"]
    assert output["peak_composition"][0]["bytes"] == 512
    assert output["allocation_hot_paths"][0]["bytes"] == 512


def test_large_pool_unsplit_tail_is_counted_in_allocated_bytes():
    requested = 5 * MIB // 2
    output = analyze(
        [event("segment_alloc", 0, 3 * MIB), event("alloc", 0, requested)],
        [segment(0, [(3 * MIB, "active_allocated")])],
        3 * MIB,
    )
    assert output["header"]["peak_is_exact"]
    assert output["peak_composition"][0]["bytes"] == 3 * MIB


def test_max_split_size_changes_physical_block_size():
    output = analyze(
        [event("segment_alloc", 0, 8 * MIB), event("alloc", 0, 3 * MIB)],
        [segment(0, [(8 * MIB, "active_allocated")])],
        8 * MIB,
        settings={"max_split_size": 2 * MIB},
    )
    assert output["header"]["peak_is_exact"]


def test_requested_free_releases_counter_before_pending_block_is_reusable():
    output = analyze(
        [
            event("segment_alloc", 0, 2048),
            event("alloc", 0, 1024),
            event("free_requested", 0, 1024),
            event("oom", size=1536, device_free=0),
        ],
        [segment(0, [(1024, "active_awaiting_free"), (1024, "inactive")])],
        1024,
    )
    assert output["timeline"][2]["allocated_bytes"] == 0
    assert output["header"]["history_complete"]
    assert output["header"]["cached_free_bytes"] == 2048
    assert output["header"]["inactive_free_bytes"] == 1024
    assert output["oom_events"][0]["largest_free_block_bytes"] == 1024
    assert not output["header"]["fragmentation_confirmed"]


def test_full_signature_merges_identical_stacks_and_keeps_other_callers_distinct():
    shared = [frame("forward", line=10), frame("main", line=100)]
    other = [frame("forward", line=10), frame("main", line=200)]
    output = analyze(
        [
            event("segment_alloc", 0, 4096),
            event("alloc", 0, 512, shared),
            event("alloc", 512, 1024, shared),
            event("alloc", 1536, 2048, other),
        ],
        [
            segment(
                0,
                [
                    (512, "active_allocated"),
                    (1024, "active_allocated"),
                    (2048, "active_allocated"),
                    (512, "inactive"),
                ],
            )
        ],
        3584,
    )
    assert len(output["peak_composition"]) == 2
    assert sorted(entry["bytes"] for entry in output["peak_composition"]) == [1536, 2048]
    assert sorted(entry["blocks"] for entry in output["peak_composition"]) == [1, 2]
    assert sum(output["category_bytes"].values()) == 3584


@pytest.mark.parametrize(
    ("frames", "category"),
    [
        ([frame("_init_group", "/opt/torch/optim/adamw.py", 140)], "optimizer_state"),
        ([frame("_multi_tensor_adamw", "/opt/torch/optim/adamw.py", 900)], "temporaries"),
        ([frame("torch::autograd::AccumulateGrad::apply", "??", 0)], "grads"),
        ([frame("_apply", "/opt/torch/nn/modules/module.py", 900)], "params"),
        ([frame("forward", "/source/train.py", 40)], "activations"),
        ([frame("main", "/source/train.py", 40)], "unknown"),
    ],
)
def test_origin_heuristic_distinguishes_adam_state_and_foreach_temporaries(frames, category):
    assert classify_stack(frames) == category


def test_missing_history_never_borrows_terminal_blocks_for_peak_composition():
    output = analyze(
        [event("alloc", 1024, 512)],
        [segment(0, [(1024, "active_allocated"), (512, "active_allocated"), (512, "inactive")])],
        1536,
    )
    assert not output["header"]["history_complete"]
    assert not output["header"]["peak_is_exact"]
    assert output["header"]["recorded_peak_allocated_bytes"] == 1536
    assert output["header"]["peak_allocated_bytes"] == 512
    assert sum(item["bytes"] for item in output["peak_composition"]) == 512
    assert any("differ" in warning for warning in output["header"]["warnings"])


def test_unknown_event_and_counter_mismatch_are_reported():
    output = analyze(
        [
            event("segment_alloc", 0, 1024),
            event("alloc", 0, 512),
            {"action": "future_allocator_action"},
        ],
        [segment(0, [(512, "active_allocated"), (512, "inactive")])],
        1024,
    )
    assert not output["header"]["history_complete"]
    assert output["coverage"]["unknown_actions"] == {"future_allocator_action": 1}
    assert output["header"]["recorded_peak_allocated_bytes"] == 1024
    assert output["header"]["peak_allocated_bytes"] == 512


def test_cache_gap_proxy_alone_is_not_confirmed_fragmentation():
    output = analyze(
        [event("segment_alloc", 0, 2 * 1024**3), event("alloc", 0, 512)],
        [segment(0, [(512, "active_allocated"), (2 * 1024**3 - 512, "inactive")])],
        512,
    )
    assert output["header"]["fragmentation_indicator"] == "high"
    assert not output["header"]["fragmentation_confirmed"]
    assert any("proxy" in warning for warning in output["header"]["warnings"])


@pytest.mark.parametrize(("driver_free", "confirmed"), [(128 * KIB, True), (4 * MIB, False)])
def test_fragmentation_confirmation_requires_observed_oom_and_driver_pressure(
    driver_free, confirmed
):
    output = analyze(
        [
            event("segment_alloc", 0, 2 * MIB),
            event("alloc", 0, 512 * KIB),
            event("segment_alloc", 4 * MIB, 2 * MIB),
            event("alloc", 4 * MIB, 512 * KIB),
            event("oom", size=2 * MIB, device_free=driver_free),
        ],
        [
            segment(0, [(512 * KIB, "active_allocated"), (1536 * KIB, "inactive")]),
            segment(4 * MIB, [(512 * KIB, "active_allocated"), (1536 * KIB, "inactive")]),
        ],
        MIB,
    )
    assert output["header"]["history_complete"]
    assert output["header"]["fragmentation_confirmed"] is confirmed
    assert output["oom_events"][0]["inactive_split_bytes"] == 3 * MIB


def test_adjacent_separate_segments_are_not_invented_as_one_free_block():
    output = analyze(
        [
            event("segment_alloc", 0, 1024),
            event("segment_alloc", 1024, 1024),
            event("oom", size=1536, device_free=0),
        ],
        [segment(0, [(1024, "inactive")]), segment(1024, [(1024, "inactive")])],
        0,
    )
    assert output["oom_events"][0]["largest_free_block_bytes"] == 1024
    assert not output["header"]["fragmentation_confirmed"]


def test_expandable_map_unmap_is_replayed_without_double_reserved_bytes():
    output = analyze(
        [
            event("segment_map", 0, 2048),
            event("segment_map", 2048, 2048),
            event("alloc", 0, 512),
            event("segment_unmap", 2048, 2048),
        ],
        [segment(0, [(512, "active_allocated"), (1536, "inactive")])],
        512,
        reserved=4096,
        settings={"expandable_segments": True},
    )
    assert output["header"]["history_complete"]
    assert output["header"]["peak_reserved_bytes"] == 4096
    assert output["header"]["terminal_reserved_bytes"] == 2048


def test_short_lived_bytes_use_explicit_free_request_lifetime():
    events = [
        event("segment_alloc", 0, 2048),
        event("alloc", 0, 512),
        event("free_requested", 0, 512),
        event("free_completed", 0, 512),
        event("alloc", 0, 1024),
    ]
    events.extend({"action": "snapshot"} for _ in range(40))
    events.extend([event("free_requested", 0, 1024), event("free_completed", 0, 1024)])
    output = analyze(events, [segment(0, [(2048, "inactive")])], 1024)
    assert output["header"]["history_complete"]
    assert output["allocation_hot_paths"][0]["bytes"] == 1536
    assert output["allocation_hot_paths"][0]["short_lived_bytes"] == 512


def test_downsampling_preserves_true_peak_and_oom_and_never_averages_bytes():
    events = [event("segment_alloc", 0, 2048), event("alloc", 0, 1024)]
    events.extend({"action": "snapshot"} for _ in range(50))
    events.append(event("oom", size=4096, device_free=0))
    output = analyze(
        events, [segment(0, [(1024, "active_allocated"), (1024, "inactive")])], 1024, buckets=3
    )
    assert len(output["timeline"]) <= 3
    assert any(point["is_oom"] for point in output["timeline"])
    assert output["peak_event_index"] in {point["event_index"] for point in output["timeline"]}
    assert all(point["allocated_bytes"] in (0, 1024) for point in output["timeline"])


def test_step_boundaries_use_real_timestamps_and_skip_old_records():
    output = analyze(
        [
            event("segment_alloc", 0, 2048, time_us=10),
            event("alloc", 0, 1024, time_us=20),
            event("free_requested", 0, 1024, time_us=30),
            event("free_completed", 0, 1024, time_us=40),
        ],
        [segment(0, [(2048, "inactive")])],
        1024,
        records=[
            {"step": 1, "wall_time_us": 25},
            {"step": 2, "wall_time_us": 40},
            {"step": 3, "elapsed_ms": 10},
        ],
    )
    assert [entry["event_index"] for entry in output["step_boundaries"]] == [1, 3]
    assert any("wall_time_us" in warning for warning in output["header"]["warnings"])


def test_nondefault_unsupported_rounding_cannot_claim_exact_reconstruction():
    output = analyze(
        [event("segment_alloc", 0, 2048), event("alloc", 0, 512)],
        [segment(0, [(512, "active_allocated"), (1536, "inactive")])],
        512,
        settings={"roundup_power2_divisions": {"1": 4}},
    )
    assert not output["header"]["history_complete"]
    assert not output["header"]["peak_is_exact"]
