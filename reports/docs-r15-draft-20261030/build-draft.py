"""Build report-only R15 document drafts; never writes source docs or public data."""

import copy
import difflib
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FILES = ("README.md", "docs/RESULTS.md", "docs/DEVPOST.md")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bound(path, pointer):
    path = ROOT / path
    return {
        "path": str(path.relative_to(ROOT)),
        "sha256": digest(path),
        "bytes": path.stat().st_size,
        "json_pointer": pointer,
    }


def pointer(value, path):
    for part in path.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def claim(path, field):
    return {
        "value": pointer(json.loads((ROOT / path).read_text()), field),
        "source": bound(path, field),
    }


def replace_once(text, before, after):
    assert text.count(before) == 1, before[:150]
    return text.replace(before, after, 1)


summary_path = "reports/r15-20261030-review/terminal-review-20261030/summary.json"
summary = json.loads((ROOT / summary_path).read_text())
campaign_path = "runs/repair-followup/execution-r15-20261030/campaign.json"
campaign = json.loads((ROOT / campaign_path).read_text())
assert campaign["status"] == "finished" and summary["provisional"] is False
assert summary["metrics"]["memory_targets"] == 1 and len(summary["rows"]) == 9
assert summary["source_revision"] == "964b6581d0322a6699e81eae7619129f0e90d3e7"
previous_path = "reports/docs-r13-20261030/numbers-r13-v1.json"
previous = json.loads((ROOT / previous_path).read_text())
r14_path = "reports/r14-20261030-review/docs-draft/numbers-r14-draft-v1.json"
r14 = json.loads((ROOT / r14_path).read_text())

claims = {}
for name, field in {
    "targets": "memory_targets",
    "raw_category_matches": "raw_category_matches",
    "valid_correct_first_causes": "valid_correct_first_causes",
    "first_round_ready": "valid_ready_diagnoses",
    "first_round_ready_valid_correct": "ready_valid_correct_first_causes",
    "executed_cases": "attempted_rows",
    "fixed_denominator": "fixed_denominator",
    "minimum_targets": "minimum_memory_targets",
}.items():
    claims["latest." + name] = claim(summary_path, "/metrics/" + field)
for name, field in {
    "charged_upper_usd": "charged_total_usd",
    "known_actual_subtotal_usd": "known_actual_subtotal_usd",
    "actual_total_usd": "actual_total_usd",
}.items():
    claims["latest." + name] = claim(summary_path, "/metrics/cost/" + field)
claims["latest.rows"] = claim(summary_path, "/rows")
claims["latest.source_revision"] = claim(summary_path, "/source_revision")
claims["latest.execution_status"] = claim(campaign_path, "/status")
final_inputs = {"valid": [], "ready": []}
for row in campaign["rows"]:
    sid = row["scenario_id"]
    path = str((Path(row["run_dir"]) / "diagnosis.json").relative_to(ROOT))
    for key, field in [("valid", "/valid"), ("ready", "/ready_for_patch")]:
        name = f"latest.final.{sid}.{key}"
        claims[name] = claim(path, field)
        final_inputs[key].append(name)
for kind, input_names in final_inputs.items():
    claims["latest.final_" + kind] = {
        "value": sum(claims[name]["value"] is True for name in input_names),
        "inputs": input_names,
        "formula": "count input values that are exactly true",
    }

old_path = "runs/evaluation/live/20261027T022818939585Z-151818b1/jobs/84f929ba8ace49b3829df6455419641d/report.json"
new_path = (
    "runs/repair-followup/execution-r15-20261030/jobs/0317411d868e41309c09974d1f573cb2/report.json"
)
new_diag = "runs/repair-followup/execution-r15-20261030/jobs/0317411d868e41309c09974d1f573cb2/rounds/01/diagnosis.json"
for label, path in [("previous.s3", old_path), ("selected.s3", new_path)]:
    for name, field in {
        "before_bytes": "/measurements/before/peak_allocated_bytes",
        "after_bytes": "/measurements/after/peak_allocated_bytes",
        "before_updates": "/measurements/before/steps",
        "after_updates": "/measurements/after/steps",
        "before_losses": "/measurements/before/loss_series",
        "after_losses": "/measurements/after/loss_series",
        "checks": "/verification/checks",
        "target_met": "/verification/target_met",
        "loss_equivalence": "/verification/loss_equivalence",
        "numerical_basis": "/verification/numerical_basis",
        "params_before": "/verification/parameter_count_before",
        "params_after": "/verification/parameter_count_after",
        "notes": "/verification/notes",
    }.items():
        claims[label + "." + name] = claim(path, field)
