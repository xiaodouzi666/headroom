"""Versioned product views. Stored evidence and default/download APIs stay unchanged."""

import re
from copy import deepcopy

PRODUCT_VIEW = "product-v1"


def wants_product(request):
    return request.headers.get("x-headroom-view") == PRODUCT_VIEW or (
        request.query_params.get("view") == PRODUCT_VIEW
    )


def _record(value):
    return value if isinstance(value, dict) else {}


def _pick(value, names):
    source = _record(value)
    return {name: deepcopy(source[name]) for name in names if name in source}


def product_message(value, fallback="Additional details are available in the downloaded report."):
    """Only system messages are translated; model evidence and source text are not."""
    if not isinstance(value, str) or not value.strip():
        return fallback
    normalized = re.sub(r"[_-]+", " ", value).lower()
    if re.search(
        r"unknown (?:charge|cost)|unconfirmed.*charge|unresolved (?:charge|cost)", normalized
    ):
        return "The provider has not supplied a complete usage total."
    if re.search(r"budget|cannot reserve|reservation|ledger", normalized):
        return "The run reached its model-usage limit."
    if re.search(r"provider profile|runtime profile|model access", normalized):
        return "Model access is unavailable."
    if "loss" in normalized and any(
        word in normalized for word in ("changed", "tolerance", "differ")
    ):
        return "The numerical comparison did not pass."
    if "reference" in normalized and "differ" in normalized:
        return "The numerical reference differs."
    if "patch" in normalized and any(word in normalized for word in ("missing", "unavailable")):
        return "A complete patch was not produced."
    if "timeout" in normalized or "timed out" in normalized or "deadline" in normalized:
        return "The run reached its time limit."
    if normalized.strip() in {"target met", "memory target reached"}:
        return "The requested memory target was reached."
    if "target" in normalized and ("unverified" in normalized or "without" in normalized):
        return "A completed run has not verified the repair."
    if "conflicting" in normalized or "capture" in normalized or "peak" in normalized:
        return "Some captured measurements are incomplete or inconsistent. Inspect the downloaded report."
    if "artifact unavailable" in normalized or "patch unavailable" in normalized:
        return "Some output files are unavailable. Inspect the downloaded report."
    if "529" in normalized or "provider" in normalized or "service unavailable" in normalized:
        return "The model service is unavailable."
    return fallback


def product_queue(value):
    result = _pick(value, ("capacity", "pending", "preparing", "running", "closing"))
    result["paused"] = _record(value).get("halted") is True
    return result


def product_usage(value):
    return _pick(
        value, ("calls", "total_cost_usd", "known_cost_usd", "unknown_cost_calls", "complete")
    )


def product_run(value):
    result = deepcopy(value)
    if "reason" in result:
        result["reason"] = product_message(result["reason"])
    if "usage" in result:
        result["usage"] = product_usage(result["usage"])
    for name in ("api_report_error",):
        if result.get(name):
            result[name] = "The report is not available yet."
    return result


EVENT_LABELS = {
    "run.started": "Run started",
    "baseline.started": "Baseline started",
    "baseline.oom": "Baseline ran out of memory",
    "baseline.completed": "Baseline completed",
    "evidence.built": "Evidence prepared",
    "annotate.done": "Stack labels ready",
    "diagnose.started": "Diagnosis started",
    "diagnose.done": "Diagnosis completed",
    "research.called": "Research started",
    "research.done": "Research completed",
    "patch.written": "Patch written",
    "patch.applied": "Patch applied",
    "patch.failed": "Patch unsuccessful",
    "verify.started": "Verification started",
    "verify.done": "Verification completed",
    "round.done": "Round completed",
    "target.met": "Memory target reached",
    "budget.exceeded": "Usage limit reached",
    "run.done": "Run completed",
    "run.failed": "Run failed",
    "needs_human": "Needs attention",
    "run.preflight": "Checking requirements",
    "run.queued": "Run queued",
    "evidence.started": "Preparing evidence",
    "patch.started": "Preparing patch",
    "report.started": "Preparing report",
    "report.written": "Report ready",
    "verify.reference": "Checking numerical reference",
    "budget.reserved": "Model request prepared",
}


def product_event(value):
    result = _pick(value, ("sequence", "kind", "created_at"))
    source = _record(value.get("data"))
    result["label"] = EVENT_LABELS.get(value.get("kind"), "Run update")
    data = _pick(source, ("model", "elapsed_seconds", "cost_usd", "target_met", "round"))
    if "cost_usd" not in source and isinstance(source.get("cost"), dict):
        data["cost_usd"] = source["cost"].get("usd")
    if "reason" in source:
        data["reason"] = product_message(source["reason"])
    result["data"] = data
    return result


