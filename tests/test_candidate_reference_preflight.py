"""Offline capability guards: no model, Lab, GPU, or numerical acceptance claim."""

import copy
import json
from pathlib import Path

import pytest
from test_orchestrator import search_run
from test_verify_checkpoint_reference import SCRIPT, SOURCE, TRANSFORMED

from headroom.solver_context import MAX_SOLVER_CONTEXT_BYTES, solver_prompt_context
from headroom.verify.candidate_preflight import (
    candidate_reference_preflight,
    reference_family_reading_aid,
)
from headroom.verify.pairing import source_contract


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in candidate capability tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def active_context():
    contract = source_contract(SCRIPT)
    return {
        "protocol": "headroom.numerical_reference_context.v1",
        "selected_strategy": "original_workload_checkpoint",
        "original_source": {
            "status": "supported",
            "normalized_contract_sha256": contract["contract_sha256"],
        },
        "source_contract_boundary": {
            "active_for_this_oom_baseline": True,
            "candidate_source_must_remain_within_reviewed_contract": True,
        },
    }


def test_reviewed_checkpoint_source_is_only_statically_admitted(tmp_path):
    script = tmp_path / "candidate.py"
    script.write_bytes(TRANSFORMED)
    result = candidate_reference_preflight(script, active_context())
    assert result["status"] == "admitted_static"
    assert result["candidate_contract_sha256"] == result["expected_contract_sha256"]
    assert result["execution_performed_by_preflight"] is False
    assert result["candidate_equivalence_verified"] is None


def test_rewritten_training_loop_rejected_without_running_or_certifying_mismatch(tmp_path):
    script = tmp_path / "candidate.py"
    original = SOURCE.decode()
    candidate = original.replace("predictions = model(inputs)", "predictions = model(inputs[:4])")
    assert candidate != original
    script.write_text(candidate)
    before = script.read_bytes()
    result = candidate_reference_preflight(script, active_context())
    assert result["status"] == "rejected"
    assert result["reason"] == "candidate_source_contract_unsupported"
    assert result["candidate_source_sha256"] is not None
    assert result["candidate_contract_sha256"] is None
    assert result["candidate_equivalence_verified"] is None
    assert "Do not retry this unsupported source" in result["next_action"]
    assert script.read_bytes() == before


def test_other_supported_profile_still_rejected_as_different_workload(tmp_path):
    context = active_context()
    context["original_source"]["normalized_contract_sha256"] = "0" * 64
    result = candidate_reference_preflight(SCRIPT, context)
    assert result["status"] == "rejected"
    assert result["reason"] == "candidate_source_contract_mismatch"


def test_unreadable_candidate_is_unknown_and_not_a_known_static_rejection(tmp_path):
    result = candidate_reference_preflight(tmp_path / "absent.py", active_context())
    assert result["status"] == "unverified"
    assert result["candidate_equivalence_verified"] is None


@pytest.mark.parametrize(
    "change", ["completed_baseline", "legacy", "no_contract_boundary", "unbound_original"]
)
def test_inactive_or_unknown_boundary_never_applies_a_new_static_rejection(tmp_path, change):
    context = active_context()
    if change == "completed_baseline":
        context["source_contract_boundary"]["active_for_this_oom_baseline"] = False
    elif change == "legacy":
        context["selected_strategy"] = "legacy_small_batch"
    elif change == "no_contract_boundary":
        context.pop("source_contract_boundary")
    else:
        context["original_source"]["status"] = "unknown"
    result = candidate_reference_preflight(tmp_path / "absent.py", context)
    assert result["status"] == ("unverified" if change == "unbound_original" else "not_applicable")
    if change == "unbound_original":
        aid = reference_family_reading_aid(context)
        assert "With a known original static contract" in aid["planning_constraint"]


def test_offload_family_uses_its_existing_source_contract_boundary():
    context = active_context()
    context["selected_strategy"] = "original_saved_tensor_offload"
    assert candidate_reference_preflight(SCRIPT, context)["status"] == "admitted_static"


def test_capability_and_retained_reading_aids_preserve_full_metadata_and_wire_bound():
    context = active_context()
    original = copy.deepcopy(context)
    result = solver_prompt_context(
        execution_context={"selected_round": None},
        candidate_evidence=[{"round": 1, "decision": "revert", "candidate_selected": False}],
        numerical_reference_context=context,
    )
    assert result["reference_family_reading_aid"]["active"] is True
    assert result["retained_state_reading_aid"]["current_source_basis"] == "original_baseline"
    assert result["numerical_reference_context"] == original == context
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    assert reference_family_reading_aid(None) is None
    assert solver_prompt_context() == {}


def test_known_unsupported_patch_skips_verify_and_reaches_next_round_with_exact_feedback(
    tmp_path, monkeypatch
):
    import headroom.orchestrator as module

    context = active_context()
    monkeypatch.setattr(
        module, "numerical_reference_context", lambda *args, **kwargs: copy.deepcopy(context)
    )
    # The integration source is intentionally a synthetic, unsupported program.
    # Every patch is retained as an artifact but must never reach the fake verifier.
    plans = [{"before": "VALUE = 1\n", "after": "VALUE = 2\n"}] * 6
    result, store, calls, verifies, root = search_run(tmp_path, plans, max_rounds=6)
    try:
        assert result["status"] == "completed"
        assert result["search"]["rounds_executed"] == 6
        assert result["search"]["stop_reason"] == "max_rounds_reached"
        assert result["target_met"] is False
        assert verifies == []
        assert len(calls) == 12
        rounds = store.rounds(result["run_id"])
        assert len(rounds) == 6
        assert all(row["decision"] == "revert" for row in rounds)
        assert all(row["reason"] == "candidate_source_contract_unsupported" for row in rounds)
        assert all(
            row["candidate_reference_preflight"]["candidate_equivalence_verified"] is None
            for row in rounds
        )
        assert all(row.get("verification") is None for row in rounds)
        assert all(
            row["candidate_evidence"]["outcome_stage"]["candidate_runtime_observed"] is False
            for row in rounds
        )
        assert (root / "train.py").read_text() == "VALUE = 1\n"
        next_request = json.loads(calls[2]["messages"][-1]["content"])
        receipt = next_request["verification_feedback"][0]["candidate_reference_preflight"]
        assert receipt["reason"] == "candidate_source_contract_unsupported"
        assert receipt["execution_performed_by_preflight"] is False
        assert next_request["reference_family_reading_aid"]["active"] is True
        assert next_request["verification_feedback"][0]["verification_available"] is False
        for row in rounds:
            round_dir = Path(result["run_dir"]) / "rounds" / f"{row['number']:02d}"
            assert (round_dir / "candidate-reference-preflight.json").is_file()
            assert (Path(result["run_dir"]) / row["patch"]).is_file()
    finally:
        store.close()


@pytest.mark.parametrize("strategy", [[], {}, True, None])
def test_malformed_strategy_does_not_turn_unknown_metadata_into_rejection(strategy, tmp_path):
    context = active_context()
    context["selected_strategy"] = strategy
    assert reference_family_reading_aid(context) is None
    assert (
        candidate_reference_preflight(tmp_path / "absent.py", context)["status"] == "not_applicable"
    )
