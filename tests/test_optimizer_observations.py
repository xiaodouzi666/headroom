"""Offline capture summaries reach the actual Ultra/Super SDK request paths."""

import builtins
import copy
import json
import os

import pytest
from test_orchestrator import search_run

from headroom import orchestrator
from headroom.evidence_blockers import (
    build_evidence_availability_catalog,
    evidence_reference_catalog,
)
from headroom.optimizer_observations import (
    MAX_OPTIMIZER_OBSERVATION_BYTES,
    runtime_optimizer_observations,
)
from headroom.solver_context import (
    MAX_EXECUTION_BYTES,
    MAX_SOLVER_CONTEXT_BYTES,
    execution_context,
    solver_prompt_context,
)


def captured(*, steps=20, parameters=3, complete=True):
    ids = [f"p{number:05d}" for number in range(1, parameters + 1)]
    return {
        "protocol": "headroom.lab.v1",
        "run_id": "b" * 32,
        "capture_complete": complete,
        "steps": steps,
        "parameter_count": parameters * 7,
        "parameter_count_complete": True,
        "pairing_capture": {
            "source_contract": {"source_sha256": "a" * 64, "supported": False},
        },
        "optimizer_update_observation": {
            "protocol": "headroom.optimizer_updates.v1",
            "complete": complete and steps > 0,
            "logical_boundary_complete": complete,
            "parameter_update_sets_complete": complete and steps > 0,
            "optimizer_step_calls": steps,
            "successful_optimizer_step_calls": steps,
            "logical_updates": steps,
            "parameter_catalog": [
                {"id": identity, "numel": 7, "requires_grad_at_observation": True}
                for identity in ids
            ],
        },
        "step_records": [
            {
                "step": number,
                "optimizer_classes": ["torch.optim.adamw.AdamW"],
                "updated_parameter_ids": list(ids),
                "parameter_update_coverage_complete": complete,
            }
            for number in range(1, steps + 1)
        ],
    }


def sources():
    return [{"path": "train.py", "sha256": "a" * 64}]


def facts(value=None, source_files=None):
    return runtime_optimizer_observations(
        captured() if value is None else value,
        sources() if source_files is None else source_files,
        script="train.py",
        selected_round=2,
    )


def context(value):
    return execution_context(
        script="train.py",
        script_args=[],
        execution_argv=None,
        source_files=sources(),
        selected_round=2,
        repository_mode=False,
        seed=1,
        max_steps=20,
        device="cuda",
        allocator_conf=None,
        runtime_result=value,
    )


