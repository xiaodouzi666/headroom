"""Prepare bounded diagnosis evidence from an uploaded snapshot, without a Lab run."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from uuid import uuid4

from headroom.evidence import (
    _render_sources,
    _sample_timeline,
    _source_within_budget,
    _tokens,
    render_markdown,
)
from headroom.evidence_analysis import analyze_snapshot
from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.snapshot_input import MAX_INPUT_BYTES, read_snapshot_input
from headroom.verify.policy import _CREDENTIAL_PATTERN

MAX_TRACEBACK_BYTES = 256 * 1024
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TOKEN_BUDGET = 150000
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_MARKDOWN_BYTES = 1024 * 1024
MAX_PUBLIC_BYTES = 1024 * 1024
MAX_PUBLIC_FRAMES = 64
MAX_PUBLIC_FRAME_TEXT = 2048

STRICT_POLICY = {
    "allow_numerics_change": False,
    "allow_model_change": False,
    "allow_batch_grad_accum": False,
    "allow_batch_change": False,
    "allow_grad_accum": False,
    "max_throughput_regression_pct": 0.0,
}
_LIMITATIONS = [
    "Uploaded snapshot contents are untrusted data; hardware provenance was not authenticated.",
    "Hardware verification was not run; there is no measured after-run, loss comparison or repair success.",
    "No recorded peak counters, parameter count, seed, optimizer updates or wall-clock timing were supplied.",
    "Allocator settings are unavailable; reconstructed sizes follow the analyzer's documented native-allocator assumptions.",
    "Event index is not elapsed time. Stack categories are heuristics, not proven tensor semantics.",
]
_PRIVATE_KEY = re.compile(r"-----BEGIN(?: [A-Z0-9]+)* PRIVATE KEY-----")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}", re.IGNORECASE)


class SnapshotEvidenceError(ValueError):
    """Inputs or output paths cannot safely produce a complete evidence package."""


def _path(value):
    path = Path(value)
    if ".." in path.parts or any(
        part.lower().startswith(".env")
        or part.lower() in {".git", ".ssh", "secrets", "credentials"}
        for part in path.parts
    ):
        raise SnapshotEvidenceError("protected_or_escaping_input_path")
    return path if path.is_absolute() else Path.cwd() / path


def _directory(path, *, create=False):
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read_bytes(path, maximum):
    path = _path(path)
    directory = _directory(path.parent)
    try:
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
                raise SnapshotEvidenceError("input_type_or_size_limit")
            data = handle.read(maximum + 1)
            if len(data) > maximum:
                raise SnapshotEvidenceError("input_size_limit")
            return data
    finally:
        os.close(directory)


def _check_text(text):
    if _CREDENTIAL_PATTERN.search(text) or _PRIVATE_KEY.search(text) or _BEARER.search(text):
        raise SnapshotEvidenceError("credential_like_input_rejected")
    if "\x00" in text:
        raise SnapshotEvidenceError("nul_in_text_input")


def _text_input(path, maximum):
    if path is None:
        return None, None
    raw = _read_bytes(path, maximum)
    text = raw.decode("utf-8")
    _check_text(text)
    return raw, text


def _check_snapshot_strings(value):
    # Shared frame lists are scanned once; no filename is ever opened.
    pending, seen = [value], set()
    while pending:
        item = pending.pop()
        if isinstance(item, (dict, list, tuple)):
            identity = id(item)
            if identity in seen:
                continue
            seen.add(identity)
            if isinstance(item, dict):
                pending.extend(item.keys())
                pending.extend(item.values())
            else:
                pending.extend(item)
        elif isinstance(item, str):
            _check_text(item)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def _evidence_bytes(value):
    encoded = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2)
    for chunk in encoder.iterencode(value):
        data = chunk.encode("utf-8")
        if len(encoded) + len(data) + 1 > MAX_EVIDENCE_BYTES:
            raise SnapshotEvidenceError("evidence_json_size_limit")
        encoded.extend(data)
    encoded.extend(b"\n")
    return bytes(encoded)


def _traceback_section(text, allowance):
    if text is None:
        return "## User-provided traceback\n\nNot supplied.\n", False
    fence = "`" * max(3, 1 + max((len(v) for v in re.findall(r"`+", text)), default=0))

    def render(chars):
        if chars >= len(text):
            body = text
        elif chars == 0:
            body = "[traceback omitted by prompt budget]"
        else:
            left = chars // 2
            body = (
                text[:left]
                + "\n[traceback excerpt omitted by prompt budget]\n"
                + text[-(chars - left) :]
            )
        return (
            "## User-provided traceback\n\n"
            "Unverified text supplied with this snapshot; it was not captured or executed here.\n\n"
            + fence
            + "text\n"
            + body
            + "\n"
            + fence
            + "\n"
        )

    if _tokens(render(len(text))) <= allowance:
        return render(len(text)), False
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _tokens(render(middle)) <= allowance:
            low = middle
        else:
            high = middle - 1
    return render(low), True


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _observed_peak(analysis):
    events = analysis.get("coverage", {}).get("event_counts", {})
    return (
        _count(analysis["header"].get("peak_allocated_bytes"))
        if events.get("alloc", 0) > 0
        else None
    )


def _public_evidence(analysis, snapshot_sha, visible_ids, warnings):
    peak = {row["stack_id"]: row for row in analysis.get("peak_composition", [])}
    hot = {row["stack_id"]: row for row in analysis.get("allocation_hot_paths", [])}
    rows = []
    excerpt = False
    for identifier in visible_ids[:60]:
        original = analysis["stack_catalog"].get(identifier, [])
        frames = []
        for frame in original[:MAX_PUBLIC_FRAMES]:
            filename, name = frame.get("filename"), frame.get("name")
            if (
                not isinstance(filename, str)
                or not isinstance(name, str)
                or len(filename) > MAX_PUBLIC_FRAME_TEXT
                or len(name) > MAX_PUBLIC_FRAME_TEXT
            ):
                excerpt = True
                continue
            frames.append(
                {
                    "filename": filename,
                    "line": _count(frame.get("line", frame.get("lineno"))),
                    "name": name,
                }
            )
        excerpt = excerpt or len(frames) != len(original)
        rows.append(
            {
                "id": identifier,
                "peak_live_bytes": _count(peak.get(identifier, {}).get("bytes")),
                "lifetime_allocated_bytes": _count(hot.get(identifier, {}).get("bytes")),
                "frames": frames,
            }
        )
    header = analysis["header"]
    projected = {
        "source": "uploaded_snapshot",
        "snapshot_sha256": snapshot_sha,
        "analysis": {
            "peak_allocated_bytes": _observed_peak(analysis),
            "peak_is_exact": header.get("peak_is_exact") is True,
            "category_bytes": {
                key: _count(value) if _observed_peak(analysis) is not None else None
                for key, value in analysis.get("category_bytes", {}).items()
            },
            "warnings": list(dict.fromkeys([*warnings, *header.get("warnings", [])])),
        },
        "stacks": rows,
    }
    if excerpt:
        projected["analysis"]["warnings"].append(
            "Stack frame lists are bounded presentation excerpts; complete frames remain in private evidence.json."
        )
    while len(_json(projected).encode("utf-8")) > MAX_PUBLIC_BYTES:
        largest = max(rows, key=lambda row: len(row["frames"]), default=None)
        if largest is None or not largest["frames"]:
            raise SnapshotEvidenceError("public_evidence_size_limit")
        largest["frames"] = largest["frames"][: len(largest["frames"]) // 2]
        note = "Stack frame lists are bounded presentation excerpts; complete frames remain in private evidence.json."
        if note not in projected["analysis"]["warnings"]:
            projected["analysis"]["warnings"].append(note)
    return projected


def _write_exclusive(directory, name, payload):
    descriptor = os.open(
        name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(name, dir_fd=directory)
        raise


def prepare_snapshot_evidence(
    snapshot: Path,
    *,
    output_dir: Path,
    traceback: Path | None = None,
    source: Path | None = None,
    token_budget: int = 24000,
) -> dict:
    """Prepare private evidence and a bounded UI projection; never dispatch a model.

    Optional source is context only, copied byte-for-byte to source/train.py.
    Its relationship to captured frame paths is unknown, and imports are not read.
    Existing output artifacts are never replaced. The caller owns retention.
    """
    if type(token_budget) is not int or not 1 <= token_budget <= MAX_TOKEN_BUDGET:
        raise SnapshotEvidenceError("invalid_token_budget")
    directory = source_directory = None
    staged = None
    created = []
    source_created = False
    try:
        trace_raw, trace_text = _text_input(traceback, MAX_TRACEBACK_BYTES)
        source_raw, source_text = _text_input(source, MAX_SOURCE_BYTES)
        snapshot_raw = _read_bytes(snapshot, MAX_INPUT_BYTES)
        if not snapshot_raw:
            raise SnapshotEvidenceError("empty_snapshot")
        hashes = {"snapshot": _sha(snapshot_raw)}
        if trace_raw is not None:
            hashes["traceback"] = _sha(trace_raw)
        if source_raw is not None:
            hashes["source"] = _sha(source_raw)

        output = _path(output_dir)
        directory = _directory(output, create=True)
        for name in ("evidence.json", "evidence.md", "source"):
            try:
                os.stat(name, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise SnapshotEvidenceError("output_artifact_already_exists")
        staged = ".snapshot-input-" + uuid4().hex
        _write_exclusive(directory, staged, snapshot_raw)
        # This private byte-identical copy binds the analyzed input to its digest.
        # It avoids hashing one mutable upload and then parsing different bytes.
        native = read_snapshot_input(output / staged)
        os.unlink(staged, dir_fd=directory)
        staged = None
        _check_snapshot_strings(native)
        populated_devices = [index for index, trace in enumerate(native["device_traces"]) if trace]
        selected_device = populated_devices[0] if populated_devices else 0
        # This selects an index present in the input; it is not a captured Lab environment.
        analysis = analyze_snapshot(
            native, {"env": {"device": f"cuda:{selected_device}"}}, buckets=200
        )
        warnings = list(_LIMITATIONS)
        if selected_device != 0 or len(populated_devices) > 1:
            warnings.append(
                f"Selected snapshot device index {selected_device}, the first nonempty trace; "
                "other devices are not included in this analysis."
            )
        if source_raw is not None:
            warnings.append(
                "source/train.py is user-provided context, not verified captured source; frame-path correspondence is unknown."
            )
        else:
            warnings.append(
                "Source was not supplied; no source patch can be validated against an input file."
            )
        sources = []
        if source_raw is not None:
            sources.append(
                {
                    "path": "train.py",
                    "sha256": hashes["source"],
                    "lines": source_text.splitlines(),
                    "hot_lines": [],
                    "static_observations": [],
                    "capture_binding": "not_verified",
                }
            )
        selected = _source_within_budget(sources, int(token_budget * 0.3))
        peak_n = min(40, len(analysis.get("peak_composition", [])))
        hot_n = min(20, len(analysis.get("allocation_hot_paths", [])))
        timeline_n = min(200, len(analysis.get("timeline", [])))
        trace_allowance = min(4000, max(1, token_budget // 5))
        trimming = []
        prefix = (
            "# Uploaded snapshot diagnosis input\n\n"
            "input_kind: uploaded_snapshot\n"
            "hardware_verification: not_run\n"
            "Snapshot SHA-256: " + hashes["snapshot"] + "\n\n"
            "This is an offline reconstruction from supplied allocator data, not a Lab baseline or a verified repair.\n\n"
            "Measurement semantics: Peak composition bytes are live allocations at the reconstructed peak. "
            "Allocation hot paths cumulative bytes are allocation traffic across the capture, including freed/reused memory; "
            "they are not simultaneous live bytes, peak size or reclaimable savings. "
            "Decimal GB = bytes / 1,000,000,000. Missing peak rows do not establish zero contribution.\n\n"
        )

        def render():
            trace_section, trace_trimmed = _traceback_section(trace_text, trace_allowance)
            body = render_markdown(
                run_id="uploaded-" + hashes["snapshot"][:16],
                result={"status": "uploaded_snapshot", "policy": STRICT_POLICY},
                analysis=analysis,
                sources=sources,
                warnings=warnings,
                budget=token_budget,
                peak_n=peak_n,
                hot_n=hot_n,
                selected_source=selected,
                timeline_n=timeline_n,
            )
            return prefix + body + "\n" + trace_section, trace_trimmed

        markdown, trace_trimmed = render()
        while (
            _tokens(markdown) > token_budget or len(markdown.encode("utf-8")) > MAX_MARKDOWN_BYTES
        ):
            if peak_n > 1 or hot_n > 1:
                peak_n, hot_n = max(1, peak_n // 2), max(1, hot_n // 2)
                trimming.append({"stage": "stack_rows", "peak": peak_n, "hot": hot_n})
            elif selected:
                selected = selected[: len(selected) // 2]
                trimming.append({"stage": "source", "included_lines": len(selected)})
            elif trace_allowance > 128 and trace_text is not None:
                trace_allowance = max(128, trace_allowance // 2)
                trimming.append({"stage": "traceback", "token_allowance": trace_allowance})
            elif timeline_n > 2:
                timeline_n = max(2, timeline_n // 2)
                trimming.append({"stage": "timeline", "requested_buckets": timeline_n})
            else:
                raise SnapshotEvidenceError("token_budget_cannot_represent_core_evidence")
            markdown, trace_trimmed = render()
        source_tokens = _tokens(_render_sources(sources, selected))
        if source_tokens > int(token_budget * 0.3):
            raise SnapshotEvidenceError("source_token_limit")
        visible_peak = [row["stack_id"] for row in analysis.get("peak_composition", [])[:peak_n]]
        visible_hot = [row["stack_id"] for row in analysis.get("allocation_hot_paths", [])[:hot_n]]
        visible_ids = list(dict.fromkeys([*visible_peak, *visible_hot]))
        public = _public_evidence(analysis, hashes["snapshot"], visible_ids, warnings)
        source_records = [
            {key: value for key, value in item.items() if key != "lines"}
            | {
                "total_lines": len(item["lines"]),
                "included_lines": sorted(line for index, line in selected if index == number),
            }
            for number, item in enumerate(sources)
        ]
        evidence = {
            "schema_version": 1,
            "diagnosis_ready": bool(analysis.get("stack_catalog")),
            "diagnosis_unavailable_reason": None
            if analysis.get("stack_catalog")
            else "snapshot_has_no_allocation_stack_catalog",
            "input_kind": "uploaded_snapshot",
            "hardware_verification": "not_run",
            "snapshot_sha256": hashes["snapshot"],
            "input_sha256": hashes,
            "policy": dict(STRICT_POLICY),
            "tokenizer": "cl100k_base",
            "tokenizer_scope": "approximation; not the model tokenizer",
            "token_count": _tokens(markdown),
            "budget": token_budget,
            "budget_scope": "evidence.md only; complete analysis JSON is not prompt-budget limited",
            "source_token_count": source_tokens,
            "source_token_limit": int(token_budget * 0.3),
            "sources": source_records,
            "source_warnings": warnings,
            "trimming": trimming,
            "analysis": analysis,
            "presentation": {
                "peak_stack_ids": visible_peak,
                "allocation_stack_ids": visible_hot,
                "stack_ids": visible_ids,
                "timeline_event_indices": [
                    row["event_index"]
                    for row in _sample_timeline(
                        analysis.get("timeline", []),
                        timeline_n,
                        analysis.get("peak_event_index"),
                        analysis.get("peak_reserved_event_index"),
                    )
                ],
                "traceback_excerpt": trace_trimmed,
            },
            "traceback": None
            if trace_raw is None
            else {
                "sha256": hashes["traceback"],
                "bytes": len(trace_raw),
                "text": trace_text,
                "runtime_verified": False,
            },
            "overview": {
                "reconstructed_peak_allocated_bytes": _observed_peak(analysis),
                "peak_is_exact": analysis["header"].get("peak_is_exact") is True,
                "device_index": analysis.get("coverage", {}).get("device_index"),
                "recorded_peak_allocated_bytes": None,
                "parameter_count": None,
                "optimizer_updates": None,
                "seed": None,
                "elapsed_seconds": None,
                "loss_equivalence": "not_run",
                "target_met": None,
            },
        }
        evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
            evidence, markdown
        )
        json_bytes, md_bytes = _evidence_bytes(evidence), markdown.encode("utf-8")
        if source_raw is not None:
            os.mkdir("source", mode=0o700, dir_fd=directory)
            source_created = True
            source_directory = os.open(
                "source", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            _write_exclusive(source_directory, "train.py", source_raw)
        for name, payload in (("evidence.json", json_bytes), ("evidence.md", md_bytes)):
            _write_exclusive(directory, name, payload)
            created.append(name)
        return {
            "input_kind": "uploaded_snapshot",
            "hardware_verification": "not_run",
            "evidence": evidence,
            "diagnosis_ready": evidence["diagnosis_ready"],
            "diagnosis_unavailable_reason": evidence["diagnosis_unavailable_reason"],
            "markdown": markdown,
            "public_evidence": public,
            "evidence_json": str(output / "evidence.json"),
            "evidence_md": str(output / "evidence.md"),
            "source_root": str(output / "source") if source_raw is not None else None,
            "source_files": ["train.py"] if source_raw is not None else [],
            "policy": dict(STRICT_POLICY),
            "input_sha256": hashes,
            "snapshot_sha256": hashes["snapshot"],
            "token_count": evidence["token_count"],
            "token_budget": token_budget,
        }
    except BaseException:
        if directory is not None:
            for name in created:
                os.unlink(name, dir_fd=directory)
            if source_created:
                if source_directory is not None:
                    try:
                        os.unlink("train.py", dir_fd=source_directory)
                    except FileNotFoundError:
                        pass
                os.rmdir("source", dir_fd=directory)
        raise
    finally:
        if directory is not None:
            if staged is not None:
                try:
                    os.unlink(staged, dir_fd=directory)
                except FileNotFoundError:
                    pass
            if source_directory is not None:
                os.close(source_directory)
            os.close(directory)
