"""Bounded application-level correction with real SDK/router and isolated budgets."""

import copy
import dataclasses
import json
import pickle
import socket
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from test_snapshot_diagnosis import diagnosis, native_snapshot

import headroom.snapshot_diagnosis as core
from headroom.budget import BudgetLedger
from headroom.config import (
    ULTRA_MODEL,
    Pricing,
    RuntimeConfig,
    VerifiedCapabilities,
    candidate_models,
)
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter
from headroom.snapshot_diagnosis import (
    SnapshotDiagnosisRequest,
    SnapshotServices,
    run_snapshot_diagnosis,
)


@pytest.fixture(autouse=True)
def deny_live(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Correction tests cannot access network or live runtime")

    monkeypatch.setattr(core, "_live_runtime", denied)
    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)


class Factory:
    def __init__(self, outcomes, *, deny_second=False):
        self.outcomes = outcomes
        self.requests = []
        self.admissions = []
        self.deny_second = deny_second

    def __call__(self, run_id, store, directory):
        evidence = json.loads((directory / "evidence.json").read_text())
        ref = evidence["presentation"]["peak_stack_ids"][0]
        base = diagnosis(ref)
        base["root_causes"][0].pop("bytes_gb")
        base.update(plan=[], needs_more_info=True)
        self.budget = BudgetLedger(
            directory / "isolated-budget.db", daily_limit=".25", total_limit=".25"
        )
        self.budget.open_run(
            run_id, ".0052" if self.deny_second else ".25", budget_mode="strict_reservation"
        )
        pending = {}

        def before(role, spec, attempt, body):
            attempt_id = uuid4().hex
            self.admissions.append(attempt_id)
            self.budget.reserve(run_id, attempt_id, ".005", dispatched=False)
            self.budget.mark_dispatched(run_id, attempt_id)
            pending["id"] = attempt_id

        def after(record):
            self.budget.settle(run_id, pending.pop("id"), record.cost.usd)

        def respond(request):
            body = json.loads(request.content)
            self.requests.append(body)
            position = len(self.requests) - 1
            assert position < len(self.outcomes), "Unexpected extra model dispatch"
            outcome = self.outcomes[position]
            if outcome == "transport":
                raise httpx.ReadTimeout("offline transport fixture")
            if outcome == "http":
                return httpx.Response(503, json={"error": {"message": "offline failure"}})
            payload = copy.deepcopy(base)
            if outcome == "schema":
                payload["root_causes"][0]["bytes_gb"] = 3.36
            elif outcome == "semantic":
                payload["plan"] = [
                    {
                        "fix_id": "p1",
                        "type": "code",
                        "title": "Change workload",
                        "description": "Reduce batch size to one.",
                        "expected_saving_gb": 0.1,
                        "numerics_impact": "none",
                        "throughput_impact": "none",
                        "risk": "Unverified",
                        "requires_policy": [],
                    }
                ]
            elif outcome in {"prose", "unknown"}:
                payload["notes"].append("3.36 GB live")
            usage = (
                None
                if outcome == "unknown"
                else {
                    "prompt_tokens": 200,
                    "completion_tokens": 100,
                    "total_tokens": 300,
                }
            )
            return httpx.Response(
                200,
                json={
                    "id": "offline-correction",
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
                    "usage": usage,
                },
            )

        models = candidate_models()
        models["ultra"] = dataclasses.replace(
            models["ultra"],
            capabilities=VerifiedCapabilities(
                reasoning_method="chat_template_kwargs", evidence="offline fixture"
            ),
            pricing=Pricing("1", "1", verified=True, source="synthetic unit-test tariff"),
        )
        client = TokenFactoryClient(
            config=RuntimeConfig(models=models),
            transport=httpx.MockTransport(respond),
            before_attempt=before,
            after_record=after,
            max_http_retries=0,
        )
        self.client = client

        def close():
            client.close()
            self.budget.close_run(run_id)

        return SimpleNamespace(router=LLMRouter(client), client=client, close=close)


def execute(tmp_path, outcomes, **options):
    upload = tmp_path / "input.pickle"
    upload.write_bytes(pickle.dumps(native_snapshot()))
    factory = Factory(outcomes, **options)
    result = run_snapshot_diagnosis(
        SnapshotDiagnosisRequest(snapshot=upload, budget_usd=".25"),
        run_root=tmp_path / "jobs",
        run_id="b" * 32,
        services=SnapshotServices(runtime_factory=factory),
    )
    return result, factory, tmp_path / "jobs" / ("b" * 32) / "private"


def test_valid_unknown_is_not_retried_or_forced_into_patch(tmp_path):
    result, factory, private = execute(tmp_path, ["valid"])
    assert len(factory.requests) == len(factory.admissions) == 1
    assert result["status"] == "needs_human" and result["diagnosis"] is not None
    assert result["diagnosis"]["needs_more_info"] is True and result["patch"]["diff"] is None
    assert (
        json.loads((private / "diagnosis-correction.json").read_text())["attempts"][0]["outcome"]
        == "valid"
    )


