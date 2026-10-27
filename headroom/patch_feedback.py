"""Bounded feedback about rejected patch bytes; never execute or rewrite source."""

from __future__ import annotations

import ast
import hashlib
import json
import re

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


MAX_NAME_FEEDBACK_BYTES = MAX_SYNTAX_FEEDBACK_BYTES
MAX_NAME_DIAGNOSTICS = 12
_NAME_DETAIL = re.compile(
    r"(?P<path>[^:\r\n]+):(?P<row>[1-9][0-9]{0,8}):(?P<column>[1-9][0-9]{0,8}) "
    r"F821 Undefined name `(?P<name>[^`\r\n]{1,128})`"
)
_NAME_SHA = re.compile(r"[0-9a-f]{64}")


def rejected_name_feedback(candidate_root, changed_files, *, reason, detail, application_check):
    """Explain existing F821 diagnostics, without linting, executing or repairing.

    The caller passes the host's original reason/detail and exact-application
    receipt. A matching AST Name only corroborates the reported location; it
    does not independently prove that a name is undefined or change the gate.
    Ruff columns count Unicode characters; AST offsets count UTF-8 bytes.
    """
    feedback = {
        "schema": "headroom.rejected_name_feedback.v1",
        "coordinate_space": "rejected_candidate",
        "original_source_span_ids": False,
        "status": "not_applicable",
        "diagnostics": [],
        "omitted_diagnostic_count": 0,
        "source_is_untrusted": True,
    }
    if reason != "NEW_UNDEFINED_NAME":
        return feedback
    feedback.update(status="unavailable", reason="candidate_evidence_unavailable")
    if (
        candidate_root is None
        or type(detail) is not str
        or not detail
        or len(detail.encode("utf-8")) > 2000
        or type(application_check) is not dict
        or application_check.get("protocol") != "headroom.exact_application.v1"
        or application_check.get("verified") is not True
    ):
        return feedback
    try:
        details = detail.splitlines()
        feedback["omitted_diagnostic_count"] = len(details)
        matches = [_NAME_DETAIL.fullmatch(line) for line in details]
        if not all(matches) or not isinstance(changed_files, (tuple, list)):
            return feedback
        bindings = application_check.get("files")
        if type(bindings) is not list or not 1 <= len(bindings) <= 20:
            return feedback
        records = {}
        for binding in bindings:
            if type(binding) is not dict:
                return feedback
            path = binding.get("path")
            if type(path) is not str or path in records:
                return feedback
            records[path] = binding
        checked = {}
        items = []
        for match in matches[:MAX_NAME_DIAGNOSTICS]:
            path, name = match["path"], match["name"]
            row, column = int(match["row"]), int(match["column"])
            if (
                path not in changed_files
                or path not in records
                or len(path.encode("utf-8")) > 512
                or not path.lower().endswith(".py")
                or not name.isidentifier()
            ):
                return feedback
            if path not in checked:
                if len(checked) >= MAX_SYNTAX_FILES:
                    break
                record = records[path]
                expected = record.get("expected_sha256")
                if (
                    type(expected) is not str
                    or _NAME_SHA.fullmatch(expected) is None
                    or record.get("candidate_sha256") != expected
                    or type(record.get("bytes")) is not int
                ):
                    return feedback
                data = _read_bytes(candidate_root, path)
                if hashlib.sha256(data).hexdigest() != expected or len(data) != record["bytes"]:
                    return feedback
                source = data.decode("utf-8")
                # Only Python physical newlines define AST/Ruff row coordinates.
                lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                withheld = _CREDENTIAL_PATTERN.search(source) is not None
                names = set()
                if not withheld:
                    for node in ast.walk(ast.parse(source)):
                        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                            # Convert byte offset to the exact character column.
                            prefix = lines[node.lineno - 1].encode("utf-8")[: node.col_offset]
                            char_column = len(prefix.decode("utf-8")) + 1
                            names.add((node.lineno, char_column, node.id))
                checked[path] = expected, lines, names, withheld
            expected, lines, names, withheld = checked[path]
            item = {"path": path, "candidate_sha256": expected}
            if withheld:
                item.update(status="withheld", reason="credential_like_source")
            else:
                if (row, column, name) not in names:
                    return feedback
                excerpt = []
                for index in range(max(0, row - 2), min(len(lines), row + 1)):
                    text = _text(lines[index], 512)
                    excerpt.append(
                        {"line": index + 1, "text": text, "truncated": text != lines[index]}
                    )
                item.update(
                    status="undefined_name",
                    code="F821",
                    name=name,
                    line=row,
                    column=column,
                    excerpt=excerpt,
                )
            proposed_items = [*items, item]
            proposed = {
                **feedback,
                "status": "partial",
                "diagnostics": proposed_items,
                "omitted_diagnostic_count": len(details) - len(proposed_items),
            }
            if len(json.dumps(proposed, ensure_ascii=False).encode()) > MAX_NAME_FEEDBACK_BYTES:
                break
            items = proposed_items
        feedback["diagnostics"] = items
        feedback["omitted_diagnostic_count"] = len(details) - len(items)
        if items:
            complete = not feedback["omitted_diagnostic_count"] and all(
                item["status"] == "undefined_name" for item in items
            )
            feedback["status"] = "complete" if complete else "partial"
            feedback.pop("reason", None)
    except (OSError, ValueError, TypeError, KeyError, RecursionError, SyntaxError, OverflowError):
        # Ancillary evidence is unavailable; do not leak private exception text
        # or replace the original rejection or bounded repair behavior.
        return {
            **feedback,
            "status": "unavailable",
            "reason": "candidate_evidence_unavailable",
            "diagnostics": [],
        }
    return feedback
