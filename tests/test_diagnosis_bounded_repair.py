"""Offline provider-shaped repairs retain all gates and the existing finite call cap."""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from jsonschema import Draft202012Validator

from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.schemas import Diagnosis
from headroom.solver_context import (
    invocation_reading_aid,
    invocation_reference_catalog,
    prompt_arguments,
    solver_prompt_context,
)


def evidence(args=("--width=7", "--chunks=3")):
    return {
        "analysis": {"stack_catalog": {"stk": []}},
        "execution_context": {
            "script": "entry.py",
            "script_args": prompt_arguments(args),
            "execution_argv": prompt_arguments(["python3", "entry.py", *args]),
        },
    }


def payload():
    return {
        "root_causes": [
            {
                "id": "cause",
                "title": "Measured activations",
                "category": "activations",
                "bytes_gb": 1.0,
                "evidence_refs": ["stk"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "fix",
                "type": "code",
                "title": "Recompute an intermediate",
                "description": "Recompute the intermediate during backward, preserving its consumers.",
                "expected_saving_gb": 1.0,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Measure recomputation cost",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": [],
    }


def provider_client(replies, requests):
    models = candidate_models()
    models["ultra"] = replace(
        models["ultra"],
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="offline fixture",
        ),
    )

    def provider(request):
        requests.append(json.loads(request.content))
        reply = replies[min(len(requests) - 1, len(replies) - 1)]
        return httpx.Response(
            200,
            json={
                "id": "offline-repair",
                "object": "chat.completion",
                "created": 0,
                "model": models["ultra"].model_id,
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


def run(router, **kw):
    return diagnose_with_router(
        router, "Measured stacks and source", evidence=evidence(), goal="reclaim", policy={}, **kw
    )


def test_host_refs_preserve_namespace_order_and_only_advertise_visible_tokens():
    source = evidence(("--width=7", "--width=9", "--flag", "positional"))
    before = copy.deepcopy(source)
    view = invocation_reading_aid(source["execution_context"])
    catalog = invocation_reference_catalog(source["execution_context"])
    assert catalog["script_args[0]"] == {"source": "script_args", "index": 0, "token": "--width=7"}
    assert catalog["script_args[1]"]["token"] == "--width=9"
    assert catalog["script_args[2]"]["token"] == "--flag"
    assert all(item["source"] == "script_args" for item in view["assignments"])
    assert source == before
    schema = build_diagnosis_schema(evidence=source, policy={})
    assert schema["properties"]["invocation_refs"]["items"]["enum"] == sorted(catalog)
    assert "--width=7" not in json.dumps(schema)  # Values stay in evidence, not the schema.
    reply = payload()
    reply["invocation_refs"] = ["script_args[0]", "script_args[1]"]
    Draft202012Validator(schema).validate(reply)
    result = validate_diagnosis(reply, evidence=source, policy={})
    assert result.ready_for_patch
    assert result.invocation_provenance["status"] == "references_resolved"
    assert result.invocation_provenance["references"] == {"resolved": 2, "unresolved": 0}
    assert result.invocation_provenance["target_effective_configuration"] == "unverified"
    assert not result.invocation_provenance["reference_resolution_proves_interpretation"]
    assert not result.invocation_provenance["unstructured_prose_checked"]
    assert "invocation_refs" not in Diagnosis.model_json_schema()["required"]


def test_resolved_reference_never_repairs_a_contradictory_legacy_claim():
    reply = payload()
    reply.update(
        invocation_refs=["script_args[0]"],
        invocation_claims=[{"source": "execution_argv", "index": 0, "token": "--width=7"}],
    )
    result = validate_diagnosis(reply, evidence=evidence(), policy={})
    assert not result.valid
    assert result.invocation_provenance["status"] == "contradicted"
    assert result.diagnosis.invocation_claims[0].source == "execution_argv"
    assert result.issues[0].path == "/invocation_claims/0"


@pytest.mark.parametrize(
    "mutation", ["secret", "missing_metadata", "truncated", "view_bound", "missing_context"]
)
def test_unknown_positions_cannot_be_advertised_or_validated_by_reference(mutation):
    source = evidence()
    forbidden = "script_args[0]"
    if mutation == "secret":
        source = evidence(("--password=canary-never-echo",))
    elif mutation == "missing_metadata":
        del source["execution_context"]["script_args"]["redacted_positions"]
    elif mutation == "truncated":
        source["execution_context"]["script_args"].update(complete=False, omitted_count=20)
        forbidden = "script_args[4]"
    elif mutation == "view_bound":
        source = evidence(tuple("--label=" + "界" * 300 for _ in range(8)))
    else:
        del source["execution_context"]
    schema = build_diagnosis_schema(evidence=source, policy={})
    allowed = schema["properties"]["invocation_refs"]["items"].get("enum", [])
    assert forbidden not in allowed
    reply = payload()
    reply.update(needs_more_info=True, invocation_refs=[forbidden])
    result = validate_diagnosis(reply, evidence=source, policy={})
    assert not result.valid and not result.ready_for_patch
    assert result.diagnosis.needs_more_info
    assert result.invocation_provenance["references"]["unresolved"] == 1
    assert result.invocation_provenance["status"] == "unverified"
    assert "canary" not in (result.supplement_request or "")
    if mutation != "missing_context":
        context = solver_prompt_context(execution_context=source["execution_context"])
        assert len(json.dumps(context, ensure_ascii=True).encode()) <= 64 * 1024
        assert (
            len(json.dumps(context["invocation_reading_aid"], ensure_ascii=True).encode()) <= 4096
        )


@pytest.mark.parametrize(
    "title,code",
    [
        ("Reduce sequence length", "MODEL_CHANGE_FORBIDDEN"),
        ("Switch to bf16", "NUMERICS_CHANGE_FORBIDDEN"),
        ("Reduce batch size", "BATCH_CHANGE_FORBIDDEN"),
        ("Skip training", "TRAINING_TRUNCATION_FORBIDDEN"),
    ],
)
def test_policy_errors_produce_exact_bounded_feedback_without_altering_output(title, code):
    reply = payload()
    reply["plan"][0]["title"] = title
    original = copy.deepcopy(reply)
    result = validate_diagnosis(reply, evidence=evidence(), policy={})
    assert not result.ready_for_patch and result.requires_supplement
    assert any(item.code == code and item.path == "/plan/0" for item in result.issues)
    assert code in result.supplement_request and '"path": "/plan/0"' in result.supplement_request
    assert "ALL supplied evidence" in result.supplement_request
    assert reply == original and result.diagnosis.plan[0].title == title


def test_entire_validator_runs_after_schema_repair_and_every_call_uses_same_cap():
    first = payload()
    first["invocation_refs"] = ["execution_argv[0]"]  # Not an advertised ID.
    second = payload()
    second["invocation_refs"] = ["script_args[0]"]
    second["plan"][0]["title"] = "Reduce sequence length"
    third = payload()
    third["invocation_refs"] = ["script_args[0]"]
    requests = []
    with provider_client([first, second, third], requests) as sdk:
        result = run(LLMRouter(sdk), max_supplements=2)
        assert len(sdk.ledger.entries) == 3
    assert result.ready_for_patch and len(requests) == 3
    assert "JSON_SCHEMA_MISMATCH" in requests[1]["messages"][-1]["content"]
    assert "MODEL_CHANGE_FORBIDDEN" in requests[2]["messages"][-1]["content"]
    assert all(r["max_tokens"] == 16384 for r in requests)
    assert all(r["chat_template_kwargs"] == {"enable_thinking": True} for r in requests)
    assert all(r["response_format"] == requests[0]["response_format"] for r in requests)
    assert len(requests[2]["messages"]) == len(requests[0]["messages"]) + 4


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_persistent_policy_violation_stops_at_existing_allowance(limit):
    reply = payload()
    reply["plan"][0]["title"] = "Reduce sequence length"
    requests = []
    with provider_client([reply], requests) as sdk:
        result = run(LLMRouter(sdk), max_supplements=limit)
        assert len(sdk.ledger.entries) == limit + 1
    assert len(requests) == limit + 1 and not result.valid
    assert result.requires_supplement and not result.ready_for_patch


def test_valid_remaining_evidence_gap_does_not_force_an_extra_call_or_ready():
    bad = payload()
    bad["plan"][0]["title"] = "Reduce sequence length"
    gap = payload()
    gap.update(
        needs_more_info=True,
        evidence_requests=[
            {
                "field": "target.loss_reduction",
                "reason": "ambiguous",
                "detail": "Consumer contract unavailable.",
            }
        ],
    )
    requests = []
    with provider_client([bad, gap], requests) as sdk:
        result = run(LLMRouter(sdk), max_supplements=3)
    assert len(requests) == 2
    assert result.valid and not result.ready_for_patch and not result.requires_supplement
    assert result.diagnosis.needs_more_info


def test_schema_feedback_does_not_echo_invalid_input_or_extra_field_text():
    bad = payload()
    bad["plan"][0]["expected_saving_gb"] = "canary-sensitive-value"
    bad["canary-sensitive-field"] = "canary-sensitive-value"
    requests = []
    with provider_client([bad, payload()], requests) as sdk:
        result = run(LLMRouter(sdk))
    assert result.ready_for_patch and len(requests) == 2
    feedback = requests[1]["messages"][-1]["content"]
    assert "canary" not in feedback
    assert "/plan/0/expected_saving_gb" in feedback
    assert "JSON_SCHEMA_MISMATCH" in feedback and "INVALID_SCHEMA" in feedback


@pytest.mark.parametrize("reason", ["filtered", "unknown"])
def test_filtered_or_unknown_provider_failure_does_not_enter_repair_loop(reason):
    class Router:
        calls = 0

        def chat(self, *args, **kwargs):
            self.calls += 1
            raise ResponseValidationError(
                "rejected", reason=reason, response=SimpleNamespace(text="{}")
            )

    router = Router()
    with pytest.raises(ResponseValidationError):
        run(router, max_supplements=3)
    assert router.calls == 1


def test_large_error_feedback_is_bounded_and_explicit_about_omissions():
    bad = payload()
    bad["plan"] = [
        dict(bad["plan"][0], title="Reduce sequence length", fix_id=f"f{i}") for i in range(200)
    ]
    result = validate_diagnosis(bad, evidence=evidence(), policy={})
    assert not result.valid and result.requires_supplement
    assert len(result.supplement_request.encode()) < 16 * 1024
    data = json.loads(result.supplement_request.split("Errors: ", 1)[1])
    assert data["omitted_items"] > 0
    assert all(item["path"].startswith("/plan/") for item in data["issues"])


@pytest.mark.parametrize("limit", [0, 1])
def test_persistent_schema_error_keeps_failed_response_boundary_and_shared_cap(limit):
    bad = payload()
    bad["invocation_refs"] = ["execution_argv[0]"]
    bad["plan"][0]["title"] = "Reduce sequence length"
    requests = []
    with provider_client([bad], requests) as sdk:
        with pytest.raises(ResponseValidationError) as failure:
            run(LLMRouter(sdk), max_supplements=limit)
        assert len(sdk.ledger.entries) == limit + 1
        assert failure.value.reason == "schema_mismatch"
        assert failure.value.response.text == json.dumps(bad)
    assert len(requests) == limit + 1
    if limit:
        feedback = requests[1]["messages"][-1]["content"]
        for code in (
            "JSON_SCHEMA_MISMATCH",
            "UNKNOWN_INVOCATION_REFERENCE",
            "MODEL_CHANGE_FORBIDDEN",
        ):
            assert code in feedback


@pytest.mark.parametrize("name", ["diagnose.md", "patch.md"])
def test_prompt_preserves_parameter_updates_independent_of_eval_labels(name):
    from headroom.diagnose import PROMPT_PATH

    prompt = (PROMPT_PATH.parent / name).read_text()
    for contract in (
        "module.eval() changes module behavior; it does not disable gradient computation",
        'A filename, comment or label saying "frozen" is not',
        "existing requires_grad",
        "parameters actually updated by the optimizer",
        "request explicitly authorizes that objective",
        "head-only optimization",
        "Precision permission alone does not authorize dropping parameter",
        "accumulation or global-gradient dependencies",
    ):
        assert contract in prompt
    assert "optimizer_step_in_backward_tutorial" not in prompt
    assert "headroom.optim" not in prompt
