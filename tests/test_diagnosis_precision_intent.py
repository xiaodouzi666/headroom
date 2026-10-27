"""Plan prose may describe existing precision without authorizing a dtype edit."""

import copy

import pytest

from headroom.diagnose import _proposes_precision_change, validate_diagnosis


@pytest.mark.parametrize(
    "text",
    [
        "Preserve existing BF16.",
        "Keep BF16 logits in the current dtype.",
        "The current BF16 producer remains unchanged.",
        "Source already produces BF16 logits.",
        "BF16 logits are already produced by the model.",
        "Preserve the existing BF16 logits to FP32 conversion while chunking its consumer.",
        "Chunk existing BF16 logits before the unchanged FP32 conversion.",
        "Release BF16 buffers after their final consumer.",
        "Do not enable BF16.",
        "Avoid introducing autocast.",
        "Without converting model weights to FP16.",
        "Preserve BF16 but do not enable FP16.",
        "Keep existing autocast.",
    ],
)
def test_preserved_facts_lifetime_and_local_negation_are_not_precision_changes(text):
    assert _proposes_precision_change(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Enable BF16.",
        "BF16 optimization.",
        "Autocast for memory savings.",
        "Cast weights to FP16.",
        "Use mixed precision.",
        "Run training in half precision.",
        "model.half()",
        "Preserve BF16 but convert weights to FP16.",
        "Preserve existing BF16 and enable autocast.",
        "Do not use BF16; cast weights to FP16.",
        "Avoid BF16, use FP16.",
        "Do not avoid BF16.",
        "Never avoid introducing autocast.",
        "Do not preserve BF16.",
        "Enable existing BF16.",
        "Cast weights to existing BF16.",
        "Convert weights to existing BF16 tensors.",
        "Switch computation to current BF16.",
        "Enable computation under current BF16.",
        "Set model dtype to existing BF16.",
        "Change model dtype to current BF16.",
        "Run training in current BF16.",
        "Replace FP32 weights with existing BF16 weights.",
        "Force computation into existing BF16.",
        "Preserve BF16 compatibility by downcasting the FP32 weights.",
        "Maintain BF16 execution by casting all FP32 parameters to that dtype.",
        "Existing BF16 will replace FP32 for all model parameters.",
        "Preserve existing BF16 and cast all FP32 weights to that dtype.",
        "Keep BF16; convert all weights to that dtype.",
        "Preserve existing BF16 then use FP16.",
        "The current BF16 producer remains unchanged; introduce autocast.",
        "Release BF16 buffers and convert weights to FP16.",
    ],
)
def test_affirmative_ambiguous_mixed_and_double_negative_changes_remain_rejected(text):
    assert _proposes_precision_change(text) is True


def payload(description, *, impact="none"):
    return {
        "root_causes": [
            {
                "id": "cause",
                "title": "Live temporary buffers",
                "category": "temporaries",
                "bytes_gb": 3.0,
                "evidence_refs": ["stk_actual"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "fix",
                "type": "code",
                "title": "Reduce temporary lifetime",
                "description": description,
                "expected_saving_gb": 1.0,
                "numerics_impact": impact,
                "throughput_impact": "minor",
                "risk": "Real source and numerical checks remain required.",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Offline prose test, not a candidate acceptance."],
    }


@pytest.mark.parametrize(
    "description,impact,forbidden",
    [
        ("Preserve existing BF16 while chunking the existing FP32 consumer.", "none", False),
        ("Preserve BF16 but cast weights to FP16.", "none", True),
        ("Preserve existing BF16.", "minor", True),
        ("Autocast memory optimization.", "none", True),
    ],
)
def test_real_diagnosis_validation_preserves_numeric_impact_gate(description, impact, forbidden):
    value = payload(description, impact=impact)
    original = copy.deepcopy(value)
    verdict = validate_diagnosis(
        value,
        evidence={"stack_catalog": {"stk_actual": []}},
        policy={"allow_numerics_change": False},
        required_saving_gb=0.5,
    )
    assert ("NUMERICS_CHANGE_FORBIDDEN" in [issue.code for issue in verdict.issues]) is forbidden
    assert value == original


def test_bad_lifetime_proposal_is_not_claimed_semantically_valid_by_precision_classifier():
    # This is deliberately incorrect code: removing a value before its consumer
    # remains invalid. This narrow prose predicate certifies neither its source
    # semantics nor policy/runtime acceptance.
    text = "Delete BF16 logits before logits.float(); preserve the existing precision."
    assert _proposes_precision_change(text) is False


def test_title_preservation_cannot_hide_description_cast():
    value = payload("Cast all FP32 weights to that dtype.")
    value["plan"][0]["title"] = "Preserve existing BF16"
    verdict = validate_diagnosis(
        value,
        evidence={"stack_catalog": {"stk_actual": []}},
        policy={"allow_numerics_change": False},
        required_saving_gb=0.5,
    )
    assert "NUMERICS_CHANGE_FORBIDDEN" in [issue.code for issue in verdict.issues]
