import json

import httpx
import pytest

from headroom.budget import BudgetExceeded, BudgetLedger
from headroom.config import candidate_models
from headroom.runtime import LiveProfile, RuntimeNotReady, build_live_runtime, read_live_profile
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Real network forbidden in runtime budget tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def fixture_runtime(
    tmp_path, handler, limit="0.05", prompt_ceiling=30000, profile_only=False, cap_fields=None
):
    env = tmp_path / ".env"
    env.write_text("NEBIUS_API_KEY=offline-placeholder\n")
    env.chmod(0o600)
    profile = LiveProfile.model_validate(
        {
            "live_enabled": True,
            "credit_confirmed": True,
            "available_credit_usd": "1",
            "authorized_total_usd": "1",
            "verified_at": "offline-fixture",
            "evidence": "offline-fixture",
            "base_url": "https://api.tokenfactory.us-central1.nebius.com/v1/",
            "evidence_token_budget": 1000,
            "models": {
                role: {
                    "model_id": model.model_id,
                    "input_usd_per_million": "1",
                    "output_usd_per_million": "2",
                    "evidence": "offline fixture, not provider pricing",
                    "billing": {
                        "prompt_token_ceiling": prompt_ceiling,
                        "max_prompt_utf8_bytes": 100000,
                        "max_completion_tokens": 4000,
                        "output_cap_field": (cap_fields or {}).get(role, "max_tokens"),
                        "output_cap_includes_reasoning": True,
                        "verified": True,
                        "evidence": "offline fixture only",
                    },
                }
                for role, model in candidate_models().items()
            },
        }
    )
    if profile_only:
        return profile
    store = Store(tmp_path / "store.db")
    store.create_run("run")
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit="1", total_limit="1")
    budget.open_run("run", limit)
    bundle = build_live_runtime(
        "run",
        profile=profile,
        budget=budget,
        store=store,
        env_file=env,
        transport=httpx.MockTransport(handler),
    )
    bundle.client._sleep = lambda _: None
    return bundle, budget, store


def test_retry_is_blocked_before_a_second_billable_attempt(tmp_path):
    calls = []

    def rate_limit(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "fixture"}})

    bundle, budget, store = fixture_runtime(tmp_path, rate_limit)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "test"}])
        assert len(calls) == 1
        assert store.usage("run")["unknown_cost_calls"] == 1
        assert store.usage("run")["total_cost_usd"] is None
        assert store.llm_calls("run")[0]["settled"] is True
        assert budget.snapshot("run")["conservative_charge_usd"] == "0.038"
    finally:
        bundle.close()
        store.close()


def test_interrupted_attempt_keeps_unknown_cost_and_is_not_retried(tmp_path):
    def interrupted(request):
        raise KeyboardInterrupt

    bundle, budget, store = fixture_runtime(tmp_path, interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):
            bundle.router.chat("diagnose", [{"role": "user", "content": "test"}])
        rows = store.llm_calls("run")
        assert len(rows) == 1 and rows[0]["outcome"] == "interrupted" and rows[0]["settled"]
        assert store.usage("run")["total_cost_usd"] is None
        assert budget.snapshot("run")["unknown_attempts"] == 1
    finally:
        bundle.close()
        store.close()


def test_model_identity_failure_halts_budget_with_unknown_bill(tmp_path):
    def wrong_model(request):
        return httpx.Response(
            200,
            json={
                "id": "fake",
                "created": 0,
                "object": "chat.completion",
                "model": "nvidia/wrong-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            },
        )

    bundle, budget, store = fixture_runtime(tmp_path, wrong_model)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "test"}])
        assert budget.snapshot("run")["billing_bound_unresolved"]
        assert store.usage("run")["total_cost_usd"] is None
    finally:
        bundle.close()
        store.close()


def test_small_budget_rejects_first_attempt_without_network_or_pending_row(tmp_path):
    calls = []
    bundle, budget, store = fixture_runtime(tmp_path, lambda req: calls.append(req), limit="0.01")
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "test"}])
        assert calls == [] and store.llm_calls("run") == []
        assert budget.snapshot("run")["unknown_attempts"] == 0
    finally:
        bundle.close()
        store.close()


def test_invalid_profile_error_does_not_echo_embedded_values(tmp_path):
    profile = tmp_path / "bad.json"
    profile.write_text(json.dumps({"secret": "private-canary-value"}))
    with pytest.raises(RuntimeNotReady) as error:
        read_live_profile(profile)
    assert "private-canary-value" not in str(error.value)


