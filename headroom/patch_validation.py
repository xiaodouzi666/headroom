"""Bounded diff diagnostics and exact, read-only application verification.

This module never repairs a diff or runs target code. Git may use its direct
fallback; acceptance here depends on exact declared positions and bytes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from headroom.verify.policy import safe_relative_path

MAX_DIFF_BYTES = 512_000
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_DIAGNOSTIC_CHARS = 1800
_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:[^\r\n]*)$")
_MARKER = "\\ No newline at end of file"
_METADATA = ("diff --git ", "index ", "new file mode 100644")


def _lines(text: str) -> list[str]:
    # splitlines() treats Unicode separators inside source literals as newlines.
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _message(details: dict) -> str:
    bounded = {
        key: value[:160] if isinstance(value, str) else value for key, value in details.items()
    }
    return json.dumps(bounded, ensure_ascii=True, sort_keys=True)[:MAX_DIAGNOSTIC_CHARS]


class PatchValidationError(ValueError):
    """A structural/application mismatch, without source-code excerpts."""

    def __init__(self, code, **details):
        self.details = {"code": code, **details}
        super().__init__(_message(self.details))


def _fail(code, **details):
    raise PatchValidationError(code, **details)


@dataclass
class _Line:
    prefix: str
    value: str
    number: int
    no_newline: bool = False


@dataclass
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    number: int
    line: int
    body: list[_Line] = field(default_factory=list)


@dataclass
class _File:
    path: str
    added: bool
    line: int
    hunks: list[_Hunk] = field(default_factory=list)


def _parse(diff: str) -> list[_File]:
    if not isinstance(diff, str):
        _fail("diff_must_be_text")
    try:
        size = len(diff.encode("utf-8"))
    except UnicodeError:
        _fail("diff_not_utf8")
    if size > MAX_DIFF_BYTES or "\x00" in diff:
        _fail("diff_bounds", byte_limit=MAX_DIFF_BYTES)
    if not diff.strip():
        return []
    lines = _lines(diff)
    files = []
    current = None
    index = 0
    while index < len(lines):
        raw = lines[index]
        text = raw.rstrip("\r\n")
        if text.startswith(_METADATA) or not text:
            index += 1
            continue
        if text.startswith("--- "):
            old = text[4:].split("\t", 1)[0]
            if index + 1 >= len(lines) or not lines[index + 1].startswith("+++ "):
                _fail("missing_target_header", line=index + 1)
            new = lines[index + 1].rstrip("\r\n")[4:].split("\t", 1)[0]
            if not new.startswith("b/"):
                _fail("target_header_prefix", line=index + 2, prefix=new[:2])
            try:
                name = safe_relative_path(new[2:])
            except ValueError:
                _fail("unsafe_target_path", line=index + 2)
            if old not in {"/dev/null", "a/" + name}:
                _fail("source_target_disagree", file=name, line=index + 1)
            if any(item.path == name for item in files):
                _fail("duplicate_target", file=name, line=index + 1)
            current = _File(name, old == "/dev/null", index + 1)
            files.append(current)
            if len(files) > 20:
                _fail("too_many_files", limit=20)
            index += 2
            continue
        if text.startswith("@@"):
            if current is None:
                _fail("hunk_without_file", line=index + 1)
            match = _HEADER.fullmatch(text)
            if not match or any(len(value) > 8 for value in match.groups() if value):
                _fail(
                    "invalid_hunk_header",
                    file=current.path,
                    hunk=len(current.hunks) + 1,
                    line=index + 1,
                )
            old_start, old_count, new_start, new_count = (
                int(match[1]),
                int(match[2] or 1),
                int(match[3]),
                int(match[4] or 1),
            )
            if (old_count and not old_start) or (new_count and not new_start):
                _fail("invalid_zero_start", file=current.path, line=index + 1)
            hunk = _Hunk(
                old_start, old_count, new_start, new_count, len(current.hunks) + 1, index + 1
            )
            current.hunks.append(hunk)
            index += 1
            old_seen = new_seen = 0
            while old_seen < old_count or new_seen < new_count:
                facts = {
                    "file": current.path,
                    "hunk": hunk.number,
                    "line": index + 1,
                    "declared_old": old_count,
                    "declared_new": new_count,
                    "observed_old": old_seen,
                    "observed_new": new_seen,
                }
                if index == len(lines):
                    _fail("hunk_short", **facts)
                body = lines[index]
                if body.rstrip("\r\n") == _MARKER:
                    _mark_no_newline(hunk, current.path, index + 1)
                    index += 1
                    continue
                prefix = body[:1]
                value = body[1:]
                if body in {"\n", "\r\n"}:
                    prefix, value = " ", body
                if prefix not in {" ", "+", "-"}:
                    _fail("hunk_bad_prefix", prefix=prefix, **facts)
                if not body.endswith("\n"):
                    _fail("unterminated_patch_line", prefix=prefix, **facts)
                old_seen += prefix in {" ", "-"}
                new_seen += prefix in {" ", "+"}
                if old_seen > old_count or new_seen > new_count:
                    _fail(
                        "hunk_long",
                        prefix=prefix,
                        **{
                            **facts,
                            "observed_old": old_seen,
                            "observed_new": new_seen,
                        },
                    )
                hunk.body.append(_Line(prefix, value, index + 1))
                index += 1
            if index < len(lines) and lines[index].rstrip("\r\n") == _MARKER:
                _mark_no_newline(hunk, current.path, index + 1)
                index += 1
            continue
        facts = {"line": index + 1, "prefix": raw[:1]}
        if current is not None:
            facts["file"] = current.path
            if current.hunks:
                hunk = current.hunks[-1]
                facts.update(
                    hunk=hunk.number, declared_old=hunk.old_count, declared_new=hunk.new_count
                )
                facts.update(
                    observed_old=sum(x.prefix in {" ", "-"} for x in hunk.body),
                    observed_new=sum(x.prefix in {" ", "+"} for x in hunk.body),
                )
        _fail("unexpected_diff_line", **facts)
    if not files:
        _fail("missing_file_header")
    for item in files:
        if not item.hunks:
            _fail("file_without_hunks", file=item.path, line=item.line)
    return files


def _mark_no_newline(hunk, name, number):
    if not hunk.body or hunk.body[-1].no_newline or not hunk.body[-1].value.endswith("\n"):
        _fail("unexpected_no_newline_marker", file=name, hunk=hunk.number, line=number)
    hunk.body[-1].value = hunk.body[-1].value[:-1]
    hunk.body[-1].no_newline = True


def bounded_structural_error(diff: str, exception: Exception) -> str:
    """Return bounded file/hunk/count/prefix facts, never arbitrary exception text."""
    try:
        parsed = _parse(diff)
    except PatchValidationError as error:
        return _message({**error.details, "parser_error": type(exception).__name__})
    details = {"code": "parser_rejected", "parser_error": type(exception).__name__}
    if parsed:
        item = parsed[-1]
        hunk = item.hunks[-1]
        details.update(
            file=item.path,
            hunk=hunk.number,
            line=hunk.line,
            declared_old=hunk.old_count,
            declared_new=hunk.new_count,
        )
    return _message(details)


def _read(root: Path, name: str, *, missing=False) -> bytes | None:
    safe_relative_path(name, root)
    path = root / name
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if missing:
            return None
        _fail("missing_file", file=name)
    except OSError:
        _fail("unreadable_file", file=name)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            _fail("file_bounds_or_type", file=name, byte_limit=MAX_FILE_BYTES)
        data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        _fail("file_bounds_or_type", file=name, byte_limit=MAX_FILE_BYTES)
    try:
        data.decode("utf-8")
    except UnicodeError:
        _fail("file_not_utf8", file=name)
    return data


def _expected(item: _File, original: bytes) -> bytes:
    source = _lines(original.decode("utf-8"))
    output = []
    cursor = 0
    for hunk in item.hunks:
        facts = {
            "file": item.path,
            "hunk": hunk.number,
            "line": hunk.line,
            "declared_old": hunk.old_count,
            "declared_new": hunk.new_count,
        }
        start = hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1
        if start < cursor or start > len(source) or start + hunk.old_count > len(source):
            _fail(
                "source_range_mismatch",
                source_lines=len(source),
                source_start=hunk.old_start,
                **facts,
            )
        output.extend(source[cursor:start])
        target_start = hunk.new_start if hunk.new_count == 0 else hunk.new_start - 1
        if target_start != len(output):
            _fail(
                "target_position_mismatch",
                target_start=hunk.new_start,
                expected_offset=len(output),
                **facts,
            )
        cursor = start
        for line in hunk.body:
            if line.prefix in {" ", "-"}:
                if cursor >= len(source) or source[cursor] != line.value:
                    _fail(
                        "source_content_mismatch",
                        source_line=cursor + 1,
                        prefix=line.prefix,
                        **{**facts, "line": line.number},
                    )
                cursor += 1
            if line.prefix in {" ", "+"}:
                output.append(line.value)
    output.extend(source[cursor:])
    if any(not line.endswith("\n") for line in output[:-1]):
        _fail("no_newline_not_at_eof", file=item.path)
    expected = "".join(output).encode("utf-8")
    if len(expected) > MAX_FILE_BYTES:
        _fail("expected_file_bounds", file=item.path, byte_limit=MAX_FILE_BYTES)
    return expected


def verify_exact_application(
    diff: str, source_root: str | Path, candidate_root: str | Path
) -> dict:
    """Rebuild declared files at exact old/new coordinates and compare all bytes.

    Success verifies every declared file, including unchanged portions of those
    files. Directory-wide provenance remains the caller's copy/policy contract.
    Raises ValueError on drift; no source is executed or rewritten.
    """
    files = _parse(diff)
    source = Path(source_root).resolve(strict=True)
    candidate = Path(candidate_root).resolve(strict=True)
    if not source.is_dir() or not candidate.is_dir():
        _fail("roots_must_be_directories")
    receipts = []
    for item in files:
        original = _read(source, item.path, missing=item.added)
        if item.added and original is not None:
            _fail("added_file_already_exists", file=item.path)
        original = original if original is not None else b""
        expected = _expected(item, original)
        actual = _read(candidate, item.path)
        expected_hash = hashlib.sha256(expected).hexdigest()
        actual_hash = hashlib.sha256(actual).hexdigest()
        if actual != expected:
            _fail(
                "application_content_mismatch",
                file=item.path,
                expected_sha256=expected_hash,
                candidate_sha256=actual_hash,
                expected_bytes=len(expected),
                candidate_bytes=len(actual),
            )
        receipts.append(
            {
                "path": item.path,
                "before_sha256": hashlib.sha256(original).hexdigest(),
                "expected_sha256": expected_hash,
                "candidate_sha256": actual_hash,
                "hunks": len(item.hunks),
                "bytes": len(actual),
            }
        )
    return {"protocol": "headroom.exact_application.v1", "verified": True, "files": receipts}
