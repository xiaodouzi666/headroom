"""Replay native allocator JSON without loading pickle or inventing peak stacks."""

from __future__ import annotations

import bisect
import hashlib
import json
from collections import Counter
from typing import Any

CATEGORIES = (
    "params",
    "grads",
    "optimizer_state",
    "activations",
    "temporaries",
    "cache",
    "unknown",
)
SHORT_LIVED_EVENTS = 32


class _Warnings:
    def __init__(self) -> None:
        self.items: dict[str, tuple[str, int]] = {}
        self.incomplete = False

    def add(self, code: str, message: str, *, incomplete: bool = False) -> None:
        previous = self.items.get(code)
        self.items[code] = (previous[0], previous[1] + 1) if previous else (message, 1)
        self.incomplete |= incomplete

    def render(self) -> list[str]:
        return [
            f"{text} (occurrences={count})" if count > 1 else text
            for text, count in self.items.values()
        ]


def _integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def classify_stack(frames: list[dict[str, Any]]) -> str:
    """Conservative origin heuristic; allocation lifetime is reported separately."""
    names = "\n".join(str(frame.get("name", "")) for frame in frames).lower()
    paths = [str(frame.get("filename", "")).replace("\\", "/").lower() for frame in frames]
    # Adam(W) moment initialization is persistent state; its update temporaries are not.
    if any(
        str(frame.get("name", "")) == "_init_group"
        and str(frame.get("filename", ""))
        .replace("\\", "/")
        .endswith(("/optim/adam.py", "/optim/adamw.py"))
        for frame in frames
    ):
        return "optimizer_state"
    if "accumulategrad" in names or "accumulate_grad" in names:
        return "grads"
    if any("/optim/" in path for path in paths):
        return "temporaries"
    if any(
        str(frame.get("name", "")) == "_apply"
        and str(frame.get("filename", "")).replace("\\", "/").endswith("/nn/modules/module.py")
        for frame in frames
    ) or any(path.endswith(("/nn/parameter.py", "/nn/init.py")) for path in paths):
        return "params"
    if any(token in names for token in ("allocate_kv_cache", "init_kv_cache", "allocate_cache")):
        return "cache"
    if "backward" in names or "autograd::engine::evaluate_function" in names:
        return "temporaries"
    if any(str(frame.get("name", "")) == "forward" for frame in frames):
        return "activations"
    return "unknown"


def _representative(frames: list[dict[str, Any]]) -> str:
    selected = []
    for frame in frames:
        filename, name = str(frame.get("filename", "")), str(frame.get("name", ""))
        user = (
            filename.endswith(".py")
            and (
                filename.startswith("/source/")
                or not filename.startswith(("/usr/", "/opt/", "/runtime/", "<"))
            )
            and "/site-packages/" not in filename
        )
        key_library = filename.endswith(".py") and any(
            token in name.lower() for token in ("backward", "autograd", "optimizer")
        )
        key_library |= name.startswith(
            (
                "torch::autograd::AccumulateGrad::",
                "torch::autograd::Engine::",
                "torch::autograd::generated::",
            )
        )
        key_library |= name == "_init_group" and "/optim/" in filename
        key_library |= (
            name in ("__call__", "_call_impl", "_wrapped_call_impl") and "/nn/" in filename
        )
        if user or key_library:
            selected.append(frame)
    if not selected:
        selected = frames[-5:]
    return "\n".join(
        f"{frame.get('filename', '?')}:{frame.get('line', '?')} in {frame.get('name', '?')}"
        for frame in selected
    )