@pytest.mark.parametrize("initial", ["semantic", "schema", "prose"])
def test_invalid_then_correct_gets_one_precise_correction_with_separate_admissions(
    tmp_path, initial
):
    result, factory, private = execute(tmp_path, [initial, "valid"])
    assert len(factory.requests) == len(factory.admissions) == 2
    assert len(set(factory.admissions)) == 2
    assert result["diagnosis"] is not None and result["diagnosis"]["needs_more_info"] is True
    assert Decimal(str(result["cost_usd"])) == Decimal(".0006")
    for request in factory.requests:
        assert request["max_tokens"] == 2000
        assert request["chat_template_kwargs"]["enable_thinking"] is False
    first, second = private / "diagnosis-attempts/1", private / "diagnosis-attempts/2"
    feedback = json.loads((first / "correction-feedback.json").read_text())
    assert feedback["policy"]["allow_batch_change"] is False
    assert all({"code", "path", "message"} <= set(item) for item in feedback["issues"])
    assert "deleting requires_policy" in feedback["instructions"]
    assert "Do not clear genuine needs_more_info" in feedback["instructions"]
    assert factory.requests[1]["messages"][-2]["role"] == "assistant"
    assert json.loads(factory.requests[1]["messages"][-1]["content"]) == feedback
    assert (first / "diagnosis-validation.json").is_file()
    assert (second / "snapshot-intent.json").is_file()
    assert (private / "snapshot-intent.json").read_bytes() == (
        second / "snapshot-intent.json"
    ).read_bytes()
    assert (first / "correction-feedback.json").stat().st_mode & 0o777 == 0o600
    if initial == "schema":
        assert "3.36" in (first / "model-error.json").read_text()
    else:
        saved = json.loads((first / "snapshot-intent.json").read_text())["intent"]
        assert saved["plan"] or "3.36 GB live" in saved["notes"]


def test_invalid_twice_stops_without_third_request_or_clearing_policy_blocker(tmp_path):
    result, factory, private = execute(tmp_path, ["semantic", "semantic"])
    assert len(factory.requests) == 2
    assert result["status"] == "needs_human" and result["diagnosis"] is None
    history = json.loads((private / "diagnosis-correction.json").read_text())["attempts"]
    assert len(history) == 2 and history[-1]["correction_scheduled"] is False
    assert all((private / f"diagnosis-attempts/{n}/snapshot-intent.json").is_file() for n in (1, 2))


def test_second_request_budget_denied_before_any_additional_dispatch(tmp_path):
    result, factory, private = execute(tmp_path, ["prose"], deny_second=True)
    assert len(factory.admissions) == 2 and len(factory.requests) == 1
    assert result["status"] == "budget_exceeded" and result["diagnosis"] is None
    assert Decimal(str(result["cost_usd"])) == Decimal(".0003")
    assert (private / "diagnosis-attempts/1/snapshot-intent.json").is_file()
    stopped = json.loads((private / "diagnosis-attempts/2/stopped.json").read_text())
    assert stopped["error_type"] == "BudgetExceeded"


@pytest.mark.parametrize("outcome", ["transport", "http", "unknown"])
def test_transport_http_or_unknown_cost_cannot_start_a_correction(tmp_path, outcome):
    result, factory, private = execute(tmp_path, [outcome])
    assert len(factory.requests) == len(factory.admissions) == 1
    assert result["diagnosis"] is None and result["cost_usd"] is None
    assert not (private / "diagnosis-attempts/2").exists()
    assert len(factory.client.ledger.entries) == 1


def test_second_schema_failure_retains_both_responses_and_compatible_final_error(tmp_path):
    result, factory, private = execute(tmp_path, ["schema", "schema"])
    assert len(factory.requests) == 2
    assert result["status"] == "failed" and result["diagnosis"] is None
    assert (private / "model-error.json").is_file()
    for number in (1, 2):
        assert (private / f"diagnosis-attempts/{number}/model-error.json").is_file()


def test_filtered_response_is_not_treated_as_a_correctable_schema_error():
    from headroom.snapshot_feedback import correction_messages

    response = SimpleNamespace(text="filtered response", finish_reason="content_filter")
    assert correction_messages(
        [], response, [{"code": "INTENT_RESPONSE_FILTERED", "path": "/"}], {}
    ) == (None, None)


