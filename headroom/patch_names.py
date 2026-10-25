"""Incremental undefined-name checks on source text; never execute target code.

Existing diagnostics are retained only when their exact name/message and source
line are unchanged. This is a syntax/name check, not proof of program semantics.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

_MAX_RESULT_BYTES = 2 * 1024 * 1024
_MAX_DIAGNOSTICS = 4096
_TOOL_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8"}


def _lint(text: str, name: str) -> list[dict]:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--ignore-noqa",
            "--select",
            "F821",
            "--target-version",
            "py312",
            "--output-format",
            "json",
            "--stdin-filename",
            name,
            "-",
        ],
        input=text,
        cwd=Path(sys.executable).parent,
        env=_TOOL_ENV,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode not in (0, 1):
        raise ValueError("Ruff F821 checker unavailable or failed")
    if len(completed.stdout.encode("utf-8")) > _MAX_RESULT_BYTES:
        raise ValueError("Ruff F821 result exceeds the review bound")
    records = json.loads(completed.stdout)
    if type(records) is not list or len(records) > _MAX_DIAGNOSTICS:
        raise ValueError("Invalid or excessive Ruff F821 diagnostics")
    if (completed.returncode == 0) != (not records):
        raise ValueError("Ruff F821 status and diagnostics disagree")
    lines = text.splitlines()
    output = []
    for record in records:
        if type(record) is not dict or record.get("code") != "F821":
            raise ValueError("Unexpected Ruff diagnostic")
        message = record.get("message")
        location = record.get("location", {})
        row, column = location.get("row"), location.get("column")
        if (
            type(message) is not str
            or not message.startswith("Undefined name ")
            or len(message) > 4096
            or type(row) is not int
            or not 1 <= row <= len(lines)
            or type(column) is not int
            or column < 1
        ):
            raise ValueError("Malformed Ruff F821 diagnostic")
        output.append(
            {"path": name, "code": "F821", "message": message, "row": row, "column": column}
        )
    return output


def _name_scopes(text: str) -> dict:
    scopes = {}

    class Names(ast.NodeVisitor):
        def __init__(self):
            self.scope = ()

        def visit_Name(self, node):
            scopes[(node.lineno, node.col_offset + 1)] = self.scope

        def visit_FunctionDef(self, node):
            previous = self.scope
            self.scope += (node.name,)
            self.generic_visit(node)
            self.scope = previous

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

    Names().visit(ast.parse(text))
    return scopes


def _key(record, lines, scopes):
    location = record["row"], record["column"]
    # Non-Name diagnostics (e.g. string annotations) require unchanged position.
    # Unknown scope is never broadly grandfathered by matching a name alone.
    scope = scopes.get(location, ("unclassified", *location))
    return scope, record["message"], lines[record["row"] - 1]


def check_undefined_names(before: Mapping[str, str], after: Mapping[str, str]) -> dict:
    """Reject new F821 diagnostics; missing checker never counts as success."""
    result = {
        "protocol": "headroom.incremental_f821.v1",
        "checker": "isolated installed Ruff F821; no repository configuration or target execution",
        "status": "error",
        "reason": "NAME_CHECK_UNAVAILABLE",
        "checked_files": [],
        "preserved_existing_diagnostics": [],
        "new_diagnostics": [],
        "limitations": (
            "Only changed Python files and newly observed undefined-name diagnostics are checked. "
            "Unchanged existing dynamic-name diagnostics are retained; no runtime semantic proof."
        ),
    }
    try:
        for name in sorted(after):
            if not name.lower().endswith(".py"):
                continue
            original, candidate = before.get(name, ""), after[name]
            if type(original) is not str or type(candidate) is not str:
                raise ValueError("Name checker requires source text")
            old_records, new_records = _lint(original, name), _lint(candidate, name)
            old_lines, new_lines = original.splitlines(), candidate.splitlines()
            old_scopes, new_scopes = _name_scopes(original), _name_scopes(candidate)
            retained = Counter(_key(record, old_lines, old_scopes) for record in old_records)
            result["checked_files"].append(
                {"path": name, "before_count": len(old_records), "after_count": len(new_records)}
            )
            for record in new_records:
                key = _key(record, new_lines, new_scopes)
                if retained[key]:
                    retained[key] -= 1
                    result["preserved_existing_diagnostics"].append(record)
                else:
                    result["new_diagnostics"].append(record)
        result["status"] = "failed" if result["new_diagnostics"] else "passed"
        result["reason"] = "NEW_UNDEFINED_NAME" if result["new_diagnostics"] else "NO_NEW_F821"
    except (
        OSError,
        subprocess.SubprocessError,
        ValueError,
        TypeError,
        AttributeError,
        RecursionError,
        SyntaxError,
    ) as error:
        result["detail"] = str(error)[:1000]
    return result
