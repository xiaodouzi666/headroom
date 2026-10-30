"""Versioned lossless allocator stack interning, with bounded shared decoding."""

from __future__ import annotations

import json
import math
import os
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_SNAPSHOT_BYTES = 512 * 1024 * 1024
FORMAT_KEY = "__headroom_snapshot__"
FORMAT = "stack-frames"
VERSION = 1


@dataclass(frozen=True)
class CodecLimits:
    max_frames: int = 131_072
    max_stacks: int = 65_536
    max_stack_depth: int = 512
    max_stack_entries: int = 2_000_000
    max_references: int = 2_000_000
    max_expanded_frames: int = 64_000_000
    max_expanded_frame_nodes: int = 256_000_000
    max_expanded_frame_bytes: int = 8 * 1024**3
    max_frame_nodes: int = 4_096
    max_frame_bytes: int = 65_536
    max_table_bytes: int = 64 * 1024**2
    max_payload_nodes: int = 8_000_000
    max_depth: int = 128

    def __post_init__(self):
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ValueError("Codec limits must be positive integers")


DEFAULT_LIMITS = CodecLimits()


class _FrozenList(list):
    __slots__ = ()

    def __new__(cls, values=()):
        instance = list.__new__(cls)
        list.__init__(instance, values)
        return instance

    def __init__(self, values=()):
        # Re-initialization through the public instance method must not mutate it.
        pass

    def _immutable(self, *args, **kwargs):
        raise TypeError("Decoded shared snapshot values are immutable")

    __setitem__ = __delitem__ = append = extend = insert = pop = remove = clear = _immutable
    reverse = sort = __iadd__ = __imul__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


class FrozenStack(_FrozenList):
    """A shared read-only list; native JSON/list consumers retain their interfaces."""

    __slots__ = ()


class _FrozenDict(dict):
    __slots__ = ()

    def __new__(cls, values=()):
        instance = dict.__new__(cls)
        dict.__init__(instance, values)
        return instance

    def __init__(self, values=()):
        pass

    def _immutable(self, *args, **kwargs):
        raise TypeError("Decoded shared snapshot values are immutable")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        return self


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict((key, _freeze(item)) for key, item in value.items())
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _native_key(value, limits, depth=0, state=None):
    """Typed immutable key preserves scalar types, object order, and nested values."""
    if depth > limits.max_depth:
        raise ValueError("Snapshot nesting exceeds codec limit")
    kind = type(value)
    state = [0, 0] if state is None else state
    state[0] += 1 + (len(value) if kind is dict else 0)
    if state[0] > limits.max_frame_nodes:
        raise ValueError("Frame node count exceeds codec limit")
    state[1] += len(value) if kind is str else 0
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("Snapshot object keys must be strings")
        state[1] += sum(len(key) for key in value)
    if state[1] > limits.max_frame_bytes:
        raise ValueError("Frame byte size exceeds codec limit")
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("Snapshot object keys must be strings")
        children = [
            (key, _native_key(item, limits, depth + 1, state)) for key, item in value.items()
        ]
        count = 1 + sum(1 + child[1] for _, child in children)
        deepest = max((1 + child[2] for _, child in children), default=0)
        key = ("object", tuple((name, child[0]) for name, child in children))
    elif kind in (list, tuple):
        children = [_native_key(item, limits, depth + 1, state) for item in value]
        count = 1 + sum(child[1] for child in children)
        deepest = max((1 + child[2] for child in children), default=0)
        key = ("array", tuple(child[0] for child in children))
    elif kind in (type(None), bool, int, str):
        key, count, deepest = (kind.__name__, value), 1, 0
    elif kind is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite snapshot scalar")
        key, count, deepest = ("float", value.hex()), 1, 0
    else:
        raise TypeError("Unsupported snapshot value type")
    if count > limits.max_frame_nodes:
        raise ValueError("Frame node count exceeds codec limit")
    return key, count, deepest


def _from_key(key):
    kind, value = key
    if kind == "object":
        return {name: _from_key(item) for name, item in value}
    if kind == "array":
        return [_from_key(item) for item in value]
    if kind == "float":
        return float.fromhex(value)
    return value


