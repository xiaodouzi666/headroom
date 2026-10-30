"""Offline request-policy contracts; no live credentials, provider, GPU, or allocation."""

import json
import socket
from dataclasses import FrozenInstanceError, replace

import httpx
import pytest
from test_diagnosis_bounded_repair import evidence, payload

from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.diagnose import PROMPT_PATH, build_diagnosis_messages, diagnose_with_router
from headroom.diagnosis_protocol import (
    COMMON_4000,
    COMPACT_PROMPT_PATH,
    FINAL48_DIAGNOSIS_ONLY,
    PLANNER_COMPACT_INSTRUCTIONS,
    PROMPT_CAP_MARKER,
    DiagnosisRequestPolicy,
    diagnosis_cap,
)
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("DNS and real sockets are forbidden in request-policy tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def client_for(replies, requests, *, cap_field="max_completion_tokens"):
    models = candidate_models()
    models["ultra"] = replace(
        models["ultra"],
        output_cap_field=cap_field,
        evidence="synthetic output-cap fixture; no provider capability claim",
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="synthetic offline fixture; no provider capability claim",
        ),
    )

    def respond(request):
        requests.append(json.loads(request.content))
        text, finish = replies[min(len(requests) - 1, len(replies) - 1)]
        return httpx.Response(
            200,
            json={
                "id": "offline-policy",
                "object": "chat.completion",
                "created": 0,
                "model": models["ultra"].model_id,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {"role": "assistant", "content": text},
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 30,
                    "total_tokens": 50,
                },
            },
        )

    return TokenFactoryClient(
        config=RuntimeConfig(models=models),
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )


def diagnose(router, **kwargs):
    return diagnose_with_router(
        router,
        "Measured snapshot stack stk",
        evidence=evidence(),
        goal="reclaim",
        policy={},
        **kwargs,
    )


def test_explicit_policy_changes_prompt_cap_without_changing_old_requests():
    ordinary = build_diagnosis_messages("same evidence", goal="reclaim", policy={})
    study = build_diagnosis_messages(
        "same evidence", goal="reclaim", policy={}, study_protocol=COMMON_4000
    )
    final48 = build_diagnosis_messages(
        "same evidence", goal="reclaim", policy={}, request_policy=FINAL48_DIAGNOSIS_ONLY
    )
    template = PROMPT_PATH.read_text()
    assert ordinary[0]["content"] == template.replace(PROMPT_CAP_MARKER, "16384")
    assert study[0]["content"] == template.replace(PROMPT_CAP_MARKER, "4000")
    assert final48[0]["content"] == (
        PLANNER_COMPACT_INSTRUCTIONS
        + "\n"
        + COMPACT_PROMPT_PATH.read_text().replace(PROMPT_CAP_MARKER, "2000")
    )
    assert ordinary[1] == study[1]
    # The explicit bounded planner keeps all input values while moving the
    # actual task after long evidence; the older request byte order is retained.
    assert ordinary[1]["role"] == final48[1]["role"] == "user"
    assert json.loads(ordinary[1]["content"]) == json.loads(final48[1]["content"])
    assert diagnosis_cap() == 16384
    assert diagnosis_cap(COMMON_4000) == 4000
    assert diagnosis_cap(request_policy=FINAL48_DIAGNOSIS_ONLY) == 2000
    with pytest.raises(FrozenInstanceError):
        FINAL48_DIAGNOSIS_ONLY.reasoning = True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "arbitrary"},
        {"max_completion_tokens": 2001},
        {"max_completion_tokens": True},
        {"max_completion_tokens": 2000.0},
        {"reasoning": True},
        {"reasoning": 0},
        {"reasoning": None},
    ],
)
def test_policy_cannot_silently_expand_or_change_request_mode(kwargs):
    with pytest.raises(ValueError):
        DiagnosisRequestPolicy(**kwargs)