def test_nano_attempts_share_two_cent_sub_budget(tmp_path):
    calls = []

    def limited(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "offline fixture"}})

    bundle, budget, store = fixture_runtime(tmp_path, limited, limit="0.1", prompt_ceiling=1000)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("annotate", [{"role": "user", "content": "stack"}])
        assert len(calls) == 1
        assert store.usage("run")["unknown_cost_calls"] == 1
        assert budget.snapshot("run")["conservative_charge_usd"] == "0.009"
        assert budget.snapshot("run")["halt_reason"] == "provider_charge_unknown"
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize(
    "flags",
    [
        {"live_enabled": False},
        {"credit_confirmed": False},
        {"authorized_total_usd": "2"},
    ],
)
def test_direct_runtime_profile_cannot_bypass_confirmation(tmp_path, flags):
    profile = fixture_runtime(tmp_path, None, profile_only=True).model_copy(update=flags)
    with pytest.raises(RuntimeNotReady):
        # Fails before reading this deliberately absent private file.
        build_live_runtime(
            "run",
            profile=profile,
            budget=None,
            store=None,
            env_file=tmp_path / "absent-private.env",
        )


def test_duplicate_model_ids_fail_before_selecting_wrong_billing_role(tmp_path):
    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["nano"].model_id = profile.models["ultra"].model_id
    with pytest.raises(RuntimeNotReady, match="distinct"):
        profile.runtime_config()


def test_cached_price_above_standard_price_is_reserved_at_worst_case(tmp_path):
    from decimal import Decimal

    profile = fixture_runtime(tmp_path, None, profile_only=True)
    profile.models["nano"].cached_input_usd_per_million = "4"
    config = profile.runtime_config()
    upper = profile.models["nano"].billing.upper_usd(
        config.models["nano"],
        {
            "messages": [{"role": "user", "content": "fixture"}],
            "max_tokens": 1000,
        },
    )
    assert upper == Decimal("0.122")


def test_provider_cap_violation_halts_even_if_total_cost_is_below_reservation(tmp_path):
    def exceeded(request):
        return httpx.Response(
            200,
            json={
                "id": "fake",
                "created": 0,
                "object": "chat.completion",
                "model": candidate_models()["ultra"].model_id,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "{}"},
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 4001, "total_tokens": 4001},
            },
        )

    bundle, budget, store = fixture_runtime(tmp_path, exceeded)
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}])
        assert budget.snapshot("run")["billing_bound_unresolved"]
        assert len(store.llm_calls("run")) == 1
    finally:
        bundle.close()
        store.close()


def fixture_completion(request, *, output_tokens=20):
    return httpx.Response(
        200,
        json={
            "id": "fake",
            "created": 0,
            "object": "chat.completion",
            "model": json.loads(request.content)["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ok"},
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": output_tokens,
                "total_tokens": 10 + output_tokens,
                "completion_tokens_details": {"reasoning_tokens": output_tokens - 1},
            },
        },
    )


def test_profile_cap_selection_reaches_sdk_and_durable_budget_for_each_model(tmp_path):
    from decimal import Decimal

    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return fixture_completion(request)

    bundle, budget, store = fixture_runtime(
        tmp_path, respond, prompt_ceiling=1000, cap_fields={"super": "max_completion_tokens"}
    )
    try:
        for role in ("patch", "annotate"):
            result = bundle.router.chat(
                role, [{"role": "user", "content": "fixture"}], max_tokens=128
            )
            assert result.cost.usd == Decimal("0.00005")
        assert calls[0]["max_completion_tokens"] == 128
        assert "max_tokens" not in calls[0]
        assert calls[1]["max_tokens"] == 128
        assert "max_completion_tokens" not in calls[1]
        rows = store.llm_calls("run")
        assert [row["output_cap_field"] for row in rows] == [
            "max_completion_tokens",
            "max_tokens",
        ]
        assert all(row["output_cap_tokens"] == 128 for row in rows)
        assert all(row["reservation_usd"] == "0.001256" for row in rows)
        assert Decimal(budget.snapshot("run")["conservative_charge_usd"]) == Decimal("0.0001")
        assert not budget.snapshot("run")["billing_bound_unresolved"]
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize("field", ["max_tokens", "max_completion_tokens"])
def test_actual_output_is_checked_against_selected_request_cap(tmp_path, field):
    calls = []

    def exceeded(request):
        calls.append(request)
        return fixture_completion(request, output_tokens=129)

    bundle, budget, store = fixture_runtime(tmp_path, exceeded, cap_fields={"super": field})
    try:
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("patch", [{"role": "user", "content": "fixture"}], max_tokens=128)
        assert len(calls) == 1
        assert store.llm_calls("run")[0]["output_cap_tokens"] == 128
        assert budget.snapshot("run")["billing_bound_unresolved"]
        # Even a second request with a lower cap must stop before transport.
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("patch", [{"role": "user", "content": "fixture"}], max_tokens=16)
        assert len(calls) == 1
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"max_tokens": 128},
        {"max_tokens": 128, "max_completion_tokens": 128},
        {"max_completion_tokens": True},
        {"max_completion_tokens": 0},
        {"max_completion_tokens": 4001},
        {"max_completion_tokens": 128, "extra_body": {"max_tokens": 4096}},
        {"max_completion_tokens": 128, "extra_body": {"max_completion_tokens": 4096}},
    ],
)
def test_billing_rejects_ambiguous_or_out_of_range_output_fields(tmp_path, body):
    profile = fixture_runtime(
        tmp_path, None, profile_only=True, cap_fields={"super": "max_completion_tokens"}
    )
    spec = profile.runtime_config().models["super"]
    with pytest.raises(RuntimeNotReady):
        profile.models["super"].billing.upper_usd(spec, body)


