"""Dynamic request schemas through the real router/SDK, entirely offline."""

import builtins
import copy
import io
import json
import os
import socket
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator

from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.diagnose import validate_diagnosis
from headroom.diagnosis_schema import DiagnosisSchemaError, build_diagnosis_schema
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.schemas import Diagnosis


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No real DNS/INET request in schema tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module in (builtins, io):
        original = module.open

        def guarded(file, *args, _original=original, **kwargs):
            if isinstance(file, (str, bytes, os.PathLike)) and Path(
                os.fsdecode(file)
            ).name.startswith(".env"):
                raise AssertionError("Schema construction and MockTransport never read credentials")
            return _original(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)


def evidence():
    return {
        "analysis": {
            "stack_catalog": {
                "stk_z": [{"filename": "private-source.py", "line": 14, "name": "a frame"}],
                "stk_a": [],
            }
        },
        "other_evidence": {"measured_peak": 100},
    }


def payload():
    return {
        "root_causes": [
            {
                "id": "cause",
                "title": "Observed allocation",
                "category": "temporaries",
                "bytes_gb": 1.0,
                "evidence_refs": ["stk_a"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "fix",
                "type": "code",
                "title": "Release an unused buffer",
                "description": "Release the temporary after its last consumer.",
                "expected_saving_gb": 0.5,
                "numerics_impact": "none",
                "throughput_impact": "none",
                "risk": "Lifetime must be preserved",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Offline fixture only"],
    }


def client(reply, requests, *, model_role="ultra"):
    models = candidate_models()
    models[model_role] = replace(
        models[model_role],
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="offline fixture",
        ),
    )

    def provider(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "offline-schema",
                "object": "chat.completion",
                "created": 0,
                "model": models[model_role].model_id,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(reply)},
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            },
        )

    return TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(provider)
    )


@pytest.mark.parametrize("direct_analysis", [False, True])
def test_native_schema_contains_only_current_references_and_true_permissions(direct_analysis):
    source = evidence()
    if direct_analysis:
        source = source["analysis"]
    policy = {
        "allow_numerics_change": False,
        "allow_batch_grad_accum": True,
        "allow_model_change": 1,
        "other_permission": "true",
        "max_throughput_regression_pct": 25,
    }
    before, policy_before = copy.deepcopy(source), copy.deepcopy(policy)
    schema = build_diagnosis_schema(evidence=source, policy=policy)
    reply = payload()
    reply["root_causes"][0]["evidence_refs"] = ["stk_z", "stk_a"]
    reply["plan"][0]["requires_policy"] = ["allow_batch_grad_accum"]
    requests = []
    with client(reply, requests) as sdk:
        response = LLMRouter(sdk).chat(
            "diagnose",
            [{"role": "user", "content": "Measured evidence"}],
            schema,
            reasoning=False,
            max_tokens=8192,
        )
        assert len(sdk.ledger.entries) == 1
        assert response.cost.usd is None  # Fixture has no verified provider pricing.
    assert response.parsed == reply and len(requests) == 1
    native = requests[0]["response_format"]
    assert native["type"] == "json_schema"
    assert native["json_schema"]["schema"] == schema
    definitions = schema["$defs"]
    assert definitions["RootCause"]["properties"]["evidence_refs"]["items"]["enum"] == [
        "stk_a",
        "stk_z",
    ]
    step = definitions["PlanStep"]["properties"]
    assert step["requires_policy"]["items"]["enum"] == ["allow_batch_grad_accum"]
    assert step["numerics_impact"]["enum"] == ["none"]
    assert "private-source.py" not in json.dumps(schema)
    assert source == before and policy == policy_before
    assert validate_diagnosis(response.parsed, evidence=source, policy=policy).valid


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_ref",
        "false_permission",
        "numeric_truthy_permission",
        "unknown_permission",
        "minor_numerics",
        "significant_numerics",
    ],
)
def test_real_router_rejects_outputs_outside_the_request_constraints(mutation):
    policy = {
        "allow_numerics_change": False,
        "allow_batch_grad_accum": True,
        "allow_model_change": 1,
    }
    schema = build_diagnosis_schema(evidence=evidence(), policy=policy)
    reply = payload()
    if mutation == "unknown_ref":
        reply["root_causes"][0]["evidence_refs"] = ["stk_invented"]
    elif mutation.endswith("permission"):
        reply["plan"][0]["requires_policy"] = [
            {
                "false_permission": "allow_numerics_change",
                "numeric_truthy_permission": "allow_model_change",
                "unknown_permission": "missing_permission",
            }[mutation]
        ]
    else:
        reply["plan"][0]["numerics_impact"] = mutation.removesuffix("_numerics")
    requests = []
    with client(reply, requests) as sdk, pytest.raises(ResponseValidationError) as error:
        LLMRouter(sdk).chat("diagnose", [{"role": "user", "content": "Evidence"}], schema)
    assert error.value.reason == "schema_mismatch"
    assert len(requests) == 1  # Rejection never triggers a repair request.
    assert requests[0]["response_format"]["json_schema"]["schema"] == schema


