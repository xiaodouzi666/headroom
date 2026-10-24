"""Local admission estimates are reservations, never provider billing guarantees."""

import stat
from decimal import ROUND_CEILING, Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from headroom.budget import money
from headroom.llm.preflight import ASSET_HASHES, MODEL_ID, PreflightRefused, PromptAuditor


class RuntimeNotReady(RuntimeError):
    pass


def output_limit(policy, spec, body):
    """Validate the reviewed output field independently of input-count evidence."""
    fields = {"max_tokens", "max_completion_tokens"}
    if (
        not policy.output_cap_includes_reasoning
        or policy.output_cap_field != spec.output_cap_field
        or set(body).intersection(fields) != {policy.output_cap_field}
        or (isinstance(body.get("extra_body"), dict) and set(body["extra_body"]) & fields)
    ):
        raise RuntimeNotReady("Output cap field differs from the reviewed billing field")
    limit = body[policy.output_cap_field]
    if type(limit) is not int or not 0 < limit <= policy.max_completion_tokens:
        raise RuntimeNotReady("Requested output exceeds the reviewed billing cap")
    return limit


class LocalEstimateAdmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["local_estimate"]  # No default: selecting an estimate must be explicit.
    tokenizer_assets_dir: str = Field(min_length=1)
    token_multiplier: str
    additive_tokens: int = Field(gt=0, le=1_000_000)
    max_prompt_utf8_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    max_completion_tokens: int = Field(gt=0)
    output_cap_field: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"
    output_cap_includes_reasoning: bool
    output_cap_verified: bool
    output_cap_evidence: str = Field(min_length=1)
    risk_acknowledged: bool
    evidence: str = Field(min_length=1)

    @field_validator("tokenizer_assets_dir")
    @classmethod
    def absolute_assets(cls, value):
        if not Path(value).is_absolute():
            raise ValueError("Tokenizer assets require an absolute local directory")
        return value

    @field_validator("token_multiplier")
    @classmethod
    def margin(cls, value):
        if money(value) <= 1:
            raise ValueError("Estimated admission requires a multiplier greater than one")
        return value

    @field_validator("risk_acknowledged")
    @classmethod
    def acknowledged(cls, value):
        if value is not True:
            raise ValueError("Estimated admission risk must be explicitly acknowledged")
        return value

    def output_limit(self, spec, body):
        if not self.output_cap_verified:
            raise RuntimeNotReady("Output cap semantics are not verified")
        return output_limit(self, spec, body)

    def load_auditor(self):
        # No downloader/AutoTokenizer/remote code. Refuse special files before read_bytes.
        root = Path(self.tokenizer_assets_dir)
        try:
            if root.is_symlink() or not root.is_dir():
                raise ValueError
            for name in ASSET_HASHES:
                info = (root / name).lstat()
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 64 * 1024 * 1024:
                    raise ValueError
            return PromptAuditor(root)
        except (OSError, ValueError, ImportError):
            raise RuntimeNotReady(
                "Reviewed local tokenizer assets or dependencies unavailable"
            ) from None

    def decide(self, spec, body, auditor):
        cap = self.output_limit(spec, body)
        if spec.model_id != MODEL_ID:
            raise RuntimeNotReady("Local estimate only supports the pinned Ultra model")
        try:
            audit = auditor.audit(body)
        except PreflightRefused:
            raise RuntimeNotReady(
                "Final request is outside the supported local estimate domain"
            ) from None
        local = audit["local_template"]
        if (
            audit["request"]["compact_json_utf8_bytes"] > self.max_prompt_utf8_bytes
            or audit["provider_only_unmodeled_fields"]
            or audit["historical_tool_id_fields_ignored_by_local_template"]
            or local["exceeds_template_config_max_length"]
        ):
            raise RuntimeNotReady("Final request contains unmodeled or oversized estimate domains")
        price = spec.pricing
        if price is None or not price.verified:
            raise RuntimeNotReady("Live pricing is not verified")
        with localcontext() as context:
            context.prec = 256
            reserved_tokens = (
                int(
                    (Decimal(local["tokens"]) * money(self.token_multiplier)).to_integral_value(
                        rounding=ROUND_CEILING
                    )
                )
                + self.additive_tokens
            )
            reservation = (
                reserved_tokens
                * max(price.input_per_million, price.cached_input_per_million or Decimal(0))
                + cap * price.output_per_million
            ) / Decimal(1_000_000)
        return reservation, {
            "admission_kind": "local_estimate",
            "provider_cost_upper_usd": None,
            "provider_prompt_token_ceiling": None,
            "local_template_tokens": local["tokens"],
            "estimated_prompt_tokens_with_margin": reserved_tokens,
            "token_multiplier": self.token_multiplier,
            "additive_tokens": self.additive_tokens,
            "request_input_form": audit["input_form"],
            "request_sha256": audit["request"]["compact_json_sha256"],
            "request_utf8_bytes": audit["request"]["compact_json_utf8_bytes"],
            "template_sha256": local["sha256"],
            "tokenizer_revision": audit["tokenizer"]["revision"],
            "tokenizer_asset_hashes": {
                name: value["sha256"] for name, value in audit["tokenizer"]["assets"].items()
            },
            "note": "Local estimate with risk margin; actual charges may exceed this reservation.",
        }
