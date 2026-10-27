"""Offline diagnostic feedback fixtures; no GPU, provider or production database."""

import copy
import json
from types import SimpleNamespace

import pytest
from test_diagnosis_bounded_repair import payload, run
from test_diagnosis_output_recovery import sdk_fixture

from headroom import diagnose as diagnosis_module
from headroom.diagnose import validate_diagnosis
from headroom.llm import validation_history
from headroom.llm.cost import Usage
from headroom.llm.router import LLMRouter, ResponseValidationError, response_validation_metadata
from headroom.orchestrator import FixRequest, Services, run_fix
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket

    def denied(*_args, **_kwargs):
        pytest.fail("No network in diagnostic-feedback fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def validate(value, policy=None):
    return validate_diagnosis(
        value, evidence={"stack_catalog": {"stk": []}}, policy=policy or {}, required_saving_gb=0.5
    )


def trigger(result):
    data = json.loads(result.supplement_request.split("Errors: ", 1)[1])
    return next(
        x["precision_trigger"] for x in data["issues"] if x["code"] == "NUMERICS_CHANGE_FORBIDDEN"
    )


@pytest.mark.parametrize(
    ("title", "description", "field", "criterion"),
    [
        ("Enable BF16", "Keep workload.", "title", "unrecognized_precision_wording"),
        (
            "Existing memory",
            "Projection output falls to 2 GB BF16.",
            "description",
            "unrecognized_precision_wording",
        ),
        (
            "Keep BF16",
            "Cast all FP32 weights to that dtype.",
            "description",
            "precision_context_with_cast_or_dtype_action",
        ),
        (
            "Repair memory",
            "Switch from BF16 to FP16.",
            "description",
            "multiple_precision_mentions_in_clause",
        ),
    ],
)
def test_exact_trigger_location_is_feedback_not_permission(title, description, field, criterion):
    value = payload()
    value["plan"][0].update(title=title, description=description)
    before = copy.deepcopy(value)
    result = validate(value)
    item = trigger(result)
    assert not result.ready_for_patch
    assert item["path"] == "/plan/0/" + field and item["criterion"] == criterion
    assert item["clause"] in value["plan"][0][field]
    assert item["semantic_precision_change_proven"] is False
    assert item["content_is_untrusted_data"] is True
    assert value == before


def test_declared_impact_is_not_misreported_as_a_precision_word():
    value = payload()
    value["plan"][0]["numerics_impact"] = "minor"
    result = validate(value)
    item = trigger(result)
    assert not result.ready_for_patch
    assert item["path"] == "/plan/0/numerics_impact"
    assert item["criterion"] == "declared_numerics_impact" and item["value"] == "minor"
    assert "clause" not in item


def test_existing_preservation_whitelist_and_authorized_policy_are_unchanged():
    value = payload()
    value["plan"][0]["description"] = "Preserve existing BF16."
    assert validate(value).ready_for_patch
    value["plan"][0]["description"] = "Enable BF16."
    result = validate(value, {"allow_numerics_change": True})
    assert result.ready_for_patch and not result.issues


def test_trigger_excerpts_are_bounded_and_mark_truncation():
    step = SimpleNamespace(
        title="Repair", description="界" * 2000 + " BF16", numerics_impact="none"
    )
    item = diagnosis_module._precision_rejection_trigger(step, "/plan/0")
    assert item["clause_truncated"] is True
    assert len(json.dumps(item["clause"], ensure_ascii=False).encode()) <= 1024
    assert item["path"] == "/plan/0/description"


def test_secret_anywhere_in_pair_withholds_entire_precision_excerpt():
    value = payload()
    value["plan"][0].update(title="Enable BF16", description='api_key = "OFFLINE_SECRET_CANARY"')
    item = trigger(validate(value))
    assert item["status"] == "withheld" and "clause" not in item
    assert "CANARY" not in json.dumps(item)
    assert not validate(value).ready_for_patch


def test_bad_ancillary_precision_lookup_cannot_change_original_issue():
    item = diagnosis_module.DiagnosisIssue("NUMERICS_CHANGE_FORBIDDEN", "host error", "/plan/999")
    result = diagnosis_module._precision_issue_trigger(SimpleNamespace(plan=[]), item)
    assert result["precision_trigger"]["status"] == "unavailable"
    assert item.code == "NUMERICS_CHANGE_FORBIDDEN"


def error(reason="truncated", finish="length", number=1):
    return ResponseValidationError(
        "exception-secret-canary",
        reason=reason,
        response=SimpleNamespace(
            role="diagnose",
            finish_reason=finish,
            usage=Usage(number, 16, number + 16, cached_tokens=0, reasoning_tokens=12),
            text="raw-body-secret-canary",
            reasoning_content="hidden-secret-canary",
        ),
    )


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (("", "stop"), ('{"partial":', "length")),
        (('{"partial":', "length"), ("not-json", "stop")),
        (('{"partial":', "length"), ('{"partial-again":', "length")),
    ],
)
def test_terminal_exception_keeps_two_public_records_with_same_call_cap(first, second):
    requests = []
    with sdk_fixture([first, second, (json.dumps(payload()), "stop")], requests) as client:
        with pytest.raises(ResponseValidationError) as caught:
            run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert len(requests) == 2
    history = validation_history.response_validation_history(caught.value)
    assert history["status"] == "recorded"
    assert history["total_failures"] == 2 and history["omitted_failures"] == 0
    assert [x["request_index"] for x in history["failures"]] == [1, 2]
    assert [x["requested_reasoning"] for x in history["failures"]] == [True, first[1] != "length"]
    assert all(r["max_completion_tokens"] == 16384 for r in requests)
    assert requests[0]["model"] == requests[1]["model"]
    assert requests[0]["response_format"] == requests[1]["response_format"]
    assert "partial" not in json.dumps(history) and "not-json" not in json.dumps(history)