claims["selected.s3.first_category"] = claim(new_diag, "/diagnosis/root_causes/0/category")
claims["selected.s3.authored_cause"] = claim(
    summary_path, "/rows/2/first_round_diagnosis/ground_truth"
)
claims["selected.s3.first_valid_correct"] = claim(
    summary_path, "/rows/2/first_round_diagnosis/valid_and_correct"
)
assert (
    claims["previous.s3.after_bytes"]["value"]
    == claims["selected.s3.after_bytes"]["value"]
    == 648419840
)
assert claims["selected.s3.target_met"]["value"] is True
assert claims["selected.s3.before_losses"]["value"] == claims["selected.s3.after_losses"]["value"]
assert len(claims["selected.s3.before_losses"]["value"]) == 20
assert all(
    claims["selected.s3.checks"]["value"][key] is None
    for key in ["same_inputs", "same_effective_batch", "same_objective"]
)
with localcontext() as context:
    context.prec = 40
    before = Decimal(claims["selected.s3.before_bytes"]["value"])
    after = Decimal(claims["selected.s3.after_bytes"]["value"])
    claims["selected.s3.before_GB"] = {
        "value": str(before / 10**9),
        "inputs": ["selected.s3.before_bytes"],
        "formula": "bytes / 1000000000",
    }
    claims["selected.s3.after_GB"] = {
        "value": str(after / 10**9),
        "inputs": ["selected.s3.after_bytes"],
        "formula": "bytes / 1000000000",
    }
    claims["selected.s3.reduction_pct"] = {
        "value": str((before - after) * 100 / before),
        "inputs": ["selected.s3.before_bytes", "selected.s3.after_bytes"],
        "formula": "(before_bytes-after_bytes)*100/before_bytes",
    }

publication = json.loads(
    (ROOT / "reports/r15-20261030-review/publication-applied.json").read_text()
)
public = ROOT / "public-evidence/public-evaluations.json"
assert digest(public) == publication["manifest_sha256"]
(OUT / "publication-snapshot.json").write_bytes(public.read_bytes())
claims["publication.entries"] = claim(
    str((OUT / "publication-snapshot.json").relative_to(ROOT)), "/campaigns"
)
claims["publication.old_entries_preserved"] = claim(
    "reports/r15-20261030-review/publication-applied.json", "/old_entries_and_files_unchanged"
)
assert (
    len(claims["publication.entries"]["value"]) == 11
    and claims["publication.entries"]["value"][0]["id"] == "r15-terminal-20261030"
)

selections = copy.deepcopy(previous["historical_best_selection"])
selected = next(row for row in selections if row["scenario_id"] == "s3_eval_no_grad_missing")
selected.update(
    selection="latest campaign wins exact lowest successful after-byte tie",
    previous_run_id=selected["run_id"],
    run_id="0317411d868e41309c09974d1f573cb2",
    source_commit=summary["source_revision"],
    source_claim="selected.s3.after_bytes",
    pairing_complete=False,
    compared_scalars_identical=True,
)