@pytest.mark.parametrize("invalid", [{}, "final48", True, 2000])
def test_untyped_policy_refused_before_router(invalid):
    class Never:
        def chat(self, *args, **kwargs):
            pytest.fail("Invalid policy must not reach a router")

    with pytest.raises(ValueError):
        diagnose(Never(), request_policy=invalid)


def test_study_and_request_policy_cannot_be_mixed():
    with pytest.raises(ValueError, match="cannot mix"):
        build_diagnosis_messages(
            "evidence",
            goal="reclaim",
            policy={},
            study_protocol=COMMON_4000,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )


@pytest.mark.parametrize(
    "kwargs,cap,reasoning",
    [
        ({}, 16384, True),
        ({"study_protocol": COMMON_4000}, 4000, True),
        ({"request_policy": FINAL48_DIAGNOSIS_ONLY}, 2000, False),
    ],
)
def test_wire_prompt_recorded_mode_and_selected_schema_agree(kwargs, cap, reasoning):
    requests = []
    with client_for([(json.dumps(payload()), "stop")], requests) as client:
        result = diagnose(LLMRouter(client), max_supplements=0, **kwargs)
    assert result.valid
    assert len(requests) == 1
    body = requests[0]
    assert body["max_completion_tokens"] == cap
    assert "max_tokens" not in body
    assert body["chat_template_kwargs"] == {"enable_thinking": reasoning}
    assert body["response_format"]["type"] == "json_schema"
    expected_prompt = PROMPT_PATH.read_text().replace(PROMPT_CAP_MARKER, str(cap))
    if kwargs.get("request_policy") is FINAL48_DIAGNOSIS_ONLY:
        expected_prompt = (
            PLANNER_COMPACT_INSTRUCTIONS
            + "\n"
            + COMPACT_PROMPT_PATH.read_text().replace(PROMPT_CAP_MARKER, str(cap))
        )
    assert body["messages"][1]["content"] == expected_prompt
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["plan"].get("maxItems") == (1 if cap == 2000 else None)
    assert result.response_request_modes == (
        {
            "request_index": 1,
            "purpose": "initial",
            "requested_reasoning": reasoning,
            "max_completion_tokens": cap,
            "scope": "host_requested_mode_only",
        },
    )


@pytest.mark.parametrize(
    "bad_text,finish",
    [
        ("not JSON", "stop"),
        ("", "stop"),
        ('{"root_causes":', "length"),
    ],
)
def test_explicit_policy_survives_existing_format_supplement(bad_text, finish):
    requests = []
    with client_for([(bad_text, finish), (json.dumps(payload()), "stop")], requests) as client:
        result = diagnose(
            LLMRouter(client),
            max_supplements=1,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert result.valid
    assert len(requests) == 2
    assert all(body["max_completion_tokens"] == 2000 for body in requests)
    assert all(body["chat_template_kwargs"] == {"enable_thinking": False} for body in requests)
    assert all(mode["requested_reasoning"] is False for mode in result.response_request_modes)


def test_zero_supplements_preserves_paid_validation_failure_without_second_request():
    requests = []
    with (
        client_for([("not JSON", "stop")], requests) as client,
        pytest.raises(ResponseValidationError) as caught,
    ):
        diagnose(
            LLMRouter(client),
            max_supplements=0,
            request_policy=FINAL48_DIAGNOSIS_ONLY,
        )
    assert caught.value.response.usage.prompt_tokens == 20
    assert len(requests) == 1


def test_policy_keeps_the_model_selected_output_field():
    requests = []
    with client_for([(json.dumps(payload()), "stop")], requests, cap_field="max_tokens") as client:
        result = diagnose(
            LLMRouter(client), max_supplements=0, request_policy=FINAL48_DIAGNOSIS_ONLY
        )
    assert result.valid
    assert requests[0]["max_tokens"] == 2000
    assert "max_completion_tokens" not in requests[0]
