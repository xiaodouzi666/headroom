"""Explicit F3 numerical tiers; legacy acceptance and recorded history stay unchanged."""

import math
import struct
from collections.abc import Mapping
from typing import Literal

from headroom.verify.checkpoint import STRATEGY as CHECKPOINT_STRATEGY
from headroom.verify.checkpoint import reference_proof as checkpoint_reference_proof
from headroom.verify.offload import LEGACY_STRATEGY, STRATEGY, reference_proof
from headroom.verify.pairing import derive_pairing
from headroom.verify.precision import observed_precision

NumericalRequirement = Literal["legacy", "exact-loss20-v1", "observed-bf16-v1"]
REQUIREMENTS = ("legacy", "exact-loss20-v1", "observed-bf16-v1")
PAIRING_KEYS = ("same_inputs", "same_effective_batch", "same_objective")
SCOPE = (
    "When exact-loss20-v1 is selected, only the 20 recorded backward loss scalars "
    "are compared bitwise as IEEE-754 "
    "binary64 values after Lab .item() capture; parameters and optimizer state "
    "are not compared bitwise. Workload pairing requires separate evidence."
)


def requirement_name(policy: Mapping) -> NumericalRequirement:
    name = policy.get("numerical_requirement", "legacy")
    if name not in REQUIREMENTS or not isinstance(name, str):
        raise ValueError("Unknown numerical requirement")
    allowed = policy.get("allow_numerics_change", False)
    if name == "exact-loss20-v1" and allowed is not False:
        raise ValueError("exact-loss20-v1 forbids numerical changes")
    if name == "observed-bf16-v1" and allowed is not True:
        raise ValueError("observed-bf16-v1 requires explicit numerical-change permission")
    return name


def _loss_bits(result):
    values = result.get("loss_series")
    if not isinstance(values, list) or len(values) != 20:
        return None
    try:
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            return None
        return b"".join(struct.pack(">d", value) for value in values)
    except (OverflowError, struct.error):
        return None


def requirement_evidence(
    baseline,
    candidate,
    *,
    policy,
    pairing=None,
    numerics_changed=False,
    required_steps=20,
    reference=None,
    reference_strategy=LEGACY_STRATEGY,
):
    """Observe a tier independently of legacy tolerance, using the original baseline."""
    name = requirement_name(policy)
    if name == "legacy":
        return {}
    if type(required_steps) is not int or required_steps != 20:
        raise ValueError("F3 numerical requirements need exactly 20 optimizer updates")
    pairing = pairing or {}
    before, after = observed_precision(baseline), observed_precision(candidate)
    comparator = reference if baseline.get("status") == "oom" else baseline
    comparator = comparator or {}
    comparison_precision = observed_precision(comparator)
    complete = candidate.get("status") == "completed" and candidate.get("steps") == 20
    reference_chain = {
        "baseline_run_id": baseline.get("run_id"),
        "baseline_status": baseline.get("status"),
        "comparison_run_id": comparator.get("run_id"),
        "comparison_source": "reference" if baseline.get("status") == "oom" else "baseline",
        "reference_strategy": reference_strategy if baseline.get("status") == "oom" else None,
        "original_workload_bound": baseline.get("status") == "completed",
    }
    actual_pairing = derive_pairing(comparator, candidate, required_steps)
    bound = baseline.get("status") == "completed"
    if baseline.get("status") == "oom":
        proof = {"valid": False, "checks": {}}
        if reference_strategy == STRATEGY:
            proof = reference_proof(reference, candidate, required_steps, baseline=baseline)
        elif reference_strategy == CHECKPOINT_STRATEGY:
            proof = checkpoint_reference_proof(
                reference, candidate, required_steps, baseline=baseline
            )
        bound = proof["valid"] is True
        reference_chain["original_workload_bound"] = bound
        reference_chain["proof_checks"] = proof["checks"]
    if name == "exact-loss20-v1":
        left, right = _loss_bits(comparator), _loss_bits(candidate)
        checks = {
            "candidate_completed20": complete,
            "comparison_completed20": comparator.get("status") == "completed"
            and comparator.get("steps") == 20,
            "original_workload_bound": bound,
            "recorded_loss20_bitwise_identical": left is not None and left == right,
            "known_unchanged_precision": before != "unknown"
            and before == comparison_precision == after,
            "unchanged_numerics": numerics_changed is False,
            **{
                key: pairing.get(key) is True and actual_pairing["checks"].get(key) is True
                for key in PAIRING_KEYS
            },
        }
    else:
        checks = {
            "candidate_completed20": complete,
            "observed_bf16": after == "bf16",
        }
    return {
        "protocol": name,
        "met": all(value is True for value in checks.values()),
        "checks": checks,
        "observed_precision_before": before,
        "observed_precision_after": after,
        "scope": SCOPE,
        "reference_chain": reference_chain,
        "observed_pairing": actual_pairing,
        "pairing": {
            key: pairing.get(key) if type(pairing.get(key)) is bool else None
            for key in PAIRING_KEYS
        },
        "limitations": [
            "Unsupported pairing stays unknown; equal scalars do not establish workload equality.",
            "No parameter or optimizer-state bitwise equivalence is claimed.",
        ],
    }


def requirement_context(policy):
    name = requirement_name(policy)
    if name == "legacy":
        return None
    rule = (
        "Require all 20 recorded backward loss scalars to be bitwise identical to the "
        "original baseline or a completed original-workload-bound reference, known unchanged "
        "precision, and independently "
        "verified same inputs/effective batch/objective. Within-tolerance loss differences "
        "or unsupported pairing do not pass this tier. Do not modify capture hooks or "
        "fabricate evidence to satisfy it."
        if name == "exact-loss20-v1"
        else "Permission to change precision is explicit. This tier completes only when Lab "
        "actually observes BF16 forward precision and all original tolerance, memory and "
        "safety checks pass. FP32 intermediate improvements may be retained but cannot "
        "complete the BF16 tier. Do not label permission alone as observed BF16."
    )
    return {"numerical_requirement": name, "rule": rule, "scope": SCOPE}
