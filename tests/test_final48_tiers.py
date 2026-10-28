"""Synthetic observations only; no model, GPU, source execution or production ledger."""

import json
import socket
from dataclasses import asdict

import pytest

from headroom.acceptance.final48_tiers import prepare_s2_tiers, summarize_s2_tier
from headroom.evaluation import resolve_policies
from headroom.orchestrator import FixRequest, Policy
from headroom.search import decide_keep, policy_key
from headroom.verify.compare import compare_runs
from headroom.verify.numerical_requirement import requirement_context
from headroom.verify.policy import normalize_policy

PAIR = {"same_inputs": True, "same_effective_batch": True, "same_objective": True}
EXACT = {"allow_numerics_change": False, "numerical_requirement": "exact-loss20-v1"}
BF16 = {"allow_numerics_change": True, "numerical_requirement": "observed-bf16-v1"}
LEGACY = {
    "allow_numerics_change": False,
    "allow_model_change": False,
    "allow_batch_grad_accum": True,
    "max_throughput_regression_pct": 25.0,
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in F3 tier tests")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def run(*, peak=23_000_000_000, precision="fp32"):
    from test_verify_offload_reference import measured

    return {
        "pairing_capture": measured()["pairing_capture"],
        "protocol": "headroom.lab.v1",
        "capture_complete": True,
        "cleanup_verified": True,
        "status": "completed",
        "steps": 20,
        "loss_series": [1.0 - i * 0.01 for i in range(20)],
        "peak_allocated_bytes": peak,
        "step_ms_median": 100.0,
        "shared_gpu": False,
        "gpu_observation_complete": True,
        "parameter_count": 161,
        "parameter_count_complete": True,
        "parameter_count_source": "lab_module_parameter_hooks",
        "env": {
            "device": "cuda",
            "seed": 7,
            "seeded": {"torch": True, "python": True, "numpy": True},
            "deterministic_algorithms": True,
            "gpu_name": "offline fixture",
            "gpu_total_memory_bytes": 24 * 2**30,
        },
        "precision_observation": {
            "protocol": "headroom.precision.v1",
            "source": "lab_runtime_precision_observer_v1",
            "complete": True,
            "device": "cuda",
            "errors": {},
            "precision": precision,
            "root_modes": {
                "fp32": int(precision == "fp32"),
                "bf16": int(precision == "bf16"),
                "unknown": 0,
            },
        },
    }


def compare(before, after, policy=EXACT, pairing=PAIR):
    return compare_runs(before, after, target="fit:22GB", policy=policy, pairing=pairing)


def keep(before, after, report, policy=EXACT):
    return decide_keep(
        before,
        after,
        report.model_dump() if hasattr(report, "model_dump") else report,
        original_baseline=before,
        policy=policy,
    )


def test_legacy_serialization_has_exact_original_keys_including_nested_and_json():
    assert Policy().model_dump() == LEGACY
    assert Policy(numerical_requirement="legacy").model_dump() == LEGACY
    assert json.loads(Policy().model_dump_json()) == LEGACY
    request = FixRequest(script="train.py")
    assert request.model_dump()["policy"] == LEGACY
    assert json.loads(request.model_dump_json())["policy"] == LEGACY
    policies = dict(resolve_policies(("default", "strict", "allow_precision")))
    assert policies["default"] == policies["strict"]
    assert policies["strict"].model_dump() == LEGACY


@pytest.mark.parametrize(
    "policy",
    [
        {"numerical_requirement": "unknown"},
        {"numerical_requirement": "exact-loss20-v1", "allow_numerics_change": True},
        {"numerical_requirement": "observed-bf16-v1"},
    ],
)
def test_invalid_tiers_rejected_by_policy_patch_and_comparison(policy):
    with pytest.raises(ValueError):
        Policy(**policy)
    with pytest.raises(ValueError):
        normalize_policy(policy)
    with pytest.raises(ValueError):
        compare(run(), run(), policy=policy)


def test_exact_requires_all20_same_precision_and_pairing():
    before, after = run(), run(peak=21_000_000_000)
    report = compare(before, after)
    assert report.target_met and keep(before, after, report).keep
    assert report.loss_equivalence == "identical"
    assert report.numerical_requirement_evidence["met"]
    assert "optimizer" in report.numerical_requirement_evidence["scope"]
    assert report.numerical_requirement_evidence["pairing"] == PAIR


@pytest.mark.parametrize("delta", [0.0000001, 0.0005])
def test_strict_rejects_within_tol_but_legacy_unchanged(delta):
    before, after = run(), run(peak=21_000_000_000)
    after["loss_series"][19] += delta
    old, strict = compare(before, after, policy={}), compare(before, after)
    assert old.target_met and old.loss_equivalence == "within_tol"
    assert not strict.target_met and strict.loss_equivalence == "within_tol"
    assert strict.checks["loss_tolerance"] is True
    assert strict.checks["numerical_acceptance"] is False
    assert not keep(before, after, strict).keep
    forged = strict.model_dump()
    forged.update(target_met=True, loss_equivalence="identical")
    forged["checks"].update(numerical_acceptance=True, numerical_tier=True)
    assert not keep(before, after, forged).keep


def test_signed_zero_not_bit_identical():
    before, after = run(), run(peak=21_000_000_000)
    before["loss_series"][0], after["loss_series"][0] = 0.0, -0.0
    report = compare(before, after)
    assert report.max_loss_delta == 0 and report.loss_equivalence == "identical"
    assert not report.target_met
    assert not report.numerical_requirement_evidence["checks"]["recorded_loss20_bitwise_identical"]


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_pairing",
        "false_pairing",
        "precision_unknown",
        "precision_change",
        "nineteen_losses",
        "twentyone_losses",
        "nonfinite",
        "huge_integer",
        "oom_original",
    ],
)
def test_exact_missing_or_unsupported_evidence_never_passes(mutation):
    before, after, pairing = run(), run(peak=21_000_000_000), dict(PAIR)
    if mutation == "missing_pairing":
        pairing = {}
    elif mutation == "false_pairing":
        pairing["same_inputs"] = False
    elif mutation == "precision_unknown":
        after.pop("precision_observation")
    elif mutation == "precision_change":
        after = run(peak=21_000_000_000, precision="bf16")
    elif mutation == "nineteen_losses":
        after["loss_series"].pop()
    elif mutation == "twentyone_losses":
        after["loss_series"].append(0.0)
    elif mutation == "nonfinite":
        after["loss_series"][0] = float("nan")
    elif mutation == "huge_integer":
        after["loss_series"][0] = 10**400
    elif mutation == "oom_original":
        before.update(status="oom", steps=0)
    report = compare(before, after, pairing=pairing)
    assert not report.target_met
    assert not keep(before, after, report).keep
    if mutation == "missing_pairing":
        assert report.numerical_requirement_evidence["pairing"]["same_inputs"] is None


