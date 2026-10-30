"""Offline snapshot-only quantitative grounding; no model/GPU/network."""

import copy
import json
from pathlib import Path

import pytest

from headroom.snapshot_grounding import (
    canonical_peak_table,
    render_peak_grounding,
    validate_snapshot_grounding,
)

A = "stk_0000000000000001"
B = "stk_0000000000000002"
C = "stk_0000000000000003"


def evidence():
    return {
        "analysis": {
            "peak_composition": [
                {"stack_id": A, "bytes": 1_000_000_001, "category": "optimizer_state"},
                {"stack_id": B, "bytes": 2_000_000_002, "category": "optimizer_state"},
            ],
            "category_bytes": {"optimizer_state": 3_000_000_003},
            "allocation_hot_paths": [{"stack_id": C, "bytes": 9_000_000_000}],
        },
        "presentation": {"peak_stack_ids": [A, B], "allocation_stack_ids": [C]},
    }


def diagnosis(refs=None, amount=1.000000001):
    return {
        "root_causes": [
            {"title": "Persistent allocation", "bytes_gb": amount, "evidence_refs": refs or [A]}
        ],
        "plan": [
            {
                "title": "Preserve semantics",
                "description": "Inspect lifetimes.",
                "risk": "Unverified.",
                "expected_saving_gb": 0.5,
            }
        ],
        "notes": ["Native counters unknown; no hardware verification."],
        "needs_more_info": True,
    }


def codes(payload, prepared):
    return {issue.code for issue in validate_snapshot_grounding(payload, prepared)}


def test_exact_single_aggregate_and_duplicate_refs_do_not_change_output():
    for refs, amount in [([A], 1.000000001), ([A, B], 3.000000003), ([A, A, B], 3.000000003)]:
        payload, prepared = diagnosis(refs, amount), evidence()
        before = copy.deepcopy((payload, prepared))
        assert validate_snapshot_grounding(payload, prepared) == ()
        assert (payload, prepared) == before
        assert payload["needs_more_info"] is True


@pytest.mark.parametrize(
    ("amount", "valid"),
    [
        (1.0, True),
        (1.000000002, True),
        (0.999999999, False),
        (1.000000003, False),
        (3.36, False),
        (float("inf"), False),
        (float("nan"), False),
        (None, False),
    ],
)
def test_decimal_comparison_tolerance_is_at_most_one_byte(amount, valid):
    assert (not codes(diagnosis(amount=amount), evidence())) is valid


@pytest.mark.parametrize("ref", [C, "stk_ffffffffffffffff"])
def test_lifetime_only_or_missing_peak_is_not_zero(ref):
    assert codes(diagnosis([ref], 0), evidence()) == {"SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE"}


def test_hidden_peak_is_not_usable_and_partial_category_total_is_not_advertised():
    prepared = evidence()
    prepared["presentation"]["peak_stack_ids"] = [A]
    table = canonical_peak_table(prepared["analysis"], [A])
    assert table["rows"] == [
        {"stack_id": A, "peak_bytes": 1_000_000_001, "decimal_GB": "1.000000001"}
    ]
    assert table["complete_category_sums"] == []
    assert codes(diagnosis([B], 2.000000002), prepared) == {"SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE"}
    assert codes(diagnosis([A], 3.000000003), prepared) == {"SNAPSHOT_PEAK_BYTES_MISMATCH"}


def test_category_total_requires_all_contributing_refs_and_matching_analysis_total():
    prepared = evidence()
    table = canonical_peak_table(prepared["analysis"], [A, B])
    assert table["complete_category_sums"] == [
        {
            "heuristic_category": "optimizer_state",
            "peak_bytes": 3_000_000_003,
            "decimal_GB": "3.000000003",
            "all_contributing_refs": [A, B],
        }
    ]
    prepared["analysis"]["category_bytes"]["optimizer_state"] += 10
    assert canonical_peak_table(prepared["analysis"], [A, B])["complete_category_sums"] == []
    assert "not causal ground truth" in render_peak_grounding(prepared["analysis"], [A])


