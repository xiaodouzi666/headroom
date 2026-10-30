"""Bounded text-availability and declared-dependency checks, not semantic inference."""

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from headroom.solver_context import invocation_observation

MAX_CATALOG_BYTES = 8 * 1024
MAX_SOURCE_FILES = 64
MAX_FIELD_ENTRIES = 20
MAX_SOURCE_LINES = 8192
MAX_LINE_NUMBER = 1_000_000
MAX_MARKDOWN_BYTES = 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}")
_NUMBERED = re.compile(r" *([0-9]+) \| (.*)")
_REDACTED = re.compile(r"\[(?:redacted|truncated|omitted)\]|<redacted>", re.IGNORECASE)


def _ranges(numbers):
    result = []
    for number in numbers:
        if result and number == result[-1][1] + 1:
            result[-1][1] = number
        else:
            result.append([number, number])
    return result


def _source_entry(number, source, section):
    if not isinstance(source, Mapping):
        return None
    path, sha = source.get("path"), source.get("sha256")
    if (
        type(path) is not str
        or not path
        or len(path.encode("utf-8")) > 512
        or "\n" in path
        or "\r" in path
        or PurePosixPath(path).is_absolute()
        or ".." in PurePosixPath(path).parts
        or any(part.startswith(".env") for part in PurePosixPath(path).parts)
        or type(sha) is not str
        or not _HEX.fullmatch(sha)
    ):
        return None
    entry = {
        "evidence_ref": f"source[{number}]",
        "kind": "source",
        "path": path,
        "source_sha256": sha,
        "availability": "unknown",
        "visible_ranges": [],
        "redacted_ranges": [],
        "total_lines": None,
        "text_availability_only": True,
        "runtime_values_verified": False,
    }
    total, included = source.get("total_lines"), source.get("included_lines")
    if (
        type(total) is not int
        or not 1 <= total <= MAX_LINE_NUMBER
        or type(included) is not list
        or not included
        or len(included) > MAX_SOURCE_LINES
        or any(type(n) is not int or not 1 <= n <= total for n in included)
        or included != sorted(set(included))
    ):
        return entry
    entry["total_lines"] = total
    marker = f"### {path}\nSHA-256: `{sha}`\n"
    if section is None or section.count(marker) != 1:
        return entry
    following = section.split(marker, 1)[1]
    opening = re.match(r"(`{3,})python\n", following)
    if opening is None:
        return entry
    end = following.find("\n" + opening.group(1) + "\n", opening.end())
    if end < 0:
        return entry
    parsed = []
    visible, redacted = [], []
    for line in following[opening.end() : end].splitlines():
        match = _NUMBERED.fullmatch(line)
        if match is None:
            if re.fullmatch(r"\.\.\. lines [0-9]+-[0-9]+ omitted \.\.\.", line):
                continue
            return entry
        number = int(match.group(1))
        parsed.append(number)
        (redacted if _REDACTED.search(match.group(2)) else visible).append(number)
    if parsed != included:
        return entry
    entry["visible_ranges"] = _ranges(visible)
    entry["redacted_ranges"] = _ranges(redacted)
    if len(visible) == total and entry["visible_ranges"] == [[1, total]]:
        entry["availability"] = "visible"
    return entry


