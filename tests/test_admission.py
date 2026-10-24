"""Real pinned CPU tokenizer + final SDK requests, with independent network refusal."""

import copy
import json
import socket
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from test_runtime_budget import fixture_completion, fixture_runtime

from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.diagnose import build_diagnosis_messages
from headroom.llm.admission import LocalEstimateAdmission
from headroom.llm.preflight import ASSET_HASHES, TOKENIZER_REVISION, PromptAuditor
from headroom.runtime import LiveProfile, RuntimeNotReady, build_live_runtime
from headroom.store.db import Store

ASSETS = (
    Path(__file__).resolve().parents[1] / ".cache/tokenizers/nemotron-3-ultra" / TOKENIZER_REVISION
)


@pytest.fixture(autouse=True)
def deny_network_and_real_credentials(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("Network is forbidden in admission tests")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, refused)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, refused)
    # Runtime tests only use this explicit offline placeholder; no dotenv is read.
    monkeypatch.setattr("headroom.runtime.read_nebius_key", lambda path: "offline-placeholder")


@pytest.fixture
def auditor():
    if not all((ASSETS / name).is_file() for name in ASSET_HASHES):
        pytest.skip("Pinned tokenizer assets are absent; this test never downloads them")
    return PromptAuditor(ASSETS)


def policy(**changes):
    return LocalEstimateAdmission.model_validate(
        {
            "mode": "local_estimate",
            "tokenizer_assets_dir": str(ASSETS),
            "token_multiplier": "2",
            "additive_tokens": 1024,
            "max_prompt_utf8_bytes": 1_000_000,
            "max_completion_tokens": 4000,
            "output_cap_field": "max_completion_tokens",
            "output_cap_includes_reasoning": True,
            "output_cap_verified": True,
            "output_cap_evidence": "offline fixture only",
            "risk_acknowledged": True,
            "evidence": "offline fixture policy, not authorization",
            **changes,
        }
    )


def runtime(tmp_path, handler, *, capabilities=None):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["ultra"].billing = policy()
    if capabilities is not None:
        profile.models["ultra"].capabilities = capabilities
    store = Store(tmp_path / "store.db")
    store.create_run("run")
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit="1", total_limit="1")
    budget.open_run("run", "0.6")
    bundle = build_live_runtime(
        "run", profile=profile, budget=budget, store=store, transport=httpx.MockTransport(handler)
    )
    bundle.client._sleep = lambda _: None
    return profile, bundle, budget, store


@pytest.mark.parametrize(
    "change",
    [
        {"mode": "verified_provider_bound"},
        {"mode": None},
        {"token_multiplier": "1"},
        {"token_multiplier": "NaN"},
        {"token_multiplier": 2.0},
        {"additive_tokens": 0},
        {"additive_tokens": True},
        {"risk_acknowledged": False},
        {"risk_acknowledged": 1},
        {"tokenizer_assets_dir": "relative/path"},
    ],
)
def test_estimate_requires_explicit_valid_policy(change):
    with pytest.raises((ValidationError, ValueError, TypeError)):
        policy(**change)


def test_legacy_mode_and_authorization_are_not_changed(tmp_path):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    assert all(p.billing.mode == "verified_provider_bound" for p in profile.models.values())
    profile.models["ultra"].billing = policy()
    restored = LiveProfile.model_validate_json(profile.model_dump_json())
    assert isinstance(restored.models["ultra"].billing, LocalEstimateAdmission)
    assert restored.models["super"].billing.mode == "verified_provider_bound"
    missing_mode = policy().model_dump()
    missing_mode.pop("mode")
    with pytest.raises(ValidationError):
        LocalEstimateAdmission.model_validate(missing_mode)
    for flags in (
        {"live_enabled": False},
        {"credit_confirmed": False},
        {"authorized_total_usd": "2"},
    ):
        with pytest.raises(RuntimeNotReady):
            profile.model_copy(update=flags).runtime_config()
    profile.models["super"].billing = policy()
    with pytest.raises(RuntimeNotReady, match="Ultra"):
        profile.runtime_config()


def test_assets_never_download_and_special_files_are_refused(tmp_path):
    with pytest.raises(RuntimeNotReady, match="assets"):
        policy(tokenizer_assets_dir=str(tmp_path / "missing")).load_auditor()
    import os

    os.mkfifo(tmp_path / "tokenizer.json")
    with pytest.raises(RuntimeNotReady, match="assets"):
        policy(tokenizer_assets_dir=str(tmp_path)).load_auditor()
    (tmp_path / "tokenizer.json").unlink()
    for name in ASSET_HASHES:
        (tmp_path / name).write_text("tampered fixture")
    with pytest.raises(RuntimeNotReady, match="assets"):
        policy(tokenizer_assets_dir=str(tmp_path)).load_auditor()


