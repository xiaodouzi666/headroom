"""Snapshot-only quantitative grounding, independent of the shared diagnosis validator.

These checks constrain numeric attribution, not causal truth or repair feasibility.
No output is corrected, no missing measurement is zero-filled, and no retry is made.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation, localcontext

from headroom.diagnose import DiagnosisIssue

MAX_PEAK_ROWS = 40
_STACK_ID = re.compile(r"stk_[a-f0-9]{16}\Z")
_CATEGORIES = {
    "params",
    "grads",
    "optimizer_state",
    "activations",
    "temporaries",
    "retained_graph",
    "cache",
    "fragmentation_candidate",
    "unknown",
}
# Numeric memory quantities in model prose are disallowed, even when correct:
# measured quantities belong in grounded bytes_gb, predictions in expected_saving_gb.
# A separated "B" denotes bytes; attached "7B" can be a model's parameter count.
_NUMBER = r"(?<![\w.])[-+−]?(?:\d[\d,_]*(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
_MEMORY_QUANTITY = re.compile(
    _NUMBER + r"(?:\s*(?:[KMGTPE]i?B|bytes?|[kmgtpe]i?bibytes?|"
    r"(?:kilo|mega|giga|tera|peta|exa)bytes?)\b|\s+B\b)",
    re.IGNORECASE,
)


def canonical_peak_table(analysis, visible_peak_ids):
    """Bounded exact visible rows; publish category totals only with all contributors."""
    visible = list(dict.fromkeys(visible_peak_ids))[:MAX_PEAK_ROWS]
    available = {}
    duplicates = set()
    for row in analysis.get("peak_composition", []):
        identifier, count = row.get("stack_id"), row.get("bytes")
        if (
            not isinstance(identifier, str)
            or not _STACK_ID.fullmatch(identifier)
            or type(count) is not int
            or count < 0
        ):
            continue
        if identifier in available:
            duplicates.add(identifier)
        available[identifier] = row
    rows = []
    for identifier in visible:
        if identifier not in available or identifier in duplicates:
            continue
        row = available[identifier]
        count = row["bytes"]
        # Integer formatting preserves all nine decimal places without float rounding.
        rows.append(
            {
                "stack_id": identifier,
                "peak_bytes": count,
                "decimal_GB": f"{count // 1_000_000_000}.{count % 1_000_000_000:09d}",
            }
        )
    categories = []
    for category in sorted(_CATEGORIES):
        contributors = [
            row for row in rows if available[row["stack_id"]].get("category") == category
        ]
        count = sum(row["peak_bytes"] for row in contributors)
        total = analysis.get("category_bytes", {}).get(category)
        # A truncated category must not be advertised as a complete category total.
        complete_ids = {key for key, row in available.items() if row.get("category") == category}
        refs = [row["stack_id"] for row in contributors]
        if (
            refs
            and type(total) is int
            and count == total
            and complete_ids == set(refs)
            and not (complete_ids & duplicates)
        ):
            categories.append(
                {
                    "heuristic_category": category,
                    "peak_bytes": count,
                    "decimal_GB": f"{count // 1_000_000_000}.{count % 1_000_000_000:09d}",
                    "all_contributing_refs": refs,
                }
            )
    return {"rows": rows, "complete_category_sums": categories}


def render_peak_grounding(analysis, visible_peak_ids):
    table = canonical_peak_table(analysis, visible_peak_ids)
    return (
        "## Canonical visible peak quantities\n\n"
        "Select exact stack reference(s) for your explanation. The host will calculate "
        "their deduplicated peak-live sum; do not output bytes_gb or copy memory numbers "
        "into prose. For a complete category explanation include ALL all_contributing_refs. "
        "Categories are allocation-origin heuristics, not causal ground truth. "
        "Unlisted/hot-path-only rows have unknown peak contribution, not zero. "
        "Cache gaps are not stack live bytes; discuss them qualitatively. "
        "Do not repeat numeric memory quantities in prose.\n\n"
        + json.dumps(table, ensure_ascii=False, separators=(",", ":"))
        + "\n\n"
    )


def _prose_fields(diagnosis):
    for i, cause in enumerate(diagnosis.get("root_causes", [])):
        yield f"root_causes[{i}].title", cause.get("title", "")
    for i, step in enumerate(diagnosis.get("plan", [])):
        for field in ("title", "description", "risk"):
            yield f"plan[{i}].{field}", step.get(field, "")
    for i, note in enumerate(diagnosis.get("notes", [])):
        yield f"notes[{i}]", note
    for i, request in enumerate(diagnosis.get("evidence_requests", [])):
        for field in ("field", "detail"):
            yield f"evidence_requests[{i}].{field}", request.get(field, "")


def memory_quantity_mentions(value):
    """Bounded excerpts for correction feedback, never automatic text edits."""
    if not isinstance(value, str):
        return []
    return [match.group()[:64] for match in list(_MEMORY_QUANTITY.finditer(value[:8192]))[:8]]


def validate_snapshot_grounding(diagnosis, evidence):
    """Return issues only; never repair an answer or clear genuine unknowns."""
    table = canonical_peak_table(
        evidence.get("analysis", {}),
        evidence.get("presentation", {}).get("peak_stack_ids", []),
    )
    peaks = {row["stack_id"]: row["peak_bytes"] for row in table["rows"]}
    issues = []
    for i, cause in enumerate(diagnosis.get("root_causes", [])):
        refs = set(cause.get("evidence_refs", []))
        path = f"root_causes[{i}].bytes_gb"
        if not refs or any(ref not in peaks for ref in refs):
            issues.append(
                DiagnosisIssue(
                    "SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE",
                    "Every quantitative cause needs an exact visible peak measurement; missing is not zero.",
                    path,
                )
            )
            continue
        try:
            with localcontext() as context:
                context.prec = 50
                claimed = Decimal(str(cause.get("bytes_gb"))) * Decimal(1_000_000_000)
                expected = sum(peaks[ref] for ref in refs)
                matches = claimed.is_finite() and abs(claimed - expected) <= Decimal(1)
        except (InvalidOperation, ValueError, TypeError):
            matches = False
        if not matches:
            issues.append(
                DiagnosisIssue(
                    "SNAPSHOT_PEAK_BYTES_MISMATCH",
                    "bytes_gb must match the deduplicated referenced peak-byte sum within one byte.",
                    path,
                )
            )
    for path, value in _prose_fields(diagnosis):
        if isinstance(value, str) and _MEMORY_QUANTITY.search(value):
            issues.append(
                DiagnosisIssue(
                    "SNAPSHOT_MEMORY_QUANTITY_IN_PROSE",
                    "Keep memory quantities in grounded structured fields, not narrative text.",
                    path,
                )
            )
    return tuple(issues)
