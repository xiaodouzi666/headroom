#!/usr/bin/env python3
"""Offline-first, bounded Token Factory probes. Never loads .env or accepts keys in CLI."""

from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import dataclasses
import datetime as dt
import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

ENDPOINTS = (
    "https://api.tokenfactory.us-central1.nebius.com/v1/",
    "https://api.tokenfactory.nebius.com/v1/",
)
MODELS = {
    "ultra": "nvidia/Nemotron-3-Ultra-550b-a55b",
    "super": "nvidia/nemotron-3-super-120b-a12b",
    "nano": "nvidia/nvidia-nemotron-3-nano-30b-a3b",
    "lightning": "nvidia/Nemotron-3_5-Lightning",
}
ULTRA_TIMEOUT = 600
OTHER_TIMEOUT = 120
LONG_SIZES = (64000, 200000, 500000, 900000)
METHODS = (
    "chat",
    "json_object",
    "json_schema",
    "fenced",
    "tools",
    "template_on",
    "template_off",
    "prefix_on",
    "prefix_off",
    "effort_high",
    "effort_none",
    "reasoning_budget",
    "max_thinking_tokens",
)


class Refused(ValueError):
    """A local precondition failed; no request should be made."""


def require_standalone_paid_dispatch() -> None:
    """The external probe allocation is retired; historical flags cannot reopen it."""
    raise Refused(
        "Standalone paid model probes are retired; use the reviewed shared runtime ledger"
    )


