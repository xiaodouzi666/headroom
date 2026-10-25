"""Prepared request evidence must match the SDK's actual transport bytes."""

import hashlib
import json
from dataclasses import replace

import httpx
import pytest
from test_llm_client import completion
from test_runtime_budget import fixture_runtime

from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import LLMError, TokenFactoryClient
from headroom.llm.request_audit import MAX_CAPTURE_BYTES, capture_request
from headroom.llm.router import LLMRouter


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Real network forbidden in request-audit tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


def test_prepared_capture_includes_router_schema_reasoning_and_supplement():
    captured, transported = [], []
    models = candidate_models()
    models["super"] = replace(
        models["super"],
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            tools=True,
            evidence="offline fixture only",
        ),
    )

    def handler(request):
        transported.append(request.content)
        return httpx.Response(200, json=completion(content='{"answer": 1}'))

    schema = {"type": "object", "properties": {"answer": {"type": "integer"}}}
    messages = [
        {"role": "user", "content": "execution_context batch=32"},
        {"role": "assistant", "content": '{"needs_more_info": true}'},
        {"role": "user", "content": "fact feedback: the actual argv is available"},
    ]
    with TokenFactoryClient(
        config=RuntimeConfig(models=models),
        transport=httpx.MockTransport(handler),
        on_request=lambda *args: captured.append(args),
    ) as client:
        LLMRouter(client).chat("patch", messages, schema, reasoning=False)
    role, model, attempt, evidence = captured[0]
    assert role == "patch" and attempt == 1
    assert model == models["super"].model_id
    assert evidence["wire_body_sha256"] == hashlib.sha256(transported[0]).hexdigest()
    assert evidence["payload"] == json.loads(transported[0])
    assert evidence["payload"]["messages"][1:] == messages
    assert evidence["payload"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert evidence["payload"]["response_format"]["json_schema"]["schema"] == schema
    assert "timeout" not in evidence["payload"]
    assert "authorization" not in json.dumps(evidence).lower()
    assert evidence["delivery_confirmed"] is False


def test_runtime_calls_each_have_prepared_evidence_linked_to_budget(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(200, json=completion(model=json.loads(request.content)["model"]))

    bundle, budget, store = fixture_runtime(tmp_path, handler, limit="0.5")
    try:
        bundle.router.chat("diagnose", [{"role": "user", "content": "context"}])
        bundle.router.chat("diagnose", [{"role": "user", "content": "supplement"}])
        rows = store.llm_calls("run")
        assert len(rows) == len(bodies) == 2
        for row, body in zip(rows, bodies, strict=True):
            evidence = row["request_evidence"]
            assert evidence["wire_body_sha256"] == hashlib.sha256(body).hexdigest()
            assert evidence["attempt"] == row["attempt"]
            assert row["budget_attempt_id"]
            assert row["settled"]
        assert rows[0]["budget_attempt_id"] != rows[1]["budget_attempt_id"]
        assert budget.snapshot("run")["unknown_attempts"] == 0
    finally:
        bundle.close()
        store.close()


def test_runtime_key_redacted_from_body_copy_without_modifying_dispatch(tmp_path):
    bodies = []

    def handler(request):
        bodies.append(request.content)
        return httpx.Response(200, json=completion(model=json.loads(request.content)["model"]))

    bundle, _, store = fixture_runtime(tmp_path, handler)
    try:
        bundle.router.chat(
            "diagnose", [{"role": "user", "content": "do not retain offline-placeholder"}]
        )
        evidence = store.llm_calls("run")[0]["request_evidence"]
        assert b"offline-placeholder" in bodies[0]
        assert "offline-placeholder" not in json.dumps(evidence)
        assert evidence["payload_status"] == "redacted"
    finally:
        bundle.close()
        store.close()


def test_hook_failure_prevents_dispatch_and_keeps_conservative_attempt_record():
    transported = []

    def handler(request):
        transported.append(request)
        return httpx.Response(200, json=completion())

    def fail(*args):
        raise OSError("private local failure")

    with TokenFactoryClient(transport=httpx.MockTransport(handler), on_request=fail) as client:
        with pytest.raises(LLMError, match="response error"):
            client.complete("patch", [{"role": "user", "content": "hello"}])
        assert not transported
        assert client.ledger.unknown_attempts == 1


def test_bounded_capture_and_scoped_redaction():
    body = json.dumps(
        {"api_key": "sensitive", "messages": [{"content": "Bearer token-value"}]}
    ).encode()
    result = capture_request(body)
    assert result["payload_status"] == "redacted"
    assert "sensitive" not in json.dumps(result)
    assert "token-value" not in json.dumps(result)
    oversized = capture_request(b"x" * (MAX_CAPTURE_BYTES + 1))
    assert oversized["payload_status"] == "omitted_size"
    assert oversized["payload"] is None
    invalid = capture_request(b"not JSON")
    assert invalid["payload_status"] == "invalid_json"


def test_store_capture_failure_cannot_be_reported_as_success(tmp_path, monkeypatch):
    transported = []

    def handler(request):
        transported.append(request)
        return httpx.Response(200, json=completion())

    bundle, budget, store = fixture_runtime(tmp_path, handler)

    def refuse_evidence(call_id, evidence):
        raise OSError("audit unavailable")

    monkeypatch.setattr(store, "record_llm_request", refuse_evidence)
    try:
        with pytest.raises(LLMError, match="response error"):
            bundle.router.chat("diagnose", [{"role": "user", "content": "context"}])
        assert not transported
        assert store.llm_calls("run")[0]["outcome"] == "response_error"
        assert budget.snapshot("run")["unknown_attempts"] == 1
    finally:
        bundle.close()
        store.close()


def test_client_retry_captures_both_attempts_without_reconstruction():
    captures, bodies = [], []

    def handler(request):
        bodies.append(request.content)
        if len(bodies) == 1:
            return httpx.Response(503, json={"error": {"message": "temporary"}})
        return httpx.Response(200, json=completion())

    with TokenFactoryClient(
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        on_request=lambda *args: captures.append(args),
    ) as client:
        client.complete("patch", [{"role": "user", "content": "context"}])
    assert [item[2] for item in captures] == [1, 2]
    assert [item[3]["wire_body_sha256"] for item in captures] == [
        hashlib.sha256(body).hexdigest() for body in bodies
    ]


def test_prepared_evidence_cannot_be_replaced_or_attached_to_wrong_attempt(tmp_path):
    bundle, _, store = fixture_runtime(tmp_path, lambda _: None)
    try:
        row = store.add_llm_call(
            "run", model="model", role="patch", attempt=1, outcome="pending", settled=False
        )
        evidence = {"model": "wrong", "role": "patch", "attempt": 1}
        with pytest.raises(ValueError, match="differs"):
            store.record_llm_request(row["id"], evidence)
        evidence["model"] = "model"
        store.record_llm_request(row["id"], evidence)
        with pytest.raises(ValueError, match="uncaptured pending"):
            store.record_llm_request(row["id"], evidence)
        persisted = store.llm_calls("run")[0]
        assert persisted["outcome"] == "pending" and persisted["settled"] is False
    finally:
        bundle.close()
        store.close()


def test_evaluation_initial_copy_retains_context_and_failure_feedback(tmp_path, monkeypatch):
    import headroom.diagnose
    import headroom.orchestrator  # Capture real Services defaults before patching.
    from headroom.evaluation import condition_services

    seen = {}

    def fake(router, markdown, **kwargs):
        seen.update(kwargs)
        return "observed"

    monkeypatch.setattr(headroom.diagnose, "diagnose_with_router", fake)
    evidence = {
        "execution_context": {"script_args": {"values": ["--batch_size=32"], "complete": True}},
        "candidate_evidence": [{"round": 1, "fixture_marker": "prior-candidate"}],
    }
    feedback = [{"round": 1, "failure": {"phase": "application", "reason": "rejected-source"}}]
    result = condition_services("full_ultra", tmp_path / "audit").diagnose(
        object(),
        "evidence",
        evidence=evidence,
        goal="reclaim",
        policy={"allow_numerics_change": False},
        verification_feedback=feedback,
    )
    assert result == "observed"
    messages = json.loads((tmp_path / "audit/01-initial-messages.json").read_text())
    expected = headroom.diagnose.build_diagnosis_messages(
        "evidence",
        goal="reclaim",
        policy={"allow_numerics_change": False},
        execution_context=evidence["execution_context"],
        candidate_evidence=evidence["candidate_evidence"],
        verification_feedback=feedback,
    )
    assert messages == expected
    assert seen["evidence"] == evidence and seen["verification_feedback"] == feedback
