"""Offline integration tests through the real SDK and an HTTP MockTransport."""

import json
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest

from headroom.config import (
    NANO_MODEL,
    SUPER_MODEL,
    ULTRA_MODEL,
    RuntimeConfig,
    VerifiedCapabilities,
    candidate_models,
    normalize_base_url,
)
from headroom.llm.client import (
    CapabilityNotVerified,
    LiveRequestsDisabled,
    LLMError,
    TokenFactoryClient,
)
from headroom.llm.cost import Pricing

MESSAGES = [{"role": "user", "content": "Return an answer"}]


def completion(content="ok", *, usage=True, finish="stop", tool_calls=None, model=SUPER_MODEL):
    result = {
        "id": "mock-completion",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {"role": "assistant", "content": content},
            }
        ],
    }
    if usage:
        result["usage"] = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    if tool_calls:
        result["choices"][0]["message"]["tool_calls"] = tool_calls
    return result


def priced_config(**kwargs):
    models = candidate_models()
    models["super"] = replace(
        models["super"],
        pricing=Pricing("0.30", "0.90", verified=True, source="offline fixture, not live pricing"),
    )
    return RuntimeConfig(models=models, **kwargs)


@pytest.mark.parametrize(
    "role,model,timeout",
    [
        ("diagnose", ULTRA_MODEL, 600),
        ("planner", ULTRA_MODEL, 600),
        ("patch", SUPER_MODEL, 120),
        ("verifier", SUPER_MODEL, 120),
        ("annotate", NANO_MODEL, 120),
        ("summarizer", NANO_MODEL, 120),
    ],
)
def test_roles_and_timeouts(role, model, timeout):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=completion(model=json.loads(request.content)["model"]))

    with TokenFactoryClient(transport=httpx.MockTransport(respond)) as client:
        result = client.complete(role, MESSAGES)
    assert json.loads(seen[0].content)["model"] == model
    assert seen[0].extensions["timeout"]["read"] == timeout
    assert result.model == model
    assert result.cost.status == "unknown"


def test_default_cannot_send_or_read_ambient_credentials(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "should-not-be-loaded")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-loaded")
    client = TokenFactoryClient()
    with pytest.raises(LiveRequestsDisabled):
        client.complete("patch", MESSAGES)
    assert not client.ledger.entries
    with pytest.raises(LiveRequestsDisabled):
        TokenFactoryClient(config=RuntimeConfig(live_enabled=True)).complete("patch", MESSAGES)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.tokenfactory.nebius.com/v1",
        "https://api.tokenfactory.nebius.com:443/v1",
        "https://api.tokenfactory.nebius.com.evil/v1",
        "https://api.tokenfactory.nebius.com/v1/?x=1",
        "https://key@api.tokenfactory.nebius.com/v1",
        "https://api.tokenfactory.nebius.com/v1/../x",
    ],
)
def test_rejects_nonofficial_base_urls(url):
    with pytest.raises(ValueError):
        normalize_base_url(url)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_exact_retry_schedule_and_no_sdk_nested_retries(status):
    requests, sleeps = [], []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "private-error-body"}})

    with (
        TokenFactoryClient(
            transport=httpx.MockTransport(respond),
            sleep=sleeps.append,
        ) as client,
        pytest.raises(LLMError, match=f"HTTP {status}; attempts=6") as error,
    ):
        client.complete("patch", MESSAGES)
    assert len(requests) == 6
    assert sleeps == [1, 2, 4, 8, 16]
    assert len(client.ledger.entries) == 6
    assert client.ledger.total_usd is None
    assert "private-error-body" not in str(error.value)


def test_success_after_retry_retains_unknown_failed_attempt_cost():
    responses = [
        httpx.Response(429, json={"error": "rate limit"}),
        httpx.Response(200, json=completion()),
    ]
    with TokenFactoryClient(
        config=priced_config(),
        transport=httpx.MockTransport(lambda _: responses.pop(0)),
        sleep=lambda _: None,
    ) as client:
        result = client.complete("patch", MESSAGES)
    assert result.attempts == 2
    assert result.cost.usd == Decimal("0.000048")
    assert client.ledger.known_subtotal_usd == result.cost.usd
    assert client.ledger.total_usd is None
    assert client.ledger.unknown_attempts == 1


@pytest.mark.parametrize("status", [400, 401, 403, 408, 409, 422])
def test_nonretryable_errors_are_sanitized(status):
    seen = []
    key = "secret-never-log"

    def respond(request):
        seen.append(request)
        return httpx.Response(status, json={"error": {"message": key}})

    with (
        TokenFactoryClient(key, transport=httpx.MockTransport(respond)) as client,
        pytest.raises(LLMError) as error,
    ):
        client.complete("patch", MESSAGES)
    assert len(seen) == 1
    assert key not in str(error.value)


