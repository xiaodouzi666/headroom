"""Prompt audit boundaries; no HTTP, DNS, credentials, or model execution."""

import builtins
import copy
import hashlib
import json
import os
import socket
from pathlib import Path

import pytest

from headroom.llm.preflight import (
    ASSET_HASHES,
    MODEL_ID,
    TOKENIZER_REVISION,
    PreflightRefused,
    PromptAuditor,
    load_request,
    validate_request,
)
from scripts.audit_prompt_tokens import main

ASSET_DIR = (
    Path(__file__).resolve().parents[1] / ".cache/tokenizers/nemotron-3-ultra" / TOKENIZER_REVISION
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Network is forbidden in prompt audit tests")

    for name in ("getaddrinfo", "create_connection"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, name, denied)


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    original_getitem = type(os.environ).__getitem__
    original_open = builtins.open
    original_path_open = Path.open

    def env_getitem(self, name):
        if name in {"NEBIUS_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"}:
            raise AssertionError("Credential read is forbidden")
        return original_getitem(self, name)

    def guarded_open(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)) and Path(file).name.startswith(".env"):
            raise AssertionError("dotenv read is forbidden")
        return original_open(file, *args, **kwargs)

    def guarded_path_open(self, *args, **kwargs):
        if self.name.startswith(".env"):
            raise AssertionError("dotenv read is forbidden")
        return original_path_open(self, *args, **kwargs)

    monkeypatch.setattr(type(os.environ), "__getitem__", env_getitem)
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)


@pytest.fixture
def auditor(no_network, no_credentials):
    if not all((ASSET_DIR / name).is_file() for name in ASSET_HASHES):
        pytest.skip("Install the explicitly pinned tokenizer assets for integration tests")
    return PromptAuditor(ASSET_DIR)


def request():
    return {
        "model": MODEL_ID,
        "messages": [{"role": "user", "content": "Reply OK."}],
        "max_completion_tokens": 128,
    }


def test_exact_local_render_and_no_provider_claim(auditor):
    report = auditor.audit(request())
    expected = (
        "<|im_start|>system\n<|im_end|>\n"
        "<|im_start|>user\nReply OK.<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n"
    )
    assert report["local_template"]["sha256"] == hashlib.sha256(expected.encode()).hexdigest()
    assert report["local_template"]["tokens"] == len(
        auditor.tokenizer.encode(expected, add_special_tokens=False)
    )
    assert report["provider_billable_token_ceiling"] is None
    assert report["provider_cost_upper_usd"] is None
    assert report["provider_tokenizer_match_verified"] is False
    assert report["live_authorized"] is False
    assert report["tokenizer"]["revision"] == TOKENIZER_REVISION
    assert {k: v["sha256"] for k, v in report["tokenizer"]["assets"].items()} == ASSET_HASHES


def test_full_request_domains_and_schema_not_added_as_prompt(auditor):
    body = request()
    body.update(
        {
            "messages": [
                {"role": "system", "content": "Return JSON. private-marker-761"},
                {"role": "user", "content": "Inspect 中文 GPU code."},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "inspect",
                        "description": "Inspect code",
                        "strict": True,
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Relative path"}
                            },
                            "required": ["path"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "result",
                    "strict": True,
                    "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                },
            },
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
            "temperature": 0,
            "timeout": 600,
        }
    )
    untouched = copy.deepcopy(body)
    report = auditor.audit(body)
    assert body == untouched
    assert "private-marker-761" not in json.dumps(report)
    assert set(report["request_fields"]) == set(body) - {"extra_body"} | {"chat_template_kwargs"}
    assert report["extra_schema"]["serialized_json_local_tokens_estimate"] > 0
    assert report["provider_only_unmodeled_fields"] == ["response_format"]
    without_schema = copy.deepcopy(body)
    without_schema.pop("response_format")
    assert report["local_template"] == auditor.audit(without_schema)["local_template"]
    without_tools = copy.deepcopy(body)
    without_tools.pop("tools")
    assert (
        report["local_template"]["tokens"]
        > auditor.audit(without_tools)["local_template"]["tokens"]
    )


