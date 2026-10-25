"""Offline payload bounds and annotation invariants; no provider or GPU access."""

import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from test_llm_client import completion

from headroom.annotate import (
    MAX_ANNOTATION_CONTENT_ESCAPED_BYTES,
    MAX_ANNOTATION_FRAME_ESCAPED_BYTES,
    MAX_ANNOTATION_FRAMES,
    annotate_stacks,
    annotation_payload,
)
from headroom.config import RuntimeConfig, VerifiedCapabilities, candidate_models
from headroom.llm.client import TokenFactoryClient
from headroom.llm.request_audit import MAX_CAPTURE_BYTES, capture_request
from headroom.llm.router import LLMRouter


def frames(count):
    return [
        {"filename": "/source/train.py", "name": "frame_" + str(i), "line": i} for i in range(count)
    ]


def stack(count, **extra):
    return {
        "stack_id": "stk_a",
        "bytes": 42,
        "category": "activations",
        "frames": frames(count),
        **extra,
    }


def encoded_size(content):
    return len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode())


class Router:
    def __init__(self):
        self.calls = []

    def chat(self, role, messages, **kwargs):
        self.calls.append((role, messages, kwargs))
        body = json.loads(messages[-1]["content"])
        return SimpleNamespace(
            parsed={
                "annotations": [
                    {"stack_id": row["stack_id"], "category": "unknown", "label": "Ambiguous"}
                    for row in body["stacks"]
                ]
            }
        )


def test_long_common_stack_keeps_all_ordered_frames_without_mutating_evidence():
    row = stack(109)
    before = copy.deepcopy(row)
    content, metadata = annotation_payload({"stk_a": row}, input_stack_count=1)
    supplied = json.loads(content)["stacks"][0]
    assert supplied["frames"] == row["frames"]
    assert supplied["coverage"]["complete"]
    assert supplied["coverage"]["retained_frame_ranges_zero_based"] == [[0, 108]]
    assert supplied["coverage"]["omitted_frame_count"] == 0
    assert metadata["all_selected_frame_content_complete"]
    assert row == before


def test_frame_limit_keeps_both_ends_and_marks_exact_omissions():
    content, _ = annotation_payload({"stk_a": stack(1000)}, input_stack_count=1)
    supplied = json.loads(content)["stacks"][0]
    assert len(supplied["frames"]) == MAX_ANNOTATION_FRAMES
    assert supplied["frames"][0]["name"] == "frame_0"
    assert supplied["frames"][-1]["name"] == "frame_999"
    assert supplied["coverage"]["retained_frame_ranges_zero_based"] == [[0, 127], [872, 999]]
    assert supplied["coverage"]["omitted_frame_count"] == 744
    assert supplied["coverage"]["complete"] is False


@pytest.mark.parametrize(
    "text", ["x" * 2_000_000, "汉字" * 10000, '"\\\n' * 10000, "\ud800" * 10000]
)
def test_large_or_escaped_fields_are_bounded_and_explicitly_incomplete(text):
    row = stack(1)
    row["frames"][0]["name"] = text
    content, _ = annotation_payload({"stk_a": row}, input_stack_count=1)
    supplied = json.loads(content)["stacks"][0]
    frame = supplied["frames"][0]
    assert (
        encoded_size(json.dumps(frame, ensure_ascii=False, separators=(",", ":")))
        <= MAX_ANNOTATION_FRAME_ESCAPED_BYTES
    )
    assert "name" in frame["truncated_fields"]
    assert supplied["coverage"]["complete"] is False
    assert encoded_size(content) <= MAX_ANNOTATION_CONTENT_ESCAPED_BYTES


def test_global_bound_is_fair_to_both_ends_of_every_stack():
    selected = {}
    for i in range(40):
        row = stack(300, stack_id=f"stack_{i}")
        for frame in row["frames"]:
            frame["name"] = "a" * 1500
        selected[row["stack_id"]] = row
    content, metadata = annotation_payload(selected, input_stack_count=40)
    body = json.loads(content)
    assert encoded_size(content) <= MAX_ANNOTATION_CONTENT_ESCAPED_BYTES
    assert len(body["stacks"]) == 40
    assert metadata["all_selected_frame_content_complete"] is False
    for row in body["stacks"]:
        assert len(row["frames"]) >= 2
        assert row["frames"][0]["line"] == 0
        assert row["frames"][-1]["line"] == 299
        assert row["coverage"]["omitted_frame_count"] > 0


