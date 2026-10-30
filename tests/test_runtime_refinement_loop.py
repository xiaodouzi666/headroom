"""Offline real-SDK loop tests. All Lab measurements are synthetic, never GPU runs."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
import test_orchestrator as fixtures

from headroom import orchestrator
from headroom.budget import BudgetExceeded
from headroom.config import ULTRA_MODEL
from headroom.diagnose import DiagnosisIssue, DiagnosisValidation
from headroom.solver_context import MAX_SOLVER_CONTEXT_BYTES, solver_prompt_context


def error_metadata():
    return {
        "status": "error",
        "execution_status": "error",
        "steps": 1,
        "pid": 12345,
        "capture_complete": True,
        "cleanup_verified": True,
        "shared_gpu": False,
        "gpu_observation_complete": True,
        "exception": {"type": "AttributeError", "message": "synthetic consumer error"},
        "execution": {
            "cleanup_verified": True,
            "artifact_export": {"export_verified": True},
            "artifact_cleanup": {"cleanup_verified": True},
        },
    }


def plans(*, count=2, all_error=False, first_changes=None, huge_diff=False):
    output = []
    for index in range(count):
        after = f"VALUE = {index + 2}\n"
        if huge_diff and index == 0:
            after += "UNUSED_TEXT = " + repr("x" * 6000) + "\n"
        item = {
            "before": "VALUE = 1\n",
            "after": after,
            "peak": 20,
            "target": not all_error and index > 0,
        }
        if index == 0 or all_error:
            item["candidate_extra"] = error_metadata()
            item["verification_extra"] = {"completed": False}
        if index == 0 and first_changes:
            item.update(first_changes)
        output.append(item)
    return output


def install_capture_adapters(monkeypatch, *, mutate_after_first=None, deny_second_patch=False):
    """Create complete owned capture files around the existing synthetic Lab fixture.

    The protocol/provenance readers and host fingerprint remain real. Only Lab
    execution and provider transport are the explicit dependency-injection fixtures.
    """
    real_services = fixtures.Services
    calls = {"verifications": 0}

    def recorded_capture(result):
        path = Path(result["run_dir"])
        selected = path.parent / uuid4().hex
        path.rename(selected)
        result["run_id"], result["run_dir"] = selected.name, str(selected)
        result["selected_capture_relative"] = None  # reviewed single-owner legacy capture branch
        (selected / "artifacts").mkdir(exist_ok=True)
        source_files = {}
        for file in (selected / "source").rglob("*"):
            if file.is_file() and ".git" not in file.relative_to(selected / "source").parts:
                raw = file.read_bytes()
                source_files[str(file.relative_to(selected / "source"))] = {
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                }
        (selected / "manifest.json").write_text(json.dumps({"source": {"files": source_files}}))
        if result["status"] == "error":
            exception = result["exception"]
            (selected / "artifacts/traceback.txt").write_text(
                "Traceback (most recent call last):\n"
                '  File "/source/train.py", line 1, in <module>\n'
                + exception["type"]
                + ": "
                + exception["message"]
                + "\n"
            )
        return result

    def services(**kwargs):
        baseline, verify = kwargs["baseline"], kwargs["verify"]

        def capture_baseline(*args, **options):
            return recorded_capture(baseline(*args, **options))

        def capture_verify(*args, **options):
            value = verify(*args, **options)
            value["candidate"] = recorded_capture(value["candidate"])
            calls["verifications"] += 1
            if calls["verifications"] == 1 and mutate_after_first is not None:
                mutate_after_first(args[0])
            return value

        kwargs.update(baseline=capture_baseline, verify=capture_verify)
        if deny_second_patch:
            factory = kwargs["runtime_factory"]

            def with_budget(*args, **options):
                bundle = factory(*args, **options)
                original = bundle.client._before_attempt

                def before(role, spec, attempt, body):
                    if original is not None:
                        original(role, spec, attempt, body)
                    prior = sum(x.role == "patcher" for x in bundle.client.ledger.entries)
                    if role == "patcher" and prior >= 1:
                        raise BudgetExceeded("Synthetic second-patch reservation denied")

                bundle.client._before_attempt = before
                return bundle

            kwargs["runtime_factory"] = with_budget
        return real_services(**kwargs)

    monkeypatch.setattr(fixtures, "Services", services)
    return calls


def outcomes(requests):
    return [request["model"] for request in requests]


def reused_events(store, run_id):
    return [
        event
        for event in store.events(run_id)
        if event["kind"] == "diagnose.reused_for_patch_refinement"
    ]


def test_one_ultra_then_two_fresh_supers_reverts_original_source_and_marks_reuse(
    tmp_path, monkeypatch
):
    install_capture_adapters(monkeypatch)
    result, store, requests, verifies, root = fixtures.search_run(tmp_path, plans())
    try:
        assert result["target_met"]  # Synthetic verification only.
        assert len(requests) == 3
        assert outcomes(requests)[0] == ULTRA_MODEL
        assert all(name != ULTRA_MODEL for name in outcomes(requests)[1:])
        assert len(verifies) == 2
        assert root.joinpath("train.py").read_text() == "VALUE = 1\n"
        assert [x["decision"] for x in store.rounds(result["run_id"])] == ["revert", "keep"]
        assert len(reused_events(store, result["run_id"])) == 1
        first_patch = json.loads(requests[1]["messages"][-1]["content"])
        assert "runtime_patch_refinement" not in first_patch["evidence_context"]
        assert requests[1]["max_tokens"] == requests[2]["max_tokens"] == 4000
        assert sum(x["kind"] == "diagnose.started" for x in store.events(result["run_id"])) == 1
        second = json.loads(requests[2]["messages"][-1]["content"])
        assert second["plan_step"]["fix_id"] == "f1"
        assert "VALUE = 1" in json.dumps(second["sources"])
        assert "VALUE = 2" not in json.dumps(second["sources"])
        context = second["evidence_context"]["runtime_patch_refinement"]
        assert context["failed_round"] == context["diagnosis_origin_round"] == 1
        assert "VALUE = 2" in context["failed_patch_diff"]["text"]
        assert context["failure"]["exception_type"] == "AttributeError"
        assert context["failure"]["source_frames"][0]["source_path"] == "train.py"
        assert (
            second["evidence_context"]["solver_context_availability"]["wire_limit_bytes"]
            == 64 * 1024
        )
        final = json.loads((Path(result["run_dir"]) / "rounds/02/diagnosis.json").read_text())
        assert final["new_diagnosis_request"] is False
        assert final["model_response_reused_from"]["round"] == 1
        prior_file = Path(result["run_dir"]) / "rounds/01/diagnosis.json"
        assert (
            final["model_response_reused_from"]["sha256"]
            == hashlib.sha256(prior_file.read_bytes()).hexdigest()
        )
        assert final["response_request_modes"] == []
        assert store.usage(result["run_id"])["calls"] == 3
    finally:
        store.close()


@pytest.mark.parametrize("change", ["loss", "policy", "cleanup", "evidence", "cuda"])
def test_semantic_policy_unknown_cleanup_and_nonpython_errors_replan(tmp_path, monkeypatch, change):
    mutation = None
    if change == "evidence":

        def mutation(original):
            evidence = Path(original["run_dir"]).parents[1] / "evidence/before/evidence.md"
            evidence.write_text(evidence.read_text() + "\nChanged captured context.\n")

    install_capture_adapters(monkeypatch, mutate_after_first=mutation)
    items = plans()
    if change == "loss":
        items[0]["loss"] = "changed"
        items[0]["candidate_extra"].update(
            status="completed", execution_status="completed", steps=20, exception=None
        )
        items[0]["verification_extra"]["completed"] = True
        items[0]["checks"] = {"numerical_acceptance": False, "loss_tolerance": False}
    elif change == "policy":
        items[0]["checks"] = {"numerics_policy": False}
    elif change == "cleanup":
        items[0]["candidate_extra"]["cleanup_verified"] = False
    elif change == "cuda":
        items[0]["candidate_extra"]["exception"] = {
            "type": "RuntimeError",
            "message": "CUDA device-side assertion synthetic",
        }
    result, store, requests, _, _ = fixtures.search_run(tmp_path, items)
    try:
        assert outcomes(requests).count(ULTRA_MODEL) == 2
        assert not reused_events(store, result["run_id"])
        assert len(requests) == 4
    finally:
        store.close()


def test_host_revalidation_can_refuse_old_ready_response(tmp_path, monkeypatch):
    install_capture_adapters(monkeypatch)
    real = orchestrator.validate_diagnosis

    def new_validator(payload, **kwargs):
        checked = real(payload, **kwargs)
        return DiagnosisValidation(
            checked.diagnosis,
            (DiagnosisIssue("SYNTHETIC_REVALIDATION_REJECTED", "New host check refused reuse"),),
        )

    monkeypatch.setattr(orchestrator, "validate_diagnosis", new_validator)
    result, store, requests, _, _ = fixtures.search_run(tmp_path, plans())
    try:
        assert outcomes(requests).count(ULTRA_MODEL) == 2
        assert not reused_events(store, result["run_id"])
    finally:
        store.close()


def test_six_round_limit_counts_every_refinement_and_never_adds_a_seventh(tmp_path, monkeypatch):
    install_capture_adapters(monkeypatch)
    result, store, requests, verifies, _ = fixtures.search_run(
        tmp_path, plans(count=6, all_error=True), max_rounds=6
    )
    try:
        assert not result["target_met"]
        assert len(verifies) == 6
        assert len(store.rounds(result["run_id"])) == 6
        assert outcomes(requests).count(ULTRA_MODEL) == 1
        assert len(requests) == 7
        assert len(reused_events(store, result["run_id"])) == 5
        assert result["search"]["stop_reason"] == "max_rounds_reached"
    finally:
        store.close()


def test_existing_budget_hook_stops_fresh_super_before_transport(tmp_path, monkeypatch):
    install_capture_adapters(monkeypatch, deny_second_patch=True)
    result, store, requests, verifies, root = fixtures.search_run(tmp_path, plans())
    try:
        assert result["status"] == "budget_exceeded"
        assert not result["target_met"] and len(verifies) == 1
        assert len(requests) == 2
        assert outcomes(requests).count(ULTRA_MODEL) == 1
        assert root.joinpath("train.py").read_text() == "VALUE = 1\n"
    finally:
        store.close()


def test_truncated_failed_diff_invalidates_ticket_instead_of_expanding_context(
    tmp_path, monkeypatch
):
    install_capture_adapters(monkeypatch)
    result, store, requests, _, _ = fixtures.search_run(tmp_path, plans(huge_diff=True))
    try:
        assert outcomes(requests).count(ULTRA_MODEL) == 2
        assert not reused_events(store, result["run_id"])
        first = store.rounds(result["run_id"])[0]
        assert first["candidate_evidence"]["diff"]["truncated"] is True
    finally:
        store.close()


def test_unavailable_combined_context_falls_back_to_normal_diagnosis(tmp_path, monkeypatch):
    install_capture_adapters(monkeypatch)
    real = orchestrator.solver_prompt_context

    def bounded(**kwargs):
        if kwargs.get("runtime_patch_refinement") is not None:
            raise ValueError("Synthetic combined-context admission refusal")
        return real(**kwargs)

    monkeypatch.setattr(orchestrator, "solver_prompt_context", bounded)
    result, store, requests, _, _ = fixtures.search_run(tmp_path, plans())
    try:
        assert outcomes(requests).count(ULTRA_MODEL) == 2
        assert not reused_events(store, result["run_id"])
        assert any(
            event["kind"] == "diagnose.refinement_invalidated"
            for event in store.events(result["run_id"])
        )
    finally:
        store.close()


def test_refinement_never_changes_shared_solver_or_per_field_byte_limits():
    assert MAX_SOLVER_CONTEXT_BYTES == 64 * 1024
    with pytest.raises(ValueError, match="runtime_patch_refinement"):
        solver_prompt_context(runtime_patch_refinement={"unbounded": "x" * 8192})


def test_changed_retained_source_invalidates_fingerprint_and_requires_new_diagnosis(
    tmp_path, monkeypatch
):
    def mutate(original):
        (Path(original["run_dir"]) / "source/train.py").write_text("VALUE = 999" + chr(10))

    install_capture_adapters(monkeypatch, mutate_after_first=mutate)
    items = plans()
    items[1]["needs_more_info"] = True
    result, store, requests, verifies, _ = fixtures.search_run(tmp_path, items)
    try:
        assert outcomes(requests).count(ULTRA_MODEL) >= 2
        assert not reused_events(store, result["run_id"])
        assert len(verifies) == 1
        assert not result["target_met"]
    finally:
        store.close()