def test_unsupported_named_input_contract_does_not_hide_actual_optimizer_observations():
    value = captured(parameters=34)
    before = copy.deepcopy(value)
    result = facts(value)
    assert result["status"] == "observed"
    assert result["selected_run_id"] == "b" * 32
    assert result["source_sha256"] == "a" * 64
    assert result["selected_round"] == 2
    assert result["parameters"]["requires_grad_true_entries"] == 34
    assert result["updates"]["recorded_logical_updates"] == 20
    assert result["updates"]["all_catalog_updated_records"] == 20
    assert result["updates"]["all_catalog_parameters_updated_each_record"] is True
    assert result["optimizer_group_hyperparameters"] == "not_captured"
    assert result["numerical_equivalence_proven"] is False
    assert result["input_coverage_proven"] is False
    visible = context(value)
    assert visible["runtime_input_observations"]["status"] == "unsupported"
    assert visible["runtime_optimizer_observations"] == result
    assert len(json.dumps(result).encode()) <= MAX_OPTIMIZER_OBSERVATION_BYTES
    assert len(json.dumps(visible).encode()) <= MAX_EXECUTION_BYTES
    assert value == before


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "missing_source",
        "duplicate_source",
        "wrong_path",
        "missing_run",
        "invalid_run",
        "invalid_protocol",
    ],
)
def test_missing_or_different_source_and_run_never_certify_selected_capture(change):
    value, catalog = captured(), sources()
    if change == "source":
        catalog[0]["sha256"] = "c" * 64
    elif change == "missing_source":
        value["pairing_capture"].clear()
    elif change == "duplicate_source":
        catalog *= 2
    elif change == "wrong_path":
        catalog[0]["path"] = "other.py"
    elif change == "missing_run":
        value.pop("run_id")
    elif change == "invalid_run":
        value["run_id"] = "SECRET_RUN_TEXT"
    else:
        value["protocol"] = "untrusted.external"
    result = facts(value, catalog)
    assert result["status"] in {"unverified", "unsupported"}
    assert "parameters" not in result
    assert "SECRET_RUN_TEXT" not in json.dumps(result)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_id",
        "invalid_id",
        "invalid_numel",
        "missing_flag",
        "wrong_steps",
        "unknown_updated_id",
        "duplicate_updated_id",
        "wrong_record_sequence",
        "too_many_parameters",
        "too_many_records",
    ],
)
def test_malformed_or_oversized_metadata_cannot_become_complete(change):
    value = captured()
    observation = value["optimizer_update_observation"]
    catalog, records = observation["parameter_catalog"], value["step_records"]
    if change == "duplicate_id":
        catalog.append(copy.deepcopy(catalog[0]))
    elif change == "invalid_id":
        catalog[0]["id"] = "SECRET_IDENTIFIER"
    elif change == "invalid_numel":
        catalog[0]["numel"] = True
    elif change == "missing_flag":
        catalog[0].pop("requires_grad_at_observation")
    elif change == "wrong_steps":
        value["steps"] += 1
    elif change == "unknown_updated_id":
        records[0]["updated_parameter_ids"].append("p99999")
    elif change == "duplicate_updated_id":
        records[0]["updated_parameter_ids"].append("p00001")
    elif change == "wrong_record_sequence":
        records[0]["step"] = 2
    elif change == "too_many_parameters":
        observation["parameter_catalog"] = [catalog[0]] * 65537
    else:
        value["step_records"] = [records[0]] * 10001
    result = facts(value)
    assert result["status"] == "unverified"
    assert "SECRET_IDENTIFIER" not in json.dumps(result)


def test_partial_capture_and_partial_coverage_preserve_observed_prefix_only():
    value = captured(steps=2, complete=False)
    result = facts(value)
    assert result["status"] == "partial"
    assert result["capture_complete"] is False
    assert result["reported_complete"] is False
    assert result["logical_updates"] == 2
    assert result["updates"]["complete_update_set_records"] == 0
    assert result["updates"]["all_catalog_parameters_updated_each_record"] is None


def test_zero_step_oom_retains_catalog_facts_but_never_invents_update_success():
    value = captured(steps=0)
    value["status"] = "oom"
    result = facts(value)
    assert result["status"] == "partial"
    assert result["parameters"]["requires_grad_true_entries"] == 3
    assert result["optimizer_step_calls"] == 0
    assert result["logical_updates"] == 0
    assert result["updates"]["recorded_logical_updates"] == 0
    assert result["updates"]["all_catalog_parameters_updated_each_record"] is None


def test_subset_updates_and_frozen_flags_are_not_promoted_to_all_parameter_updates():
    value = captured()
    observation = value["optimizer_update_observation"]
    observation["parameter_catalog"][0]["requires_grad_at_observation"] = False
    for record in value["step_records"]:
        record["updated_parameter_ids"] = ["p00002", "p00003"]
    result = facts(value)
    assert result["parameters"]["requires_grad_false_entries"] == 1
    assert result["parameters"]["requires_grad_true_entries"] == 2
    assert result["updates"]["all_catalog_parameters_updated_each_record"] is False
    assert result["updates"]["updated_numel_per_complete_record_range"] == [14, 14]


def test_inconsistent_call_counts_cannot_be_complete():
    value = captured()
    value["optimizer_update_observation"]["successful_optimizer_step_calls"] = 0
    result = facts(value)
    assert result["status"] == "partial"
    assert result["optimizer_call_counts_consistent"] is False


