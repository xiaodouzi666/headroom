"""Evidence-preserving, offline report rendering. JSON is the source of display numbers."""

import hashlib
import html
import json
import re
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path, PurePosixPath
from urllib.parse import quote, urlsplit
from uuid import uuid4

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from headroom.api.security import open_regular

MAX_ROUND_DIFF_BYTES = 2 * 1024 * 1024  # PatchProposal permits at most 512,000 Unicode characters.

NUMBER_UNIT = re.compile(r"(?<![\w.])([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(GiB|GB|%)")


def _json_default(value):
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError("Reports require JSON-compatible finite values")


def _clone(value):
    return json.loads(json.dumps(value, allow_nan=False, default=_json_default))


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or abs(number) > Decimal("1e30"):
        return None
    return number


def _number(value, unit="", places=3):
    number = _decimal(value)
    if number is None:
        return "unknown"
    with localcontext() as context:
        context.prec = 64
        return f"{number:.{places}f}{(' ' + unit) if unit != '%' and unit else unit}"


def _gb(value):
    number = _decimal(value)
    return _number(number / Decimal(1_000_000_000), "GB") if number is not None else "unknown"


def _text(value):
    """Escape raw HTML, Markdown links/images, table/heading/newline injection."""
    if value is None:
        return "unknown"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    value = html.escape(str(value), quote=True).replace("|", "&#124;")
    value = re.sub(r"([\\`*_{}\[\]()#!])", r"\\\1", value)
    return value.replace("\r", " ").replace("\n", " ")


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Artifact links must be safe relative paths")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or ".." in path.parts
        or value.startswith("//")
        or ":" in value
        or any(ord(c) < 32 for c in value)
        or str(path) == "."
    ):
        raise ValueError("Artifact links must stay inside the report directory")
    return str(path)


def _source_url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username:
        return None
    return quote(value, safe=":/?#=&%+@,;~.-_")


def _analysis(evidence):
    if not isinstance(evidence, dict):
        return {}
    return evidence.get("analysis", evidence if "header" in evidence else {})


def _measure(result, analysis):
    result = result if isinstance(result, dict) else {}
    header = analysis.get("header", {})
    exact = header.get("peak_is_exact", result.get("capture_complete"))
    warnings = list(header.get("warnings", []))
    values = {}
    for key in ("peak_allocated_bytes", "peak_reserved_bytes"):
        raw = result.get(key, header.get(key))
        if type(raw) is not int or raw < 0:
            raw = None
        other = header.get(key)
        if raw is not None and other is not None and raw != other:
            exact = False
            warnings.append(f"Conflicting {key} in Lab result and evidence header")
        values[key] = raw
    if result.get("capture_complete") is False:
        exact = False
    step = _decimal(result.get("step_ms_median", result.get("step_ms")))
    return {
        **values,
        "status": result.get("status", "unknown"),
        "peak_is_exact": exact if isinstance(exact, bool) else None,
        "peak_basis": "exact capture" if exact is True else "partial or unverified capture",
        "step_ms": str(step) if step is not None and step >= 0 else None,
        "steps": result.get("steps"),
        "loss_series": result.get("loss_series"),
        "shared_gpu": result.get("shared_gpu"),
        "warnings": warnings,
    }


def _pareto_report(value):
    """Display supplied retained points; never infer dominance in the renderer."""
    value = _clone(value) if isinstance(value, dict) else {}
    for group in ("points", "frontier"):
        rows = value.get(group, [])
        value[group] = []
        for point in rows if isinstance(rows, list) else []:
            if not isinstance(point, dict):
                continue
            point["display_peak"] = _number(point.get("peak_gb"), "GB")
            point["display_step"] = (
                _number(point.get("step_ms"), "ms")
                if point.get("timing_trusted") is True
                else "unknown / shared timing"
            )
            links = {}
            for key, path in point.get("artifacts", {}).items():
                try:
                    links[key] = _relative(path)
                except ValueError:
                    continue
            point["artifacts"] = links
            value[group].append(point)
    return value


def numerical_basis_label(value):
    return {
        "original_plan_first_five_backward_scalars": "Observed first five backward losses (original plan)",
        "original_plan_full_backward_scalar_series": "Observed full backward-loss sequence (original plan)",
        "repository_no_reference_exception": "Repository without reference; numerical equivalence unverified",
        "unavailable": "Comparison unavailable",
    }.get(value, "Comparison basis not recorded")


