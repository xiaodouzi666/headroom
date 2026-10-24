"""CPU-only local Ultra prompt audit; never a provider billing bound or live gate."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
from typing import Any

MODEL_ID = "nvidia/Nemotron-3-Ultra-550b-a55b"
TOKENIZER_REPO = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4"
TOKENIZER_REVISION = "02462641f13d3af838b904f48195b9bb8a1e4ebc"
ASSET_HASHES = {
    "tokenizer.json": "623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7",
    "tokenizer_config.json": "10f93eabcb9b1602fbb991d6308e787ce1df28ee9cd7a1c6d1e8c3f338b957bc",
    "chat_template.jinja": "82753bef5cedc4932c1ed509b5c9a12be680fd86d1adb65bc3f7398d11c8eebc",
}
TEMPLATE_DEFAULTS = {
    "enable_thinking": True,
    "medium_effort": False,
    "truncate_history_thinking": True,
}
PROVIDER_ONLY_FIELDS = {
    "response_format",
    "reasoning_effort",
    "reasoning_budget",
    "max_thinking_tokens",
    "tool_choice",
    "parallel_tool_calls",
}
CONTROL_FIELDS = {
    "max_tokens",
    "max_completion_tokens",
    "temperature",
    "top_p",
    "stop",
    "n",
    "stream",
    "stream_options",
    "timeout",
    "seed",
    "frequency_penalty",
    "presence_penalty",
}
EXTRA_FIELDS = {
    "chat_template_kwargs",
    "reasoning_effort",
    "reasoning_budget",
    "max_thinking_tokens",
}
TOP_FIELDS = (
    {"model", "messages", "tools", "extra_body"}
    | EXTRA_FIELDS
    | PROVIDER_ONLY_FIELDS
    | CONTROL_FIELDS
)
MAX_REQUEST_BYTES = 16 * 1024 * 1024


class PreflightRefused(ValueError):
    """A safe local error; no prompt values appear in error messages."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightRefused(message)


def _object(value: Any, allowed: set[str], path: str) -> None:
    _require(type(value) is dict, path + " must be an object")
    # Do not echo unknown keys: they may themselves contain private prompt data.
    _require(not (set(value) - allowed), path + " contains unsupported fields")


def _json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise PreflightRefused("Request must contain finite, UTF-8 JSON values") from None


def _json_tree(value: Any) -> None:
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "JSON object keys must be strings")
        for item in value.values():
            _json_tree(item)
    elif type(value) is list:
        for item in value:
            _json_tree(item)
    else:
        _require(value is None or type(value) in {str, int, float, bool}, "Unsupported JSON value")
        _require(type(value) is not float or math.isfinite(value), "JSON numbers must be finite")


def _text(value: Any, path: str) -> None:
    _require(type(value) is str, path + " must be plain text; multimodal content is unsupported")


def _tool_schema(value: Any, path: str) -> None:
    _object(value, {"type", "function"}, path)
    _require(value.get("type") == "function", path + " supports function tools only")
    function = value.get("function")
    _object(function, {"name", "description", "parameters", "strict"}, path + ".function")
    _text(function.get("name"), path + ".function.name")
    if "description" in function:
        _text(function["description"], path + ".function.description")
    _require(
        type(function.get("parameters")) is dict,
        path + ".function.parameters must be a schema object",
    )
    if "strict" in function:
        _require(type(function["strict"]) is bool, path + ".function.strict must be boolean")