def test_filtered_response_still_never_uses_the_supplement():
    requests = []
    with sdk_fixture(
        [("private-body", "content_filter"), (json.dumps(payload()), "stop")], requests
    ) as client:
        with pytest.raises(ResponseValidationError) as caught:
            run(LLMRouter(client))
        assert len(client.ledger.entries) == 1
    assert len(requests) == 1
    history = validation_history.response_validation_history(caught.value)
    assert history["total_failures"] == 1
    assert history["failures"][0]["error_reason"] == "filtered"


def test_history_uses_at_most_two_even_for_legacy_explicit_larger_allowance():
    class Router:
        calls = 0

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            raise error(number=self.calls)

    router = Router()
    with pytest.raises(ResponseValidationError) as caught:
        run(router, max_supplements=3)
    history = validation_history.response_validation_history(caught.value)
    assert router.calls == 4  # Existing explicit test allowance, never increased.
    assert len(history["failures"]) == 2
    assert history["total_failures"] == 4 and history["omitted_failures"] == 2
    assert [v["request_index"] for v in history["failures"]] == [3, 4]


@pytest.mark.parametrize(
    "bad", ["SECRET_CANARY", True, -1, float("nan"), 2**70, {"hidden": "CANARY"}]
)
def test_history_usage_and_mode_cannot_echo_arbitrary_values(bad):
    final = error()
    previous = response_validation_metadata(error("invalid_json", "stop"))
    previous.update(
        text="raw-secret-canary",
        reasoning_content="hidden-secret-canary",
        error_reason=bad,
        finish_reason=bad,
        role=bad,
        request_index=bad,
        requested_reasoning=bad,
    )
    previous["usage"] = {k: bad for k in previous["usage"]}
    validation_history.attach_validation_failure_history(
        final, [previous, response_validation_metadata(final)]
    )
    result = validation_history.response_validation_history(final)
    first = result["failures"][0]
    assert first["error_reason"] == "unknown"
    assert first["finish_reason"] is None and first["role"] is None
    assert all(v is None for v in first["usage"].values())
    assert "canary" not in json.dumps(result).lower()
    assert len(result["failures"]) <= 2


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h: h.update(failures=h["failures"] * 3),
        lambda h: h.update(failures=[]),
        lambda h: h.update(total_failures=True),
        lambda h: h.update(omitted_failures=-1),
        lambda h: h["failures"][-1].update(error_reason="empty_json"),
        lambda h: h["failures"][-1]["usage"].update(completion_tokens=99),
    ],
)
def test_malformed_or_wrong_final_history_falls_back_without_inventing_total(mutation):
    final = error()
    validation_history.attach_validation_failure_history(
        final, [response_validation_metadata(final)]
    )
    mutation(final._headroom_validation_history)
    result = validation_history.response_validation_history(final)
    assert result["status"] == "last_error_only"
    assert result["total_failures"] is None and result["omitted_failures"] is None
    assert len(result["failures"]) == 1
    assert result["failures"][0]["error_reason"] == "truncated"


def test_terminal_event_persists_both_errors_without_gpu_or_body(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("VALUE = 1\n")
    requests = []
    with sdk_fixture(
        [('{"body-canary":', "length"), ("body-canary-invalid", "stop")], requests
    ) as client:

        def runtime(*_args, **_kwargs):
            return run(LLMRouter(client))

        def forbidden(*_args, **_kwargs):
            pytest.fail("No GPU/baseline may run in this fixture")

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
            assert len(events) == 1 and result["status"] == "failed"
            history = events[0]["response_validation_history"]
            assert [r["error_reason"] for r in history["failures"]] == ["truncated", "invalid_json"]
            assert [r["requested_reasoning"] for r in history["failures"]] == [True, False]
            assert "canary" not in json.dumps(events).lower()
            assert store.usage(result["run_id"])["calls"] == 0
            assert len(requests) == len(client.ledger.entries) == 2
        finally:
            store.close()


def test_new_precision_feedback_uses_only_existing_semantic_supplement():
    bad = payload()
    bad["plan"][0]["description"] = "Use BF16 for all model weights."
    requests = []
    with sdk_fixture(
        [(json.dumps(bad), "stop"), (json.dumps(payload()), "stop")], requests
    ) as client:
        result = run(LLMRouter(client))
        assert len(client.ledger.entries) == 2
    assert result.ready_for_patch and len(requests) == 2
    content = requests[1]["messages"][-1]["content"]
    assert "precision_trigger" in content and "unrecognized_precision_wording" in content
    assert all(r["chat_template_kwargs"]["enable_thinking"] is True for r in requests)
    assert all(r["max_completion_tokens"] == 16384 for r in requests)
