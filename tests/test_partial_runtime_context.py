"""Partial observations stay distinct from complete optimizer-update proof."""

import copy
import json

import pytest
from test_reference_context import bound_baseline, context
from test_runtime_input_observations import result, source

from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.solver_context import runtime_input_observations, solver_prompt_context


def oom_result():
    value = result()
    value.update(status="oom", steps=0)
    value["pairing_capture"].update(
        complete=False, reason="captured initialized tensors before training loop", updates=[]
    )
    value["optimizer_update_observation"] = {
        "logical_updates": 0,
        "optimizer_step_calls": 0,
    }
    return value


def test_oom_exposes_only_observed_initialization_not_effective_batch_or_update_proof():
    value = oom_result()
    before = copy.deepcopy(value)
    facts = runtime_input_observations(value, source())
    assert facts["status"] == "unverified"
    assert facts["initial_tensors"]["status"] == "observed"
    assert facts["initial_tensors"]["tensors"]["train_inputs"]["shape"] == [3, 7]
    assert facts["initial_tensors"]["workload_equivalence_proven"] is False
    assert facts["logical_updates"]["status"] == "not_reached"
    assert facts["logical_updates"]["observed_optimizer_updates"] == 0
    for key in (
        "tensors",
        "effective_batch_per_optimizer_update",
        "backwards_per_optimizer_update",
    ):
        assert key not in facts
        assert key not in facts["logical_updates"]
    assert facts["target_effective_configuration"] == "unverified"
    assert value == before


@pytest.mark.parametrize("bad", ["digest", "shape", "missing", "reason", "finalize", "source"])
def test_incomplete_or_unbound_initialization_does_not_claim_observed_tensors(bad):
    value = oom_result()
    sources = source()
    if bad == "digest":
        value["pairing_capture"]["tensors"]["train_inputs"]["sha256"] = "invalid"
    elif bad == "shape":
        value["pairing_capture"]["tensors"]["train_inputs"]["shape"] = [True]
    elif bad == "missing":
        value["pairing_capture"]["tensors"].pop("eval_inputs")
    elif bad == "reason":
        value["pairing_capture"]["reason"] = "initialization capture failed: RuntimeError"
    elif bad == "finalize":
        value["capture_complete"] = False
    else:
        sources[0]["sha256"] = "e" * 64
    facts = runtime_input_observations(value, sources)
    assert facts["status"] in {"unverified", "unsupported"}
    assert "initial_tensors" not in facts
    assert "tensors" not in facts


@pytest.mark.parametrize("bad", ["step", "backwards", "batch", "count"])
def test_partial_or_inconsistent_updates_do_not_hide_valid_initial_tensors(bad):
    value = result()
    if bad == "step":
        value["pairing_capture"]["updates"][0]["step"] = 2
    elif bad == "backwards":
        value["pairing_capture"]["updates"][0]["backwards"] = 2
    elif bad == "batch":
        value["pairing_capture"]["updates"][0]["effective_batch"] = 5
    else:
        value["steps"] = 19
        value["pairing_capture"]["updates"].pop()
    facts = runtime_input_observations(value, source())
    assert facts["status"] == "unverified"
    assert facts["initial_tensors"]["status"] == "observed"
    assert facts["logical_updates"]["status"] == "unverified"
    assert "effective_batch_per_optimizer_update" not in facts


def test_complete_twenty_updates_retains_legacy_fields_and_component_evidence():
    facts = runtime_input_observations(result(), source())
    assert facts["status"] == "observed"
    assert facts["tensors"] == facts["initial_tensors"]["tensors"]
    assert facts["logical_updates"]["status"] == "observed"
    assert facts["logical_updates"]["effective_batch_per_optimizer_update"] == 3
    assert facts["logical_updates"]["observed_optimizer_updates"] == 20


@pytest.mark.parametrize("bad", ["missing", "bool", "has_calls"])
def test_zero_pairing_updates_alone_does_not_claim_update_boundary_was_not_reached(bad):
    value = oom_result()
    if bad == "missing":
        value.pop("optimizer_update_observation")
    elif bad == "bool":
        value["optimizer_update_observation"]["logical_updates"] = False
    else:
        value["optimizer_update_observation"]["optimizer_step_calls"] = 1
    facts = runtime_input_observations(value, source())
    assert facts["initial_tensors"]["status"] == "observed"
    assert facts["logical_updates"]["status"] == "unverified"