def build_evidence_availability_catalog(evidence, evidence_markdown):
    """Cross-check host source metadata against the exact Markdown being sent.

    Source contents never enter the catalogue/schema/feedback. Unknown or missing
    metadata cannot establish visibility. This reads no files or environment.
    """
    result = {
        "schema": "headroom.evidence_availability.v1",
        "entries": [],
        "omitted_entries": 0,
        "text_availability_only": True,
        "runtime_values_verified": False,
    }
    section = None
    if isinstance(evidence_markdown, str):
        raw = evidence_markdown.encode("utf-8")
        if len(raw) <= MAX_MARKDOWN_BYTES:
            result["evidence_markdown_sha256"] = hashlib.sha256(raw).hexdigest()
            start, stop = "## Source\n", "\n## Static source observations"
            if evidence_markdown.count(start) == evidence_markdown.count(stop) == 1:
                section = evidence_markdown.split(start, 1)[1].split(stop, 1)[0] + "\n"
    context = evidence.get("execution_context") if isinstance(evidence, Mapping) else None
    entries = []
    for field in ("script_args", "execution_argv"):
        state, _ = invocation_observation(context, field)
        entries.append(
            {
                "evidence_ref": "execution_context." + field,
                "kind": "field",
                "availability": "visible"
                if state == "available"
                else "unsupported"
                if state == "unsupported"
                else "unknown",
                "text_availability_only": True,
                "runtime_values_verified": False,
            }
        )
    observed = context.get("runtime_input_observations") if isinstance(context, Mapping) else None
    entries.append(
        {
            "evidence_ref": "execution_context.runtime_input_observations",
            "kind": "field",
            "availability": "visible"
            if isinstance(observed, Mapping) and observed.get("status") == "observed"
            else "unsupported"
            if isinstance(observed, Mapping) and observed.get("status") == "unsupported"
            else "unknown",
            "text_availability_only": True,
            "runtime_values_verified": False,
        }
    )
    # Partial initialization evidence does not establish complete update coverage.
    # Child references let the model ask for the unknown component precisely.
    for child in ("initial_tensors", "logical_updates"):
        component = observed.get(child) if isinstance(observed, Mapping) else None
        if not isinstance(component, Mapping):
            continue
        entries.append(
            {
                "evidence_ref": "execution_context.runtime_input_observations." + child,
                "kind": "field",
                "availability": "visible" if component.get("status") == "observed" else "unknown",
                "text_availability_only": True,
                "runtime_values_verified": False,
            }
        )
    # Advertise exact observed leaves, not only a parent object. A model asking
    # for a supplied optimizer-input name receives literal contradiction feedback;
    # missing leaves and semantic uncertainty remain genuine unknowns.
    input_prefix = "execution_context.runtime_input_observations"
    for suffix, component in (
        ("", observed),
        (
            ".logical_updates",
            observed.get("logical_updates") if isinstance(observed, Mapping) else None,
        ),
    ):
        if not isinstance(component, Mapping) or component.get("status") != "observed":
            continue
        for name in (
            "optimizer_input_name",
            "effective_batch_per_optimizer_update",
            "required_optimizer_updates",
            "observed_optimizer_updates",
            "training_forwards_per_optimizer_update",
            "backwards_per_optimizer_update",
        ):
            value = component.get(name)
            present = (
                isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value)
                if name == "optimizer_input_name"
                else type(value) is int and 0 <= value <= 1_000_000
            )
            if present:
                entries.append(
                    {
                        "evidence_ref": input_prefix + suffix + "." + name,
                        "kind": "field",
                        "availability": "visible",
                        "text_availability_only": True,
                        "runtime_values_verified": False,
                    }
                )
    optimizer = (
        context.get("runtime_optimizer_observations") if isinstance(context, Mapping) else None
    )
    optimizer_summary = (
        isinstance(optimizer, Mapping)
        and optimizer.get("schema") == "headroom.runtime_optimizer_observations.v1"
    )
    for suffix in ("", ".parameters", ".updates"):
        visible = optimizer_summary and optimizer.get("status") in {"observed", "partial"}
        if suffix:
            visible = visible and isinstance(optimizer.get(suffix[1:]), Mapping)
        entries.append(
            {
                "evidence_ref": "execution_context.runtime_optimizer_observations" + suffix,
                "kind": "field",
                "availability": "visible"
                if visible
                else "unsupported"
                if optimizer_summary and optimizer.get("status") == "unsupported"
                else "unknown",
                "text_availability_only": True,
                "runtime_values_verified": False,
            }
        )
    sources = evidence.get("sources") if isinstance(evidence, Mapping) else None
    if isinstance(sources, list):
        result["omitted_entries"] += max(0, len(sources) - MAX_SOURCE_FILES)
        for number, source in enumerate(sources[:MAX_SOURCE_FILES]):
            entry = _source_entry(number, source, section)
            if entry is None:
                result["omitted_entries"] += 1
            else:
                entries.append(entry)
    for entry in entries:
        result["entries"].append(entry)
        if len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()) > MAX_CATALOG_BYTES:
            result["entries"].pop()
            result["omitted_entries"] += 1
    while len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode()) > MAX_CATALOG_BYTES:
        result["entries"].pop()
        result["omitted_entries"] += 1
    return result


def evidence_reference_catalog(evidence):
    value = evidence.get("evidence_availability_catalog") if isinstance(evidence, Mapping) else None
    if not isinstance(value, Mapping) or value.get("schema") != "headroom.evidence_availability.v1":
        return {}
    entries = value.get("entries")
    if not isinstance(entries, list) or len(entries) > MAX_SOURCE_FILES + MAX_FIELD_ENTRIES:
        return {}
    result = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            return {}
        ref = entry.get("evidence_ref")
        if type(ref) is not str or not 1 <= len(ref) <= 160 or ref in result:
            return {}
        result[ref] = entry
    return result


def _visible(entry, start, end):
    if entry.get("kind") != "source" or start is None:
        return entry.get("availability") == "visible"
    total = entry.get("total_lines")
    if type(total) is not int or not 1 <= start <= end <= total:
        return False
    ranges = entry.get("visible_ranges")
    if not isinstance(ranges, list):
        return False
    return any(
        isinstance(pair, list)
        and len(pair) == 2
        and all(type(n) is int for n in pair)
        and pair[0] <= start <= end <= pair[1]
        for pair in ranges
    )