def test_complete_diagnosis_payload_is_measured_and_actual_cost_separate(tmp_path, auditor):
    sent = []

    def respond(request):
        sent.append(json.loads(request.content))
        response = fixture_completion(request)
        data = json.loads(response.content)
        data["choices"][0]["message"]["content"] = '{"ok": true}'
        return httpx.Response(200, json=data)

    _, bundle, budget, store = runtime(tmp_path, respond)
    captured_sdk = []
    original = bundle.client._before_attempt

    def capture(role, spec, attempt, body):
        captured_sdk.append(copy.deepcopy(body))
        return original(role, spec, attempt, body)

    bundle.client._before_attempt = capture
    try:
        messages = build_diagnosis_messages(
            "显存证据 🧪\n# Stack fixture", goal="fix-oom", policy={}
        )
        bundle.router.chat(
            "diagnose",
            messages,
            {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            max_tokens=128,
        )
        row = store.llm_calls("run")[0]
        audit = auditor.audit(captured_sdk[0])
        assert {k: v for k, v in captured_sdk[0].items() if k != "timeout"} == sent[0]
        assert audit["local_template"] == auditor.audit(sent[0])["local_template"]
        assert row["request_input_form"] == "sdk_kwargs"
        assert len(sent[0]["messages"]) > len(messages)  # Router's full schema fallback counted.
        assert row["admission_kind"] == "local_estimate"
        assert row["provider_cost_upper_usd"] is None
        assert row["provider_prompt_token_ceiling"] is None
        assert row["request_sha256"] == audit["request"]["compact_json_sha256"]
        assert row["local_template_tokens"] == audit["local_template"]["tokens"]
        assert row["estimated_prompt_tokens_with_margin"] == 2 * row["local_template_tokens"] + 1024
        assert Decimal(row["reservation_usd"]) > Decimal(row["cost_usd"])
        assert store.usage("run")["total_cost_usd"] == "0.00005"
        assert store.usage("run")["admission_counts"] == {
            "verified_provider_bound": 0,
            "local_estimate": 1,
            "unknown": 0,
        }
        assert budget.snapshot("run")["contains_local_estimate"]
        assert not budget.snapshot("run")["dispatch_blocked"]
        assert "显存" not in json.dumps(row, ensure_ascii=False)
        assert str(ASSETS) not in json.dumps(row)
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize(
    "extra",
    [
        {"response_format": {"type": "json_object"}},
        {"extra_body": {"reasoning_budget": 10}},
        {"messages": [{"role": "tool", "content": "x", "tool_call_id": "opaque"}]},
        {
            "messages": [
                {"role": "user", "content": [{"type": "image_url", "image_url": "private"}]}
            ]
        },
        {"unknown_provider_field": "private"},
    ],
)
def test_unmodeled_domains_do_not_silently_become_zero(tmp_path, auditor, extra):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    body = {
        "model": profile.models["ultra"].model_id,
        "messages": [{"role": "user", "content": "fixture"}],
        "max_completion_tokens": 128,
    }
    body.update(copy.deepcopy(extra))
    profile.models["ultra"].billing = policy()
    with pytest.raises(RuntimeNotReady):
        policy().decide(profile.runtime_config().models["ultra"], body, auditor)


@pytest.mark.parametrize(
    "outcome", ["unknown", "over_estimate", "output_overrun", "429", "interrupt"]
)
def test_uncertain_or_overrun_attempt_blocks_all_later_calls(tmp_path, auditor, outcome):
    calls = []

    def respond(request):
        calls.append(request)
        if outcome == "interrupt":
            raise KeyboardInterrupt
        if outcome == "429":
            return httpx.Response(429, json={"error": {"message": "fixture"}})
        response = fixture_completion(
            request, output_tokens=129 if outcome == "output_overrun" else 20
        )
        data = json.loads(response.content)
        if outcome == "unknown":
            data.pop("usage")
        if outcome == "over_estimate":
            data["usage"] = {
                "prompt_tokens": 100000,
                "completion_tokens": 20,
                "total_tokens": 100020,
            }
        return httpx.Response(200, json=data)

    _, bundle, budget, store = runtime(tmp_path, respond)
    try:
        expected = KeyboardInterrupt if outcome == "interrupt" else BudgetExceeded
        with pytest.raises(expected):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}], max_tokens=128)
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("patch", [{"role": "user", "content": "fixture"}], max_tokens=128)
        assert len(calls) == 1
        snap = budget.snapshot("run")
        assert snap["dispatch_blocked"] and snap["halt_reason"]
        if outcome == "over_estimate":
            assert snap["known_charge_usd"] == "0.10004"
            assert snap["halt_reason"] == "estimate_reservation_exceeded"
        if outcome in {"unknown", "429", "interrupt"}:
            assert snap["total_actual_usd"] is None
            assert store.usage("run")["total_cost_usd"] is None
    finally:
        bundle.close()
        store.close()


def test_native_structured_output_is_not_silently_downgraded(tmp_path, auditor):
    calls = []
    _, bundle, budget, store = runtime(
        tmp_path,
        lambda request: calls.append(request),
        capabilities={"json_method": "json_schema", "evidence": "offline fixture"},
    )
    try:
        with pytest.raises(RuntimeNotReady, match="unmodeled"):
            bundle.router.chat(
                "diagnose",
                [{"role": "user", "content": "fixture"}],
                {"type": "object"},
                max_tokens=128,
            )
        assert calls == [] and store.llm_calls("run") == []
        assert budget.snapshot("run")["pending_attempts"] == 0
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize(
    "change",
    [
        {"output_cap_verified": False},
        {"output_cap_includes_reasoning": False},
        {"max_completion_tokens": 127},
        {"max_prompt_utf8_bytes": 1},
    ],
)
def test_estimate_does_not_bypass_cap_or_request_domain(tmp_path, auditor, change):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["ultra"].billing = policy(**change)
    body = {
        "model": profile.models["ultra"].model_id,
        "messages": [{"role": "user", "content": "fixture"}],
        "max_completion_tokens": 128,
    }
    with pytest.raises(RuntimeNotReady):
        profile.models["ultra"].billing.decide(
            profile.runtime_config().models["ultra"], body, auditor
        )
