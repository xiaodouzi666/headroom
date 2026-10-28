"""Offline strategy prompts and unchanged policy gates; no model, GPU or network calls."""

import dataclasses
import json
import re
import socket

import httpx
import pytest

from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.diagnose import PROMPT_PATH, build_diagnosis_messages, validate_diagnosis
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter
from headroom.patch import PatchEngine


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Only the in-process MockTransport is permitted")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def strategy_section(prompt):
    marker = "Evidence-guided strategy hints:"
    assert prompt.count(marker) == 1
    return prompt.split(marker, 1)[1].split("\n\n", 2)[:2]


@pytest.mark.parametrize("name", ["diagnose.md", "patch.md", "patch_fix.md"])
def test_strategy_instructions_keep_permission_weighting_and_reference_boundaries(name):
    prompt = (PROMPT_PATH.parent / name).read_text()
    activation, temporaries = (" ".join(part.split()) for part in strategy_section(prompt))
    for required in (
        "activations peak, first consider",
        "only when allow_batch_grad_accum=true",
        "neither allow_batch_change nor allow_grad_accum is false",
        "do not propose this strategy, even as an optional fallback",
        "micro_batch * accum_steps = original effective batch for that replica",
        "distributed factor and global effective batch unchanged",
        "loss / K only for equal-weight K chunks",
        "gradient reset, clipping, optimizer and scheduler",
        "priority cannot override",
    ):
        assert required in activation
    for required in (
        "temporaries peak from full-vocabulary logits",
        "streams the producer/projection and loss over tokens",
        "retaining every chunk's autograd graph",
        "Every token must still see the full vocabulary",
        "independent softmax over vocabulary chunks changes the objective",
        "masks, class weights, ignore_index and label smoothing",
        "without removing it or changing computation/loss dtypes",
        "allow_numerics_change=true",
        "numerical_basis, reference, tolerance and loss checks",
        "Do not suppress, rescale or hide changed losses",
        "unverified until the existing real checks pass",
    ):
        assert required in temporaries
    assert not re.search(r"scenarios/|s[1-9]_|nanogpt|train\\.py", activation + temporaries)


def diagnosis_payload(title, description, permissions=()):
    return {
        "root_causes": [
            {
                "id": "c1",
                "title": "Measured activation working set",
                "category": "activations",
                "bytes_gb": 4.0,
                "evidence_refs": ["stk_actual"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "p1",
                "type": "code",
                "title": title,
                "description": description,
                "expected_saving_gb": 2.0,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Unverified hypothesis; source prerequisites and real checks still apply.",
                "requires_policy": list(permissions),
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Synthetic contract test, never a measured repair."],
    }


@pytest.mark.parametrize(
    "permission,allowed",
    [
        ({}, False),
        ({"allow_batch_grad_accum": None}, False),
        ({"allow_batch_grad_accum": False}, False),
        ({"allow_batch_grad_accum": True, "allow_batch_change": False}, False),
        ({"allow_batch_grad_accum": True, "allow_grad_accum": False}, False),
        ({"allow_batch_grad_accum": True}, True),
    ],
)
def test_accumulation_hint_does_not_authorize_a_forbidden_strategy(permission, allowed):
    policy = {"allow_numerics_change": False, **permission}
    messages = build_diagnosis_messages(
        "Observed runtime stack: stk_actual",
        goal="fit:22GB",
        policy=policy,
        required_saving_gb=1.0,
    )
    assert strategy_section(messages[0]["content"])
    assert json.loads(messages[1]["content"])["policy"] == policy
    payload = diagnosis_payload(
        "Reduce microbatch with gradient accumulation",
        "Preserve effective batch and the original weighted loss and update boundary.",
        ["allow_batch_grad_accum"],
    )
    result = validate_diagnosis(
        payload,
        evidence={"stack_catalog": {"stk_actual": []}},
        policy=policy,
        required_saving_gb=1.0,
    )
    assert result.ready_for_patch is allowed
    if not allowed:
        assert "BATCH_CHANGE_FORBIDDEN" in {issue.code for issue in result.issues}
    assert result.diagnosis.verification.max_steps == 20
    assert result.diagnosis.verification.compare_loss is True
    assert result.diagnosis.verification.tolerance == 0.001


@pytest.mark.parametrize(
    "description,permitted",
    [
        ("Stream projection and cross-entropy over tokens in the original FP32 dtype.", True),
        ("Use bf16 autocast for cross-entropy to avoid FP32 logits.", False),
    ],
)
def test_chunked_loss_hint_is_not_permission_to_change_precision(description, permitted):
    payload = diagnosis_payload("Bound temporary logits lifetime", description)
    payload["root_causes"][0]["category"] = "temporaries"
    result = validate_diagnosis(
        payload,
        evidence={"stack_catalog": {"stk_actual": []}},
        policy={"allow_numerics_change": False, "allow_batch_grad_accum": False},
        required_saving_gb=1.0,
    )
    assert result.ready_for_patch is permitted
    if not permitted:
        assert "NUMERICS_CHANGE_FORBIDDEN" in {issue.code for issue in result.issues}


def test_initial_and_repair_patch_requests_both_receive_strategy_constraints(tmp_path):
    requests = []

    def reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "offline-strategy-contract",
                "object": "chat.completion",
                "created": 0,
                "model": SUPER_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {"edits": [], "env_changes": {}, "cli_changes": [], "notes": []}
                            ),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
            },
        )

    models = candidate_models()
    models["super"] = dataclasses.replace(
        models["super"],
        capabilities=VerifiedCapabilities(
            reasoning_method="chat_template_kwargs", evidence="offline test fixture"
        ),
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "program.py").write_text("value = 1\n")
    with TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(reply)
    ) as client:
        result = PatchEngine(LLMRouter(client), max_repairs=1).generate_and_apply(
            source,
            {"fix_id": "p1", "type": "code"},
            work_root=tmp_path / "work",
            policy={"allow_batch_grad_accum": False, "allow_numerics_change": False},
        )
    assert not result.applied
    assert len(requests) == 2
    for request, name in zip(requests, ["patch.md", "patch_fix.md"], strict=True):
        prompt = (PROMPT_PATH.parent / name).read_text()
        strategy_messages = [
            message
            for message in request["messages"]
            if message["role"] == "system"
            and "Evidence-guided strategy hints:" in message["content"]
        ]
        assert len(strategy_messages) == 1
        assert strategy_messages[0]["content"] == prompt
        assert strategy_section(prompt)
        user_message = next(message for message in request["messages"] if message["role"] == "user")
        actual_policy = json.loads(user_message["content"])["policy"]
        assert actual_policy["allow_batch_grad_accum"] is False
        assert actual_policy["allow_numerics_change"] is False
        assert request["max_tokens"] == 4000
