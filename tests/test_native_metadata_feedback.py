"""New metadata reference and scoped repetition; old observations remain intact."""

import copy
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_diagnosis_bounded_repair import provider_client
from test_scoped_observation_feedback import PREFIX, blocked, observed_source

from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import FINAL48_DIAGNOSIS_ONLY
from headroom.evidence_blockers import (
    MAX_CATALOG_BYTES,
    MAX_FIELD_ENTRIES,
    MAX_SOURCE_FILES,
    build_evidence_availability_catalog,
    evidence_reference_catalog,
)
from headroom.llm.router import LLMRouter
from headroom.observation_feedback import (
    MAX_OBSERVATION_FEEDBACK_BYTES,
    supplied_runtime_observation,
)
from headroom.schemas import Diagnosis
from headroom.validation_feedback import MAX_CONTEXT_BYTES, validation_issue_context

NATIVE = PREFIX + ".parameter_tensor_metadata"


def with_metadata():
    evidence, markdown = observed_source()
    observation = evidence["execution_context"]["runtime_optimizer_observations"]
    observation["parameter_tensor_metadata"] = {
        "status": "observed",
        "scope": "sampled_parameters_only_not_states",
        "events": [1, 20, 20],
        "parameters": 34,
        "all_observed": {
            "dtype": "float32",
            "device_type": "cuda",
            "device_index": 0,
            "layout": "strided",
            "is_leaf": True,
        },
        "changed_parameters": 0,
        "unsupported_observations": 0,
        "state_tensors": "not_captured",
    }
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    return evidence, markdown


