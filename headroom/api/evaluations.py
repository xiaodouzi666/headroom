"""Explicitly curated, read-only evaluation publication. No workload or credential access."""

import json
import math
import re
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException

from headroom.api.security import open_regular
from headroom.budget import money
from headroom.evaluation import CONDITIONS, SEARCH_MODES, campaign_tables, public_outcomes

IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]{0,99}\Z")


def _label(value):
    return value if isinstance(value, str) and LABEL.fullmatch(value) else None


def _number(value):
    return (
        value
        if type(value) in (float, int) and abs(value) <= 1e30 and math.isfinite(value)
        else None
    )


def _percentage(value):
    # Report summaries intentionally encode Decimal results as strings. Preserve
    # their precision instead of losing a measured value or rounding via float.
    if not isinstance(value, str):
        return _number(value)
    if len(value) > 160 or not re.fullmatch(
        r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value
    ):
        return None
    try:
        number = Decimal(value)
        if (
            number.is_finite()
            and number.copy_abs() <= Decimal("1e30")
            and len(number.as_tuple().digits) <= 80
            and abs(number.as_tuple().exponent) <= 80
        ):
            return value
    except InvalidOperation:
        pass
    return None


def _public_row(row, provenance):
    if not isinstance(row, dict):
        raise TypeError("Invalid row")
    result = {
        name: _label(row.get(name))
        for name in (
            "scenario_id",
            "policy_name",
            "status",
            "group",
            "ground_truth",
            "truth_status",
            "first_cause",
            "search_stop_reason",
        )
    }
    for name, allowed in (
        ("loss_equivalence", {"identical", "within_tol", "changed", "n/a", "unknown"}),
        (
            "numerical_basis",
            {
                "original_plan_first_five_backward_scalars",
                "original_plan_full_backward_scalar_series",
                "repository_no_reference_exception",
                "unavailable",
            },
        ),
        ("acceptance_scope", {"standard", "repository"}),
        ("search_mode", set(SEARCH_MODES)),
    ):
        value = row.get(name)
        result[name] = value if isinstance(value, str) and value in allowed else None
    result.update(public_outcomes(row))
    result["policy_name"] = result["policy_name"] or "default"
    result["status"] = result["status"] or "unknown"
    result["provenance"] = (
        "offline_fixture"
        if provenance == "offline_fixture"
        else row.get("provenance")
        if row.get("provenance") in {"live", "offline_fixture"}
        else "unknown"
    )
    result["condition"] = row.get("condition") if row.get("condition") in CONDITIONS else None
    for name in ("target_met", "first_cause_matches", "baseline_target_met"):
        result[name] = row.get(name) if type(row.get(name)) is bool else None
    for name in (
        "peak_before_bytes",
        "peak_after_bytes",
        "peak_reduction_pct",
        "throughput_change_pct",
        "step_time_change_pct",
        "rounds",
        "search_rounds_executed",
        "first_target_met_round",
        "wall_seconds",
    ):
        result[name] = (
            _percentage(row.get(name))
            if name in {"peak_reduction_pct", "throughput_change_pct", "step_time_change_pct"}
            else _number(row.get(name))
        )
    try:
        result["cost_usd"] = (
            str(money(row["cost_usd"])) if row.get("cost_usd") is not None else None
        )
    except (TypeError, ValueError, ArithmeticError):
        result["cost_usd"] = None
    result["billing_complete"] = row.get("billing_complete", result["cost_usd"] is not None) is True
    result["cost_upper_usd"] = None
    result["cost_basis"] = "actual" if result["cost_usd"] is not None else None
    if (
        result["cost_usd"] is None
        and result["billing_complete"]
        and row.get("cost_basis") == "verified_upper_bound"
    ):
        try:
            upper = row.get("cost_upper_usd")
            if upper is not None:
                result["cost_upper_usd"] = str(money(upper))
                result["cost_basis"] = "verified_upper_bound"
        except (TypeError, ValueError, ArithmeticError):
            pass
    if result["cost_usd"] is None and result["cost_upper_usd"] is None:
        result["billing_complete"] = False
    for name, length in (("run_id", 32), ("source_sha256", 64)):
        value = row.get(name)
        result[name] = (
            value
            if isinstance(value, str) and re.fullmatch("[a-f0-9]{" + str(length) + "}", value)
            else None
        )
    policy = row.get("policy", {})
    if not isinstance(policy, dict):
        policy = {}
    result["policy"] = {
        name: value
        for name, value in policy.items()
        if (
            name in {"allow_numerics_change", "allow_model_change", "allow_batch_grad_accum"}
            and type(value) is bool
        )
        or (name == "max_throughput_regression_pct" and _number(value) is not None)
    }
    if set(policy) != set(result["policy"]):
        raise ValueError("Unsupported or invalid effective policy")
    return result


def _registry(root):
    try:
        with open_regular(root, "public-evaluations.json", 65536) as handle:
            document = json.load(handle)
    except FileNotFoundError:
        return []
    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError("Invalid publication manifest")
    entries = document.get("campaigns")
    if not isinstance(entries, list) or len(entries) > 20:
        raise ValueError("Invalid publication list")
    identifiers = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("Invalid publication entry")
        identifier, title = entry.get("id"), entry.get("title")
        if (
            not isinstance(identifier, str)
            or not IDENTIFIER.fullmatch(identifier)
            or identifier in identifiers
        ):
            raise ValueError("Invalid publication identifier")
        if not isinstance(title, str) or not 1 <= len(title) <= 120:
            raise ValueError("Invalid publication title")
        identifiers.add(identifier)
    return entries


def _campaign(root, entry):
    with open_regular(
        root, "published-evaluations/" + entry["id"] + ".json", 2 * 1024 * 1024
    ) as handle:
        source = json.load(handle)
    if not isinstance(source, dict) or source.get("mode") != "campaign":
        raise ValueError("Invalid campaign")
    provenance = source.get("provenance")
    if provenance not in {"live", "offline_fixture"}:
        raise ValueError("Campaign provenance is required")
    rows = source.get("rows")
    if not isinstance(rows, list) or len(rows) > 1000:
        raise ValueError("Invalid campaign rows")
    document = campaign_tables(
        {
            "mode": "campaign",
            "search_mode": (
                source.get("search_mode") if source.get("search_mode") in SEARCH_MODES else None
            ),
            "provenance": provenance,
            "status": _label(source.get("status")) or "unknown",
            "rows": [_public_row(row, provenance) for row in rows],
        }
    )
    return {"id": entry["id"], "title": entry["title"], **document}


def register_evaluations(app, data_root):
    router = APIRouter()

    def registry():
        try:
            return _registry(data_root)
        except (OSError, ValueError, TypeError, UnicodeError):
            raise HTTPException(503, "Published evaluation catalog is unavailable") from None

    def read(entry):
        try:
            return _campaign(data_root, entry)
        except (OSError, ValueError, TypeError, ArithmeticError, KeyError, UnicodeError):
            raise HTTPException(503, "Published evaluation evidence is unavailable") from None

    @router.get("/api/evaluations")
    def evaluations():
        items = []
        for entry in registry():
            document = read(entry)
            items.append(
                {key: document[key] for key in ("id", "title", "status", "provenance", "summary")}
            )
        return {"status": "published" if items else "pending", "evaluations": items}

    @router.get("/api/evaluations/{identifier}")
    def evaluation(identifier: str):
        entry = next((entry for entry in registry() if entry["id"] == identifier), None)
        if entry is None:
            raise HTTPException(404, "Published evaluation not found")
        return read(entry)

    app.include_router(router)
