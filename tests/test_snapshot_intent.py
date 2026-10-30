"""Snapshot intent contract: measurements derive from evidence, never model numbers."""

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from headroom.schemas import Diagnosis
from headroom.snapshot_grounding import validate_snapshot_grounding
from headroom.snapshot_intent import (
    MAX_SCHEMA_BYTES,
    SNAPSHOT_INTENT_PROTOCOL,
    SnapshotIntentError,
    build_snapshot_intent_schema,
    derive_snapshot_diagnosis,
)

A = "stk_0000000000000001"
B = "stk_0000000000000002"
HOT = "stk_0000000000000003"


def evidence():
    return {
        "snapshot_sha256": "a" * 64,
        "analysis": {
            "header": {"peak_is_exact": False},
            "stack_catalog": {A: [], B: [], HOT: []},
            "peak_composition": [
                {"stack_id": A, "bytes": 4565352448, "category": "optimizer_state"},
                {"stack_id": B, "bytes": 4565352448, "category": "optimizer_state"},
            ],
            "allocation_hot_paths": [{"stack_id": HOT, "bytes": 91307048960}],
            "category_bytes": {"optimizer_state": 9130704896},
        },
        "presentation": {"peak_stack_ids": [A, B], "allocation_stack_ids": [HOT]},
    }


def intent():
    return {
        "root_causes": [
            {
                "id": "c1",
                "title": "Persistent allocations",
                "category": "optimizer_state",
                "evidence_refs": [A, B],
                "confidence": 0.8,
            }
        ],
        "plan": [],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": True,
        "notes": ["Native peak counters and source correspondence remain unverified."],
        "invocation_claims": [],
        "invocation_refs": [],
        "evidence_requests": [],
    }


def test_host_derives_exact_peak_sum_and_keeps_original_intent_and_unknowns():
    value, prepared = intent(), evidence()
    before = copy.deepcopy((value, prepared))
    derived, provenance = derive_snapshot_diagnosis(value, evidence=prepared, policy={})
    assert (value, prepared) == before
    assert "bytes_gb" not in value["root_causes"][0]
    assert derived["root_causes"][0]["bytes_gb"] == 9.130704896
    assert derived["needs_more_info"] is True and derived["notes"] == value["notes"]
    assert Diagnosis.model_validate(derived)
    assert validate_snapshot_grounding(derived, prepared) == ()
    assert provenance["protocol"] == SNAPSHOT_INTENT_PROTOCOL
    assert provenance["derivations"][0]["cited_peak_bytes"] == 9130704896
    assert provenance["derivations"][0]["decimal_GB"] == "9.130704896"
    assert provenance["causal_contribution_verified"] is False
    assert provenance["native_peak_counter_verified"] is False
    assert provenance["hardware_verification"] == "not_run"


@pytest.mark.parametrize("amount", [0, 3.36, 9.130704896, None])
def test_any_model_authored_bytes_field_is_rejected_not_silently_overwritten(amount):
    value = intent()
    value["root_causes"][0]["bytes_gb"] = amount
    before = copy.deepcopy(value)
    schema = build_snapshot_intent_schema(evidence=evidence(), policy={})
    assert list(Draft202012Validator(schema).iter_errors(value))
    with pytest.raises(SnapshotIntentError, match="SNAPSHOT_INTENT_SCHEMA_REJECTED"):
        derive_snapshot_diagnosis(value, evidence=evidence(), policy={})
    assert value == before


@pytest.mark.parametrize("ref", [HOT, "stk_ffffffffffffffff"])
def test_hotpath_only_and_unknown_refs_are_rejected_by_schema_and_host(ref):
    value, prepared = intent(), evidence()
    value["root_causes"][0]["evidence_refs"] = [ref]
    schema = build_snapshot_intent_schema(evidence=prepared, policy={})
    assert list(Draft202012Validator(schema).iter_errors(value))
    with pytest.raises(SnapshotIntentError, match="SCHEMA_REJECTED"):
        derive_snapshot_diagnosis(value, evidence=prepared, policy={})


def test_missing_peak_and_all_hidden_peaks_stop_before_a_model_schema_is_usable():
    prepared = evidence()
    prepared["presentation"]["peak_stack_ids"] = []
    with pytest.raises(SnapshotIntentError, match="NO_VISIBLE_PEAK"):
        build_snapshot_intent_schema(evidence=prepared, policy={})


def test_duplicate_refs_do_not_inflate_and_cross_cause_overlap_is_explicit():
    value = intent()
    value["root_causes"][0]["evidence_refs"] = [A, A, B]
    second = copy.deepcopy(value["root_causes"][0])
    second.update(id="c2", evidence_refs=[A])
    value["root_causes"].append(second)
    derived, provenance = derive_snapshot_diagnosis(value, evidence=evidence(), policy={})
    assert derived["root_causes"][0]["bytes_gb"] == 9.130704896
    assert derived["root_causes"][1]["bytes_gb"] == 4.565352448
    assert provenance["overlapping_cause_refs"] == [A]
    assert provenance["cross_cause_totals_permitted"] is False
    assert len(provenance["derivations"][0]["unique_references"]) == 2


def test_more_than_three_causes_are_rejected_not_truncated():
    value = intent()
    value["root_causes"] *= 4
    with pytest.raises(SnapshotIntentError, match="SCHEMA_REJECTED"):
        derive_snapshot_diagnosis(value, evidence=evidence(), policy={})
    assert len(value["root_causes"]) == 4


@pytest.mark.parametrize("location", ["note", "plan"])
def test_host_quantities_do_not_bypass_remaining_narrative_guard(location):
    value = intent()
    if location == "note":
        value["notes"].append("3.36 GB live")
    else:
        value["plan"] = [
            {
                "fix_id": "p1",
                "type": "code",
                "title": "Inspect storage",
                "description": "Save 3.36 GB",
                "risk": "Unverified",
                "expected_saving_gb": 0.5,
                "numerics_impact": "none",
                "throughput_impact": "none",
                "requires_policy": [],
            }
        ]
    derived, _ = derive_snapshot_diagnosis(value, evidence=evidence(), policy={})
    assert "SNAPSHOT_MEMORY_QUANTITY_IN_PROSE" in {
        i.code for i in validate_snapshot_grounding(derived, evidence())
    }


def test_dynamic_schema_is_bounded_and_shared_diagnosis_schema_still_requires_bytes():
    prepared = evidence()
    rows = [
        {"stack_id": f"stk_{i:016x}", "bytes": 512, "category": "unknown"} for i in range(1, 41)
    ]
    prepared["analysis"]["peak_composition"] = rows
    prepared["analysis"]["stack_catalog"] = {row["stack_id"]: [] for row in rows}
    prepared["presentation"]["peak_stack_ids"] = [row["stack_id"] for row in rows]
    schema = build_snapshot_intent_schema(evidence=prepared, policy={})
    cause = schema["$defs"]["RootCause"]
    assert "bytes_gb" not in cause["properties"]
    assert cause["additionalProperties"] is False
    assert len(cause["properties"]["evidence_refs"]["items"]["enum"]) == 40
    assert len(json.dumps(schema, ensure_ascii=True).encode()) < MAX_SCHEMA_BYTES
    assert "bytes_gb" in Diagnosis.model_json_schema()["$defs"]["RootCause"]["required"]