def _round_report(row, provenance):
    """Retain verifier values and round identity without certifying a candidate."""
    row = _clone(row)
    verification = row.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    after = verification.get("after", row.get("after"))
    after = after if isinstance(after, dict) else {}
    peak_after = verification.get("peak_after")
    row["provenance"] = row.get("provenance") or provenance or "unknown"
    row["display_verification"] = {
        "peak_before": _number(verification.get("peak_before"), "GB"),
        "peak_after": _number(peak_after, "GB")
        if _decimal(peak_after) is not None
        else _gb(after.get("peak_allocated_bytes")),
        "reduction_pct": _number(verification.get("reduction_pct"), "%"),
        "step_ms_before": _number(verification.get("step_ms_before"), "ms"),
        "step_ms_after": _number(verification.get("step_ms_after"), "ms"),
        "throughput_regression_pct": _number(verification.get("throughput_regression_pct"), "%"),
        "max_loss_delta": _number(verification.get("max_loss_delta"), places=6),
        "completed": verification.get("completed")
        if type(verification.get("completed")) is bool
        else None,
        "target_met": verification.get("target_met")
        if type(verification.get("target_met")) is bool
        else None,
        "loss_equivalence": verification.get("loss_equivalence") or "unknown",
        "numerical_basis": numerical_basis_label(verification.get("numerical_basis")),
        "comparison_precision": verification.get("comparison_precision") or "unknown",
        "loss_tolerance": _number(verification.get("loss_tolerance"), places=6),
        "observed_precision_change": verification.get("observed_precision_change"),
    }
    row["display_peak_after"] = row["display_verification"]["peak_after"]
    row["diff_sha256"] = None
    row["diff_bytes"] = None
    if row.get("patch"):
        try:
            row["patch"] = _relative(row["patch"])
        except ValueError:
            row["patch"] = None
            row["diff"] = None
            row["diff_status"] = "unavailable"
            row["diff_summary"] = "Stored patch path is invalid."
        else:
            # Only generate_report may promote this to an available persisted artifact.
            row["diff"] = None
            row["diff_status"] = "not_loaded"
            row["diff_summary"] = "Stored patch has not been loaded."
    elif isinstance(row.get("diff"), str):
        row["diff_status"] = "provided_text"
        row["diff_summary"] = (
            row.get("diff_summary") or "Supplied inline diff; no stored patch verified."
        )
    else:
        row["diff"] = None
        row["diff_status"] = "unavailable"
        row["diff_summary"] = "No patch was recorded for this round."
    return row


def _load_round_diff(output, row, warnings):
    """Load an actual kept or reverted candidate patch without following symlinks."""
    if row["diff_status"] != "not_loaded":
        return
    try:
        with open_regular(output, row["patch"], max_bytes=MAX_ROUND_DIFF_BYTES) as handle:
            raw = handle.read(MAX_ROUND_DIFF_BYTES + 1)
        if len(raw) > MAX_ROUND_DIFF_BYTES:
            raise ValueError("Patch exceeds the report limit")
        diff = raw.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        row["diff_status"] = "unavailable"
        row["diff_summary"] = "Stored patch is missing, unsafe, oversized, or not UTF-8."
        row["patch"] = None
        warnings.append(
            "Round patch unavailable: " + str(row.get("number", row.get("round", "unknown")))
        )
        return
    row.update(
        diff=diff,
        diff_status="available",
        diff_sha256=hashlib.sha256(raw).hexdigest(),
        diff_bytes=len(raw),
    )
    if not diff:
        row["diff_summary"] = (
            "Empty code diff; consult this round's recorded plan and configuration changes."
        )
        return
    try:
        parsed = PatchSet(diff)
        if not parsed:
            raise UnidiffParseError("No file changes")
        row["diff_summary"] = (
            f"{len(parsed)} file(s), {parsed.added} added line(s), {parsed.removed} removed line(s)."
        )
        row["diff_files"] = [entry.path for entry in parsed]
    except (UnidiffParseError, ValueError):
        # Failed/invalid patch attempts are still evidence; do not hide their bytes.
        row["diff_summary"] = "Stored patch text; unified-diff summary unavailable."


