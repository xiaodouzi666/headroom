"""Offline search decisions: synthetic observations, no GPU or model requests."""

import json
import socket
import subprocess
from pathlib import Path

import pytest

from headroom.search import (
    HARD_CHECKS,
    decide_keep,
    dominates,
    pareto_front,
    pareto_point,
    select_research_topics,
    write_cumulative_patch,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in search tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def observed(peak=30, ms=100, *, status="completed", shared=False):
    return {
        "status": status,
        "peak_allocated_bytes": int(peak * 1e9),
        "step_ms_median": ms,
        "shared_gpu": shared,
        "gpu_observation_complete": True,
        "env": {
            "device": "cuda",
            "gpu_name": "SYNTHETIC",
            "gpu_total_memory_bytes": 40_000_000_000,
        },
    }


def report(*, target=False):
    return {
        "completed": True,
        "target_met": target,
        "loss_equivalence": "identical",
        "numerics_changed": False,
        "checks": {
            **dict.fromkeys(HARD_CHECKS, True),
            "parameter_count_unchanged": True,
            "loss_tolerance": True,
            "throughput_limit": True,
            "memory_target": target,
        },
    }


def test_keep_before_target_if_all_original_and_current_constraints_pass():
    baseline, candidate = observed(), observed(25, 110)
    decision = decide_keep(baseline, candidate, report(), original_baseline=baseline, policy={})
    assert decision.keep and decision.memory_improvement_pct == pytest.approx(100 / 6)


@pytest.mark.parametrize("field", HARD_CHECKS)
def test_missing_hard_constraint_never_keeps(field):
    baseline, candidate, verification = observed(), observed(25, 110), report()
    verification["checks"].pop(field)
    assert not decide_keep(
        baseline, candidate, verification, original_baseline=baseline, policy={}
    ).keep


def test_original_tolerance_cannot_be_accumulated_between_rounds():
    baseline, current, candidate = observed(), observed(25, 110), observed(20, 120)
    verification = report(target=True)
    verification.update(loss_equivalence="changed")
    verification["checks"]["loss_tolerance"] = False
    assert not decide_keep(
        current, candidate, verification, original_baseline=baseline, policy={}
    ).keep


@pytest.mark.parametrize(
    "candidate,reason",
    [
        (observed(26, 110), "no_memory_improvement"),
        (observed(20, 140), "current_throughput_regression"),
        (observed(20, 100, shared=True), "current_throughput_unverified"),
    ],
)
def test_current_kept_state_is_the_incremental_performance_reference(candidate, reason):
    decision = decide_keep(
        observed(25, 100), candidate, report(), original_baseline=observed(), policy={}
    )
    assert not decision.keep and decision.reason == reason


def point(peak, ms, **kwargs):
    return (
        pareto_point(
            1,
            observed(peak, ms),
            report(),
            policy=kwargs.pop("policy", {}),
            artifacts={"patch": "x/patch.diff"},
            provenance="offline_fixture",
        )
        | kwargs
    )


def test_frontier_preserves_tradeoffs_and_cannot_compare_numerical_policies():
    low_memory, fast = point(20, 120), point(25, 90)
    dominated = point(28, 130)
    different_policy = point(18, 80, policy={"allow_numerics_change": True})
    different_numerics = point(15, 70, numerics="changed", numerics_changed=True)
    assert pareto_front([low_memory, fast, dominated, different_policy, different_numerics]) == [
        low_memory,
        fast,
        different_policy,
        different_numerics,
    ]


@pytest.mark.parametrize(
    "missing", [{"timing_trusted": False}, {"step_ms": None}, {"step_ms": float("nan")}]
)
def test_unknown_or_shared_timing_cannot_establish_dominance(missing):
    candidate = point(10, 10) | missing
    other = point(20, 100)
    assert not dominates(candidate, other) and not dominates(other, candidate)
    assert len(pareto_front([candidate, other])) == 2


def test_cumulative_patch_applies_directly_to_original_and_carries_env_argv(tmp_path):
    original, candidate = tmp_path / "original", tmp_path / "candidate"
    original.mkdir()
    candidate.mkdir()
    (original / "train.py").write_text("a=1\nb=1\n")
    (candidate / "train.py").write_text("a=2\nb=2\n")
    paths = write_cumulative_patch(
        original,
        candidate,
        tmp_path / "tier",
        env_changes={"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
        effective_cli=["--batch=4"],
        base_cli=["--batch=32"],
        metadata={"provenance": "offline_fixture"},
    )
    diff = Path(paths["patch"]).read_text()
    assert "-a=1" in diff and "+b=2" in diff
    assert (original / "train.py").read_text() == "a=1\nb=1\n"
    assert json.loads(Path(paths["manifest"]).read_text())["apply_check"]["status"] == "passed"
    assert json.loads(Path(paths["cli"]).read_text())["effective"] == ["--batch=4"]
    assert "PYTORCH_CUDA_ALLOC_CONF" in Path(paths["env"]).read_text()
    checked = subprocess.run(
        ["git", "apply", "--check", paths["patch"]], cwd=original, capture_output=True, check=False
    )
    assert checked.returncode == 0


def test_research_selects_actual_proposed_api_flags_and_at_most_two_topics():
    assert select_research_topics(
        {
            "description": "checkpoint(use_reentrant=False) with allocator expandable_segments and AdamW fused=True"
        }
    ) == ["checkpoint", "allocator"]
    assert select_research_topics({"description": "release Python references"}) == []


def test_original_oom_loss_decrease_gate_is_not_dropped_in_search():
    original = observed(status="oom")
    verification = report()
    verification["checks"]["throughput_limit"] = None
    verification["checks"]["loss_decreases"] = False
    assert not decide_keep(
        original, observed(20, 100), verification, original_baseline=original, policy={}
    ).keep


def test_cumulative_diff_handles_missing_final_newline(tmp_path):
    original, candidate = tmp_path / "old", tmp_path / "new"
    original.mkdir()
    candidate.mkdir()
    (original / "train.py").write_text("x=1")
    (candidate / "train.py").write_text("x=2")
    paths = write_cumulative_patch(
        original,
        candidate,
        tmp_path / "tier",
        env_changes={},
        effective_cli=[],
        base_cli=[],
        metadata={},
    )
    assert "\\ No newline at end of file" in Path(paths["patch"]).read_text()
    assert json.loads(Path(paths["manifest"]).read_text())["apply_check"]["status"] == "passed"


def test_informational_pairing_and_scalar_count_do_not_become_hard_gates():
    baseline, candidate, verification = observed(), observed(25, 110), report()
    verification["checks"].update(
        loss_tolerance=True,
        same_inputs=None,
        same_effective_batch=False,
        same_objective=None,
        loss_comparable=False,
        loss_series_aligned_to_updates=False,
        repository_no_reference_exception=False,
    )
    assert decide_keep(
        baseline, candidate, verification, original_baseline=baseline, policy={}
    ).keep


def test_repository_no_reference_exception_stays_scoped_in_keep():
    from test_compare import run

    from headroom.verify.compare import compare_runs

    baseline, candidate = run(status="oom", peak=24_000_000_000), run(peak=20_000_000_000)
    verification = compare_runs(baseline, candidate, acceptance_scope="repository").model_dump()
    assert decide_keep(
        baseline, candidate, verification, original_baseline=baseline, policy={}
    ).keep
    verification["acceptance_scope"] = "standard"
    assert not decide_keep(
        baseline, candidate, verification, original_baseline=baseline, policy={}
    ).keep
