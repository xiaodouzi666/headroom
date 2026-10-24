import copy

import pytest

from headroom.verify.compare import compare_runs, parse_target

PAIR = {"same_inputs": True, "same_effective_batch": True, "same_objective": True}


def run(*, peak=10_000_000_000, losses=None, status="completed", parameters=161):
    return {
        "protocol": "headroom.lab.v1",
        "capture_complete": True,
        "cleanup_verified": True,
        "status": status,
        "steps": 20 if status == "completed" else 0,
        "loss_series": losses if losses is not None else [1 - i * 0.01 for i in range(20)],
        "peak_allocated_bytes": peak,
        "peak_reserved_bytes": peak + 1_000_000_000,
        "step_ms_median": 100,
        "shared_gpu": False,
        "gpu_observation_complete": True,
        "parameter_count": parameters,
        "parameter_count_complete": True,
        "parameter_count_source": "lab_module_parameter_hooks",
        "env": {
            "device": "cuda",
            "seed": 7,
            "seeded": {"torch": True, "python": True, "numpy": True},
            "deterministic_algorithms": True,
            "gpu_name": "fixture GPU",
            "gpu_total_memory_bytes": 24 * 2**30,
        },
    }


@pytest.mark.parametrize(
    "delta,expected", [(0, "identical"), (0.0005, "within_tol"), (0.01, "changed")]
)
def test_original_fp32_loss_threshold_and_reclaim(delta, expected):
    baseline = run()
    candidate = run(peak=7_000_000_000, losses=[v + delta for v in baseline["loss_series"]])
    report = compare_runs(baseline, candidate, target="reclaim", pairing=PAIR)
    assert report.loss_equivalence == expected
    assert report.reduction_pct == 30
    assert report.target_met == (delta <= 1e-3)


def test_original_scalar_comparison_does_not_claim_workload_comparability():
    report = compare_runs(run(), run(peak=6_000_000_000), target="reclaim")
    assert report.loss_equivalence == "identical"
    assert report.max_loss_delta == 0
    assert report.target_met
    assert report.checks["same_inputs"] is None
    assert report.checks["loss_comparable"] is False
    assert "not proof" in " ".join(report.notes)


def test_reduced_model_is_changed_even_if_it_spoofs_identical_loss():
    report = compare_runs(
        run(), run(peak=5_000_000_000, parameters=81), target="reclaim", pairing=PAIR
    )
    assert report.loss_equivalence == "changed"
    assert not report.target_met
    assert report.checks["parameter_count_unchanged"] is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("capture_complete", False),
        ("cleanup_verified", False),
        ("steps", 19),
        ("status", "timeout"),
        ("parameter_count_complete", False),
        ("parameter_count_source", "target_self_report"),
        ("peak_allocated_bytes", None),
    ],
)
def test_missing_or_failed_evidence_cannot_pass(field, value):
    candidate = run(peak=6_000_000_000)
    candidate[field] = value
    assert not compare_runs(run(), candidate, target="reclaim", pairing=PAIR).target_met


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), True])
def test_nonfinite_or_missing_losses_cannot_pass(bad):
    candidate = run(peak=6_000_000_000)
    candidate["loss_series"][2] = bad
    report = compare_runs(run(), candidate, target="reclaim", pairing=PAIR)
    assert not report.target_met
    assert report.checks["finite_candidate_losses"] is False


def test_oom_requires_completed_reference_five_losses_and_decrease():
    baseline = run(status="oom", peak=24_000_000_000, losses=[])
    candidate = run(peak=20_000_000_000)
    missing = compare_runs(baseline, candidate, target="fit:22GB", pairing=PAIR)
    assert missing.loss_equivalence == "n/a" and not missing.target_met
    passed = compare_runs(baseline, candidate, target="fit:22GB", pairing=PAIR, reference=run())
    assert passed.target_met and passed.loss_equivalence == "identical"
    assert passed.checks["throughput_limit"] is None
    candidate["loss_series"] = list(reversed(candidate["loss_series"]))
    assert not compare_runs(baseline, candidate, reference=run(), pairing=PAIR).target_met


def test_original_small_batch_rule_keeps_pairing_mismatch_visible():
    pair = {**PAIR, "same_effective_batch": False}
    report = compare_runs(run(status="oom"), run(), reference=run(), pairing=pair)
    assert report.max_loss_delta == 0
    assert report.loss_equivalence == "identical" and report.target_met
    assert report.checks["same_effective_batch"] is False
    assert report.checks["loss_comparable"] is False


def test_microbatch_scalar_losses_are_not_implicitly_optimizer_step_losses():
    candidate = run(peak=6_000_000_000)
    candidate["loss_series"] *= 2
    report = compare_runs(run(), candidate, target="reclaim", pairing=PAIR)
    assert report.loss_equivalence == "n/a"
    assert not report.checks["loss_series_aligned_to_updates"]


