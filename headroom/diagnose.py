"""Prepare diagnosis requests and check model claims against evidence and policy."""

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from headroom.diagnosis_schema import build_diagnosis_schema
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
# Match the grammatical object of a shrinking action, not a later mention of
# a layer whose *memory/workspace* is being reduced. These are intent hints;
# applied source and measured parameter-count checks remain authoritative.
MODEL_SHRINK = re.compile(
    r"\b(?:delete|deleting|remove|removing|halve|halving|reduce|reducing|shrink|shrinking|"
    r"decrease|decreasing|truncate|truncating|cut|cutting)\s+"
    r"(?:(?:the|a|an|all|some|any|half|one|two|first|last|every|other|few|total|"
    r"remaining|unused|redundant|input|training|maximum|model(?:[\'’]s)?|"
    r"network(?:[\'’]s)?|transformer|encoder|decoder|attention|\d+)(?:\s+of)?\s+){0,6}"
    r"(?:(?:number|count)\s+of\s+(?:(?:the|model(?:[\'’]s)?|network(?:[\'’]s)?|"
    r"transformer|encoder|decoder)\s+){0,3})?"
    r"(?:layers?|blocks?|width|(?:hidden|embedding)[\s_-]+(?:size|dim(?:ension)?)|"
    r"n_layer|num_layers|num_hidden_layers|n_embd|d_model|"
    r"vocab(?:ulary)?(?:[\s_-]+size)?|(?:sequence|context)[\s_-]+length|"
    r"seq_len|max_seq_len|max_seq_length|block_size|model[\s_-]+depth)\b",
    re.IGNORECASE,
)
_MODEL_SHRINK_NEGATION = re.compile(
    r"\b(?:do\s+not|does\s+not|did\s+not|should\s+not|must\s+not|"
    r"would\s+not|could\s+not|cannot|can['’]t|don['’]t|"
    r"never|not|without|avoid|avoiding|instead\s+of|rather\s+than)"
    r"\s+(?:(?:ever|actually|directly)\s+)?$",
    re.IGNORECASE,
)
_MODEL_MEMORY_OBJECT = re.compile(
    r"(?:['’]s?)?\s+(?:(?:activation|temporary|peak|GPU|CUDA|allocated|cached)\s+){0,3}"
    r"(?:memory|workspace|allocations?|buffers?|caches?|overhead|footprint|storage|usage)\b",
    re.IGNORECASE,
)


def _proposes_model_shrink(text: str) -> bool:
    for match in MODEL_SHRINK.finditer(text):
        if _MODEL_MEMORY_OBJECT.match(text, match.end()):
            continue
        # Negation belongs to this action only. "Do not reduce layers; halve
        # hidden_size" still contains a forbidden second action.
        prefix = re.split(r"[.;!?\n]", text[: match.start()])[-1]
        negation = _MODEL_SHRINK_NEGATION.search(prefix)
        # Do not let "do not avoid reducing layers" hide positive intent.
        if (
            negation is not None
            and _MODEL_SHRINK_NEGATION.search(prefix[: negation.start()]) is None
        ):
            continue
        return True
    return False


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


FEEDBACK_MAX_ROUNDS = 6
FEEDBACK_MAX_BYTES = 64_000
_FEEDBACK_METRICS = (
    "peak_before",
    "peak_after",
    "reduction_pct",
    "step_ms_before",
    "step_ms_after",
    "max_loss_delta",
    "throughput_regression_pct",
    "parameter_count_before",
    "parameter_count_after",
    "loss_tolerance",
)
_FEEDBACK_FLAGS = ("completed", "target_met", "numerics_changed", "observed_precision_change")
_FEEDBACK_TEXT = ("loss_equivalence", "numerical_basis", "comparison_precision", "acceptance_scope")


