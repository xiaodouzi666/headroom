"""Request-specific Nano identities: no oracle, retry or live inference."""

import copy
import json
from dataclasses import replace

import httpx
import pytest
from test_llm_client import completion

from headroom.annotate import StackLabels, annotate_stacks
from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter


def evidence(ids=("opaque-a", "opaque-b")):
    return {
        "analysis": {
            "peak_composition": [
                {
                    "stack_id": identifier,
                    "bytes": 10 - index,
                    "category": "PRIVATE_ORACLE_CATEGORY",
                    "label": "PRIVATE_ORACLE_LABEL",
                    "frames": [{"filename": "/src/train.py", "name": "fn", "line": 10}],
                }
                for index, identifier in enumerate(ids)
            ]
        }
    }


def sdk_call(document, *, json_method="json_schema", mutate=lambda rows: rows):
    models = candidate_models()
    models["nano"] = replace(
        models["nano"],
        output_cap_field="max_completion_tokens",
        evidence="offline schema fixture",
        capabilities=VerifiedCapabilities(
            json_method=json_method,
            reasoning_method="chat_template_kwargs",
            evidence="offline fixture",
        ),
    )
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        supplied = json.loads(payload["messages"][-1]["content"])["stacks"]
        rows = [
            {"stack_id": item["stack_id"], "category": "unknown", "label": "Unresolved"}
            for item in supplied
        ]
        return httpx.Response(
            200,
            json=completion(
                model=models["nano"].model_id,
                content=json.dumps({"annotations": mutate(rows)}),
            ),
        )

    with TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(handler)
    ) as client:
        result = annotate_stacks(LLMRouter(client), document)
    assert len(requests) == 1
    return result, requests[0]


@pytest.mark.parametrize("json_method", ["json_schema", "json_object"])
def test_real_sdk_request_pins_only_supplied_ids_and_exact_count(json_method):
    document = evidence()
    before = copy.deepcopy(document)
    result, request = sdk_call(document, json_method=json_method)
    schema = json.loads(request["messages"][0]["content"].split("\n", 1)[1])
    if json_method == "json_schema":
        assert request["response_format"]["json_schema"]["schema"] == schema
    assert schema["$defs"]["StackLabel"]["properties"]["stack_id"]["enum"] == [
        "opaque-a",
        "opaque-b",
    ]
    assert schema["properties"]["annotations"]["minItems"] == 2
    assert schema["properties"]["annotations"]["maxItems"] == 2
    assert "PRIVATE_ORACLE" not in json.dumps(request)
    assert result["complete"] is True and result["heuristic_agreement"] == 0
    assert result["acceptance"] is False and document == before
    assert request["max_completion_tokens"] == 3000
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    assert "max_tokens" not in request


@pytest.mark.parametrize("kind", ["missing", "extra", "unknown_id", "duplicate_id"])
def test_sdk_and_host_reject_invalid_identity_sets_without_retry(kind):
    def mutate(rows):
        if kind == "missing":
            return rows[:1]
        if kind == "extra":
            return rows + [rows[0]]
        if kind == "unknown_id":
            return [{**rows[0], "stack_id": "invented"}, rows[1]]
        return [rows[0], {**rows[0], "label": "Other description"}]

    result, _ = sdk_call(evidence(), mutate=mutate)
    assert result["complete"] is False
    assert result["status"] == "failed"
    assert result["heuristic_agreement"] is None
    assert result["reason"] == (
        "missing_duplicate_or_unrecognized_stack"
        if kind == "duplicate_id"
        else "model_or_schema_error"
    )


def test_schema_is_fresh_per_capture_and_shared_schema_is_unchanged():
    original = StackLabels.model_json_schema()
    first, request_a = sdk_call(evidence(("capture-a-only",)))
    second, request_b = sdk_call(evidence(("capture-b-only",)))
    assert first["complete"] and second["complete"]
    assert "capture-a-only" not in json.dumps(request_b)
    assert "capture-b-only" not in json.dumps(request_a)
    assert StackLabels.model_json_schema() == original
    assert "enum" not in original["$defs"]["StackLabel"]["properties"]["stack_id"]