def test_timeouts_are_not_retried_and_do_not_expose_request():
    seen = []

    def respond(request):
        seen.append(request)
        raise httpx.ReadTimeout("secret-never-log", request=request)

    with (
        TokenFactoryClient(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(LLMError, match="timeout") as error,
    ):
        client.complete("patch", MESSAGES)
    assert len(seen) == 1
    assert "secret-never-log" not in str(error.value)
    assert client.ledger.unknown_attempts == 1


def test_redirect_never_sends_credentials_to_destination(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:1")
    monkeypatch.setenv(
        "OPENAI_CUSTOM_HEADERS", "X-Private: ambient-secret\nAuthorization: stale-key"
    )
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(307, headers={"Location": "https://attacker.invalid/steal"})

    with TokenFactoryClient("only-current-key", transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(LLMError):
            client.complete("patch", MESSAGES)
        assert client._sdk.max_retries == 0
        assert client._sdk._client._trust_env is False
        assert client._sdk._client.follow_redirects is False
    assert len(requests) == 1
    assert requests[0].headers["Authorization"] == "Bearer only-current-key"
    assert "X-Private" not in requests[0].headers
    assert requests[0].headers["Host"] == "api.tokenfactory.us-central1.nebius.com"
    assert int(requests[0].headers["Content-Length"]) == len(requests[0].content)
    assert requests[0].url.host == "api.tokenfactory.us-central1.nebius.com"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reasoning": True},
        {"token_budget": 200},
        {"tools": [{"type": "function"}]},
    ],
)
def test_unverified_capability_sends_no_request(kwargs):
    seen = []
    with (
        TokenFactoryClient(
            transport=httpx.MockTransport(lambda request: seen.append(request))
        ) as client,
        pytest.raises(CapabilityNotVerified),
    ):
        client.complete("patch", MESSAGES, **kwargs)
    assert not seen


@pytest.mark.parametrize("method", ["chat_template_kwargs", "system_prefix", "reasoning_effort"])
def test_reasoning_and_budget_only_use_configured_methods(method):
    requests = []
    caps = VerifiedCapabilities(
        reasoning_method=method,
        token_budget_method="max_thinking_tokens",
        reasoning_on="high",
        reasoning_off="none",
        evidence="offline fixture",
    )
    models = candidate_models()
    models["ultra"] = replace(models["ultra"], capabilities=caps)

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=completion(model=json.loads(request.content)["model"]))

    messages = [{"role": "system", "content": "original"}, *MESSAGES]
    with TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(respond)
    ) as client:
        client.complete("diagnose", messages, reasoning=False, token_budget=512)
    body = requests[0]
    assert body["max_thinking_tokens"] == 512
    if method == "system_prefix":
        assert body["messages"][0]["content"] == "/no_think\noriginal"
    elif method == "reasoning_effort":
        assert body["reasoning_effort"] == "none"
    else:
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert messages[0]["content"] == "original"


def test_missing_usage_is_unknown_not_free():
    with TokenFactoryClient(
        config=priced_config(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion(usage=False))),
    ) as client:
        result = client.complete("patch", MESSAGES)
    assert result.usage is None
    assert result.cost.usd is None
    assert client.ledger.total_usd is None


@pytest.mark.parametrize("reported", ["nvidia/different-model", None, "", 123])
def test_wrong_or_missing_model_is_rejected_after_unknown_cost_is_recorded(reported):
    body = completion()
    if reported is None:
        body.pop("model")
    else:
        body["model"] = reported
    with (
        TokenFactoryClient(
            config=priced_config(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
        ) as client,
        pytest.raises(LLMError, match="model identity"),
    ):
        client.complete("patch", MESSAGES)
    assert len(client.ledger.entries) == 1
    entry = client.ledger.entries[0]
    assert entry.usage is not None
    assert entry.cost.reason == "response_model_mismatch"
    assert client.ledger.total_usd is None


def test_tool_call_response_is_preserved_without_executing_tools():
    models = candidate_models()
    models["super"] = replace(
        models["super"], capabilities=VerifiedCapabilities(tools=True, evidence="offline fixture")
    )
    tool_calls = [
        {"id": "call_test", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}
    ]
    with TokenFactoryClient(
        config=RuntimeConfig(models=models),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json=completion(content=None, finish="tool_calls", tool_calls=tool_calls)
            )
        ),
    ) as client:
        result = client.complete(
            "patch",
            MESSAGES,
            tools=[
                {
                    "type": "function",
                    "function": {"name": "lookup", "parameters": {"type": "object"}},
                }
            ],
        )
    assert result.tool_calls[0]["function"]["name"] == "lookup"
    assert result.text == ""


@pytest.mark.parametrize("bad_usage", ["unexpected", {"prompt_tokens": "wrong"}, None])
def test_malformed_provider_usage_is_accounted_as_unknown(bad_usage):
    body = completion()
    body["usage"] = bad_usage
    with TokenFactoryClient(
        config=priced_config(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    ) as client:
        result = client.complete("patch", MESSAGES)
    assert result.usage is None
    assert result.cost.status == "unknown"
    assert client.ledger.unknown_attempts == 1


def test_sdk_debug_logs_do_not_expose_credentials_or_error_bodies(caplog):
    import logging

    secret = "sensitive-key-for-log-test"
    caplog.set_level(logging.DEBUG)
    with (
        TokenFactoryClient(
            secret,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(401, json={"error": {"message": secret}})
            ),
        ) as client,
        pytest.raises(LLMError),
    ):
        client.complete("patch", MESSAGES)
    assert secret not in caplog.text


@pytest.mark.parametrize("payload", ["not-json", '{"secret":"sensitive-value",bad}'])
def test_invalid_success_body_has_unknown_cost_and_no_automatic_retry(payload, caplog):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers={"Content-Type": "application/json"}, text=payload)

    with (
        TokenFactoryClient(
            config=priced_config(), transport=httpx.MockTransport(respond)
        ) as client,
        pytest.raises(LLMError, match="response error; attempts=1") as error,
    ):
        client.complete("patch", MESSAGES)
    assert len(requests) == 1
    assert len(client.ledger.entries) == 1
    assert client.ledger.entries[0].outcome == "response_error"
    assert client.ledger.unknown_attempts == 1
    assert client.ledger.total_usd is None
    assert payload not in str(error.value)
    assert "sensitive-value" not in caplog.text