def test_bf16_changes_need_permission_and_original_tolerance():
    baseline = run()
    candidate = run(peak=6_000_000_000, losses=[x + 0.01 for x in baseline["loss_series"]])
    report = compare_runs(baseline, candidate, target="reclaim", pairing=PAIR, precision="bf16")
    assert report.loss_equivalence == "changed" and not report.target_met
    allowed = compare_runs(
        baseline,
        candidate,
        target="reclaim",
        pairing=PAIR,
        precision="bf16",
        policy={"allow_numerics_change": True},
    )
    assert allowed.target_met and allowed.numerics_changed
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate, tolerance=0.1)


def test_shared_gpu_or_slowdown_cannot_satisfy_throughput_gate():
    candidate = run(peak=6_000_000_000)
    candidate["step_ms_median"] = 126
    assert not compare_runs(run(), candidate, target="reclaim", pairing=PAIR).target_met
    candidate["step_ms_median"] = 100
    candidate["shared_gpu"] = True
    report = compare_runs(run(), candidate, target="reclaim", pairing=PAIR)
    assert not report.target_met and not report.checks["throughput_limit"]


def test_cpu_capture_never_claims_gpu_memory_success():
    baseline, candidate = run(), run(peak=6_000_000_000)
    for result in (baseline, candidate):
        result["env"]["device"] = "cpu"
        result["peak_allocated_bytes"] = None
    report = compare_runs(baseline, candidate, target="reclaim", pairing=PAIR)
    assert report.loss_equivalence == "identical" and not report.target_met


def test_seed_difference_is_not_a_comparable_pair():
    candidate = run(peak=6_000_000_000)
    candidate["env"]["seed"] = 8
    assert compare_runs(run(), candidate, target="reclaim", pairing=PAIR).loss_equivalence == "n/a"


def test_fit_units_and_exact_boundary():
    assert parse_target("fit:22GB")[1] == 22 * 10**9
    assert parse_target("fit:22GiB")[1] == 22 * 2**30
    baseline = run(status="oom")
    assert compare_runs(
        baseline, run(peak=22 * 10**9), reference=run(), pairing=PAIR, target="fit:22GB"
    ).target_met
    assert not compare_runs(
        baseline, run(peak=22 * 10**9 + 1), reference=run(), pairing=PAIR, target="fit:22GB"
    ).target_met


def test_input_results_are_not_modified():
    baseline, candidate = run(), run(peak=6_000_000_000)
    before = copy.deepcopy((baseline, candidate))
    compare_runs(baseline, candidate, target="reclaim", pairing=PAIR)
    assert (baseline, candidate) == before


def test_reclaim_target_requires_a_completed_baseline():
    report = compare_runs(
        run(status="oom", peak=24_000_000_000),
        run(peak=10_000_000_000),
        target="reclaim",
        reference=run(),
        pairing=PAIR,
    )
    assert not report.target_met and not report.checks["target_mode_valid"]


def test_impossible_or_fractional_byte_peak_is_not_measured_cuda_evidence():
    for peak in (30_000_000_000, 1.5):
        report = compare_runs(run(), run(peak=peak), target="reclaim", pairing=PAIR)
        assert not report.target_met
        assert not report.checks["measured_cuda_peaks"]


def test_matching_microbatch_sequences_compare_without_inventing_update_losses():
    baseline, candidate = run(), run(peak=6_000_000_000)
    baseline["loss_series"] *= 2
    candidate["loss_series"] *= 2
    report = compare_runs(baseline, candidate, target="reclaim")
    assert report.target_met and report.loss_equivalence == "identical"
    assert report.checks["loss_series_aligned_to_updates"] is False
    assert report.checks["loss_series_comparison_available"] is True


def test_oom_uses_first_five_scalars_with_actual_twenty_updates():
    baseline = run(status="oom", losses=[])
    candidate, reference = run(), run()
    candidate["loss_series"] += [0.1] * 20
    reference["loss_series"] += [0.2] * 40
    report = compare_runs(baseline, candidate, reference=reference)
    assert report.target_met and report.max_loss_delta == 0
    assert report.checks["loss_series_aligned_to_updates"] is False
    candidate["steps"] = 19
    assert not compare_runs(baseline, candidate, reference=reference).target_met


def test_repository_no_reference_is_a_scoped_na_exception():
    baseline, candidate = run(status="oom", losses=[]), run(peak=6_000_000_000)
    standard = compare_runs(baseline, candidate)
    report = compare_runs(baseline, candidate, acceptance_scope="repository")
    assert not standard.target_met
    assert report.target_met and report.loss_equivalence == "n/a"
    assert report.numerical_basis == "repository_no_reference_exception"
    assert report.checks["loss_tolerance"] is False
    assert report.checks["numerical_acceptance"] is True
    assert report.checks["same_inputs"] is None
    assert not compare_runs(
        baseline, candidate, reference=run(losses=[2.0] * 20), acceptance_scope="repository"
    ).target_met
    assert not compare_runs(
        baseline, candidate, reference=run(status="error"), acceptance_scope="repository"
    ).target_met
    candidate["loss_series"] = [1.0] * 20
    assert not compare_runs(baseline, candidate, acceptance_scope="repository").target_met