def test_non_whitelisted_prose_class_strings_and_secret_fields_are_never_forwarded():
    value = captured()
    value["optimizer_update_observation"]["coverage"] = "SECRET_COVERAGE"
    value["optimizer_update_observation"]["parameter_catalog"][0]["name"] = "SECRET_NAME"
    value["weights"] = "SECRET_WEIGHTS"
    value["step_records"][0]["optimizer_classes"] = ["SECRET_CLASS"]
    result = facts(value)
    wire = json.dumps(result)
    assert "SECRET_" not in wire
    assert result["updates"]["unrecognized_optimizer_class_records"] == 1
    assert "reported class tags" in result["optimizer_classes_basis"]


def test_summary_does_not_read_files_environment_or_import_torch(monkeypatch):
    value = captured()
    original_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            pytest.fail("capture summary must not import torch")
        return original_import(name, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "__import__", no_torch)
        patch.setattr(builtins, "open", lambda *args, **kwargs: pytest.fail("no file read"))
        patch.setattr(os, "getenv", lambda *args: pytest.fail("no environment read"))
        result = facts(value)
    assert result["status"] == "observed"


def test_shared_context_counts_observations_under_existing_total_bound():
    visible = context(captured())
    shared = solver_prompt_context(execution_context=visible)
    assert shared["execution_context"]["runtime_optimizer_observations"] == facts()
    assert len(json.dumps(shared, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES


def test_both_fresh_real_sdk_request_paths_receive_same_selected_optimizer_facts(
    tmp_path, monkeypatch
):
    real_context = orchestrator.execution_context

    def with_offline_capture(**kwargs):
        value = captured()
        kwargs["source_files"] = [{**item, "sha256": "a" * 64} for item in kwargs["source_files"]]
        kwargs["runtime_result"] = value
        return real_context(**kwargs)

    monkeypatch.setattr(orchestrator, "execution_context", with_offline_capture)
    result, store, calls, _, _ = search_run(
        tmp_path, [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}]
    )
    try:
        assert result["target_met"]
        assert len(calls) == 2
        ultra = json.loads(calls[0]["messages"][-1]["content"])
        patch = json.loads(calls[1]["messages"][-1]["content"])["evidence_context"]
        ultra_facts = ultra["execution_context"]["runtime_optimizer_observations"]
        assert ultra_facts == patch["execution_context"]["runtime_optimizer_observations"]
        assert ultra_facts["updates"]["recorded_logical_updates"] == 20
        assert ultra_facts["parameters"]["requires_grad_true_entries"] == 3
        assert ultra["execution_context"]["runtime_input_observations"]["status"] == "unsupported"
        assert calls[0].get("tools") is None and calls[1].get("tools") is None
    finally:
        store.close()


@pytest.mark.parametrize("steps,complete", [(20, True), (2, False), (0, True)])
def test_availability_advertises_only_summary_text_not_runtime_or_equivalence_proof(
    steps, complete
):
    visible = context(captured(steps=steps, complete=complete))
    catalog = build_evidence_availability_catalog({"execution_context": visible}, "")
    entries = evidence_reference_catalog({"evidence_availability_catalog": catalog})
    prefix = "execution_context.runtime_optimizer_observations"
    for suffix in ("", ".parameters", ".updates"):
        assert entries[prefix + suffix]["availability"] == "visible"
        assert entries[prefix + suffix]["text_availability_only"] is True
        assert entries[prefix + suffix]["runtime_values_verified"] is False


def test_missing_optimizer_capture_remains_unsupported_in_availability():
    catalog = build_evidence_availability_catalog({"execution_context": context(None)}, "")
    entries = evidence_reference_catalog({"evidence_availability_catalog": catalog})
    assert (
        entries["execution_context.runtime_optimizer_observations"]["availability"] == "unsupported"
    )
