"""Offline scoped-fact repetition and optional catalog selection; no model/GPU work."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_diagnosis_bounded_repair import payload, provider_client
from test_evidence_blockers import source

from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.llm.router import LLMRouter
from headroom.observation_feedback import (
    MAX_OBSERVATION_FEEDBACK_BYTES,
    bound_optimizer_observation,
    supplied_runtime_observation,
)
from headroom.operator_capabilities import runtime_operator_catalog
from headroom.schemas import Diagnosis
from headroom.solver_context import (
    MAX_SOLVER_CONTEXT_BYTES,
    execution_context,
    solver_prompt_context,
)
from headroom.validation_feedback import MAX_CONTEXT_BYTES, validation_issue_context

PREFIX = "execution_context.runtime_optimizer_observations"


def observed_source():
    evidence, markdown = source()
    sha = evidence["sources"][0]["sha256"]
    run_id = "a" * 32
    observation = {
        "schema": "headroom.runtime_optimizer_observations.v1",
        "status": "observed",
        "scope": "selected_run_cooperative_optimizer_capture_only",
        "selected_run_id": run_id,
        "selected_round": None,
        "source_sha256": sha,
        "source_binding": "capture source digest matches retained entrypoint source",
        "capture_complete": True,
        "reported_complete": True,
        "logical_boundary_complete": True,
        "parameter_update_sets_complete": True,
        "optimizer_call_counts_consistent": True,
        "optimizer_step_calls": 20,
        "successful_optimizer_step_calls": 20,
        "logical_updates": 20,
        "parameters": {
            "catalog_entries": 34,
            "catalog_numel": 1234,
            "requires_grad_true_entries": 34,
            "requires_grad_true_numel": 1234,
            "requires_grad_false_entries": 0,
            "requires_grad_false_numel": 0,
            "registered_parameter_numel": 1234,
            "catalog_numel_matches_registered_count": True,
        },
        "updates": {
            "recorded_logical_updates": 20,
            "complete_update_set_records": 20,
            "all_catalog_updated_records": 20,
            "all_catalog_parameters_updated_each_record": True,
            "updated_entries_per_complete_record_range": [34, 34],
            "updated_numel_per_complete_record_range": [1234, 1234],
            "optimizer_classes": ["torch.optim.sgd.SGD"],
            "unrecognized_optimizer_class_records": 0,
        },
        "optimizer_group_hyperparameters": {
            "status": "observed",
            "configurations": [
                {"id": "c001", "present": {"lr": ["float", 0.0001], "momentum": ["int", 0]}}
            ],
        },
    }
    evidence["run_id"] = run_id
    context = evidence["execution_context"]
    context.update(
        schema="headroom.solver_execution.v1",
        selected_run_id=run_id,
        selected_round=None,
        source_files=[{"path": "entry.py", "sha256": sha}],
        runtime_optimizer_observations=observation,
    )
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    return evidence, markdown


def blocked(reason="ambiguous"):
    answer = payload()
    answer.update(
        needs_more_info=True,
        evidence_requests=[
            {
                "field": PREFIX + ".updates",
                "reason": reason,
                "detail": "The selected candidate requires interpreting actual update coverage.",
                "evidence_ref": PREFIX + ".updates",
                "source_line_start": None,
                "source_line_end": None,
                "blocking_scope": "current_plan",
                "blocked_plan_ids": ["fix"],
            }
        ],
    )
    return answer


def test_exact_supplied_values_repeat_without_mutation_or_new_proof():
    evidence, _ = observed_source()
    before = copy.deepcopy(evidence)
    repeated = supplied_runtime_observation(evidence, PREFIX + ".updates")
    original = evidence["execution_context"]["runtime_optimizer_observations"]
    assert repeated["status"] == original["status"]
    assert repeated["selected_run_id"] == original["selected_run_id"]
    assert repeated["source_sha256"] == original["source_sha256"]
    assert repeated["logical_updates"] == 20
    assert repeated["parameters"] == original["parameters"]
    assert repeated["updates"] == original["updates"]
    assert not repeated["resolves_prerequisite"]
    assert not repeated["native_optimizer_implementation_authenticated"]
    assert not repeated["numerical_equivalence_proven"]
    assert evidence == before
    assert len(json.dumps(repeated, ensure_ascii=True).encode()) <= MAX_OBSERVATION_FEEDBACK_BYTES


@pytest.mark.parametrize(
    "mutation",
    [
        "evidence_run",
        "missing_evidence_run",
        "context_run",
        "observation_run",
        "source",
        "context_source",
        "missing_sources",
        "missing_context_sources",
        "round",
        "invalid_round",
        "bad_schema",
    ],
)
def test_mismatch_or_missing_identity_never_becomes_an_observation(mutation):
    evidence, _ = observed_source()
    context = evidence["execution_context"]
    observation = context["runtime_optimizer_observations"]
    if mutation == "evidence_run":
        evidence["run_id"] = "b" * 32
    elif mutation == "missing_evidence_run":
        del evidence["run_id"]
    elif mutation == "context_run":
        context["selected_run_id"] = "b" * 32
    elif mutation == "observation_run":
        observation["selected_run_id"] = "b" * 32
    elif mutation == "source":
        evidence["sources"][0]["sha256"] = "b" * 64
    elif mutation == "context_source":
        context["source_files"][0]["sha256"] = "b" * 64
    elif mutation == "missing_sources":
        del evidence["sources"]
    elif mutation == "missing_context_sources":
        del context["source_files"]
    elif mutation == "round":
        observation["selected_round"] = 2
    elif mutation == "invalid_round":
        context["selected_round"] = observation["selected_round"] = True
    else:
        context["schema"] = "untrusted"
    assert supplied_runtime_observation(evidence, PREFIX + ".updates") is None


def test_partial_zero_update_or_unknown_is_not_promoted_to_twenty():
    evidence, _ = observed_source()
    observed = evidence["execution_context"]["runtime_optimizer_observations"]
    observed.update(
        status="partial",
        logical_updates=0,
        optimizer_step_calls=0,
        successful_optimizer_step_calls=0,
    )
    observed["updates"] = {}
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert repeated["status"] == "partial" and repeated["logical_updates"] == 0
    assert "updates" not in repeated
    observed["status"] = "unverified"
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert repeated["status"] == "unverified"
    assert "logical_updates" not in repeated and "parameters" not in repeated


def test_whitelist_omits_arbitrary_strings_secrets_and_oversized_components():
    evidence, _ = observed_source()
    observed = evidence["execution_context"]["runtime_optimizer_observations"]
    observed["secret"] = "private_canary"
    observed["parameters"]["password"] = "private_canary"
    observed["updates"]["optimizer_classes"] = ["private_canary"]
    observed["optimizer_group_hyperparameters"]["configurations"][0]["present"]["api_key"] = [
        "float",
        1.0,
    ]
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert "private_canary" not in json.dumps(repeated)
    assert "api_key" not in json.dumps(repeated)
    assert "optimizer_group_hyperparameters" not in repeated
    assert len(json.dumps(repeated, ensure_ascii=True).encode()) <= MAX_OBSERVATION_FEEDBACK_BYTES


def test_original_availability_and_genuine_unknown_still_control_readiness():
    evidence, _ = observed_source()
    diagnosis = Diagnosis.model_validate(blocked())
    before = diagnosis.model_dump()
    issue = SimpleNamespace(
        code="PREREQUISITE_REVIEW", message="Declared prerequisite", path="/evidence_requests/0"
    )
    context = validation_issue_context(issue, diagnosis, evidence)["request_context"]
    assert context["declared_reference_observation"]["runtime_values_verified"] is False
    assert context["separate_supplied_runtime_observation"]["logical_updates"] == 20
    assert context["needs_more_info"] is True
    assert len(json.dumps(context, ensure_ascii=True).encode()) <= MAX_CONTEXT_BYTES
    assert diagnosis.model_dump() == before


@pytest.mark.parametrize(
    "reason,purpose", [("ambiguous", "prerequisite_review"), ("missing", "validation_repair")]
)
def test_actual_second_sdk_wire_receives_same_facts_without_new_calls_or_false_ready(
    reason, purpose
):
    evidence, markdown = observed_source()
    before = copy.deepcopy(evidence)
    requests = []
    answer = blocked(reason)
    with provider_client([answer], requests) as client:
        result = diagnose_with_router(
            LLMRouter(client),
            markdown,
            evidence=evidence,
            goal="reclaim",
            policy={},
            max_supplements=1,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert len(requests) == 2
    assert [item["purpose"] for item in result.response_request_modes] == ["initial", purpose]
    first = json.loads(requests[0]["messages"][2]["content"])
    original = first["execution_context"]["runtime_optimizer_observations"]
    last = requests[1]["messages"][-1]["content"]
    if reason == "ambiguous":
        metadata = json.loads(last.split("Prior prerequisite metadata: ", 1)[1])
        echoed = metadata["prior_requests"][0]["separate_supplied_runtime_observation"]
        assert metadata["new_runtime_evidence_supplied"] is False
    else:
        metadata = json.loads(last.split("Errors: ", 1)[1])
        echoed = metadata["issues"][0]["request_context"]["separate_supplied_runtime_observation"]
    assert echoed["logical_updates"] == original["logical_updates"]
    assert echoed["updates"] == original["updates"]
    assert echoed["selected_run_id"] == original["selected_run_id"]
    assert result.diagnosis.needs_more_info and not result.ready_for_patch
    assert all(
        request["max_tokens"] == 2000 and request.get("tools") is None for request in requests
    )
    assert evidence == before


def test_complete_other_optimizer_excludes_recipe_without_native_or_target_proof():
    evidence, _ = observed_source()
    catalog = runtime_operator_catalog(execution_context=evidence["execution_context"])
    assert catalog["operators"] == []
    excluded = catalog["excluded_operators"][0]
    assert excluded["reported_optimizer_classes"] == ["torch.optim.sgd.SGD"]
    assert excluded["selection_status"] == "not_applicable_to_observed_optimizer_class"
    assert catalog["current_target_applicability"] == "unverified"
    assert catalog["current_runtime_availability"] == "unverified"
    assert "python_import" not in json.dumps(catalog)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_run",
        "invalid_run",
        "stale_run",
        "source",
        "partial",
        "unverified",
        "incomplete",
        "adamw",
        "custom",
        "mixed",
        "unknown_classes",
        "no_updates",
    ],
)
def test_uncertain_native_or_mixed_optimizer_is_never_excluded_or_certified(mutation):
    evidence, _ = observed_source()
    context = evidence["execution_context"]
    observed = context["runtime_optimizer_observations"]
    if mutation == "missing_run":
        del context["selected_run_id"]
    elif mutation == "invalid_run":
        context["selected_run_id"] = "not-a-run"
    elif mutation == "stale_run":
        context["selected_run_id"] = "b" * 32
    elif mutation == "source":
        context["source_files"][0]["sha256"] = "b" * 64
    elif mutation in {"partial", "unverified"}:
        observed["status"] = mutation
    elif mutation == "incomplete":
        observed["parameter_update_sets_complete"] = False
    elif mutation == "adamw":
        observed["updates"]["optimizer_classes"] = ["torch.optim.adamw.AdamW"]
    elif mutation == "custom":
        observed["updates"]["optimizer_classes"] = ["custom.AdamW"]
    elif mutation == "mixed":
        observed["updates"]["optimizer_classes"] = [
            "torch.optim.sgd.SGD",
            "torch.optim.adamw.AdamW",
        ]
    elif mutation == "unknown_classes":
        observed["updates"]["unrecognized_optimizer_class_records"] = 1
    else:
        observed["logical_updates"] = 0
    catalog = runtime_operator_catalog(execution_context=context)
    assert len(catalog["operators"]) == 1
    assert "excluded_operators" not in catalog
    assert catalog["current_target_applicability"] == "unverified"


@pytest.mark.parametrize("run_id,expected", [("a" * 32, "a" * 32), ("invalid", None), (None, None)])
def test_execution_identity_comes_from_capture_not_observer_self_reference(run_id, expected):
    context = execution_context(
        script="entry.py",
        script_args=[],
        execution_argv=None,
        source_files=[],
        selected_round=None,
        repository_mode=False,
        seed=1,
        max_steps=20,
        device="cuda",
        allocator_conf=None,
        runtime_result={
            "run_id": run_id,
            "runtime_optimizer_observations": {"selected_run_id": "b" * 32},
        },
    )
    assert context["selected_run_id"] == expected


def test_selective_catalog_is_inside_original_solver_bound():
    evidence, _ = observed_source()
    fields = solver_prompt_context(execution_context=evidence["execution_context"])
    assert fields["runtime_operator_catalog"]["operators"] == []
    assert len(json.dumps(fields, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    assert bound_optimizer_observation(evidence["execution_context"]) is not None


def test_missing_requested_component_is_not_presented_as_observed():
    evidence, _ = observed_source()
    del evidence["execution_context"]["runtime_optimizer_observations"]["updates"]
    assert supplied_runtime_observation(evidence, PREFIX + ".updates") is None


@pytest.mark.parametrize("bad_status", [[], {}])
def test_malformed_optional_group_status_does_not_cancel_scoped_fact_echo(bad_status):
    evidence, _ = observed_source()
    evidence["execution_context"]["runtime_optimizer_observations"][
        "optimizer_group_hyperparameters"
    ]["status"] = bad_status
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert repeated["status"] == "observed" and repeated["logical_updates"] == 20
    assert "optimizer_group_hyperparameters" not in repeated


def test_only_betas_can_be_a_numeric_pair_in_repeated_group_options():
    evidence, _ = observed_source()
    present = evidence["execution_context"]["runtime_optimizer_observations"][
        "optimizer_group_hyperparameters"
    ]["configurations"][0]["present"]
    pair = ["tuple", [["float", 0.9], ["float", 0.999]]]
    present["betas"] = pair
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert (
        repeated["optimizer_group_hyperparameters"]["configurations"][0]["present"]["betas"] == pair
    )
    present["lr"] = pair
    repeated = supplied_runtime_observation(evidence, PREFIX)
    assert "optimizer_group_hyperparameters" not in repeated