class _Tables:
    def __init__(self, limits):
        self.limits = limits
        self.frames = []
        self.frame_costs = []
        self.stacks = []
        self.stack_costs = []
        self.stats = {
            "frame_count": 0,
            "stack_count": 0,
            "stack_entries": 0,
            "max_stack_depth": 0,
            "stack_references": 0,
            "expanded_frames": 0,
            "expanded_frame_nodes": 0,
            "expanded_frame_bytes": 0,
            "frame_table_bytes": 0,
            "payload_nodes": 0,
        }

    def add_frame(self, value, key=None):
        if type(value) is not dict:
            raise TypeError("Frame table entries must be native objects")
        if len(self.frames) >= self.limits.max_frames:
            raise ValueError("Frame table count exceeds codec limit")
        key, nodes, depth = key or _native_key(value, self.limits)
        normalized = _from_key(key)
        size = len(_json(normalized).encode("utf-8"))
        if size > self.limits.max_frame_bytes:
            raise ValueError("Frame byte size exceeds codec limit")
        total = self.stats["frame_table_bytes"] + size
        if total > self.limits.max_table_bytes:
            raise ValueError("Frame table byte size exceeds codec limit")
        self.frames.append(normalized)
        self.frame_costs.append((nodes, size, depth))
        self.stats["frame_count"] += 1
        self.stats["frame_table_bytes"] = total
        return len(self.frames) - 1

    def add_stack(self, references):
        if type(references) is not list:
            raise TypeError("Stack table entries must be arrays")
        if len(self.stacks) >= self.limits.max_stacks:
            raise ValueError("Stack table count exceeds codec limit")
        if len(references) > self.limits.max_stack_depth:
            raise ValueError("Stack depth exceeds codec limit")
        entries = self.stats["stack_entries"] + len(references)
        if entries > self.limits.max_stack_entries:
            raise ValueError("Stack table entries exceed codec limit")
        costs = []
        for reference in references:
            if type(reference) is not int or not 0 <= reference < len(self.frames):
                raise ValueError("Invalid frame reference")
            costs.append(self.frame_costs[reference])
        self.stacks.append(references)
        self.stack_costs.append(
            (
                sum(row[0] for row in costs),
                sum(row[1] for row in costs),
                max((row[2] for row in costs), default=0),
            )
        )
        self.stats["stack_count"] += 1
        self.stats["stack_entries"] = entries
        self.stats["max_stack_depth"] = max(self.stats["max_stack_depth"], len(references))
        return len(self.stacks) - 1

    def reference(self, index, depth):
        if type(index) is not int or not 0 <= index < len(self.stacks):
            raise ValueError("Invalid stack reference")
        frames = len(self.stacks[index])
        nodes, size, nested_depth = self.stack_costs[index]
        if frames and depth + 1 + nested_depth > self.limits.max_depth:
            raise ValueError("Expanded stack nesting exceeds codec limit")
        for field, increment, maximum in (
            ("stack_references", 1, self.limits.max_references),
            ("expanded_frames", frames, self.limits.max_expanded_frames),
            ("expanded_frame_nodes", nodes, self.limits.max_expanded_frame_nodes),
            ("expanded_frame_bytes", size, self.limits.max_expanded_frame_bytes),
        ):
            self.stats[field] += increment
            if self.stats[field] > maximum:
                raise ValueError(f"{field} exceeds codec limit")

    def node(self, depth):
        if depth > self.limits.max_depth:
            raise ValueError("Snapshot nesting exceeds codec limit")
        self.stats["payload_nodes"] += 1
        if self.stats["payload_nodes"] > self.limits.max_payload_nodes:
            raise ValueError("Snapshot payload nodes exceed codec limit")


def encode_snapshot(snapshot, *, limits=DEFAULT_LIMITS):
    """Return a lossless v1 envelope, without touching its native input or pickle."""
    if snapshot is None:
        return None
    if type(snapshot) is not dict:
        raise TypeError("CUDA snapshot must be a native object")
    tables = _Tables(limits)
    frames_by_value, stacks_by_value = {}, {}
    # Capture graphs share native frame/stack objects. These per-call identity
    # caches retain their objects, avoiding id reuse and bounded by table limits.
    # The input, like the original walker, must remain stable during encoding.
    frame_objects, stack_objects = {}, {}

    def frame_field(value, depth):
        if type(value) in (list, tuple) and all(type(frame) is dict for frame in value):
            tables.node(depth)
            if len(value) > limits.max_stack_depth:
                raise ValueError("Stack depth exceeds codec limit")
            cached_stack = stack_objects.get(id(value))
            if cached_stack is not None and cached_stack[0] is value:
                index = cached_stack[1]
            else:
                ids = []
                for frame in value:
                    cached_frame = frame_objects.get(id(frame))
                    if cached_frame is not None and cached_frame[0] is frame:
                        frame_index = cached_frame[1]
                    else:
                        key = _native_key(frame, limits)
                        if key[0] not in frames_by_value:
                            frames_by_value[key[0]] = tables.add_frame(frame, key)
                        frame_index = frames_by_value[key[0]]
                        if len(frame_objects) < limits.max_frames:
                            frame_objects[id(frame)] = (frame, frame_index)
                    ids.append(frame_index)
                stack_key = tuple(ids)
                if stack_key not in stacks_by_value:
                    stacks_by_value[stack_key] = tables.add_stack(ids)
                index = stacks_by_value[stack_key]
                if len(stack_objects) < limits.max_stacks:
                    stack_objects[id(value)] = (value, index)
            tables.reference(index, depth)
            return {"stack": index}
        # Every frames field is tagged, including non-stack native values.
        # Thus an original {"stack": 0} is data, never confused with a reference.
        return {"literal": walk(value, depth)}

    def walk(value, depth=0):
        tables.node(depth)
        kind = type(value)
        if kind is dict:
            if any(type(key) is not str for key in value):
                raise TypeError("Snapshot object keys must be strings")
            return {
                key: frame_field(item, depth + 1) if key == "frames" else walk(item, depth + 1)
                for key, item in value.items()
            }
        if kind in (list, tuple):
            return [walk(item, depth + 1) for item in value]
        if kind in (type(None), bool, int, str):
            return value
        if kind is float and math.isfinite(value):
            return value
        raise TypeError("Unsupported or nonfinite snapshot value")

    body = walk(snapshot)
    return {
        FORMAT_KEY: FORMAT,
        "version": VERSION,
        "frame_table": tables.frames,
        "stack_table": tables.stacks,
        "snapshot": body,
        "stats": tables.stats,
    }