def test_repository_exception_never_waives_bad_losses_model_or_precision():
    baseline = run(status="oom", losses=[])
    for candidate in (run(losses=[]), run(losses=[float("nan")] * 20), run(parameters=81)):
        assert not compare_runs(baseline, candidate, acceptance_scope="repository").target_met
    assert not compare_runs(
        baseline,
        run(),
        acceptance_scope="repository",
        precision="bf16",
        policy={"allow_numerics_change": True},
    ).target_met
    with pytest.raises(ValueError, match="scope"):
        compare_runs(baseline, run(), acceptance_scope="anything")


def test_shared_gpu_does_not_invalidate_oom_measured_capacity():
    baseline, candidate, reference = run(status="oom"), run(peak=6_000_000_000), run()
    baseline["shared_gpu"] = candidate["shared_gpu"] = True
    report = compare_runs(baseline, candidate, reference=reference, target="fit:22GB")
    assert report.target_met
    assert report.checks["gpu_observation_clear"] is False
    assert report.checks["throughput_limit"] is None


def with_precision(result, mode, *, complete=True):
    result["precision_observation"] = {
        "protocol": "headroom.precision.v1",
        "source": "lab_runtime_precision_observer_v1",
        "device": result["env"]["device"],
        "complete": complete,
        "precision": mode,
        "root_modes": {key: 20 if key == mode else 0 for key in ("fp32", "bf16", "unknown")},
        "errors": {},
    }
    return result


def test_existing_bf16_workload_uses_original_tolerance_without_a_new_precision_change():
    baseline = with_precision(run(), "bf16")
    candidate = with_precision(
        run(peak=6_000_000_000, losses=[x + 0.01 for x in baseline["loss_series"]]), "bf16"
    )
    report = compare_runs(baseline, candidate, target="reclaim")
    assert report.target_met and report.loss_equivalence == "within_tol"
    assert report.comparison_precision == "bf16" and report.loss_tolerance == 0.02
    assert report.observed_precision_change is False and report.numerics_changed is False


def test_actual_fp32_to_bf16_transition_requires_policy_even_if_plan_claims_none():
    baseline = with_precision(run(), "fp32")
    candidate = with_precision(
        run(peak=6_000_000_000, losses=[x + 0.01 for x in baseline["loss_series"]]), "bf16"
    )
    denied = compare_runs(baseline, candidate, target="reclaim")
    allowed = compare_runs(
        baseline, candidate, target="reclaim", policy={"allow_numerics_change": True}
    )
    assert denied.observed_precision_change and denied.numerics_changed
    assert denied.loss_equivalence == "changed" and not denied.target_met
    assert denied.checks["numerics_policy"] is False
    assert allowed.target_met and allowed.loss_equivalence == "changed"
    assert allowed.loss_tolerance == 0.02
    candidate["loss_series"] = [x + 0.03 for x in baseline["loss_series"]]
    assert not compare_runs(
        baseline, candidate, target="reclaim", policy={"allow_numerics_change": True}
    ).target_met


@pytest.mark.parametrize("unknown_side", ["baseline", "candidate"])
def test_missing_or_incomplete_precision_does_not_upgrade_tolerance(unknown_side):
    baseline = with_precision(run(), "bf16", complete=unknown_side != "baseline")
    candidate = with_precision(
        run(peak=6_000_000_000, losses=[x + 0.01 for x in baseline["loss_series"]]),
        "bf16",
        complete=unknown_side != "candidate",
    )
    report = compare_runs(
        baseline, candidate, target="reclaim", policy={"allow_numerics_change": True}
    )
    assert report.comparison_precision == "fp32" and report.loss_tolerance == 0.001
    assert report.observed_precision_change is None
    assert not report.target_met


def test_precision_metadata_does_not_create_a_new_global_gate_for_legacy_runs():
    report = compare_runs(run(), run(peak=6_000_000_000), target="reclaim")
    assert report.target_met and report.loss_equivalence == "identical"
    assert report.observed_precision_change is None
    assert report.loss_tolerance == 0.001


def test_oom_bf16_tolerance_uses_original_reference_precision():
    baseline = with_precision(run(status="oom", losses=[]), "bf16")
    reference = with_precision(run(), "bf16")
    candidate = with_precision(run(losses=[x + 0.01 for x in reference["loss_series"]]), "bf16")
    report = compare_runs(baseline, candidate, reference=reference)
    assert report.target_met and report.loss_equivalence == "within_tol"
    reference["precision_observation"]["complete"] = False
    assert compare_runs(baseline, candidate, reference=reference).loss_tolerance == 0.001


def test_observed_fp32_after_bf16_does_not_inherit_relaxed_bf16_bound():
    baseline = with_precision(run(), "bf16")
    candidate = with_precision(
        run(peak=6_000_000_000, losses=[x + 0.01 for x in baseline["loss_series"]]), "fp32"
    )
    report = compare_runs(
        baseline, candidate, target="reclaim", policy={"allow_numerics_change": True}
    )
    assert report.observed_precision_change and report.numerics_changed
    assert report.loss_tolerance == 0.001 and not report.target_met