def build_report(
    run,
    *,
    evidence=None,
    rounds=None,
    verification=None,
    usage=None,
    diagnosis=None,
    sources=None,
    artifacts=None,
):
    """Build a serializable report without reading artifacts or executing any workload.

    evidence is {before: bundle, after: bundle}, or one before bundle. Lab results
    are run.baseline and verification.after (fallback run.after). All judgments
    originate with the supplied verifier; this renderer never certifies a fix.
    """
    run = _clone(run)
    if not isinstance(run, dict):
        raise TypeError("Run must be a dictionary")
    evidence, verification = _clone(evidence or {}), _clone(verification or {})
    rounds, diagnosis = _clone(rounds or []), _clone(diagnosis or {})
    usage, sources = _clone(usage or {}), _clone(sources or [])
    artifacts = {
        key: _relative(value) for key, value in (artifacts or {}).items() if value is not None
    }
    before_analysis = _analysis(evidence.get("before", evidence))
    after_analysis = _analysis(evidence.get("after", {}))
    before = _measure(run.get("baseline", verification.get("before", {})), before_analysis)
    after = _measure(verification.get("after", run.get("after", {})), after_analysis)
    warnings = [*before["warnings"], *after["warnings"]]
    for group in [usage, *usage.get("by_model", [])]:
        unknown = group.get("unknown_cost_calls")
        if group.get("complete") is False or (type(unknown) is int and unknown > 0):
            if group.get("total_cost_usd") is not None:
                warnings.append("A total cost with unknown calls was replaced by unknown")
            group["total_cost_usd"] = None
    target_met = verification.get("target_met", run.get("target_met"))
    target_met = target_met if isinstance(target_met, bool) else None
    if target_met is True and after["status"] != "completed":
        target_met = None
        warnings.append("A target-met claim without a completed after-run is unverified")
    reduction = None
    b, a = before["peak_allocated_bytes"], after["peak_allocated_bytes"]
    if b and a is not None and before["peak_is_exact"] and after["peak_is_exact"]:
        reduction = (Decimal(b) - Decimal(a)) * 100 / Decimal(b)
    step_change = None
    old, new = _decimal(before["step_ms"]), _decimal(after["step_ms"])
    if old is not None and old > 0 and new is not None:
        step_change = (new - old) * 100 / old
    composition = []
    for category, value in before_analysis.get("category_bytes", {}).items():
        valid = type(value) is int and value >= 0
        fraction = Decimal(value) * 100 / Decimal(b) if valid and b else None
        composition.append(
            {
                "category": category,
                "bytes": value if valid else None,
                "gb": _gb(value if valid else None),
                "percent_of_peak": _number(fraction, "%"),
            }
        )
    header = before_analysis.get("header", {})
    display = {
        "peak_before": _gb(b),
        "peak_after": _gb(a),
        "reserved_before": _gb(before["peak_reserved_bytes"]),
        "reserved_after": _gb(after["peak_reserved_bytes"]),
        "peak_reduction": _number(reduction, "%"),
        "step_before": _number(old, "ms"),
        "step_after": _number(new, "ms"),
        "step_time_change": _number(step_change, "%"),
        "cached_free": _gb(header.get("cached_free_bytes")),
    }
    for cause in diagnosis.get("root_causes", []):
        cause["display_estimate"] = _number(cause.get("bytes_gb"), "GB")
        confidence = _decimal(cause.get("confidence"))
        cause["display_confidence"] = _number(
            confidence * 100 if confidence is not None else None, "%"
        )
    for item in diagnosis.get("plan", []):
        item["display_expected_saving"] = _number(item.get("expected_saving_gb"), "GB")
    rounds = [_round_report(row, run.get("provenance")) for row in rounds]
    return {
        "schema_version": 1,
        "scope": "Report of supplied artifacts; generation does not certify diagnosis or repair",
        "units": "GB is decimal bytes divided by 1,000,000,000",
        "run": run,
        "status": run.get("status", "unknown"),
        "summary": {
            "target": run.get("target"),
            "target_met": target_met,
            "loss_equivalence": verification.get("loss_equivalence", "unknown"),
            "numerical_basis": verification.get("numerical_basis", "unavailable"),
            "numerical_basis_label": numerical_basis_label(verification.get("numerical_basis")),
            "peak_reduction_pct": str(reduction) if reduction is not None else None,
            "step_time_change_pct": str(step_change) if step_change is not None else None,
        },
        "measurements": {"before": before, "after": after},
        "display": display,
        "peak_composition": composition,
        "diagnosis": diagnosis,
        "rounds": rounds,
        "pareto": _pareto_report(run.get("pareto")),
        "verification": verification,
        "allocator": {
            "cached_free_bytes": header.get("cached_free_bytes"),
            "fragmentation_indicator": header.get("fragmentation_indicator"),
            "fragmentation_confirmed": header.get("fragmentation_confirmed"),
            "history_complete": header.get("history_complete"),
            "note": "A reserved-minus-allocated gap alone does not prove fragmentation.",
        },
        "sources": sources,
        "usage": usage,
        "artifacts": artifacts,
        "evidence": evidence,
        "warnings": warnings,
    }


