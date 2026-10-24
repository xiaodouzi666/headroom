"""Bounded search with offline SDK transport; no model/GPU acceptance claims."""

import json
import socket
from pathlib import Path

import pytest
from test_orchestrator import search_run

from headroom.orchestrator import FixRequest
from headroom.search import baseline_target_met


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in bounded-search fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def plan(old, new, *, peak=20, ms=100, target=True, **extra):
    return {
        "before": f"VALUE = {old}\n",
        "after": f"VALUE = {new}\n",
        "peak": peak,
        "ms": ms,
        "target": target,
        **extra,
    }


def document(result):
    return json.loads(Path(result["report_json"]).read_text())


def assert_selected(result, store, number, value):
    assert result["kept"]["round"] == number and result["target_met"] is True
    assert store.get_run(result["run_id"])["kept"]["round"] == number
    assert f"+VALUE = {value}" in Path(result["run_dir"], "patch.diff").read_text()
    tier = result["kept"]["artifacts"]
    assert (
        Path(result["run_dir"], tier["patch"]).read_bytes()
        == Path(result["run_dir"], "patch.diff").read_bytes()
    )
    saved = document(result)
    assert saved["run"]["kept"]["round"] == number
    assert saved["verification"]["after"]["run_dir"].endswith(f"candidate-{number}")


def test_default_stops_at_first_verified_target(tmp_path):
    result, store, calls, verifies, _ = search_run(tmp_path, [plan(1, 2)])
    try:
        assert result["search"] == {
            "mode": "until_target",
            "baseline_target_met": False,
            "first_target_met_round": 1,
            "stop_reason": "target_met",
            "rounds_executed": 1,
        }
        assert result["status"] == "completed" and result["reason"] is None
        assert len(verifies) == 1 and len(calls) == 2
        assert_selected(result, store, 1, 2)
    finally:
        store.close()


def test_bounded_continues_to_real_memory_latency_tradeoff_with_independent_patches(tmp_path):
    plans = [plan(1, 2), plan(2, 3, peak=18, ms=120)]
    result, store, calls, verifies, _ = search_run(
        tmp_path, plans, max_rounds=2, search_mode="bounded_pareto"
    )
    try:
        assert result["search"]["first_target_met_round"] == 1
        assert result["search"]["stop_reason"] == "max_rounds_reached"
        assert result["search"]["rounds_executed"] == 2
        assert result["status"] == "completed" and result["reason"] == "max_rounds_reached"
        assert len(calls) == 4 and len(verifies) == 2
        assert [point["round"] for point in result["pareto"]["frontier"]] == [1, 2]
        for point in result["pareto"]["points"]:
            patch = Path(result["run_dir"], point["artifacts"]["patch"]).read_text()
            assert "-VALUE = 1" in patch
        assert_selected(result, store, 2, 3)
        targets = [row for row in store.events(result["run_id"]) if row["kind"] == "target.met"]
        assert len(targets) == 1
        assert (
            '"target_already_met": true'
            in json.loads(calls[2]["messages"][-1]["content"])["evidence_markdown"]
        )
    finally:
        store.close()


def test_bounded_frontier_removes_genuinely_dominated_keeps(tmp_path):
    plans = [plan(1, 2), plan(2, 3, peak=18, ms=120), plan(3, 4, peak=16, ms=90)]
    result, store, _, _, _ = search_run(tmp_path, plans, max_rounds=3, search_mode="bounded_pareto")
    try:
        assert len(result["pareto"]["points"]) == 3
        assert [point["round"] for point in result["pareto"]["frontier"]] == [3]
        assert all(
            Path(result["run_dir"], p["artifacts"]["patch"]).is_file()
            for p in result["pareto"]["points"]
        )
        assert_selected(result, store, 3, 4)
    finally:
        store.close()


@pytest.mark.parametrize(
    "failure,stop,status",
    [
        ("budget", "budget_exceeded", "budget_exceeded"),
        ("deadline", "deadline", "timeout"),
        ("verify", "pipeline_error", "failed"),
    ],
)
def test_interrupted_exploration_preserves_success_as_partial(tmp_path, failure, stop, status):
    kwargs = {
        "budget": {"budget_after": 1},
        "deadline": {"cancel_after": 1},
        "verify": {"verify_error_at": 2},
    }[failure]
    result, store, _, _, _ = search_run(
        tmp_path,
        [plan(1, 2), plan(2, 3, peak=18)],
        max_rounds=3,
        search_mode="bounded_pareto",
        **kwargs,
    )
    try:
        assert result["status"] == status
        assert result["search"]["stop_reason"] == stop
        assert result["search"]["first_target_met_round"] == 1
        assert result["search"]["rounds_executed"] == 2
        assert_selected(result, store, 1, 2)
    finally:
        store.close()


@pytest.mark.parametrize(
    "second,reason",
    [
        ({"target": False}, "verified_target_regression"),
        ({"peak": 21, "ms": 80}, "no_memory_improvement"),
        ({"checks": {"numerics_policy": False}}, "verification_hard_constraints_unmet"),
    ],
)
def test_post_success_revert_preserves_selected_configuration(tmp_path, second, reason):
    result, store, _, _, _ = search_run(
        tmp_path,
        [plan(1, 2), plan(2, 3, **({"peak": 18} | second))],
        max_rounds=2,
        search_mode="bounded_pareto",
    )
    try:
        assert [r["decision"] for r in store.rounds(result["run_id"])] == ["keep", "revert"]
        assert store.rounds(result["run_id"])[-1]["reason"] == reason
        assert len(result["pareto"]["points"]) == 1
        assert_selected(result, store, 1, 2)
    finally:
        store.close()