def validate_request(request: Any) -> dict[str, Any]:
    """Accept an explicit text-only subset of SDK kwargs or the flattened wire body."""
    _object(request, TOP_FIELDS, "request")
    try:
        _json_tree(request)
    except RecursionError:
        raise PreflightRefused("Request nesting is unsupported") from None
    _require(
        len(_json_bytes(request)) <= MAX_REQUEST_BYTES, "Request exceeds the local audit byte limit"
    )
    body = dict(request)
    extra = body.pop("extra_body", {})
    _object(extra, EXTRA_FIELDS, "extra_body")
    _require(not (set(extra) & set(body)), "Duplicate SDK and wire fields are unsupported")
    body.update(extra)
    _require(body.get("model") == MODEL_ID, "Only the pinned Ultra model identity is supported")
    caps = set(body) & {"max_tokens", "max_completion_tokens"}
    _require(len(caps) == 1, "Exactly one explicit output cap is required")
    cap = body[next(iter(caps))]
    _require(type(cap) is int and cap > 0, "Output cap must be a positive integer")
    _require(body.get("n", 1) == 1 and type(body.get("n", 1)) is int, "Only n=1 is supported")
    for name in ("reasoning_budget", "max_thinking_tokens"):
        if name in body:
            _require(type(body[name]) is int and body[name] > 0, name + " must be positive")
    if "reasoning_effort" in body:
        _require(
            body["reasoning_effort"] in ("none", "minimal", "low", "medium", "high"),
            "Unsupported reasoning_effort",
        )
    kwargs = body.get("chat_template_kwargs", {})
    _object(kwargs, set(TEMPLATE_DEFAULTS), "chat_template_kwargs")
    _require(all(type(v) is bool for v in kwargs.values()), "Template switches must be booleans")
    _require(
        not (kwargs and "reasoning_effort" in body), "Combined reasoning selectors are unsupported"
    )
    if "response_format" in body:
        form = body["response_format"]
        _object(form, {"type", "json_schema"}, "response_format")
        _require(
            form.get("type") in ("text", "json_object", "json_schema"),
            "Unsupported response_format type",
        )
        if form["type"] == "json_schema":
            schema = form.get("json_schema")
            _object(
                schema, {"name", "description", "schema", "strict"}, "response_format.json_schema"
            )
            _text(schema.get("name"), "response_format.json_schema.name")
            _require(type(schema.get("schema")) is dict, "response_format schema must be an object")
            if "strict" in schema:
                _require(type(schema["strict"]) is bool, "response_format strict must be boolean")
            if "description" in schema:
                _text(schema["description"], "response_format.json_schema.description")
        else:
            _require(
                "json_schema" not in form, "json_schema requires its matching response_format type"
            )
    messages = body.get("messages")
    _require(type(messages) is list and bool(messages), "messages must be a nonempty list")
    for index, message in enumerate(messages):
        path = f"messages[{index}]"
        _object(
            message, {"role", "content", "reasoning_content", "tool_calls", "tool_call_id"}, path
        )
        role = message.get("role")
        _require(role in ("system", "user", "assistant", "tool"), path + " has an unsupported role")
        if role == "assistant" and message.get("content") is None:
            _require(bool(message.get("tool_calls")), path + " requires text or tool calls")
        else:
            _text(message.get("content"), path + ".content")
        if "reasoning_content" in message:
            _require(role == "assistant", path + " reasoning requires assistant role")
            _text(message["reasoning_content"], path + ".reasoning_content")
        if "tool_call_id" in message:
            _require(role == "tool", path + " tool_call_id requires tool role")
            _text(message["tool_call_id"], path + ".tool_call_id")
        if "tool_calls" in message:
            _require(
                role == "assistant" and type(message["tool_calls"]) is list,
                path + " has invalid tool_calls",
            )
            for call in message["tool_calls"]:
                _object(call, {"id", "type", "function"}, path + ".tool_calls")
                _require(call.get("type") == "function", "Only function tool calls are supported")
                if "id" in call:
                    _text(call["id"], path + ".tool_calls.id")
                function = call.get("function")
                _object(function, {"name", "arguments"}, path + ".tool_calls.function")
                _text(function.get("name"), path + ".tool_calls.function.name")
                _require(
                    type(function.get("arguments")) is dict,
                    "Historical tool arguments must be objects; JSON-string normalization is unsupported",
                )
    if "tools" in body:
        _require(type(body["tools"]) is list, "tools must be a list")
        for tool in body["tools"]:
            _tool_schema(tool, "tools[]")
    for name in ("stream", "parallel_tool_calls"):
        if name in body:
            _require(type(body[name]) is bool, name + " must be boolean")
    if "stream_options" in body:
        _object(body["stream_options"], {"include_usage"}, "stream_options")
        _require(
            type(body["stream_options"].get("include_usage")) is bool,
            "stream_options.include_usage must be boolean",
        )
    if "tool_choice" in body:
        choice = body["tool_choice"]
        if type(choice) is dict:
            _object(choice, {"type", "function"}, "tool_choice")
            _require(choice.get("type") == "function", "Unsupported tool_choice type")
            _object(choice.get("function"), {"name"}, "tool_choice.function")
            _text(choice["function"].get("name"), "tool_choice.function.name")
        else:
            _require(choice in ("auto", "none", "required"), "Unsupported tool_choice")
    for name in ("temperature", "top_p", "timeout", "frequency_penalty", "presence_penalty"):
        if name in body:
            _require(type(body[name]) in {int, float}, name + " must be a finite number")
    if "seed" in body:
        _require(type(body["seed"]) is int, "seed must be an integer")
    if "stop" in body:
        stop = body["stop"]
        _require(
            type(stop) is str or (type(stop) is list and all(type(s) is str for s in stop)),
            "stop must be text or a list of text",
        )
    return body


