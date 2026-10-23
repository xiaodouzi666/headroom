"""Structured diagnosis contracts; validation is separate from GPU verification."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Confidence = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class DiagnosisModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RootCause(DiagnosisModel):
    id: Nonempty
    title: Nonempty
    category: Nonempty
    bytes_gb: Nonnegative
    evidence_refs: list[Nonempty] = Field(min_length=1)
    confidence: Confidence


class PlanStep(DiagnosisModel):
    fix_id: Nonempty
    type: Literal["code", "config", "env"]
    title: Nonempty
    description: Nonempty
    expected_saving_gb: Nonnegative
    numerics_impact: Literal["none", "minor", "significant"]
    throughput_impact: Literal["none", "minor", "major"]
    risk: Nonempty
    requires_policy: list[Nonempty]


class VerificationPlan(DiagnosisModel):
    max_steps: int = Field(ge=1)
    compare_loss: bool
    tolerance: Nonnegative


class Diagnosis(DiagnosisModel):
    root_causes: list[RootCause]
    plan: list[PlanStep]
    verification: VerificationPlan
    needs_more_info: bool
    notes: list[str]
