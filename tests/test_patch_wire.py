"""Wire-array tests use real SDK/router and static Git/compile, never live models."""

import dataclasses
import hashlib
import json
import socket
import stat
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from headroom.config import SUPER_MODEL, RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter
from headroom.patch import PatchEngine, PatchProposal, PatchWireProposal

LINES = ["--- a/train.py", "+++ b/train.py", "@@ -1 +1 @@", "-x = 1", "+x = 2"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No network or DNS in wire protocol tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def wire(lines=(), **extra):
    return {"diff_lines": list(lines), "env_changes": {}, "cli_changes": [], "notes": [], **extra}


def run_wire(tmp_path, payloads, *, max_repairs=0, base_cli=()):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("x = 1\n")
    models = candidate_models()
    models["super"] = dataclasses.replace(
        models["super"],
        output_cap_field="max_completion_tokens",
        evidence="offline wire fixture",
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="offline mock only, not real capability evidence",
        ),
    )
    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        payload = payloads[min(len(calls) - 1, len(payloads) - 1)]
        return httpx.Response(
            200,
            json={
                "id": "offline-wire",
                "object": "chat.completion",
                "created": 0,
                "model": SUPER_MODEL,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": json.dumps(payload)},
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
            },
        )

    with TokenFactoryClient(
        api_key="offline-not-a-real-key",
        config=RuntimeConfig(models=models),
        transport=httpx.MockTransport(respond),
    ) as client:
        result = PatchEngine(LLMRouter(client), max_repairs=max_repairs).generate_and_apply(
            source,
            {"fix_id": "generic-offline-fixture"},
            work_root=tmp_path / "work",
            base_cli=base_cli,
        )
    return result, calls, source


def test_wire_is_separate_from_unchanged_public_contract():
    public = PatchProposal.model_json_schema()
    schema = PatchWireProposal.model_json_schema()
    assert "diff" in public["properties"] and "diff_lines" not in public["properties"]
    assert "diff_lines" in schema["properties"] and "diff" not in schema["properties"]
    assert schema["additionalProperties"] is False
    assert "pattern" not in json.dumps(schema)
    assert PatchProposal(diff="", env_changes={}, cli_changes=[]).diff == ""
    assert PatchWireProposal(**wire()).to_proposal().diff == ""


def test_normalization_preserves_whitespace_and_literal_source_escapes():
    lines = ["--- a/train.py", "+++ b/train.py", "@@ -1 +1 @@", r'-s = "\n"', r'+s = "\t"']
    value = PatchWireProposal(**wire(lines)).to_proposal()
    assert value.diff == "\n".join(lines) + "\n"
    assert r'"\n"' in value.diff  # Legitimate source text is never unescaped.
    assert value.diff.count("\n") == len(lines)


@pytest.mark.parametrize("item", ["a\nb", "a\rb", "a\r\nb"])
def test_embedded_line_separators_are_rejected_locally(item):
    with pytest.raises(ValidationError):
        PatchWireProposal(**wire([item]))


@pytest.mark.parametrize("lines", ["not-an-array", None, [1], [True], [None], [[]]])
def test_strict_wire_types(lines):
    with pytest.raises(ValidationError):
        PatchWireProposal.model_validate({**wire(), "diff_lines": lines}, strict=True)


@pytest.mark.parametrize("extra", [{"diff": ""}, {"unexpected": True}])
def test_legacy_or_unknown_fields_do_not_trigger_implicit_conversion(extra):
    with pytest.raises(ValidationError):
        PatchWireProposal.model_validate({**wire(), **extra}, strict=True)


def test_original_joined_character_limit_remains():
    exact = PatchWireProposal(**wire(["a" * 511999])).to_proposal()
    assert len(exact.diff) == 512000
    for lines in (["a" * 512000], ["a" * 255999, "b" * 256000]):
        with pytest.raises(ValidationError):
            PatchWireProposal(**wire(lines))