class _Ranges:
    """Mapped segment ranges; distinct cudaMalloc segments must not be coalesced."""

    def __init__(self, warnings: _Warnings) -> None:
        self.ranges: list[tuple[int, int, bool]] = []
        self.warnings = warnings
        self.total = 0

    @property
    def size(self) -> int:
        return self.total

    def add(self, address: int, size: int, expandable: bool) -> None:
        end = address + size
        if any(address < old_end and end > old_start for old_start, old_end, _ in self.ranges):
            self.warnings.add(
                "segment_overlap",
                "Mapped segment events overlap; history is ambiguous.",
                incomplete=True,
            )
            return
        self.ranges.append((address, end, expandable))
        self.total += size
        self.ranges.sort()
        merged: list[tuple[int, int, bool]] = []
        for start, stop, is_expandable in self.ranges:
            if merged and is_expandable and merged[-1][2] and merged[-1][1] == start:
                merged[-1] = (merged[-1][0], stop, True)
            else:
                merged.append((start, stop, is_expandable))
        self.ranges = merged

    def remove(self, address: int, size: int) -> None:
        end, removed = address + size, 0
        remaining = []
        for start, stop, expandable in self.ranges:
            left, right = max(start, address), min(stop, end)
            if left >= right:
                remaining.append((start, stop, expandable))
                continue
            removed += right - left
            if start < left:
                remaining.append((start, left, expandable))
            if right < stop:
                remaining.append((right, stop, expandable))
        self.ranges = remaining
        self.total -= removed
        if removed != size:
            self.warnings.add(
                "unknown_segment_free",
                "Segment release has no complete preceding mapped range.",
                incomplete=True,
            )

    def allocation_size(
        self,
        address: int,
        requested: int,
        addresses: list[int],
        occupied: dict[int, dict[str, Any]],
        max_split_size: int | None,
        expandable_segments: bool,
    ) -> int:
        # PyTorch 2.5 ALLOC/FREE trace sizes are requested bytes, while allocator
        # counters and segment block.size include rounding and unsplit slack.
        rounded = max(512, ((requested + 511) // 512) * 512)
        segment = next((item for item in self.ranges if item[0] <= address < item[1]), None)
        if segment is None:
            self.warnings.add(
                "allocation_without_segment",
                "Allocation has no preceding mapped segment; block size is only estimated.",
                incomplete=True,
            )
            return rounded
        begin, end, _ = segment
        index = bisect.bisect_left(addresses, address)
        hole_start = begin
        if index > 0 and addresses[index - 1] >= begin:
            left = addresses[index - 1]
            hole_start = left + occupied[left]["size"]
        hole_end = addresses[index] if index < len(addresses) and addresses[index] < end else end
        if address != hole_start or hole_end - address < rounded:
            self.warnings.add(
                "allocation_hole_mismatch",
                "Allocation address/size does not match a reconstructed free block; block size is estimated.",
                incomplete=True,
            )
            return rounded
        available = hole_end - address
        remaining = available - rounded
        split = (
            remaining >= 512
            if rounded <= 1048576 or expandable_segments
            else ((max_split_size is None or rounded < max_split_size) and remaining > 1048576)
        )
        return rounded if split else available

    def holes(self, blocks: dict[int, dict[str, Any]]) -> tuple[int, int, int]:
        """Return all inactive bytes, largest gap, and bytes in partly occupied segments."""
        occupied = sorted((address, address + block["size"]) for address, block in blocks.items())
        total, largest, split_bytes = 0, 0, 0
        for start, end, _ in self.ranges:
            cursor, gaps, has_live = start, [], False
            for left, right in occupied:
                if right <= start:
                    continue
                if left >= end:
                    break
                has_live = True
                if left > cursor:
                    gaps.append(left - cursor)
                cursor = max(cursor, min(end, right))
            if cursor < end:
                gaps.append(end - cursor)
            total += sum(gaps)
            largest = max([largest, *gaps])
            if has_live:
                split_bytes += sum(gaps)
        return total, largest, split_bytes


def _terminal_state(segments: list[Any], device: int, warnings: _Warnings) -> dict[str, Any]:
    live, pending = {}, {}
    reserved, inactive, largest, splits = 0, 0, 0, 0
    for segment in segments:
        if not isinstance(segment, dict) or segment.get("device", 0) != device:
            continue
        if not _integer(segment.get("total_size")) or not _integer(segment.get("address")):
            warnings.add(
                "terminal_segment_invalid",
                "Terminal segment has invalid size/address.",
                incomplete=True,
            )
            continue
        reserved += segment["total_size"]
        cursor, block_total, segment_free = segment["address"], 0, 0
        blocks = segment.get("blocks", [])
        if not isinstance(blocks, list):
            warnings.add(
                "terminal_blocks_invalid",
                "Terminal segment blocks are not a list.",
                incomplete=True,
            )
            continue
        for block in blocks:
            if not isinstance(block, dict) or not _integer(block.get("size")):
                warnings.add(
                    "terminal_block_invalid", "Terminal block has invalid size.", incomplete=True
                )
                continue
            address, size = block.get("address", cursor), block["size"]
            if not _integer(address):
                warnings.add(
                    "terminal_block_address", "Terminal block address is invalid.", incomplete=True
                )
                continue
            state = block.get("state")
            if state == "active_allocated":
                live[address] = size
            elif state == "active_awaiting_free":
                pending[address] = size
            elif state == "inactive":
                inactive += size
                segment_free += size
                largest = max(largest, size)
            else:
                warnings.add(
                    "terminal_block_state", "Unknown terminal block state.", incomplete=True
                )
            block_total += size
            cursor = address + size
        if block_total != segment["total_size"]:
            warnings.add(
                "terminal_block_total",
                "Terminal block sizes do not equal segment total_size.",
                incomplete=True,
            )
        if segment_free < segment["total_size"]:
            splits += segment_free
    return {
        "live": live,
        "pending": pending,
        "allocated": sum(live.values()),
        "reserved": reserved,
        "inactive": inactive,
        "largest": largest,
        "split_free": splits,
        "pending_bytes": sum(pending.values()),
    }


def _timeline_sample(
    points: list[dict[str, Any]], buckets: int, peak: int, reserved_peak: int, warnings: _Warnings
) -> list[dict[str, Any]]:
    if len(points) <= buckets:
        return points
    oom_indexes = [i for i, point in enumerate(points) if point["is_oom"]]
    priority = list(dict.fromkeys([*oom_indexes, peak, reserved_peak, 0, len(points) - 1]))
    priority = [index for index in priority if index >= 0]
    if len(priority) > buckets:
        warnings.add(
            "timeline_required_overflow",
            "Timeline limit cannot retain every OOM/peak/boundary; full OOM summaries remain available.",
        )
        if oom_indexes and buckets == 1:
            return [points[oom_indexes[-1]]]
        priority = priority[:buckets]
    selected = set(priority)
    spare = buckets - len(selected)
    # Select a true peak inside each remaining event bucket, never averaged bytes.
    for bucket in range(spare):
        start = bucket * len(points) // spare
        stop = (bucket + 1) * len(points) // spare
        candidate = max(range(start, stop), key=lambda i: points[i]["allocated_bytes"])
        selected.add(candidate)
    if len(selected) < buckets:
        for i in range(buckets):
            selected.add(i * (len(points) - 1) // max(1, buckets - 1))
            if len(selected) >= buckets:
                break
    return [points[index] for index in sorted(selected)]


def _step_boundaries(
    trace: list[Any], result: dict[str, Any], warnings: _Warnings
) -> list[dict[str, Any]]:
    records = result.get("step_records", [])
    if not records:
        return []
    timed = [
        (event["time_us"], index)
        for index, event in enumerate(trace)
        if isinstance(event, dict) and _integer(event.get("time_us"))
    ]
    if not timed or any(timed[i][0] < timed[i - 1][0] for i in range(1, len(timed))):
        warnings.add(
            "step_time_trace",
            "Step alignment unavailable: trace timestamps are absent or not monotonic.",
        )
        return []
    times = [item[0] for item in timed]
    boundaries = []
    for record in records:
        if not isinstance(record, dict) or not _integer(record.get("wall_time_us")):
            warnings.add(
                "step_time_missing", "Step alignment unavailable for a record without wall_time_us."
            )
            continue
        index = bisect.bisect_right(times, record["wall_time_us"]) - 1
        if index < 0:
            warnings.add(
                "step_before_trace",
                "Optimizer boundary predates the first retained allocator event.",
            )
            continue
        boundaries.append(
            {
                "step": record.get("step"),
                "event_index": timed[index][1],
                "wall_time_us": record["wall_time_us"],
                "alignment": "last allocator event before optimizer hook",
            }
        )
    return boundaries


def analyze_snapshot(snapshot: dict, result: dict, buckets: int = 200) -> dict:
    """Analyze one CUDA device. Incomplete histories are labeled, never filled in."""
    if not isinstance(snapshot, dict) or not isinstance(result, dict):
        raise TypeError("snapshot and result must be dictionaries")
    if type(buckets) is not int or buckets < 1:
        raise ValueError("buckets must be a positive integer")
    traces, segments = snapshot.get("device_traces"), snapshot.get("segments")
    if not isinstance(traces, list) or not isinstance(segments, list):
        raise TypeError("Native snapshot requires device_traces and segments lists")
    device_value = result.get("env", {}).get("device", "cuda")
    device = (
        int(device_value.split(":", 1)[1])
        if isinstance(device_value, str) and ":" in device_value
        else 0
    )
    if device < 0 or device >= len(traces) or not isinstance(traces[device], list):
        raise ValueError("Selected device has no native trace list")
    trace = traces[device]
    warnings = _Warnings()
    terminal = _terminal_state(segments, device, warnings)
    other_devices = [i for i, events in enumerate(traces) if i != device and events]
    if other_devices:
        warnings.add(
            "other_devices",
            f"Only device {device} is analyzed; other devices have trace events: {other_devices}.",
        )
    if len(trace) >= 200_000:
        warnings.add(
            "ring_capacity",
            "Trace reaches the configured 200000-event ring capacity; an earlier prefix may be missing.",
            incomplete=True,
        )
    if not trace:
        warnings.add(
            "empty_history",
            "Allocator history is empty; no peak composition can be reconstructed.",
            incomplete=True,
        )
    settings = snapshot.get("allocator_settings", {})
    if not isinstance(settings, dict):
        settings = {}
    max_split_setting = settings.get("max_split_size", -1)
    max_split_size = (
        max_split_setting if _integer(max_split_setting) and max_split_setting > 0 else None
    )
    expandable_segments = bool(settings.get("expandable_segments", False))
    divisions = settings.get("roundup_power2_divisions", {})
    if isinstance(divisions, dict) and any(value != 0 for value in divisions.values()):
        warnings.add(
            "unsupported_rounding",
            "Nondefault power-of-two rounding is not reconstructed; block sizes are estimates.",
            incomplete=True,
        )
    allocator_conf = str(settings.get("PYTORCH_CUDA_ALLOC_CONF", ""))
    if "cudaMallocAsync" in allocator_conf:
        warnings.add(
            "unsupported_allocator",
            "cudaMallocAsync block policy is not reconstructed by the native allocator replay.",
            incomplete=True,
        )
    ranges = _Ranges(warnings)
    active: dict[int, dict[str, Any]] = {}
    pending: dict[int, dict[str, Any]] = {}
    occupied: dict[int, dict[str, Any]] = {}
    occupied_addresses: list[int] = []
    catalog: dict[str, list[dict[str, Any]]] = {}
    signatures: dict[str, str] = {}
    categories: dict[str, str] = {}
    hot: dict[str, dict[str, Any]] = {}
    allocations: dict[int, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    unknown_events: Counter[str] = Counter()
    points, ooms = [], []
    allocated = peak_allocated = peak_reserved = 0
    peak_index = reserved_peak_index = -1
    missing_frames = 0

    def stack_id_for(event: dict[str, Any]) -> str:
        nonlocal missing_frames
        frames = event.get("frames", [])
        if not isinstance(frames, list) or any(not isinstance(frame, dict) for frame in frames):
            frames = []
        if not frames:
            missing_frames += 1
        signature = json.dumps(frames, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if signature not in signatures:
            digest = hashlib.sha256(signature.encode()).hexdigest()
            stack_id = "stk_" + digest[:16]
            if stack_id in catalog:
                stack_id = "stk_" + digest
            signatures[signature] = stack_id
            catalog[stack_id] = frames
            categories[stack_id] = classify_stack(frames)
            hot[stack_id] = {
                "stack_id": stack_id,
                "bytes": 0,
                "allocations": 0,
                "frames": frames,
                "short_lived_bytes": 0,
            }
        return signatures[signature]

    for index, event in enumerate(trace):
        if not isinstance(event, dict):
            warnings.add(
                "malformed_event", "An allocator event is not a dictionary.", incomplete=True
            )
            event = {}
        action = event.get("action", "<missing>")
        action = action if isinstance(action, str) else "<invalid>"
        counts[action] += 1
        address, size = event.get("addr"), event.get("size")
        valid_range = _integer(address) and _integer(size)
        if (
            action
            in (
                "alloc",
                "free_requested",
                "free_completed",
                "segment_alloc",
                "segment_free",
                "segment_map",
                "segment_unmap",
            )
            and not valid_range
        ):
            warnings.add(
                "event_range_invalid",
                "An allocator event has invalid address/size.",
                incomplete=True,
            )
        elif action == "alloc":
            if address in active or address in pending:
                warnings.add(
                    "allocation_overlap",
                    "Allocation reuses a block without a complete free sequence.",
                    incomplete=True,
                )
                if address in active:
                    allocated -= active.pop(address)["size"]
                pending.pop(address, None)
                occupied.pop(address, None)
                old_index = bisect.bisect_left(occupied_addresses, address)
                if old_index < len(occupied_addresses) and occupied_addresses[old_index] == address:
                    occupied_addresses.pop(old_index)
            stack_id = stack_id_for(event)
            block_size = ranges.allocation_size(
                address, size, occupied_addresses, occupied, max_split_size, expandable_segments
            )
            block = {
                "size": block_size,
                "requested_size": size,
                "stack_id": stack_id,
                "event_index": index,
            }
            active[address] = block
            occupied[address] = block
            bisect.insort(occupied_addresses, address)
            allocations[index] = block
            allocated += block_size
            hot[stack_id]["bytes"] += block_size
            hot[stack_id]["allocations"] += 1
        elif action == "free_requested":
            block = active.pop(address, None)
            if block is None:
                warnings.add(
                    "unknown_free_requested",
                    "free_requested has no preceding live allocation; history is incomplete.",
                    incomplete=True,
                )
                pending.setdefault(address, {"size": size, "stack_id": None, "event_index": None})
            else:
                allocated -= block["size"]
                if size != block["requested_size"]:
                    warnings.add(
                        "free_size_mismatch",
                        "Free size differs from its recorded allocation.",
                        incomplete=True,
                    )
                pending[address] = block
                if index - block["event_index"] <= SHORT_LIVED_EVENTS:
                    hot[block["stack_id"]]["short_lived_bytes"] += block["size"]
        elif action == "free_completed":
            block = pending.pop(address, None)
            if block is None:
                warnings.add(
                    "unknown_free_completed",
                    "free_completed has no preceding free_requested event.",
                    incomplete=True,
                )
                block = active.pop(address, None)
                if block is not None:
                    allocated -= block["size"]
            if block is not None and block.get("requested_size", block["size"]) != size:
                warnings.add(
                    "completed_free_size",
                    "Completed free size differs from its pending block.",
                    incomplete=True,
                )
            occupied.pop(address, None)
            completed_index = bisect.bisect_left(occupied_addresses, address)
            if (
                completed_index < len(occupied_addresses)
                and occupied_addresses[completed_index] == address
            ):
                occupied_addresses.pop(completed_index)
        elif action in ("segment_alloc", "segment_map"):
            ranges.add(address, size, action == "segment_map")
        elif action in ("segment_free", "segment_unmap"):
            if any(
                address < start + block["size"] and address + size > start
                for start, block in {**active, **pending}.items()
            ):
                warnings.add(
                    "release_live_segment",
                    "Segment release overlaps a live/pending block.",
                    incomplete=True,
                )
            ranges.remove(address, size)
        elif action == "oom":
            free, largest, split_free = ranges.holes({**active, **pending})
            requested = size if _integer(size) else None
            driver_free = event.get("device_free") if _integer(event.get("device_free")) else None
            ooms.append(
                {
                    "event_index": index,
                    "requested_bytes": requested,
                    "device_free_bytes": driver_free,
                    "allocated_bytes": allocated,
                    "reserved_bytes": ranges.size,
                    "cached_free_bytes": ranges.size - allocated,
                    "inactive_free_bytes": free,
                    "largest_free_block_bytes": largest,
                    "inactive_split_bytes": split_free,
                    "pending_free_bytes": sum(block["size"] for block in pending.values()),
                    "fragmentation_confirmed": False,
                }
            )
        elif action != "snapshot":
            unknown_events[action] += 1
            warnings.add(
                "unknown_actions",
                "Unknown allocator actions were retained in coverage but not interpreted.",
                incomplete=True,
            )
        reserved = ranges.size
        if allocated > peak_allocated:
            peak_allocated, peak_index = allocated, index
        if reserved > peak_reserved:
            peak_reserved, reserved_peak_index = reserved, index
        point = {
            "event_index": index,
            "allocated_bytes": allocated,
            "reserved_bytes": reserved,
            "is_oom": action == "oom",
        }
        if _integer(event.get("time_us")):
            point["time_us"] = event["time_us"]
        points.append(point)

    if allocated != terminal["allocated"]:
        warnings.add(
            "terminal_alloc_mismatch",
            f"Replayed terminal allocated bytes ({allocated}) differ from snapshot segments ({terminal['allocated']}).",
            incomplete=True,
        )
    if ranges.size != terminal["reserved"]:
        warnings.add(
            "terminal_reserved_mismatch",
            f"Replayed terminal reserved bytes ({ranges.size}) differ from snapshot segments ({terminal['reserved']}).",
            incomplete=True,
        )
    if {address: block["size"] for address, block in active.items()} != terminal["live"]:
        warnings.add(
            "terminal_live_mismatch",
            "Replayed live block addresses/sizes differ from terminal segments.",
            incomplete=True,
        )
    if {address: block["size"] for address, block in pending.items()} != terminal["pending"]:
        warnings.add(
            "terminal_pending_mismatch",
            "Replayed pending-free blocks differ from terminal segments.",
            incomplete=True,
        )
    recorded_alloc = result.get("peak_allocated_bytes")
    recorded_reserved = result.get("peak_reserved_bytes")
    for name, recorded, replayed in (
        ("allocated", recorded_alloc, peak_allocated),
        ("reserved", recorded_reserved, peak_reserved),
    ):
        if not _integer(recorded):
            warnings.add(
                "counter_missing_" + name,
                f"Exact recorded peak {name} counter is unavailable; replay cannot be cross-checked.",
            )
        elif recorded != replayed:
            warnings.add(
                "counter_mismatch_" + name,
                f"Replayed peak {name} bytes ({replayed}) differ from recorded counter ({recorded}); composition describes only the reconstructed peak.",
                incomplete=True,
            )
    if missing_frames:
        warnings.add(
            "frames_missing",
            f"{missing_frames} allocations lack usable frames; their origin remains unknown.",
        )
    # A second replay obtains the actual live set at peak without O(n^2) snapshots.
    peak_blocks: dict[int, dict[str, Any]] = {}
    for index, event in enumerate(trace[: peak_index + 1]):
        if not isinstance(event, dict):
            continue
        if index in allocations:
            peak_blocks[event["addr"]] = allocations[index]
        elif event.get("action") in ("free_requested", "free_completed"):
            peak_blocks.pop(event.get("addr"), None)
    composition_by_stack: dict[str, dict[str, Any]] = {}
    category_bytes = dict.fromkeys(CATEGORIES, 0)
    for block in peak_blocks.values():
        stack_id = block["stack_id"]
        if stack_id not in composition_by_stack:
            composition_by_stack[stack_id] = {
                "stack_id": stack_id,
                "category": categories[stack_id],
                "bytes": 0,
                "blocks": 0,
                "frames": catalog[stack_id],
                "representative_stack": _representative(catalog[stack_id]),
            }
        composition_by_stack[stack_id]["bytes"] += block["size"]
        composition_by_stack[stack_id]["blocks"] += 1
        category_bytes[categories[stack_id]] += block["size"]
    composition = sorted(
        composition_by_stack.values(), key=lambda item: (-item["bytes"], item["stack_id"])
    )
    cached = terminal["reserved"] - terminal["allocated"]
    if cached >= 1_000_000_000:
        warnings.add(
            "fragmentation_proxy",
            "reserved - allocated >= 1 GB is a high cache-gap proxy; it does not by itself prove harmful fragmentation.",
        )
    history_complete = not warnings.incomplete
    for oom in ooms:
        request, driver_free = oom["requested_bytes"], oom["device_free_bytes"]
        oom["fragmentation_confirmed"] = bool(
            history_complete
            and request is not None
            and request > 0
            and driver_free is not None
            and driver_free < request
            and oom["inactive_split_bytes"] >= request
            and oom["largest_free_block_bytes"] < request
        )
    boundaries = _step_boundaries(trace, result, warnings)
    timeline = _timeline_sample(points, buckets, peak_index, reserved_peak_index, warnings)
    fallback_oom = result.get("oom") or {}
    requested = ooms[-1]["requested_bytes"] if ooms else fallback_oom.get("requested_bytes")
    if not _integer(requested):
        requested = None
    return {
        "header": {
            "peak_allocated_bytes": peak_allocated,
            "peak_reserved_bytes": peak_reserved,
            "recorded_peak_allocated_bytes": recorded_alloc if _integer(recorded_alloc) else None,
            "recorded_peak_reserved_bytes": recorded_reserved
            if _integer(recorded_reserved)
            else None,
            "terminal_allocated_bytes": terminal["allocated"],
            "terminal_reserved_bytes": terminal["reserved"],
            "replayed_terminal_allocated_bytes": allocated,
            "replayed_terminal_reserved_bytes": ranges.size,
            "cached_free_bytes": cached,
            "inactive_free_bytes": terminal["inactive"],
            "pending_free_bytes": terminal["pending_bytes"],
            "largest_free_block_bytes": terminal["largest"],
            "oom_requested_bytes": requested,
            "fragmentation_indicator": "high" if cached >= 1_000_000_000 else "low",
            "fragmentation_confirmed": any(oom["fragmentation_confirmed"] for oom in ooms),
            "fragmentation_evidence_rule": "Complete history with OOM, driver free < request, inactive split bytes >= request and largest inactive block < request; not proof of the sole cause.",
            "history_complete": history_complete,
            "peak_is_exact": history_complete
            and _integer(recorded_alloc)
            and recorded_alloc == peak_allocated,
            "warnings": warnings.render(),
        },
        "timeline": timeline,
        "peak_composition": composition[:40],
        "peak_composition_all_stacks": len(composition),
        "peak_composition_omitted_bytes": sum(item["bytes"] for item in composition[40:]),
        "allocation_hot_paths": sorted(
            hot.values(), key=lambda item: (-item["bytes"], item["stack_id"])
        )[:20],
        "stack_catalog": catalog,
        "peak_event_index": peak_index,
        "peak_reserved_event_index": reserved_peak_index,
        "oom_events": ooms,
        "category_bytes": category_bytes,
        "step_boundaries": boundaries,
        "coverage": {
            "device_index": device,
            "trace_events_total": len(trace),
            "timeline_points": len(timeline),
            "event_counts": dict(counts),
            "unknown_event_count": sum(unknown_events.values()),
            "unknown_actions": dict(unknown_events.most_common(20)),
            "allocations_missing_frames": missing_frames,
            "unique_allocation_stacks": len(catalog),
            "peak_live_blocks": len(peak_blocks),
            "peak_composition_covered_bytes": sum(category_bytes.values()),
            "short_lived_threshold_events": SHORT_LIVED_EVENTS,
            "short_lived_definition": "alloc to free_requested, measured in allocator event distance",
            "timeline_sampling": "Native event points; mandatory OOM/global peaks plus per-bucket maxima",
            "category_method": "Heuristic allocation-origin classes, not a proof of tensor semantics",
            "allocation_size_basis": "PyTorch native requested-size traces plus 512-byte rounding and address-based block splitting; checked against terminal blocks and peak counters",
        },
    }
