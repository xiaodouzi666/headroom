"""Bounded data schema for a prepared historical gallery; no API routes or workers."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from headroom.api.security import open_regular

Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Count = Annotated[int, Field(ge=0)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Text = Annotated[str, Field(max_length=8000)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Frame(Record):
    filename: Annotated[str, Field(max_length=512)]
    name: Text
    line: Count


class EvidenceStack(Record):
    id: Annotated[str, Field(pattern=r"^stk_[a-f0-9]{16}$")]
    peak_live_bytes: Count | None
    lifetime_allocated_bytes: Count | None
    frames: Annotated[list[Frame], Field(max_length=512)]


class RootCause(Record):
    title: Text
    category: Text
    confidence: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
    evidence_refs: list[str]


class Diagnosis(Record):
    root_causes: Annotated[list[RootCause], Field(max_length=30)]
    needs_more_info: bool
    notes: Annotated[list[Text], Field(max_length=100)]


class Measurement(Record):
    status: str
    peak_allocated_bytes: Count
    peak_is_exact: bool
    optimizer_updates: Count
    parameter_count: Count
    loss_series: Annotated[list[Finite], Field(max_length=1000)]


class Verification(Record):
    loss_equivalence: Literal["identical", "within_tol", "changed", "n/a", "unknown"]
    numerical_basis: str
    compared_loss_count: Count
    comparison_losses: list[Finite]
    max_loss_delta: Finite | None
    parameter_count_before: Count | None
    parameter_count_after: Count | None
    requested_updates: Count
    comparison_precision: str | None
    checks: dict[str, bool | None]
    note: Text


class Source(Record):
    url: Annotated[str, Field(max_length=2048)]
    title: Text
    provider: Literal["Tavily"]
    version_match: bool | None

    @model_validator(mode="after")
    def safe_url(self):
        parsed = urlsplit(self.url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Source must be a plain HTTPS documentation URL")
        return self


class Asset(Record):
    path: Annotated[
        str,
        Field(pattern=r"^verified-assets/[a-f0-9]{32}/(?:patch\.diff|report\.json|report\.md)$"),
    ]
    sha256: Digest
    bytes: Annotated[int, Field(ge=0, le=8 * 1024 * 1024)]


class Attempt(Record):
    round: Annotated[int, Field(ge=1, le=6)]
    kept: bool
    target_met: bool
    reason: Text
    candidate: Measurement
    verification: Verification


class DiagnosisBinding(Record):
    round: Literal[1]
    stage: Literal["baseline"]
    evidence_json_sha256: Digest
    evidence_markdown_sha256: Digest
    diagnosis_sha256: Digest
    request_payload_sha256: Digest
    request_wire_sha256: Digest


class VerifiedRun(Record):
    run_id: Identifier
    scenario_id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,100}$")]
    title: Text
    description: Text
    created_at: str
    provenance: Literal["live"]
    outcome: Literal["target_met", "not_solved"]
    target: str
    selected_round: int | None
    before: Measurement
    after: Measurement | None
    peak_reduction_pct: Annotated[str, Field(pattern=r"^-?\d+(?:\.\d+)?$")] | None
    verification: Verification | None
    last_attempt: Attempt | None
    diagnosis: Diagnosis
    diagnosis_binding: DiagnosisBinding
    stacks: Annotated[list[EvidenceStack], Field(max_length=200)]
    sources: Annotated[list[Source], Field(max_length=100)]
    limitations: Annotated[list[Text], Field(max_length=30)]
    source_sha256: dict[str, Digest]
    downloads: dict[Literal["patch", "report_json", "report_markdown"], Asset]

    @model_validator(mode="after")
    def coherent(self):
        ids = {s.id for s in self.stacks}
        if len(ids) != len(self.stacks):
            raise ValueError("Duplicate evidence stack")
        refs = {ref for cause in self.diagnosis.root_causes for ref in cause.evidence_refs}
        if not refs <= ids:
            raise ValueError("Unresolved evidence reference")
        for stack in self.stacks:
            if not stack.frames or (
                stack.peak_live_bytes is None and stack.lifetime_allocated_bytes is None
            ):
                raise ValueError("Evidence stack lacks measured bytes or frames")
        if self.outcome == "target_met":
            v = self.verification
            if self.after is None or v is None or self.selected_round is None:
                raise ValueError("Successful run needs selected hardware evidence")
            if (
                self.after.status != "completed"
                or self.after.optimizer_updates < v.requested_updates
                or self.before.parameter_count != self.after.parameter_count
                or v.parameter_count_before != self.before.parameter_count
                or v.parameter_count_after != self.after.parameter_count
                or v.loss_equivalence not in {"identical", "within_tol"}
                or v.compared_loss_count <= 0
                or not v.checks.get("numerical_acceptance")
                or not v.checks.get("parameter_count_unchanged")
                or not v.checks.get("memory_target")
            ):
                raise ValueError("Successful run verification is inconsistent")
            if len(v.comparison_losses) != v.compared_loss_count or v.compared_loss_count > len(
                self.after.loss_series
            ):
                raise ValueError("Compared loss count is inconsistent")
            delta = max(
                abs(a - b)
                for a, b in zip(
                    v.comparison_losses,
                    self.after.loss_series[: v.compared_loss_count],
                    strict=True,
                )
            )
            if delta != v.max_loss_delta:
                raise ValueError("Compared loss delta is inconsistent")
            if self.before.peak_allocated_bytes <= 0:
                raise ValueError("Successful baseline peak must be positive")
            expected = (
                (
                    Decimal(self.before.peak_allocated_bytes)
                    - Decimal(self.after.peak_allocated_bytes)
                )
                * 100
                / Decimal(self.before.peak_allocated_bytes)
            )
            if self.peak_reduction_pct is None or abs(
                expected - Decimal(self.peak_reduction_pct)
            ) > Decimal("1e-20"):
                raise ValueError("Peak reduction is inconsistent")
            if v.loss_equivalence == "identical" and v.max_loss_delta != 0:
                raise ValueError("Identical loss claim has a nonzero delta")
        elif (
            self.after is not None
            or self.verification is not None
            or self.selected_round is not None
        ):
            raise ValueError("Failed candidate must not be presented as a selected repair")
        if "patch" in self.downloads and self.downloads["patch"].bytes == 0:
            raise ValueError("Empty code diff must not be offered as a patch download")
        for asset in self.downloads.values():
            if not asset.path.startswith(f"verified-assets/{self.run_id}/"):
                raise ValueError("Cross-run artifact reference")
        return self


class VerifiedCatalog(Record):
    schema_version: Literal[1]
    publication_status: Literal["prepared_not_enabled"]
    selection_policy: str
    runs: Annotated[list[VerifiedRun], Field(min_length=1, max_length=30)]

    @model_validator(mode="after")
    def unique_runs(self):
        if len({run.run_id for run in self.runs}) != len(self.runs):
            raise ValueError("Duplicate run ID")
        return self


def load_verified(root: Path) -> VerifiedCatalog:
    """Read only explicit curated files; deliberately does not register an HTTP route."""
    with open_regular(root, "verified-runs.json", max_bytes=8 * 1024 * 1024) as handle:
        document = json.load(handle)
    catalog = VerifiedCatalog.model_validate(document)
    for run in catalog.runs:
        for asset in run.downloads.values():
            with open_regular(root, asset.path, max_bytes=8 * 1024 * 1024) as handle:
                raw = handle.read()
            if len(raw) != asset.bytes or hashlib.sha256(raw).hexdigest() != asset.sha256:
                raise ValueError("Published asset fingerprint mismatch")
    return catalog