@pytest.mark.parametrize(
    "policy",
    [
        {},
        {"allow_numerics_change": False},
        {"allow_numerics_change": 1},
        {"allow_numerics_change": "true"},
        {"allow_batch_grad_accum": None},
    ],
)
def test_no_true_permissions_requires_empty_array_without_invalid_empty_enum(policy):
    schema = build_diagnosis_schema(evidence=evidence(), policy=policy)
    Draft202012Validator.check_schema(schema)
    required = schema["$defs"]["PlanStep"]["properties"]["requires_policy"]
    assert required["maxItems"] == 0 and "enum" not in required["items"]
    validator = Draft202012Validator(schema)
    validator.validate(payload())
    reply = payload()
    reply["plan"][0]["requires_policy"] = ["allow_batch_grad_accum"]
    assert list(validator.iter_errors(reply))
    assert schema["$defs"]["PlanStep"]["properties"]["numerics_impact"]["enum"] == ["none"]


def test_explicit_precision_permission_preserves_all_original_numerics_choices():
    schema = build_diagnosis_schema(evidence=evidence(), policy={"allow_numerics_change": True})
    step = schema["$defs"]["PlanStep"]["properties"]
    assert (
        step["numerics_impact"]
        == Diagnosis.model_json_schema()["$defs"]["PlanStep"]["properties"]["numerics_impact"]
    )
    for value in ["none", "minor", "significant"]:
        reply = payload()
        reply["plan"][0].update(numerics_impact=value, requires_policy=["allow_numerics_change"])
        Draft202012Validator(schema).validate(reply)


@pytest.mark.parametrize(
    "source",
    [
        None,
        [],
        {},
        {"analysis": None},
        {"stack_catalog": {}},
        {"analysis": {"stack_catalog": []}},
        {"analysis": {"stack_catalog": {1: []}}},
        {"stack_catalog": {"": []}},
        {"stack_catalog": {" padded ": []}},
        {"stack_catalog": {"bad\ud800": []}},
    ],
)
def test_invalid_catalog_refuses_before_transport(source):
    requests = []
    with client(payload(), requests) as sdk, pytest.raises(DiagnosisSchemaError):
        schema = build_diagnosis_schema(evidence=source, policy={})
        LLMRouter(sdk).chat("diagnose", [{"role": "user", "content": "Evidence"}], schema)
    assert requests == []


@pytest.mark.parametrize(
    "policy", [None, [], {1: True}, {"": True}, {" padded ": False}, {"bad\ud800": True}]
)
def test_invalid_policy_keys_fail_closed_without_coercion(policy):
    with pytest.raises(DiagnosisSchemaError):
        build_diagnosis_schema(evidence=evidence(), policy=policy)


