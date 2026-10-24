"""Offline contract: a provider-shaped reply still needs real evidence validation."""

import json

import httpx
import pytest

from headroom.config import ULTRA_MODEL
from headroom.diagnose import build_diagnosis_messages, validate_diagnosis
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter
from headroom.schemas import Diagnosis


@pytest.mark.parametrize("reference,ready", [("stk_actual", True), ("stk_invented", False)])
def test_router_output_requires_runtime_evidence(reference, ready):
    payload = {
        "root_causes": [
            {
                "id": "c1",
                "title": "Activations",
                "category": "activations",
                "bytes_gb": 4.0,
                "evidence_refs": [reference],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "p1",
                "type": "code",
                "title": "Checkpoint block",
                "description": "Recompute block activations during backward.",
                "expected_saving_gb": 3.0,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Recomputation overhead",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": False,
        "notes": ["Synthetic test reply, not a GPU measurement."],
    }
    requests = []

    def provider_reply(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "offline-diagnosis",
                "object": "chat.completion",
                "created": 0,
                "model": ULTRA_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
            },
        )

    policy = {"allow_numerics_change": False, "allow_batch_grad_accum": False}
    messages = build_diagnosis_messages(
        "Observed runtime stack: stk_actual",
        goal="fit:22GB",
        policy=policy,
        required_saving_gb=2.0,
    )
    with TokenFactoryClient(transport=httpx.MockTransport(provider_reply)) as client:
        reply = LLMRouter(client).chat("diagnose", messages, Diagnosis)
        verdict = validate_diagnosis(
            reply.parsed,
            evidence={"stack_catalog": {"stk_actual": []}},
            policy=policy,
            required_saving_gb=2.0,
        )
        assert len(client.ledger.entries) == 1
        assert reply.cost.usd is None  # Offline fixture supplies no verified prices.
    assert len(requests) == 1
    assert requests[0]["model"] == ULTRA_MODEL
    assert verdict.ready_for_patch is ready
    if not ready:
        assert [issue.code for issue in verdict.issues] == ["UNKNOWN_STACK_REFERENCE"]


def test_prompt_defines_generic_categories_post_step_and_fixed_verification():
    from headroom.diagnose import PROMPT_PATH

    prompt = PROMPT_PATH.read_text()
    for category in (
        "params",
        "grads",
        "optimizer_state",
        "activations",
        "temporaries",
        "retained_graph",
        "cache",
        "fragmentation_candidate",
        "unknown",
    ):
        assert f"- {category}:" in prompt
    assert "origin heuristics, not causal ground truth" in prompt
    assert "post-step observations" in prompt
    assert "before" in prompt and "completion marker" in prompt
    assert '{"max_steps": 20, "compare_loss": true, "tolerance": 0.001}' in prompt
    assert "selected by the host" in prompt
    assert not any(f"s{number}_" in prompt for number in range(1, 9))
