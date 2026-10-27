"""Role routing and local JSON/schema validation, without implicit extra calls."""

import copy
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from headroom.llm.client import ClientResponse, LLMError, TokenFactoryClient
from headroom.llm.cost import Usage


class ResponseValidationError(LLMError):
    """Validation failure with optional response evidence, never response text in str()."""

    def __init__(self, message, *, reason="invalid_json", response=None):
        super().__init__(message)
        self.reason = reason
        self.response = response


_RESPONSE_ERROR_REASONS = frozenset(
    {"invalid_json", "empty_json", "truncated", "filtered", "schema_mismatch"}
)
_RESPONSE_FINISH_REASONS = frozenset(
    {"stop", "length", "tool_calls", "content_filter", "function_call"}
)


def response_validation_metadata(error: ResponseValidationError) -> dict[str, Any]:
    """Public error facts only: no exception text, response text or hidden reasoning."""
    response = error.response
    reason = error.reason
    finish = getattr(response, "finish_reason", None)
    role = getattr(response, "role", None)
    usage = getattr(response, "usage", None)
    return {
        "schema": "headroom.response-validation-metadata.v1",
        "error_reason": reason
        if type(reason) is str and reason in _RESPONSE_ERROR_REASONS
        else "unknown",
        "finish_reason": finish
        if type(finish) is str and finish in _RESPONSE_FINISH_REASONS
        else None,
        "role": role
        if type(role) is str and role in {"annotate", "diagnose", "patcher", "research"}
        else None,
        "usage": {
            name: getattr(usage, name) if isinstance(usage, Usage) else None
            for name in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "cached_tokens",
                "reasoning_tokens",
            )
        },
    }


def _reject_constant(_):
    raise ValueError("Nonfinite JSON value")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _finite_float(value):
    decoded = float(value)
    if not math.isfinite(decoded):
        raise ValueError("Nonfinite JSON number")
    return decoded


_DECODER = json.JSONDecoder(
    parse_constant=_reject_constant, parse_float=_finite_float, object_pairs_hook=_unique_object
)


def parse_json(text: str):
    """Accept raw JSON, a fenced response, or one unambiguous embedded JSON value.

    No eval, YAML coercion, key invention or automatic paid repair requests.
    Duplicate keys, nonfinite numbers and multiple JSON objects are rejected.
    """
    if not isinstance(text, str) or not text.strip():
        raise ResponseValidationError("Model returned no JSON text", reason="empty_json")
    text = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*\n?(.*?)\n?```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return _DECODER.decode(text)
    except (ValueError, json.JSONDecodeError):
        pass
    found = []
    cursor = 0
    while cursor < len(text):
        start = re.search(r"[\[{]", text[cursor:])
        if start is None:
            break
        offset = cursor + start.start()
        try:
            value, end = _DECODER.raw_decode(text, offset)
        except (ValueError, json.JSONDecodeError):
            # Do not salvage an inner object from an invalid outer JSON object.
            raise ResponseValidationError("Model returned invalid JSON") from None
        found.append(value)
        cursor = end
    if len(found) != 1:
        raise ResponseValidationError("Model response does not contain one unambiguous JSON value")
    return found[0]


@dataclass(frozen=True)
class ChatResult(ClientResponse):
    parsed: Any = None


class LLMRouter:
    def __init__(self, client: TokenFactoryClient):
        self.client = client

    def chat(
        self,
        role: str,
        messages: Sequence[Mapping[str, Any]],
        json_schema: Mapping[str, Any] | type[BaseModel] | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        *,
        reasoning: bool | None = None,
        low_effort: bool = False,
        token_budget: int | None = None,
        max_tokens: int = 4000,
        temperature: float | None = None,
    ) -> ChatResult:
        model_type = None
        schema = None
        if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):
            model_type = json_schema
            schema = json_schema.model_json_schema()
        elif isinstance(json_schema, Mapping):
            schema = copy.deepcopy(dict(json_schema))
        elif json_schema is not None:
            raise ValueError("json_schema must be a JSON Schema mapping or Pydantic model class")
        if schema is not None:
            _check_local_references(schema)
            Draft202012Validator.check_schema(schema)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON matching this schema, without markdown or commentary.\n"
                        + json.dumps(schema, ensure_ascii=False, allow_nan=False)
                    ),
                },
                *copy.deepcopy(list(messages)),
            ]
        response = self.client.complete(
            role,
            messages,
            schema=schema,
            tools=tools,
            reasoning=reasoning,
            low_effort=low_effort,
            token_budget=token_budget,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        parsed = None
        try:
            if schema is not None:
                if response.finish_reason in {"length", "content_filter"}:
                    raise ResponseValidationError(
                        "Structured response was truncated or filtered",
                        reason="truncated" if response.finish_reason == "length" else "filtered",
                    )
                parsed = parse_json(response.text)
                # Both validation paths return data, not a Pydantic instance, for downstream use.
                if model_type is not None:
                    try:
                        model_type.model_validate(parsed, strict=True)
                    except ValidationError:
                        raise ResponseValidationError(
                            "Model JSON does not match the requested schema",
                            reason="schema_mismatch",
                        ) from None
                if next(Draft202012Validator(schema).iter_errors(parsed), None) is not None:
                    raise ResponseValidationError(
                        "Model JSON does not match the requested schema", reason="schema_mismatch"
                    )
        except ResponseValidationError as error:
            # Preserve paid response evidence without weakening validation or making another call.
            error.response = response
            raise
        return ChatResult(**vars(response), parsed=parsed)


def _check_local_references(value):
    """JSON Schema validation must never fetch remote references or access files."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"$ref", "$dynamicRef", "$recursiveRef"} and (
                not isinstance(item, str) or not item.startswith("#")
            ):
                raise ValueError("Only document-local JSON Schema references are allowed")
            if key in {"$id", "id"} and isinstance(item, str) and ":" in item:
                raise ValueError("External JSON Schema identifiers are not allowed")
            _check_local_references(item)
    elif isinstance(value, list):
        for item in value:
            _check_local_references(item)
