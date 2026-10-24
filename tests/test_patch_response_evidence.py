"""Offline SDK evidence tests: no target execution, live keys or sockets."""

import dataclasses
import hashlib
import json
import stat
from pathlib import Path

import httpx
import pytest

from headroom.budget import BudgetExceeded
from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter, ResponseValidationError
from headroom.patch import PatchEngine
from headroom.patch_evidence import MAX_RESPONSE_ARTIFACT_BYTES, _publish


def router_for(text, calls, *, finish="stop", completion=100, reasoning=0, **client_options):
    models = candidate_models()
    models["super"] = dataclasses.replace(
        models["super"],
        capabilities=VerifiedCapabilities(
            reasoning_method="chat_template_kwargs", evidence="offline mock evidence only"
        ),
        output_cap_field="max_completion_tokens",
        evidence="offline cap fixture",
    )

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"x-secret-test-header": "NEVER_CAPTURE_HEADER"},
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": SUPER_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": {
                            "role": "assistant",
                            "content": text,
                            "reasoning_content": "NEVER_CAPTURE_HIDDEN_REASONING",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 200,
                    "completion_tokens": completion,
                    "total_tokens": 200 + completion,
                    "completion_tokens_details": {"reasoning_tokens": reasoning},
                },
            },
        )

    return LLMRouter(
        TokenFactoryClient(
            api_key="offline-key-must-not-be-recorded",
            config=RuntimeConfig(models=models),
            transport=httpx.MockTransport(handler),
            **client_options,
        )
    )


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source"
    path.mkdir()
    (path / "train.py").write_text("x = 1\n")
    return path


