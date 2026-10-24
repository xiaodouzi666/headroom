"""Explicit live-runtime setup from a reviewed profile; never guess prices or caps."""

import json
import stat
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

from headroom.budget import BudgetExceeded, money
from headroom.config import ROLE_MODELS, ModelSpec, RuntimeConfig, VerifiedCapabilities
from headroom.llm.client import TokenFactoryClient
from headroom.llm.cost import Pricing
from headroom.llm.router import LLMRouter

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimeNotReady(RuntimeError):
    pass


class BillingBound(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    prompt_token_ceiling: int = Field(gt=0)
    max_prompt_utf8_bytes: int = Field(gt=0)
    max_completion_tokens: int = Field(gt=0)
    output_cap_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    output_cap_includes_reasoning: bool
    verified: bool
    evidence: str = Field(min_length=1)

    def output_limit(self, spec, body):
        """Accept exactly the reviewed top-level cap, never an SDK override."""
        if not self.verified or not self.output_cap_includes_reasoning:
            raise RuntimeNotReady("Billing token ceiling/cap semantics are not verified")
        cap_fields = {"max_tokens", "max_completion_tokens"}
        if (
            self.output_cap_field != spec.output_cap_field
            or set(body).intersection(cap_fields) != {self.output_cap_field}
            or (
                isinstance(body.get("extra_body"), dict)
                and set(body["extra_body"]).intersection(cap_fields)
            )
        ):
            raise RuntimeNotReady("Output cap field differs from the reviewed billing field")
        limit = body[self.output_cap_field]
        if type(limit) is not int or not 0 < limit <= self.max_completion_tokens:
            raise RuntimeNotReady("Requested output exceeds the reviewed billing cap")
        return limit

    def upper_usd(self, spec, body):
        max_tokens = self.output_limit(spec, body)
        # The profile must independently establish this bound for every accepted
        # prompt up to max_prompt_utf8_bytes. This is not a cl100k approximation.
        request = {
            key: body[key]
            for key in ("messages", "tools", "response_format", "extra_body")
            if key in body
        }
        size = len(json.dumps(request, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > self.max_prompt_utf8_bytes:
            raise RuntimeNotReady("Prompt exceeds the reviewed billing-bound domain")
        price = spec.pricing
        if price is None or not price.verified:
            raise RuntimeNotReady("Live pricing is not verified")
        input_price = max(price.input_per_million, price.cached_input_per_million or Decimal(0))
        with localcontext() as context:
            context.prec = 256
            return (
                self.prompt_token_ceiling * input_price + max_tokens * price.output_per_million
            ) / Decimal(1_000_000)


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: str
    timeout_seconds: int = 120
    input_usd_per_million: str
    output_usd_per_million: str
    cached_input_usd_per_million: str | None = None
    capabilities: dict = Field(default_factory=dict)
    billing: BillingBound
    evidence: str = Field(min_length=1)


class LiveProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    live_enabled: bool = False
    credit_confirmed: bool = False
    available_credit_usd: str
    authorized_total_usd: str
    verified_at: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    base_url: str
    evidence_token_budget: int = Field(gt=0, le=150000)
    models: dict[str, ProfileModel]

    def runtime_config(self):
        if not self.live_enabled or not self.credit_confirmed:
            raise RuntimeNotReady("Token Factory live use and credits have not been confirmed")
        if not 0 < money(self.authorized_total_usd) <= money(self.available_credit_usd):
            raise RuntimeNotReady("Authorized budget exceeds confirmed available credit")
        if len({item.model_id for item in self.models.values()}) != len(self.models):
            raise RuntimeNotReady("Each reviewed model role must have a distinct model ID")
        if set(self.models) != {"ultra", "super", "nano"}:
            raise RuntimeNotReady("Reviewed profile requires Ultra, Super and Nano")
        models = {}
        for role, item in self.models.items():
            models[role] = ModelSpec(
                item.model_id,
                item.timeout_seconds,
                capabilities=VerifiedCapabilities(**item.capabilities),
                pricing=Pricing(
                    item.input_usd_per_million,
                    item.output_usd_per_million,
                    item.cached_input_usd_per_million,
                    verified=True,
                    source=item.evidence,
                ),
                model_verified=True,
                evidence=item.evidence,
                output_cap_field=item.billing.output_cap_field,
            )
        return RuntimeConfig(base_url=self.base_url, live_enabled=True, models=models)


def read_live_profile(path=PROJECT_ROOT / ".cache/tokenfactory-runtime.json"):
    path = Path(path)
    if not path.exists():
        raise RuntimeNotReady(
            "Token Factory reviewed runtime profile is missing; complete T0.4 first"
        )
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        raise RuntimeNotReady("Runtime profile must be a bounded regular local JSON file")
    try:
        profile = LiveProfile.model_validate_json(path.read_text())
        if not profile.live_enabled or not profile.credit_confirmed:
            raise RuntimeNotReady("Token Factory live use and credits have not been confirmed")
        if not 0 < money(profile.authorized_total_usd) <= money(profile.available_credit_usd):
            raise RuntimeNotReady("Authorized budget exceeds confirmed available credit")
        profile.runtime_config()
        return profile
    except RuntimeNotReady:
        raise
    except (OSError, ValueError, TypeError, ArithmeticError):
        raise RuntimeNotReady(
            "Reviewed runtime profile is invalid; values are not echoed"
        ) from None


def read_nebius_key(path=PROJECT_ROOT / ".env"):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise RuntimeNotReady("Private regular .env file with mode 0600 is required")
    key = (dotenv_values(path, interpolate=False).get("NEBIUS_API_KEY") or "").strip()
    if not key:
        raise RuntimeNotReady("NEBIUS_API_KEY is not configured")
    return key


@dataclass
class RuntimeBundle:
    router: LLMRouter
    client: TokenFactoryClient
    evidence_token_budget: int

    def close(self):
        self.client.close()


def build_live_runtime(
    run_id, *, profile, budget, store, env_file=PROJECT_ROOT / ".env", transport=None
):
    """No request on construction; each actual retry reserves before transport."""
    config = profile.runtime_config()
    pending = {}

    def before_attempt(role, spec, attempt, body):
        name = ROLE_MODELS[role]
        upper = profile.models[name].billing.upper_usd(spec, body)
        if name == "nano":
            reserved = Decimal(0)
            for row in store.llm_calls(run_id):
                if row.get("model") != spec.model_id:
                    continue
                cost = row.get("cost_usd")
                if cost is None:
                    cost = row.get("reservation_usd")
                if cost is None:
                    raise BudgetExceeded("Nano prior charge is unresolved without a bound")
                with localcontext() as context:
                    context.prec = 256
                    reserved += money(cost)
            with localcontext() as context:
                context.prec = 256
                exceeds_nano = reserved + upper > Decimal("0.02")
            if exceeds_nano:
                raise BudgetExceeded("Nano annotation budget would exceed 0.02 USD")
        attempt_id = uuid.uuid4().hex
        budget.reserve(run_id, attempt_id, upper)
        pending["id"] = attempt_id
        pending["prompt_ceiling"] = profile.models[name].billing.prompt_token_ceiling
        pending["completion_ceiling"] = profile.models[name].billing.output_limit(spec, body)
        pending["record_id"] = store.add_llm_call(
            run_id,
            {
                "model": spec.model_id,
                "role": role,
                "attempt": attempt,
                "outcome": "pending",
                "settled": False,
                "reservation_usd": str(upper),
                "output_cap_field": spec.output_cap_field,
                "output_cap_tokens": pending["completion_ceiling"],
                "cost_usd": None,
            },
        )["id"]

    def after_record(record):
        data = asdict(record)
        data["cost"] = record.cost.as_dict()
        data["settled"] = True
        store.update_llm_call(pending.pop("record_id"), data)
        invalid = record.cost.reason in {"response_model_mismatch", "missing_cached_input_price"}
        prompt_ceiling = pending.pop("prompt_ceiling")
        completion_ceiling = pending.pop("completion_ceiling")
        if record.usage is not None:
            invalid = invalid or (
                record.usage.prompt_tokens > prompt_ceiling
                or record.usage.completion_tokens > completion_ceiling
            )
        budget.settle(run_id, pending.pop("id"), record.cost.usd, bound_invalid=invalid)

    client = TokenFactoryClient(
        api_key=read_nebius_key(env_file),
        config=config,
        transport=transport,
        before_attempt=before_attempt,
        after_record=after_record,
    )
    return RuntimeBundle(LLMRouter(client), client, profile.evidence_token_budget)
