"""Prepare diagnosis requests and check model claims against evidence and policy."""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from headroom.schemas import Diagnosis

PROMPT_PATH = Path(__file__).parent / "prompts" / "diagnose.md"
PRECISION_CHANGE = re.compile(
    r"\b(?:bf16|bfloat16|fp16|float16|autocast|mixed[\s-]+precision|"
    r"half[\s-]+precision)\b|\.half\s*\(",
    re.IGNORECASE,
)


BATCH_CHANGE = re.compile(
    r"\b(?:micro[\s_-]?batch(?:ing)?|grad(?:ient)?[\s_-]+accumulat(?:ion|e)|"
    r"gradient_accumulation_steps|batch[\s_-]+size)\b|"
    r"\b(?:reduce|change|decrease|increase|shrink|lower|set)\s+(?:the\s+)?batch\b",
    re.IGNORECASE,
)
MODEL_SHRINK = re.compile(
    r"\b(?:delete|remove|halve|reduce|shrink|truncate|cut)\b.{0,60}"
    r"\b(?:layers?|blocks?|hidden[\s_-]+size|vocab(?:ulary)?|sequence[\s_-]+length)\b",
    re.IGNORECASE,
)
TRAINING_TRUNCATION = re.compile(
    r"\b(?:train|run|execute)\s+(?:for\s+)?(?:only|just)\s+(?:one|1)\s+"
    r"(?:step|iteration)\b|\b(?:skip|truncate)\s+(?:the\s+)?(?:training|dataset|data)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DiagnosisIssue:
    code: str
    message: str


@dataclass(frozen=True)
class DiagnosisValidation:
    diagnosis: Diagnosis | None
    issues: tuple[DiagnosisIssue, ...]
    requires_supplement: bool = False
    supplement_request: str | None = None

    @property
    def valid(self) -> bool:
        return not self.issues and self.diagnosis is not None

    @property
    def ready_for_patch(self) -> bool:
        return self.valid and not self.diagnosis.needs_more_info and bool(self.diagnosis.plan)


def build_diagnosis_messages(
    evidence_markdown: str,
    *,
    goal: str,
    policy: Mapping[str, Any],
    required_saving_gb: float | None = None,
) -> list[dict[str, str]]:
    """No network access; generated request is for the Token Factory router only."""
    _check_required_saving(required_saving_gb)
    if not evidence_markdown.strip() or not goal.strip():
        raise ValueError("evidence and goal must be nonempty")
    request = {
        "goal": goal,
        "policy": dict(policy),
        "required_saving_gb": required_saving_gb,
        "evidence_markdown": evidence_markdown,
    }
    return [
        {"role": "system", "content": PROMPT_PATH.read_text()},
        {"role": "user", "content": json.dumps(request, ensure_ascii=False, allow_nan=False)},
    ]


def _check_required_saving(value: float | None) -> None:
    if value is not None and (
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
    ):
        raise ValueError("required_saving_gb must be finite and nonnegative, or unknown (None)")


def validate_diagnosis(
    payload: Any,
    *,
    evidence: Mapping[str, Any],
    policy: Mapping[str, Any],
    required_saving_gb: float | None = None,
) -> DiagnosisValidation:
    """Check schema/references/policy; this does not establish scientific correctness.

    required_saving_gb is supplied by the caller only when it is known. In
    particular a failed OOM request is not treated as the full model's memory need.
    """
    _check_required_saving(required_saving_gb)
    try:
        diagnosis = Diagnosis.model_validate(payload)
    except ValidationError as error:
        locations = [
            ".".join(str(part) for part in item["loc"])
            for item in error.errors(include_input=False, include_url=False)
        ]
        return DiagnosisValidation(
            None,
            (DiagnosisIssue("INVALID_SCHEMA", "Invalid fields: " + ", ".join(locations)),),
        )
    analysis = evidence.get("analysis", evidence)
    catalog = analysis.get("stack_catalog") if isinstance(analysis, Mapping) else None
    if not isinstance(catalog, Mapping) or not catalog:
        return DiagnosisValidation(
            diagnosis,
            (DiagnosisIssue("EVIDENCE_CATALOG_MISSING", "No runtime stack catalog is available."),),
        )
    issues = []
    root_ids = [cause.id for cause in diagnosis.root_causes]
    fix_ids = [step.fix_id for step in diagnosis.plan]
    if len(set(root_ids)) != len(root_ids) or len(set(fix_ids)) != len(fix_ids):
        issues.append(DiagnosisIssue("DUPLICATE_ID", "Cause and plan IDs must each be unique."))
    if not diagnosis.needs_more_info and (not diagnosis.root_causes or not diagnosis.plan):
        issues.append(
            DiagnosisIssue(
                "EMPTY_DIAGNOSIS",
                "A complete diagnosis requires at least one evidenced cause and one plan step.",
            )
        )
    for cause in diagnosis.root_causes:
        if any(reference not in catalog for reference in cause.evidence_refs):
            issues.append(
                DiagnosisIssue(
                    "UNKNOWN_STACK_REFERENCE",
                    f"Cause {cause.id} references a stack outside the runtime evidence catalog.",
                )
            )
    for step in diagnosis.plan:
        for permission in step.requires_policy:
            if policy.get(permission) is not True:
                issues.append(
                    DiagnosisIssue(
                        "POLICY_PERMISSION_DENIED",
                        f"Step {step.fix_id} requires an absent or disabled policy permission.",
                    )
                )
        text = step.title + "\n" + step.description
        batch_allowed = policy.get("allow_batch_grad_accum") is True and not any(
            policy.get(key) is False for key in ("allow_batch_change", "allow_grad_accum")
        )
        if BATCH_CHANGE.search(text) and not batch_allowed:
            issues.append(
                DiagnosisIssue(
                    "BATCH_CHANGE_FORBIDDEN",
                    f"Step {step.fix_id} proposes batch/accumulation changes without permission.",
                )
            )
        if MODEL_SHRINK.search(text) and policy.get("allow_model_change") is not True:
            issues.append(
                DiagnosisIssue(
                    "MODEL_CHANGE_FORBIDDEN",
                    f"Step {step.fix_id} proposes shrinking the model or its inputs.",
                )
            )
        if TRAINING_TRUNCATION.search(text):
            issues.append(
                DiagnosisIssue(
                    "TRAINING_TRUNCATION_FORBIDDEN",
                    f"Step {step.fix_id} proposes truncating training instead of a repair.",
                )
            )
        if policy.get("allow_numerics_change") is not True and (
            step.numerics_impact != "none" or PRECISION_CHANGE.search(text)
        ):
            issues.append(
                DiagnosisIssue(
                    "NUMERICS_CHANGE_FORBIDDEN",
                    f"Step {step.fix_id} changes numerics or names a disallowed precision method.",
                )
            )
    try:
        expected_total = math.fsum(step.expected_saving_gb for step in diagnosis.plan)
    except OverflowError:
        issues.append(
            DiagnosisIssue("INVALID_SAVINGS_TOTAL", "Expected savings overflow the numeric range.")
        )
        return DiagnosisValidation(diagnosis, tuple(issues))
    # An explicit request for evidence may legitimately have no proposed fix yet.
    # Repeating the same evidence to demand a larger estimate cannot supply it.
    insufficient = (
        not diagnosis.needs_more_info
        and required_saving_gb is not None
        and expected_total < required_saving_gb
    )
    supplement = None
    if insufficient:
        issues.append(
            DiagnosisIssue(
                "INSUFFICIENT_EXPECTED_SAVING",
                "The proposed savings do not cover the caller's known required reduction.",
            )
        )
        supplement = (
            f"Proposed savings total {expected_total:g} GB; the required reduction is "
            f"{required_saving_gb:g} GB. Supply additional evidenced, policy-compliant "
            "steps, explain overlap between savings, or explicitly request more information. "
            "Do not inflate estimates to satisfy this check."
        )
    return DiagnosisValidation(
        diagnosis=diagnosis,
        issues=tuple(issues),
        requires_supplement=insufficient,
        supplement_request=supplement,
    )


def diagnose_with_router(
    router,
    evidence_markdown: str,
    *,
    evidence: Mapping[str, Any],
    goal: str,
    policy: Mapping[str, Any],
    required_saving_gb: float | None = None,
    max_supplements: int = 1,
) -> DiagnosisValidation:
    """Call Ultra through the supplied budgeted router; keep invalid evidence invalid.

    Only an insufficient-savings response can request one bounded supplement by
    default. Credentials, pricing and budget authorization belong to the caller.
    """
    if type(max_supplements) is not int or not 0 <= max_supplements <= 3:
        raise ValueError("max_supplements must be between 0 and 3")
    messages = build_diagnosis_messages(
        evidence_markdown, goal=goal, policy=policy, required_saving_gb=required_saving_gb
    )
    for attempt in range(max_supplements + 1):
        response = router.chat("diagnose", messages, Diagnosis, max_tokens=4000)
        result = validate_diagnosis(
            response.parsed,
            evidence=evidence,
            policy=policy,
            required_saving_gb=required_saving_gb,
        )
        if not result.requires_supplement or attempt == max_supplements:
            return result
        messages.extend(
            [
                {"role": "assistant", "content": json.dumps(response.parsed, allow_nan=False)},
                {"role": "user", "content": result.supplement_request},
            ]
        )
    raise AssertionError("Diagnosis loop must return")