def test_needs_more_information_stops_after_verified_success(tmp_path):
    result, store, _, verifies, _ = search_run(
        tmp_path,
        [plan(1, 2), plan(2, 3, needs_more_info=True)],
        max_rounds=3,
        search_mode="bounded_pareto",
    )
    try:
        assert result["status"] == "needs_human" and len(verifies) == 1
        assert result["search"]["stop_reason"] == "diagnosis_needs_more_info"
        assert_selected(result, store, 1, 2)
    finally:
        store.close()


def test_selected_new_keep_cannot_reuse_old_after_evidence(tmp_path):
    result, store, _, _, _ = search_run(
        tmp_path,
        [plan(1, 2), plan(2, 3, peak=18)],
        max_rounds=3,
        search_mode="bounded_pareto",
        evidence_fail_at=2,
    )
    try:
        assert result["status"] == "needs_human"
        assert result["search"]["stop_reason"] == "fresh_evidence_unavailable"
        assert store.get_run(result["run_id"])["after_evidence_status"] == "unavailable"
        saved = document(result)
        assert "after" not in saved["evidence"]
        assert "after_png" not in saved["artifacts"]
        assert Path(result["run_dir"], "rounds/01/evidence/evidence.json").is_file()
        assert_selected(result, store, 2, 3)
    finally:
        store.close()


def test_last_bounded_round_needs_no_next_prompt_evidence(tmp_path):
    result, store, _, _, _ = search_run(
        tmp_path,
        [plan(1, 2)],
        max_rounds=1,
        search_mode="bounded_pareto",
        evidence_fail_at=1,
    )
    try:
        assert result["status"] == "completed"
        assert result["search"]["stop_reason"] == "max_rounds_reached"
        assert store.get_run(result["run_id"])["after_evidence_status"] == "unavailable"
        assert_selected(result, store, 1, 2)
    finally:
        store.close()


def test_baseline_satisfying_goal_does_not_become_verified_repair(tmp_path):
    result, store, _, _, _ = search_run(
        tmp_path,
        [plan(1, 2, peak=30, target=False)],
        target="fit:40GB",
        max_rounds=1,
        search_mode="bounded_pareto",
    )
    try:
        assert result["search"]["baseline_target_met"] is True
        assert result["search"]["first_target_met_round"] is None
        assert result["target_met"] is False and result["kept"] is None
        assert result["pareto"]["points"] == []
    finally:
        store.close()


def test_search_mode_and_original_round_limit_are_strict():
    assert FixRequest(script="train.py").search_mode == "until_target"
    for mode in ("other", True, None, 1):
        with pytest.raises(ValueError):
            FixRequest(script="train.py", search_mode=mode)
    for rounds in (0, 7, True):
        with pytest.raises(ValueError):
            FixRequest(script="train.py", search_mode="bounded_pareto", max_rounds=rounds)


def test_baseline_observation_unknown_oom_and_completed_are_distinct():
    base = {"capture_complete": True, "cleanup_verified": True, "steps": 20}
    assert baseline_target_met(base, "fix-oom", required_steps=20) is None
    assert baseline_target_met(base | {"status": "oom"}, "fit:20GB", required_steps=20) is False
    assert baseline_target_met(base | {"status": "oom"}, "reclaim", required_steps=20) is None
    assert baseline_target_met(base | {"status": "completed"}, "fix-oom", required_steps=20) is True
    assert (
        baseline_target_met(base | {"status": "completed"}, "fit:20GB", required_steps=20) is None
    )


def test_baseline_fit_uses_exact_observed_bytes_at_fractional_gb_boundary():
    observed = {
        "status": "completed",
        "capture_complete": True,
        "cleanup_verified": True,
        "steps": 20,
        "peak_allocated_bytes": 15_000_000_001,
    }
    assert baseline_target_met(observed, "fit:15.000000001GB", required_steps=20) is True
    assert baseline_target_met(observed, "fit:15GB", required_steps=20) is False


def test_bounded_uses_at_most_six_measured_rounds(tmp_path):
    plans = [plan(i, i + 1, peak=21 - i) for i in range(1, 7)]
    result, store, calls, verifies, _ = search_run(tmp_path, plans, search_mode="bounded_pareto")
    try:
        assert len(verifies) == 6 and len(calls) == 12
        assert result["search"]["rounds_executed"] == 6
        assert result["search"]["stop_reason"] == "max_rounds_reached"
        assert_selected(result, store, 6, 7)
    finally:
        store.close()


def test_round_done_error_cannot_erase_committed_first_success(tmp_path, monkeypatch):
    from headroom.store.db import Store

    original = Store.add_event
    raised = False

    def interrupted(self, run_id, kind, payload):
        nonlocal raised
        event = original(self, run_id, kind, payload)
        if kind == "round.done" and not raised:
            raised = True
            raise ValueError("Synthetic event publication interruption")
        return event

    monkeypatch.setattr(Store, "add_event", interrupted)
    result, store, _, _, _ = search_run(
        tmp_path, [plan(1, 2)], max_rounds=2, search_mode="bounded_pareto"
    )
    try:
        assert result["status"] == "failed"
        assert result["search"]["stop_reason"] == "pipeline_error"
        assert result["search"]["first_target_met_round"] == 1
        assert_selected(result, store, 1, 2)
    finally:
        store.close()
