"""Offline request/settlement checks for reasoning within unchanged provider caps."""

import json
import socket
from decimal import Decimal

import httpx
import pytest

from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.config import candidate_models
from headroom.runtime import LiveProfile, build_live_runtime
from headroom.store.db import Store

# Public reviewed limits and prices are test data; no live profile or DB is read.
CASES = [
    ("diagnose", "ultra", 8192, "1.073152", "0.0016"),
    ("patcher", "super", 4000, "0.0822432", "0.00048"),
]
SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("Real network forbidden in reasoning budget tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def offline_runtime(tmp_path, handler, *, pool="9.99964904", run_limit="0.6"):
    models = {}
    for role, spec in candidate_models().items():
        ultra = role == "ultra"
        models[role] = {
            "model_id": spec.model_id,
            "input_usd_per_million": "1" if ultra else "0.3",
            "output_usd_per_million": "3" if ultra else "0.9",
            "cached_input_usd_per_million": "0.12" if ultra else "0.06",
            "evidence": "Offline public tariff fixture, not a live authorization",
            "capabilities": {
                "json_method": "json_schema",
                "reasoning_method": "chat_template_kwargs",
                "evidence": "Offline transport fixture only",
            },
            "billing": {
                "prompt_token_ceiling": 1048576 if ultra else 262144,
                "max_prompt_utf8_bytes": 8000000,
                "max_completion_tokens": 8192,
                "output_cap_field": "max_completion_tokens",
                "output_cap_includes_reasoning": True,
                "verified": True,
                "evidence": "Offline provider-bound fixture only",
            },
        }
    profile = LiveProfile.model_validate(
        {
            "live_enabled": True,
            "credit_confirmed": True,
            "available_credit_usd": pool,
            "authorized_total_usd": pool,
            "verified_at": "offline-fixture",
            "evidence": "Offline fixture, never authorizes a live request",
            "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
            "evidence_token_budget": 1000,
            "run_budget_mode": "actual_usage",
            "models": models,
        }
    )
    env = tmp_path / ".env"
    env.write_text("NEBIUS_API_KEY=offline-placeholder\n")
    env.chmod(0o600)
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit=pool, total_limit=pool)
    budget.open_run("run", run_limit, budget_mode="actual_usage")
    store = Store(tmp_path / "store.db")
    store.create_run("run")
    bundle = build_live_runtime(
        "run",
        profile=profile,
        budget=budget,
        store=store,
        env_file=env,
        transport=httpx.MockTransport(handler),
    )
    return bundle, budget, store


@pytest.mark.parametrize("role,model_role,cap,full_bound,actual_cost", CASES)
def test_reasoning_reserves_full_request_and_bills_all_completion_tokens(
    tmp_path, role, model_role, cap, full_bound, actual_cost
):
    calls = []
    expected_model = candidate_models()[model_role].model_id

    def respond(request):
        sent = json.loads(request.content)
        calls.append(sent)
        # Reservation is already durable before the transport can send any bytes.
        snapshot = budget.snapshot("run")
        assert snapshot["pending_attempts"] == 1
        assert Decimal(snapshot["reserved_or_actual_usd"]) == Decimal(full_bound)
        pending = store.llm_calls("run")[0]
        assert Decimal(pending["reservation_usd"]) == Decimal(full_bound)
        assert sent["model"] == expected_model
        assert sent["chat_template_kwargs"] == {"enable_thinking": True}
        assert sent["response_format"]["type"] == "json_schema"
        assert sent["max_completion_tokens"] == cap and "max_tokens" not in sent
        assert "reasoning_budget" not in sent and "max_thinking_tokens" not in sent
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "created": 0,
                "object": "chat.completion",
                "model": expected_model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": '{"ok": true}',
                            "reasoning_content": "PRIVATE_REASONING_NOT_FOR_ARTIFACTS",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 500,
                    "total_tokens": 600,
                    "prompt_tokens_details": {"cached_tokens": 0},
                    "completion_tokens_details": {"reasoning_tokens": 490},
                },
            },
        )

    bundle, budget, store = offline_runtime(tmp_path, respond)
    try:
        result = bundle.router.chat(
            role,
            [{"role": "user", "content": "Offline fixture"}],
            SCHEMA,
            max_tokens=cap,
            reasoning=True,
        )
        assert len(calls) == 1 and result.parsed == {"ok": True}
        assert result.usage.reasoning_tokens == 490
        assert result.usage.completion_tokens == 500
        snapshot = budget.close_run("run")
        assert snapshot["billing_complete"] and snapshot["pending_attempts"] == 0
        assert Decimal(snapshot["total_actual_usd"]) == Decimal(actual_cost)
        assert snapshot["halt_reason"] is None
        rows = store.llm_calls("run")
        assert len(rows) == 1 and rows[0]["settled"]
        assert Decimal(rows[0]["cost_usd"]) == Decimal(actual_cost)
        assert "PRIVATE_REASONING_NOT_FOR_ARTIFACTS" not in json.dumps(rows)
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize("role,model_role,cap,full_bound,actual_cost", CASES)
def test_reasoning_cannot_dispatch_if_shared_pool_cannot_fund_full_bound(
    tmp_path, role, model_role, cap, full_bound, actual_cost
):
    calls = []
    pool = str(Decimal(full_bound) - Decimal("0.000000001"))
    bundle, budget, store = offline_runtime(
        tmp_path, lambda request: calls.append(request), pool=pool, run_limit="0.01"
    )
    try:
        with pytest.raises(BudgetExceeded, match="pool"):
            bundle.router.chat(
                role,
                [{"role": "user", "content": "Tiny prompt"}],
                SCHEMA,
                max_tokens=cap,
                reasoning=True,
            )
        assert calls == [] and store.llm_calls("run") == []
        assert budget.snapshot("run")["pending_attempts"] == 0
    finally:
        bundle.close()
        store.close()
