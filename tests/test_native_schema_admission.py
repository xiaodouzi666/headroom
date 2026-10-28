"""Opt-in native-schema estimates only; synthetic requests and no external network."""

import copy
import json
import socket
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from test_runtime_budget import fixture_completion, fixture_runtime

from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.config import candidate_models
from headroom.llm.admission import LocalEstimateAdmission, NativeSchemaEstimateAdmission
from headroom.llm.cost import Pricing
from headroom.llm.preflight import ASSET_HASHES, MODEL_ID, TOKENIZER_REVISION, PromptAuditor
from headroom.runtime import LiveProfile, RuntimeNotReady, build_live_runtime
from headroom.store.db import Store

ASSETS = (
    Path(__file__).resolve().parents[1] / ".cache/tokenizers/nemotron-3-ultra" / TOKENIZER_REVISION
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Native admission tests may not use DNS or sockets")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr("headroom.runtime.read_nebius_key", lambda path: "offline-placeholder")


@pytest.fixture(scope="module")
def auditor():
    if not all((ASSETS / name).is_file() for name in ASSET_HASHES):
        pytest.skip("Pinned assets absent; never download them")
    return PromptAuditor(ASSETS)


def policy(**changes):
    return NativeSchemaEstimateAdmission.model_validate(
        {
            "mode": "local_estimate",
            "estimate_protocol": "ultra_native_schema_v1",
            "tokenizer_assets_dir": str(ASSETS),
            "token_multiplier": "2",
            "additive_tokens": 1024,
            "max_prompt_utf8_bytes": 300000,
            "min_local_template_tokens": 1,
            "max_local_template_tokens": 100000,
            "max_response_format_utf8_bytes": 8000,
            "max_completion_tokens": 2000,
            "output_cap_field": "max_completion_tokens",
            "output_cap_includes_reasoning": True,
            "output_cap_verified": True,
            "output_cap_evidence": "offline fixture; not provider certification",
            "risk_acknowledged": True,
            "evidence": "offline fixture only; not funding authorization",
            "calibration_evidence": "synthetic fixture; no empirical match claimed",
            **changes,
        }
    )


def spec():
    return replace(
        candidate_models()["ultra"],
        output_cap_field="max_completion_tokens",
        evidence="offline cap fixture",
        pricing=Pricing("1", "3", "0.12", verified=True, source="offline fixture"),
    )


def body():
    return {
        "model": MODEL_ID,
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Measured snapshot fixture."},
        ],
        "max_completion_tokens": 2000,
        "timeout": 600,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "headroom_response",
                "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            },
        },
    }


def test_whole_native_domain_is_added_with_margin_and_preserved_as_estimate(auditor):
    source = body()
    before = copy.deepcopy(source)
    price, record = policy().decide(spec(), source, auditor)
    audit = auditor.audit(source)
    native = audit["request_fields"]["response_format"]["serialized_json_local_tokens_estimate"]
    base = audit["local_template"]["tokens"]
    estimated = (base + native) * 2 + 1024
    assert native > audit["extra_schema"]["serialized_json_local_tokens_estimate"] > 0
    assert record["native_response_format_local_tokens"] == native
    assert record["estimated_prompt_tokens_with_margin"] == estimated
    assert price == (Decimal(estimated) + Decimal(2000) * 3) / 1_000_000
    assert record["provider_cost_upper_usd"] is None
    assert record["provider_prompt_token_ceiling"] is None
    assert record["admission_kind"] == "local_estimate"
    assert record["estimate_protocol"] == "ultra_native_schema_v1"
    assert source == before


def test_schema_growth_changes_reservation_even_with_same_messages(auditor):
    original = body()
    larger = copy.deepcopy(original)
    larger["response_format"]["json_schema"]["schema"]["description"] = (
        "additional schema text " * 40
    )
    low, _ = policy().decide(spec(), original, auditor)
    high, meta = policy().decide(spec(), larger, auditor)
    assert high > low
    assert meta["native_response_format_utf8_bytes"] > len(json.dumps(original["response_format"]))


@pytest.mark.parametrize(
    "changes",
    [
        {"estimate_protocol": None},
        {"estimate_protocol": "unreviewed"},
        {"token_multiplier": "1"},
        {"additive_tokens": 0},
        {"risk_acknowledged": False},
        {"max_completion_tokens": 2001},
        {"min_local_template_tokens": 200, "max_local_template_tokens": 100},
        {"max_response_format_utf8_bytes": 0},
        {"calibration_evidence": ""},
    ],
)
def test_explicit_version_and_all_existing_risk_controls_are_required(changes):
    with pytest.raises((ValidationError, ValueError)):
        policy(**changes)


def test_missing_protocol_cannot_select_extension_or_relax_old_policy(auditor):
    dumped = policy().model_dump()
    dumped.pop("estimate_protocol")
    with pytest.raises(ValidationError):
        NativeSchemaEstimateAdmission.model_validate(dumped)
    with pytest.raises(ValidationError):
        LocalEstimateAdmission.model_validate(policy().model_dump())
    old = LocalEstimateAdmission.model_validate(
        {
            key: value
            for key, value in policy().model_dump().items()
            if key
            not in {
                "estimate_protocol",
                "min_local_template_tokens",
                "max_local_template_tokens",
                "max_response_format_utf8_bytes",
                "calibration_evidence",
            }
        }
    )
    with pytest.raises(RuntimeNotReady, match="unmodeled"):
        old.decide(spec(), body(), auditor)


