"""Bounded explanation of existing host MODEL_CHANGED binding rejections."""

from __future__ import annotations

import ast
import hashlib
import json
import re

from headroom.patch_edits import _read_bytes
from headroom.patch_feedback import _text
from headroom.verify.policy import (
    _CREDENTIAL_PATTERN,
    MODEL_KEYS,
    PolicyIssue,
    _binding_issues,
    _bindings,
    normalize_policy,
)

MAX_BINDING_FEEDBACK_BYTES = 8192
MAX_BINDING_FILES = 3
MAX_BINDING_ENTRIES = 3
_SHA = re.compile(r"[0-9a-f]{64}")
_MESSAGES = {
    "Model shape must remain unchanged.",
    "A new shape override needs permission.",
}


def _origin(value, lines):
    if value is None:
        return None
    row, end_row = value["line"], value["end_line"]
    col, end_col = value["column_bytes"], value["end_column_bytes"]
    if not (
        all(type(x) is int for x in (row, end_row, col, end_col))
        and 1 <= row <= end_row <= len(lines)
        and 0 <= col <= len(lines[row - 1].encode())
        and 0 <= end_col <= len(lines[end_row - 1].encode())
        and (row != end_row or col <= end_col)
    ):
        return None
    excerpt = _text(lines[row - 1], 384)
    return {
        "kind": value["kind"],
        "line": row,
        "column": len(lines[row - 1].encode()[:col].decode()) + 1,
        "end_line": end_row,
        "end_column": len(lines[end_row - 1].encode()[:end_col].decode()) + 1,
        "enclosing_call": _text(value["enclosing_call"], 128)
        if value["enclosing_call"] is not None
        else None,
        "excerpt": excerpt,
        "excerpt_truncated": excerpt != lines[row - 1],
    }


def _side(values, origins, lines):
    entries = []
    for index, (number, expression) in enumerate(values[:MAX_BINDING_ENTRIES]):
        rendered = _text(expression, 256)
        entries.append(
            {
                "resolved_number": number,
                "expression_ast": rendered,
                "expression_truncated": rendered != expression,
                "origin": _origin(origins[index], lines) if index < len(origins) else None,
            }
        )
    return {
        "binding_count": len(values),
        "entries": entries,
        "entries_omitted": max(0, len(values) - len(entries)),
    }


