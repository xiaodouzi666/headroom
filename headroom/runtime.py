"""Explicit live-runtime setup from a reviewed profile; never guess prices or caps."""

import hashlib
import json
import stat
import uuid
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

from headroom.api.security import open_regular
from headroom.budget import BudgetExceeded, RunBudgetReached, money
from headroom.config import ROLE_MODELS, ModelSpec, RuntimeConfig, VerifiedCapabilities
from headroom.diagnosis_protocol import named_diagnosis_request_policy
from headroom.llm.admission import (
    LocalEstimateAdmission,
    NativeSchemaEstimateAdmission,
    RuntimeNotReady,
    output_limit,
)
from headroom.llm.client import DEFAULT_HTTP_RETRIES, TokenFactoryClient
from headroom.llm.cost import Pricing
from headroom.llm.preflight import MODEL_ID
from headroom.llm.router import LLMRouter

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BillingBound(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["verified_provider_bound"] = "verified_provider_bound"
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
        return output_limit(self, spec, body)

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
    billing: BillingBound | NativeSchemaEstimateAdmission | LocalEstimateAdmission
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
    run_budget_mode: Literal["strict_reservation", "actual_usage"] = "strict_reservation"
    diagnosis_request_policy: Literal["final48-diagnosis-only-2000-v1"] | None = None
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
        if self.run_budget_mode == "actual_usage" and any(
            not isinstance(item.billing, BillingBound)
            or not item.billing.verified
            or not item.billing.output_cap_includes_reasoning
            for item in self.models.values()
        ):
            raise RuntimeNotReady(
                "Actual-usage run mode requires strict provider bounds for all roles"
            )
        models = {}
        for role, item in self.models.items():
            if isinstance(item.billing, LocalEstimateAdmission) and (
                role != "ultra" or item.model_id != MODEL_ID
            ):
                raise RuntimeNotReady("Local estimate is only available for the pinned Ultra role")
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


def _verify_low_effort_evidence(profile):
    """Verify the independent compatibility receipt without changing money/state."""
    for item in profile.models.values():
        caps = item.capabilities
        if caps.get("low_effort_method") is None:
            continue
        path = Path(caps["low_effort_evidence"])
        project_root = Path(PROJECT_ROOT)
        if path.is_absolute():
            try:
                relative = path.relative_to(project_root)
            except ValueError:
                raise RuntimeNotReady(
                    "Low-effort evidence must remain within the project"
                ) from None
        else:
            relative = path
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise RuntimeNotReady("Low-effort evidence must remain within the project")
        if (
            any(part.lower().startswith(".env") for part in relative.parts)
            or relative.suffix != ".json"
        ):
            raise RuntimeNotReady(
                "Low-effort evidence must be a bounded noncredential JSON artifact"
            )
        # Keep the lexical relative path. Resolving it first could hide a symlink
        # component from open_regular's per-component O_NOFOLLOW traversal.
        with open_regular(project_root, relative.as_posix(), max_bytes=256 * 1024) as handle:
            raw = handle.read(256 * 1024 + 1)
        if (
            len(raw) > 256 * 1024
            or hashlib.sha256(raw).hexdigest() != caps["low_effort_evidence_sha256"]
        ):
            raise RuntimeNotReady("Low-effort evidence hash differs")
        report = json.loads(raw)
        if type(report) is not dict:
            raise RuntimeNotReady("Low-effort evidence must be an object")
        reasoning = report.get("reasoning_tokens")
        completion = report.get("completion_tokens")
        if (
            report.get("scope") != "super_low_effort_schema_code_probe_v1"
            or report.get("accepted") is not True
            or report.get("provenance") != "live"
            or report.get("verdict") != "request_combination_usable_in_one_sample"
            or report.get("finish_reason") != "stop"
            or report.get("response_model") != item.model_id
            or report.get("base_url") != profile.base_url
            or report.get("profile_model_compatibility")
            != item.model_dump(exclude={"capabilities"})
            or type(reasoning) is not int
            or type(completion) is not int
            or not 0 < reasoning <= completion <= 4000
        ):
            raise RuntimeNotReady(
                "Low-effort receipt does not match the reviewed request combination"
            )


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
        _verify_low_effort_evidence(profile)
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
    run_id,
    *,
    profile,
    budget,
    store,
    env_file=PROJECT_ROOT / ".env",
    transport=None,
    max_http_retries=DEFAULT_HTTP_RETRIES,
    low_effort_probe_request_sha256=None,
):
    """No request on construction; each actual retry reserves before transport."""
    config = profile.runtime_config()
    state = budget.snapshot(run_id)
    if state["run_budget_mode"] != profile.run_budget_mode:
        raise RuntimeNotReady("Run budget mode differs from its reviewed runtime profile")
    if profile.run_budget_mode == "actual_usage":
        budget.require_actual_pool()
    pending = {}
    auditors = {}

    def before_attempt(role, spec, attempt, body):
        name = ROLE_MODELS[role]
        policy = profile.models[name].billing
        if isinstance(policy, LocalEstimateAdmission):
            if name not in auditors:
                auditors[name] = policy.load_auditor()
            upper, admission = policy.decide(spec, body, auditors[name])
            prompt_ceiling = None
        else:
            upper = policy.upper_usd(spec, body)
            prompt_ceiling = policy.prompt_token_ceiling
            admission = {
                "admission_kind": "verified_provider_bound",
                "provider_cost_upper_usd": str(upper),
                "provider_prompt_token_ceiling": prompt_ceiling,
            }
        if name == "nano":
            reserved = Decimal(0)
            for row in store.llm_calls(run_id):
                if row.get("model") != spec.model_id:
                    continue
                cost = row.get("cost_usd")
                if (
                    cost is None
                    and row.get("billing_status") == "bounded"
                    and row.get("settled") is True
                    and row.get("admission_kind") == "verified_provider_bound"
                    and row.get("cost_basis") == "verified_tariff_missing_cache_count"
                ):
                    cost = row.get("cost_upper_usd")
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
        budget.reserve(run_id, attempt_id, upper, admission_kind=policy.mode, dispatched=False)
        pending["id"] = attempt_id
        pending["prompt_ceiling"] = prompt_ceiling
        pending["strict_provider_bound"] = isinstance(policy, BillingBound)
        pending["model_id"] = spec.model_id
        pending["completion_ceiling"] = policy.output_limit(spec, body)
        try:
            pending["record_id"] = store.add_llm_call(
                run_id,
                {
                    **admission,
                    "budget_attempt_id": attempt_id,
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
            budget.mark_dispatched(run_id, attempt_id)
        except BaseException:
            # The SDK has not been called while this before-attempt callback runs.
            # Only reservations still marked undispatched may be released.
            try:
                budget.cancel_undispatched(run_id, attempt_id)
            except BaseException:  # noqa: BLE001, S110 - preserve the original cancellation.
                # mark_dispatched may have committed before interruption. Preserve that
                # uncertain reservation and the original exception; never force-release it.
                pass
            else:
                if "record_id" in pending:
                    try:
                        store.update_llm_call(
                            pending["record_id"],
                            {
                                "outcome": "not_dispatched",
                                "settled": True,
                                "cost_usd": "0",
                                "charge_basis": "confirmed_not_dispatched",
                            },
                        )
                    except BaseException:  # noqa: BLE001 - preserve the outer failure.
                        budget.halt(run_id, "local_accounting_incomplete")
            pending.clear()
            raise

    def after_record(record):
        data = asdict(record)
        data["cost"] = record.cost.as_dict()
        data["settled"] = True
        data["budget_attempt_id"] = pending["id"]
        record_id = pending.pop("record_id")
        invalid = record.cost.reason in {"response_model_mismatch", "missing_cached_input_price"}
        prompt_ceiling = pending.pop("prompt_ceiling")
        completion_ceiling = pending.pop("completion_ceiling")
        strict_bound = pending.pop("strict_provider_bound")
        expected_model = pending.pop("model_id")
        if record.usage is not None:
            invalid = invalid or (
                (prompt_ceiling is not None and record.usage.prompt_tokens > prompt_ceiling)
                or record.usage.completion_tokens > completion_ceiling
            )
        bounded = (
            record.cost.status == "upper_bound"
            and record.cost.usd is None
            and record.cost.reason == "missing_cached_token_usage"
            and record.cost.basis == "verified_tariff_missing_cache_count"
            and record.cost.upper_usd is not None
            and strict_bound
            and record.outcome == "response"
            and record.http_status == 200
            and record.response_model == record.model == expected_model
            and record.usage is not None
            and record.usage.cached_tokens is None
            and not invalid
        )
        data["billing_status"] = "unresolved"
        bounded_settled = False

        def record_bound_commit():
            nonlocal bounded_settled
            bounded_settled = True
            data.update(
                billing_status="bounded",
                cost_upper_usd=str(record.cost.upper_usd),
                cost_basis=record.cost.basis,
            )

        try:
            if bounded:
                try:
                    budget.settle_upper_bound(
                        run_id, pending.pop("id"), record.cost.upper_usd, basis=record.cost.basis
                    )
                except RunBudgetReached:
                    # This exception is raised only after committing the bounded settlement.
                    record_bound_commit()
                    raise
                else:
                    record_bound_commit()
            else:
                try:
                    budget.settle(run_id, pending.pop("id"), record.cost.usd, bound_invalid=invalid)
                except RunBudgetReached:
                    if record.cost.usd is not None and not invalid:
                        data["billing_status"] = "known"
                    raise
                else:
                    if record.cost.usd is not None and not invalid:
                        data["billing_status"] = "known"
        finally:
            # Store can mark bounded only after the authoritative ledger commit.
            try:
                store.update_llm_call(record_id, data)
            except BaseException:
                budget.halt(run_id, "local_accounting_incomplete")
                raise
        if record.cost.usd is None and record.outcome == "response" and not bounded_settled:
            raise BudgetExceeded("Provider charge is unknown; further calls stopped")

    def on_request(role, model, attempt, evidence):
        # Capture the SDK-serialized body (including merged extra_body and router
        # schema messages), attached to the already reserved attempt. A local hook
        # failure stops transport; existing conservative accounting remains intact.
        if pending.get("model_id") != model or "record_id" not in pending:
            raise RuntimeNotReady("Prepared request has no matching reserved attempt")
        store.record_llm_request(
            pending["record_id"],
            {**evidence, "role": role, "model": model, "attempt": attempt},
        )

    client = TokenFactoryClient(
        api_key=read_nebius_key(env_file),
        config=config,
        transport=transport,
        before_attempt=before_attempt,
        after_record=after_record,
        on_request=on_request,
        max_http_retries=max_http_retries,
        low_effort_probe_request_sha256=low_effort_probe_request_sha256,
    )
    return RuntimeBundle(
        LLMRouter(
            client,
            diagnosis_request_policy=named_diagnosis_request_policy(
                profile.diagnosis_request_policy
            ),
        ),
        client,
        profile.evidence_token_budget,
    )