def run_engine(source, tmp_path, router, **options):
    try:
        return PatchEngine(router, **options).generate_and_apply(
            source, {"fix_id": "offline-fixture"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()


def artifacts(tmp_path):
    return sorted((tmp_path / "work").rglob("attempt-*-response.json"))


def test_rejected_diff_is_saved_verbatim_before_diff_validation(source, tmp_path):
    raw_diff = "not a unified diff\\nwith literal backslash n"
    parsed = {"diff": raw_diff, "env_changes": {}, "cli_changes": []}
    text = json.dumps(parsed)
    calls = []
    result = run_engine(source, tmp_path, router_for(text, calls), max_repairs=0)
    assert result.status == "rejected"
    assert result.attempts[0].detail == "diff must touch between one and twenty files"
    path = Path(result.attempts[0].response_artifact)
    record = json.loads(path.read_text())
    assert record["visible"]["text"] == text
    assert record["parsed"] == parsed
    assert record["diff"]["text"] == raw_diff
    assert record["diff"]["sha256"] == hashlib.sha256(raw_diff.encode()).hexdigest()
    assert record["validation"] == "schema_passed"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert calls[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert calls[0]["max_completion_tokens"] == 4000
    assert "max_tokens" not in calls[0]
    for secret in (
        "NEVER_CAPTURE_HIDDEN_REASONING",
        "NEVER_CAPTURE_HEADER",
        "offline-key-must-not-be-recorded",
    ):
        assert secret not in path.read_text()
    assert not record["diff"]["truncated"]
    assert (source / "train.py").read_text() == "x = 1\n"


@pytest.mark.parametrize(
    ("text", "finish", "completion", "reasoning", "reason"),
    [
        ("{broken", "stop", 100, 0, "invalid_json"),
        ("", "length", 4000, 4000, "truncated"),
        ('{"diff":3,"env_changes":{},"cli_changes":[]}', "stop", 100, 0, "schema_mismatch"),
    ],
)
def test_validation_failure_keeps_actual_response_protocol(
    source, tmp_path, text, finish, completion, reasoning, reason
):
    calls = []
    router = router_for(text, calls, finish=finish, completion=completion, reasoning=reasoning)
    result = run_engine(source, tmp_path, router, max_repairs=0)
    assert not result.applied and len(calls) == 1
    assert result.attempts[0].llm_usage["completion_tokens"] == completion
    record = json.loads(artifacts(tmp_path)[0].read_text())
    assert record["response_available"] is True
    assert record["visible"]["text"] == text
    assert record["finish_reason"] == finish
    assert record["usage"]["reasoning_tokens"] == reasoning
    assert record["validation"] == "failed"
    assert record["validation_reason"] == reason
    assert record["parsed"] is None and record["diff"] is None
    assert record["protocol_records"][0]["http_status"] == 200


@pytest.mark.parametrize("failure", [BudgetExceeded, KeyboardInterrupt])
def test_callback_failure_saves_only_available_protocol_and_propagates(source, tmp_path, failure):
    calls = []
    error = failure("must remain original")

    def after_record(record):
        raise error

    router = router_for("{}", calls, after_record=after_record)
    with pytest.raises(failure) as captured:
        run_engine(source, tmp_path, router)
    assert captured.value is error and len(calls) == 1
    record = json.loads(artifacts(tmp_path)[0].read_text())
    assert record["response_available"] is False
    assert record["visible"] is None and record["finish_reason"] is None
    assert record["protocol_records"][0]["http_status"] == 200
    assert record["protocol_records"][0]["usage"]["completion_tokens"] == 100
    assert record["error_type"] == failure.__name__


def test_pre_dispatch_failure_does_not_copy_previous_call_record(source, tmp_path):
    calls = []

    def before_attempt(*_args):
        if calls:
            raise BudgetExceeded("offline next admission refused")

    router = router_for(
        json.dumps({"diff": "invalid", "env_changes": {}, "cli_changes": []}),
        calls,
        before_attempt=before_attempt,
    )
    with pytest.raises(BudgetExceeded):
        run_engine(source, tmp_path, router)
    assert len(calls) == 1
    saved = [json.loads(p.read_text()) for p in artifacts(tmp_path)]
    assert len(saved) == 2
    assert len(saved[0]["protocol_records"]) == 1
    assert saved[1]["protocol_records"] == []
    assert saved[1]["visible"] is None and saved[1]["usage"] is None


def test_evidence_write_failure_never_retries_or_loses_original_validation_error(
    source, tmp_path, monkeypatch
):
    def failed(*_args, **_kwargs):
        raise OSError("offline write failure")

    monkeypatch.setattr("headroom.patch.save_patch_response", failed)
    calls = []
    with pytest.raises(ResponseValidationError) as captured:
        run_engine(source, tmp_path, router_for("{broken", calls))
    assert len(calls) == 1 and captured.value.response.usage.completion_tokens == 100
    assert "could not be saved" in captured.value.__notes__[0]


def test_large_unicode_response_is_bounded_with_full_hashes(source, tmp_path):
    diff = "字" * 200000
    parsed = {"diff": diff, "env_changes": {}, "cli_changes": []}
    text = json.dumps(parsed, ensure_ascii=False)
    calls = []
    result = run_engine(source, tmp_path, router_for(text, calls), max_repairs=0)
    assert not result.applied
    path = artifacts(tmp_path)[0]
    raw = path.read_bytes()
    record = json.loads(raw)
    assert len(raw) <= MAX_RESPONSE_ARTIFACT_BYTES
    assert record["parsed"] is None and record["parsed_omitted"]
    assert record["diff"]["utf8_bytes"] == len(diff.encode())
    assert record["diff"]["sha256"] == hashlib.sha256(diff.encode()).hexdigest()
    assert record["visible"]["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert record["diff"]["truncated"] and record["visible"]["truncated"]
    assert diff.startswith(record["diff"]["text"])
    assert text.startswith(record["visible"]["text"])


@pytest.mark.parametrize("kind", ["file", "parent", "ancestor", "existing"])
def test_private_writer_refuses_symlinks_and_existing_targets(tmp_path, kind):
    safe = tmp_path / "safe"
    safe.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    victim = outside / "victim"
    victim.write_text("do not change")
    path = safe / "attempt-1-response.json"
    if kind == "file":
        path.symlink_to(victim)
    elif kind == "parent":
        link = tmp_path / "linked"
        link.symlink_to(safe, target_is_directory=True)
        path = link / path.name
    elif kind == "ancestor":
        inner = safe / "inner"
        inner.mkdir(mode=0o700)
        link = tmp_path / "linked"
        link.symlink_to(safe, target_is_directory=True)
        path = link / "inner" / path.name
    else:
        path.write_text("existing evidence")
    with pytest.raises((OSError, ValueError)):
        _publish(path, b"{}\n")
    assert victim.read_text() == "do not change"
    if kind == "existing":
        assert path.read_text() == "existing evidence"
    assert not list(safe.glob(".*.tmp"))


def test_unverified_reasoning_refuses_before_network_without_repair_storm(source, tmp_path):
    def handler(_request):
        pytest.fail("Unverified capability must never dispatch")

    router = LLMRouter(TokenFactoryClient(transport=httpx.MockTransport(handler)))
    result = run_engine(source, tmp_path, router)
    assert len(result.attempts) == 1
    record = json.loads(artifacts(tmp_path)[0].read_text())
    assert record["error_type"] == "CapabilityNotVerified"
    assert record["protocol_records"] == []