def load_request(path: Path) -> dict[str, Any]:
    """No dotenv, credential discovery, network, or permissive JSON parsing."""

    def unique_pairs(pairs):
        value = {}
        for key, item in pairs:
            _require(key not in value, "Duplicate JSON object keys are unsupported")
            value[key] = item
        return value

    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_REQUEST_BYTES + 1)
        _require(len(raw) <= MAX_REQUEST_BYTES, "Request file exceeds the local audit byte limit")
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise PreflightRefused("Cannot read a valid request JSON file") from None
    validate_request(value)
    return value


class PromptAuditor:
    """Loads three hash-pinned local files; it has no download or model-client path."""

    def __init__(self, asset_dir: Path):
        loaded = {}
        self.assets = {}
        for name, expected in ASSET_HASHES.items():
            try:
                raw = (asset_dir / name).read_bytes()
            except OSError:
                raise PreflightRefused(
                    "Pinned tokenizer assets must already exist locally"
                ) from None
            digest = hashlib.sha256(raw).hexdigest()
            _require(digest == expected, "Pinned tokenizer asset hash mismatch")
            loaded[name] = raw
            self.assets[name] = {
                "sha256": digest,
                "bytes": len(raw),
                "source_url": f"https://huggingface.co/{TOKENIZER_REPO}/resolve/{TOKENIZER_REVISION}/{name}",
            }
        # Imported only after all hashes pass. No AutoTokenizer, remote code, or model weights.
        from tokenizers import Tokenizer
        from transformers import PreTrainedTokenizerFast

        config = json.loads(loaded["tokenizer_config.json"])
        self.tokenizer = PreTrainedTokenizerFast(
            tokenizer_object=Tokenizer.from_str(loaded["tokenizer.json"].decode("utf-8")),
            model_max_length=config["model_max_length"],
            chat_template=loaded["chat_template.jinja"].decode("utf-8"),
        )
        self.model_max_length = config["model_max_length"]

    def _stats(self, value: Any) -> dict[str, Any]:
        raw = _json_bytes(value)
        return {
            "compact_json_utf8_bytes": len(raw),
            "compact_json_sha256": hashlib.sha256(raw).hexdigest(),
            "serialized_json_local_tokens_estimate": len(
                self.tokenizer.encode(raw.decode("utf-8"), add_special_tokens=False)
            ),
        }

    def audit(self, request: Any) -> dict[str, Any]:
        body = validate_request(request)
        switches = {**TEMPLATE_DEFAULTS, **body.get("chat_template_kwargs", {})}
        try:
            rendered = self.tokenizer.apply_chat_template(
                body["messages"],
                tools=body.get("tools") or None,
                tokenize=False,
                add_generation_prompt=True,
                **switches,
            )
            token_ids = self.tokenizer.encode(rendered, add_special_tokens=False)
        except Exception:  # noqa: BLE001 - keep private prompt data out of library errors.
            raise PreflightRefused("Pinned template cannot render this supported request") from None
        rendered_bytes = rendered.encode("utf-8")
        fields = {name: self._stats(value) for name, value in body.items()}
        unmodeled = sorted(set(body) & PROVIDER_ONLY_FIELDS)
        history_ids = sum(
            int("tool_call_id" in message)
            + sum(int("id" in call) for call in message.get("tool_calls", []))
            for message in body["messages"]
        )
        warnings = [
            "Local template exactness is conditional on these pinned NVIDIA assets and switches.",
            "Nebius deployment tokenizer, template, defaults, and preprocessing have not been matched.",
            "The NVIDIA tokenizer config says 262144 tokens; observed Nebius catalogue context is 1048576.",
            "Serialized JSON counts are local estimates of separate domains, not provider injected tokens.",
            "Domain estimates are non-additive and must not be added to template tokens as a billing bound.",
            "No provider truncation, hard input cap, cache discount, or cost authorization is established.",
        ]
        if unmodeled:
            warnings.append(
                "Provider-only fields are recorded but are not injected into the local template."
            )
        if history_ids:
            warnings.append(
                "The pinned template ignores tool call IDs; provider handling is unverified."
            )
        return {
            "format_version": 1,
            "purpose": "offline_prompt_diagnostic_only",
            "model": MODEL_ID,
            "provider_tokenizer_match_verified": False,
            "provider_billable_token_ceiling": None,
            "provider_cost_upper_usd": None,
            "live_authorized": False,
            "local_template": {
                "tokens": len(token_ids),
                "count_kind": "exact_for_pinned_local_rendering_only",
                "utf8_bytes": len(rendered_bytes),
                "sha256": hashlib.sha256(rendered_bytes).hexdigest(),
                "add_generation_prompt": True,
                "add_special_tokens": False,
                "switches": switches,
                "template_config_max_length": self.model_max_length,
                "exceeds_template_config_max_length": len(token_ids) > self.model_max_length,
                "domains": ["messages"]
                + (["tools"] if body.get("tools") else [])
                + ["chat_template_kwargs"],
            },
            "request": self._stats(body),
            "input_form": "sdk_kwargs"
            if "extra_body" in request or "timeout" in request
            else "wire_json",
            "request_fields": fields,
            "provider_only_unmodeled_fields": unmodeled,
            "historical_tool_id_fields_ignored_by_local_template": history_ids,
            "extra_schema": (
                self._stats(body["response_format"]["json_schema"]["schema"])
                if body.get("response_format", {}).get("type") == "json_schema"
                else None
            ),
            "tokenizer": {
                "repo": TOKENIZER_REPO,
                "revision": TOKENIZER_REVISION,
                "assets": self.assets,
                "libraries": {
                    name: importlib.metadata.version(name)
                    for name in ("transformers", "tokenizers", "jinja2")
                },
            },
            "supported_domains": {
                "top_level": sorted(TOP_FIELDS),
                "extra_body": sorted(EXTRA_FIELDS),
                "template_switches": sorted(TEMPLATE_DEFAULTS),
                "messages": "plain-text system/user/assistant/tool; assistant reasoning_content; function calls with object arguments",
                "tools": "function schema objects rendered with the pinned NVIDIA template",
                "json_schema": "raw local JSON estimate only; provider injection unverified",
                "unknown_fields": "rejected",
            },
            "warnings": warnings,
        }
