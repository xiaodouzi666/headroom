"""Optional exact edit provenance for existing rejected-candidate syntax feedback.

No source repair, causal inference, patch application or execution occurs here.
All original feedback is retained; the enclosing old 8 KiB limit is unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json

from headroom.patch_edits import _read_bytes, _source_parts
from headroom.patch_feedback import MAX_SYNTAX_FEEDBACK_BYTES, _text
from headroom.patch_spans import SCHEMA_NAME, SourceSpanProposal, normalize_span_edits
from headroom.verify.policy import _CREDENTIAL_PATTERN

MAX_ORIGIN_CONTEXT_BYTES = 8192
MAX_ORIGIN_FILES = 3
MAX_ORIGINAL_EXCERPT_LINES = 7


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _id(index):
    return f"L{index + 1:06d}"


def _original_excerpt(lines, start, end):
    indices = sorted(
        set(range(max(0, start - 1), min(len(lines), start + 3)))
        | set(range(max(0, end - 2), min(len(lines), end + 1)))
    )[:MAX_ORIGINAL_EXCERPT_LINES]
    return [
        {
            "id": _id(index),
            "text": _text(lines[index], 512),
            "truncated": _text(lines[index], 512) != lines[index],
        }
        for index in indices
    ]


def _map_line(original, edits, candidate_line):
    """Map provenance only; replaced lines cannot identify a unique causal old line."""
    source_cursor = candidate_cursor = 0
    segments, deletions = [], []
    for edit in sorted(edits, key=lambda item: int(item.start_id[1:])):
        start, end = int(edit.start_id[1:]) - 1, int(edit.end_id[1:])
        retained = start - source_cursor
        if retained:
            segments.append(
                (candidate_cursor, candidate_cursor + retained, source_cursor, start, "unchanged")
            )
        candidate_cursor += retained
        replacement_count = len(edit.new_lines)
        if replacement_count:
            segments.append(
                (candidate_cursor, candidate_cursor + replacement_count, start, end, "replacement")
            )
        else:
            deletions.append(
                {
                    "candidate_boundary_line": candidate_cursor + 1,
                    "original_start_id": edit.start_id,
                    "original_end_id": edit.end_id,
                }
            )
        candidate_cursor += replacement_count
        source_cursor = end
    if source_cursor < len(original):
        segments.append(
            (
                candidate_cursor,
                candidate_cursor + len(original) - source_cursor,
                source_cursor,
                len(original),
                "unchanged",
            )
        )
    at = candidate_line - 1
    adjacent = [item for item in deletions if item["candidate_boundary_line"] == candidate_line]
    for first, last, start, end, kind in segments:
        if first <= at < last:
            if kind == "unchanged":
                start = start + at - first
                end = start + 1
            result = {
                "status": "bound",
                "mapping_kind": kind,
                "original_start_id": _id(start),
                "original_end_id": _id(end - 1),
                "nearby_original_lines": _original_excerpt(original, start, end),
                "adjacent_deletions": adjacent,
            }
            if kind == "replacement":
                result["candidate_replacement_start_line"] = first + 1
                result["candidate_replacement_end_line"] = last
                result["line_offset_in_replacement"] = at - first + 1
            return result
    if adjacent:
        # A deleted span has no candidate line. At EOF/boundary we can name only
        # adjacency, not an original line corresponding to the parser location.
        return {
            "status": "bound_boundary_only",
            "mapping_kind": "deletion_boundary",
            "adjacent_deletions": adjacent,
        }
    return {"status": "unavailable", "reason": "candidate_line_has_no_bound_origin"}


def with_original_span_context(
    syntax_feedback, *, original_root, candidate_root, proposal, normalization_metadata
):
    """Add exact origin beside existing syntax data only when the old budget fits.

    A missing optional field means omitted/unavailable. Never remove old
    diagnostics or enlarge their existing enclosing 8 KiB bound to fit this aid.
    """
    if type(syntax_feedback) is not dict or "original_span_context" in syntax_feedback:
        return syntax_feedback
    try:
        original_feedback = copy.deepcopy(syntax_feedback)
        diagnostics = original_feedback.get("diagnostics")
        if type(diagnostics) is not list or not diagnostics:
            return syntax_feedback
        value = proposal.model_dump() if isinstance(proposal, SourceSpanProposal) else proposal
        parsed = SourceSpanProposal.model_validate(value, strict=True)
        if normalization_metadata.get("schema") != SCHEMA_NAME:
            raise ValueError("source-span protocol unavailable")
        files = normalization_metadata["files"]
        if type(files) is not list or len(files) > 20:
            raise ValueError("unbound normalization")
        records = {item["path"]: item for item in files}
        if len(records) != len(files):
            raise ValueError("duplicate file metadata")
        context = {
            "schema": "headroom.original_span_feedback.v1",
            "coordinate_space": "original_source",
            "status": "unavailable",
            "mappings": [],
            "omitted_diagnostic_count": len(diagnostics),
            "source_is_untrusted": True,
            "scope": "Exact edit provenance only; not the cause, a correct next edit range, or permission to repair.",
        }
        seen = set()
        for diagnostic in diagnostics:
            if len(seen) >= MAX_ORIGIN_FILES:
                break
            if type(diagnostic) is not dict or diagnostic.get("status") != "syntax_error":
                continue
            path, row = diagnostic.get("path"), diagnostic.get("line")
            if type(path) is not str or len(path.encode("utf-8")) > 512 or path in seen:
                continue
            if type(row) is not int or row < 1:
                continue
            seen.add(path)
            item = {"path": path, "candidate_line": row, "status": "unavailable"}
            try:
                edits = [edit for edit in parsed.edits if edit.path == path]
                if not edits:
                    raise ValueError("no original edit")
                narrowed = SourceSpanProposal(edits=edits, env_changes={}, cli_changes=[], notes=[])
                rebuilt = normalize_span_edits(
                    narrowed, original_root, allowed_source_paths=(path,)
                )
                binding = rebuilt.metadata["files"][0]
                record = records[path]
                for key in ("source_sha256", "source_bytes", "expected_sha256", "expected_bytes"):
                    if record.get(key) != binding[key]:
                        raise ValueError("normalization binding differs")
                candidate = _read_bytes(candidate_root, path)
                candidate_hash = hashlib.sha256(candidate).hexdigest()
                if (
                    candidate_hash != binding["expected_sha256"]
                    or candidate_hash != diagnostic.get("candidate_sha256")
                    or len(candidate) != binding["expected_bytes"]
                ):
                    raise ValueError("candidate binding differs")
                source = _read_bytes(original_root, path)
                if hashlib.sha256(source).hexdigest() != binding["source_sha256"]:
                    raise ValueError("original source changed")
                text, original_lines, _newline, _terminal = _source_parts(source)
                if _CREDENTIAL_PATTERN.search(text):
                    item.update(status="withheld", reason="credential_like_original_source")
                else:
                    _candidate_text, candidate_lines, _newline, _terminal = _source_parts(candidate)
                    if row > len(candidate_lines) + 1:
                        raise ValueError("candidate row outside captured bytes")
                    item.update(
                        original_sha256=binding["source_sha256"],
                        candidate_sha256=candidate_hash,
                        **_map_line(original_lines, edits, row),
                    )
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                RuntimeError,
                RecursionError,
                OverflowError,
                UnicodeError,
            ):
                item.update(status="unavailable", reason="source_or_candidate_binding_unavailable")
            proposed = copy.deepcopy(context)
            proposed["mappings"].append(item)
            proposed["omitted_diagnostic_count"] -= 1
            statuses = [
                entry["status"] in {"bound", "bound_boundary_only"}
                for entry in proposed["mappings"]
            ]
            proposed["status"] = (
                "bound"
                if all(statuses) and not proposed["omitted_diagnostic_count"]
                else "partial"
                if any(statuses)
                else "unavailable"
            )
            combined = {**original_feedback, "original_span_context": proposed}
            if (
                _size(proposed) > MAX_ORIGIN_CONTEXT_BYTES
                or _size(combined) > MAX_SYNTAX_FEEDBACK_BYTES
            ):
                break
            context = proposed
        if context["mappings"]:
            return {**original_feedback, "original_span_context": context}
        omitted = {"status": "omitted", "reason": "existing_feedback_budget_or_binding_unavailable"}
        combined = {**original_feedback, "original_span_context": omitted}
        return combined if _size(combined) <= MAX_SYNTAX_FEEDBACK_BYTES else syntax_feedback
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RuntimeError,
        RecursionError,
        OverflowError,
        UnicodeError,
    ):
        omitted = {"status": "unavailable", "reason": "source_or_candidate_binding_unavailable"}
        try:
            combined = {**syntax_feedback, "original_span_context": omitted}
            return combined if _size(combined) <= MAX_SYNTAX_FEEDBACK_BYTES else syntax_feedback
        except (ValueError, TypeError, RecursionError, OverflowError, UnicodeError):
            return syntax_feedback
