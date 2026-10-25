"""Deterministic, source-bound edits; this module never applies or executes a patch.

The caller retains the original path/policy/compile/Lab gates. A successful
conversion proves exact text placement and expected bytes, not program safety.
The caller controls source selection and the separate 128 KiB prompt budget.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import stat
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
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

from headroom.verify.policy import safe_relative_path

SCHEMA_NAME = "source_anchored_edits_v1"
MAX_TEXT = 512000
MAX_FILES = 20
MAX_EDITS = 200
MAX_FILE_BYTES = 2 * 1024 * 1024
_LABEL = re.compile(r"(?m)^[ \t]*[0-9]{4,}: ")
_SHA = re.compile(r"[0-9a-f]{64}")


def _utf8(value: str) -> bytes:
    try:
        return value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError("source/edit text must be valid UTF-8") from error


def _check_text(value: str) -> str:
    if "\x00" in value or "\r" in value.replace("\r\n", ""):
        raise ValueError("NUL and standalone CR are not supported")
    if len(value) > MAX_TEXT or len(_utf8(value)) > MAX_TEXT:
        raise ValueError("edit text exceeds 512000 characters or UTF-8 bytes")
    if _LABEL.search(value):
        raise ValueError("source display line-number labels are not editable source")
    return value


class SourceAnchoredEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(max_length=4096)
    source_sha256: str = Field(min_length=64, max_length=64)
    old_lines: list[Annotated[str, StringConstraints(max_length=MAX_TEXT)]] = Field(
        min_length=1, max_length=MAX_TEXT
    )
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

    @field_validator("old_lines", "new_lines")
    @classmethod
    def physical_lines(cls, lines):
        for line in lines:
            if "\r" in line or "\n" in line:
                raise ValueError("edit line items must exclude CR and LF")
            _check_text(line)
        return lines

    @model_validator(mode="after")
    def changed(self):
        if self.old_lines == self.new_lines:
            raise ValueError("edit makes no change")
        return self


class SourceAnchoredProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, title=SCHEMA_NAME)

    edits: list[SourceAnchoredEdit] = Field(max_length=MAX_EDITS)
    env_changes: dict[str, str]
    cli_changes: list[Annotated[str, StringConstraints(max_length=1000)]] = Field(max_length=60)
    notes: list[Annotated[str, StringConstraints(max_length=2000)]] = Field(
        default_factory=list, max_length=20
    )

    @model_validator(mode="after")
    def bounded_edits(self):
        if len({edit.path for edit in self.edits}) > MAX_FILES:
            raise ValueError("edits may touch at most twenty files")
        lines = [line for edit in self.edits for line in (*edit.old_lines, *edit.new_lines)]
        if (
            sum(len(line) + 1 for line in lines) > MAX_TEXT
            or sum(len(_utf8(line)) + 1 for line in lines) > MAX_TEXT
        ):
            raise ValueError("aggregate edit text exceeds 512000 characters or UTF-8 bytes")
        return self


@dataclass(frozen=True)
class AnchoredConversion:
    proposal: dict[str, Any]
    metadata: dict[str, Any]


def _read_bytes(source_root: str | Path, path: str) -> bytes:
    """Read an existing bounded regular file without following any path component."""
    name = safe_relative_path(path, source_root)
    root = Path(source_root)
    if root.is_symlink():
        raise ValueError("source root must not be a symbolic link")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = name.split("/")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                raise ValueError("source must be an existing bounded regular file")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ValueError("source exceeds file byte limit")
            after = os.fstat(fd)
            if (
                info.st_size != after.st_size
                or info.st_mtime_ns != after.st_mtime_ns
                or info.st_ctime_ns != after.st_ctime_ns
            ):
                raise ValueError("source changed while reading")
            return data
        finally:
            os.close(fd)
    except OSError as error:
        raise ValueError("source must be an existing non-symlink regular file") from error
    finally:
        os.close(directory)


def _source_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError("source must be valid UTF-8") from error
    if "\x00" in text or "\r" in text.replace("\r\n", ""):
        raise ValueError("NUL and standalone CR source files are not supported")
    return text


def _source_parts(data: bytes) -> tuple[str, list[str], str, bool]:
    text = _source_text(data)
    lf, crlf = text.count("\n"), text.count("\r\n")
    if crlf and lf != crlf:
        raise ValueError("mixed source line endings are not supported")
    newline = "\r\n" if crlf else "\n"
    terminal = text.endswith("\n")
    lines = text.split(newline) if text else []
    if terminal:
        lines.pop()
    return text, lines, newline, terminal


def source_document(source_root: str | Path, path: str) -> dict[str, Any]:
    """Return exact source and independent metadata; never add display line labels."""
    data = _read_bytes(source_root, path)
    text, _lines_value, newline, terminal = _source_parts(data)
    return {
        "path": path,
        "source_sha256": hashlib.sha256(data).hexdigest(),
        "text": text,
        "newline": newline,
        "terminal_newline": terminal,
        "utf8_bytes": len(data),
    }


def _lines(text: str) -> list[str]:
    # Only LF is a diff line boundary; str.splitlines() also splits Unicode
    # separators which Git treats as ordinary bytes.
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _unified(path: str, before: str, after: str) -> str:
    output = []
    for line in difflib.unified_diff(
        _lines(before), _lines(after), fromfile="a/" + path, tofile="b/" + path, n=3
    ):
        output.append(line)
        if not line.endswith("\n"):
            output.append("\n\\ No newline at end of file\n")
    return "".join(output)


def normalize_anchored_edits(
    proposal: SourceAnchoredProposal | Mapping[str, Any],
    source_root: str | Path,
    *,
    allowed_source_paths: Collection[str] | None = None,
) -> AnchoredConversion:
    """Build a standard diff against original bytes, never sequential guessed edits.

    Each old line block must occur exactly once in its original file. Edits are
    applied simultaneously by original line span, preserving LF/CRLF and EOF. The metadata's expected_sha256 and
    expected_bytes let the caller verify the entire applied candidate file.
    Config-only proposals keep an empty diff; existing policy decides acceptance.
    """
    # Revalidate even a mutable/already-created model; model_construct or later
    # mutation must not bypass local exact-match and resource constraints.
    value = proposal.model_dump() if isinstance(proposal, SourceAnchoredProposal) else proposal
    proposal = SourceAnchoredProposal.model_validate(value, strict=True)
    grouped = defaultdict(list)
    for index, edit in enumerate(proposal.edits):
        if allowed_source_paths is not None and edit.path not in allowed_source_paths:
            raise ValueError("edit path was not included in the supplied source context")
        grouped[edit.path].append((index, edit))
    diffs, files = [], []
    for path, edits in sorted(grouped.items()):
        original = _read_bytes(source_root, path)
        before, source_lines, newline, terminal = _source_parts(original)
        offsets = [0]
        for index, line in enumerate(source_lines):
            ending = newline if index < len(source_lines) - 1 or terminal else ""
            offsets.append(offsets[-1] + len(_utf8(line + ending)))
        source_hash = hashlib.sha256(original).hexdigest()
        spans = []
        for index, edit in edits:
            if edit.source_sha256 != source_hash:
                raise ValueError(f"stale source_sha256 for {path}")
            old = edit.old_lines
            matches = [
                start
                for start in range(len(source_lines) - len(old) + 1)
                if source_lines[start : start + len(old)] == old
            ]
            if not matches:
                raise ValueError(f"old_lines do not exactly match complete lines in {path}")
            if len(matches) != 1:
                raise ValueError(f"old_lines are not unique in {path}")
            start = matches[0]
            spans.append((start, start + len(old), index, edit.new_lines))
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
                        "start_line": start + 1,
                        "end_line": end,
                        "start_byte": offsets[start],
                        "end_byte": offsets[end],
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
            "conversion": "exact_original_lines_to_unified_diff",
            "context_lines": 3,
            "edit_count": len(proposal.edits),
            "file_count": len(files),
            "diff_sha256": hashlib.sha256(_utf8(diff)).hexdigest(),
            "diff_bytes": len(_utf8(diff)),
            "files": files,
        },
    )
