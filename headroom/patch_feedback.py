"""Bounded feedback about rejected patch bytes; never execute or rewrite source."""

from __future__ import annotations

import hashlib
import json

from headroom.patch_edits import _read_bytes
from headroom.verify.policy import _CREDENTIAL_PATTERN

MAX_SYNTAX_FEEDBACK_BYTES = 8192
MAX_SYNTAX_FILES = 3


def candidate_content_fingerprint(metadata, proposal):
    """Compare source-bound candidate content/configuration, ignoring prose notes."""
    content = {
        "files": sorted(
            (
                {
                    "path": item["path"],
                    "sha256": item["expected_sha256"],
                    "bytes": item["expected_bytes"],
                }
                for item in metadata["files"]
            ),
            key=lambda item: item["path"],
        ),
        "env_changes": proposal["env_changes"],
        "cli_changes": proposal["cli_changes"],
    }
    encoded = json.dumps(content, sort_keys=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def _text(value, limit=256):
    # Bounds refer to serialized bytes, including escaped control characters.
    value = str(value)
    result = value[:limit]
    while len(json.dumps(result, ensure_ascii=False).encode()) > limit:
        result = result[:-1]
    return result


def rejected_syntax_feedback(candidate_root, changed_files, *, reason, issues=()):
    """Read only changed regular files and compile without executing target code.

    Candidate line numbers are deliberately not original source-span IDs. The
    policy result remains authoritative; this function never turns a failure
    into acceptance and never modifies a candidate.
    """
    syntax_codes = {"SYNTAX_INVALID", "SOURCE_SYNTAX_INVALID"}
    paths = {item.path for item in issues if item.code in syntax_codes and item.path is not None}
    if reason == "COMPILE_FAILED":
        paths.update(changed_files)
    paths.intersection_update(changed_files)
    paths = sorted(path for path in paths if path.lower().endswith(".py"))
    feedback = {
        "coordinate_space": "rejected_candidate",
        "diagnostics": [],
        "omitted_file_count": len(paths),
    }
    if candidate_root is None:
        return feedback
    for path in paths[:MAX_SYNTAX_FILES]:
        if len(path.encode()) > 512:
            continue
        try:
            data = _read_bytes(candidate_root, path)
            source = data.decode("utf-8")
        except (ValueError, OSError, UnicodeError):
            continue
        item = {"path": path, "candidate_sha256": hashlib.sha256(data).hexdigest()}
        # Reuse the policy's credential detector; never echo suspect source,
        # including nearby context or a parser message that quotes source text.
        if _CREDENTIAL_PATTERN.search(source):
            item.update(status="withheld", reason="credential_like_source")
        else:
            try:
                compile(source, path, "exec", dont_inherit=True)
            except SyntaxError as error:
                row = error.lineno
                lines = source.split("\n")
                excerpt = []
                if row is not None and 1 <= row <= len(lines):
                    for index in range(max(0, row - 2), min(len(lines), row + 1)):
                        text = _text(lines[index].removesuffix("\r"), 512)
                        excerpt.append(
                            {
                                "line": index + 1,
                                "text": text,
                                "truncated": text != lines[index].removesuffix("\r"),
                            }
                        )
                item.update(
                    status="syntax_error",
                    message=_text(error.msg),
                    line=row,
                    column=error.offset,
                    end_line=getattr(error, "end_lineno", None),
                    end_column=getattr(error, "end_offset", None),
                    excerpt=excerpt,
                )
            except (ValueError, RecursionError, OverflowError):
                item.update(status="unavailable", reason="parser_bounds")
            else:
                continue
        proposed = {**feedback, "diagnostics": [*feedback["diagnostics"], item]}
        proposed["omitted_file_count"] -= 1
        if len(json.dumps(proposed, ensure_ascii=False).encode()) > MAX_SYNTAX_FEEDBACK_BYTES:
            break
        feedback = proposed
    return feedback