def _verification(value):
    result = _pick(
        value,
        (
            "completed",
            "target_met",
            "peak_before",
            "peak_after",
            "reduction_pct",
            "step_ms_before",
            "step_ms_after",
            "throughput_regression_pct",
            "loss_equivalence",
            "numerical_basis",
            "comparison_precision",
            "loss_tolerance",
            "observed_precision_change",
            "max_loss_delta",
            "numerics_changed",
            "parameter_count_before",
            "parameter_count_after",
            "target",
            "units",
            "run_ids",
            "reference_run",
            "precision_evidence",
            "numerical_requirement",
            "numerical_requirement_evidence",
            "checks",
        ),
    )
    if "acceptance_scope" in _record(value):
        result["comparison_scope"] = value["acceptance_scope"]
    if isinstance(_record(value).get("notes"), list):
        # Keep scientific limitations; explain this one historical protocol in product language.
        known_note = (
            "PLAN T1.9 permits repository OOM acceptance with loss_equivalence=n/a "
            "when no reference is available; numerical equivalence remains unverified."
        )
        product_note = (
            "The original evaluation rules allowed this repository OOM run to pass without "
            "a numerical reference; numerical equivalence remains unverified (n/a)."
        )
        result["notes"] = [
            product_note if note == known_note else deepcopy(note) for note in value["notes"]
        ]
    checks = _record(result.get("checks"))
    result["checks"] = {
        ("numerical_comparison" if name == "numerical_acceptance" else name): checked
        for name, checked in checks.items()
        if name
        in {
            "baseline_capture",
            "target_mode_valid",
            "candidate_completed_required_steps",
            "finite_candidate_losses",
            "parameter_count_unchanged",
            "numerics_policy",
            "same_seed",
            "same_inputs",
            "same_effective_batch",
            "same_objective",
            "small_batch_reference_completed",
            "small_batch_reference_same_seed",
            "loss_decreases",
            "loss_series_aligned_to_updates",
            "loss_series_comparison_available",
            "original_workload_offload_reference",
            "original_workload_checkpoint_reference",
            "gpu_observation_clear",
            "loss_comparable",
            "loss_tolerance",
            "measured_cuda_peaks",
            "memory_target",
            "numerical_acceptance",
            "numerical_tier",
            "parameter_policy",
            "repository_no_reference_exception",
            "same_gpu_hardware",
            "throughput_limit",
        }
        and (type(checked) is bool or checked is None)
    }
    return result


def product_report(value):
    """Copy only rendered evidence; translate control/status prose separately."""
    source = _record(value)
    result = _pick(
        source,
        (
            "provenance",
            "summary",
            "display",
            "measurements",
            "evidence",
            "diagnosis",
            "peak_composition",
            "sources",
        ),
    )
    result["view"] = PRODUCT_VIEW
    result["run"] = _pick(source.get("run"), ("provenance", "annotations"))
    result["usage"] = product_usage(source.get("usage"))
    result["verification"] = _verification(source.get("verification"))
    # Allocation interpretation is scientific evidence; preserve its exact wording.
    result["allocator"] = _pick(
        source.get("allocator"),
        (
            "cached_free_bytes",
            "fragmentation_indicator",
            "fragmentation_confirmed",
            "history_complete",
            "note",
        ),
    )
    if isinstance(source.get("warnings"), list):
        result["warnings"] = [product_message(item) for item in source["warnings"]]
    selected = _record(source.get("selected_configuration"))
    result["selected_configuration"] = {"available": True} if selected else {}
    if selected.get("wrapper_replay") is not None:
        result["selected_configuration"]["wrapper_replay"] = True
    frontier = _record(source.get("pareto")).get("frontier")
    result["pareto"] = {
        "frontier": [
            _pick(row, ("round", "display_peak", "display_step", "numerics", "artifacts"))
            for row in (frontier if isinstance(frontier, list) else [])
            if isinstance(row, dict)
        ]
    }
    result["rounds"] = []
    for row in source.get("rounds", []) if isinstance(source.get("rounds"), list) else []:
        if not isinstance(row, dict):
            continue
        item = _pick(
            row,
            (
                "number",
                "provenance",
                "diff_status",
                "diff",
                "diff_summary",
                "display_verification",
            ),
        )
        item["decision"] = {
            "keep": "Kept",
            "retain": "Kept",
            "retained": "Kept",
            "revert": "Reverted",
            "reverted": "Reverted",
            "reject": "Not applied",
            "rejected": "Not applied",
        }.get(row.get("decision", row.get("status")), "Recorded")
        item["reason"] = product_message(row.get("reason"))
        item["verification"] = _verification(row.get("verification"))
        result["rounds"].append(item)
    return result


def product_evaluation(value):
    result = deepcopy(value)
    if "acceptance" in result:
        suite = result.pop("acceptance")
        if "target_gate_met" in suite:
            suite["threshold_met"] = suite.pop("target_gate_met")
        result["suite_result"] = suite
    for row in result.get("rows", []):
        if "acceptance_scope" in row:
            row["comparison_scope"] = row.pop("acceptance_scope")
        if row.get("search_stop_reason"):
            row["search_stop_reason"] = product_message(
                row["search_stop_reason"], "Analysis stopped."
            )
    return result