def test_canonical_table_is_bounded_and_invalid_measurements_are_not_zero_filled():
    rows = [{"stack_id": f"stk_{i:016x}", "bytes": i, "category": "unknown"} for i in range(1, 81)]
    table = canonical_peak_table({"peak_composition": rows}, [r["stack_id"] for r in rows])
    assert len(table["rows"]) == 40
    prepared = evidence()
    prepared["analysis"]["peak_composition"][0]["bytes"] = None
    assert codes(diagnosis(amount=0), prepared) == {"SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE"}


@pytest.mark.parametrize(
    "text",
    [
        "3.36 GB live",
        "0.033554432GB live",
        "1 GiB",
        ".5 MiB",
        "512 bytes",
        "1 byte",
        "1e9 bytes",
        "1,024 MB",
        "1_024 KiB",
        "64 KB",
        "2 TB",
        "4 gigabytes",
        "2 gibibytes",
        "3.36\u00a0GB",
        "512 B",
        "−0.5 GB",
    ],
)
def test_numeric_memory_units_are_rejected_in_prose(text):
    payload = diagnosis()
    payload["notes"] = [text]
    assert codes(payload, evidence()) == {"SNAPSHOT_MEMORY_QUANTITY_IN_PROSE"}


@pytest.mark.parametrize(
    "text",
    [
        "FP32 parameters and BF16 source context.",
        "A 7B model is unverified.",
        "After 20 updates, verify 0.001 tolerance.",
        "The GB field is not measured here.",
        "Native counters unknown.",
        "Memory may improve; saved bytes remain unverified.",
    ],
)
def test_nonmemory_numbers_and_qualitative_unknowns_are_allowed(text):
    payload = diagnosis()
    payload["notes"] = [text]
    assert validate_snapshot_grounding(payload, evidence()) == ()


@pytest.mark.parametrize("field", ["title", "description", "risk", "evidence_request"])
def test_other_narrative_locations_cannot_hide_memory_amount(field):
    payload = diagnosis()
    if field == "title":
        payload["root_causes"][0]["title"] = "3.36 GB"
    elif field == "evidence_request":
        payload["evidence_requests"] = [{"field": "peak", "detail": "Confirm 3.36 GB"}]
    else:
        payload["plan"][0][field] = "3.36 GB"
    assert "SNAPSHOT_MEMORY_QUANTITY_IN_PROSE" in codes(payload, evidence())


def test_saved_s2_error_is_rejected_without_altering_the_historical_answer():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/snapshot_s2_grounding_error.json").read_text()
    )
    original = copy.deepcopy(fixture)
    issues = validate_snapshot_grounding(fixture["diagnosis"], fixture["evidence"])
    assert "SNAPSHOT_PEAK_BYTES_MISMATCH" in {i.code for i in issues}
    assert any(
        i.code == "SNAPSHOT_MEMORY_QUANTITY_IN_PROSE" and i.path == "notes[5]" for i in issues
    )
    assert fixture == original
    assert fixture["source_run_id"] == "cd565dc58c9e4d668b48621532dfbe2b"
    assert fixture["diagnosis"]["root_causes"][0]["bytes_gb"] == 9.130704


def test_duplicate_peak_identity_is_ambiguous_not_zero_or_double_counted():
    prepared = evidence()
    prepared["analysis"]["peak_composition"].append(
        {"stack_id": A, "bytes": 0, "category": "optimizer_state"}
    )
    for amount in (0, 1.000000001):
        assert codes(diagnosis([A], amount), prepared) == {"SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE"}
    assert canonical_peak_table(prepared["analysis"], [A, B])["complete_category_sums"] == []


def test_missing_peak_never_passes_one_byte_tolerance():
    prepared = evidence()
    prepared["analysis"]["peak_composition"] = []
    for amount in (0, 0.000000001):
        assert codes(diagnosis([A], amount), prepared) == {"SNAPSHOT_PEAK_REFERENCE_UNAVAILABLE"}