def test_real_failed_s2_fixture_gets_specific_feedback_in_actual_sdk_messages(tmp_path):
    from pathlib import Path

    from headroom.snapshot_intent import build_snapshot_intent_schema

    saved = json.loads(
        (Path(__file__).parent / "fixtures/snapshot_s2_feedback_error.json").read_text()
    )
    original = saved["intent"]
    corrected = copy.deepcopy(original)
    corrected["root_causes"][2]["title"] = "Optimizer update temporary buffers"
    corrected["notes"][0] = (
        "Optimizer states, parameters and temporary workspaces occupy the reconstructed peak."
    )
    corrected["notes"][1] = (
        "The cache-gap proxy is high, but harmful fragmentation is not confirmed."
    )
    for request in corrected["evidence_requests"][:2]:
        request["evidence_ref"] = "execution_context.runtime_input_observations"
        request["source_line_start"] = request["source_line_end"] = None
    prepared_evidence = saved["evidence"]
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(prepared_evidence))
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        assert len(requests) <= 2
        value = original if len(requests) == 1 else corrected
        return httpx.Response(
            200,
            json={
                "id": "offline-real-failure-fixture",
                "object": "chat.completion",
                "created": 0,
                "model": ULTRA_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(value)},
                    }
                ],
                "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
            },
        )

    models = candidate_models()
    models["ultra"] = dataclasses.replace(
        models["ultra"],
        capabilities=VerifiedCapabilities(
            reasoning_method="chat_template_kwargs", evidence="offline fixture"
        ),
        pricing=Pricing("1", "1", verified=True, source="synthetic unit-test tariff"),
    )
    client = TokenFactoryClient(
        config=RuntimeConfig(models=models),
        transport=httpx.MockTransport(respond),
        max_http_retries=0,
    )
    try:
        runtime = SimpleNamespace(client=client, router=LLMRouter(client))
        verdict, grounding = core._diagnose_with_correction(
            runtime,
            [
                {"role": "system", "content": core.SNAPSHOT_PROMPT.read_text()},
                {
                    "role": "user",
                    "content": "Offline fixed evidence fixture; not a real model run.",
                },
            ],
            build_snapshot_intent_schema(evidence=prepared_evidence, policy=saved["policy"]),
            prepared_evidence,
            {"policy": saved["policy"], "evidence_json": str(evidence_path)},
            private,
        )
    finally:
        client.close()
    assert verdict.valid and not grounding
    assert verdict.diagnosis.needs_more_info is True
    assert len(verdict.diagnosis.evidence_requests) == len(original["evidence_requests"])
    assert len(requests) == 2
    feedback = json.loads(requests[1]["messages"][-1]["content"])
    saved_feedback = json.loads(
        (private / "diagnosis-attempts/1/correction-feedback.json").read_text()
    )
    assert feedback == saved_feedback
    errors = {x["path"]: x for x in feedback["issues"]}
    assert set(errors) == set(saved["expected_issue_paths"])
    for path in ("/evidence_requests/0", "/evidence_requests/1"):
        issue = errors[path]
        assert (
            issue["message"]
            == "The exact declared source range or field is visible in this request; semantics may remain ambiguous."
        )
        assert issue["declared_reference_observation"]["availability"] == "visible"
        assert issue["declared_reference_observation"]["runtime_values_verified"] is False
        assert issue["advertised_unknown_runtime_reference"]["availability"] == "unknown"
        assert "runtime value" in issue["required_change"]
        assert "Preserve the real missing value" in issue["required_change"]
        assert '"evidence_ref": "source[0]"' in issue["offending_field"]["excerpt"]
    assert errors["root_causes[2].title"]["memory_mentions"] == ["9 GB"]
    assert errors["notes[0]"]["memory_mentions"]
    assert "qualitatively" in errors["notes[0]"]["required_change"]
    retained = json.loads((private / "diagnosis-attempts/1/snapshot-intent.json").read_text())
    assert retained["intent"] == original
    assert "peak at ~9 GB" in retained["intent"]["root_causes"][2]["title"]


def test_feedback_does_not_invent_visible_source_when_catalog_says_unknown():
    from headroom.snapshot_feedback import correction_messages

    value = {"evidence_requests": [{"evidence_ref": "source[0]", "reason": "missing"}]}
    evidence = {
        "evidence_availability_catalog": {
            "schema": "headroom.evidence_availability.v1",
            "entries": [
                {
                    "evidence_ref": "source[0]",
                    "availability": "unknown",
                    "runtime_values_verified": False,
                }
            ],
        }
    }
    _, feedback = correction_messages(
        [],
        SimpleNamespace(text=json.dumps(value), finish_reason="stop"),
        [
            {
                "code": "EVIDENCE_AVAILABILITY_CONTRADICTED",
                "path": "/evidence_requests/0",
                "message": "Fixture issue.",
            }
        ],
        {},
        evidence=evidence,
    )
    issue = feedback["issues"][0]
    assert issue["declared_reference_observation"]["availability"] == "unknown"
    assert "required_change" not in issue
