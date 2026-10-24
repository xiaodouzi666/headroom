"""Compare measured Lab runs without converting missing evidence into a pass."""

import math
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from headroom.verify.precision import derive_precision

# Original-plan acceptance gates. Diagnostic observations (including optional
# workload pairing) must not silently become additional mandatory requirements.
REQUIRED_CHECKS = (
    "baseline_capture",
    "target_mode_valid",
    "candidate_completed_required_steps",
    "finite_candidate_losses",
    "numerics_policy",
    "same_seed",
    "numerical_acceptance",
    "parameter_policy",
    "measured_cuda_peaks",
    "same_gpu_hardware",
)


class VerifyReport(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    completed: bool
    peak_before: float | None
    peak_after: float | None
    reduction_pct: float | None
    step_ms_before: float | None
    step_ms_after: float | None
    loss_equivalence: Literal["identical", "within_tol", "changed", "n/a"]
    target_met: bool
    notes: list[str]
    checks: dict[str, bool | None]
    max_loss_delta: float | None = None
    throughput_regression_pct: float | None = None
    numerics_changed: bool = False
    parameter_count_before: int | None = None
    parameter_count_after: int | None = None
    target: str
    units: str = "GB = 1e9 bytes; percentages are relative to baseline"
    run_ids: dict[str, str | None] = Field(default_factory=dict)
    reference_run: str | None = None
    acceptance_scope: Literal["standard", "repository"] = "standard"
    numerical_basis: str = "unavailable"
    comparison_precision: Literal["fp32", "bf16"] = "fp32"
    loss_tolerance: float = 1e-3
    observed_precision_change: bool | None = None
    precision_evidence: dict = Field(default_factory=dict)


def _number(value, *, positive=False):
    if type(value) not in (int, float):
        return None
    try:
        if not math.isfinite(value):
            return None
    except OverflowError:
        return None
    if value < 0 or (positive and value == 0):
        return None
    return value


def _capture_valid(result):
    return (
        result.get("protocol") == "headroom.lab.v1"
        and result.get("capture_complete") is True
        and result.get("cleanup_verified") is True
    )


def _losses(result):
    values = result.get("loss_series")
    if not isinstance(values, list) or not values:
        return None
    for value in values:
        if type(value) not in (int, float):
            return None
        try:
            if not math.isfinite(value):
                return None
        except OverflowError:
            return None
    return values


def _parameters(result):
    value = result.get("parameter_count")
    if type(value) is not int or value < 0 or result.get("parameter_count_complete") is not True:
        return None
    if result.get("parameter_count_source") != "lab_module_parameter_hooks":
        return None
    return value


def _same_seed(left, right):
    first, second = left.get("env", {}), right.get("env", {})
    seed = first.get("seed")
    return (
        type(seed) is int
        and seed == second.get("seed")
        and all(first.get("seeded", {}).get(k) is True for k in ("python", "torch", "numpy"))
        and all(second.get("seeded", {}).get(k) is True for k in ("python", "torch", "numpy"))
        and first.get("deterministic_algorithms") is True
        and second.get("deterministic_algorithms") is True
    )


def _gpu_clear(result):
    return result.get("shared_gpu") is False and result.get("gpu_observation_complete") is True


def parse_target(target):
    if target in {"fix-oom", "reclaim"}:
        return target, None
    match = re.fullmatch(r"fit:([0-9]+(?:\.[0-9]+)?)(GB|GiB)", target)
    if not match:
        raise ValueError("Target must be fix-oom, reclaim, fit:<positive>GB or fit:<positive>GiB")
    amount = Decimal(match.group(1))
    if amount <= 0:
        raise ValueError("Fit target must be positive")
    return "fit", amount * (Decimal(10**9) if match.group(2) == "GB" else Decimal(2**30))


def compare_runs(
    baseline: Mapping,
    candidate: Mapping,
    *,
    target="fix-oom",
    policy=None,
    reference: Mapping | None = None,
    pairing: Mapping | None = None,
    numerics_impact="none",
    precision=None,
    tolerance=None,
    required_steps=20,
    reclaim_reduction_pct=30,
    acceptance_scope="standard",
) -> VerifyReport:
    """Apply PLAN C.5, with the explicit T1.9 repository no-reference exception.

    Loss states describe the prescribed observed scalar comparison, not a proof
    of workload equivalence. Stronger pairing observations remain diagnostic.
    """
    mode, fit_bytes = parse_target(target)
    if acceptance_scope not in {"standard", "repository"}:
        raise ValueError("Unsupported acceptance scope")
    if type(required_steps) is not int or required_steps < 1:
        raise ValueError("required_steps must be a positive integer")
    if numerics_impact not in {"none", "minor", "significant"} or precision not in {
        None,
        "fp32",
        "bf16",
    }:
        raise ValueError("Unsupported numerical impact or precision")
    precision_evidence = derive_precision(baseline, candidate, reference)
    explicit_precision = precision is not None
    if precision is None:
        precision = precision_evidence["comparison_precision"]
    else:
        # Compatibility for trusted direct callers; production derives the mode
        # from Lab observations rather than accepting a model's precision claim.
        precision_evidence["source"] = "explicit caller precision; observations retained separately"
        precision_evidence["notes"] = [
            "Comparison precision was supplied explicitly by the caller; it is not an automatic runtime inference."
        ]
        precision_evidence["comparison_precision"] = precision
    observed_change = precision_evidence["observed_change"]
    if _number(reclaim_reduction_pct) is None or reclaim_reduction_pct > 100:
        raise ValueError("Reclaim reduction must be between 0 and 100 percent")
    policy = dict(policy or {})
    pairing = dict(pairing or {})
    for key in ("allow_numerics_change", "allow_model_change", "allow_batch_grad_accum"):
        if key in policy and type(policy[key]) is not bool:
            raise ValueError("Policy flags must be booleans")
    regression_limit = policy.get("max_throughput_regression_pct", 25)
    if _number(regression_limit) is None:
        raise ValueError("Throughput regression limit must be finite and nonnegative")
    default_tolerance = 2e-2 if precision == "bf16" else 1e-3
    # Caller can tighten the original bound, never silently relax it.
    tolerance = default_tolerance if tolerance is None else tolerance
    if _number(tolerance) is None or tolerance > default_tolerance:
        raise ValueError("Tolerance cannot exceed the original precision-specific bound")
    before_bytes = _number(baseline.get("peak_allocated_bytes"), positive=True)
    after_bytes = _number(candidate.get("peak_allocated_bytes"), positive=True)
    before = before_bytes / 1e9 if before_bytes is not None else None
    after = after_bytes / 1e9 if after_bytes is not None else None
    reduction = (
        (before_bytes - after_bytes) / before_bytes * 100 if before_bytes and after_bytes else None
    )
    before_ms = _number(baseline.get("step_ms_median"), positive=True)
    after_ms = _number(candidate.get("step_ms_median"), positive=True)
    regression = (after_ms / before_ms - 1) * 100 if before_ms and after_ms else None
    if regression is not None and not math.isfinite(regression):
        regression = None
    notes = list(precision_evidence["notes"])
    baseline_oom = baseline.get("status") == "oom"
    baseline_valid = _capture_valid(baseline) and baseline.get("status") in {"oom", "completed"}
    completed = (
        candidate.get("status") == "completed"
        and _capture_valid(candidate)
        and candidate.get("steps") == required_steps
    )
    candidate_losses = _losses(candidate)
    numerical_change = (
        numerics_impact != "none"
        or observed_change is True
        or (explicit_precision and precision == "bf16" and observed_change is None)
    )
    param_before, param_after = _parameters(baseline), _parameters(candidate)
    parameter_equal = (
        (param_before == param_after) if None not in (param_before, param_after) else None
    )
    checks = {
        "baseline_capture": baseline_valid,
        "target_mode_valid": mode != "reclaim" or baseline.get("status") == "completed",
        "candidate_completed_required_steps": completed,
        "finite_candidate_losses": candidate_losses is not None,
        "parameter_count_unchanged": parameter_equal,
        "numerics_policy": not numerical_change or policy.get("allow_numerics_change", False),
        "same_seed": _same_seed(baseline, candidate),
        "same_inputs": pairing.get("same_inputs")
        if type(pairing.get("same_inputs")) is bool
        else None,
        "same_effective_batch": pairing.get("same_effective_batch")
        if type(pairing.get("same_effective_batch")) is bool
        else None,
        "same_objective": pairing.get("same_objective")
        if type(pairing.get("same_objective")) is bool
        else None,
    }
    if parameter_equal is None:
        notes.append("Parameter count is missing or its Lab hook coverage is incomplete.")
    if parameter_equal is False:
        notes.append(
            "Measured model parameter count changed; a smaller model is not a memory repair."
        )
    comparator = reference if baseline_oom else baseline
    equivalence = "n/a"
    max_delta = None
    numerics_ok = False
    reference_valid = (
        comparator is not None
        and _capture_valid(comparator)
        and comparator.get("status") == "completed"
        and comparator.get("steps") == required_steps
    )
    other_losses = _losses(comparator) if comparator is not None else None
    # Backward scalars and optimizer updates are different units: gradient
    # accumulation legitimately captures multiple losses per update.
    aligned_to_updates = (
        candidate_losses is not None
        and other_losses is not None
        and len(candidate_losses) == required_steps
        and len(other_losses) == required_steps
    )
    reference_seed = comparator is not None and _same_seed(comparator, candidate)
    if baseline_oom:
        checks["small_batch_reference_completed"] = reference_valid
        checks["small_batch_reference_same_seed"] = reference_seed
        checks["loss_decreases"] = bool(
            candidate_losses
            and len(candidate_losses) >= 2
            and candidate_losses[-1] < candidate_losses[0]
        )
        count = 5
        series_usable = (
            candidate_losses is not None
            and other_losses is not None
            and len(candidate_losses) >= count
            and len(other_losses) >= count
        )
        numerical_basis = "original_plan_first_five_backward_scalars"
        notes.append(
            "OOM comparison uses the original small-batch reference's first five backward scalars."
        )
    else:
        count = len(candidate_losses) if candidate_losses is not None else 0
        series_usable = (
            candidate_losses is not None
            and other_losses is not None
            and len(candidate_losses) == len(other_losses)
        )
        numerical_basis = "original_plan_full_backward_scalar_series"
    checks["loss_series_aligned_to_updates"] = aligned_to_updates
    checks["loss_series_comparison_available"] = bool(series_usable)
    comparable = reference_valid and reference_seed and checks["same_seed"] and series_usable
    # Retain stronger evidence without inventing it for generic user programs.
    checks["loss_comparable"] = bool(
        comparable
        and all(
            checks[k] is True for k in ("same_inputs", "same_effective_batch", "same_objective")
        )
    )
    if series_usable:
        max_delta = max(
            abs(a - b) for a, b in zip(candidate_losses[:count], other_losses[:count], strict=True)
        )
        if not math.isfinite(max_delta):
            max_delta = None
    if comparable and max_delta is not None:
        numerics_ok = max_delta <= tolerance
        equivalence = (
            "identical" if max_delta == 0 else ("within_tol" if numerics_ok else "changed")
        )
        if numerical_change:
            equivalence = "changed"
    else:
        numerical_basis = "unavailable"
        notes.append(
            "Loss equivalence is n/a: the original-plan scalar comparison lacks a completed same-seed reference or aligned finite losses."
        )
    if not checks["loss_comparable"]:
        notes.append(
            "Loss states describe the original-plan observed scalar comparison; matching inputs, effective batch and objective are not established. This is not proof of workload equivalence."
        )
    no_reference_exception = (
        acceptance_scope == "repository"
        and baseline_oom
        and reference is None
        and candidate_losses is not None
        and not numerical_change
    )
    checks["repository_no_reference_exception"] = no_reference_exception
    if no_reference_exception:
        numerical_basis = "repository_no_reference_exception"
        notes.append(
            "PLAN T1.9 permits repository OOM acceptance with loss_equivalence=n/a when no reference is available; numerical equivalence remains unverified."
        )
    if parameter_equal is False and not policy.get("allow_model_change", False):
        equivalence, numerics_ok = "changed", False
    if numerical_change:
        notes.append(
            "Numerics changed; this requires explicit policy permission and the original tolerance."
        )
    checks["loss_tolerance"] = numerics_ok
    checks["numerical_acceptance"] = numerics_ok or no_reference_exception
    checks["parameter_policy"] = parameter_equal is True or (
        parameter_equal is False and policy.get("allow_model_change", False)
    )
    gpu_pair = all(r.get("env", {}).get("device") == "cuda" for r in (baseline, candidate))
    hardware_equal = gpu_pair and (
        baseline.get("env", {}).get("gpu_name") == candidate.get("env", {}).get("gpu_name")
        and baseline.get("env", {}).get("gpu_total_memory_bytes")
        == candidate.get("env", {}).get("gpu_total_memory_bytes")
        and baseline.get("env", {}).get("gpu_name") is not None
    )
    checks["measured_cuda_peaks"] = gpu_pair and all(
        type(result.get("peak_allocated_bytes")) is int
        and _number(result.get("peak_allocated_bytes"), positive=True) is not None
        and type(result.get("env", {}).get("gpu_total_memory_bytes")) is int
        and result["peak_allocated_bytes"] <= result["env"]["gpu_total_memory_bytes"]
        for result in (baseline, candidate)
    )
    checks["same_gpu_hardware"] = hardware_equal
    checks["gpu_observation_clear"] = _gpu_clear(baseline) and _gpu_clear(candidate)
    if not checks["gpu_observation_clear"]:
        notes.append(
            "GPU sharing or incomplete observations prevent a reliable throughput verdict; measured peak memory is still reported."
        )
    if baseline_oom:
        checks["throughput_limit"] = None
        notes.append(
            "OOM baseline has no comparable completed-run throughput; slowdown is not certified."
        )
    else:
        checks["throughput_limit"] = (
            regression is not None
            and checks["gpu_observation_clear"]
            and hardware_equal
            and regression <= regression_limit
        )
    if mode == "fit":
        memory_target = after_bytes is not None and Decimal(str(after_bytes)) <= fit_bytes
    elif mode == "reclaim":
        memory_target = reduction is not None and reduction >= reclaim_reduction_pct
    else:
        memory_target = baseline_oom and completed
    checks["memory_target"] = memory_target
    required = [checks[key] for key in REQUIRED_CHECKS]
    required.append(checks["memory_target"])
    required.append(checks["loss_decreases"] if baseline_oom else checks["throughput_limit"])
    target_met = all(value is True for value in required)
    if baseline_oom:
        notes.append(
            "OOM peak reduction compares observed peaks, not the unobserved memory needed to finish the baseline."
        )
    return VerifyReport(
        completed=completed,
        acceptance_scope=acceptance_scope,
        numerical_basis=numerical_basis,
        comparison_precision=precision,
        loss_tolerance=tolerance,
        observed_precision_change=observed_change,
        precision_evidence=precision_evidence,
        peak_before=before,
        peak_after=after,
        reduction_pct=reduction,
        step_ms_before=before_ms,
        step_ms_after=after_ms,
        loss_equivalence=equivalence,
        target_met=target_met,
        notes=notes,
        checks=checks,
        max_loss_delta=max_delta,
        throughput_regression_pct=regression,
        numerics_changed=numerical_change,
        parameter_count_before=param_before,
        parameter_count_after=param_after,
        target=target,
        run_ids={"baseline": baseline.get("run_id"), "candidate": candidate.get("run_id")},
        reference_run=reference.get("run_dir") if reference is not None else None,
    )
