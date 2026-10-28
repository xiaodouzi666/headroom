"""Pure F3 s2 tier request/result helpers. No dispatch, allocation or artifact writes."""

from collections.abc import Mapping

from headroom.orchestrator import FixRequest
from headroom.verify.compare import compare_runs
from headroom.verify.numerical_requirement import SCOPE, requirement_evidence

PROTOCOL = "headroom.final48.s2-tiers.v1"
TIERS = {"strict": "exact-loss20-v1", "allow_precision": "observed-bf16-v1"}


def prepare_s2_tiers(base: FixRequest) -> dict[str, FixRequest]:
    """Build independent requests, preserving all caps and the original source."""
    if not isinstance(base, FixRequest):
        raise TypeError("base must be a FixRequest")
    if base.target != "fit:22GB" or base.max_steps != 20:
        raise ValueError("F3 s2 tiers preserve fit:22GB and 20 optimizer updates")
    if base.policy.allow_model_change or base.repository_mode:
        raise ValueError("F3 s2 tiers require the fixed standalone model")
    requests = {}
    for tier, requirement in TIERS.items():
        value = base.model_dump()
        value["policy"] = {
            **base.policy.model_dump(),
            "allow_numerics_change": tier == "allow_precision",
            "numerical_requirement": requirement,
        }
        requests[tier] = FixRequest.model_validate(value)
    return requests


def summarize_s2_tier(
    tier: str, request: FixRequest, result: Mapping, *, reference: Mapping | None = None
) -> dict:
    """Describe real observations without promoting memory-only success to a tier."""
    if tier not in TIERS or request.policy.numerical_requirement != TIERS[tier]:
        raise ValueError("Tier/request numerical requirement mismatch")
    run_record = result.get("run", result)
    if not isinstance(run_record, Mapping):
        raise TypeError("Run observations must be a mapping")
    verification = result.get("verification") or {}
    baseline, candidate = run_record.get("baseline") or {}, run_record.get("after") or {}
    if not all(isinstance(value, Mapping) for value in (verification, baseline, candidate)):
        raise TypeError("Tier observations must be mappings")
    checks = verification.get("checks") or {}
    if not isinstance(checks, Mapping):
        raise TypeError("Verification checks must be a mapping")
    observed = requirement_evidence(
        baseline,
        candidate,
        policy=request.policy.model_dump(),
        pairing=checks,
        numerics_changed=verification.get("numerics_changed"),
        required_steps=request.max_steps,
        reference=reference,
        reference_strategy=request.numerical_reference.strategy,
    )
    recomputed = compare_runs(
        baseline,
        candidate,
        target=request.target,
        policy=request.policy.model_dump(),
        pairing=checks,
        required_steps=request.max_steps,
        reference=reference,
        reference_strategy=request.numerical_reference.strategy,
        numerics_impact="minor" if verification.get("numerics_changed") is True else "none",
        reclaim_reduction_pct=request.reclaim_reduction_pct,
    )
    successful = (
        run_record.get("target_met") is True
        and recomputed.target_met is True
        and verification.get("target_met") is True
        and verification.get("numerical_requirement") == TIERS[tier]
        and checks.get("numerical_tier") is True
        and checks.get("numerical_acceptance") is True
        and observed["met"] is True
    )
    return {
        "protocol": PROTOCOL,
        "tier": tier,
        "run_id": run_record.get("run_id"),
        "provenance": run_record.get("provenance", "unknown"),
        "policy": request.policy.model_dump(),
        "target": request.target,
        "memory_target_met": recomputed.checks.get("memory_target"),
        "reported_memory_target_met": checks.get("memory_target"),
        "tier_met": successful,
        "numerical_requirement_evidence": observed,
        "loss_equivalence": recomputed.loss_equivalence,
        "reported_loss_equivalence": verification.get("loss_equivalence", "n/a"),
        "observed_precision": observed["observed_precision_after"],
        "peak_allocated_bytes": candidate.get("peak_allocated_bytes"),
        "step_ms_median": candidate.get("step_ms_median"),
        "timing_trusted": candidate.get("shared_gpu") is False
        and candidate.get("gpu_observation_complete") is True,
        "artifacts": dict((run_record.get("kept") or {}).get("artifacts") or {}),
        "scope": SCOPE,
        "historical_scores_modified": False,
    }