def rejected_model_binding_feedback(
    source_root, candidate_root, changed_files, *, reason, issues, application_check
):
    """Annotate the host guard's existing result; never change it or execute source.

    Sources must match the original/exact candidate application hashes. Binding
    entries are syntactic guard inputs, including conditional alternatives; their
    count is not a runtime model-shape or parameter-count measurement.
    """
    feedback = {
        "schema": "headroom.rejected_model_bindings.v1",
        "status": "not_applicable",
        "basis": "existing_host_model_binding_guard",
        "source_is_untrusted": True,
        "original_source_span_ids": False,
        "gate_changed": False,
        "model_equivalence_proven": False,
        "diagnostics": [],
    }
    if reason != "MODEL_CHANGED":
        return feedback
    feedback.update(status="unavailable", reason="binding_evidence_unavailable")
    if (
        source_root is None
        or candidate_root is None
        or not isinstance(changed_files, (tuple, list))
        or not isinstance(issues, (tuple, list))
        or len(changed_files) > 20
        or len(issues) > 128
        or type(application_check) is not dict
        or application_check.get("protocol") != "headroom.exact_application.v1"
        or application_check.get("verified") is not True
    ):
        return feedback
    try:
        matching = [
            issue
            for issue in issues
            if isinstance(issue, PolicyIssue)
            and issue.code == "MODEL_CHANGED"
            and issue.message in _MESSAGES
            and type(issue.path) is str
        ]
        paths = sorted({issue.path for issue in matching})
        files = application_check.get("files")
        if not paths or type(files) is not list or not 1 <= len(files) <= 20:
            return feedback
        records = {}
        for record in files:
            if type(record) is not dict or type(record.get("path")) is not str:
                return feedback
            if record["path"] in records:
                return feedback
            records[record["path"]] = record
        feedback["files_omitted"] = max(0, len(paths) - MAX_BINDING_FILES)
        diagnostics = []
        feedback["files_without_matching_binding"] = 0
        for path_index, path in enumerate(paths[:MAX_BINDING_FILES]):
            if (
                path not in changed_files
                or path not in records
                or len(path.encode()) > 512
                or not path.lower().endswith(".py")
            ):
                return feedback
            record = records[path]
            old_sha, new_sha = record.get("before_sha256"), record.get("expected_sha256")
            if (
                any(type(x) is not str or _SHA.fullmatch(x) is None for x in (old_sha, new_sha))
                or record.get("candidate_sha256") != new_sha
                or type(record.get("bytes")) is not int
            ):
                return feedback
            old_raw, new_raw = _read_bytes(source_root, path), _read_bytes(candidate_root, path)
            if (
                hashlib.sha256(old_raw).hexdigest() != old_sha
                or hashlib.sha256(new_raw).hexdigest() != new_sha
                or len(new_raw) != record["bytes"]
            ):
                return feedback
            old, new = old_raw.decode(), new_raw.decode()
            identity = {"path": path, "before_sha256": old_sha, "candidate_sha256": new_sha}
            if _CREDENTIAL_PATTERN.search(old) or _CREDENTIAL_PATTERN.search(new):
                item = {**identity, "status": "withheld", "reason": "credential_like_source"}
                proposed = {**feedback, "diagnostics": [*diagnostics, item]}
                if (
                    len(json.dumps(proposed, ensure_ascii=False).encode())
                    > MAX_BINDING_FEEDBACK_BYTES - 256
                ):
                    feedback["files_omitted"] = len(paths) - path_index
                    break
                diagnostics.append(item)
                continue
            old_origins, new_origins = {}, {}
            before = _bindings(ast.parse(old), origins=old_origins)
            after = _bindings(ast.parse(new), origins=new_origins)
            lines = [
                source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                for source in (old, new)
            ]
            keys = []
            for key in sorted(before.keys() | after.keys()):
                if key not in MODEL_KEYS and not key.startswith("constructor:"):
                    continue
                # Explain precisely the existing key-local guard predicate. This
                # does not rerun or replace source-policy acceptance.
                check = _binding_issues(
                    {key: before[key]} if key in before else {},
                    {key: after[key]} if key in after else {},
                    normalize_policy(None),
                    path,
                    (),
                )
                if any(issue in matching for issue in check):
                    keys.append(key)
            if not keys:
                feedback["files_without_matching_binding"] += 1
            for index, key in enumerate(keys):
                item = {
                    **identity,
                    "status": "guard_binding_difference",
                    "key": _text(key, 160),
                    "key_truncated": _text(key, 160) != key,
                    "before": _side(before.get(key, []), old_origins.get(key, []), lines[0]),
                    "after": _side(after.get(key, []), new_origins.get(key, []), lines[1]),
                }
                proposed = {**feedback, "diagnostics": [*diagnostics, item]}
                if (
                    len(json.dumps(proposed, ensure_ascii=False).encode())
                    > MAX_BINDING_FEEDBACK_BYTES - 256
                ):
                    feedback["files_omitted"] = len(paths) - path_index - 1
                    feedback["bindings_omitted"] = len(keys) - index
                    break
                diagnostics.append(item)
            if feedback.get("bindings_omitted"):
                break
        if diagnostics:
            feedback["diagnostics"] = diagnostics
            feedback["status"] = (
                "partial"
                if (
                    feedback.get("files_omitted")
                    or feedback.get("bindings_omitted")
                    or feedback.get("files_without_matching_binding")
                    or any(
                        item["status"] == "withheld"
                        or any(
                            item.get(side, {}).get("entries_omitted")
                            or any(
                                entry["origin"] is None
                                for entry in item.get(side, {}).get("entries", [])
                            )
                            for side in ("before", "after")
                        )
                        for item in diagnostics
                    )
                )
                else "complete"
            )
            feedback.pop("reason", None)
        return feedback
    except (OSError, ValueError, TypeError, KeyError, RecursionError, SyntaxError, OverflowError):
        return {
            **feedback,
            "status": "unavailable",
            "diagnostics": [],
            "reason": "binding_evidence_unavailable",
        }
