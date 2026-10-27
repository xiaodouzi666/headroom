"""Offline only: bounded format recovery and public failure metadata."""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from test_diagnosis_bounded_repair import payload, run

from headroom.budget import BudgetExceeded
from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.diagnosis_protocol import COMMON_4000
from headroom.llm.client import LLMError, TokenFactoryClient
from headroom.llm.cost import Usage
from headroom.llm.router import LLMRouter, ResponseValidationError, response_validation_metadata
from headroom.orchestrator import FixRequest, Services, run_fix
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Network forbidden in output-recovery fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def sdk_fixture(replies, requests):
    models = candidate_models()
    models["ultra"] = replace(
        models["ultra"],
        output_cap_field="max_completion_tokens",
        evidence="offline fixture",
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="offline fixture",
        ),
    )

    def provider(request):
        requests.append(json.loads(request.content))
        text, finish = replies[min(len(requests) - 1, len(replies) - 1)]
        return httpx.Response(
            200,
            json={
                "id": "offline-output-recovery",
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
                "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            },
        )

    return TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(provider)
    )


@pytest.mark.parametrize(
    ("text", "finish", "reason"),
    [
        ('{"notes":["partial-response-canary"', "length", "truncated"),
        ("", "stop", "empty_json"),
        ('{"invalid":"partial-response-canary"', "stop", "invalid_json"),
    ],
)
@pytest.mark.parametrize("protocol", [None, COMMON_4000])
def test_complete_resend_uses_same_schema_cap_model_and_thinking(text, finish, reason, protocol):
    requests = []
    with sdk_fixture([(text, finish), (json.dumps(payload()), "stop")], requests) as client:
        result = run(LLMRouter(client), **({"study_protocol": protocol} if protocol else {}))
        assert len(client.ledger.entries) == 2
    assert len(requests) == 2 and result.ready_for_patch
    first, second = requests
    for key in ("model", "response_format", "max_completion_tokens", "chat_template_kwargs"):
        assert first[key] == second[key]
    assert first["max_completion_tokens"] == (4000 if protocol else 16384)
    assert first["chat_template_kwargs"]["enable_thinking"] is True
    assert second["messages"][:-1] == first["messages"]
    assert not any(message["role"] == "assistant" for message in second["messages"])
    assert "partial-response-canary" not in json.dumps(second)
    assert "complete JSON object" in second["messages"][-1]["content"]
    assert len(result.response_validation_failures) == 1
    assert result.response_validation_failures[0]["error_reason"] == reason
    assert result.response_validation_failures[0]["finish_reason"] == finish
    assert "partial-response-canary" not in json.dumps(result.response_validation_failures)


@pytest.mark.parametrize("reason", ["truncated", "empty_json", "invalid_json"])
@pytest.mark.parametrize("limit", [0, 1, 3])
def test_persistent_format_failure_respects_original_total_allowance(reason, limit):
    class Router:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise ResponseValidationError(
                "private exception canary",
                reason=reason,
                response=SimpleNamespace(text="private body canary", finish_reason="stop"),
            )

    router = Router()
    with pytest.raises(ResponseValidationError) as caught:
        run(router, max_supplements=limit)
    assert router.calls == limit + 1
    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("reason", "finish", "present"),
    [
        ("filtered", "content_filter", True),
        ("invalid_json", "content_filter", True),
        ("unknown", "stop", True),
        (["not-a-reason"], "stop", True),
        ("truncated", "length", False),
        ("invalid_json", "stop", False),
    ],
)
def test_filtered_unknown_and_missing_response_never_resend(reason, finish, present):
    class Router:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise ResponseValidationError(
                "rejected",
                reason=reason,
                response=SimpleNamespace(text="private body canary", finish_reason=finish)
                if present
                else None,
            )

    router = Router()
    with pytest.raises(ResponseValidationError):
        run(router, max_supplements=3)
    assert router.calls == 1