def test_actual_sdk_router_engine_apply_and_compile_with_hash_linked_evidence(tmp_path):
    payload = wire(LINES)
    result, calls, source = run_wire(tmp_path, [payload])
    assert result.applied and result.attempts[0].compile_exit_code == 0
    assert (Path(result.candidate_dir) / "train.py").read_text() == "x = 2\n"
    assert (source / "train.py").read_text() == "x = 1\n"
    assert len(calls) == 1
    sent = calls[0]
    assert sent["model"] == SUPER_MODEL
    assert sent["max_completion_tokens"] == 4000
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}
    schema = sent["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["diff_lines"]["type"] == "array"
    assert "diff" not in schema["properties"]
    assert "pattern" not in json.dumps(schema)
    path = Path(result.attempts[0].response_artifact)
    artifact = json.loads(path.read_text())
    normalized = PatchWireProposal(**payload).to_proposal().model_dump()
    expected = "\n".join(LINES) + "\n"
    assert artifact["parsed"] == payload
    assert json.loads(artifact["visible"]["text"]) == payload
    assert artifact["diff"] is None
    assert artifact["normalized_proposal"] == normalized
    assert artifact["normalized_diff"]["text"] == expected
    assert Path(result.patch_path).read_text() == expected
    transformation = artifact["normalization"]
    assert transformation["algorithm"] == "diff_lines_join_lf_v1"
    assert transformation["line_count"] == len(LINES) and transformation["terminal_lf"]
    assert (
        transformation["source_parsed_sha256"]
        == hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
    )
    assert (
        transformation["output_proposal_sha256"]
        == hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
    )
    assert transformation["output_diff_sha256"] == hashlib.sha256(expected.encode()).hexdigest()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert len(path.read_bytes()) <= 256 * 1024
    assert result.runtime_verified is False


@pytest.mark.parametrize("flat", ["".join(LINES), r"\n".join(LINES)])
def test_flat_or_literal_newline_string_is_never_repaired(tmp_path, flat):
    result, calls, source = run_wire(tmp_path, [wire([flat])])
    assert not result.applied and len(calls) == 1
    assert result.attempts[0].detail == "diff must touch between one and twenty files"
    artifact = json.loads(Path(result.attempts[0].response_artifact).read_text())
    assert artifact["parsed"]["diff_lines"] == [flat]
    assert artifact["normalized_diff"]["text"] == flat + "\n"
    assert artifact["normalized_diff"]["text"].count("\n") == 1
    assert (source / "train.py").read_text() == "x = 1\n"


@pytest.mark.parametrize(
    ("extra", "base_cli"),
    [
        ({"env_changes": {"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}}, ()),
        ({"cli_changes": ["--batch_size", "2"]}, ("--batch_size", "4")),
    ],
)
def test_empty_wire_array_preserves_approved_env_or_cli_only_proposals(tmp_path, extra, base_cli):
    result, calls, _ = run_wire(tmp_path, [wire(**extra)], base_cli=base_cli)
    assert result.applied and len(calls) == 1
    artifact = json.loads(Path(result.attempts[0].response_artifact).read_text())
    assert artifact["normalized_proposal"]["diff"] == ""
    assert artifact["normalization"]["line_count"] == 0
    assert artifact["normalization"]["terminal_lf"] is False
    if extra.get("cli_changes"):
        assert result.effective_cli == ("--batch_size", "2")
    else:
        assert result.env_changes == extra["env_changes"]


def test_empty_array_does_not_bypass_no_change_policy(tmp_path):
    result, calls, _ = run_wire(tmp_path, [wire()])
    assert not result.applied and result.reason == "NO_CHANGE" and len(calls) == 1


def test_embedded_lf_failure_is_preserved_and_can_use_only_existing_repair_slot(tmp_path):
    bad = wire(["\n".join(LINES)])
    result, calls, _ = run_wire(tmp_path, [bad, wire(LINES)], max_repairs=1)
    assert result.applied and len(calls) == 2 and len(result.attempts) == 2
    first = json.loads(Path(result.attempts[0].response_artifact).read_text())
    assert json.loads(first["visible"]["text"]) == bad
    assert first["validation_reason"] == "schema_mismatch"
    assert first["normalization"]["status"] == "not_applied"
    assert first["normalized_proposal"] is None
    assert result.attempts[0].reason == "LLM_RESPONSE_REJECTED"
    assert all(call["max_completion_tokens"] == 4000 for call in calls)


def test_four_failed_wire_responses_use_no_extra_repair_calls(tmp_path):
    result, calls, _ = run_wire(tmp_path, [wire(["bad\nline"])], max_repairs=3)
    assert not result.applied and len(calls) == len(result.attempts) == 4
    assert all(a.reason == "LLM_RESPONSE_REJECTED" for a in result.attempts)


def test_original_parser_byte_limit_is_still_enforced(tmp_path):
    result, calls, _ = run_wire(tmp_path, [wire(["字" * 180000])])
    assert not result.applied and len(calls) == 1
    assert result.attempts[0].reason == "UNSAFE_OR_INVALID_PATCH"
    artifact = json.loads(Path(result.attempts[0].response_artifact).read_text())
    assert artifact["normalization"]["status"] == "applied"
    assert artifact["normalized_diff"]["utf8_bytes"] > 512000
    assert artifact["normalized_diff"]["truncated"]