def test_changed_billing_field_is_rejected_before_transport_and_reservation(tmp_path):
    calls = []
    bundle, budget, store = fixture_runtime(
        tmp_path,
        lambda request: calls.append(request),
        cap_fields={"super": "max_completion_tokens"},
    )
    # Independently replace the client selection; the billing profile still
    # requires max_completion_tokens. This cannot silently use max_tokens.
    from dataclasses import replace

    from headroom.config import RuntimeConfig

    models = dict(bundle.client.config.models)
    models["super"] = replace(models["super"], output_cap_field="max_tokens")
    bundle.client.config = RuntimeConfig(models=models, live_enabled=True)
    try:
        with pytest.raises(RuntimeNotReady, match="cap field"):
            bundle.router.chat("patch", [{"role": "user", "content": "fixture"}], max_tokens=128)
        assert calls == [] and store.llm_calls("run") == []
        assert budget.snapshot("run")["unknown_attempts"] == 0
    finally:
        bundle.close()
        store.close()


def test_legacy_profile_defaults_to_max_tokens_and_bad_field_is_invalid(tmp_path):
    from pydantic import ValidationError

    profile = fixture_runtime(tmp_path, None, profile_only=True)
    payload = profile.model_dump()
    for item in payload["models"].values():
        del item["billing"]["output_cap_field"]
    legacy = LiveProfile.model_validate(payload)
    assert all(
        spec.output_cap_field == "max_tokens" for spec in legacy.runtime_config().models.values()
    )
    payload["models"]["super"]["billing"]["output_cap_field"] = "max_output_tokens"
    with pytest.raises(ValidationError):
        LiveProfile.model_validate(payload)


def test_interruption_after_dispatch_mark_commit_preserves_original_and_unknown(
    tmp_path, monkeypatch
):
    calls = []
    bundle, budget, store = fixture_runtime(tmp_path, lambda req: calls.append(req))
    original = budget.mark_dispatched

    def interrupted(run_id, attempt_id):
        original(run_id, attempt_id)
        raise KeyboardInterrupt

    monkeypatch.setattr(budget, "mark_dispatched", interrupted)
    try:
        with pytest.raises(KeyboardInterrupt):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}])
        assert calls == []
        state = budget.snapshot("run")
        assert state["pending_attempts"] == 1 and state["total_actual_usd"] is None
        assert state["dispatch_blocked"]
    finally:
        bundle.close()
        store.close()


def test_store_failure_before_dispatch_can_release_but_not_after_response(tmp_path, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        return fixture_completion(request)

    bundle, budget, store = fixture_runtime(tmp_path, respond)
    original = store.add_llm_call

    def failed(*args, **kwargs):
        raise OSError("fixture persistence failure")

    monkeypatch.setattr(store, "add_llm_call", failed)
    try:
        with pytest.raises(OSError):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}])
        assert calls == [] and budget.snapshot("run")["total_actual_usd"] == "0"
        monkeypatch.setattr(store, "add_llm_call", original)
        monkeypatch.setattr(store, "update_llm_call", failed)
        with pytest.raises(OSError):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}])
        assert len(calls) == 1
        state = budget.snapshot("run")
        assert state["known_charge_usd"] == "0.00005"
        assert state["halt_reason"] == "local_accounting_incomplete"
        with pytest.raises(BudgetExceeded):
            bundle.router.chat("diagnose", [{"role": "user", "content": "fixture"}])
        assert len(calls) == 1
    finally:
        bundle.close()
        store.close()