def test_sdk_and_wire_forms_have_same_domain_hash_and_render(auditor):
    sdk = request()
    sdk["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    wire = request()
    wire["chat_template_kwargs"] = {"enable_thinking": False}
    a, b = auditor.audit(sdk), auditor.audit(wire)
    assert a["request"] == b["request"]
    assert a["local_template"] == b["local_template"]
    assert a["input_form"] == "sdk_kwargs"
    assert b["input_form"] == "wire_json"


def test_template_reasoning_and_history_controls(auditor):
    body = request()
    base = auditor.audit(body)
    body["chat_template_kwargs"] = {"enable_thinking": False}
    assert auditor.audit(body)["local_template"]["sha256"] != base["local_template"]["sha256"]
    body["chat_template_kwargs"] = {"medium_effort": True}
    assert auditor.audit(body)["local_template"]["tokens"] > base["local_template"]["tokens"]
    body["messages"] = [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "Done", "reasoning_content": "private thought " * 50},
        {"role": "user", "content": "Second"},
    ]
    body["chat_template_kwargs"] = {"truncate_history_thinking": True}
    truncated = auditor.audit(body)
    body["chat_template_kwargs"]["truncate_history_thinking"] = False
    assert auditor.audit(body)["local_template"]["tokens"] > truncated["local_template"]["tokens"]


def test_provider_reasoning_controls_remain_unmodeled(auditor):
    body = request()
    body["extra_body"] = {"reasoning_effort": "high", "reasoning_budget": 64}
    report = auditor.audit(body)
    assert report["provider_only_unmodeled_fields"] == ["reasoning_budget", "reasoning_effort"]
    assert report["local_template"] == auditor.audit(request())["local_template"]
    assert report["provider_billable_token_ceiling"] is None


def test_historical_tool_ids_are_accounted_but_not_claimed_rendered(auditor):
    body = request()
    body["messages"] = [
        {"role": "user", "content": "Inspect"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "inspect", "arguments": {"path": "train.py"}},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
    ]
    first = auditor.audit(body)
    assert first["historical_tool_id_fields_ignored_by_local_template"] == 2
    body["messages"][1]["tool_calls"][0]["id"] = "different_id"
    second = auditor.audit(body)
    assert first["local_template"] == second["local_template"]
    assert first["request"]["compact_json_sha256"] != second["request"]["compact_json_sha256"]


@pytest.mark.parametrize(
    "change",
    [
        {"model": "nvidia/other"},
        {"unknown-private-field": "secret"},
        {"max_tokens": 128},
        {"max_completion_tokens": True},
        {"max_completion_tokens": None},
        {"n": 2},
        {"n": True},
        {"extra_body": {"unknown": "secret"}},
        {"extra_body": {"max_completion_tokens": 1}},
        {"chat_template_kwargs": {"add_generation_prompt": False}},
        {"chat_template_kwargs": {"enable_thinking": "false"}},
        {"reasoning_effort": "invented"},
        {"reasoning_budget": 0},
        {"response_format": {"type": ["json_schema"]}},
        {"response_format": {"type": "json_schema", "json_schema": {"name": "x"}}},
        {"messages": [{"role": "developer", "content": "x"}]},
        {"messages": [{"role": "user", "content": [{"type": "text", "text": "x"}]}]},
        {"messages": [{"role": "user", "content": "x", "unknown": "secret"}]},
        {"messages": [{"role": "assistant", "content": None}]},
        {
            "messages": [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "type": "function",
                            "function": {"name": "f", "arguments": "{}"},
                        }
                    ],
                }
            ]
        },
        {"temperature": float("nan")},
        {
            "tools": [
                {"type": "function", "function": {"name": "x", "parameters": {}, "unknown": 1}}
            ]
        },
    ],
)
def test_rejects_unknown_ambiguous_or_unsupported_inputs(change):
    body = request()
    body.update(change)
    with pytest.raises(PreflightRefused) as caught:
        validate_request(body)
    assert "secret" not in str(caught.value)
    assert "unknown-private-field" not in str(caught.value)