summary_prose = "Historically, **5 of 9** distinct scenarios have a run that met its configured memory target. The best single evaluation reached **3 of 9**. The latest October 30 evaluation reached **1 of 9**. Its first saved diagnosis rounds produced **3 of 9** valid correct first-cause diagnoses and **2 of 9** ready for patching; raw first-category matches were **4 of 9**. At the final stopping point, **1 of 9** diagnoses remained ready. <!-- numbers: summary -->"
for name in FILES:
    current = ROOT / name
    before_dir = OUT / "before"
    before_dir.mkdir(exist_ok=True)
    (before_dir / name.replace("/", "__")).write_bytes(current.read_bytes())
    text = (ROOT / "reports/r14-20261030-review/docs-draft" / name).read_text()
    if name != "docs/RESULTS.md":
        oldline = next(
            line for line in text.splitlines() if line.startswith("Historically, **5 of 9**")
        )
        text = replace_once(
            text,
            oldline,
            summary_prose
            + (
                " The target of six successful scenarios has not been reached."
                if name == "docs/DEVPOST.md"
                else ""
            ),
        )
        text = text.replace(
            "latest October 30 evaluation met none of its nine memory targets",
            "latest October 30 evaluation met one of nine memory targets",
        )
    if name == "README.md":
        text = replace_once(
            text,
            "20 losses identical; workload pairing matched | <!-- numbers: best.s3_eval_no_grad_missing -->",
            "20 scalar losses identical; workload pairing incomplete | <!-- numbers: best.s3_eval_no_grad_missing -->",
        )
        text = replace_once(
            text,
            "s3 has a paired, identical full loss series; s1 and s4 compare the first five backward-loss values against documented references. s2 uses a tolerance-based comparison, and s2/s8 lack complete input, effective-batch and objective pairing.",
            "The selected s3 and s8 runs have identical recorded scalar loss series but incomplete input, effective-batch and objective pairing. An earlier s3 run had complete pairing, as preserved in the history. s1 and s4 compare the first five backward-loss values against documented references, and s2 uses a tolerance-based comparison with incomplete workload pairing.",
        )
    if name == "docs/DEVPOST.md":
        text = replace_once(
            text,
            "with all 20 compared losses identical and matched inputs, effective batch, objective and seed.",
            "with all 20 recorded scalar losses identical; input, effective-batch and objective pairing was not established for the selected latest run.",
        )
    if name == "docs/RESULTS.md":
        oldline = next(
            line
            for line in text.splitlines()
            if line.startswith("The latest October 30 evaluation (R14)")
        )
        text = replace_once(
            text,
            oldline,
            "The latest October 30 evaluation (R15) met **1/9 memory targets**. Its first saved diagnosis rounds produced **3/9 valid correct first causes**, **4/9 raw first-category matches**, and **2/9 ready diagnoses**, including **1/9 ready valid correct first causes**. At the final stopping point, **5/9** diagnoses were valid and **1/9** remained ready. The unchanged memory-target threshold is **6/9**, which was not met. Historical coverage remains five distinct successful scenarios and a best single evaluation of **3/9**. <!-- numbers: summary -->",
        )
        row = "| [R15](../reports/r15-20261030-review/terminal-review-20261030/review.md) | 1/9 | 4/9 | 3/9 | 1/9 | 0.65563404 |"
        r14row = next(line for line in text.splitlines() if line.startswith("| [R14]"))
        text = replace_once(text, r14row, r14row + "\n" + row)
        oldline = next(
            line
            for line in text.splitlines()
            if line.startswith("All five completed all nine scenarios.")
        )
        text = replace_once(
            text,
            oldline,
            "All six completed all nine scenarios. Fully known actual totals remain unavailable; the amounts include conservative bounds and are not presented as exact provider billing. The R13, R14 and R15 amounts each cover only their own new runs and exclude earlier retained amounts. R15 has a known actual subtotal of $0.62755938 and a conservatively charged total of $0.65563404; its exact actual total remains unknown. Ready counts in this table refer to the first saved round; R14 finished with zero final diagnoses ready, and R15 finished with one. Historical successes remain separate. Nano label coverage was 8/8 in R8 and 7/8 in R9; neither reached 80% heuristic agreement on any of those eight cases. Identifier coverage is not label accuracy.",
        )
        oldline = next(
            line
            for line in text.splitlines()
            if line.startswith("| s3: evaluation autograd | Activations")
        )
        text = replace_once(
            text,
            oldline,
            "| s3: evaluation autograd | Activations | Category mismatch / target met | 2.436 → 0.648 (−73.38%) | 20 identical recorded scalars; input/batch/objective pairing unknown; seed matched. | [2026-10-30 / 964b658](../reports/r15-20261030-review/terminal-review-20261030/review.md) |",
        )
        text = replace_once(
            text,
            "| s3: evaluation autograd | 84f929ba8ace49b3829df6455419641d | 20 → 20 | 20 | 37,791,744 |",
            "| s3: evaluation autograd | 0317411d868e41309c09974d1f573cb2 | 20 → 20 | 20 | 37,791,744 |",
        )
        s8note = next(
            line for line in text.splitlines() if line.startswith("The new s8 run has exactly")
        )
        note = "The selected s3 run also ties the earlier lowest successful after-peak byte count (648,419,840), so the same latest-on-tie rule selects the October 30 run at revision 964b658. Its20 recorded scalars are identical and the seed matches, but input/effective-batch/objective pairing is unknown; the earlier fully paired s3 result is retained in the history. The selected s3 first category is retained_graph rather than the authored activations reference, so target success is not a correct-first-cause score."
        note = note.replace("Its20", "Its 20")
        text = replace_once(text, s8note, s8note + "\n\n" + note)
    draft = OUT / "docs-draft" / name
    draft.parent.mkdir(parents=True, exist_ok=True)
    draft.write_text(text)

