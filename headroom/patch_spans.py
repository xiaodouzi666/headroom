"""Source SHA plus explicit original line IDs; no inferred or fuzzy source matching.

IDs are metadata, never source text. Exact placement does not establish semantic
correctness: the existing policy, compile, candidate-byte and Lab checks remain.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Collection, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from headroom.patch_edits import (
    MAX_EDITS,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TEXT,
    AnchoredConversion,
    _check_text,
    _read_bytes,
    _source_parts,
    _source_text,
    _unified,
    _utf8,
)
from headroom.verify.policy import safe_relative_path

SCHEMA_NAME = "source_span_edits_v1"
_ID = re.compile(r"L[0-9]{6,8}")
_SHA = re.compile(r"[0-9a-f]{64}")
_ID_LABEL = re.compile(r"^[ \t]*L[0-9]{6,8}(?:[ \t]*[|:]|[ \t]+)")


def _line_id(index: int) -> str:
    return f"L{index + 1:06d}"


class SourceSpanEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(max_length=4096)
    source_sha256: str = Field(min_length=64, max_length=64)
    start_id: str = Field(min_length=7, max_length=9)
    end_id: str = Field(min_length=7, max_length=9)
    new_lines: list[Annotated[str, StringConstraints(max_length=MAX_TEXT)]] = Field(
        max_length=MAX_TEXT
    )

    @field_validator("path")
    @classmethod
    def path_is_safe(cls, value):
        return safe_relative_path(value)

    @field_validator("source_sha256")
    @classmethod
    def hash_is_canonical(cls, value):
        if not _SHA.fullmatch(value):
            raise ValueError("source_sha256 must be 64 lowercase hexadecimal characters")
        return value

    @field_validator("start_id", "end_id")
    @classmethod
    def id_is_canonical(cls, value):
        if not _ID.fullmatch(value):
            raise ValueError("line ID must be copied from the supplied source metadata")
        return value

    @field_validator("new_lines")
    @classmethod
    def physical_lines(cls, lines):
        for line in lines:
            if "\r" in line or "\n" in line:
                raise ValueError("edit line items must exclude CR and LF")
            _check_text(line)
            if _ID_LABEL.match(line):
                raise ValueError("source line IDs are metadata, not editable code")
        return lines


class SourceSpanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, title=SCHEMA_NAME)

    edits: list[SourceSpanEdit] = Field(max_length=MAX_EDITS)
    env_changes: dict[str, str]
    cli_changes: list[Annotated[str, StringConstraints(max_length=1000)]] = Field(max_length=60)
    notes: list[Annotated[str, StringConstraints(max_length=2000)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def bounded_edits(self):
        if len({edit.path for edit in self.edits}) > MAX_FILES:
            raise ValueError("edits may touch at most twenty files")
        lines = [line for edit in self.edits for line in edit.new_lines]
        if (
            sum(len(line) + 1 for line in lines) > MAX_TEXT
            or sum(len(_utf8(line)) + 1 for line in lines) > MAX_TEXT
        ):
            raise ValueError("aggregate edit text exceeds 512000 characters or UTF-8 bytes")
        return self


def source_span_document(source_root: str | Path, path: str) -> dict[str, Any]:
    """Expose exact physical lines and separate IDs, bound to the full original bytes."""
    data = _read_bytes(source_root, path)
    _text, lines, newline, terminal = _source_parts(data)
    return {
        "path": path,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "lines": [{"id": _line_id(index), "text": line} for index, line in enumerate(lines)],
        "newline": newline,
        "terminal_newline": terminal,
        "utf8_bytes": len(data),
    }


def normalize_span_edits(
    proposal: SourceSpanProposal | Mapping[str, Any],
    source_root: str | Path,
    *,
    allowed_source_paths: Collection[str] | None = None,
) -> AnchoredConversion:
    """Resolve inclusive, nonempty original ranges without model-supplied old text.

    All edits use original coordinates simultaneously. Repeated text is unambiguous
    because IDs identify physical lines; existing IDs can still select the wrong
    semantic location, which is not verified by this conversion.
    """
    value = proposal.model_dump() if isinstance(proposal, SourceSpanProposal) else proposal
    proposal = SourceSpanProposal.model_validate(value, strict=True)
    grouped = defaultdict(list)
    for index, edit in enumerate(proposal.edits):
        if allowed_source_paths is not None and edit.path not in allowed_source_paths:
            raise ValueError("edit path was not included in the supplied source context")
        grouped[edit.path].append((index, edit))
    diffs, files = [], []
    for path, edits in sorted(grouped.items()):
        original = _read_bytes(source_root, path)
        before, source_lines, newline, terminal = _source_parts(original)
        source_hash = hashlib.sha256(original).hexdigest()
        catalog = {_line_id(index): index for index in range(len(source_lines))}
        offsets = [0]
        for index, line in enumerate(source_lines):
            ending = newline if index < len(source_lines) - 1 or terminal else ""
            offsets.append(offsets[-1] + len(_utf8(line + ending)))
        spans = []
        for index, edit in edits:
            if edit.source_sha256 != source_hash:
                raise ValueError(f"stale source_sha256 for {path}")
            if edit.start_id not in catalog or edit.end_id not in catalog:
                raise ValueError(f"line ID was not supplied for {path}")
            start, end = catalog[edit.start_id], catalog[edit.end_id] + 1
            if end <= start:
                raise ValueError(f"reversed or empty source span in {path}")
            if source_lines[start:end] == edit.new_lines:
                raise ValueError(f"edit makes no change in {path}")
            spans.append((start, end, index, edit.new_lines))
        spans.sort()
        for previous, following in pairwise(spans):
            if following[0] < previous[1]:
                raise ValueError(f"duplicate or overlapping edits in {path}")
        changed_lines, cursor = [], 0
        for start, end, _index, replacement in spans:
            changed_lines.extend(source_lines[cursor:start])
            changed_lines.extend(replacement)
            cursor = end
        changed_lines.extend(source_lines[cursor:])
        if terminal and not changed_lines:
            raise ValueError("empty candidate cannot preserve the terminal newline")
        if not terminal and changed_lines and changed_lines[-1] == "":
            raise ValueError("empty final line cannot preserve the absent terminal newline")
        expected = _utf8(newline.join(changed_lines) + (newline if terminal else ""))
        if len(expected) > MAX_FILE_BYTES:
            raise ValueError("expected candidate exceeds original file byte limit")
        if expected == original:
            raise ValueError(f"combined edits make no change in {path}")
        diff = _unified(path, before, _source_text(expected))
        if not diff:
            raise ValueError("changed bytes did not produce a unified diff")
        diffs.append(diff)
        files.append(
            {
                "path": path,
                "source_sha256": source_hash,
                "source_bytes": len(original),
                "expected_sha256": hashlib.sha256(expected).hexdigest(),
                "expected_bytes": len(expected),
                "edits": [
                    {
                        "edit_index": index,
                        "start_id": _line_id(start),
                        "end_id": _line_id(end - 1),
                        "start_line": start + 1,
                        "end_line": end,
                        "start_byte": offsets[start],
                        "end_byte": offsets[end],
                        "old_sha256": hashlib.sha256(
                            original[offsets[start] : offsets[end]]
                        ).hexdigest(),
                        "old_bytes": offsets[end] - offsets[start],
                    }
                    for start, end, index, _replacement in spans
                ],
            }
        )
    diff = "".join(diffs)
    if len(diff) > MAX_TEXT or len(_utf8(diff)) > MAX_TEXT:
        raise ValueError("generated diff exceeds 512000 characters or UTF-8 bytes")
    return AnchoredConversion(
        proposal={
            "diff": diff,
            "env_changes": proposal.env_changes.copy(),
            "cli_changes": list(proposal.cli_changes),
            "notes": list(proposal.notes),
        },
        metadata={
            "schema": SCHEMA_NAME,
            "conversion": "exact_original_span_ids_to_unified_diff",
            "context_lines": 3,
            "edit_count": len(proposal.edits),
            "file_count": len(files),
            "diff_sha256": hashlib.sha256(_utf8(diff)).hexdigest(),
            "diff_bytes": len(_utf8(diff)),
            "files": files,
        },
    )
