"""Offline proposed regression for the narrow model-width intent gap."""

import pytest

from headroom.diagnose import _proposes_model_shrink, validate_diagnosis
from headroom.verify.policy import (
    check_cli_changes,
    check_parameter_counts,
    check_source_changes,
)


@pytest.mark.parametrize(
    "text",
    [
        "Reduce model width",
        "Decrease the model width (--width) to reduce activation and parameter memory quadratically.",
        "Decrease hidden_size",
        "Decreasing the model width",
        "Do not reduce model width; decrease layers",
        "Do not avoid decreasing model width",
    ],
)
def test_model_width_or_decrease_is_a_positive_shrink_action(text):
    assert _proposes_model_shrink(text)


@pytest.mark.parametrize(
    "text",
    [
        "Do not reduce model width",
        "Avoid decreasing model width",
        "Reduce model width memory",
        "Decrease model width workspace",
        "Reduce workspace allocations in model layers",
        "Use a fixed model width while reducing memory overhead",
    ],
)
def test_negation_and_memory_objects_do_not_become_shape_changes(text):
    assert not _proposes_model_shrink(text)


def diagnosis_payload():
    return {
        "root_causes": [
            {
                "id": "c1",
                "title": "Observed activations",
                "category": "activations",
                "bytes_gb": 1.0,
                "evidence_refs": ["stk_observed"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "width",
                "type": "config",
                "title": "Reduce model width",
                "description": (
                    "Decrease the model width (--width) to reduce activation and "
                    "parameter memory quadratically."
                ),
                "expected_saving_gb": 0.5,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Changes model capacity.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Synthetic regression, not a model measurement."],
    }


@pytest.mark.parametrize("allowed", [False, True])
def test_omitted_requires_policy_cannot_hide_width_change(allowed):
    result = validate_diagnosis(
        diagnosis_payload(),
        evidence={"stack_catalog": {"stk_observed": []}},
        policy={"allow_model_change": allowed},
    )
    codes = [issue.code for issue in result.issues]
    assert ("MODEL_CHANGE_FORBIDDEN" in codes) is (not allowed)
    assert result.ready_for_patch is allowed


def test_real_cli_and_source_shape_guards_remain_in_force():
    cli = check_cli_changes(["--width", "256"], ["--width", "128"])
    assert not cli.allowed
    assert "MODEL_SHRUNK" in [issue.code for issue in cli.issues]
    source = check_source_changes(
        {"train.py": "width = 256\n"},
        {"train.py": "width = 128\n"},
    )
    assert not source.allowed
    assert "MODEL_SHRUNK" in [issue.code for issue in source.issues]


@pytest.mark.parametrize("after", [128, None])
def test_smaller_or_unobserved_parameter_count_remains_rejected(after):
    report = check_parameter_counts(256, after)
    assert not report.allowed
