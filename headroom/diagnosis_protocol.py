"""Explicit completion caps for the ordinary pipeline and a versioned study.

This is request configuration, never a billing clamp or funding authorization.
The named study is the original independent end-to-end three-arm comparison.
"""

from dataclasses import dataclass
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


@dataclass(frozen=True)
class DiagnosisRequestPolicy:
    """One explicit request configuration, not funding or a call-count allowance."""

    id: str = "final48-diagnosis-only-2000-v1"
    max_completion_tokens: int = 2000
    reasoning: bool = False

    def __post_init__(self):
        if (
            self.id != "final48-diagnosis-only-2000-v1"
            or type(self.max_completion_tokens) is not int
            or self.max_completion_tokens != 2000
            or self.reasoning is not False
        ):
            raise ValueError("Unknown explicit diagnosis request policy")


FINAL48_DIAGNOSIS_ONLY = DiagnosisRequestPolicy()


def diagnosis_cap(study_protocol=None, *, request_policy=None):
    if request_policy is not None:
        if (
            study_protocol is not None
            or type(request_policy) is not DiagnosisRequestPolicy
            or request_policy != FINAL48_DIAGNOSIS_ONLY
        ):
            raise ValueError("Request policy must be explicit and cannot mix with a study protocol")
        return request_policy.max_completion_tokens
    if study_protocol is None:
        return DEFAULT_DIAGNOSIS_CAP
    if type(study_protocol) is str and study_protocol == COMMON_4000:
        return STUDY_DIAGNOSIS_CAP
    raise ValueError("Unknown explicit diagnosis study protocol")


def named_diagnosis_request_policy(name):
    """Resolve only the explicit profile identifier; missing selection stays disabled."""
    if name is None:
        return None
    if type(name) is str and name == FINAL48_DIAGNOSIS_ONLY.id:
        return FINAL48_DIAGNOSIS_ONLY
    raise ValueError("Unknown explicit diagnosis request policy")


def carried_diagnosis_request_policy(router):
    """Read a real instance attribute, never a dynamic proxy/MagicMock fallback."""
    try:
        value = vars(router).get("diagnosis_request_policy")
    except TypeError:
        value = None
    if value is not None:
        diagnosis_cap(request_policy=value)
    return value


def resolve_diagnosis_request_policy(*, carried=None, explicit=None, study_protocol=None):
    for value in (carried, explicit):
        if value is not None:
            diagnosis_cap(request_policy=value)
    if carried is not None and explicit is not None and carried != explicit:
        raise ValueError("Explicit diagnosis policy conflicts with the runtime profile")
    selected = carried if explicit is None else explicit
    diagnosis_cap(study_protocol, request_policy=selected)
    return selected


def diagnosis_prompt(template, study_protocol=None, *, request_policy=None):
    cap = diagnosis_cap(study_protocol, request_policy=request_policy)
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
