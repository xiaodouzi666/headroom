"""No network, credentials or GPU access: every transport/tokenizer is a local fake."""

import copy
import importlib.util
import json
import sys
import threading
from decimal import Decimal
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "headroom_model_probe", Path(__file__).parents[1] / "scripts/probe_models.py"
)
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


@pytest.fixture(autouse=True)
def block_real_network(monkeypatch):
    import socket

    def denied(*args, **kwargs):
        pytest.fail("Real network access is forbidden in model probe tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def classify_known(spec, observation, metadata):
    """Existing behavior fixtures explicitly identify their requested model."""
    return probe.classify(spec, {"response_model": spec.model, **observation}, metadata)


def price():
    return probe.Price(Decimal(1), Decimal(3), 1_000_000, "max_tokens")


def verified_prices():
    return {
        "verified": True,
        "verified_at": "2026-10-24",
        "source": "official account catalogue",
        "output_caps_include_reasoning": True,
        "models": {
            model: {
                "input_usd_per_million": "1",
                "output_usd_per_million": "3",
                "prompt_token_ceiling": 1_000_000,
                "output_cap_field": "max_tokens",
            }
            for model in probe.MODELS.values()
        },
    }


def catalogue_model(model, *, context=1_000_000):
    return {
        "id": model,
        "advertised_metadata": {
            "context_length": context,
            "pricing": {
                "prompt": "0.000001",
                "completion": "0.000003",
                "input_cache_read": "0.0000001",
                "request": "0",
                "image": "0",
                "price_per_video_second": "0",
                "price_per_minute": "0",
            },
        },
    }


class FakeTransport:
    def __init__(self, observations=None, available=True):
        self.observations = list(observations or [])
        self.calls = []
        self.available = available

    def catalogue(self, spec):
        return {
            "http_status": 200,
            "models": [catalogue_model(model) for model in probe.MODELS.values()]
            if self.available
            else [],
        }

    def chat(self, spec, payload):
        self.calls.append((spec, payload))
        if self.observations:
            result = self.observations.pop(0)
            if result.get("http_status") == 200:
                result.setdefault("response_model", spec.model)
            return result
        return {
            "http_status": 200,
            "response_model": spec.model,
            "_content": "headroom",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            "ttft_ms": 4,
            "ttft_content_ms": 4,
            "elapsed_ms": 8,
        }


class Encoder:
    def encode(self, text):
        return list(text.encode())

    def decode(self, values):
        return bytes(values).decode()


def test_full_plan_covers_all_requested_matrix_and_two_catalogues():
    plan = probe.build_plan()
    assert len(plan) == 62
    assert {p.endpoint for p in plan if p.method == "catalogue"} == set(probe.ENDPOINTS)
    for role in probe.MODELS:
        assert {p.method for p in plan if p.role == role and p.method in probe.METHODS} == set(
            probe.METHODS
        )
    assert [p.approx_input_tokens for p in plan if p.method == "long_context"] == list(
        probe.LONG_SIZES
    )
    assert len([p for p in plan if p.concurrency_group]) == 4


def test_dry_run_does_not_read_key_prices_tokenizer_or_transport(monkeypatch, capsys):
    monkeypatch.setattr(probe.Path, "read_text", lambda *a, **k: pytest.fail("file read"))
    original_get = probe.os.environ.get

    def guard_key(name, *args):
        if name == "NEBIUS_API_KEY":
            pytest.fail("key read")
        return original_get(name, *args)

    monkeypatch.setattr(probe.os.environ, "get", guard_key)
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    assert probe.main(["--pricing-file", "/absent.json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["network_requests"] == 0 and output["accepted"] is False


def test_execution_without_explicit_gates_never_touches_network(monkeypatch, capsys):
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    assert probe.main(["--execute"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-0.01", "not money"])
def test_prices_and_caps_reject_nonfinite_or_negative_values(value):
    with pytest.raises(probe.Refused):
        probe.money(value)


def test_prices_fail_closed_for_missing_model_or_output_cap():
    document = verified_prices()
    document["models"].pop(probe.MODELS["ultra"])
    with pytest.raises(probe.Refused):
        probe.validate_prices(document, {"ultra"})
    document = verified_prices()
    document["output_caps_include_reasoning"] = False
    with pytest.raises(probe.Refused):
        probe.validate_prices(document, {"ultra"})


def test_exact_reservation_before_dispatch_includes_all_retries():
    transport = FakeTransport()
    budget = probe.Budget(Decimal(2))
    spec = probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat")
    with pytest.raises(probe.Refused):
        probe.probe_attempts(spec, price(), budget, transport, 256, retries=2)
    assert transport.calls == [] and budget.outstanding == 0


def test_unused_retry_reservations_release_after_accounted_success():
    budget = probe.Budget(Decimal(5))
    row = probe.probe_attempts(
        probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat"),
        price(),
        budget,
        FakeTransport(),
        256,
        retries=2,
    )
    assert row["reservation_usd"] == str(Decimal("1.000768") * 3)
    assert budget.actual_known == Decimal("0.000016")
    assert budget.charged == budget.actual_known and budget.outstanding == 0


def test_unknown_usage_retains_full_upper_and_missing_usage_not_fabricated():
    transport = FakeTransport(
        [{"http_status": 200, "_content": "headroom", "finish_reason": "stop"}]
    )
    budget = probe.Budget(Decimal(3))
    row = probe.probe_attempts(
        probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat"),
        price(),
        budget,
        transport,
        256,
        retries=0,
    )
    assert row["attempts"][0]["actual_cost_usd"] is None
    assert row["attempts"][0]["cost_status"] == "unknown_reserved_upper_bound"
    assert budget.charged == Decimal("1.000768") and budget.actual_known == 0


def test_retry_429_reserves_unknown_attempt_and_backs_off():
    transport = FakeTransport([{"http_status": 429, "error": "http_429"}])
    sleeps = []
    budget = probe.Budget(Decimal(5))
    row = probe.probe_attempts(
        probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat"),
        price(),
        budget,
        transport,
        256,
        retries=2,
        sleep=sleeps.append,
    )
    assert len(row["attempts"]) == 2 and sleeps == [1]
    assert budget.charged == Decimal("1.000784")


def test_usage_over_verified_bound_halts_future_dispatch():
    transport = FakeTransport(
        [
            {
                "http_status": 200,
                "_content": "headroom",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 1_000_001, "completion_tokens": 2},
            }
        ]
    )
    budget = probe.Budget(Decimal(5))
    row = probe.probe_attempts(
        probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat"),
        price(),
        budget,
        transport,
        256,
        retries=2,
    )
    assert row["detail"] == "provider_exceeded_verified_token_bound"
    with pytest.raises(probe.Refused):
        budget.reserve(Decimal("0.01"))


@pytest.mark.parametrize("method", ["json_object", "json_schema", "fenced"])
def test_all_json_candidates_and_fenced_tolerant_parser(method):
    spec = probe.Probe("json", probe.ENDPOINTS[0], "super", method)
    payload, _ = probe.make_payload(spec, price(), 128)
    assert payload["stream"] and payload["stream_options"]["include_usage"]
    content = '{"probe":"headroom","value":7}'
    if method == "fenced":
        content = "\x60\x60\x60json\n" + content + "\n\x60\x60\x60"
    observation = {"http_status": 200, "_content": content}
    assert classify_known(spec, observation, {})[0] == "ok"
    assert classify_known(spec, {"http_status": 200, "_content": "{}"}, {})[0] == "fail"


def test_tools_validate_actual_function_and_arguments():
    spec = probe.Probe("tool", probe.ENDPOINTS[0], "super", "tools")
    payload, _ = probe.make_payload(spec, price(), 128)
    assert payload["tool_choice"]["function"]["name"] == "add"
    observation = {
        "http_status": 200,
        "_tool_calls": [{"name": "add", "arguments": '{"a":2,"b":3}'}],
    }
    assert classify_known(spec, observation, {})[0] == "ok"


@pytest.mark.parametrize(
    "method",
    [m for m in probe.METHODS if m.startswith(("template_", "prefix_", "effort_"))]
    + ["reasoning_budget", "max_thinking_tokens"],
)
def test_reasoning_and_token_budget_200_still_unknown(method):
    spec = probe.Probe("reason", probe.ENDPOINTS[0], "ultra", method)
    payload, _ = probe.make_payload(spec, price(), 256)
    assert payload["max_tokens"] == 256
    assert (
        classify_known(
            spec, {"http_status": 200, "_content": "432", "reasoning_observed": True}, {}
        )[0]
        == "unknown"
    )


def test_long_input_reports_approximation_and_never_serializes_prompt_or_needle():
    spec = probe.Probe("long", probe.ENDPOINTS[0], "ultra", "long_context", 64000)

    class NeedleTransport(FakeTransport):
        def chat(self, spec, payload):
            import re

            needle = re.search(
                r"HEADROOM_NEEDLE_[a-f0-9]+", payload["messages"][0]["content"]
            ).group()
            return {
                "http_status": 200,
                "response_model": spec.model,
                "_content": needle,
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 12345, "completion_tokens": 12},
            }

    row = probe.probe_attempts(
        spec, price(), probe.Budget(Decimal(2)), NeedleTransport(), 64, 0, encoder=Encoder()
    )
    serialized = json.dumps(row)
    assert row["status"] == "ok"
    assert row["measured_cl100k_tokens"] == 64000
    assert row["token_count_kind"] == "approximation_not_model_tokenizer"
    assert "HEADROOM_NEEDLE_" not in serialized and "Calibration passage" not in serialized


def test_concurrent_four_requests_reserve_group_before_any_dispatch():
    plan = probe.build_plan(["concurrency"])
    transport = FakeTransport()
    report = probe.execute_plan(
        plan,
        {"super": price()},
        probe.Budget(Decimal(3)),
        transport,
        256,
        0,
    )
    assert transport.calls == [] and len(report["probes"]) == 4
    assert all(row["status"] == "refused" for row in report["probes"])


def test_real_concurrency_uses_four_workers_and_still_never_accepts():
    barrier = threading.Barrier(4)

    class ConcurrentTransport(FakeTransport):
        def chat(self, spec, payload):
            barrier.wait(timeout=5)
            return super().chat(spec, payload)

    report = probe.execute_plan(
        probe.build_plan(["concurrency"]),
        {"super": price()},
        probe.Budget(Decimal(5)),
        ConcurrentTransport(),
        256,
        0,
    )
    assert len(report["probes"]) == 4
    assert all(row["status"] == "ok" for row in report["probes"])
    assert report["accepted"] is False and report["config_proposal"]["applied"] is False


def test_catalogue_model_absence_prevents_paid_dispatch():
    transport = FakeTransport(available=False)
    report = probe.execute_plan(
        probe.build_plan(["concurrency"]),
        {"super": price()},
        probe.Budget(Decimal(5)),
        transport,
        256,
        0,
    )
    assert transport.calls == []
    assert all(row["detail"] == "model_not_in_live_endpoint_catalogue" for row in report["probes"])


def test_usage_rejects_boolean_and_preserves_selected_numeric_details():
    assert probe.sanitized_usage({"prompt_tokens": True, "completion_tokens": 3}) is None
    usage = probe.sanitized_usage(
        {
            "prompt_tokens": 10,
            "completion_tokens": 4,
            "completion_tokens_details": {"reasoning_tokens": 2, "secret": "fake secret"},
        }
    )
    assert usage["completion_tokens_details"] == {"reasoning_tokens": 2}


def test_nonofficial_endpoint_refused():
    with pytest.raises(probe.Refused):
        probe.build_plan(endpoint="https://other-provider.invalid/v1/")


def test_unexpected_transport_failure_retains_charge_and_redacts_exception():
    class BrokenTransport(FakeTransport):
        def chat(self, spec, payload):
            raise RuntimeError("secret-must-not-appear")

    budget = probe.Budget(Decimal(2))
    row = probe.probe_attempts(
        probe.Probe("test", probe.ENDPOINTS[0], "ultra", "chat"),
        price(),
        budget,
        BrokenTransport(),
        256,
        0,
    )
    assert row["status"] == "fail"
    assert "secret-must-not-appear" not in json.dumps(row)
    assert budget.charged == Decimal("1.000768")
    assert budget.outstanding == 0


def test_http_transport_stream_usage_ttft_and_endpoint_without_network(monkeypatch):
    import httpx

    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert request.url.host == "api.tokenfactory.us-central1.nebius.com"
        assert payload["max_tokens"] == 256
        assert payload["stream_options"]["include_usage"] is True
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "internal"}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "headroom"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        ]
        for chunk in chunks:
            chunk["model"] = probe.MODELS["ultra"]
        stream = (
            "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    spec = probe.Probe("chat", probe.ENDPOINTS[0], "ultra", "chat")
    payload, _ = probe.make_payload(spec, price(), 256)
    observed = probe.HTTPTransport("offline-placeholder").chat(spec, payload)
    assert len(requests) == 1
    assert observed["usage"] == {"prompt_tokens": 10, "completion_tokens": 3}
    assert observed["reasoning_observed"]
    assert observed["ttft_ms"] is not None
    assert observed["ttft_content_ms"] >= observed["ttft_ms"]
    assert observed["elapsed_ms"] >= observed["ttft_content_ms"]


def test_http_transport_never_follows_redirect_or_reports_error_body(monkeypatch):
    import httpx

    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"location": "https://untrusted.invalid"}, text="secret-in-error-body"
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    spec = probe.Probe("chat", probe.ENDPOINTS[0], "ultra", "chat")
    payload, _ = probe.make_payload(spec, price(), 256)
    observed = probe.HTTPTransport("offline-placeholder").chat(spec, payload)
    assert len(requests) == 1 and observed["http_status"] == 302
    assert "secret-in-error-body" not in json.dumps(observed)


def test_catalogue_verbose_query_and_actual_ids_without_network(monkeypatch):
    import httpx

    real_client = httpx.AsyncClient
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.params["verbose"] == "true"
        return httpx.Response(
            200, json={"data": [{"id": probe.MODELS["super"], "context_length": 256000}]}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    observed = probe.HTTPTransport("offline-placeholder").catalogue(
        probe.build_plan(["catalogue"])[0]
    )
    assert len(seen) == 1 and observed["models"][0]["id"] == probe.MODELS["super"]


@pytest.mark.parametrize("method", ["json_object", "json_schema"])
@pytest.mark.parametrize(
    "content",
    [
        '\x60\x60\x60json\n{"probe":"headroom","value":7}\n\x60\x60\x60',
        '{"probe":"headroom","value":7.0}',
        '{"probe":"headroom","value":true}',
    ],
)
def test_native_json_capability_rejects_fences_and_noninteger_values(method, content):
    spec = probe.Probe("native-json", probe.ENDPOINTS[0], "super", method)
    assert classify_known(spec, {"http_status": 200, "_content": content}, {})[0] == "fail"


def test_peer_bound_violation_prevents_any_next_retry():
    budget = probe.Budget(Decimal(5))

    class PeerViolationTransport(FakeTransport):
        def chat(self, spec, payload):
            self.calls.append((spec, payload))
            with budget.lock:
                budget.violated = True
            return {"http_status": 429, "error": "http_429"}

    transport = PeerViolationTransport()
    row = probe.probe_attempts(
        probe.Probe("retry", probe.ENDPOINTS[0], "super", "chat"),
        price(),
        budget,
        transport,
        256,
        1,
        sleep=lambda _: None,
    )
    assert len(transport.calls) == 1
    assert row["status"] == "refused" and row["detail"] == "shared_provider_bound_violation"
    assert budget.charged == Decimal("1.000768")


def test_transport_direct_entry_refuses_nonofficial_endpoint():
    transport = probe.HTTPTransport("offline-placeholder")
    spec = probe.Probe("bad", "https://untrusted.invalid/", "super", "chat")
    with pytest.raises(probe.Refused):
        transport.chat(spec, {})
    with pytest.raises(probe.Refused):
        transport.catalogue(spec)


def test_absolute_deadline_stops_continuous_sse_heartbeats(monkeypatch):
    import asyncio

    import httpx

    real_client = httpx.AsyncClient

    class Heartbeats(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.001)
                yield b": heartbeat\n\n"

    def handler(request):
        return httpx.Response(
            200, stream=Heartbeats(), headers={"content-type": "text/event-stream"}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    monkeypatch.setattr(probe, "ULTRA_TIMEOUT", 0.02)
    spec = probe.Probe("heartbeat", probe.ENDPOINTS[0], "ultra", "chat")
    payload, _ = probe.make_payload(spec, price(), 256)
    observed = probe.HTTPTransport("offline-placeholder").chat(spec, payload)
    assert observed["error"] == "TimeoutError"
    assert 10 <= observed["elapsed_ms"] < 1000
    assert observed["usage"] is None


@pytest.mark.parametrize(
    "identity_fields, expected",
    [
        ({"response_model": None}, "missing"),
        ({"response_model": probe.MODELS["super"]}, "mismatch"),
        (
            {
                "response_model": probe.MODELS["ultra"],
                "response_model_ids": [probe.MODELS["ultra"], probe.MODELS["super"]],
            },
            "conflicting",
        ),
        ({"response_model": probe.MODELS["ultra"], "response_model_missing_events": 1}, "missing"),
    ],
)
def test_unverified_model_identity_never_prices_or_accepts_response(identity_fields, expected):
    spec = probe.Probe("identity", probe.ENDPOINTS[0], "ultra", "json_object")
    observation = {
        "http_status": 200,
        "_content": '{"probe":"headroom","value":7}',
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        **identity_fields,
    }
    assert probe.classify(spec, observation, {}) == ("unknown", "response_model_" + expected)
    budget = probe.Budget(Decimal(5))
    row = probe.probe_attempts(spec, price(), budget, FakeTransport([observation]), 256, 2)
    attempt = row["attempts"][0]
    assert row["status"] == "unknown" and row["model_identity"] == expected
    assert attempt["actual_cost_usd"] is None
    assert attempt["cost_status"] == "unknown_model_identity_requested_reservation_retained"
    assert attempt["billing_bound_verified_for_response"] is False
    assert budget.actual_known == 0 and budget.charged == Decimal("1.000768")
    assert budget.summary()["billing_bound_unresolved"] is True
    assert budget.summary()["halt_reason"] == "response_model_identity_unverified"
    with pytest.raises(probe.Refused):
        budget.reserve(Decimal("0.001"))


@pytest.mark.parametrize(
    "models, expected, missing",
    [
        ([probe.MODELS["ultra"], probe.MODELS["ultra"]], "matched", 0),
        ([None, None], "missing", 2),
        ([probe.MODELS["ultra"], None], "missing", 1),
        ([probe.MODELS["super"], probe.MODELS["super"]], "mismatch", 0),
        ([probe.MODELS["ultra"], probe.MODELS["super"]], "conflicting", 0),
    ],
)
def test_sse_model_identity_is_collected_and_consistent(monkeypatch, models, expected, missing):
    import httpx

    real_client = httpx.AsyncClient

    def handler(request):
        events = [
            {"choices": [{"delta": {"content": "headroom"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        ]
        for event, model in zip(events, models, strict=True):
            if model is not None:
                event["model"] = model
        stream = (
            "".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    spec = probe.Probe("identity", probe.ENDPOINTS[0], "ultra", "chat")
    payload, _ = probe.make_payload(spec, price(), 256)
    observation = probe.HTTPTransport("offline-placeholder").chat(spec, payload)
    assert probe.response_identity(spec, observation) == expected
    assert observation["response_model_missing_events"] == missing
    assert observation["response_model_ids"] == list(
        dict.fromkeys(model for model in models if model)
    )
    assert probe.classify(spec, observation, {})[0] == (
        "ok" if expected == "matched" else "unknown"
    )


def test_identity_failure_blocks_later_paid_probes():
    plan = probe.build_plan(["catalogue"]) + [
        probe.Probe("first", probe.ENDPOINTS[0], "ultra", "chat"),
        probe.Probe("second", probe.ENDPOINTS[0], "ultra", "chat"),
    ]
    transport = FakeTransport(
        [
            {
                "http_status": 200,
                "response_model": None,
                "_content": "headroom",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        ]
    )
    report = probe.execute_plan(
        plan, {"ultra": price()}, probe.Budget(Decimal(5)), transport, 256, 0
    )
    assert len(transport.calls) == 1
    assert report["probes"][0]["status"] == "unknown"
    assert report["probes"][1]["status"] == "refused"
    assert report["budget"]["actual_known_usd"] == "0"
    assert report["budget"]["billing_bound_unresolved"]
    assert report["accepted"] is False


def test_wrong_model_needle_does_not_inflate_long_context_success(monkeypatch):
    import re

    original_make_payload = probe.make_payload
    monkeypatch.setattr(
        probe,
        "make_payload",
        lambda spec, price, limit, encoder=None: original_make_payload(
            spec, price, limit, Encoder()
        ),
    )

    class WrongModelNeedle(FakeTransport):
        def chat(self, spec, payload):
            self.calls.append((spec, payload))
            needle = re.search(
                r"HEADROOM_NEEDLE_[a-f0-9]+", payload["messages"][0]["content"]
            ).group()
            return {
                "http_status": 200,
                "response_model": probe.MODELS["super"],
                "_content": needle,
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 64000, "completion_tokens": 12},
            }

    report = probe.execute_plan(
        probe.build_plan(["long"], long_sizes=[64000]),
        {"ultra": price()},
        probe.Budget(Decimal(5)),
        WrongModelNeedle(),
        256,
        0,
    )
    assert report["probes"][0]["status"] == "unknown"
    assert report["config_proposal"]["largest_successful_cl100k_approximation"] is None
    assert report["config_proposal"]["largest_successful_server_prompt_tokens"] is None
    assert report["budget"]["actual_known_usd"] == "0"


EXACT_NANO = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"


def test_explicit_model_override_preserves_default_matrix_and_other_roles():
    defaults = dict(probe.MODELS)
    plan = probe.build_plan(model_ids={"nano": EXACT_NANO})
    assert len(plan) == 62 and probe.MODELS == defaults
    assert all(p.model == EXACT_NANO for p in plan if p.role == "nano")
    assert all(p.model == defaults[p.role] for p in plan if p.role and p.role != "nano")
    assert probe.Probe("legacy", probe.ENDPOINTS[0], "nano", "chat").model == defaults["nano"]


@pytest.mark.parametrize(
    "entries",
    [
        ["typo=nvidia/example"],
        ["Nano=nvidia/example"],
        ["nano"],
        ["nano="],
        ["nano=other-provider/example"],
        ["nano=nvidia/example with-space"],
        ["nano=nvidia/example", "nano=nvidia/another"],
    ],
)
def test_invalid_overrides_refuse_before_key_price_or_transport(entries, monkeypatch, capsys):
    monkeypatch.setattr(probe.Path, "read_text", lambda *a, **k: pytest.fail("file read"))
    original_get = probe.os.environ.get

    def guard_key(name, *args):
        if name == "NEBIUS_API_KEY":
            pytest.fail("key read")
        return original_get(name, *args)

    monkeypatch.setattr(probe.os.environ, "get", guard_key)
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    args = [item for entry in entries for item in ("--model-id", entry)]
    assert probe.main(["--execute", *args]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


def test_model_override_dry_run_has_no_key_price_or_network(monkeypatch, capsys):
    monkeypatch.setattr(probe.Path, "read_text", lambda *a, **k: pytest.fail("file read"))
    original_get = probe.os.environ.get

    def guard_key(name, *args):
        if name == "NEBIUS_API_KEY":
            pytest.fail("key read")
        return original_get(name, *args)

    monkeypatch.setattr(probe.os.environ, "get", guard_key)
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    assert (
        probe.main(
            ["--suite", "capabilities", "--roles", "nano", "--model-id", "nano=" + EXACT_NANO]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["network_requests"] == 0 and report["accepted"] is False
    assert report["model_overrides"] == {"nano": EXACT_NANO}
    assert all(p["model"] == EXACT_NANO for p in report["plan"] if p["role"])
    assert len(report["plan"]) == 15


def test_model_override_does_not_bypass_execution_gates(monkeypatch, capsys):
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    assert probe.main(["--execute", "--model-id", "nano=" + EXACT_NANO]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "refused" and "confirmations" in report["detail"]


def test_override_prices_use_exact_id_without_fallback():
    document = verified_prices()
    overrides = {"nano": EXACT_NANO}
    with pytest.raises(probe.Refused, match="missing verified price"):
        probe.validate_prices(document, {"nano"}, overrides)
    document["models"][EXACT_NANO] = {
        **document["models"][probe.MODELS["nano"]],
        "input_usd_per_million": "7",
        "prompt_token_ceiling": 1000,
    }
    prices = probe.validate_prices(document, {"nano"}, overrides)
    assert prices["nano"].input_per_million == Decimal(7)
    assert prices["nano"].prompt_token_ceiling == 1000


class ExactNanoCatalogue(FakeTransport):
    def __init__(self, model=EXACT_NANO, endpoint=None, observations=None):
        super().__init__(observations)
        self.catalogue_model, self.catalogue_endpoint = model, endpoint

    def catalogue(self, spec):
        return {
            "http_status": 200,
            "models": (
                [catalogue_model(self.catalogue_model, context=1000)]
                if self.catalogue_endpoint is None or spec.endpoint == self.catalogue_endpoint
                else []
            ),
        }


def nano_chat_plan():
    return [
        *probe.build_plan(["catalogue"]),
        probe.Probe("nano-chat", probe.ENDPOINTS[0], "nano", "chat", model_id=EXACT_NANO),
    ]


@pytest.mark.parametrize(
    "model,endpoint",
    [
        (EXACT_NANO.lower(), None),
        ("nvidia/unknown-model", None),
        (EXACT_NANO, probe.ENDPOINTS[1]),
    ],
)
def test_override_requires_exact_id_in_selected_endpoint_catalogue(model, endpoint):
    transport = ExactNanoCatalogue(model, endpoint)
    budget = probe.Budget(Decimal(1))
    report = probe.execute_plan(nano_chat_plan(), {"nano": price()}, budget, transport, 256, 0)
    assert transport.calls == [] and budget.charged == 0 and budget.outstanding == 0
    assert report["selected_models"] == {"nano": EXACT_NANO}
    assert report["probes"][0] == {
        "id": "nano-chat",
        "role": "nano",
        "model": EXACT_NANO,
        "endpoint": probe.ENDPOINTS[0],
        "status": "refused",
        "detail": "model_not_in_live_endpoint_catalogue",
    }


def test_override_flows_through_payload_identity_and_budget():
    transport = ExactNanoCatalogue()
    price_for_actual_id = probe.Price(Decimal(7), Decimal(9), 1000, "max_tokens")
    budget = probe.Budget(Decimal("0.01"))
    report = probe.execute_plan(
        nano_chat_plan(), {"nano": price_for_actual_id}, budget, transport, 256, 0
    )
    assert len(transport.calls) == 1
    assert transport.calls[0][1]["model"] == EXACT_NANO
    assert report["probes"][0]["status"] == "ok"
    assert report["probes"][0]["model"] == EXACT_NANO
    assert budget.actual_known == Decimal("0.000088")
    assert report["accepted"] is False and report["config_proposal"]["applied"] is False


def test_overridden_request_rejects_old_default_response_identity():
    transport = ExactNanoCatalogue(
        observations=[
            {
                "http_status": 200,
                "response_model": probe.MODELS["nano"],
                "_content": "headroom",
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 10, "completion_tokens": 2},
            }
        ]
    )
    budget = probe.Budget(Decimal(2))
    report = probe.execute_plan(nano_chat_plan(), {"nano": price()}, budget, transport, 256, 0)
    assert len(transport.calls) == 1
    assert report["probes"][0]["status"] == "unknown"
    assert report["probes"][0]["detail"] == "response_model_mismatch"
    assert budget.halt_reason == "response_model_identity_unverified"


def test_selected_chat_method_is_exactly_one_paid_row_per_selected_role():
    plan = probe.build_plan(
        ["capabilities"],
        ["ultra", "super", "nano"],
        capability_methods=["chat"],
        model_ids={"nano": EXACT_NANO},
    )
    assert len(plan) == 5
    assert len([p for p in plan if p.method == "catalogue"]) == 2
    assert [(p.role, p.method) for p in plan if p.role] == [
        ("ultra", "chat"),
        ("super", "chat"),
        ("nano", "chat"),
    ]
    assert next(p.model for p in plan if p.role == "nano") == EXACT_NANO
    assert len(probe.build_plan()) == 62
    assert len(probe.build_plan(["all"], capability_methods=["chat"])) == 14


@pytest.mark.parametrize("methods", [[], ["chat", "chat"], ["unknown"]])
def test_invalid_capability_method_selection_refused(methods):
    with pytest.raises(probe.Refused):
        probe.build_plan(["capabilities"], capability_methods=methods)


def test_capability_method_on_catalogue_only_is_not_silently_ignored(monkeypatch, capsys):
    original_get = probe.os.environ.get
    monkeypatch.setattr(
        probe.os.environ,
        "get",
        lambda key, *a: (
            pytest.fail("key read") if key == "NEBIUS_API_KEY" else original_get(key, *a)
        ),
    )
    assert probe.main(["--execute", "--suite", "catalogue", "--capability-method", "chat"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


@pytest.mark.parametrize("method_args", [["chat", "chat"], ["unknown"]])
def test_bad_capability_methods_reject_before_secret_lookup(method_args, monkeypatch, capsys):
    original_get = probe.os.environ.get
    monkeypatch.setattr(
        probe.os.environ,
        "get",
        lambda key, *a: (
            pytest.fail("key read") if key == "NEBIUS_API_KEY" else original_get(key, *a)
        ),
    )
    args = [
        "--execute",
        "--suite",
        "capabilities",
        *[part for method in method_args for part in ("--capability-method", method)],
    ]
    if method_args == ["unknown"]:
        with pytest.raises(SystemExit) as error:
            probe.main(args)
        assert error.value.code == 2
    else:
        assert probe.main(args) == 2
        assert json.loads(capsys.readouterr().out)["status"] == "refused"


@pytest.mark.parametrize("suites", [["all"], ["catalogue", "capabilities"], ["capabilities"]])
def test_mixed_or_full_execution_cannot_use_catalogue_only_key_gate(suites, monkeypatch, capsys):
    original_get = probe.os.environ.get
    monkeypatch.setattr(
        probe.os.environ,
        "get",
        lambda key, *a: (
            pytest.fail("key read") if key == "NEBIUS_API_KEY" else original_get(key, *a)
        ),
    )
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    args = ["--execute", *[part for suite in suites for part in ("--suite", suite)]]
    assert probe.main(args) == 2
    assert "confirmations" in json.loads(capsys.readouterr().out)["detail"]


def test_catalogue_missing_key_is_refused_before_transport_or_output(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    directory = tmp_path / "catalogue"
    assert probe.main(["--execute", "--suite", "catalogue", "--output-dir", str(directory)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    assert not directory.exists()


def test_catalogue_only_real_http_adapter_sends_exactly_two_gets_without_paid_gates(
    tmp_path, monkeypatch, capsys
):
    import httpx

    monkeypatch.setenv("NEBIUS_API_KEY", "offline-placeholder-not-a-real-key")
    monkeypatch.setattr(probe, "validate_prices", lambda *a: pytest.fail("price validation"))
    monkeypatch.setattr(probe, "Budget", lambda *a: pytest.fail("budget construction"))
    monkeypatch.setattr(probe.HTTPTransport, "chat", lambda *a: pytest.fail("chat called"))
    monkeypatch.setattr(probe.Path, "read_text", lambda *a, **k: pytest.fail("price/file read"))
    real_client = httpx.AsyncClient
    requests = []
    metadata = {
        "pricing": {
            "prompt": "0.1",
            "completion": "0.3",
            "request": "0",
            "input_cache_read": "0.05",
        },
        "per_request_limits": {"prompt_tokens": 1000},
        "context_length": 1000,
        "supported_sampling_parameters": ["max_completion_tokens"],
    }

    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == "/v1/models"
        assert request.url.params["verbose"] == "true"
        return httpx.Response(200, json={"data": [{"id": EXACT_NANO, **metadata}]})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    directory = tmp_path / "catalogue"
    assert (
        probe.main(
            [
                "--execute",
                "--suite",
                "catalogue",
                "--pricing-file",
                "/absent.json",
                "--output-dir",
                str(directory),
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    with (directory / "report.json").open() as handle:
        report = json.load(handle)
    assert len(requests) == 2 and len({r.url.host for r in requests}) == 2
    assert output["status"] == "complete" and output["inference_requests"] == 0
    assert report["accepted"] is False and "budget" not in report
    assert report["catalogues"][0]["models"][0]["advertised_metadata"] == metadata
    assert "offline-placeholder-not-a-real-key" not in json.dumps(report)


@pytest.mark.parametrize(
    "status,body",
    [
        (401, {"error": "not authorized"}),
        (500, {"error": "server error"}),
        (200, {"data": []}),
        (200, {"data": [{"id": 123}]}),
        (200, {"data": "malformed"}),
        (200, []),
        (200, None),
    ],
)
def test_catalogue_failure_empty_or_malformed_is_saved_and_nonzero(
    status, body, tmp_path, monkeypatch, capsys
):
    import httpx

    monkeypatch.setenv("NEBIUS_API_KEY", "offline-placeholder-not-a-real-key")
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        return (
            httpx.Response(status, json=body)
            if body is not None
            else httpx.Response(status, text="invalid JSON")
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    directory = tmp_path / "catalogue"
    assert probe.main(["--execute", "--suite", "catalogue", "--output-dir", str(directory)]) == 2
    output = json.loads(capsys.readouterr().out)
    report = json.loads((directory / "report.json").read_text())
    assert len(requests) == 2
    assert output["status"] == "failed" and report["accepted"] is False
    assert all(
        row["status"] == "failed" and row["http_status"] == status for row in report["catalogues"]
    )
    assert report["inference_requests"] == 0


@pytest.mark.parametrize(
    "plan",
    [
        [],
        [
            probe.Probe("bad", "https://untrusted.invalid/v1/", None, "catalogue"),
            probe.Probe("ok", probe.ENDPOINTS[1], None, "catalogue"),
        ],
        [
            probe.Probe("ok", probe.ENDPOINTS[0], None, "catalogue"),
            probe.Probe("bad", probe.ENDPOINTS[1], "nano", "chat"),
        ],
    ],
)
def test_catalogue_helper_validates_entire_plan_before_first_get(plan):
    class NoRequests:
        def catalogue(self, spec):
            pytest.fail("GET before full-plan validation")

    with pytest.raises(probe.Refused):
        probe.execute_catalogue_plan(plan, NoRequests())


class GuardCatalogue(FakeTransport):
    def __init__(self, mutate=None, *, duplicate=False, http_status=200, error=None):
        super().__init__()
        self.mutate, self.duplicate = mutate, duplicate
        self.http_status, self.error = http_status, error
        self.gets = []

    def catalogue(self, spec):
        self.gets.append(spec.endpoint)
        row = catalogue_model(probe.MODELS["super"])
        if self.mutate:
            self.mutate(row["advertised_metadata"])
        return {
            "http_status": self.http_status,
            "models": [row, copy.deepcopy(row)] if self.duplicate else [row],
            **({"error": self.error} if self.error else {}),
        }


def super_chat_plan():
    return probe.build_plan(["capabilities"], ["super"], capability_methods=["chat"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt", "0.00000100000000000000000000000000001"),
        ("completion", "0.0000031"),
        ("input_cache_read", "0.0000011"),
        ("input_cache_read", None),
        ("input_cache_read", "NaN"),
        ("request", "0.01"),
        ("image", "0.01"),
        ("price_per_video_second", "0.01"),
        ("price_per_minute", "0.01"),
        ("unknown_service_fee", "0.00001"),
        ("input_cache_write", "0.00001"),
        ("request", None),
        ("prompt", True),
    ],
)
def test_live_catalogue_rate_or_fee_disagreement_blocks_plan_and_direct_probe(field, value):
    def change(metadata):
        metadata["pricing"][field] = value

    for direct in (False, True):
        transport = GuardCatalogue(change)
        budget = probe.Budget(Decimal(3))
        if direct:
            row = probe.probe_attempts(super_chat_plan()[-1], price(), budget, transport, 128, 0)
            guard = row["catalogue_guard"]
        else:
            report = probe.execute_plan(
                super_chat_plan(), {"super": price()}, budget, transport, 128, 0
            )
            row, guard = report["probes"][0], report["catalogue_guards"][0]
            assert report["catalogue_consistency_passed"] is False
            assert (
                report["catalogues"][0]["models"][0]["advertised_metadata"]["pricing"][field]
                == value
            )
        assert row["status"] == guard["status"] == "refused"
        assert transport.calls == [] and budget.charged == budget.outstanding == 0
        assert len(transport.gets) == (1 if direct else 2)


@pytest.mark.parametrize("context", [None, 0, True, 1_000_001])
def test_context_must_be_known_positive_and_no_larger_than_reviewed(context):
    transport = GuardCatalogue(lambda metadata: metadata.update(context_length=context))
    report = probe.execute_plan(
        super_chat_plan(), {"super": price()}, probe.Budget(Decimal(3)), transport, 128, 0
    )
    assert not transport.calls
    assert "context" in report["catalogue_guards"][0]["detail"]


@pytest.mark.parametrize(
    "field",
    [
        "prompt",
        "completion",
        "input_cache_read",
        "request",
        "image",
        "price_per_video_second",
        "price_per_minute",
    ],
)
def test_required_price_and_zero_fee_fields_may_not_disappear(field):
    transport = GuardCatalogue(lambda metadata: metadata["pricing"].pop(field))
    row = probe.probe_attempts(
        super_chat_plan()[-1], price(), probe.Budget(Decimal(3)), transport, 128, 0
    )
    assert row["status"] == "refused" and transport.calls == []
    assert row["catalogue_guard"]["detail"] == "catalogue_pricing_field_missing"
    assert field in row["catalogue_guard"]["fields"]


@pytest.mark.parametrize(
    "kwargs", [{"duplicate": True}, {"http_status": 503}, {"error": "fixture_directory_error"}]
)
def test_model_identity_is_not_enough_when_catalogue_response_is_invalid(kwargs):
    transport = GuardCatalogue(**kwargs)
    report = probe.execute_plan(
        super_chat_plan(), {"super": price()}, probe.Budget(Decimal(3)), transport, 128, 0
    )
    assert report["probes"][0]["status"] == "refused" and transport.calls == []


def test_guard_preserves_legacy_reviewed_schema_and_safe_price_margin():
    prices = probe.validate_prices(verified_prices(), {"super"})
    transport = GuardCatalogue(
        lambda metadata: metadata["pricing"].update(prompt="0.0000009", unknown_fee="0")
    )
    saved = []

    def record(report):
        saved.append(copy.deepcopy(report))

    report = probe.execute_plan(
        super_chat_plan(), prices, probe.Budget(Decimal(3)), transport, 128, 0, record
    )
    assert len(transport.calls) == 1 and len(transport.gets) == 2
    assert report["catalogue_consistency_passed"] is True
    assert report["probes"][0]["catalogue_guard"]["status"] == "matched"
    assert any(row["catalogue_guards"] and not row["probes"] for row in saved)
    assert report["accepted"] is False and report["config_proposal"]["applied"] is False


def fallback_document():
    document = verified_prices()
    document["models"][probe.MODELS["super"]].update(
        {
            "cached_input_usd_per_million": "0.1",
            "reviewed_cache_price_evidence": "offline independent Prices UI receipt",
            "allow_catalogue_cache_price_missing": True,
        }
    )
    return document


@pytest.mark.parametrize(
    "change",
    [
        {"cached_input_usd_per_million": None},
        {"cached_input_usd_per_million": "NaN"},
        {"cached_input_usd_per_million": "-0.1"},
        {"cached_input_usd_per_million": "1.01"},
        {"reviewed_cache_price_evidence": ""},
        {"reviewed_cache_price_evidence": "  "},
        {"reviewed_cache_price_evidence": None},
        {"allow_catalogue_cache_price_missing": 1},
    ],
)
def test_missing_cache_fallback_requires_explicit_valid_review(change):
    document = fallback_document()
    document["models"][probe.MODELS["super"]].update(change)
    with pytest.raises(probe.Refused):
        probe.validate_prices(document, {"super"})


@pytest.mark.parametrize("missing", [True, False])
def test_explicit_reviewed_fallback_preserves_null_or_missing_catalogue(missing):
    def mutate(metadata):
        if missing:
            metadata["pricing"].pop("input_cache_read")
        else:
            metadata["pricing"]["input_cache_read"] = None

    prices = probe.validate_prices(fallback_document(), {"super"})
    transport = GuardCatalogue(mutate)
    report = probe.execute_plan(
        super_chat_plan(), prices, probe.Budget(Decimal(3)), transport, 128, 0
    )
    guard = report["catalogue_guards"][0]
    assert len(transport.calls) == 1 and guard["status"] == "matched"
    assert guard["cache_price_basis"] == "reviewed_external_fallback"
    assert guard["adopted_cache_usd_per_million"] == "0.1"
    assert guard["reviewed_cache_price_evidence"] == "offline independent Prices UI receipt"
    raw = guard["observed"]["pricing"]
    assert ("input_cache_read" not in raw) if missing else raw["input_cache_read"] is None
    assert report["accepted"] is False


def test_cache_price_and_evidence_without_flag_do_not_authorize_missing_value():
    document = fallback_document()
    document["models"][probe.MODELS["super"]].pop("allow_catalogue_cache_price_missing")
    prices = probe.validate_prices(document, {"super"})
    transport = GuardCatalogue(lambda metadata: metadata["pricing"].update(input_cache_read=None))
    report = probe.execute_plan(
        super_chat_plan(), prices, probe.Budget(Decimal(3)), transport, 128, 0
    )
    assert transport.calls == [] and report["probes"][0]["status"] == "refused"


def test_real_catalogue_cache_price_must_not_be_replaced_by_fallback():
    prices = probe.validate_prices(fallback_document(), {"super"})
    transport = GuardCatalogue(
        lambda metadata: metadata["pricing"].update(input_cache_read="0.00000011")
    )
    report = probe.execute_plan(
        super_chat_plan(), prices, probe.Budget(Decimal(3)), transport, 128, 0
    )
    guard = report["catalogue_guards"][0]
    assert guard["cache_price_basis"] == "live_catalogue"
    assert guard["field"] == "input_cache_read" and transport.calls == []


def test_http_adapter_catalogue_mismatch_exits_nonzero_without_post_and_saves_evidence(
    tmp_path, monkeypatch, capsys
):
    import httpx

    # Preserve this historical catalogue-adapter check behind the retired CLI gate.
    # The test installs an in-memory HTTP transport that accepts GET only below.
    monkeypatch.setattr(probe, "require_standalone_paid_dispatch", lambda: None)
    monkeypatch.setenv("NEBIUS_API_KEY", "offline-placeholder-not-real")
    path = tmp_path / "pricing.json"
    path.write_text(json.dumps(verified_prices()))
    real_client = httpx.AsyncClient
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        row = catalogue_model(probe.MODELS["super"])
        metadata = row["advertised_metadata"]
        metadata["pricing"]["request"] = "0.25"
        return httpx.Response(200, json={"data": [{"id": row["id"], **metadata}]})

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    directory = tmp_path / "execute"
    assert (
        probe.main(
            [
                "--execute",
                "--allow-paid-requests",
                "--credit-confirmed",
                "--budget-usd",
                "3",
                "--available-credit-usd",
                "3",
                "--pricing-file",
                str(path),
                "--suite",
                "capabilities",
                "--roles",
                "super",
                "--capability-method",
                "chat",
                "--output-dir",
                str(directory),
            ]
        )
        == 2
    )
    output = json.loads(capsys.readouterr().out)
    report = json.loads((directory / "report.json").read_text())
    assert len(requests) == 2 and output["accepted"] is False
    assert report["budget"]["actual_known_usd"] == "0"
    assert report["catalogue_guards"][0]["detail"] == "catalogue_unmodeled_fee_nonzero"
    assert report["catalogue_guards"][0]["field"] == "request"
    assert (
        report["catalogues"][0]["models"][0]["advertised_metadata"]["pricing"]["request"] == "0.25"
    )


def rate_limit_fixture():
    return {
        "x-ratelimit-limit-requests": "100",
        "x-ratelimit-remaining-requests": "9",
        "x-ratelimit-reset-requests": "0.25",
        "x-ratelimit-limit-tokens": "1000000",
        "x-ratelimit-remaining-tokens": "900000",
        "x-ratelimit-reset-tokens": "60",
        "x-ratelimit-over-limit": "yes",
        "retry-after": "Wed, 21 Oct 2026 07:28:00 GMT",
    }


def test_rate_limit_whitelist_preserves_only_eight_bounded_response_fields():
    expected = rate_limit_fixture()
    supplied = {
        **{key.upper(): value for key, value in expected.items()},
        "authorization": "Bearer private-value",
        "set-cookie": "private-value",
        "x-request-id": "private-value",
        "location": "https://private-value.invalid",
        "x-ratelimit-reset-unreviewed": "private-value",
        "x-ratelimit-limit-requests-extra": "100",
    }
    assert probe.sanitized_rate_limit_headers(supplied) == expected
    assert len(probe.RATE_LIMIT_HEADERS) == 8


@pytest.mark.parametrize(
    "name,value",
    [
        ("x-ratelimit-limit-tokens", 123),
        ("x-ratelimit-remaining-requests", True),
        ("x-ratelimit-limit-requests", "1.5"),
        ("x-ratelimit-remaining-tokens", "-1"),
        ("x-ratelimit-limit-tokens", "1e6"),
        ("x-ratelimit-reset-requests", "NaN"),
        ("x-ratelimit-reset-tokens", "Infinity"),
        ("x-ratelimit-reset-tokens", "2s"),
        ("x-ratelimit-reset-tokens", "-0.1"),
        ("x-ratelimit-over-limit", "true"),
        ("retry-after", ""),
        ("retry-after", "   "),
        ("retry-after", "x" * 129),
        ("retry-after", "1\r\nAuthorization: private-value"),
        ("retry-after", "1\t"),
        ("retry-after", "\x7f"),
        ("retry-after", "\u00a0"),
        ("retry-after", ["1"]),
    ],
)
def test_rate_limit_rejects_invalid_type_format_length_and_controls(name, value):
    assert probe.sanitized_rate_limit_headers({name: value}) == {}


def test_rate_limit_duplicate_case_and_reflected_key_are_omitted():
    import httpx

    headers = httpx.Headers(
        [
            ("retry-after", "1"),
            ("Retry-After", "2"),
            ("x-ratelimit-remaining-tokens", "123"),
        ]
    )
    assert probe.sanitized_rate_limit_headers(headers) == {"x-ratelimit-remaining-tokens": "123"}
    assert (
        probe.sanitized_rate_limit_headers(
            {"x-ratelimit-limit-tokens": "100", "X-Ratelimit-Limit-Tokens": "100"}
        )
        == {}
    )
    assert (
        probe.sanitized_rate_limit_headers(
            {"retry-after": "private-placeholder"}, secret="private-placeholder"
        )
        == {}
    )
    assert probe.sanitized_rate_limit_headers(None) == {}


@pytest.mark.parametrize("status", [200, 429])
def test_http_rate_limit_headers_reach_saved_report_on_success_and_failure(monkeypatch, status):
    import httpx

    real_client = httpx.AsyncClient
    requests = []
    expected = rate_limit_fixture()

    def handler(request):
        requests.append(request)
        headers = {
            **expected,
            "authorization": "Bearer private-response",
            "set-cookie": "private-response",
            "x-request-id": "private-response",
        }
        if request.method == "GET":
            row = catalogue_model(probe.MODELS["super"])
            return httpx.Response(
                200,
                headers=headers,
                json={"data": [{"id": row["id"], **row["advertised_metadata"]}]},
            )
        if status == 429:
            return httpx.Response(429, headers=headers, text="private-error-body")
        event = {
            "model": probe.MODELS["super"],
            "choices": [{"delta": {"content": "headroom"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2},
        }
        return httpx.Response(
            200, headers=headers, text="data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n"
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    saved = []
    report = probe.execute_plan(
        super_chat_plan(),
        {"super": price()},
        probe.Budget(Decimal(3)),
        probe.HTTPTransport("offline-placeholder"),
        128,
        0,
        lambda value: saved.append(copy.deepcopy(value)),
    )
    assert [request.method for request in requests] == ["GET", "GET", "POST"]
    assert all(row["rate_limit_headers"] == expected for row in report["catalogues"])
    attempt = report["probes"][0]["attempts"][0]
    assert attempt["http_status"] == status
    assert attempt["rate_limit_headers"] == expected
    assert saved[-1]["probes"][0]["attempts"][0]["rate_limit_headers"] == expected
    public = json.dumps(report)
    assert "private-response" not in public and "private-error-body" not in public
    assert "offline-placeholder" not in public
    if status == 429:
        assert attempt["cost_status"] == "unknown_reserved_upper_bound"
        assert report["budget"]["charged_or_conservatively_retained_usd"] == "1.000384"
    else:
        assert attempt["status"] == "ok"


def test_rate_limit_headers_survive_midstream_read_timeout(monkeypatch):
    import httpx

    class InterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": heartbeat\n\n"
            raise httpx.ReadTimeout("private-exception")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"x-ratelimit-reset-tokens": "0.125"},
                    stream=InterruptedStream(),
                )
            ),
            **kwargs,
        ),
    )
    spec = super_chat_plan()[-1]
    payload, _ = probe.make_payload(spec, price(), 128)
    result = probe.HTTPTransport("offline-placeholder").chat(spec, payload)
    assert result["error"] == "ReadTimeout"
    assert result["rate_limit_headers"] == {"x-ratelimit-reset-tokens": "0.125"}
    assert "private-exception" not in json.dumps(result)


def test_catalogue_rate_limit_headers_survive_invalid_json(monkeypatch):
    import httpx

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"retry-after": "2"}, text="private-invalid-json"
                )
            ),
            **kwargs,
        ),
    )
    result = probe.HTTPTransport("offline-placeholder").catalogue(
        probe.build_plan(["catalogue"])[0]
    )
    assert result["error"] == "JSONDecodeError"
    assert result["rate_limit_headers"] == {"retry-after": "2"}
    assert "private-invalid-json" not in json.dumps(result)


def test_attempt_publication_resanitizes_transport_metadata():
    transport = FakeTransport(
        [
            {
                "http_status": 429,
                "error": "http_429",
                "rate_limit_headers": {
                    "retry-after": "3",
                    "authorization": "private-value",
                    "x-ratelimit-reset-tokens": "not-seconds",
                },
            }
        ]
    )
    row = probe.probe_attempts(
        super_chat_plan()[-1], price(), probe.Budget(Decimal(3)), transport, 128, 0
    )
    assert row["attempts"][0]["rate_limit_headers"] == {"retry-after": "3"}
    assert "private-value" not in json.dumps(row)


@pytest.mark.parametrize(
    "suites", [["all"], ["capabilities"], ["long"], ["concurrency"], ["catalogue", "capabilities"]]
)
def test_retired_paid_cli_refuses_fully_armed_legacy_flags_before_any_prerequisite(
    tmp_path, monkeypatch, capsys, suites
):
    original_get = probe.os.environ.get

    def guard_key(name, *args):
        if name == "NEBIUS_API_KEY":
            pytest.fail("retired probe read key")
        return original_get(name, *args)

    monkeypatch.setattr(probe.os.environ, "get", guard_key)
    monkeypatch.setattr(probe.Path, "read_text", lambda *a, **k: pytest.fail("price read"))
    monkeypatch.setattr(probe.HTTPTransport, "__init__", lambda *a: pytest.fail("transport"))
    monkeypatch.setattr(probe, "execute_plan", lambda *a, **k: pytest.fail("dispatch"))
    target = tmp_path / "no-output"
    argv = [
        "--execute",
        "--allow-paid-requests",
        "--credit-confirmed",
        "--budget-usd",
        "6",
        "--available-credit-usd",
        "24.52",
        "--pricing-file",
        str(tmp_path / "old-pricing.json"),
        "--output-dir",
        str(target),
        *[part for suite in suites for part in ("--suite", suite)],
    ]
    assert probe.main(argv) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["accepted"] is False and result["status"] == "refused"
    assert (
        result["detail"]
        == "Standalone paid model probes are retired; use the reviewed shared runtime ledger"
    )
    assert not target.exists()


def test_paid_retirement_gate_has_no_credit_or_override_argument():
    with pytest.raises(probe.Refused, match="Standalone paid model probes are retired"):
        probe.require_standalone_paid_dispatch()