def test_new_field_is_independently_advertised_after_all_old_entries():
    evidence, markdown = with_metadata()
    before = copy.deepcopy(evidence)
    old_evidence = copy.deepcopy(evidence)
    del old_evidence["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    old = build_evidence_availability_catalog(old_evidence, markdown)
    new = build_evidence_availability_catalog(evidence, markdown)
    assert new["entries"][:-1] == old["entries"]
    entry = new["entries"][-1]
    assert entry["evidence_ref"] == NATIVE and entry["availability"] == "visible"
    assert entry["runtime_values_verified"] is False and entry["text_availability_only"] is True
    assert NATIVE in evidence_reference_catalog({"evidence_availability_catalog": new})
    assert len(new["entries"]) <= MAX_SOURCE_FILES + MAX_FIELD_ENTRIES
    assert len(json.dumps(new, ensure_ascii=True).encode()) <= MAX_CATALOG_BYTES
    assert evidence == before


def test_optional_field_never_displaces_old_fields_or_sources_at_byte_limit(monkeypatch):
    evidence, markdown = with_metadata()
    old_evidence = copy.deepcopy(evidence)
    del old_evidence["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    old = build_evidence_availability_catalog(old_evidence, markdown)
    limit = len(json.dumps(old, ensure_ascii=True).encode())
    monkeypatch.setattr("headroom.evidence_blockers.MAX_CATALOG_BYTES", limit)
    new = build_evidence_availability_catalog(evidence, markdown)
    assert new["entries"] == old["entries"]
    assert len(json.dumps(new, ensure_ascii=True).encode()) <= limit


def test_optional_field_uses_only_spare_existing_flat_entry_capacity(monkeypatch):
    evidence, markdown = with_metadata()
    old_evidence = copy.deepcopy(evidence)
    del old_evidence["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    old = build_evidence_availability_catalog(old_evidence, markdown)
    field_count = sum(item["kind"] == "field" for item in old["entries"])
    monkeypatch.setattr("headroom.evidence_blockers.MAX_SOURCE_FILES", 1)
    monkeypatch.setattr("headroom.evidence_blockers.MAX_FIELD_ENTRIES", field_count)
    new = build_evidence_availability_catalog(evidence, markdown)
    assert new["entries"] == old["entries"]
    assert NATIVE not in evidence_reference_catalog({"evidence_availability_catalog": new})


@pytest.mark.parametrize("status", ["unverified", "unsupported"])
def test_parent_unknown_status_never_advertises_native_values_as_known(status):
    evidence, markdown = with_metadata()
    evidence["execution_context"]["runtime_optimizer_observations"]["status"] = status
    catalog = build_evidence_availability_catalog(evidence, markdown)
    entry = next(item for item in catalog["entries"] if item["evidence_ref"] == NATIVE)
    assert entry["availability"] == "unknown" and entry["runtime_values_verified"] is False
    repeated = supplied_runtime_observation(evidence, NATIVE)
    assert repeated["status"] == status and "parameter_tensor_metadata" not in repeated


def test_scoped_native_repeat_preserves_existing_component_without_other_proofs():
    evidence, _ = with_metadata()
    before = copy.deepcopy(evidence)
    repeated = supplied_runtime_observation(evidence, NATIVE)
    expected = evidence["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    assert repeated["parameter_tensor_metadata"] == expected
    assert set(repeated["parameter_tensor_metadata"]) == set(expected)
    assert "parameters" not in repeated and "updates" not in repeated
    assert repeated["native_optimizer_implementation_authenticated"] is False
    assert (
        repeated["numerical_equivalence_proven"] is False
        and repeated["resolves_prerequisite"] is False
    )
    assert len(json.dumps(repeated, ensure_ascii=True).encode()) <= MAX_OBSERVATION_FEEDBACK_BYTES
    assert evidence == before


@pytest.mark.parametrize("status", ["partial", "unverified", "not_captured"])
def test_partial_missing_and_unverified_component_status_stays_honest(status):
    evidence, _ = with_metadata()
    value = evidence["execution_context"]["runtime_optimizer_observations"][
        "parameter_tensor_metadata"
    ]
    if status == "partial":
        value.update(status=status, all_observed=None, changed_parameters=1)
    else:
        value.clear()
        value["status"] = status
    repeated = supplied_runtime_observation(evidence, NATIVE)["parameter_tensor_metadata"]
    assert repeated["status"] == status
    assert repeated.get("all_observed") is None


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "source",
        "round",
        "missing_component",
        "dtype",
        "boolean_count",
        "wrong_count",
        "wrong_events",
        "bad_state",
        "arbitrary_uniform_key",
        "contradictory_status",
    ],
)
def test_stale_or_malformed_native_metadata_is_not_repeated(fault):
    evidence, _ = with_metadata()
    context = evidence["execution_context"]
    observed = context["runtime_optimizer_observations"]
    metadata = observed["parameter_tensor_metadata"]
    if fault == "run":
        evidence["run_id"] = "b" * 32
    elif fault == "source":
        evidence["sources"][0]["sha256"] = "b" * 64
    elif fault == "round":
        observed["selected_round"] = 2
    elif fault == "missing_component":
        del observed["parameter_tensor_metadata"]
    elif fault == "dtype":
        metadata["all_observed"]["dtype"] = "private_canary"
    elif fault == "boolean_count":
        metadata["parameters"] = True
    elif fault == "wrong_count":
        metadata["parameters"] = 33
    elif fault == "wrong_events":
        metadata["events"][1] = 19
    elif fault == "bad_state":
        metadata["state_tensors"] = "proven"
    elif fault == "arbitrary_uniform_key":
        metadata["all_observed"]["password"] = "private_canary"
    else:
        metadata["status"] = "observed"
        metadata["all_observed"] = None
    assert supplied_runtime_observation(evidence, NATIVE) is None


def test_existing_reference_repeats_are_byte_identical_to_before_module():
    snapshot = (
        Path(__file__).parents[1]
        / "reports/native-metadata-feedback-integration-20261030/before/observation_feedback.py.txt"
    )
    loader = importlib.machinery.SourceFileLoader("native_feedback_before", str(snapshot))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    evidence, _ = with_metadata()
    for reference in (
        PREFIX,
        PREFIX + ".parameters",
        PREFIX + ".updates",
        PREFIX + ".optimizer_group_hyperparameters",
    ):
        assert supplied_runtime_observation(
            evidence, reference
        ) == module.supplied_runtime_observation(evidence, reference)


def test_feedback_context_exposes_exact_new_component_but_keeps_real_dependency():
    evidence, _ = with_metadata()
    reply = blocked("ambiguous")
    reply["evidence_requests"][0]["field"] = NATIVE
    reply["evidence_requests"][0]["evidence_ref"] = NATIVE
    diagnosis = Diagnosis.model_validate(reply)
    before = diagnosis.model_dump()
    issue = type(
        "Issue",
        (),
        {
            "code": "PREREQUISITE_REVIEW",
            "message": "Declared dependency",
            "path": "/evidence_requests/0",
        },
    )()
    context = validation_issue_context(issue, diagnosis, evidence)["request_context"]
    assert (
        context["separate_supplied_runtime_observation"]["parameter_tensor_metadata"]["status"]
        == "observed"
    )
    assert context["declared_reference_observation"]["runtime_values_verified"] is False
    assert len(json.dumps(context, ensure_ascii=True).encode()) <= MAX_CONTEXT_BYTES
    assert diagnosis.model_dump() == before and diagnosis.needs_more_info


def test_two_mock_requests_revalidate_without_clearing_need_or_adding_a_call():
    evidence, markdown = with_metadata()
    first = blocked("missing")
    first["evidence_requests"][0].update(field=NATIVE, evidence_ref=NATIVE)
    second = copy.deepcopy(first)
    second["evidence_requests"][0]["reason"] = "ambiguous"
    requests = []
    with provider_client([first, second], requests) as client:
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
    assert [r.get("max_completion_tokens", r.get("max_tokens")) for r in requests] == [2000, 2000]
    assert NATIVE in requests[0]["messages"][0]["content"]
    assert "sampled_parameters_only_not_states" in requests[1]["messages"][-1]["content"]
    assert result.valid and result.diagnosis.needs_more_info and not result.ready_for_patch
    assert not any(issue.code == "UNKNOWN_EVIDENCE_REFERENCE" for issue in result.issues)