def test_format_and_schema_failures_share_one_supplement():
    bad = payload()
    bad["plan"][0]["expected_saving_gb"] = "not-a-number"
    requests = []
    with sdk_fixture(
        [(json.dumps(bad), "stop"), ('{"partial":', "length"), (json.dumps(payload()), "stop")],
        requests,
    ) as client:
        with pytest.raises(ResponseValidationError) as caught:
            run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert caught.value.reason == "truncated"
    assert len(requests) == 2


def test_format_recovery_does_not_weaken_precision_or_verification():
    bad = payload()
    bad["plan"][0]["title"] = "Convert the model to BF16"
    requests = []
    with sdk_fixture([("", "stop"), (json.dumps(bad), "stop")], requests) as client:
        result = run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert len(requests) == 2 and not result.ready_for_patch
    assert "NUMERICS_CHANGE_FORBIDDEN" in {issue.code for issue in result.issues}
    assert result.diagnosis.verification.compare_loss is True
    assert result.response_validation_failures[0]["error_reason"] == "empty_json"


@pytest.mark.parametrize("error_type", [LLMError, BudgetExceeded])
def test_network_and_budget_class_failures_are_not_format_retries(error_type):
    class Router:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise error_type("offline non-format fixture")

    router = Router()
    with pytest.raises(error_type):
        run(router)
    assert router.calls == 1


def test_metadata_is_a_whitelist_and_contains_only_public_numeric_usage():
    response = SimpleNamespace(
        role="diagnose",
        finish_reason="length",
        usage=Usage(42900, 16384, 59284, cached_tokens=0, reasoning_tokens=15632),
        text="raw-body-secret-canary",
        reasoning_content="hidden-reasoning-secret-canary",
    )
    error = ResponseValidationError("error-secret-canary", reason="truncated", response=response)
    before = copy.deepcopy(vars(response))
    metadata = response_validation_metadata(error)
    assert metadata == {
        "schema": "headroom.response-validation-metadata.v1",
        "error_reason": "truncated",
        "finish_reason": "length",
        "role": "diagnose",
        "usage": {
            "prompt_tokens": 42900,
            "completion_tokens": 16384,
            "total_tokens": 59284,
            "cached_tokens": 0,
            "reasoning_tokens": 15632,
        },
    }
    assert "canary" not in json.dumps(metadata)
    assert vars(response) == before


@pytest.mark.parametrize(
    "value", ["secret-canary", ["secret-canary"], {"secret": "canary"}, None, 123]
)
def test_unknown_metadata_does_not_echo_arbitrary_input(value):
    error = ResponseValidationError(
        "private",
        reason=value,
        response=SimpleNamespace(role=value, finish_reason=value, usage=value),
    )
    result = response_validation_metadata(error)
    assert result["error_reason"] == "unknown"
    assert result["finish_reason"] is None and result["role"] is None
    assert all(value is None for value in result["usage"].values())
    assert "canary" not in json.dumps(result)


def test_terminal_failed_event_persists_safe_reason_without_body_or_gpu(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    error = ResponseValidationError(
        "exception-secret-canary",
        reason="truncated",
        response=SimpleNamespace(
            role="diagnose",
            finish_reason="length",
            usage=Usage(10, 16, 26, cached_tokens=0, reasoning_tokens=12),
            text="raw-body-secret-canary",
            reasoning_content="hidden-secret-canary",
        ),
    )

    def fail_runtime(*args, **kwargs):
        raise error

    def forbidden(*args, **kwargs):
        pytest.fail("No baseline/GPU job may run in this fixture")

    store = Store(tmp_path / "store.db")
    try:
        result = run_fix(
            FixRequest(script=str(source / "train.py")),
            store=store,
            run_root=tmp_path / "jobs",
            services=Services(
                runtime_factory=fail_runtime, baseline=forbidden, provenance="offline_fixture"
            ),
        )
        failed = [
            event for event in store.events(result["run_id"]) if event["kind"] == "run.failed"
        ]
        assert len(failed) == 1 and result["status"] == "failed"
        assert failed[0]["response_validation"]["error_reason"] == "truncated"
        assert failed[0]["response_validation"]["finish_reason"] == "length"
        assert "canary" not in json.dumps(failed)
        assert store.usage(result["run_id"])["calls"] == 0
    finally:
        store.close()
