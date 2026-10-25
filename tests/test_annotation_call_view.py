"""Offline view provenance and budget boundaries; no semantic accuracy claim."""

import copy
import json
from types import SimpleNamespace

import pytest

from headroom.annotate import (
    MAX_ANNOTATION_CALL_VIEW_ESCAPED_BYTES,
    MAX_ANNOTATION_CONTENT_ESCAPED_BYTES,
    _annotation_call_view,
    _escaped_size,
    annotate_stacks,
    annotation_payload,
)


def sample(count=60):
    return {
        "stack_id": "opaque_id",
        "bytes": 123456,
        "category": "private_oracle_category",
        "label": "private_oracle_answer",
        "frames": [
            {
                "filename": "/src/code.py" if i % 2 else "native.so",
                "name": f"fn_{i}" if i % 2 else f"namespace::fn_{i}",
                "line": i,
            }
            for i in range(count)
        ],
    }


def payload(row):
    return annotation_payload({row["stack_id"]: row}, input_stack_count=1)[0]


def test_neutral_view_indices_reference_visible_frame_positions_only():
    content = payload(sample(60))
    raw = json.loads(content)
    view = json.loads(_annotation_call_view(content))
    item = view["views"][0]
    frames = raw["stacks"][item["stack_position"]]["frames"]
    assert item["python_frame_positions"][0] == 1
    assert item["python_frame_positions"][-1] == 59
    assert item["native_frame_positions"] == list(range(0, 24, 2))
    assert all(frames[i]["filename"].endswith(".py") for i in item["python_frame_positions"])
    assert all("::" in frames[i]["name"] for i in item["native_frame_positions"])
    assert len(item["python_frame_positions"]) + item["omitted_python_positions"] == 30
    assert len(item["native_frame_positions"]) + item["omitted_native_positions"] == 30
    assert "private_oracle" not in content + json.dumps(view)
    assert "fn_" not in json.dumps(view)
    assert "opaque_id" not in json.dumps(view)


def test_view_uses_retained_positions_after_raw_frame_gaps():
    content = payload(sample(1000))
    raw = json.loads(content)["stacks"][0]
    item = json.loads(_annotation_call_view(content))["views"][0]
    assert raw["coverage"]["omitted_frame_count"] == 744
    assert item["input_partial"] is True
    assert max(item["python_frame_positions"]) < len(raw["frames"])
    assert raw["frames"][item["python_frame_positions"][-1]]["line"] == 999


def test_truncated_and_unavailable_frames_not_promoted_to_view_evidence():
    row = sample(3)
    row["frames"] = [
        None,
        {"filename": "/src/a.py", "name": "x" * 100000, "line": 2},
        {"filename": None, "name": None, "line": None},
    ]
    item = json.loads(_annotation_call_view(payload(row)))["views"][0]
    assert item["input_partial"] is True
    assert item["python_frame_positions"] == []
    assert item["native_frame_positions"] == []


def test_many_stacks_keep_independent_view_budget_without_changing_raw_payload():
    selected = {f"opaque_{i}": sample(256) | {"stack_id": f"opaque_{i}"} for i in range(40)}
    before = copy.deepcopy(selected)
    content, _ = annotation_payload(selected, input_stack_count=40)
    original_bytes = content.encode()
    view = _annotation_call_view(content)
    assert _escaped_size(view) <= MAX_ANNOTATION_CALL_VIEW_ESCAPED_BYTES
    assert _escaped_size(content) <= MAX_ANNOTATION_CONTENT_ESCAPED_BYTES
    assert content.encode() == original_bytes
    assert selected == before
    parsed = json.loads(view)
    assert [v["stack_position"] for v in parsed["views"]] == list(range(40))
    for v in parsed["views"]:
        assert v["omitted_python_positions"] > 0
        assert v["omitted_native_positions"] > 0
        assert all(0 <= i < 256 for i in v["python_frame_positions"] + v["native_frame_positions"])


@pytest.mark.parametrize("bad", [None, 1, "x" * (MAX_ANNOTATION_CONTENT_ESCAPED_BYTES + 1)])
def test_call_view_rejects_invalid_or_oversized_input(bad):
    with pytest.raises(ValueError):
        _annotation_call_view(bad)


def test_annotation_disagreement_is_preserved_and_no_oracle_sent():
    row = sample(60) | {"category": "activations"}
    original = copy.deepcopy(row)

    class Router:
        def chat(self, role, messages, **kwargs):
            assert role == "annotate"
            assert kwargs["reasoning"] is False and kwargs["max_tokens"] == 3000
            assert len(messages) == 3
            assert json.loads(messages[1]["content"])["kind"] == "visible_call_frame_index"
            assert json.loads(messages[2]["content"])["stacks"][0]["frames"] == row["frames"]
            assert "private_oracle_answer" not in json.dumps(messages)
            return SimpleNamespace(
                parsed={
                    "annotations": [
                        {
                            "stack_id": row["stack_id"],
                            "category": "unknown",
                            "label": "Unresolved ownership",
                        }
                    ]
                }
            )

    result = annotate_stacks(Router(), {"analysis": {"peak_composition": [row]}})
    assert result["heuristic_agreement"] == 0
    assert result["acceptance"] is False
    assert result["annotations"][0]["category"] == "unknown"
    assert row == original