def test_bf16_fp32_intermediate_kept_without_tier_completion():
    before, after = run(), run(peak=21_000_000_000)
    report = compare(before, after, policy=BF16)
    assert report.checks["memory_target"] and report.checks["numerical_acceptance"]
    assert not report.target_met and keep(before, after, report, BF16).keep
    forged = report.model_dump()
    forged.update(target_met=True)
    forged["checks"]["numerical_tier"] = True
    assert not keep(before, after, forged, BF16).keep


def test_observed_bf16_completes_only_under_existing_tolerance():
    before, after = run(), run(peak=21_000_000_000, precision="bf16")
    after["loss_series"] = [value + 0.01 for value in before["loss_series"]]
    report = compare(before, after, policy=BF16)
    assert report.target_met and report.loss_equivalence == "changed"
    assert report.loss_tolerance == 0.02 and keep(before, after, report, BF16).keep
    after["loss_series"][0] += 0.03
    assert not compare(before, after, policy=BF16).target_met


def test_unknown_bf16_observation_cannot_claim_tier():
    before, after = run(), run(peak=21_000_000_000, precision="bf16")
    after["precision_observation"]["complete"] = False
    report = compare(before, after, policy=BF16)
    assert not report.target_met
    assert report.numerical_requirement_evidence["observed_precision_after"] == "unknown"


def test_nonlegacy_old_verification_report_cannot_enter_search():
    before, after = run(), run(peak=21_000_000_000)
    legacy = compare(before, after, policy={})
    for policy in (EXACT, BF16):
        assert not keep(before, after, legacy, policy).keep


def test_requests_are_independent_and_preserve_original_caps_and_source():
    base = FixRequest(
        script="scenarios/s2_capacity_v2/train.py",
        target="fit:22GB",
        budget_usd="0.3",
        daily_budget_usd="4",
        max_rounds=4,
    )
    original = base.model_dump()
    tiers = prepare_s2_tiers(base)
    assert base.model_dump() == original
    assert tiers["strict"] is not tiers["allow_precision"]
    for name, request in tiers.items():
        assert request.script == base.script and request.budget_usd == "0.3"
        assert request.daily_budget_usd == "4" and request.max_rounds == 4
        assert request.policy.allow_numerics_change == (name == "allow_precision")
        assert "numerical_requirement" in request.model_dump()["policy"]
    assert policy_key(tiers["strict"].policy.model_dump()) != policy_key(
        tiers["allow_precision"].policy.model_dump()
    )


