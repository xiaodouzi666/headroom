"""Versioned plans keep precision policies and historical scores separate."""

import json
from pathlib import Path

import pytest

from headroom.acceptance.protocol_v2 import protocol_plan

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "eval/protocol_v2.json"


def plan(path=PROTOCOL, scope="primary"):
    return protocol_plan(
        path,
        scope=scope,
        per_run_budget_usd="0.6",
        campaign_budget_usd="0.6",
        daily_budget_usd="0.6",
    )


@pytest.mark.parametrize(
    "scope,count,scenarios",
    [
        ("primary", 9, 9),
        ("mvp_policy_matrix", 18, 9),
        ("phase2_policy_matrix", 20, 10),
    ],
)
def test_explicit_policy_matrix_does_not_replace_primary_gate(scope, count, scenarios):
    value = plan(scope=scope)
    assert value["executed"] is False and value["acceptance_certified"] is False
    assert value["planned_pipeline_runs"] == count
    assert len(value["scenarios"]) == scenarios
    assert value["primary_gate"] == {"target_met_minimum": 6, "denominator": 9, "policy": "strict"}
    assert value["historical_scores_modified"] is False
    assert value["calibration_required_before_execution"] is True
    assert value["authorization_expanded"] is False
    assert all("classification" not in name for name in value["scenarios"])
    names = [row["name"] for row in value["policies"]]
    assert names == (["strict"] if scope == "primary" else ["strict", "allow_precision"])
    assert value["policies"][0]["policy"]["allow_numerics_change"] is False
    if scope != "primary":
        assert value["policies"][1]["policy"]["allow_numerics_change"] is True


def test_phase2_hf_and_libraries_remain_separate():
    value = plan(scope="phase2_policy_matrix")
    assert "hf_trainer" in value["scenarios"]
    assert "vit_random" not in value["scenarios"] and "t5_random" not in value["scenarios"]
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["scopes"]["library_acceptance"]["scenario_count"] == 2
    assert protocol["scopes"]["hf_acceptance"]["scenario"] == "hf_trainer"


@pytest.mark.parametrize(
    "section,field,value",
    [
        ("primary", "minimum_target_met", 5),
        ("primary", "scenario_count", 10),
        ("primary", "policy_names", ["allow_precision"]),
        ("policy_comparison", "default_alias", "allow_precision"),
        ("policy_comparison", "combine_policy_successes", True),
        ("s2", "classification_in_primary_denominator", True),
        ("s2", "calibration_controls_count_as_model_repairs", True),
        ("s2", "fit_limit_bytes", 23_000_000_000),
        ("s2", "classification_minimum_fraction", "0.39"),
        ("s2", "required_updates", 19),
        ("s2", "minimum_successful_repair_rounds", 1),
    ],
)
def test_protocol_rejects_silent_gate_or_policy_rewrites(tmp_path, section, field, value):
    protocol = json.loads(PROTOCOL.read_text())
    protocol[section][field] = value
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError):
        plan(path)