def test_deepcopy_preserves_historical_schema_and_every_unrelated_field(monkeypatch):
    original = Diagnosis.model_json_schema()
    baseline = copy.deepcopy(original)
    monkeypatch.setattr(Diagnosis, "model_json_schema", classmethod(lambda cls: original))
    constrained = build_diagnosis_schema(evidence=evidence(), policy={})
    assert original == baseline
    restored = copy.deepcopy(constrained)
    for name, field in [
        ("RootCause", "evidence_refs"),
        ("PlanStep", "requires_policy"),
        ("PlanStep", "numerics_impact"),
    ]:
        restored["$defs"][name]["properties"][field] = copy.deepcopy(
            baseline["$defs"][name]["properties"][field]
        )
    assert restored == baseline
    constrained["$defs"]["RootCause"]["properties"]["title"]["minLength"] = 999
    assert original == baseline
    # Historical schema remains intentionally broad; postvalidation still rejects a fake reference.
    reply = payload()
    reply["root_causes"][0]["evidence_refs"] = ["stk_unknown"]
    Diagnosis.model_validate(reply)
    assert not validate_diagnosis(reply, evidence=evidence(), policy={}).valid


def test_json_unsafe_base_schema_is_not_silently_stringified(monkeypatch):
    original = Diagnosis.model_json_schema()
    original["bad_extension"] = float("nan")
    monkeypatch.setattr(Diagnosis, "model_json_schema", classmethod(lambda cls: original))
    with pytest.raises(DiagnosisSchemaError, match="JSON contract"):
        build_diagnosis_schema(evidence=evidence(), policy={})


def test_production_diagnosis_reuses_current_schema_for_the_supplement():
    from headroom.diagnose import diagnose_with_router

    requests = []
    reply = payload()
    with client(reply, requests) as sdk:
        verdict = diagnose_with_router(
            LLMRouter(sdk),
            "Measured stacks",
            evidence=evidence(),
            goal="reclaim",
            policy={},
            required_saving_gb=2.0,
            max_supplements=1,
        )
    assert verdict.requires_supplement and not verdict.valid
    assert len(requests) == 2
    expected = build_diagnosis_schema(evidence=evidence(), policy={})
    assert all(r["response_format"]["json_schema"]["schema"] == expected for r in requests)
    assert all(r["max_tokens"] == 8192 for r in requests)
    assert all(r["chat_template_kwargs"] == {"enable_thinking": False} for r in requests)
    assert len(requests[1]["messages"]) == len(requests[0]["messages"]) + 2


@pytest.mark.parametrize("source", [{}, {"analysis": {"stack_catalog": {}}}])
def test_production_diagnosis_missing_catalog_never_dispatches(source):
    from headroom.diagnose import diagnose_with_router

    requests = []
    with client(payload(), requests) as sdk, pytest.raises(DiagnosisSchemaError):
        diagnose_with_router(
            LLMRouter(sdk), "Missing evidence", evidence=source, goal="reclaim", policy={}
        )
    assert requests == []


@pytest.mark.parametrize(
    "mutation",
    [
        "wide_historical",
        "wrong_ref",
        "false_permission",
        "wrong_numerics",
        "bool_for_integer",
        "nonserializable",
    ],
)
def test_prepared_wrapper_checks_independently_rebuilt_schema_before_dispatch(tmp_path, mutation):
    from headroom.acceptance.diagnosis import DiagnosisAcceptanceRefused, _prepared_router

    source, policy = evidence(), {}
    schema = build_diagnosis_schema(evidence=source, policy=policy)
    if mutation == "wide_historical":
        schema = Diagnosis.model_json_schema()
    elif mutation == "wrong_ref":
        schema["$defs"]["RootCause"]["properties"]["evidence_refs"]["items"]["enum"] = ["invented"]
    elif mutation == "false_permission":
        schema["$defs"]["PlanStep"]["properties"]["requires_policy"]["maxItems"] = 1
    elif mutation == "wrong_numerics":
        schema["$defs"]["PlanStep"]["properties"]["numerics_impact"]["enum"] = ["minor"]
    elif mutation == "bool_for_integer":
        # Python dict equality treats True == 1; wire JSON types must still match.
        schema["$defs"]["RootCause"]["properties"]["evidence_refs"]["minItems"] = True
    else:
        schema["bad"] = object()
    requests = []
    messages = [{"role": "user", "content": "Pinned evidence"}]
    with client(payload(), requests) as sdk:
        wrapped = _prepared_router(
            LLMRouter(sdk), messages, tmp_path / "response.json", evidence=source, policy=policy
        )
        with pytest.raises(DiagnosisAcceptanceRefused, match="DIAGNOSIS_SCHEMA_CHANGED"):
            wrapped.chat("diagnose", messages, schema, max_tokens=8192, reasoning=False)
    assert requests == [] and not (tmp_path / "response.json").exists()


