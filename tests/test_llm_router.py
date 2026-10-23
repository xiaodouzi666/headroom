import json
from dataclasses import replace

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError, parse_json


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int
    label: str


def response(text, finish="stop"):
    return httpx.Response(
        200,
        json={
            "id": "mock",
            "object": "chat.completion",
            "created": 0,
            "model": SUPER_MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish,
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        },
    )


@pytest.mark.parametrize(
    "text",
    [
        '{"count": 2, "label": "ok"}',
        '```json\n{"count": 2, "label": "ok"}\n```',
        'Here is the result:\n{"count": 2, "label": "ok"}\nEnd.',
    ],
)
def test_json_fallback_and_schema_validation(text):
    with TokenFactoryClient(transport=httpx.MockTransport(lambda _: response(text))) as client:
        result = LLMRouter(client).chat("patch", [{"role": "user", "content": "answer"}], Answer)
    assert result.parsed == {"count": 2, "label": "ok"}
    assert result.usage.prompt_tokens == 10


@pytest.mark.parametrize(
    "text",
    [
        '{"count": "2", "label": "ok"}',
        '{"count": 2}',
        '{"count": 2, "label": "ok", "extra": 1}',
        '{"count": NaN, "label": "ok"}',
        '{"count": 2, "count": 3, "label": "ok"}',
        '{"count": 2, "label": "ok"} {"count": 3, "label": "wrong"}',
        "not json",
    ],
)
def test_bad_json_or_schema_raises_after_usage_is_recorded(text):
    with TokenFactoryClient(transport=httpx.MockTransport(lambda _: response(text))) as client:
        with pytest.raises(ResponseValidationError):
            LLMRouter(client).chat("patch", [{"role": "user", "content": "answer"}], Answer)
        assert len(client.ledger.entries) == 1
        assert client.ledger.entries[0].usage is not None


@pytest.mark.parametrize("method", ["text", "json_object", "json_schema"])
def test_configured_json_method_and_dict_schema(method):
    calls = []
    models = candidate_models()
    models["super"] = replace(
        models["super"],
        capabilities=VerifiedCapabilities(json_method=method, evidence="offline fixture"),
    )

    def respond(request):
        calls.append(json.loads(request.content))
        return response('{"count": 2, "label": "ok"}')

    with TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(respond)
    ) as client:
        result = LLMRouter(client).chat(
            "patch", [{"role": "user", "content": "answer"}], Answer.model_json_schema()
        )
    assert result.parsed["count"] == 2
    if method == "text":
        assert "response_format" not in calls[0]
    else:
        assert calls[0]["response_format"]["type"] == method


def test_truncated_structured_response_is_not_accepted_even_if_json_parses():
    with (
        TokenFactoryClient(
            transport=httpx.MockTransport(
                lambda _: response('{"count": 2, "label": "ok"}', finish="length")
            )
        ) as client,
        pytest.raises(ResponseValidationError, match="truncated"),
    ):
        LLMRouter(client).chat("patch", [{"role": "user", "content": "answer"}], Answer)


def test_external_schema_ref_is_rejected_before_request():
    seen = []
    with (
        TokenFactoryClient(
            transport=httpx.MockTransport(lambda request: seen.append(request))
        ) as client,
        pytest.raises(ValueError, match="local"),
    ):
        LLMRouter(client).chat(
            "patch",
            [{"role": "user", "content": "answer"}],
            {"$ref": "https://attacker.invalid/schema"},
        )
    assert not seen


def test_nested_local_schema_ref_is_supported():
    schema = {
        "$defs": {"name": {"type": "string"}},
        "type": "object",
        "properties": {"name": {"$ref": "#/$defs/name"}},
        "required": ["name"],
    }
    with TokenFactoryClient(
        transport=httpx.MockTransport(lambda _: response('{"name":"ok"}'))
    ) as client:
        assert LLMRouter(client).chat(
            "patch", [{"role": "user", "content": "answer"}], schema
        ).parsed == {"name": "ok"}


def test_malformed_outer_object_cannot_be_salvaged_as_inner_object():
    with pytest.raises(ResponseValidationError):
        parse_json('{"broken":NaN,"inner":{"ok":true}}')


@pytest.mark.parametrize(
    "text",
    [
        "1e309",
        '{"value":-1e309}',
        '[{"nested":[1,1e999]}]',
        '```json\n{"value":1e309}\n```',
        'Answer: {"value":[1e309]}',
    ],
)
def test_parser_rejects_exponent_overflow_at_any_depth(text):
    with pytest.raises(ResponseValidationError):
        parse_json(text)


def test_dict_schema_cannot_accept_nonfinite_decoded_number():
    schema = {"type": "object", "properties": {"value": {"type": "number"}}, "required": ["value"]}
    with TokenFactoryClient(
        transport=httpx.MockTransport(lambda _: response('{"value":1e309}'))
    ) as client:
        with pytest.raises(ResponseValidationError):
            LLMRouter(client).chat("patch", [{"role": "user", "content": "answer"}], schema)
        assert len(client.ledger.entries) == 1
        assert client.ledger.entries[0].usage is not None