@pytest.mark.parametrize(
    "values",
    [
        {"target": "reclaim"},
        {"max_steps": 5},
        {"repository_mode": True},
        {"policy": {"allow_model_change": True}},
    ],
)
def test_tier_helper_cannot_change_s2_contract(values):
    base = FixRequest(script="train.py", target="fit:22GB")
    altered = FixRequest.model_validate({**base.model_dump(), **values})
    with pytest.raises(ValueError):
        prepare_s2_tiers(altered)


def test_explicit_tier_requires20steps_before_any_run():
    with pytest.raises(ValueError):
        FixRequest(script="train.py", max_steps=5, policy=Policy(**EXACT))
    with pytest.raises(ValueError):
        compare_runs(run(), run(), policy=EXACT, required_steps=5)


def test_result_helper_recomputes_and_retains_pairing_boundary():
    request = prepare_s2_tiers(FixRequest(script="train.py", target="fit:22GB"))["strict"]
    before, after = run(), run(peak=21_000_000_000)
    verification = compare(before, after, pairing={}).model_dump()
    result = {
        "run_id": "offline",
        "provenance": "offline_fixture",
        "baseline": before,
        "after": after,
        "verification": verification,
        "target_met": True,
    }
    summary = summarize_s2_tier("strict", request, result)
    assert not summary["tier_met"] and summary["memory_target_met"]
    assert summary["numerical_requirement_evidence"]["pairing"]["same_inputs"] is None
    assert not summary["historical_scores_modified"]
    assert result["target_met"] is True
    with pytest.raises(ValueError):
        summarize_s2_tier("allow_precision", request, result)


def test_context_and_patch_policy_preserve_requirement_without_changing_legacy():
    assert requirement_context({}) is None
    for policy in (EXACT, BF16):
        context = requirement_context(policy)
        assert context["numerical_requirement"] == policy["numerical_requirement"]
        assert "optimizer" in context["scope"]
        assert normalize_policy(policy).numerical_requirement == policy["numerical_requirement"]
    # Production patch prompt removes only the legacy field, retaining old dataclass keys.
    original = asdict(normalize_policy({}))
    original.pop("numerical_requirement")
    assert len(original) == 6


def test_search_continues_after_nonexact_candidate_and_prompts_carry_new_rule(tmp_path):
    from test_orchestrator import search_run

    plans = [
        {
            "before": "VALUE = 1\n",
            "after": f"VALUE = {value}\n",
            "peak": 20,
            "target": True,
            "loss": "within_tol",
            "checks": {"numerical_tier": True},
            "verification_extra": {"numerical_requirement": "exact-loss20-v1"},
        }
        for value in (2, 3)
    ]
    result, store, requests, verifies, _ = search_run(
        tmp_path,
        plans,
        max_rounds=2,
        policy=Policy(**EXACT),
    )
    try:
        assert not result["target_met"]
        assert len(verifies) == 2 and len(requests) == 4
        rounds = store.rounds(result["run_id"])
        assert all(row["decision"] == "revert" for row in rounds)
        diagnosis = json.loads(requests[0]["messages"][-1]["content"])
        patch = json.loads(requests[1]["messages"][-1]["content"])
        assert diagnosis["policy"]["numerical_requirement"] == "exact-loss20-v1"
        assert "Within-tolerance loss differences" in diagnosis["evidence_markdown"]
        assert patch["policy"]["numerical_requirement"] == "exact-loss20-v1"
        assert patch["evidence_context"]["numerical_requirement"]["rule"]
    finally:
        store.close()


def test_legacy_prompt_policy_still_has_original_shape_in_pipeline(tmp_path):
    from test_orchestrator import search_run

    result, store, requests, _, _ = search_run(
        tmp_path,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
        max_rounds=1,
    )
    try:
        assert result["target_met"]
        diagnosis = json.loads(requests[0]["messages"][-1]["content"])
        patch = json.loads(requests[1]["messages"][-1]["content"])
        assert diagnosis["policy"] == LEGACY
        assert "numerical_requirement" not in patch["policy"]
        assert "numerical_requirement" not in patch["evidence_context"]
        assert "EXPLICIT NUMERICAL REQUIREMENT" not in diagnosis["evidence_markdown"]
    finally:
        store.close()


def test_result_helper_accepts_canonical_report_and_rechecks_contradictory_claim():
    request = prepare_s2_tiers(FixRequest(script="train.py", target="fit:22GB"))["strict"]
    before, after = run(), run(peak=21_000_000_000)
    verification = compare(before, after).model_dump()
    report = {
        "run": {
            "run_id": "fixture",
            "provenance": "offline_fixture",
            "baseline": before,
            "after": after,
            "target_met": True,
        },
        "verification": verification,
    }
    assert summarize_s2_tier("strict", request, report)["tier_met"]
    after["peak_allocated_bytes"] = 23_000_000_000
    summary = summarize_s2_tier("strict", request, report)
    assert not summary["tier_met"] and not summary["memory_target_met"]
    assert summary["reported_memory_target_met"] is True