def test_catalogue_exposes_exact_child_without_promoting_parent_or_missing_update_child():
    facts = runtime_input_observations(oom_result(), source())
    catalog = build_evidence_availability_catalog(
        {"execution_context": {"runtime_input_observations": facts}}, "no source"
    )
    entries = {entry["evidence_ref"]: entry for entry in catalog["entries"]}
    root = "execution_context.runtime_input_observations"
    assert entries[root]["availability"] == "unknown"
    assert entries[root + ".initial_tensors"]["availability"] == "visible"
    assert entries[root + ".logical_updates"]["availability"] == "unknown"
    assert all(item["runtime_values_verified"] is False for item in entries.values())
    assert len(json.dumps(catalog, ensure_ascii=True).encode()) <= 8192


def test_checkpoint_family_is_capability_only_with_no_candidate_source_or_success(tmp_path):
    value = context(bound_baseline(tmp_path))
    boundary = value["source_contract_boundary"]
    family = boundary["reviewed_edit_families"][0]
    assert family["kind"] == "non_reentrant_activation_checkpoint"
    assert family["api"] == "torch.utils.checkpoint.checkpoint"
    assert "use_reentrant=False" in family["requirements"]
    assert boundary["microbatch_or_gradient_accumulation_rewrites_supported"] is False
    assert value["candidate_equivalence_verified"] is None
    assert value["reference_execution_verified"] is None
    assert value["fallback_to_legacy"] is False
    wire = json.dumps(value)
    for forbidden in ("hidden", "s1_batch", "manual", "14.297", "expected_saving", "replacement"):
        assert forbidden not in wire
    solver_prompt_context(numerical_reference_context=value)


def test_unsupported_source_does_not_advertise_checkpoint_family(tmp_path):
    baseline = bound_baseline(tmp_path)
    changed = tmp_path / "changed.py"
    changed.write_text("print(1)\n")
    value = context(baseline, retained_script=changed)
    assert "reviewed_edit_families" not in value["source_contract_boundary"]
    assert value["capability_status"] == "unavailable_under_current_preconditions"


@pytest.mark.parametrize(
    "component,contradicted",
    [
        ("initial_tensors", True),
        ("logical_updates", False),
    ],
)
def test_exact_child_reference_is_in_schema_and_only_visible_child_contradicts_missing(
    component, contradicted
):
    from test_evidence_blockers import checked, payload, request
    from test_evidence_blockers import source as blocker_source

    from headroom.diagnosis_schema import build_diagnosis_schema

    evidence, markdown = blocker_source()
    evidence["execution_context"]["runtime_input_observations"] = runtime_input_observations(
        oom_result(), source()
    )
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    ref = "execution_context.runtime_input_observations." + component
    schema = build_diagnosis_schema(evidence=evidence, policy={})
    assert (
        ref in schema["$defs"]["EvidenceRequest"]["properties"]["evidence_ref"]["anyOf"][0]["enum"]
    )
    reply = payload()
    reply["evidence_requests"] = [
        request(field=ref, evidence_ref=ref, source_line_start=None, source_line_end=None)
    ]
    outcome = checked(reply, evidence)
    assert outcome.diagnosis.needs_more_info and not outcome.ready_for_patch
    assert outcome.requires_supplement is contradicted
    if not contradicted:
        assert outcome.valid


def test_new_children_keep_catalogue_complete_size_bound_with_many_sources():
    from test_evidence_blockers import source as blocker_source

    evidence, markdown = blocker_source()
    evidence["execution_context"]["runtime_input_observations"] = runtime_input_observations(
        oom_result(), source()
    )
    evidence["sources"] *= 1000
    before = copy.deepcopy(evidence)
    catalog = build_evidence_availability_catalog(evidence, markdown)
    assert len(json.dumps(catalog, ensure_ascii=True).encode()) <= 8192
    assert catalog["omitted_entries"] > 0
    assert evidence == before
    solver_prompt_context(evidence_availability_catalog=catalog)


def test_catalogue_count_bound_includes_two_new_fixed_children():
    from headroom.evidence_blockers import (
        MAX_FIELD_ENTRIES,
        MAX_SOURCE_FILES,
        evidence_reference_catalog,
    )

    assert MAX_FIELD_ENTRIES == 5
    entries = [{"evidence_ref": f"ref{i}"} for i in range(MAX_SOURCE_FILES + MAX_FIELD_ENTRIES)]
    evidence = {
        "evidence_availability_catalog": {
            "schema": "headroom.evidence_availability.v1",
            "entries": entries,
        }
    }
    assert len(evidence_reference_catalog(evidence)) == len(entries)
    entries.append({"evidence_ref": "one_too_many"})
    assert evidence_reference_catalog(evidence) == {}