def render_markdown(report):
    d, summary = report["display"], report["summary"]
    before, after = report["measurements"]["before"], report["measurements"]["after"]
    lines = [
        "# Headroom report",
        "",
        "## Summary",
        "",
        f"Run: {_text(report['run'].get('run_id', report['run'].get('id')))}",
        f"Evidence provenance: {_text(report['run'].get('provenance', 'unknown'))}.",
        (
            f"Status: {_text(report['status'])}; target: {_text(summary['target'])}; "
            f"target met: {_text(summary['target_met'])}."
        ),
        "",
        "| Measurement | Before | After |",
        "|---|---|---|",
        f"| Execution | {_text(before['status'])} | {_text(after['status'])} |",
        f"| Peak allocated | {d['peak_before']} | {d['peak_after']} |",
        f"| Peak reserved | {d['reserved_before']} | {d['reserved_after']} |",
        f"| Peak evidence | {_text(before['peak_basis'])} | {_text(after['peak_basis'])} |",
        f"| Step time | {d['step_before']} | {d['step_after']} |",
        "",
        f"Peak reduction: {d['peak_reduction']}; step-time change: {d['step_time_change']}.",
        f"Numerical equivalence: {_text(summary['loss_equivalence'])}.",
        f"Comparison basis: {_text(summary['numerical_basis_label'])}.",
        "Observed loss agreement alone does not prove identical inputs, effective batch or objective.",
        "Step-time change describes measured intervals, not a separate throughput benchmark.",
        "Memory uses decimal GB. Missing measurements remain unknown.",
        "",
        "## Root causes",
        "",
        "Diagnostic hypotheses and estimated sizes:",
    ]
    causes = report["diagnosis"].get("root_causes", [])
    if not causes:
        lines.append("No diagnosis available.")
    for cause in causes:
        lines.append(
            f"- {_text(cause.get('title'))}: {cause['display_estimate']}; "
            f"confidence {cause['display_confidence']}; evidence "
            f"{_text(cause.get('evidence_refs', []))}."
        )
    annotations = report["run"].get("annotations")
    if isinstance(annotations, dict):
        lines += [
            "",
            "## Stack annotations",
            "",
            "Status: " + _text(annotations.get("status")) + ".",
            _text(annotations.get("note", "Model labels do not replace allocator evidence.")),
        ]
        if "annotations" in report["artifacts"]:
            link = quote(_relative(report["artifacts"]["annotations"]), safe="/-._~")
            lines.append(f"[Annotation evidence]({link})")
    lines += ["", "## Fixes", ""]
    for item in report["diagnosis"].get("plan", []):
        lines.append(
            f"- Planned: {_text(item.get('title'))}; expected saving "
            f"{item['display_expected_saving']}; {_text(item.get('description'))}."
        )
    if not report["rounds"]:
        lines.append("No repair round recorded.")
    for row in report["rounds"]:
        measured = row["display_verification"]
        lines += [
            f"### Round {_text(row.get('number', row.get('round')))}",
            "",
            (
                f"Decision: {_text(row.get('decision', row.get('status')))}; "
                f"reason: {_text(row.get('reason'))}; "
                f"provenance: {_text(row['provenance'])}."
            ),
            "This round's candidate is shown even if reverted; the final retained configuration is separate.",
            f"Diff summary: {_text(row['diff_summary'])}",
        ]
        if row["provenance"] == "offline_fixture":
            lines.append("Offline fixture only; this round is not GPU acceptance evidence.")
        if row.get("plan_step"):
            lines.append("Recorded plan: " + _text(row["plan_step"]) + ".")
        if row.get("requested_information"):
            lines.append("Information requested before continuing:")
            for item in row["requested_information"]:
                lines.append("- " + _text(item))
        if row.get("supplement_request"):
            lines.append("Required planning supplement: " + _text(row["supplement_request"]))
        if row["diff_status"] == "available":
            path = quote(_relative(row["patch"]), safe="/-._~")
            lines += [
                f"[Round candidate patch]({path})",
                f"Patch SHA-256: {_text(row['diff_sha256'])}; bytes: {_text(row['diff_bytes'])}.",
                "The candidate diff applies to that round's current source, not necessarily the original baseline.",
            ]
        if isinstance(row.get("diff"), str) and row["diff"]:
            lines += ["", "<pre>" + html.escape(row["diff"]) + "</pre>", ""]
        lines += [
            "",
            "| Round verification | Recorded before | Candidate |",
            "|---|---|---|",
            f"| Peak allocated | {measured['peak_before']} | {measured['peak_after']} |",
            f"| Step time | {measured['step_ms_before']} | {measured['step_ms_after']} |",
            f"| Completed | — | {_text(measured['completed'])} |",
            f"| Target met | — | {_text(measured['target_met'])} |",
            f"| Loss equivalence | — | {_text(measured['loss_equivalence'])} |",
            f"| Comparison basis | — | {_text(measured['numerical_basis'])} |",
            f"| Comparison precision | — | {_text(measured['comparison_precision'])} |",
            f"| Loss tolerance | — | {_text(measured['loss_tolerance'])} |",
            f"| Observed precision change | — | {_text(measured['observed_precision_change'])} |",
            f"| Peak reduction | — | {measured['reduction_pct']} |",
            f"| Step-time change | — | {measured['throughput_regression_pct']} |",
            f"| Maximum loss delta | — | {measured['max_loss_delta']} |",
            "",
            "Before/after values come from this round's verifier; they are not inferred from neighboring rounds.",
            "",
            "| Round check | Result |",
            "|---|---|",
        ]
        verification = row.get("verification")
        verification = verification if isinstance(verification, dict) else {}
        checks = verification.get("checks")
        if isinstance(checks, dict) and checks:
            lines += [f"| {_text(name)} | {_text(value)} |" for name, value in checks.items()]
        else:
            lines.append("| Verification available | unknown |")
        for note in verification.get("notes", []):
            lines.append("- " + _text(note))
        lines.append("")
    for key, label in (("patch", "Patch diff"), ("env", "Environment changes")):
        if key in report["artifacts"]:
            link = quote(_relative(report["artifacts"][key]), safe="/-._~")
            lines.append(f"[{label}]({link})")
    lines += [
        "",
        "## Retained configurations",
        "",
        "| Round | Peak | Step time | Numerics | Configuration |",
        "|---|---|---|---|---|",
    ]
    frontier = report.get("pareto", {}).get("frontier", [])
    if not frontier:
        lines.append("| none | unknown | unknown | unverified | No configuration kept |")
    for point in frontier:
        links = []
        for key in ("patch", "env", "cli"):
            if point.get("artifacts", {}).get(key):
                path = quote(_relative(point["artifacts"][key]), safe="/-._~")
                links.append(f"[{key}]({path})")
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(point.get("round")),
                    point["display_peak"],
                    point["display_step"],
                    _text(point.get("numerics")),
                    " / ".join(links) or "unavailable",
                ]
            )
            + " |"
        )
    for note in report.get("pareto", {}).get("limitations", []):
        lines.append("- " + _text(note))
    for key in ("pareto_json", "pareto_md"):
        if key in report["artifacts"]:
            path = quote(_relative(report["artifacts"][key]), safe="/-._~")
            lines.append(f"[{key}]({path})")
    lines += ["", "## Verification", "", "| Check | Result |", "|---|---|"]
    checks = report["verification"].get("checks", {})
    if isinstance(checks, dict):
        lines += [f"| {_text(name)} | {_text(value)} |" for name, value in checks.items()]
    else:
        lines.append(f"| Checks | {_text(checks)} |")
    if not checks:
        lines.append("| Verification available | unknown |")
    lines.append(f"| Numerical equivalence | {_text(summary['loss_equivalence'])} |")
    lines += ["", "## Timeline", ""]
    for key, label in (("before_png", "Before timeline"), ("after_png", "After timeline")):
        if key in report["artifacts"]:
            link = quote(_relative(report["artifacts"][key]), safe="/-._~")
            lines.append(f"![{label}]({link})")
        else:
            lines.append(f"{label}: unavailable.")
    lines += [
        "",
        "## Peak composition",
        "",
        "Allocation-origin categories are heuristic labels; retained evidence carries their basis.",
        "",
        "| Category | Size | Share of before peak |",
        "|---|---|---|",
    ]
    for row in report["peak_composition"]:
        lines.append(f"| {_text(row['category'])} | {row['gb']} | {row['percent_of_peak']} |")
    if not report["peak_composition"]:
        lines.append("| unavailable | unknown | unknown |")
    allocator = report["allocator"]
    lines += [
        "",
        "## Allocator notes",
        "",
        (
            f"Cached-free gap: {d['cached_free']}; indicator: "
            f"{_text(allocator['fragmentation_indicator'])}; confirmed: "
            f"{_text(allocator['fragmentation_confirmed'])}."
        ),
        allocator["note"],
        "",
        "## Sources",
        "",
    ]
    research = report["run"].get("research", {})
    if isinstance(research, dict):
        lines.append(
            "Research status: "
            + _text(research.get("status", "unknown"))
            + "; reason: "
            + _text(research.get("reason", "see operation records"))
            + "."
        )
    if not report["sources"]:
        lines.append("No runtime research sources recorded.")
    for source in report["sources"]:
        title, url = _text(source.get("title", source.get("url"))), _source_url(source.get("url"))
        lines.append(
            f"- [{title}]({url})" if url else f"- {title} (URL omitted: unsupported scheme)"
        )
    usage = report["usage"]
    lines += [
        "",
        "## Model usage & cost",
        "",
        (
            f"Known subtotal USD: {_text(usage.get('known_cost_usd'))}; "
            f"total USD: {_text(usage.get('total_cost_usd'))}; "
            f"unknown-cost calls: {_text(usage.get('unknown_cost_calls'))}."
        ),
        "",
        "| Model | Calls | Input tokens | Output tokens | Total USD |",
        "|---|---|---|---|---|",
    ]
    for row in usage.get("by_model", []):
        lines.append(
            "| "
            + " | ".join(
                _text(row.get(k))
                for k in ("model", "calls", "input_tokens", "output_tokens", "total_cost_usd")
            )
            + " |"
        )
    admissions = usage.get("admission_counts", {})
    if admissions.get("local_estimate", 0):
        lines += [
            "",
            (
                "Admission used a local token estimate with a risk margin. This reservation is not "
                "a provider billing upper bound or an actual charge; actual charges may exceed it."
            ),
        ]
    lines += ["", "## Evidence limitations", "", _text(report["scope"])]
    lines += ["- " + _text(warning) for warning in report["warnings"]]
    if before["shared_gpu"] or after["shared_gpu"]:
        lines.append("- Shared GPU observed; timing can be affected by other workloads.")
    return "\n".join(lines) + "\n"


