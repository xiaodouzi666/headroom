"""Optional Ultra truncation-mode recovery; synthetic bounded transport only."""

import json
from dataclasses import asdict
from types import SimpleNamespace

import pytest
from test_diagnosis_bounded_repair import payload, run
from test_diagnosis_output_recovery import sdk_fixture

from headroom import diagnose
from headroom.budget import BudgetExceeded
from headroom.config import SUPER_MODEL, ULTRA_MODEL
from headroom.diagnosis_protocol import COMMON_4000
from headroom.llm import validation_history
from headroom.llm.router import LLMRouter, ResponseValidationError


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*_args, **_kwargs):
        pytest.fail("No network in optional toggle fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def test_only_truncated_existing_supplement_switches_same_ultra_and_full_evidence():
    requests = []
    with sdk_fixture(
        [('{"private-incomplete":', "length"), (json.dumps(payload()), "stop")], requests
    ) as client:
        result = run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert result.ready_for_patch and len(requests) == 2
    first, second = requests
    assert first["model"] == second["model"] == ULTRA_MODEL
    assert first["max_completion_tokens"] == second["max_completion_tokens"] == 16384
    assert first["response_format"] == second["response_format"]
    assert first["chat_template_kwargs"] == {"enable_thinking": True}
    assert second["chat_template_kwargs"] == {"enable_thinking": False}
    assert second["messages"][:-1] == first["messages"]
    assert "private-incomplete" not in json.dumps(second)
    assert [x["requested_reasoning"] for x in result.response_request_modes] == [True, False]
    assert [x["request_index"] for x in result.response_request_modes] == [1, 2]
    assert all(x["scope"] == "host_requested_mode_only" for x in result.response_request_modes)


@pytest.mark.parametrize(("text", "finish"), [("", "stop"), ("not-json", "stop")])
def test_other_format_errors_keep_thinking_on(text, finish):
    requests = []
    with sdk_fixture([(text, finish), (json.dumps(payload()), "stop")], requests) as client:
        result = run(LLMRouter(client))
    assert result.ready_for_patch and len(requests) == 2
    assert [x["requested_reasoning"] for x in result.response_request_modes] == [True, True]
    assert all(r["chat_template_kwargs"]["enable_thinking"] is True for r in requests)


def test_semantic_supplement_keeps_on_and_current_numerics_gate():
    bad = payload()
    bad["plan"][0]["description"] = "Enable BF16."
    requests = []
    with sdk_fixture([(json.dumps(bad), "stop"), (json.dumps(bad), "stop")], requests) as client:
        result = run(LLMRouter(client))
    assert not result.ready_for_patch and len(requests) == 2
    assert "NUMERICS_CHANGE_FORBIDDEN" in {x.code for x in result.issues}
    assert [x["requested_reasoning"] for x in result.response_request_modes] == [True, True]


@pytest.mark.parametrize(
    "change",
    [
        lambda v: v["plan"][0].update(description="Convert weights to FP16."),
        lambda v: v.update(needs_more_info=True),
        lambda v: v["plan"][0].update(expected_saving_gb=0),
    ],
)
def test_format_recovery_never_bypasses_semantic_or_readiness_gates(change):
    bad = payload()
    change(bad)
    requests = []
    with sdk_fixture(
        [('{"partial":', "length"), (json.dumps(bad), "stop"), (json.dumps(payload()), "stop")],
        requests,
    ) as client:
        result = run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert len(requests) == 2 and not result.ready_for_patch
    assert result.diagnosis.verification.compare_loss is True
    assert [x["requested_reasoning"] for x in result.response_request_modes] == [True, False]


def test_filtered_never_switches_or_retries():
    requests = []
    with (
        sdk_fixture(
            [("blocked", "content_filter"), (json.dumps(payload()), "stop")], requests
        ) as client,
        pytest.raises(ResponseValidationError) as caught,
    ):
        run(LLMRouter(client))
    assert len(requests) == 1
    assert (
        validation_history.response_validation_history(caught.value)["failures"][0][
            "requested_reasoning"
        ]
        is True
    )


def test_two_truncations_are_terminal_with_transparent_modes():
    requests = []
    with sdk_fixture([('{"private":', "length")], requests) as client:
        with pytest.raises(ResponseValidationError) as caught:
            run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    history = validation_history.response_validation_history(caught.value)
    assert len(requests) == 2 and history["total_failures"] == 2
    assert [x["requested_reasoning"] for x in history["failures"]] == [True, False]
    assert [x["error_reason"] for x in history["failures"]] == ["truncated", "truncated"]
    assert "private" not in json.dumps(history)


def test_common_4000_protocol_keeps_its_original_mode_and_cap():
    requests = []
    with sdk_fixture(
        [('{"partial":', "length"), (json.dumps(payload()), "stop")], requests
    ) as client:
        result = run(LLMRouter(client), study_protocol=COMMON_4000)
    assert len(requests) == 2 and result.ready_for_patch
    assert all(r["max_completion_tokens"] == 4000 for r in requests)
    assert all(r["chat_template_kwargs"]["enable_thinking"] is True for r in requests)


@pytest.mark.parametrize("limit", [0, 3])
def test_only_the_existing_one_supplement_configuration_can_switch(limit):
    requests = []
    with (
        sdk_fixture([('{"partial":', "length")], requests) as client,
        pytest.raises(ResponseValidationError),
    ):
        run(LLMRouter(client), max_supplements=limit)
    assert len(requests) == limit + 1
    assert all(r["chat_template_kwargs"]["enable_thinking"] is True for r in requests)


def fake_router(
    *,
    model=ULTRA_MODEL,
    method="chat_template_kwargs",
    json_method="json_schema",
    finish="length",
    second_error=None,
):
    spec = SimpleNamespace(
        model_id=model,
        capabilities=SimpleNamespace(reasoning_method=method, json_method=json_method),
    )

    class Router:
        client = SimpleNamespace(config=SimpleNamespace(model_for=lambda role: spec))

        def __init__(self):
            self.modes = []

        def chat(self, *_args, **kwargs):
            self.modes.append(kwargs["reasoning"])
            if len(self.modes) == 1:
                raise ResponseValidationError(
                    "private",
                    reason="truncated",
                    response=SimpleNamespace(finish_reason=finish, text="private", role="diagnose"),
                )
            if second_error:
                raise second_error("guarded admission failure")
            return SimpleNamespace(parsed=payload())

    return Router()


@pytest.mark.parametrize(
    ("model", "method", "json_method", "finish"),
    [
        (SUPER_MODEL, "chat_template_kwargs", "json_schema", "length"),
        (ULTRA_MODEL, None, "json_schema", "length"),
        (ULTRA_MODEL, "reasoning_effort", "json_schema", "length"),
        (ULTRA_MODEL, "chat_template_kwargs", None, "length"),
        (ULTRA_MODEL, "chat_template_kwargs", "json_schema", "stop"),
    ],
)
def test_foreign_unverified_or_contradictory_modes_never_switch(model, method, json_method, finish):
    router = fake_router(model=model, method=method, json_method=json_method, finish=finish)
    result = run(router)
    assert result.ready_for_patch and router.modes == [True, True]


def test_no_new_probe_or_unknown_capability_is_inferred():
    assert diagnose._verified_ultra_template_toggle(SimpleNamespace()) is False


def test_budget_failure_on_existing_second_request_does_not_add_another_attempt():
    router = fake_router(second_error=BudgetExceeded)
    with pytest.raises(BudgetExceeded):
        run(router)
    assert router.modes == [True, False]


def test_source_protocol_and_runtime_budget_objects_are_not_mutated():
    requests = []
    with sdk_fixture(
        [('{"partial":', "length"), (json.dumps(payload()), "stop")], requests
    ) as client:
        config_before = (
            client.config.base_url,
            client.config.live_enabled,
            {key: asdict(value) for key, value in client.config.models.items()},
        )
        run(LLMRouter(client))
        assert (
            client.config.base_url,
            client.config.live_enabled,
            {key: asdict(value) for key, value in client.config.models.items()},
        ) == config_before
        assert len(client.ledger.entries) == 2
        assert all(r["max_completion_tokens"] == 16384 for r in requests)


def test_terminal_event_keeps_the_actual_requested_toggle_modes(tmp_path):
    from headroom.orchestrator import FixRequest, Services, run_fix
    from headroom.store.db import Store

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    requests = []
    with sdk_fixture([('{"private-partial":', "length")], requests) as client:

        def runtime(*_args, **_kwargs):
            return run(LLMRouter(client))

        def forbidden(*_args, **_kwargs):
            pytest.fail("No GPU job is permitted")

        store = Store(tmp_path / "store.db")
        try:
            result = run_fix(
                FixRequest(script=str(source / "train.py")),
                store=store,
                run_root=tmp_path / "jobs",
                services=Services(
                    runtime_factory=runtime, baseline=forbidden, provenance="offline_fixture"
                ),
            )
            events = [e for e in store.events(result["run_id"]) if e["kind"] == "run.failed"]
            assert len(events) == 1
            history = events[0]["response_validation_history"]
            assert [v["requested_reasoning"] for v in history["failures"]] == [True, False]
            assert len(requests) == len(client.ledger.entries) == 2
            assert "private-partial" not in json.dumps(events)
        finally:
            store.close()
