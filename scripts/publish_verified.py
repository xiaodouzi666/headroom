#!/usr/bin/env python3
"""Prepare a reviewed gallery from existing records only. Never register routes or run workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from headroom.api.diagnosis_evidence import load_initial_diagnosis
from headroom.api.security import open_regular
from headroom.api.verified import VerifiedCatalog
from headroom.replay_curation import _inspection

PROJECT = Path(__file__).resolve().parents[1]
MAX_BYTES = 64 * 1024 * 1024


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(root, relative):
    with open_regular(root, relative, max_bytes=MAX_BYTES) as handle:
        return handle.read()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def clean(text):
    """Remove host paths; retain runtime/source-relative stack locations and code."""
    text = str(text).replace(str(PROJECT), "<project>")
    text = re.sub(r"/(?:home|Users)/[^/\s]+", "<user>", text)
    require(
        not re.search(r"(?:sk-[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{12,}|Bearer\s+\S+)", text),
        "Credential-like text is not publishable",
    )
    return text


def measurement(capture, shown=None):
    shown = shown or {}
    updates = capture.get("optimizer_update_observation", {})
    require(updates.get("logical_updates") == capture.get("steps"), "Update-count mismatch")
    return {
        "status": capture["status"],
        "peak_allocated_bytes": capture["peak_allocated_bytes"],
        "peak_is_exact": shown.get("peak_is_exact") is True,
        "optimizer_updates": capture["steps"],
        "parameter_count": capture["parameter_count"],
        "loss_series": [float(x) for x in capture.get("loss_series", [])],
    }


def verification(root, value, before, after, requested):
    basis = value.get("numerical_basis", "unavailable")
    count = (
        5
        if basis.endswith("first_five_backward_scalars")
        else (
            len(after.get("loss_series", []))
            if basis == "original_plan_full_backward_scalar_series"
            else 0
        )
    )
    reference = before
    reference_sha = None
    if value.get("reference_run"):
        path = Path(value["reference_run"]) / "result.json"
        require(path.is_relative_to(root / "runs"), "Reference outside runs")
        raw = read(root, path.relative_to(root).as_posix())
        reference = json.loads(raw)
        reference_sha = sha(raw)
    losses = reference.get("loss_series", [])[:count]
    candidate_losses = after.get("loss_series", [])[:count]
    if count:
        require(len(losses) == len(candidate_losses) == count, "Missing compared losses")
        delta = max(abs(x - y) for x, y in zip(losses, candidate_losses, strict=True))
        require(
            value.get("max_loss_delta") is not None
            and math.isclose(delta, value["max_loss_delta"], rel_tol=1e-12, abs_tol=1e-15),
            "Recorded loss delta does not match captures",
        )
    note = (
        "First five backward-loss scalars compared with an original-workload saved-tensor "
        "offload reference; the candidate completed 20 optimizer updates."
        if basis == "original_workload_offload_first_five_backward_scalars"
        else "The recorded full backward-loss series was compared."
        if count
        else "No numerical comparison was accepted."
    )
    return {
        "loss_equivalence": value.get("loss_equivalence", "unknown"),
        "numerical_basis": basis,
        "compared_loss_count": count,
        "comparison_losses": [float(x) for x in losses],
        "max_loss_delta": value.get("max_loss_delta"),
        "parameter_count_before": value.get("parameter_count_before"),
        "parameter_count_after": value.get("parameter_count_after"),
        "requested_updates": requested,
        "comparison_precision": value.get("comparison_precision"),
        "checks": {
            k: v for k, v in value.get("checks", {}).items() if type(v) is bool or v is None
        },
        "note": note,
    }, reference_sha


def reviewed_row(audit, selection, report_raw, report_path):
    """Read the three existing review formats without changing their scores."""
    run_id = selection["run_id"]
    kind = selection.get("audit_format", "legacy")
    if kind == "legacy":
        matches = [r for r in audit["rows"] if r.get("run_id") == run_id]
    elif kind == "final48_summary":
        matches = [r for r in audit["fixed_nine"]["rows"] if r.get("run_id") == run_id]
    elif kind == "browser_demo":
        matches = [audit] if audit.get("run_id") == run_id else []
    else:
        raise ValueError("Unsupported reviewed evidence format")
    require(len(matches) == 1, "Run missing or duplicated in independent audit")
    value = matches[0]
    if kind == "legacy":
        return value
    source = value["source_report"]
    require(
        source["sha256"] == sha(report_raw) and source["path"] == report_path,
        "Reviewed source report differs",
    )
    scenario = value.get("scenario_id") if kind == "final48_summary" else selection["scenario_id"]
    require(
        isinstance(scenario, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", scenario),
        "Invalid reviewed scenario",
    )
    return {"run_id": run_id, "scenario_id": scenario, "target": value["target_met"]}


def card_from_run(db, root, selection):
    run_id = selection["run_id"]
    row, _, assets, inspected = _inspection(db, root / "runs", run_id)
    report = json.loads(assets["report.json"])
    audit_path = selection["audit"]
    require(audit_path.startswith("reports/"), "Audit must be a project report")
    audit_raw = read(root, audit_path)
    audit = json.loads(audit_raw)
    reviewed = reviewed_row(
        audit,
        selection,
        assets["report.json"],
        (Path(row["run_dir"]).relative_to(root) / "report.json").as_posix(),
    )
    target_met = row.get("target_met") is True
    require(reviewed.get("target") is target_met, "Independent target result differs")
    require(target_met is selection["expected_target_met"], "Selection outcome differs")
    before = row["baseline"]
    after = row.get("after")
    selected = row.get("kept")
    require(not target_met or isinstance(selected, dict), "Successful selection missing")
    if target_met:
        require(
            selected["round"] in inspected["verified_attempt_rounds"],
            "Selected candidate was not independently checked",
        )
    database = Path(db.execute("PRAGMA database_list").fetchone()[2])
    bound = load_initial_diagnosis(row["run_dir"], database=database, project_root=root)
    require(bound is not None, "Initial diagnosis lacks exact evidence binding")
    diagnosis, binding, stacks = (bound[k] for k in ("diagnosis", "diagnosis_binding", "stacks"))
    requested = row["request"]["max_steps"]
    public_verification = None
    reference_sha = None
    if target_met:
        public_verification, reference_sha = verification(
            root, report["verification"], before, after, requested
        )
        require(
            report["verification"]["parameter_count_before"] == before["parameter_count"]
            and report["verification"]["parameter_count_after"] == after["parameter_count"],
            "Parameter evidence mismatch",
        )
        pct = str(
            Decimal(100)
            * (Decimal(before["peak_allocated_bytes"]) - Decimal(after["peak_allocated_bytes"]))
            / Decimal(before["peak_allocated_bytes"])
        )
        require(
            abs(Decimal(pct) - Decimal(report["summary"]["peak_reduction_pct"])) < Decimal("1e-20"),
            "Peak reduction mismatch",
        )
    last_attempt = None
    if not target_met:
        attempts = [r for r in report["rounds"] if r.get("verification", {}).get("after")]
        require(attempts, "Failure has no executed candidate")
        attempt = attempts[-1]
        value = attempt["verification"]
        av, _ = verification(root, value, before, value["after"], requested)
        last_attempt = {
            "round": attempt["number"],
            "kept": attempt.get("keep") is True,
            "target_met": value.get("target_met") is True,
            "reason": clean(attempt.get("reason", "")),
            "candidate": measurement(value["after"]),
            "verification": av,
        }
        patch = assets[attempt["patch"]]
    else:
        patch = assets["patch.diff"]
    require(len(patch) <= 1024 * 1024, "Patch too large")
    require(clean(patch.decode()).encode() == patch, "Patch needs manual redaction")
    research = row.get("research", {})
    require(
        not report["sources"] or report["sources"] == research.get("sources"),
        "Report sources lack research-record provenance",
    )
    sources = [
        {
            "url": s["url"],
            "title": clean(s["title"]),
            "provider": "Tavily",
            "version_match": s.get("version_match"),
        }
        for s in report["sources"]
    ]
    if sources:
        require(research.get("api_calls", 0) > 0, "Sources lack recorded research API calls")
    limitations = list(selection.get("limitations", []))
    if not patch.strip():
        limitations.append(
            "No code diff was recorded for this candidate; no patch download is provided."
        )
    if last_attempt:
        candidate = last_attempt["candidate"]
        limitations.append(
            f"The rejected candidate recorded {candidate['optimizer_updates']} completed "
            f"optimizer update(s); its final status was {candidate['status']}."
        )
    v = public_verification
    if v and any(
        v["checks"].get(k) is not True
        for k in ["same_inputs", "same_effective_batch", "same_objective"]
    ):
        limitations.append(
            "The historical loss comparison is recorded, but runtime pairing checks "
            "for inputs, effective batch and objective were not established."
        )
    if v and v["loss_equivalence"] == "within_tol":
        limitations.append("Losses matched within tolerance; they were not bit-identical.")
    if sources and any(s["version_match"] is not True for s in sources):
        limitations.append(
            "Retrieved documentation was not matched to the installed PyTorch version."
        )
    if not sources:
        limitations.append("No Tavily source links were recorded for this run.")
    source_hashes = {
        "report": sha(assets["report.json"]),
        "independent_audit": sha(audit_raw),
        "curation_fingerprint": inspected["fingerprint"],
    }
    if reference_sha:
        source_hashes["numerical_reference_capture"] = reference_sha
    card = {
        "run_id": run_id,
        "scenario_id": reviewed["scenario_id"],
        "title": selection["title"],
        "description": selection["description"],
        "created_at": row["created_at"],
        "provenance": "live",
        "outcome": "target_met" if target_met else "not_solved",
        "target": row["target"],
        "selected_round": selected["round"] if target_met else None,
        "before": measurement(before, report["measurements"]["before"]),
        "after": measurement(after, report["measurements"]["after"]) if target_met else None,
        "peak_reduction_pct": report["summary"]["peak_reduction_pct"] if target_met else None,
        "verification": public_verification,
        "last_attempt": last_attempt,
        "diagnosis": diagnosis,
        "diagnosis_binding": binding,
        "stacks": stacks,
        "sources": sources,
        "limitations": limitations,
        "source_sha256": source_hashes,
        "downloads": {},
    }
    report_data = encoded({k: v for k, v in card.items() if k != "downloads"})
    text = [
        f"# {card['title']}",
        "",
        f"Run: {run_id}",
        "Outcome: " + ("Historical target met" if target_met else "Not solved — here is why"),
        "",
        card["description"],
        "",
        f"Peak before: {before['peak_allocated_bytes']} bytes",
        f"Peak after: {after['peak_allocated_bytes']} bytes"
        if target_met
        else "No candidate was selected as a successful repair.",
    ]
    if v:
        text += [
            f"Loss comparison: {v['loss_equivalence']}; {v['compared_loss_count']} scalars",
            v["note"],
            f"Parameters: {v['parameter_count_before']} → {v['parameter_count_after']}",
            f"Candidate optimizer updates: {after['steps']}",
        ]
    if last_attempt:
        text += [
            f"Rejected candidate status: {last_attempt['candidate']['status']}",
            f"Rejected candidate optimizer updates: {last_attempt['candidate']['optimizer_updates']}",
        ]
    text += ["", "## Limitations", *["- " + line for line in limitations], ""]
    outputs = {}
    artifacts = [
        ("report_json", "report.json", report_data),
        ("report_markdown", "report.md", "\n".join(text).encode()),
    ]
    if patch.strip():
        artifacts.insert(0, ("patch", "patch.diff", patch))
    for key, name, raw in artifacts:
        path = f"verified-assets/{run_id}/{name}"
        outputs[path] = raw
        card["downloads"][key] = {"path": path, "sha256": sha(raw), "bytes": len(raw)}
    provenance = {
        "run_id": run_id,
        "scenario_id": card["scenario_id"],
        "source_report": str(Path(row["run_dir"]).relative_to(root) / "report.json"),
        "audit": audit_path,
        "outcome": card["outcome"],
        "source_sha256": source_hashes,
        "diagnosis_binding": binding,
        "verified_attempt_rounds": inspected["verified_attempt_rounds"],
        "source_evidence": inspected["source_evidence"],
    }
    return card, outputs, provenance


def prepare(root, selection_path):
    root = Path(root).resolve()
    selection_document = json.loads(read(root, selection_path))
    selections = selection_document["runs"]
    require(1 <= len(selections) <= 30, "Invalid selection count")
    outputs, cards, provenance = {}, [], []
    for selection in selections:
        database_name = selection.get("database", "runs/headroom.db")
        require(
            database_name in {"runs/headroom.db", "runs/public-api/headroom.db"},
            "Unsupported recorded Store",
        )
        database = root / database_name
        require(database.is_file() and not database.is_symlink(), "Recorded Store is unavailable")
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            card, files, source = card_from_run(db, root, selection)
        cards.append(card)
        outputs.update(files)
        provenance.append(source)
    document = {
        "schema_version": 1,
        "publication_status": "prepared_not_enabled",
        "selection_policy": selection_document.get(
            "selection_policy",
            "Latest preserved live target-met run per requested success scenario; "
            "latest terminated failure with an executed candidate for s1 and nanoGPT.",
        ),
        "runs": cards,
    }
    catalog = VerifiedCatalog.model_validate(document)
    outputs["verified-runs.json"] = encoded(catalog.model_dump())
    return outputs, {
        "prepared_only": True,
        "new_model_calls": 0,
        "new_gpu_runs": 0,
        "routes_registered": False,
        "historical_records_modified": False,
        "runs": provenance,
        "output_sha256": {p: sha(raw) for p, raw in sorted(outputs.items())},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--selection", required=True, help="Project-relative reviewed selection JSON"
    )
    parser.add_argument("--output", default="public-evidence")
    parser.add_argument(
        "--write", action="store_true", help="Write new prepared files, no API activation"
    )
    parser.add_argument(
        "--check", action="store_true", help="Re-extract and compare existing prepared files"
    )
    parser.add_argument("--receipt", help="Project-relative preparation audit receipt")
    args = parser.parse_args(argv)
    require(not (args.write and args.check), "Choose write or check")
    outputs, receipt = prepare(PROJECT, args.selection)
    destination = PROJECT / args.output
    require(destination.resolve().is_relative_to(PROJECT), "Output outside project")
    for relative, raw in outputs.items():
        path = destination / relative
        if args.check or path.exists():
            require(read(destination, relative) == raw, "Prepared output differs: " + relative)
        elif args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            require(
                not any(p.is_symlink() for p in [path.parent, *path.parent.parents]),
                "Symlink output directory",
            )
            with path.open("xb") as handle:
                handle.write(raw)
    if args.receipt and args.write:
        path = PROJECT / args.receipt
        require(path.resolve().is_relative_to(PROJECT), "Receipt outside project")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(encoded(receipt))
    print(
        json.dumps(
            {
                "prepared_only": True,
                "checked_existing": args.check,
                "files": len(outputs),
                "target_met": sum(r["outcome"] == "target_met" for r in receipt["runs"]),
                "not_solved": sum(r["outcome"] == "not_solved" for r in receipt["runs"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
