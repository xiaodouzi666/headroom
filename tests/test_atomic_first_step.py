"""R5 draft only: copy to tests after integrating compat-atomic-stage.patch.

Not executed while the R4 source freeze is active. These tests preserve the
original whole-plan savings check and require only a positive first candidate.
"""

import copy

import pytest

from headroom.diagnose import validate_diagnosis


def proposal(*savings, needs_more_info=False):
    return {
        "root_causes": [
            {
                "id": "cause",
                "title": "Captured intermediate storage",
                "category": "activations",
                "bytes_gb": 1.0,
                "evidence_refs": ["stack"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": f"fix-{index}",
                "type": "code",
                "title": "Recompute a source-supported intermediate",
                "description": "Recompute the intermediate while preserving every consumer.",
                "expected_saving_gb": saving,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Measure recomputation cost.",
                "requires_policy": [],
            }
            for index, saving in enumerate(savings)
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": needs_more_info,
        "notes": [],
    }


def validate(payload, required=None):
    return validate_diagnosis(
        payload,
        evidence={"stack_catalog": {"stack": []}},
        policy={},
        required_saving_gb=required,
    )


@pytest.mark.parametrize("required", [None, 0.0, 1.0])
def test_setup_only_first_step_cannot_borrow_later_saving(required):
    payload = proposal(0.0, 2.0)
    original = copy.deepcopy(payload)
    result = validate(payload, required)
    assert not result.ready_for_patch
    assert result.requires_supplement
    assert "SELECTED_STEP_NO_EXPECTED_SAVING" in {issue.code for issue in result.issues}
    issue = next(i for i in result.issues if i.code == "SELECTED_STEP_NO_EXPECTED_SAVING")
    assert issue.path == "/plan/0/expected_saving_gb"
    assert payload == original


def test_zero_estimate_can_remain_a_genuine_nonready_request_for_information():
    result = validate(proposal(0.0, needs_more_info=True), required=2.0)
    assert result.valid
    assert not result.ready_for_patch
    assert not result.requires_supplement
    assert result.diagnosis.needs_more_info


@pytest.mark.parametrize("first", [0.000001, 0.125])
def test_positive_partial_improvement_keeps_original_whole_plan_feasibility(first):
    # The first item need not meet the entire target; successful partial
    # improvements are retained by the existing search contract.
    result = validate(proposal(first, 1.0), required=1.0)
    assert result.valid
    assert result.ready_for_patch
    assert not result.requires_supplement
    assert result.diagnosis.plan[0].expected_saving_gb == first


def test_original_whole_plan_savings_requirement_is_not_removed():
    result = validate(proposal(0.125, 0.25), required=1.0)
    codes = {issue.code for issue in result.issues}
    assert "INSUFFICIENT_EXPECTED_SAVING" in codes
    assert "SELECTED_STEP_NO_EXPECTED_SAVING" not in codes
    assert not result.ready_for_patch


@pytest.mark.parametrize("needs_more_info", [False, True])
@pytest.mark.parametrize("savings", [(-0.01, 2.0), (0.25, -0.01)])
def test_negative_estimates_cannot_hide_behind_later_savings_or_needs_more_info(
    needs_more_info, savings
):
    result = validate(proposal(*savings, needs_more_info=needs_more_info), required=1.0)
    assert not result.valid and not result.ready_for_patch
    assert any(issue.code == "INVALID_SCHEMA" for issue in result.issues)


def test_zero_ready_first_and_insufficient_total_report_both_reasons():
    result = validate(proposal(0.0), required=1.0)
    assert {issue.code for issue in result.issues} >= {
        "SELECTED_STEP_NO_EXPECTED_SAVING",
        "INSUFFICIENT_EXPECTED_SAVING",
    }
