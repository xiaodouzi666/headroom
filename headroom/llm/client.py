"""Explicitly enabled, endpoint-scoped Token Factory requests through OpenAI SDK."""

import copy
import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import openai

from headroom.config import SUPER_MODEL, RuntimeConfig
from headroom.llm.cost import CallRecord, Cost, CostLedger, Usage, calculate_cost
from headroom.llm.request_audit import capture_request

RETRY_DELAYS = (1, 2, 4, 8, 16)
DEFAULT_HTTP_RETRIES = len(RETRY_DELAYS)


class LLMError(RuntimeError):
    """Safe error summary: never includes SDK response bodies or credentials."""


class LiveRequestsDisabled(LLMError):
    pass


class CapabilityNotVerified(LLMError):
    pass


@dataclass(frozen=True)
class ClientResponse:
    role: str
    model: str
    response_model: str | None
    text: str
    tool_calls: tuple[dict[str, Any], ...]
    usage: Usage | None
    cost: Cost
    attempts: int
    elapsed_seconds: float
    finish_reason: str | None


def low_effort_probe_fingerprint(body):
    """Bind a reviewed candidate request without granting a production capability.

    Hash the canonical wire fields; SDK-only timeout is excluded. The actual
    serialized wire payload is still captured by the existing runtime hook.
    """
    value = copy.deepcopy(dict(body))
    value.pop("timeout", None)
    extra = value.pop("extra_body", {})
    if type(extra) is not dict or set(extra) & set(value):
        raise ValueError("Probe request has ambiguous extra-body fields")
    value.update(extra)
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TokenFactoryClient:
    """No environment credentials are read and construction never sends a request.

    The only injectable transport is httpx.MockTransport for offline tests. Live
    traffic requires RuntimeConfig(live_enabled=True) and an explicit API key.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        config: RuntimeConfig | None = None,
        transport: httpx.MockTransport | None = None,
        ledger: CostLedger | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        before_attempt: Callable | None = None,
        after_record: Callable | None = None,
        on_request: Callable | None = None,
        max_http_retries: int = DEFAULT_HTTP_RETRIES,
        low_effort_probe_request_sha256: str | None = None,
    ):
        if type(max_http_retries) is not int or not 0 <= max_http_retries <= len(RETRY_DELAYS):
            raise ValueError("HTTP retries must be an integer within the existing retry bound")
        if low_effort_probe_request_sha256 is not None:
            digest = low_effort_probe_request_sha256
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)
                or max_http_retries != 0
            ):
                raise ValueError(
                    "Candidate capability probes require one request and a frozen SHA256"
                )
        self._retry_delays = RETRY_DELAYS[:max_http_retries]
        self._low_effort_probe_sha256 = low_effort_probe_request_sha256
        self._low_effort_probe_consumed = False
        self.config = config or RuntimeConfig()
        if transport is not None and not isinstance(transport, httpx.MockTransport):
            raise ValueError("Only an offline MockTransport may be injected")
        if api_key is not None and (
            not isinstance(api_key, str) or not api_key or any(c.isspace() for c in api_key)
        ):
            raise ValueError("API key must be a nonempty string without whitespace")
        self._api_key = api_key
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self.ledger = ledger if ledger is not None else CostLedger()
        self._before_attempt = before_attempt
        self._after_record = after_record
        self._on_request = on_request
        self._request_context = None
        self._sdk = None

    def _record(self, record):
        self.ledger.add(record)
        if self._after_record is not None:
            self._after_record(record)

    def _get_sdk(self):
        if self._sdk is not None:
            return self._sdk
        if self._transport is None and not self.config.live_enabled:
            raise LiveRequestsDisabled("Live model requests are disabled")
        if self._transport is None and not self._api_key:
            raise LiveRequestsDisabled("Live requests require an explicitly supplied API key")
        key = self._api_key or "headroom-offline-test-key"
        endpoint = self.config.base_url + "chat/completions"

        def guard_request(request):
            if str(request.url) != endpoint or request.method != "POST":
                raise LLMError("Request rejected outside the configured Token Factory endpoint")
            # Discard SDK ambient headers, cookies and unrelated credentials. Explicit
            # headers also override OPENAI_CUSTOM_HEADERS Authorization in the SDK.
            request.headers.clear()
            request.headers.update(
                {
                    "Authorization": "Bearer " + key,
                    "Host": request.url.netloc.decode("ascii"),
                    "Content-Length": str(len(request.content)),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Headroom/0.1",
                }
            )
            if self._on_request is not None:
                if self._request_context is None:
                    raise LLMError("Request has no admitted attempt context")
                role, model, attempt = self._request_context
                self._on_request(
                    role, model, attempt, capture_request(request.content, secret_values=(key,))
                )

        http_client = httpx.Client(
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
            event_hooks={"request": [guard_request]},
        )
        self._sdk = openai.OpenAI(
            api_key=key,
            admin_api_key="",
            organization="",
            project="",
            webhook_secret="",
            base_url=self.config.base_url,
            max_retries=0,
            http_client=http_client,
            default_headers={"Authorization": "Bearer " + key},
        )
        return self._sdk

    def close(self):
        if self._sdk is not None:
            self._sdk.close()
            self._sdk = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def complete(
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        schema: Mapping[str, Any] | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        reasoning: bool | None = None,
        low_effort: bool = False,
        token_budget: int | None = None,
        max_tokens: int = 4000,
        temperature: float | None = None,
    ) -> ClientResponse:
        spec = self.config.model_for(role)
        caps = spec.capabilities
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if reasoning is not None and type(reasoning) is not bool:
            raise ValueError("reasoning must be a boolean or None")
        if type(low_effort) is not bool:
            raise ValueError("low_effort must be a boolean")
        if low_effort:
            if reasoning is not True or caps.reasoning_method != "chat_template_kwargs":
                raise CapabilityNotVerified("Low-effort requires explicit template thinking")
            if (
                caps.low_effort_method != "chat_template_kwargs"
                and self._low_effort_probe_sha256 is None
            ):
                raise CapabilityNotVerified(
                    "Low-effort request combination has no saved probe evidence"
                )
        if self._low_effort_probe_sha256 is not None and (
            self._low_effort_probe_consumed
            or role != "patcher"
            or spec.model_id != SUPER_MODEL
            or reasoning is not True
            or low_effort is not True
            or max_tokens != 4000
            or token_budget is not None
            or tools
            or schema is None
            or caps.json_method != "json_schema"
            or spec.output_cap_field != "max_completion_tokens"
        ):
            raise CapabilityNotVerified(
                "Candidate probe request is outside its one-shot frozen scope"
            )
        if token_budget is not None and (type(token_budget) is not int or token_budget <= 0):
            raise ValueError("token_budget must be a positive integer")
        if not messages or isinstance(messages, (str, bytes)):
            raise ValueError("messages must be a nonempty sequence of message dictionaries")
        if not all(isinstance(message, Mapping) and "role" in message for message in messages):
            raise ValueError("Each message must contain a role")
        body = {
            "model": spec.model_id,
            "messages": copy.deepcopy(list(messages)),
            spec.output_cap_field: max_tokens,
            "timeout": spec.timeout_seconds,
        }
        if temperature is not None:
            body["temperature"] = temperature
        extra = {}
        if reasoning is not None:
            if caps.reasoning_method is None:
                raise CapabilityNotVerified("Reasoning toggle has no successful probe evidence")
            if caps.reasoning_method == "chat_template_kwargs":
                extra["chat_template_kwargs"] = {"enable_thinking": reasoning}
                if low_effort:
                    extra["chat_template_kwargs"]["low_effort"] = True
            elif caps.reasoning_method == "reasoning_effort":
                extra["reasoning_effort"] = caps.reasoning_on if reasoning else caps.reasoning_off
            elif caps.reasoning_method == "system_prefix":
                prefix = "/think" if reasoning else "/no_think"
                if body["messages"][0].get("role") == "system":
                    content = body["messages"][0].get("content", "")
                    if not isinstance(content, str):
                        raise ValueError("System-prefix reasoning requires text system content")
                    body["messages"][0]["content"] = prefix + "\n" + content
                else:
                    body["messages"].insert(0, {"role": "system", "content": prefix})
        if token_budget is not None:
            if caps.token_budget_method is None:
                raise CapabilityNotVerified("Token-budget method has no successful probe evidence")
            extra[caps.token_budget_method] = token_budget
        if tools:
            if not caps.tools:
                raise CapabilityNotVerified("Tool calling has no successful probe evidence")
            body["tools"] = copy.deepcopy(list(tools))
        if schema is not None:
            if caps.json_method == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "headroom_response", "schema": copy.deepcopy(schema)},
                }
            elif caps.json_method == "json_object":
                body["response_format"] = {"type": "json_object"}
            # Text fallback is local parsing, not a claimed provider capability.
        if extra:
            body["extra_body"] = extra
        if self._low_effort_probe_sha256 is not None:
            if low_effort_probe_fingerprint(body) != self._low_effort_probe_sha256:
                raise CapabilityNotVerified("Candidate probe differs from its frozen request")
            # Consumed before admission: even a local failure cannot dispatch a second call.
            self._low_effort_probe_consumed = True
        sdk = self._get_sdk()
        started = self._clock()
        for attempt in range(1, len(self._retry_delays) + 2):
            if self._before_attempt is not None:
                self._before_attempt(role, spec, attempt, copy.deepcopy(body))
            attempt_started = self._clock()
            self._request_context = (role, spec.model_id, attempt)
            try:
                completion = sdk.chat.completions.create(**body)
            except openai.APIStatusError as error:
                status = error.status_code
                self._record(
                    CallRecord(
                        role,
                        spec.model_id,
                        attempt,
                        "http_error",
                        self._clock() - attempt_started,
                        None,
                        calculate_cost(None, spec.pricing),
                        status,
                    )
                )
                if (status == 429 or 500 <= status <= 599) and attempt <= len(self._retry_delays):
                    self._sleep(self._retry_delays[attempt - 1])
                    continue
                raise LLMError(f"Token Factory HTTP {status}; attempts={attempt}") from None
            except (openai.OpenAIError, httpx.HTTPError) as error:
                outcome = (
                    "timeout" if isinstance(error, openai.APITimeoutError) else "transport_error"
                )
                self._record(
                    CallRecord(
                        role,
                        spec.model_id,
                        attempt,
                        outcome,
                        self._clock() - attempt_started,
                        None,
                        calculate_cost(None, spec.pricing),
                    )
                )
                raise LLMError(f"Token Factory {outcome}; attempts={attempt}") from None
            except Exception:  # noqa: BLE001 - every SDK attempt must retain unknown billing on failure.
                # Any exception after invoking the SDK leaves billing uncertain. Do
                # not let an unrecognized decoder failure make an attempt look free.
                self._record(
                    CallRecord(
                        role,
                        spec.model_id,
                        attempt,
                        "response_error",
                        self._clock() - attempt_started,
                        None,
                        calculate_cost(None, spec.pricing),
                    )
                )
                raise LLMError(f"Token Factory response error; attempts={attempt}") from None
            except BaseException:
                # Interrupts can arrive after transmission. Preserve the attempt
                # before allowing the caller to write a partial report and stop.
                self._record(
                    CallRecord(
                        role,
                        spec.model_id,
                        attempt,
                        "interrupted",
                        self._clock() - attempt_started,
                        None,
                        calculate_cost(None, spec.pricing),
                    )
                )
                raise
            usage_payload = getattr(completion, "usage", None)
            raw_usage = (
                usage_payload.model_dump(warnings=False)
                if isinstance(usage_payload, openai.types.CompletionUsage)
                else None
            )
            usage = Usage.from_payload(raw_usage)
            response_model = getattr(completion, "model", None)
            if not isinstance(response_model, str):
                response_model = None
            cost = calculate_cost(usage, spec.pricing)
            if response_model != spec.model_id:
                cost = Cost(None, "unknown", "response_model_mismatch")
            self._record(
                CallRecord(
                    role,
                    spec.model_id,
                    attempt,
                    "response",
                    self._clock() - attempt_started,
                    usage,
                    cost,
                    200,
                    response_model,
                )
            )
            if response_model != spec.model_id:
                raise LLMError("Token Factory response model identity is missing or mismatched")
            if not getattr(completion, "choices", None):
                raise LLMError("Token Factory returned no completion choices")
            choice = completion.choices[0]
            message = choice.message
            if message is None:
                raise LLMError("Token Factory returned no assistant message")
            if getattr(message, "refusal", None):
                raise LLMError("Token Factory returned a refusal")
            return ClientResponse(
                role=role,
                model=spec.model_id,
                response_model=response_model,
                text=message.content or "",
                tool_calls=tuple(
                    call.model_dump(warnings=False) for call in (message.tool_calls or [])
                ),
                usage=usage,
                cost=cost,
                attempts=attempt,
                elapsed_seconds=self._clock() - started,
                finish_reason=choice.finish_reason,
            )
        raise AssertionError("Retry loop must return or raise")