def decode_snapshot(document, *, limits=DEFAULT_LIMITS):
    """Decode a validated envelope; legacy native JSON retains its original shape."""
    if not isinstance(document, dict) or FORMAT_KEY not in document:
        return document
    # The discriminator alone can be an unknown field in an old native capture.
    # The reserved envelope signature also needs table/payload structure fields.
    if not (
        "frame_table" in document
        or "stack_table" in document
        or {"version", "snapshot", "stats"} <= set(document)
    ):
        return document
    required = {FORMAT_KEY, "version", "frame_table", "stack_table", "snapshot", "stats"}
    if (
        type(document) is not dict
        or set(document) != required
        or document[FORMAT_KEY] != FORMAT
        or type(document["version"]) is not int
        or document["version"] != VERSION
    ):
        raise ValueError("Unsupported snapshot encoding envelope or version")
    if type(document["frame_table"]) is not list or type(document["stack_table"]) is not list:
        raise TypeError("Snapshot tables must be arrays")
    if type(document["snapshot"]) is not dict:
        raise TypeError("Encoded snapshot payload must be an object")
    if (
        len(document["frame_table"]) > limits.max_frames
        or len(document["stack_table"]) > limits.max_stacks
    ):
        raise ValueError("Snapshot table count exceeds codec limit")
    tables = _Tables(limits)
    for frame in document["frame_table"]:
        tables.add_frame(frame)
    for stack in document["stack_table"]:
        tables.add_stack(stack)
    frozen_frames = [_freeze(frame) for frame in tables.frames]
    shared_stacks = [
        FrozenStack(frozen_frames[index] for index in stack) for stack in tables.stacks
    ]

    def frame_field(value, depth):
        if type(value) is not dict:
            raise ValueError("Encoded frames field requires exactly one tag")
        if set(value) == {"stack"}:
            tables.node(depth)
            index = value["stack"]
            tables.reference(index, depth)
            return shared_stacks[index]
        if set(value) == {"literal"}:
            return walk(value["literal"], depth)
        raise ValueError("Invalid encoded frames tag")

    def walk(value, depth=0):
        tables.node(depth)
        kind = type(value)
        if kind is dict:
            if any(type(key) is not str for key in value):
                raise TypeError("Snapshot object keys must be strings")
            return {
                key: frame_field(item, depth + 1) if key == "frames" else walk(item, depth + 1)
                for key, item in value.items()
            }
        if kind is list:
            return [walk(item, depth + 1) for item in value]
        if kind in (type(None), bool, int, str):
            return value
        if kind is float and math.isfinite(value):
            return value
        raise TypeError("Unsupported or nonfinite snapshot value")

    result = walk(document["snapshot"])
    stats = document["stats"]
    if (
        type(stats) is not dict
        or set(stats) != set(tables.stats)
        or any(type(value) is not int or value < 0 for value in stats.values())
        or stats != tables.stats
    ):
        raise ValueError("Snapshot codec statistics mismatch")
    return result


def read_snapshot_artifact(
    path: str | Path, max_bytes=MAX_SNAPSHOT_BYTES, *, limits=DEFAULT_LIMITS
):
    """Bounded regular-file read, strict JSON parse, then shared decode; never pickle."""
    if type(max_bytes) is not int or not 0 < max_bytes <= MAX_SNAPSHOT_BYTES:
        raise ValueError("Snapshot read limit cannot exceed 512 MiB")

    def reject_constant(value):
        raise ValueError("Nonfinite snapshot JSON constant")

    def finite_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("Nonfinite snapshot JSON number")
        return parsed

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate snapshot JSON key")
            result[key] = value
        return result

    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("Snapshot must be a regular JSON file within the size limit")
        data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Snapshot exceeds its bounded read limit")
    try:
        document = json.loads(
            data,
            parse_constant=reject_constant,
            parse_float=finite_float,
            object_pairs_hook=unique_object,
        )
    except RecursionError as error:
        raise ValueError("Snapshot JSON nesting exceeds parser limit") from error
    return decode_snapshot(document, limits=limits)