def test_rejects_duplicate_wire_and_sdk_field_and_reasoning_selectors():
    body = request()
    body.update(
        {
            "chat_template_kwargs": {"enable_thinking": True},
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
    )
    with pytest.raises(PreflightRefused, match="Duplicate"):
        validate_request(body)
    body.pop("extra_body")
    body["reasoning_effort"] = "high"
    with pytest.raises(PreflightRefused, match="Combined"):
        validate_request(body)


def test_rejects_duplicate_json_keys(tmp_path):
    file = tmp_path / "request.json"
    file.write_text('{"model":"a","model":"b"}')
    with pytest.raises(PreflightRefused, match="Duplicate"):
        load_request(file)


def test_asset_tamper_refused_before_tokenizer_load(tmp_path, monkeypatch):
    (tmp_path / "tokenizer.json").write_text("{}")
    original_import = builtins.__import__

    def guard_import(name, *args, **kwargs):
        if name in {"tokenizers", "transformers"}:
            raise AssertionError("Tokenizer loading occurred before asset integrity checks")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard_import)
    with pytest.raises(PreflightRefused, match="hash mismatch"):
        PromptAuditor(tmp_path)


def test_missing_assets_do_not_download(tmp_path):
    with pytest.raises(PreflightRefused, match="already exist locally"):
        PromptAuditor(tmp_path)


def test_cli_writes_redacted_report_and_refuses_overwrite(tmp_path, auditor, capsys):
    file, out = tmp_path / "request.json", tmp_path / "report.json"
    body = request()
    body["messages"][0]["content"] = "private-marker-761"
    file.write_text(json.dumps(body))
    args = [str(file), "--asset-dir", str(ASSET_DIR), "--output", str(out)]
    assert main(args) == 0
    first = out.read_bytes()
    assert b"private-marker-761" not in first
    assert main(args) == 2
    assert out.read_bytes() == first
    assert "already exists" in capsys.readouterr().err


def test_all_request_fields_have_statistics(auditor):
    body = request()
    body.update(
        {
            "stop": ["END"],
            "n": 1,
            "stream": True,
            "stream_options": {"include_usage": True},
            "seed": 12,
            "top_p": 0.9,
            "frequency_penalty": 0,
            "presence_penalty": 0,
            "tool_choice": "none",
            "parallel_tool_calls": False,
        }
    )
    report = auditor.audit(body)
    assert set(report["request_fields"]) == set(body)
    assert all(v["compact_json_utf8_bytes"] > 0 for v in report["request_fields"].values())
    assert report["provider_only_unmodeled_fields"] == ["parallel_tool_calls", "tool_choice"]


def test_direct_pinned_loader_matches_official_local_tokenizer_config(auditor):
    from transformers import PreTrainedTokenizerFast

    official = PreTrainedTokenizerFast.from_pretrained(
        ASSET_DIR,
        local_files_only=True,
        chat_template=(ASSET_DIR / "chat_template.jinja").read_text(),
    )
    messages = [
        {"role": "system", "content": "Use 中文 and JSON."},
        {"role": "user", "content": "Return OK."},
        {"role": "assistant", "content": "OK", "reasoning_content": "Earlier analysis"},
        {"role": "user", "content": "Continue"},
    ]
    for switches in (
        {},
        {"enable_thinking": False},
        {"medium_effort": True, "truncate_history_thinking": False},
    ):
        body = request()
        body["messages"] = messages
        body["chat_template_kwargs"] = switches
        expected = official.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True, **switches
        )
        assert auditor.audit(body)["local_template"]["tokens"] == len(expected)