def test_actual_s2_pairing_contract_is_not_silently_expanded():
    from pathlib import Path

    from headroom.verify.pairing import source_contract

    script = Path(__file__).parents[1] / "scenarios/s2_capacity_v2/train.py"
    contract = source_contract(script)
    assert contract["supported"] is False


def oom_triplet(*, bf16=False):
    from test_verify_offload_reference import measured, reference

    original, candidate, ref = measured("oom"), measured(), reference()
    original["peak_allocated_bytes"] = 23_000_000_000
    candidate["peak_allocated_bytes"] = 21_000_000_000
    if bf16:
        candidate["precision_observation"] = run(precision="bf16")["precision_observation"]
        candidate["loss_series"] = [x + 0.01 for x in ref["loss_series"]]
    return original, candidate, ref


@pytest.mark.parametrize("policy", [EXACT, BF16])
def test_oom_bound_reference_passes_without_relaxing_existing_acceptance(policy):
    from headroom.verify.offload import STRATEGY

    original, candidate, ref = oom_triplet(bf16=policy == BF16)
    report = compare_runs(
        original, candidate, policy=policy, reference=ref, reference_strategy=STRATEGY
    )
    assert report.target_met and report.checks["numerical_acceptance"]
    assert (
        report.numerical_requirement_evidence["reference_chain"]["comparison_source"] == "reference"
    )
    assert report.loss_tolerance == (0.02 if policy == BF16 else 0.001)
    decision = decide_keep(
        original,
        candidate,
        report.model_dump(),
        original_baseline=original,
        policy=policy,
        reference=ref,
        reference_strategy=STRATEGY,
    )
    assert decision.keep
    request = FixRequest(
        script="train.py",
        target="fit:22GB",
        policy=Policy(**policy),
        numerical_reference={"strategy": STRATEGY},
    )
    result = {
        "baseline": original,
        "after": candidate,
        "target_met": True,
        "verification": report.model_dump(),
    }
    tier = "allow_precision" if policy == BF16 else "strict"
    assert summarize_s2_tier(tier, request, result, reference=ref)["tier_met"]
    assert not summarize_s2_tier(tier, request, result)["tier_met"]


def test_strict_oom_checks_all20_not_original_five_and_never_trusts_report_flags():
    from headroom.verify.offload import STRATEGY

    original, candidate, ref = oom_triplet()
    report = compare_runs(
        original, candidate, policy=EXACT, reference=ref, reference_strategy=STRATEGY
    )
    assert report.target_met
    candidate["loss_series"][19] += 0.0001
    failed = compare_runs(
        original, candidate, policy=EXACT, reference=ref, reference_strategy=STRATEGY
    )
    assert failed.loss_equivalence == "identical"  # Legacy five-scalar observation remains.
    assert not failed.target_met
    assert not decide_keep(
        original,
        candidate,
        report.model_dump(),
        original_baseline=original,
        policy=EXACT,
        reference=ref,
        reference_strategy=STRATEGY,
    ).keep
    candidate["loss_series"] = list(ref["loss_series"])
    ref["original_baseline_binding"]["baseline_run_id"] = "wrong-original"
    assert not decide_keep(
        original,
        candidate,
        report.model_dump(),
        original_baseline=original,
        policy=EXACT,
        reference=ref,
        reference_strategy=STRATEGY,
    ).keep


def test_strict_no_reference_or_small_batch_reference_cannot_substitute_original_workload():
    original, candidate, ref = oom_triplet()
    for reference in (None, ref):
        report = compare_runs(original, candidate, policy=EXACT, reference=reference, pairing=PAIR)
        assert not report.target_met
        assert not report.numerical_requirement_evidence["checks"]["original_workload_bound"]


def test_strict_completed_pairing_is_derived_independently_of_claimed_checks():
    before, after = run(), run(peak=21_000_000_000)
    report = compare(before, after)
    assert report.target_met
    after["pairing_capture"]["tensors"]["inputs"] = "different-input"
    failed = compare(before, after)
    assert not failed.target_met
    assert not keep(before, after, report).keep


@pytest.mark.parametrize("failure", ["missing_reference", "bad_reference", "out_of_tolerance"])
def test_oom_bf16_observation_alone_never_establishes_success(failure):
    from headroom.verify.offload import STRATEGY

    original, candidate, ref = oom_triplet(bf16=True)
    if failure == "missing_reference":
        ref = None
    elif failure == "bad_reference":
        ref["reference_offload"]["request_verified"] = False
    else:
        candidate["loss_series"][0] += 0.03
    report = compare_runs(
        original, candidate, policy=BF16, reference=ref, reference_strategy=STRATEGY
    )
    assert report.numerical_requirement_evidence["met"]
    assert not report.target_met and not report.checks["numerical_acceptance"]
