"""Explicit completion caps for the ordinary pipeline and a versioned study.

This is request configuration, never a billing clamp or funding authorization.
The named study is the original independent end-to-end three-arm comparison.
"""

from typing import Literal

StudyProtocol = Literal["common-diagnosis-4000-v1"]
COMMON_4000 = "common-diagnosis-4000-v1"
DEFAULT_DIAGNOSIS_CAP = 16384
STUDY_DIAGNOSIS_CAP = 4000
PATCH_CAP = 4000
PROMPT_CAP_MARKER = "{{HEADROOM_DIAGNOSIS_COMPLETION_CAP}}"
STUDY_CONDITIONS = ("full_ultra", "traceback_ultra", "full_super")
STUDY_SCENARIOS = (
    "s1_batch_too_big",
    "s2_capacity_v2",
    "s3_eval_no_grad_missing",
    "s4_loss_accumulation_graph",
    "s5_fragmentation_varlen",
    "s6_full_vocab_logits_fp32",
    "s7_frozen_params_optimizer_state",
    "s8_two_models_resident",
)


STUDY_CONTROL_FIELDS = frozenset(
    {
        "seed",
        "script_args",
        "target",
        "reclaim_reduction_pct",
        "allocator_conf",
        "numerical_reference",
        "search_mode",
        "per_run_budget_usd",
        "campaign_budget_usd",
        "daily_budget_usd",
    }
)


def diagnosis_cap(study_protocol=None):
    if study_protocol is None:
        return DEFAULT_DIAGNOSIS_CAP
    if type(study_protocol) is str and study_protocol == COMMON_4000:
        return STUDY_DIAGNOSIS_CAP
    raise ValueError("Unknown explicit diagnosis study protocol")


def diagnosis_prompt(template, study_protocol=None):
    cap = diagnosis_cap(study_protocol)
    if template.count(PROMPT_CAP_MARKER) != 1:
        raise ValueError("Diagnosis prompt requires exactly one completion-cap marker")
    return template.replace(PROMPT_CAP_MARKER, str(cap))


def study_metadata(study_protocol=None):
    diagnosis_cap(study_protocol)
    if study_protocol is None:
        return {}
    return {
        "study_protocol": {
            "schema": "headroom.ablation-study.v1",
            "id": COMMON_4000,
            "design": "independent_end_to_end",
            "diagnosis_max_completion_tokens": STUDY_DIAGNOSIS_CAP,
            "patch_max_completion_tokens": PATCH_CAP,
            "diagnosis_enable_thinking": True,
            "patcher_enable_thinking": False,
            "tokens_include_hidden_reasoning": True,
            "full_provider_bound_required": True,
            "conditions": list(STUDY_CONDITIONS),
            "policy_names": ["strict"],
            "seed": 1337,
            "request_equivalence": "same source, seed, parameters, policy, search mode and budgets; actual evidence and repair trajectories may differ",
            "pure_model_causal_claim": False,
        }
    }


def validate_study_selection(study_protocol, cases, conditions, policy_names):
    metadata = study_metadata(study_protocol)
    if not metadata:
        return metadata
    if (
        tuple(case.id for case in cases) != STUDY_SCENARIOS
        or any(case.group != "synthetic" for case in cases)
        or tuple(conditions) != STUDY_CONDITIONS
        or tuple(policy_names) != ("strict",)
    ):
        raise ValueError(
            "The study requires the eight v2 synthetic cases, all three ordered conditions and explicit strict policy"
        )
    return metadata
