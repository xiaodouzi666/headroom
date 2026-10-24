"""Exact token accounting. An unknown charge is never a zero-dollar charge."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any


@dataclass(frozen=True)
class Pricing:
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None
    verified: bool = False
    source: str | None = None

    def __post_init__(self):
        for name in ("input_per_million", "output_per_million", "cached_input_per_million"):
            value = getattr(self, name)
            if value is None and name == "cached_input_per_million":
                continue
            if isinstance(value, (float, bool)):
                raise TypeError("Prices must use decimal strings or Decimal, not floats")
            value = Decimal(value)
            if not value.is_finite() or value < 0:
                raise ValueError("Prices must be finite and nonnegative")
            if len(value.as_tuple().digits) > 80 or abs(value.as_tuple().exponent) > 80:
                raise ValueError("Price precision exceeds supported bounds")
            object.__setattr__(self, name, value)
        if self.verified and not self.source:
            raise ValueError("Verified prices require a source")


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int | None = None
    reasoning_tokens: int | None = None

    def __post_init__(self):
        counts = (self.prompt_tokens, self.completion_tokens, self.total_tokens)
        if not all(type(value) is int and value >= 0 for value in counts):
            raise ValueError("Usage counts must be nonnegative integers")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError("Usage totals must equal prompt plus completion tokens")
        for value, upper in (
            (self.cached_tokens, self.prompt_tokens),
            (self.reasoning_tokens, self.completion_tokens),
        ):
            if value is not None and (type(value) is not int or not 0 <= value <= upper):
                raise ValueError("Usage details must be subsets of their token totals")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None):
        if not isinstance(payload, Mapping):
            return None
        prompt = payload.get("prompt_tokens")
        completion = payload.get("completion_tokens")
        if not all(type(value) is int and value >= 0 for value in (prompt, completion)):
            return None
        total = payload.get("total_tokens", prompt + completion)
        if type(total) is not int or total != prompt + completion:
            return None
        counts = []
        for detail, key, upper in (
            ("prompt_tokens_details", "cached_tokens", prompt),
            ("completion_tokens_details", "reasoning_tokens", completion),
        ):
            details = payload.get(detail)
            value = details.get(key) if isinstance(details, Mapping) else None
            if value is not None and (type(value) is not int or not 0 <= value <= upper):
                return None
            counts.append(value)
        return cls(prompt, completion, total, *counts)


@dataclass(frozen=True)
class Cost:
    usd: Decimal | None
    status: str
    reason: str | None = None
    upper_usd: Decimal | None = None
    basis: str | None = None

    def as_dict(self):
        value = {
            "usd": str(self.usd) if self.usd is not None else None,
            "status": self.status,
            "reason": self.reason,
        }
        if self.upper_usd is not None:
            value.update(upper_usd=str(self.upper_usd), basis=self.basis)
        return value


def calculate_cost(usage: Usage | None, pricing: Pricing | None) -> Cost:
    if usage is None:
        return Cost(None, "unknown", "missing_or_invalid_usage")
    if pricing is None or not pricing.verified:
        return Cost(None, "unknown", "missing_or_unverified_pricing")
    cached = usage.cached_tokens
    if cached is None and pricing.cached_input_per_million is not None:
        with localcontext() as context:
            context.prec = 256 + max(
                len(str(usage.prompt_tokens)), len(str(usage.completion_tokens))
            )
            upper = (
                usage.prompt_tokens
                * max(pricing.input_per_million, pricing.cached_input_per_million)
                + usage.completion_tokens * pricing.output_per_million
            ) / Decimal(1_000_000)
        return Cost(
            None,
            "upper_bound",
            "missing_cached_token_usage",
            upper,
            "verified_tariff_missing_cache_count",
        )
    if cached and pricing.cached_input_per_million is None:
        return Cost(None, "unknown", "missing_cached_input_price")
    cached = cached or 0
    with localcontext() as context:
        context.prec = 256 + max(len(str(usage.prompt_tokens)), len(str(usage.completion_tokens)))
        input_charge = (usage.prompt_tokens - cached) * pricing.input_per_million
        if cached:
            input_charge += cached * pricing.cached_input_per_million
        # Reasoning tokens are already a subset of completion_tokens; never add them twice.
        output_charge = usage.completion_tokens * pricing.output_per_million
        return Cost((input_charge + output_charge) / Decimal(1_000_000), "known")


@dataclass(frozen=True)
class CallRecord:
    role: str
    model: str
    attempt: int
    outcome: str
    elapsed_seconds: float
    usage: Usage | None
    cost: Cost
    http_status: int | None = None
    response_model: str | None = None


@dataclass
class CostLedger:
    """One entry per network attempt, including failures with unknown billing."""

    entries: list[CallRecord] = field(default_factory=list)

    def add(self, record: CallRecord):
        self.entries.append(record)

    @property
    def known_subtotal_usd(self) -> Decimal:
        with localcontext() as context:
            context.prec = 256 + len(str(len(self.entries)))
            return sum((entry.cost.usd or Decimal(0) for entry in self.entries), Decimal(0))

    @property
    def unknown_attempts(self) -> int:
        return sum(entry.cost.usd is None for entry in self.entries)

    @property
    def total_usd(self) -> Decimal | None:
        return None if self.unknown_attempts else self.known_subtotal_usd