def test_does_not_send_heuristic_category_label_or_allocation_bytes():
    row = stack(20, category="PRIVATE_CATEGORY", label="PRIVATE_LABEL", bytes=987654321)
    content, _ = annotation_payload({"stk_a": row}, input_stack_count=1)
    assert not any(token in content for token in ("PRIVATE_CATEGORY", "PRIVATE_LABEL", "987654321"))
    supplied = json.loads(content)["stacks"][0]
    assert set(supplied) == {"stack_id", "frames", "coverage"}


@pytest.mark.parametrize("bad_id", ["", "a" * 161, "汉" * 100])
def test_invalid_or_oversized_stack_identity_is_not_truncated_into_another_id(bad_id):
    with pytest.raises(ValueError):
        annotation_payload({bad_id: stack(1)}, input_stack_count=1)


def test_stack_count_bounds_are_explicit():
    selected = {f"stack_{i}": stack(1, stack_id=f"stack_{i}") for i in range(41)}
    with pytest.raises(ValueError):
        annotation_payload(selected, input_stack_count=41)
    router = Router()
    result = annotate_stacks(router, {"analysis": {"peak_composition": list(selected.values())}})
    assert result["requested"] == 40
    assert result["input_transport"]["omitted_input_stack_count"] == 1
    assert len(router.calls) == 1
    too_many = {"analysis": {"peak_composition": [stack(1)] * 4097}}
    router = Router()
    skipped = annotate_stacks(router, too_many)
    assert skipped["status"] == "skipped" and skipped["complete"] is False
    assert skipped["input_transport"]["omitted_input_stacks"] is True
    assert not router.calls


@pytest.mark.parametrize(
    "value", [None, "unavailable", [{"filename": ["bad"], "name": 7, "line": True}], [None]]
)
def test_unavailable_or_invalid_frame_metadata_is_marked_incomplete(value):
    content, _ = annotation_payload({"stk_a": stack(0, frames=value)}, input_stack_count=1)
    row = json.loads(content)["stacks"][0]
    assert row["coverage"]["complete"] is False


def test_mock_sdk_wire_keeps_reasoning_disabled_and_3000_completion_cap():
    models = candidate_models()
    models["nano"] = replace(
        models["nano"],
        output_cap_field="max_completion_tokens",
        evidence="offline verified field fixture",
        capabilities=VerifiedCapabilities(
            json_method="json_schema",
            reasoning_method="chat_template_kwargs",
            evidence="offline fixture only",
        ),
    )
    transported = []

    def handler(request):
        transported.append(request.content)
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        labels = [
            {"stack_id": row["stack_id"], "category": "unknown", "label": "Ambiguous"}
            for row in body["stacks"]
        ]
        return httpx.Response(
            200,
            json=completion(
                model=models["nano"].model_id, content=json.dumps({"annotations": labels})
            ),
        )

    evidence = {"analysis": {"peak_composition": [stack(109)]}}
    with TokenFactoryClient(
        config=RuntimeConfig(models=models), transport=httpx.MockTransport(handler)
    ) as client:
        result = annotate_stacks(LLMRouter(client), evidence)
    assert result["complete"] and not result["acceptance"]
    assert result["heuristic_agreement"] == 0
    payload = json.loads(transported[0])
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["max_completion_tokens"] == 3000
    assert "max_tokens" not in payload
    assert len(transported[0]) <= MAX_CAPTURE_BYTES
    assert capture_request(transported[0])["payload_status"] == "captured"
    assert len(json.loads(payload["messages"][-1]["content"])["stacks"][0]["frames"]) == 109


@pytest.mark.parametrize("count", [True, -1, 0, 4097])
def test_invalid_total_stack_count_cannot_claim_complete_input(count):
    with pytest.raises(ValueError):
        annotation_payload({"stk_a": stack(1)}, input_stack_count=count)


def test_invalid_stack_record_fails_before_router():
    router = Router()
    result = annotate_stacks(router, {"analysis": {"peak_composition": [None]}})
    assert result["complete"] is False and not router.calls