def check_report_numbers(document, markdown):
    """Every rendered GB/GiB/percentage token must exist in JSON string values."""
    available = set()

    def visit(value):
        if isinstance(value, str):
            available.update((Decimal(n), unit) for n, unit in NUMBER_UNIT.findall(value))
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(document)
    return [
        f"{number} {unit}"
        for number, unit in NUMBER_UNIT.findall(html.unescape(markdown))
        if (Decimal(number), unit) not in available
    ]


def generate_report(output_dir, run, **kwargs):
    """Write report.json then report.md atomically per file. Paths are trusted host outputs."""
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = build_report(run, **kwargs)
    # Only link existing regular files within the report bundle; never follow outside symlinks.
    missing = []
    for key, relative in list(report["artifacts"].items()):
        artifact = (output / relative).resolve()
        if not artifact.is_relative_to(output) or not artifact.is_file():
            missing.append(key)
            report["warnings"].append(f"Artifact unavailable: {key}")
            del report["artifacts"][key]
    for group in ("points", "frontier"):
        for point in report.get("pareto", {}).get(group, []):
            for key, relative in list(point.get("artifacts", {}).items()):
                artifact = (output / relative).resolve()
                if not artifact.is_relative_to(output) or not artifact.is_file():
                    report["warnings"].append(f"Retained configuration artifact unavailable: {key}")
                    del point["artifacts"][key]
    for row in report["rounds"]:
        _load_round_diff(output, row, report["warnings"])
    report["unavailable_artifacts"] = missing
    markdown = render_markdown(report)
    if check_report_numbers(report, markdown):
        raise ValueError("Rendered measurement does not originate in report JSON")
    payloads = {
        "report.json": json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        "report.md": markdown,
    }
    for name, content in payloads.items():
        temporary = output / f".{name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(output / name)
        finally:
            temporary.unlink(missing_ok=True)
    return report