def test_prepared_wrapper_passes_pinned_schema_once_and_retains_messages_gate(tmp_path):
    from headroom.acceptance.diagnosis import DiagnosisAcceptanceRefused, _prepared_router

    source, policy = evidence(), {}
    schema = build_diagnosis_schema(evidence=source, policy=policy)
    messages = [{"role": "user", "content": "Pinned evidence"}]
    requests = []
    with client(payload(), requests) as sdk:
        wrapped = _prepared_router(
            LLMRouter(sdk), messages, tmp_path / "response.json", evidence=source, policy=policy
        )
        with pytest.raises(DiagnosisAcceptanceRefused, match="DIAGNOSIS_REQUEST_CHANGED"):
            wrapped.chat("diagnose", [], schema, max_tokens=8192, reasoning=False)
        wrapped.chat("diagnose", messages, schema, max_tokens=8192, reasoning=False)
        with pytest.raises(DiagnosisAcceptanceRefused, match="ONLY_ONE_PREPARED"):
            wrapped.chat("diagnose", messages, schema, max_tokens=8192, reasoning=False)
    assert len(requests) == 1 and (tmp_path / "response.json").is_file()
    assert requests[0]["response_format"]["json_schema"]["schema"] == schema


def test_prepared_wrapper_missing_catalog_refuses_before_wrapping_or_saving(tmp_path):
    from headroom.acceptance.diagnosis import _prepared_router

    requests = []
    with client(payload(), requests) as sdk, pytest.raises(DiagnosisSchemaError):
        _prepared_router(LLMRouter(sdk), [], tmp_path / "response.json", evidence={}, policy={})
    assert requests == [] and not (tmp_path / "response.json").exists()


@pytest.mark.parametrize("condition", ["full_super", "traceback_ultra"])
def test_evaluation_conditions_keep_dynamic_schema_with_only_visible_ids(tmp_path, condition):
    from headroom.evaluation import condition_services, restricted_evidence

    source = evidence()
    source["evaluation_inputs"] = {
        "traceback": "Captured allocation traceback",
        "memory_summary": "Captured allocation summary",
    }
    source["sources"] = [{"text": "snapshot-source-secret"}]
    visible = restricted_evidence(source)[1] if condition == "traceback_ultra" else source
    reply = payload()
    reply["root_causes"][0]["evidence_refs"] = [
        "traceback" if condition == "traceback_ultra" else "stk_a"
    ]
    requests = []
    role = "super" if condition == "full_super" else "ultra"
    services = condition_services(condition, tmp_path / "audit")
    with client(reply, requests, model_role=role) as sdk:
        checked = services.diagnose(
            LLMRouter(sdk),
            "Full measured evidence",
            evidence=source,
            goal="reclaim",
            policy={},
            max_supplements=0,
        )
    assert checked.valid and len(requests) == 1
    request = requests[0]
    expected = build_diagnosis_schema(evidence=visible, policy={})
    assert request["response_format"]["json_schema"]["schema"] == expected
    assert request["model"] == candidate_models()[role].model_id
    assert request["max_tokens"] == 8192
    assert request["chat_template_kwargs"] == {"enable_thinking": False}
    if condition == "traceback_ultra":
        references = expected["$defs"]["RootCause"]["properties"]["evidence_refs"]["items"]["enum"]
        assert references == ["memory_summary", "traceback"]
        wire = json.dumps(request)
        assert "stk_a" not in wire and "stk_z" not in wire
        assert "private-source.py" not in wire and "snapshot-source-secret" not in wire