def round_verification_feedback(row, *, selected_result, selected_round, selected_target_met):
    """Bound recorded verification facts; never promote a rejected candidate to retained state."""
    truncated = []

    def text(value, field, limit=256):
        if not isinstance(value, str):
            return None
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) > limit:
            truncated.append(field)
            return encoded[:limit].decode("utf-8", errors="ignore") + " [truncated]"
        return value

    def number(value):
        try:
            return value if type(value) in (int, float) and math.isfinite(value) else None
        except OverflowError:
            return None

    def flag(value):
        return value if type(value) is bool else None

    def observation(value, prefix):
        value = value if isinstance(value, Mapping) else {}
        exception = value.get("exception")
        exception = exception if isinstance(exception, Mapping) else {}
        oom = value.get("oom")
        oom = oom if isinstance(oom, Mapping) else {}
        return {
            "run_id": text(value.get("run_id"), prefix + ".run_id", 128),
            "status": text(value.get("status"), prefix + ".status", 64),
            "reason": text(value.get("reason"), prefix + ".reason"),
            "error": text(value.get("error"), prefix + ".error", 512),
            "exception": {
                "type": text(exception.get("type"), prefix + ".exception.type", 128),
                "message": text(exception.get("message"), prefix + ".exception.message", 512),
            },
            "oom": {
                key: number(oom.get(key))
                for key in ("requested_bytes", "free_bytes", "requested_gb", "free_gb")
            },
            "capture_complete": flag(value.get("capture_complete")),
            "steps": number(value.get("steps")),
            "peak_allocated_bytes": number(value.get("peak_allocated_bytes")),
            "peak_reserved_bytes": number(value.get("peak_reserved_bytes")),
            "step_ms_median": number(value.get("step_ms_median")),
        }

    original = row.get("verification")
    available = isinstance(original, Mapping)
    verification = None
    if available:
        verification = {key: number(original.get(key)) for key in _FEEDBACK_METRICS}
        verification.update({key: flag(original.get(key)) for key in _FEEDBACK_FLAGS})
        verification.update(
            {key: text(original.get(key), "verification." + key, 256) for key in _FEEDBACK_TEXT}
        )
        checks = original.get("checks")
        checks = checks if isinstance(checks, Mapping) else {}
        selected_checks = {}
        omitted_checks = 0
        for key, value in checks.items():
            if (
                not isinstance(key, str)
                or len(key.encode("utf-8", errors="replace")) > 96
                or len(selected_checks) >= 64
            ):
                omitted_checks += 1
                continue
            selected_checks[key] = flag(value)
        notes = original.get("notes")
        notes = notes if isinstance(notes, list) else []
        verification.update(
            checks=selected_checks,
            checks_omitted=omitted_checks,
            checks_available=isinstance(original.get("checks"), Mapping),
            failed_checks=[key for key, value in selected_checks.items() if value is False],
            unknown_checks=[key for key, value in selected_checks.items() if value is None],
            notes=[
                text(value, f"verification.notes.{index}", 320)
                for index, value in enumerate(notes[:8])
            ],
            notes_omitted=max(0, len(notes) - 8),
        )
    plan = row.get("plan_step")
    plan = plan if isinstance(plan, Mapping) else {}
    result = {
        "round": number(row.get("number")),
        "provenance": text(row.get("provenance"), "provenance", 64),
        "fix_id": text(row.get("fix_id"), "fix_id", 128),
        "change": {
            "type": text(plan.get("type"), "change.type", 32),
            "title": text(plan.get("title"), "change.title"),
            "patch_artifact": text(row.get("patch"), "change.patch_artifact", 512),
        },
        "decision": text(row.get("decision"), "decision", 32),
        "reason": text(row.get("reason"), "reason"),
        "failure": text(row.get("failure"), "failure", 512),
        "verification_available": available,
        "verification": verification,
        "candidate": observation(original.get("after"), "candidate") if available else None,
        "candidate_selected": row.get("decision") == "keep" and row.get("number") == selected_round,
        "selected_after_round": {
            "round": selected_round,
            "basis": "retained_candidate" if selected_round is not None else "original_baseline",
            "target_met": flag(selected_target_met),
            **observation(selected_result, "selected"),
        },
        "truncated_fields": truncated,
    }
    return result


def build_diagnosis_messages(
    evidence_markdown: str,
    *,
    goal: str,
    policy: Mapping[str, Any],
    required_saving_gb: float | None = None,
    verification_feedback: list[Mapping[str, Any]] | None = None,
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
    if verification_feedback is not None:
        if (
            not isinstance(verification_feedback, list)
            or len(verification_feedback) > FEEDBACK_MAX_ROUNDS
        ):
            raise ValueError("verification_feedback must contain at most six round summaries")
        feedback_json = json.dumps(verification_feedback, ensure_ascii=False, allow_nan=False)
        if len(feedback_json.encode("utf-8")) > FEEDBACK_MAX_BYTES:
            raise ValueError("verification_feedback exceeds its bounded context")
        request["verification_feedback"] = json.loads(feedback_json)
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
        if _proposes_model_shrink(text) and policy.get("allow_model_change") is not True:
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


DIAGNOSIS_MAX_COMPLETION_TOKENS = 8192


def diagnose_with_router(
    router,
    evidence_markdown: str,
    *,
    evidence: Mapping[str, Any],
    goal: str,
    policy: Mapping[str, Any],
    required_saving_gb: float | None = None,
    max_supplements: int = 1,
    verification_feedback: list[Mapping[str, Any]] | None = None,
) -> DiagnosisValidation:
    """Call Ultra through the supplied budgeted router; keep invalid evidence invalid.

    Only an insufficient-savings response can request one bounded supplement by
    default. Credentials, pricing and budget authorization belong to the caller.
    """
    if type(max_supplements) is not int or not 0 <= max_supplements <= 3:
        raise ValueError("max_supplements must be between 0 and 3")
    messages = build_diagnosis_messages(
        evidence_markdown,
        goal=goal,
        policy=policy,
        required_saving_gb=required_saving_gb,
        verification_feedback=verification_feedback,
    )
    schema = build_diagnosis_schema(evidence=evidence, policy=policy)
    for attempt in range(max_supplements + 1):
        response = router.chat(
            "diagnose",
            messages,
            schema,
            max_tokens=DIAGNOSIS_MAX_COMPLETION_TOKENS,
            reasoning=False,
        )
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