manifest = {
    "schema": "headroom.final48.numbers-update.v1",
    "version": "r15-draft-v1",
    "created_at": datetime.now(UTC).isoformat(),
    "prepared_only": True,
    "apply_authorized": False,
    "public_documents_changed": False,
    "scope": "R15 report-only draft. Never apply over a later complete evaluation; source docs remain R13 until root decides.",
    "previous_numbers": {"path": previous_path, "sha256": digest(ROOT / previous_path)},
    "previous_r14_draft": {"path": r14_path, "sha256": digest(ROOT / r14_path)},
    "claims": claims,
    "historical_union_targets": 5,
    "best_single_targets": 3,
    "historical_best_selection": selections,
    "selection_rule": "lowest successful after-byte peak; latest recorded campaign breaks exact ties",
    "s3_tie": {
        "previous_run_id": "84f929ba8ace49b3829df6455419641d",
        "new_run_id": "0317411d868e41309c09974d1f573cb2",
        "previous_after_bytes": 648419840,
        "new_after_bytes": 648419840,
        "old_pairing_complete": True,
        "new_pairing_complete": False,
        "loss_series_length": 20,
        "loss_series_identical": True,
        "new_first_cause_correct": False,
        "manual_or_research_controls_counted": False,
    },
    "count_boundaries": {
        "completed_campaign_rows_in_new_summary_table": 6,
        "reviewed_public_catalog_entries": 11,
        "catalog_is_not_full_fixed_nine_campaign_count": True,
        "R11_partial_attempted": 2,
        "R12_partial_attempted": 1,
    },
    "documents": {
        name: {
            "source_sha256": digest(ROOT / name),
            "draft_path": str((OUT / "docs-draft" / name).relative_to(ROOT)),
            "draft_sha256": digest(OUT / "docs-draft" / name),
        }
        for name in FILES
    },
    "validation": {
        "source_hashes_and_json_pointers": "pending",
        "all_history_bytes_preserved": "pending",
        "source_docs_unchanged": "pending",
        "no_publication": True,
        "no_models_or_gpu": True,
    },
}
(OUT / "numbers-r15-draft-v1.json").write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
)
diff = "".join(
    "".join(
        difflib.unified_diff(
            (ROOT / name).read_text().splitlines(True),
            (OUT / "docs-draft" / name).read_text().splitlines(True),
            fromfile="a/" + name,
            tofile="b/" + name,
        )
    )
    for name in FILES
)
(OUT / "document-draft.diff").write_text(diff)
print(
    json.dumps(
        {
            "status": "draft_only",
            "manifest_sha256": digest(OUT / "numbers-r15-draft-v1.json"),
            "claims": len(claims),
            "source_docs_changed": False,
        },
        indent=2,
    )
)