@pytest.mark.parametrize(
    "mutation",
    [
        "thinking",
        "thinking_missing",
        "strict",
        "name",
        "format",
        "format_missing",
        "temperature",
        "tools",
        "tool_choice",
        "token_budget",
        "duplicate_output",
        "oversize_output",
        "history_reasoning",
        "history_tool",
    ],
)
def test_unobserved_request_domains_fail_closed(auditor, mutation):
    request = body()
    if mutation == "thinking":
        request["extra_body"]["chat_template_kwargs"]["enable_thinking"] = True
    elif mutation == "thinking_missing":
        request.pop("extra_body")
    elif mutation == "strict":
        request["response_format"]["json_schema"]["strict"] = True
    elif mutation == "name":
        request["response_format"]["json_schema"]["name"] = "another"
    elif mutation == "format":
        request["response_format"] = {"type": "json_object"}
    elif mutation == "format_missing":
        request.pop("response_format")
    elif mutation == "temperature":
        request["temperature"] = 0.7
    elif mutation == "tools":
        request["tools"] = []
    elif mutation == "tool_choice":
        request["tool_choice"] = "none"
    elif mutation == "token_budget":
        request["extra_body"]["reasoning_budget"] = 10
    elif mutation == "duplicate_output":
        request["max_tokens"] = 2000
    elif mutation == "oversize_output":
        request["max_completion_tokens"] = 2001
    elif mutation == "history_reasoning":
        request["messages"].append(
            {"role": "assistant", "content": "old", "reasoning_content": "hidden"}
        )
    else:
        request["messages"].append({"role": "tool", "content": "old", "tool_call_id": "call"})
    with pytest.raises(RuntimeNotReady):
        policy().decide(spec(), request, auditor)


@pytest.mark.parametrize(
    "changes",
    [
        {"max_prompt_utf8_bytes": 1},
        {"max_response_format_utf8_bytes": 1},
        {"min_local_template_tokens": 99999},
        {"max_local_template_tokens": 1},
    ],
)
def test_explicit_size_and_token_domain_limits_fail_closed(auditor, changes):
    with pytest.raises(RuntimeNotReady, match="bounds"):
        policy(**changes).decide(spec(), body(), auditor)


def test_wrong_model_or_unknown_price_is_not_admitted(auditor):
    with pytest.raises(RuntimeNotReady, match="Ultra"):
        policy().decide(
            replace(spec(), model_id=candidate_models()["super"].model_id), body(), auditor
        )
    with pytest.raises(RuntimeNotReady, match="pricing"):
        policy().decide(replace(spec(), pricing=None), body(), auditor)


def test_profile_roundtrip_preserves_new_type_and_requires_strict_mode(tmp_path):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["ultra"].billing = policy()
    restored = LiveProfile.model_validate_json(profile.model_dump_json())
    assert type(restored.models["ultra"].billing) is NativeSchemaEstimateAdmission
    assert restored.models["super"].billing.mode == "verified_provider_bound"
    restored.runtime_config()
    restored.run_budget_mode = "actual_usage"
    with pytest.raises(RuntimeNotReady, match="provider bounds"):
        restored.runtime_config()


def test_native_sdk_request_reserves_then_settles_without_profile_activation(tmp_path):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["ultra"].billing = policy()
    profile.models["ultra"].capabilities = {
        "json_method": "json_schema",
        "reasoning_method": "chat_template_kwargs",
        "evidence": "offline capability fixture",
    }
    store = Store(tmp_path / "store.db")
    store.create_run("fixture")
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit="1", total_limit="1")
    budget.open_run("fixture", "0.6")
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        assert budget.snapshot("fixture")["pending_attempts"] == 1
        result = fixture_completion(request)
        data = json.loads(result.content)
        data["choices"][0]["message"]["content"] = '{"ok": true}'
        return httpx.Response(200, json=data)

    bundle = build_live_runtime(
        "fixture",
        profile=profile,
        budget=budget,
        store=store,
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    try:
        bundle.router.chat(
            "diagnose",
            [{"role": "user", "content": "fixture"}],
            {"type": "object"},
            reasoning=False,
            max_tokens=2000,
        )
        assert len(seen) == 1
        assert seen[0]["response_format"]["type"] == "json_schema"
        assert seen[0]["max_completion_tokens"] == 2000
        rows = store.llm_calls("fixture")
        assert rows[0]["estimate_protocol"] == "ultra_native_schema_v1"
        assert rows[0]["native_response_format_local_tokens"] > 0
        assert rows[0]["provider_cost_upper_usd"] is None
        assert rows[0]["settled"] is True
    finally:
        bundle.close()
        store.close()


def test_ledger_still_rejects_estimates_in_actual_usage_mode(tmp_path):
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit="1", total_limit="1")
    budget.open_run("fixture", "0.6", budget_mode="actual_usage")
    with pytest.raises(BudgetExceeded):
        budget.reserve("fixture", "attempt", "0.01", admission_kind="local_estimate")