def validate_evidence_requests(diagnosis, evidence):
    """Validate declared references/dependencies without interpreting prose."""
    catalog = evidence_reference_catalog(evidence)
    fixes = {step.fix_id for step in diagnosis.plan}
    issues, observations = [], []
    counts = {"visible": 0, "unknown": 0, "legacy_unverified": 0, "contradicted": 0}

    def issue(code, number, message):
        issues.append({"code": code, "message": message, "path": f"/evidence_requests/{number}"})

    for number, request in enumerate(diagnosis.evidence_requests):
        scope = request.blocking_scope
        blocked = request.blocked_plan_ids
        # Exact schema-owned plan assessments are not observed input fields.
        # Do not infer intent from request.detail or change needs_more_info.
        if diagnosis.needs_more_info and scope == "current_plan":
            for plan_index, step in enumerate(diagnosis.plan):
                assessment_fields = {
                    f"plan[{plan_index}].numerics_impact",
                    f"plan[{plan_index}].throughput_impact",
                    f"/plan/{plan_index}/numerics_impact",
                    f"/plan/{plan_index}/throughput_impact",
                }
                if request.field in assessment_fields and step.fix_id in blocked:
                    issue(
                        "PLAN_ASSESSMENT_IS_NOT_OBSERVED_INPUT",
                        number,
                        "This field is a prospective plan assessment, not a measured input. "
                        "Candidate loss/throughput verification remains pending and mandatory. "
                        "State supported intended invariants and verification risks; if a real "
                        "source, policy, weighting, RNG or reference prerequisite is missing, "
                        "request that exact prerequisite instead. No result is presumed passing.",
                    )
                    observations.append(
                        {
                            "code": "PLAN_ASSESSMENT_IS_NOT_OBSERVED_INPUT",
                            "request_index": number,
                            "field": request.field,
                            "plan_id": step.fix_id,
                            "observation": "plan assessment field, not observed telemetry",
                            "candidate_measurement": "not_established_by_this_check",
                            "genuine_prerequisite_status": "unverified",
                        }
                    )
        if (
            len(set(blocked)) != len(blocked)
            or any(identifier not in fixes for identifier in blocked)
            or scope == "current_plan"
            and not blocked
            or scope in ("alternative_plan", "overall_feasibility")
            and blocked
            or scope is None
            and blocked
        ):
            issue(
                "INVALID_EVIDENCE_DEPENDENCY",
                number,
                "Evidence dependencies must name existing current steps and match their declared scope.",
            )
        ref, start, end = request.evidence_ref, request.source_line_start, request.source_line_end
        if ref is None:
            counts["legacy_unverified"] += 1
            if start is not None or end is not None:
                issue(
                    "INVALID_EVIDENCE_RANGE",
                    number,
                    "A source range requires an advertised source reference.",
                )
            continue
        entry = catalog.get(ref)
        if entry is None:
            issue(
                "UNKNOWN_EVIDENCE_REFERENCE",
                number,
                "Copy an identity from the delivered availability catalogue.",
            )
            counts["unknown"] += 1
            continue
        if (start is None) != (end is None) or (
            start is not None and (end < start or entry.get("kind") != "source")
        ):
            issue(
                "INVALID_EVIDENCE_RANGE",
                number,
                "Use both ordered source line bounds only with a source reference.",
            )
            counts["unknown"] += 1
            continue
        # A visible parent container cannot disprove a missing child field or
        # a semantic request that only mentions this container as context.
        visible = _visible(entry, start, end) and (
            entry.get("kind") == "source" or request.field == ref
        )
        counts["visible" if visible else "unknown"] += 1
        if visible and request.reason in ("missing", "redacted", "truncated"):
            counts["contradicted"] += 1
            issue(
                "EVIDENCE_AVAILABILITY_CONTRADICTED",
                number,
                "The exact declared source range or field is visible in this request; semantics may remain ambiguous.",
            )
            observations.append(
                {
                    "code": "EVIDENCE_AVAILABILITY_CONTRADICTED",
                    "request_index": number,
                    "evidence_ref": ref,
                    "source_line_start": start,
                    "source_line_end": end,
                    "observation": "visible supplied text; this availability check makes no runtime determination and does not override separate scoped observations",
                }
            )
    if (
        diagnosis.needs_more_info
        and diagnosis.plan
        and diagnosis.evidence_requests
        and all(
            request.blocking_scope == "alternative_plan" for request in diagnosis.evidence_requests
        )
    ):
        issue(
            "ALTERNATIVE_EVIDENCE_BLOCKS_CURRENT_PLAN",
            0,
            "Only alternative-plan evidence was requested; state a genuine current-plan or overall blocker instead.",
        )
    return (
        issues,
        observations,
        {
            "scope": "declared_availability_and_plan_dependencies_only",
            "counts": counts,
            "unstructured_prose_checked": False,
            "semantic_dependency_proven": False,
            "runtime_values_verified": False,
        },
    )
