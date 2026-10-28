"""Profile-carried diagnosis mode through real runtime and guarded installed CLI."""

import copy
import json
import socket
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import test_cli_execution as cli_fixture
from test_ablation_common_budget import study_profile
from test_diagnosis_bounded_repair import evidence, payload
from test_llm_client import completion

from headroom.budget import BudgetLedger
from headroom.diagnose import diagnose_with_router
from headroom.diagnosis_protocol import (
    COMMON_4000,
    FINAL48_DIAGNOSIS_ONLY,
    carried_diagnosis_request_policy,
    named_diagnosis_request_policy,
    resolve_diagnosis_request_policy,
)
from headroom.evaluation import condition_services
from headroom.llm.router import LLMRouter
from headroom.runtime import build_live_runtime
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No real DNS/socket use in profile-policy tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr("headroom.runtime.read_nebius_key", lambda path: "offline-placeholder")


def runtime_case(tmp_path, *, policy_id=None, replies=None):
    profile = study_profile(tmp_path)
    profile.diagnosis_request_policy = policy_id
    store = Store(tmp_path / "store.db")
    store.create_run("fixture")
    budget = BudgetLedger(tmp_path / "budget.db", daily_limit="3", total_limit="3")
    budget.open_run("fixture", "0.6", budget_mode=profile.run_budget_mode)
    bodies = []
    replies = replies or [(json.dumps(payload()), "stop")]

    def respond(request):
        body = json.loads(request.content)
        bodies.append(body)
        text, finish = replies[min(len(bodies) - 1, len(replies) - 1)]
        result = completion(text, model=body["model"])
        result["choices"][0]["finish_reason"] = finish
        return httpx.Response(200, json=result)

    bundle = build_live_runtime(
        "fixture",
        profile=profile,
        budget=budget,
        store=store,
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    return bundle, store, bodies


def call(router, **kwargs):
    return diagnose_with_router(
        router, "Measured stk", evidence=evidence(), goal="reclaim", policy={}, **kwargs
    )


@pytest.mark.parametrize("name", [True, 2000, {}, "unknown", ""])
def test_profile_name_is_explicit_and_not_coerced(name):
    with pytest.raises(ValueError):
        named_diagnosis_request_policy(name)


def test_mock_dynamic_attributes_do_not_invent_carried_policies():
    router = MagicMock()
    assert carried_diagnosis_request_policy(router) is None
    router.diagnosis_request_policy = "untyped"
    with pytest.raises(ValueError):
        carried_diagnosis_request_policy(router)
    router.diagnosis_request_policy = FINAL48_DIAGNOSIS_ONLY
    assert carried_diagnosis_request_policy(router) is FINAL48_DIAGNOSIS_ONLY


def test_different_explicit_policy_cannot_escape_profile():
    forged = copy.copy(FINAL48_DIAGNOSIS_ONLY)
    object.__setattr__(forged, "max_completion_tokens", 16384)
    with pytest.raises(ValueError):
        resolve_diagnosis_request_policy(carried=FINAL48_DIAGNOSIS_ONLY, explicit=forged)


@pytest.mark.parametrize(
    "policy_id,cap,thinking", [(None, 16384, True), (FINAL48_DIAGNOSIS_ONLY.id, 2000, False)]
)
def test_real_runtime_carries_opt_in_and_preserves_old_profile(tmp_path, policy_id, cap, thinking):
    bundle, store, bodies = runtime_case(tmp_path, policy_id=policy_id)
    try:
        result = call(bundle.router, max_supplements=0)
        assert result.valid and len(bodies) == 1
        assert bodies[0]["max_completion_tokens"] == cap
        assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": thinking}
        assert str(cap) + "-token" in bodies[0]["messages"][1]["content"]
        assert result.response_request_modes[0]["requested_reasoning"] is thinking
        assert store.llm_calls("fixture")[0]["request_evidence"]["payload"] == bodies[0]
    finally:
        bundle.close()
        store.close()


def test_profile_mode_survives_supplement_and_its_prompt(tmp_path):
    bundle, store, bodies = runtime_case(
        tmp_path,
        policy_id=FINAL48_DIAGNOSIS_ONLY.id,
        replies=[('{"root_causes":', "length"), (json.dumps(payload()), "stop")],
    )
    try:
        result = call(bundle.router, max_supplements=1)
        assert result.valid and len(bodies) == 2
        for body in bodies:
            assert body["max_completion_tokens"] == 2000
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
            assert "2000-token" in body["messages"][1]["content"]
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize("case", ["study", "forged", "super_study"])
def test_conflicts_refused_before_dispatch(tmp_path, case):
    bundle, store, bodies = runtime_case(tmp_path, policy_id=FINAL48_DIAGNOSIS_ONLY.id)
    try:
        with pytest.raises(ValueError):
            if case == "study":
                call(bundle.router, study_protocol=COMMON_4000)
            elif case == "forged":
                fake = copy.copy(FINAL48_DIAGNOSIS_ONLY)
                object.__setattr__(fake, "reasoning", True)
                call(bundle.router, request_policy=fake)
            else:
                condition_services("full_super", tmp_path / "audit").diagnose(
                    bundle.router, "Measured stk", evidence=evidence(), goal="reclaim", policy={}
                )
        assert bodies == []
        assert store.llm_calls("fixture") == []
    finally:
        bundle.close()
        store.close()


@pytest.mark.parametrize("role", ["patcher", "annotate"])
def test_carried_policy_never_rewrites_direct_other_role_chat(role):
    seen = []

    class Captured(Exception):
        pass

    class Client:
        def complete(self, role, messages, **kwargs):
            seen.append((role, kwargs))
            raise Captured

    router = LLMRouter(Client(), diagnosis_request_policy=FINAL48_DIAGNOSIS_ONLY)
    with pytest.raises(Captured):
        router.chat(role, [{"role": "user", "content": "fixture"}], max_tokens=321, reasoning=True)
    assert seen[0][0] == role
    assert seen[0][1]["max_tokens"] == 321
    assert seen[0][1]["reasoning"] is True


def test_evaluation_saved_messages_and_metadata_match_carried_wire(tmp_path):
    bundle, store, bodies = runtime_case(tmp_path, policy_id=FINAL48_DIAGNOSIS_ONLY.id)
    audit = tmp_path / "audit"
    try:
        result = condition_services("full_ultra", audit).diagnose(
            bundle.router,
            "Measured stk",
            evidence=evidence(),
            goal="reclaim",
            policy={},
            max_supplements=0,
        )
        assert result.valid
        saved = json.loads((audit / "01-initial-messages.json").read_text())
        meta = json.loads((audit / "01-provenance.json").read_text())
        assert saved == bodies[0]["messages"][1:]
        assert meta["diagnosis_max_completion_tokens"] == 2000
        assert meta["diagnosis_request_policy"] == FINAL48_DIAGNOSIS_ONLY.id
    finally:
        bundle.close()
        store.close()


def test_installed_cli_bridge_reaches_real_runtime_and_policy_wire(tmp_path, monkeypatch):
    original = cli_fixture.child_environment

    def environment(path):
        result = original(path)
        startup = Path(result["PYTHONPATH"].split(":")[0]) / "sitecustomize.py"
        with startup.open("a") as handle:
            handle.write(
                "\nif os.environ.get('HEADROOM_EVALUATION_CONTEXT'):\n"
                "    from headroom import orchestrator as policy_orchestrator\n"
                "    previous_profile_reader = policy_orchestrator.read_live_profile\n"
                "    def selected_fixture_profile(*args, **kwargs):\n"
                "        profile = previous_profile_reader(*args, **kwargs)\n"
                "        profile.diagnosis_request_policy = 'final48-diagnosis-only-2000-v1'\n"
                "        return profile\n"
                "    policy_orchestrator.read_live_profile = selected_fixture_profile\n"
            )
        return result

    monkeypatch.setattr(cli_fixture, "child_environment", environment)
    _, run_id, values = cli_fixture.setup_case(tmp_path)
    result, receipt = cli_fixture.execute_case(tmp_path, values, mode="pipeline")
    assert result.returncode == 78, result.stderr
    assert receipt["invocation_kind"] == "installed_console_script"
    assert receipt["run_dispatched"] and receipt["result_saved"]
    store = Store(values[1])
    try:
        calls = store.llm_calls(run_id)
        assert len(calls) == 1 and calls[0]["settled"] is True
        body = calls[0]["request_evidence"]["payload"]
        # The synthetic CLI profile explicitly selects max_tokens, not the real account field.
        assert body["max_tokens"] == 2000 and "max_completion_tokens" not in body
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert "2000-token" in body["messages"][1]["content"]
        assert len([e for e in store.events(run_id) if e["kind"] == "run.started"]) == 1
        audit = Path(values[5])
        assert json.loads((audit / "01-initial-messages.json").read_text()) == body["messages"][1:]
        assert (
            json.loads((audit / "01-provenance.json").read_text())[
                "diagnosis_max_completion_tokens"
            ]
            == 2000
        )
    finally:
        store.close()