def money(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise Refused("invalid monetary value") from exc
    if not result.is_finite() or result < 0:
        raise Refused("monetary values must be finite and nonnegative")
    return result


def resolved_model_ids(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Explicit candidates only; selection never establishes catalogue access."""
    if overrides is None:
        return dict(MODELS)
    if not isinstance(overrides, dict) or set(overrides) - set(MODELS):
        raise Refused("model overrides require known Ultra/Super/Nano/Lightning roles")
    for value in overrides.values():
        if not isinstance(value, str) or not re.fullmatch(
            r"nvidia/[A-Za-z0-9][A-Za-z0-9_.-]{0,191}", value
        ):
            raise Refused("model overrides require exact bounded nvidia/ model identifiers")
    return {**MODELS, **overrides}


def parse_model_overrides(entries: list[str] | None) -> dict[str, str]:
    overrides = {}
    for entry in entries or []:
        role, separator, model_id = entry.partition("=")
        if not separator or role in overrides:
            raise Refused("use --model-id ROLE=EXACT_ID once per role")
        overrides[role] = model_id
    resolved_model_ids(overrides)
    return overrides


@dataclasses.dataclass(frozen=True)
class Probe:
    id: str
    endpoint: str
    role: str | None
    method: str
    approx_input_tokens: int | None = None
    concurrency_group: str | None = None
    model_id: str | None = None

    def __post_init__(self):
        if self.model_id is not None:
            resolved_model_ids({self.role: self.model_id})

    @property
    def model(self) -> str | None:
        return self.model_id if self.model_id is not None else MODELS.get(self.role)


@dataclasses.dataclass(frozen=True)
class Price:
    input_per_million: Decimal
    output_per_million: Decimal
    prompt_token_ceiling: int
    output_cap_field: str
    cached_input_per_million: Decimal | None = None
    reviewed_cache_price_evidence: str | None = None
    allow_catalogue_cache_price_missing: bool = False

    def __post_init__(self):
        if type(self.allow_catalogue_cache_price_missing) is not bool:
            raise Refused("cache-price fallback requires an explicit boolean")
        if self.cached_input_per_million is not None:
            cached = money(self.cached_input_per_million)
            if cached > money(self.input_per_million):
                raise Refused("reviewed cache price exceeds conservative input price")
            object.__setattr__(self, "cached_input_per_million", cached)
        if self.allow_catalogue_cache_price_missing and (
            self.cached_input_per_million is None
            or not isinstance(self.reviewed_cache_price_evidence, str)
            or not self.reviewed_cache_price_evidence.strip()
        ):
            raise Refused("cache-price fallback requires a reviewed price and independent evidence")

    def cost(self, prompt: int, completion: int) -> Decimal:
        return (prompt * self.input_per_million + completion * self.output_per_million) / 1000000


def build_plan(
    suites: list[str] | None = None,
    roles: list[str] | None = None,
    endpoint: str = ENDPOINTS[0],
    long_sizes: list[int] | None = None,
    *,
    model_ids: dict[str, str] | None = None,
    capability_methods: list[str] | None = None,
) -> list[Probe]:
    if endpoint not in ENDPOINTS:
        raise Refused("endpoint is not an official allowlisted Token Factory endpoint")
    selected_models = resolved_model_ids(model_ids)
    suites = suites or ["all"]
    roles = roles or list(MODELS)
    if set(roles) - set(MODELS) or set(suites) - {
        "all",
        "catalogue",
        "capabilities",
        "long",
        "concurrency",
    }:
        raise Refused("unknown role or suite")
    selected = (
        {"catalogue", "capabilities", "long", "concurrency"} if "all" in suites else set(suites)
    )
    methods = METHODS if capability_methods is None else tuple(capability_methods)
    if (
        not methods
        or any(not isinstance(method, str) or method not in METHODS for method in methods)
        or len(set(methods)) != len(methods)
    ):
        raise Refused("capability methods must be known, distinct and nonempty")
    if capability_methods is not None and "capabilities" not in selected:
        raise Refused("--capability-method requires a suite containing capabilities")
    probes = [Probe(f"catalogue-{i}", url, None, "catalogue") for i, url in enumerate(ENDPOINTS)]
    if "capabilities" in selected:
        for role in roles:
            probes.extend(Probe(f"{role}-{method}", endpoint, role, method) for method in methods)
    if "long" in selected:
        for size in long_sizes or LONG_SIZES:
            if size not in LONG_SIZES:
                raise Refused("long-input size is outside the planned staircase")
            probes.append(Probe(f"ultra-long-{size}", endpoint, "ultra", "long_context", size))
    if "concurrency" in selected:
        probes.extend(
            Probe(
                f"super-concurrent-{i}",
                endpoint,
                "super",
                "concurrency",
                concurrency_group="super-4",
            )
            for i in range(4)
        )
    return [
        dataclasses.replace(p, model_id=selected_models[p.role])
        if model_ids and p.role in model_ids
        else p
        for p in probes
    ]


def validate_prices(
    document: dict, roles: set[str], model_ids: dict[str, str] | None = None
) -> dict[str, Price]:
    selected_models = resolved_model_ids(model_ids)
    if roles - set(selected_models):
        raise Refused("unknown model role in reviewed pricing")
    if (
        document.get("verified") is not True
        or document.get("output_caps_include_reasoning") is not True
    ):
        raise Refused("pricing and output-cap behavior need explicit verified confirmations")
    if not document.get("verified_at") or not document.get("source"):
        raise Refused("pricing verification timestamp and source are required")
    output = {}
    for role in roles:
        item = document.get("models", {}).get(selected_models[role])
        if not isinstance(item, dict):
            raise Refused(f"missing verified price/ceiling for role {role}")
        ceiling = item.get("prompt_token_ceiling")
        if type(ceiling) is not int or ceiling <= 0:
            raise Refused(f"invalid verified server prompt-token ceiling for role {role}")
        cap = item.get("output_cap_field")
        if cap not in {"max_tokens", "max_completion_tokens"}:
            raise Refused(f"missing verified output-cap field for role {role}")
        if "input_usd_per_million" not in item or "output_usd_per_million" not in item:
            raise Refused(f"unknown price for role {role}")
        output[role] = Price(
            money(item["input_usd_per_million"]),
            money(item["output_usd_per_million"]),
            ceiling,
            cap,
            money(item["cached_input_usd_per_million"])
            if item.get("cached_input_usd_per_million") is not None
            else None,
            item.get("reviewed_cache_price_evidence"),
            item.get("allow_catalogue_cache_price_missing", False),
        )
    return output


# The verbose Token Factory catalogue advertises token rates per token.
# These non-token fees are present in the reviewed catalogue schema and are not
# included in Price.cost. Missing/null fields cannot establish a zero charge.
CATALOGUE_ZERO_FEES = frozenset({"request", "image", "price_per_video_second", "price_per_minute"})


def catalogue_guard(probe: Probe, price: Price | None, catalogue: dict | None) -> dict:
    """Validate this execution's exact endpoint/model snapshot before paid admission.

    Price remains the old reviewed conservative schema (including any margin);
    lower live rates are safe. This is consistency evidence, not a price lock,
    new capability verification or a model-tokenizer measurement.
    """
    result = {
        "endpoint": probe.endpoint,
        "model": probe.model,
        "status": "refused",
        "detail": "catalogue_unavailable",
        "reviewed": None,
        "observed": None,
    }
    if price is None:
        result["detail"] = "reviewed_price_missing"
        return result
    result["reviewed"] = {
        "input_usd_per_million": str(price.input_per_million),
        "output_usd_per_million": str(price.output_per_million),
        "prompt_token_ceiling": price.prompt_token_ceiling,
        "cached_input_usd_per_million": (
            str(price.cached_input_per_million)
            if price.cached_input_per_million is not None
            else None
        ),
        "allow_catalogue_cache_price_missing": price.allow_catalogue_cache_price_missing,
    }
    if not isinstance(catalogue, dict) or catalogue.get("endpoint") != probe.endpoint:
        return result
    if (
        probe.endpoint not in ENDPOINTS
        or catalogue.get("http_status") != 200
        or catalogue.get("error")
        or not isinstance(catalogue.get("models"), list)
    ):
        result["detail"] = "live_endpoint_catalogue_unavailable"
        return result
    matches = [
        row for row in catalogue["models"] if isinstance(row, dict) and row.get("id") == probe.model
    ]
    if len(matches) != 1:
        result["detail"] = (
            "model_not_in_live_endpoint_catalogue"
            if not matches
            else "duplicate_model_in_live_endpoint_catalogue"
        )
        return result
    metadata = matches[0].get("advertised_metadata")
    if not isinstance(metadata, dict):
        result["detail"] = "catalogue_billing_metadata_missing"
        return result
    result["observed"] = {
        key: metadata[key]
        for key in ("context_length", "max_model_len", "pricing", "price")
        if key in metadata
    }
    context = metadata.get("context_length")
    if type(context) is not int or context <= 0:
        result["detail"] = "catalogue_context_missing_or_invalid"
        return result
    contexts = [context]
    if "max_model_len" in metadata:
        if type(metadata["max_model_len"]) is not int or metadata["max_model_len"] <= 0:
            result["detail"] = "catalogue_context_missing_or_invalid"
            return result
        contexts.append(metadata["max_model_len"])
    if max(contexts) > price.prompt_token_ceiling:
        result["detail"] = "catalogue_context_exceeds_reviewed_ceiling"
        return result
    pricing = metadata.get("pricing")
    if not isinstance(pricing, dict):
        result["detail"] = "catalogue_pricing_missing"
        return result
    if metadata.get("price") is not None:
        result["detail"] = "catalogue_additional_price_schema_unmodeled"
        return result
    cache_missing = pricing.get("input_cache_read") is None
    fallback = cache_missing and price.allow_catalogue_cache_price_missing
    required = {"prompt", "completion"} | CATALOGUE_ZERO_FEES
    if not fallback:
        required.add("input_cache_read")
    missing = sorted(required - set(pricing))
    if missing:
        result.update(detail="catalogue_pricing_field_missing", fields=missing)
        return result
    parsed = {}
    for field_name, value in pricing.items():
        if field_name == "input_cache_read" and fallback:
            continue
        try:
            if value is None or isinstance(value, bool):
                raise Refused("unknown catalogue price")
            parsed[field_name] = money(value)
        except Refused:
            result.update(detail="catalogue_pricing_field_invalid", field=field_name)
            return result
    if fallback:
        with localcontext() as context:
            context.prec = max(28, len(price.cached_input_per_million.as_tuple().digits) + 10)
            parsed["input_cache_read"] = price.cached_input_per_million / 1_000_000
        result.update(
            cache_price_basis="reviewed_external_fallback",
            reviewed_cache_price_evidence=price.reviewed_cache_price_evidence,
            adopted_cache_usd_per_million=str(price.cached_input_per_million),
            catalogue_cache_price_missing=True,
        )
    else:
        result["cache_price_basis"] = "live_catalogue"
    for field_name in sorted(set(parsed) - {"prompt", "completion", "input_cache_read"}):
        if parsed[field_name] != 0:
            result.update(detail="catalogue_unmodeled_fee_nonzero", field=field_name)
            return result
    token_rates = {}
    for field_name, limit in (
        ("prompt", price.input_per_million),
        (
            "input_cache_read",
            min(price.input_per_million, price.cached_input_per_million)
            if price.cached_input_per_million is not None
            else price.input_per_million,
        ),
        ("completion", price.output_per_million),
    ):
        # Avoid rounding a long exact decimal down before its admission comparison.
        with localcontext() as context:
            context.prec = max(28, len(parsed[field_name].as_tuple().digits) + 10)
            per_million = parsed[field_name] * 1_000_000
        token_rates[field_name] = str(per_million)
        if per_million > limit:
            result.update(
                detail="catalogue_token_price_exceeds_reviewed_bound",
                field=field_name,
                observed_usd_per_million=token_rates,
            )
            return result
    result.update(
        status="matched",
        detail="catalogue_within_reviewed_billing_bounds",
        observed_usd_per_million=token_rates,
        non_token_fees="all_advertised_zero",
    )
    return result


class Budget:
    """Reserve all allowed attempts before dispatch; uncertain charges remain reserved."""

    def __init__(self, cap: Decimal):
        if cap <= 0:
            raise Refused("positive money cap required")
        self.cap = cap
        self.charged = Decimal(0)
        self.outstanding = Decimal(0)
        self.actual_known = Decimal(0)
        self.violated = False
        self.billing_bound_unresolved = False
        self.halt_reason = None
        self.lock = threading.Lock()

    def reserve(self, maximum: Decimal) -> None:
        with self.lock:
            if (
                self.violated
                or self.halt_reason
                or self.charged + self.outstanding + maximum > self.cap
            ):
                raise Refused("budget reservation refused")
            self.outstanding += maximum

    def settle(self, reserved: Decimal, charged: Decimal, known: Decimal) -> None:
        with self.lock:
            self.outstanding -= reserved
            self.charged += charged
            self.actual_known += known
            if charged > reserved or self.charged + self.outstanding > self.cap:
                self.violated = True

    def summary(self) -> dict:
        with self.lock:
            return {
                "cap_usd": str(self.cap),
                "actual_known_usd": str(self.actual_known),
                "charged_or_conservatively_retained_usd": str(self.charged),
                "outstanding_reservations_usd": str(self.outstanding),
                "provider_bound_violation": self.violated,
                "billing_bound_unresolved": self.billing_bound_unresolved,
                "halt_reason": self.halt_reason,
            }


def make_payload(probe: Probe, price: Price, max_output: int, encoder=None) -> tuple[dict, dict]:
    messages = [{"role": "user", "content": "Reply with the word headroom."}]
    metadata = {}
    payload = {
        "model": probe.model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        price.output_cap_field: max_output,
    }
    if probe.method in {"json_object", "json_schema", "fenced"}:
        messages[0]["content"] = 'Return JSON exactly {"probe":"headroom","value":7}.'
        schema = {
            "type": "object",
            "properties": {"probe": {"type": "string"}, "value": {"type": "integer"}},
            "required": ["probe", "value"],
            "additionalProperties": False,
        }
        if probe.method == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif probe.method == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "headroom_probe", "strict": True, "schema": schema},
            }
        else:
            messages[0]["content"] += " Put the object in a single fenced json code block."
    elif probe.method == "tools":
        messages[0]["content"] = "Call add with a=2 and b=3. Do not answer in prose."
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two integers.",
                    "parameters": {
                        "type": "object",
                        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                        "required": ["a", "b"],
                        "additionalProperties": False,
                    },
                },
            }
        ]
        payload["tool_choice"] = {"type": "function", "function": {"name": "add"}}
    elif probe.method.startswith(("template_", "prefix_", "effort_")) or probe.method in {
        "reasoning_budget",
        "max_thinking_tokens",
    }:
        messages[0]["content"] = "Compute 17*23+41. Return the answer. Use reasoning if enabled."
        if probe.method.startswith("template_"):
            payload["chat_template_kwargs"] = {"enable_thinking": probe.method == "template_on"}
        elif probe.method.startswith("prefix_"):
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": "/think" if probe.method == "prefix_on" else "/no_think",
                },
            )
        elif probe.method.startswith("effort_"):
            payload["reasoning_effort"] = "high" if probe.method == "effort_high" else "none"
        else:
            payload[probe.method] = 128
    elif probe.method == "long_context":
        if encoder is None:
            import tiktoken

            encoder = tiktoken.get_encoding("cl100k_base")
        needle = "HEADROOM_NEEDLE_" + uuid.uuid4().hex
        prefix = "Read the material. Return only the final needle value.\n"
        suffix = f"\nThe final needle value is {needle}. Return it exactly."
        target = probe.approx_input_tokens
        remaining = max(0, target - len(encoder.encode(prefix + suffix)))
        block = encoder.encode("Calibration passage about GPU memory allocator evidence. ")
        tokens = (block * (remaining // len(block) + 1))[:remaining]
        text = prefix + encoder.decode(tokens) + suffix
        actual_approximation = len(encoder.encode(text))
        if actual_approximation > price.prompt_token_ceiling:
            raise Refused("approximate prompt exceeds verified server token ceiling")
        messages[0]["content"] = text
        metadata = {
            "needle": needle,
            "requested_cl100k_tokens": target,
            "measured_cl100k_tokens": actual_approximation,
            "token_count_kind": "approximation_not_model_tokenizer",
            "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "prompt_utf8_bytes": len(text.encode()),
        }
    return payload, metadata


def parse_json(text: str) -> Any:
    text = text.strip()
    if text.startswith("\x60\x60\x60"):
        text = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", text)
        text = re.sub(r"\s*\x60\x60\x60$", "", text)
    return json.loads(text)


def response_identity(probe: Probe, observation: dict) -> str:
    """Exact identity only; absent identity on any JSON SSE event is unverified."""
    model = observation.get("response_model")
    seen = observation.get("response_model_ids")
    if seen is not None:
        if not isinstance(seen, list) or any(type(value) is not str for value in seen):
            return "invalid"
        if len(set(seen)) > 1 or (seen and model != seen[0]):
            return "conflicting"
    if observation.get("response_model_missing_events", 0):
        return "missing"
    if type(model) is not str or not model:
        return "missing"
    if model != probe.model:
        return "mismatch"
    return "matched"


def classify(probe: Probe, observation: dict, metadata: dict) -> tuple[str, str]:
    if observation.get("error"):
        return "fail", observation["error"]
    if observation.get("http_status") != 200:
        return "fail", f"http_{observation.get('http_status', 'unknown')}"
    identity = response_identity(probe, observation)
    if identity != "matched":
        return "unknown", "response_model_" + identity
    if observation.get("finish_reason") in {"length", "content_filter"}:
        return "unknown", "truncated_or_filtered_output"
    content = observation.get("_content", "")
    try:
        if probe.method in {"json_object", "json_schema", "fenced"}:
            parsed = parse_json(content) if probe.method == "fenced" else json.loads(content)
            valid = (
                type(parsed) is dict
                and set(parsed) == {"probe", "value"}
                and parsed["probe"] == "headroom"
                and type(parsed["probe"]) is str
                and type(parsed["value"]) is int
                and parsed["value"] == 7
            )
            return ("ok", "exact_json_shape") if valid else ("fail", "wrong_json")
        if probe.method == "tools":
            calls = observation.get("_tool_calls", [])
            ok = any(
                c["name"] == "add" and json.loads(c["arguments"]) == {"a": 2, "b": 3} for c in calls
            )
            return ("ok", "expected_tool_call") if ok else ("fail", "missing_or_wrong_tool")
        if probe.method == "long_context":
            return (
                ("ok", "needle_exact")
                if content.strip() == metadata["needle"]
                else ("fail", "needle_mismatch")
            )
    except (ValueError, KeyError, TypeError):
        return "fail", "invalid_structured_output"
    if probe.method in {"chat", "concurrency"}:
        return ("ok", "nonempty_content") if content.strip() else ("fail", "empty_content")
    return "unknown", "request_accepted_but_parameter_effect_requires_review"


RATE_LIMIT_COUNT_HEADERS = frozenset(
    f"x-ratelimit-{kind}-{unit}"
    for kind in ("limit", "remaining")
    for unit in ("requests", "tokens")
)
RATE_LIMIT_RESET_HEADERS = frozenset(f"x-ratelimit-reset-{unit}" for unit in ("requests", "tokens"))
RATE_LIMIT_HEADERS = (
    RATE_LIMIT_COUNT_HEADERS
    | RATE_LIMIT_RESET_HEADERS
    | {
        "x-ratelimit-over-limit",
        "retry-after",
    }
)


def sanitized_rate_limit_headers(headers: Any, *, secret: str | None = None) -> dict[str, str]:
    """Observe only bounded rate-limit response fields; never schedule retries from them.

    Duplicate names are ambiguous and omitted. Reset values are provider seconds;
    Retry-After is retained as text because HTTP also permits a date. Absence or
    rejection is unknown, never a zero limit or permission for another request.
    """
    if not isinstance(headers, Mapping):
        return {}
    multi_items = getattr(headers, "multi_items", None)
    items = multi_items() if callable(multi_items) else headers.items()
    selected = {}
    repeated = set()
    for name, value in items:
        if type(name) is not str or name.lower() not in RATE_LIMIT_HEADERS:
            continue
        name = name.lower()
        if name in selected:
            repeated.add(name)
        selected[name] = value
    result = {}
    for name, value in selected.items():
        if (
            name in repeated
            or type(value) is not str
            or not 1 <= len(value) <= 128
            or any(not 32 <= ord(char) <= 126 for char in value)
            or (secret and secret in value)
        ):
            continue
        if name in RATE_LIMIT_COUNT_HEADERS and not re.fullmatch(r"[0-9]+", value):
            continue
        if name in RATE_LIMIT_RESET_HEADERS and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
            continue
        if name == "x-ratelimit-over-limit" and value not in {"yes", "no"}:
            continue
        if name == "retry-after" and not value.strip():
            continue
        result[name] = value
    return result


class HTTPTransport:
    """Official HTTPS only; absolute deadlines, no redirects, no raw-body logging."""

    def __init__(self, key: str):
        self.key = key

    @staticmethod
    def check_endpoint(probe: Probe) -> None:
        if probe.endpoint not in ENDPOINTS:
            raise Refused("endpoint is not allowlisted")

    def catalogue(self, probe: Probe) -> dict:
        self.check_endpoint(probe)
        return asyncio.run(self._catalogue(probe))

    async def _catalogue(self, probe: Probe) -> dict:
        import httpx

        start = time.monotonic()
        http_status = None
        rate_limit_headers = {}
        try:
            async with (
                asyncio.timeout(OTHER_TIMEOUT),
                httpx.AsyncClient(
                    follow_redirects=False, timeout=OTHER_TIMEOUT, trust_env=False
                ) as client,
            ):
                response = await client.get(
                    probe.endpoint + "models",
                    params={"verbose": "true"},
                    headers={"Authorization": f"Bearer {self.key}"},
                )
                http_status = response.status_code
                rate_limit_headers = sanitized_rate_limit_headers(response.headers, secret=self.key)
                result = {
                    "http_status": http_status,
                    "rate_limit_headers": rate_limit_headers,
                    "elapsed_ms": (time.monotonic() - start) * 1000,
                }
                if response.status_code == 200:
                    document = response.json()
                    data = document.get("data") if isinstance(document, dict) else None
                    if not isinstance(data, list) or any(
                        not isinstance(item, dict)
                        or not isinstance(item.get("id"), str)
                        or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,200}", item["id"])
                        for item in data
                    ):
                        result["error"] = "malformed_catalogue_models"
                        result["models"] = []
                    else:
                        result["models"] = [
                            {
                                "id": item["id"],
                                "advertised_metadata": {
                                    k: item[k]
                                    for k in (
                                        "context_length",
                                        "max_model_len",
                                        "pricing",
                                        "price",
                                        "per_request_limits",
                                        "supported_sampling_parameters",
                                    )
                                    if k in item
                                },
                            }
                            for item in data
                        ]
                else:
                    result["error"] = f"http_{response.status_code}"
                return result
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            return {
                "http_status": http_status,
                "rate_limit_headers": rate_limit_headers,
                "error": type(exc).__name__,
                "elapsed_ms": (time.monotonic() - start) * 1000,
            }

    def chat(self, probe: Probe, payload: dict) -> dict:
        self.check_endpoint(probe)
        return asyncio.run(self._chat(probe, payload))

    async def _chat(self, probe: Probe, payload: dict) -> dict:
        import httpx

        start = time.monotonic()
        deadline = ULTRA_TIMEOUT if probe.role == "ultra" else OTHER_TIMEOUT
        result = {
            "ttft_ms": None,
            "ttft_content_ms": None,
            "usage": None,
            "_content": "",
            "_tool_calls": [],
            "response_model": None,
            "response_model_ids": [],
            "response_model_missing_events": 0,
            "rate_limit_headers": {},
        }
        calls = {}
        response_bytes = 0
        try:
            async with (
                asyncio.timeout(deadline),
                httpx.AsyncClient(
                    follow_redirects=False, timeout=deadline, trust_env=False
                ) as client,
                client.stream(
                    "POST",
                    probe.endpoint + "chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.key}"},
                ) as response,
            ):
                result["http_status"] = response.status_code
                result["rate_limit_headers"] = sanitized_rate_limit_headers(
                    response.headers, secret=self.key
                )
                if response.status_code != 200:
                    result["error"] = f"http_{response.status_code}"
                    return result
                async for line in response.aiter_lines():
                    response_bytes += len(line.encode())
                    if response_bytes > 2_000_000:
                        raise Refused("stream_size_limit")
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        break
                    event = json.loads(value)
                    event_model = event.get("model")
                    if (
                        type(event_model) is str
                        and re.fullmatch(r"[A-Za-z0-9_./:+-]{1,200}", event_model)
                        and event_model != self.key
                    ):
                        if result["response_model"] is None:
                            result["response_model"] = event_model
                        if event_model not in result["response_model_ids"]:
                            result["response_model_ids"].append(event_model)
                    else:
                        result["response_model_missing_events"] += 1
                    if event.get("error"):
                        result["error"] = "provider_stream_error"
                        break
                    if event.get("usage") is not None:
                        result["usage"] = event["usage"]
                    for choice in event.get("choices", []):
                        delta = choice.get("delta", {})
                        content = delta.get("content") or ""
                        reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                        fragments = delta.get("tool_calls") or []
                        if (content or reasoning or fragments) and result["ttft_ms"] is None:
                            result["ttft_ms"] = (time.monotonic() - start) * 1000
                        if content and result["ttft_content_ms"] is None:
                            result["ttft_content_ms"] = (time.monotonic() - start) * 1000
                        result["_content"] += content
                        result["reasoning_observed"] = result.get(
                            "reasoning_observed", False
                        ) or bool(reasoning)
                        if choice.get("finish_reason"):
                            result["finish_reason"] = choice["finish_reason"]
                        for fragment in fragments:
                            index = fragment.get("index", 0)
                            entry = calls.setdefault(index, {"name": "", "arguments": ""})
                            function = fragment.get("function", {})
                            entry["name"] += function.get("name", "")
                            entry["arguments"] += function.get("arguments", "")
                result["_tool_calls"] = list(calls.values())
                if result.get("finish_reason") is None and not result.get("error"):
                    result["error"] = "incomplete_stream"
        except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            result["error"] = type(exc).__name__
        finally:
            result["elapsed_ms"] = (time.monotonic() - start) * 1000
        return result


def sanitized_usage(usage: Any) -> dict | None:
    if not isinstance(usage, dict):
        return None
    if any(
        type(usage.get(k)) is not int or usage[k] < 0
        for k in ("prompt_tokens", "completion_tokens")
    ):
        return None
    result = {k: usage[k] for k in ("prompt_tokens", "completion_tokens")}
    for name in ("prompt_tokens_details", "completion_tokens_details"):
        if isinstance(usage.get(name), dict):
            result[name] = {
                k: v
                for k, v in usage[name].items()
                if k
                in {
                    "reasoning_tokens",
                    "cached_tokens",
                    "accepted_prediction_tokens",
                    "rejected_prediction_tokens",
                }
                and type(v) is int
                and v >= 0
            }
    return result


def probe_attempts(
    probe: Probe,
    price: Price,
    budget: Budget,
    transport,
    max_output: int,
    retries: int,
    sleep=time.sleep,
    encoder=None,
    already_reserved=False,
    catalogue=None,
) -> dict:
    upper = price.cost(price.prompt_token_ceiling, max_output)
    reserved = upper * (retries + 1)
    if catalogue is None:
        # Independent callers must pass the same live guard; the normal plan
        # supplies its just-fetched endpoint record so it performs only two GETs.
        try:
            observed = transport.catalogue(
                Probe("catalogue-for-" + probe.id, probe.endpoint, None, "catalogue")
            )
            catalogue = {**observed, "endpoint": probe.endpoint}
        except Exception as error:  # noqa: BLE001 - no provider exception text is persisted
            catalogue = {
                "endpoint": probe.endpoint,
                "error": "catalogue_exception_" + type(error).__name__,
            }
    guard = catalogue_guard(probe, price, catalogue)
    if guard["status"] != "matched":
        if already_reserved:
            budget.settle(reserved, Decimal(0), Decimal(0))
        return {
            "id": probe.id,
            "status": "refused",
            "detail": guard["detail"],
            "attempts": [],
            "catalogue_guard": guard,
        }
    if not already_reserved:
        budget.reserve(reserved)
    charged = Decimal(0)
    known = Decimal(0)
    attempts = []
    try:
        payload, metadata = make_payload(probe, price, max_output, encoder)
        public_metadata = {k: v for k, v in metadata.items() if k != "needle"}
        for attempt in range(retries + 1):
            # This is the dispatch decision. Already-dispatched peer requests may finish,
            # but no new attempt/retry is admitted after a shared ceiling violation.
            with budget.lock:
                if budget.violated or budget.halt_reason:
                    return {
                        "id": probe.id,
                        "catalogue_guard": guard,
                        "status": "refused",
                        "detail": budget.halt_reason or "shared_provider_bound_violation",
                        "attempts": attempts,
                    }
            charged += upper  # Retain uncertainty even if the transport raises unexpectedly.
            observation = transport.chat(probe, payload)
            usage = sanitized_usage(observation.get("usage"))
            identity = response_identity(probe, observation)
            identity_unresolved = identity != "matched" and (
                observation.get("http_status") == 200 or usage is not None
            )
            if identity_unresolved:
                with budget.lock:
                    budget.billing_bound_unresolved = True
                    budget.halt_reason = "response_model_identity_unverified"
            actual = (
                None
                if usage is None or identity != "matched"
                else price.cost(usage["prompt_tokens"], usage["completion_tokens"])
            )
            if actual is not None:
                charged += actual - upper
            known += Decimal(0) if actual is None else actual
            status, detail = classify(probe, observation, metadata)
            over_bound = (
                identity == "matched"
                and usage is not None
                and (
                    usage["prompt_tokens"] > price.prompt_token_ceiling
                    or usage["completion_tokens"] > max_output
                )
            )
            if over_bound:
                status, detail = "fail", "provider_exceeded_verified_token_bound"
                with budget.lock:
                    budget.violated = True
            row = {
                "attempt": attempt + 1,
                "status": status,
                "detail": detail,
                "http_status": observation.get("http_status"),
                "rate_limit_headers": sanitized_rate_limit_headers(
                    observation.get("rate_limit_headers")
                ),
                "usage": usage,
                "requested_model": probe.model,
                "response_model": observation.get("response_model"),
                "response_model_ids": observation.get("response_model_ids"),
                "response_model_missing_events": observation.get(
                    "response_model_missing_events", 0
                ),
                "model_identity": identity,
                "billing_bound_verified_for_response": identity == "matched",
                "actual_cost_usd": None if actual is None else str(actual),
                "retained_cost_usd": str(upper if actual is None else actual),
                "cost_status": (
                    "unknown_model_identity_requested_reservation_retained"
                    if identity_unresolved
                    else "unknown_reserved_upper_bound"
                    if actual is None
                    else "usage_based"
                ),
                "ttft_ms": observation.get("ttft_ms"),
                "ttft_content_ms": observation.get("ttft_content_ms"),
                "elapsed_ms": observation.get("elapsed_ms"),
                "finish_reason": observation.get("finish_reason"),
                "reasoning_observed": observation.get("reasoning_observed", False),
            }
            attempts.append(row)
            retryable = observation.get("http_status") == 429 or observation.get(
                "http_status", 0
            ) in range(500, 600)
            if identity_unresolved or over_bound or not retryable or attempt == retries:
                break
            sleep(2**attempt)
        return {
            "id": probe.id,
            "catalogue_guard": guard,
            "model": probe.model,
            "requested_model": probe.model,
            "response_model": attempts[-1]["response_model"],
            "model_identity": attempts[-1]["model_identity"],
            "endpoint": probe.endpoint,
            "method": probe.method,
            "status": attempts[-1]["status"],
            "detail": attempts[-1]["detail"],
            "reservation_usd": str(reserved),
            "per_attempt_upper_usd": str(upper),
            "attempts": attempts,
            **public_metadata,
        }
    except Refused as exc:
        return {
            "id": probe.id,
            "status": "refused",
            "detail": str(exc),
            "attempts": attempts,
            "catalogue_guard": guard,
        }
    except Exception as exc:  # noqa: BLE001 - preserve charged reservation and redact exception text.
        return {
            "id": probe.id,
            "catalogue_guard": guard,
            "status": "fail",
            "detail": "probe_exception_" + type(exc).__name__,
            "attempts": attempts,
        }
    finally:
        budget.settle(reserved, charged, known)


def execute_catalogue_plan(plan: list[Probe], transport, on_result=None) -> dict:
    """Only two allowlisted GETs; no price assumptions, inference or budget object."""
    if (
        len(plan) != len(ENDPOINTS)
        or {p.endpoint for p in plan} != set(ENDPOINTS)
        or any(p.method != "catalogue" or p.role is not None for p in plan)
    ):
        raise Refused("catalogue-only execution requires exactly the two official GET plans")
    report = {
        "schema_version": 1,
        "mode": "catalogue_only",
        "accepted": False,
        "live": True,
        "status": "running",
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "inference_requests": 0,
        "catalogues": [],
        "note": "Authenticated directory availability only; not model inference, capability, pricing or billing verification.",
    }
    for spec in plan:
        observed = transport.catalogue(spec)
        models = observed.get("models")
        valid = (
            observed.get("http_status") == 200
            and not observed.get("error")
            and isinstance(models, list)
            and bool(models)
            and all(
                isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
                for row in models
            )
        )
        report["catalogues"].append(
            {
                "id": spec.id,
                "endpoint": spec.endpoint,
                **observed,
                "catalogue_available": bool(valid),
                "status": "ok" if valid else "failed",
            }
        )
        if on_result:
            on_result(report)
    report["status"] = (
        "complete" if all(row["catalogue_available"] for row in report["catalogues"]) else "failed"
    )
    if on_result:
        on_result(report)
    return report


def execute_plan(
    plan: list[Probe],
    prices: dict[str, Price],
    budget: Budget,
    transport,
    max_output: int,
    retries: int,
    on_result=None,
) -> dict:
    report = {
        "schema_version": 1,
        "accepted": False,
        "live": True,
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "catalogues": [],
        "catalogue_guards": [],
        "catalogue_consistency_passed": None,
        "selected_models": {p.role: p.model for p in plan if p.role},
        "probes": [],
        "config_proposal": {},
        "acceptance_pending": [
            "Frank review of live capabilities and token ceilings",
            "At least five actual FEEDBACK entries reviewed",
            "Root-reviewed configuration update and T0.4 acceptance",
        ],
    }
    catalogues = {}
    for probe in [p for p in plan if p.method == "catalogue"]:
        observation = transport.catalogue(probe)
        row = {**observation, "id": probe.id, "endpoint": probe.endpoint}
        report["catalogues"].append(row)
        catalogues[probe.endpoint] = row

        if on_result:
            on_result(report)
    paid = [p for p in plan if p.method != "catalogue"]
    sequential = [p for p in paid if p.concurrency_group is None]
    groups = (
        [[p for p in paid if p.concurrency_group]] if any(p.concurrency_group for p in paid) else []
    )
    for group in [[p] for p in sequential] + groups:
        guards = [catalogue_guard(p, prices.get(p.role), catalogues.get(p.endpoint)) for p in group]
        report["catalogue_guards"].extend(
            {"id": p.id, **guard} for p, guard in zip(group, guards, strict=True)
        )
        report["catalogue_consistency_passed"] = all(
            guard["status"] == "matched" for guard in report["catalogue_guards"]
        )
        if on_result:
            on_result(report)  # Consistency evidence is durable before any paid reservation.
        if any(guard["status"] != "matched" for guard in guards):
            report["probes"].extend(
                {
                    "id": p.id,
                    "role": p.role,
                    "model": p.model,
                    "endpoint": p.endpoint,
                    "status": "refused",
                    "detail": guard["detail"]
                    if guard["status"] != "matched"
                    else "catalogue_group_refused",
                }
                for p, guard in zip(group, guards, strict=True)
            )
            continue
        if len(group) == 1:
            p = group[0]
            try:
                row = probe_attempts(
                    p,
                    prices[p.role],
                    budget,
                    transport,
                    max_output,
                    retries,
                    catalogue=catalogues[p.endpoint],
                )
            except Refused as exc:
                row = {"id": p.id, "status": "refused", "detail": str(exc)}
            report["probes"].append(row)
        else:
            reservations = [
                prices[p.role].cost(prices[p.role].prompt_token_ceiling, max_output) * (retries + 1)
                for p in group
            ]
            try:
                budget.reserve(sum(reservations))
            except Refused as exc:
                report["probes"].extend(
                    {"id": p.id, "status": "refused", "detail": str(exc)} for p in group
                )
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [
                        pool.submit(
                            probe_attempts,
                            p,
                            prices[p.role],
                            budget,
                            transport,
                            max_output,
                            retries,
                            already_reserved=True,
                            catalogue=catalogues[p.endpoint],
                        )
                        for p in group
                    ]
                    report["probes"].extend(f.result() for f in futures)
        report["budget"] = budget.summary()
        if on_result:
            on_result(report)
    successes = [
        p for p in report["probes"] if p.get("method") == "long_context" and p.get("status") == "ok"
    ]
    report["config_proposal"] = {
        "applied": False,
        "largest_successful_cl100k_approximation": max(
            (p["measured_cl100k_tokens"] for p in successes), default=None
        ),
        "largest_successful_server_prompt_tokens": max(
            (a["usage"]["prompt_tokens"] for p in successes for a in p["attempts"] if a["usage"]),
            default=None,
        ),
        "interpretation": "verified staircase lower bound, not an exact maximum context limit",
        "evidence_token_budget": None,
        "reason": "manual installed-config and five-feedback review required",
    }
    report["budget"] = budget.summary()
    if on_result:
        on_result(report)
    return report


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--allow-paid-requests", action="store_true")
    p.add_argument("--credit-confirmed", action="store_true")
    p.add_argument("--available-credit-usd")
    p.add_argument("--budget-usd")
    p.add_argument("--pricing-file", type=Path)
    p.add_argument(
        "--suite",
        action="append",
        choices=["all", "catalogue", "capabilities", "long", "concurrency"],
    )
    p.add_argument("--roles", nargs="+", choices=list(MODELS))
    p.add_argument(
        "--model-id",
        action="append",
        metavar="ROLE=EXACT_ID",
        help="Explicit case-sensitive candidate override; still requires live endpoint catalogue and matching reviewed pricing",
    )
    p.add_argument(
        "--capability-method",
        action="append",
        choices=METHODS,
        help="Limit capability rows only; repeat for distinct methods (default: all thirteen)",
    )
    p.add_argument("--base-url", choices=ENDPOINTS, default=ENDPOINTS[0])
    p.add_argument("--long-input-tokens", action="append", type=int, choices=LONG_SIZES)
    p.add_argument("--max-retries", type=int, choices=range(6), default=0)
    p.add_argument("--max-completion-tokens", type=int, default=256)
    p.add_argument("--output-dir", type=Path)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        model_ids = parse_model_overrides(args.model_id)
        plan = build_plan(
            args.suite,
            args.roles,
            args.base_url,
            args.long_input_tokens,
            model_ids=model_ids,
            capability_methods=args.capability_method,
        )
    except Refused as exc:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "status": "refused",
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
            )
        )
        return 2
    if not args.execute:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "live": False,
                    "network_requests": 0,
                    "model_overrides": model_ids,
                    "plan": [dataclasses.asdict(p) | {"model": p.model} for p in plan],
                    "notes": [
                        "No key, pricing file or tokenizer loaded in dry-run.",
                        "Candidate model IDs are unverified until live catalogue checks.",
                        "cl100k lengths are approximations, not exact model tokenizer lengths.",
                        "Capability parameter acceptance alone cannot verify reasoning/budget effects.",
                    ],
                },
                indent=2,
            )
        )
        return 0
    try:
        catalogue_only = bool(plan) and all(p.method == "catalogue" for p in plan)
        if not catalogue_only:
            if not args.allow_paid_requests or not args.credit_confirmed:
                raise Refused("execute requires explicit paid-request and credit confirmations")
            require_standalone_paid_dispatch()
            if not args.budget_usd or not args.available_credit_usd or args.pricing_file is None:
                raise Refused("execute requires budget, available credit and verified pricing file")
            cap = money(args.budget_usd)
            if cap <= 0 or money(args.available_credit_usd) < cap:
                raise Refused("available confirmed credit must cover the positive money cap")
            if not 1 <= args.max_completion_tokens <= 16384:
                raise Refused("completion cap must be 1..16384 and include reasoning")
            roles = {p.role for p in plan if p.role}
            prices = validate_prices(json.loads(args.pricing_file.read_text()), roles, model_ids)
        key = os.environ.get("NEBIUS_API_KEY")
        if not key:
            raise Refused("NEBIUS_API_KEY is missing; .env is never loaded by this script")
        output = args.output_dir or Path("runs/model-probes") / (
            dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
        )
        output.mkdir(parents=True, exist_ok=False)

        def save(value):
            path = output / "report.json"
            temp = output / "report.json.tmp"
            temp.write_text(json.dumps(value, indent=2) + "\n")
            temp.replace(path)

        if catalogue_only:
            report = execute_catalogue_plan(plan, HTTPTransport(key), save)
            print(
                json.dumps(
                    {
                        "accepted": False,
                        "mode": "catalogue_only",
                        "status": report["status"],
                        "inference_requests": 0,
                        "report": str(output / "report.json"),
                        "catalogues": [
                            {
                                "endpoint": row["endpoint"],
                                "http_status": row.get("http_status"),
                                "status": row["status"],
                            }
                            for row in report["catalogues"]
                        ],
                    },
                    indent=2,
                )
            )
            return 0 if report["status"] == "complete" else 2

        report = execute_plan(
            plan,
            prices,
            Budget(cap),
            HTTPTransport(key),
            args.max_completion_tokens,
            args.max_retries,
            save,
        )
        print(
            json.dumps(
                {
                    "accepted": False,
                    "report": str(output / "report.json"),
                    "budget": report["budget"],
                    "note": "Live observations require manual acceptance; no config or feedback was modified.",
                },
                indent=2,
            )
        )
        return (
            0
            if not (
                report["budget"]["provider_bound_violation"]
                or report["budget"]["billing_bound_unresolved"]
                or report["catalogue_consistency_passed"] is False
            )
            else 2
        )
    except (Refused, OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "accepted": False,
                    "status": "refused",
                    "error": type(exc).__name__,
                    "detail": str(exc)
                    if isinstance(exc, Refused)
                    else "invalid or unavailable local prerequisite",
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
