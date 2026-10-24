from types import SimpleNamespace

from headroom.annotate import annotate_stacks
from headroom.budget import BudgetExceeded


class Router:
    def __init__(self, value):
        self.value = value

    def chat(self, role, messages, **kwargs):
        assert role == "annotate" and kwargs["max_tokens"] <= 3000
        if isinstance(self.value, Exception):
            raise self.value
        return SimpleNamespace(parsed={"annotations": self.value})


def evidence():
    return {
        "analysis": {
            "peak_composition": [
                {"stack_id": "stk_a", "bytes": 42, "category": "activations", "frames": []}
            ]
        }
    }


def test_annotations_are_labels_not_acceptance():
    result = annotate_stacks(
        Router([{"stack_id": "stk_a", "category": "activations", "label": "Saved activation"}]),
        evidence(),
    )
    assert result["complete"] and result["heuristic_agreement"] == 1
    assert not result["acceptance"]


def test_fabricated_ids_and_missing_labels_rejected():
    for items in [[], [{"stack_id": "invented", "category": "params", "label": "x"}]]:
        assert annotate_stacks(Router(items), evidence())["status"] == "failed"


def test_annotations_skip_budget_without_fabricating_values():
    result = annotate_stacks(Router(BudgetExceeded("stop")), evidence())
    assert result["status"] == "skipped" and result["heuristic_agreement"] is None


def test_real_grads_and_cache_categories_are_supported_and_alias_normalized():
    from headroom.annotate import StackLabels

    data = {
        "analysis": {
            "peak_composition": [
                {"stack_id": "grad", "bytes": 2, "category": "grads", "frames": []},
                {"stack_id": "cache", "bytes": 1, "category": "cache", "frames": []},
            ]
        }
    }
    labels = [
        {"stack_id": "grad", "category": "gradients", "label": "Gradient buffer"},
        {"stack_id": "cache", "category": "cache", "label": "Cached tensor"},
    ]
    StackLabels.model_validate({"annotations": labels})
    result = annotate_stacks(Router(labels), data)
    assert result["heuristic_agreement"] == 1
    assert result["annotations"][0]["category"] == "grads"


def test_optional_annotations_skip_unverified_billing_domain():
    from headroom.runtime import RuntimeNotReady

    result = annotate_stacks(Router(RuntimeNotReady("fixture")), evidence())
    assert result["status"] == "skipped"
    assert result["reason"] == "annotation_runtime_bound_unverified"


def test_binding_preserves_measurements_and_marks_model_opinions():
    import copy

    from headroom.annotate import annotation_fingerprint, bind_stack_annotations

    original = evidence() | {"run_id": "capture-a"}
    saved = copy.deepcopy(original)
    annotations = annotate_stacks(
        Router(
            [{"stack_id": "stk_a", "category": "optimizer_state", "label": "Optimizer hypothesis"}]
        ),
        original,
    )
    bound = bind_stack_annotations(original, annotations, provenance="offline_fixture")
    stack = bound["analysis"]["peak_composition"][0]
    note = stack.pop("model_annotation")
    assert stack == saved["analysis"]["peak_composition"][0]
    assert original == saved
    assert note["category"] == "optimizer_state" and stack["category"] == "activations"
    assert note["kind"] == "model_interpretation" and note["is_measurement"] is False
    assert note["provenance"] == "offline_fixture" and note["source_run_id"] == "capture-a"
    assert note["evidence_fingerprint"] == annotation_fingerprint(original)
    assert bound["annotation_delivery"]["attached_stack_ids"] == ["stk_a"]


def test_annotations_do_not_transfer_to_another_capture_with_the_same_stack_id():
    import copy

    from headroom.annotate import bind_stack_annotations

    original = evidence() | {"run_id": "capture-a"}
    annotations = annotate_stacks(
        Router([{"stack_id": "stk_a", "category": "activations", "label": "Saved activation"}]),
        original,
    )
    for change in ("run_id", "bytes", "frames", "category"):
        other = copy.deepcopy(original)
        if change == "run_id":
            other["run_id"] = "capture-b"
        elif change == "frames":
            other["analysis"]["peak_composition"][0]["frames"] = [{"name": "changed"}]
        else:
            other["analysis"]["peak_composition"][0][change] = 43 if change == "bytes" else "params"
        bound = bind_stack_annotations(other, annotations, provenance="live")
        assert bound["annotation_delivery"]["reason"] == "source_evidence_mismatch"
        assert "model_annotation" not in bound["analysis"]["peak_composition"][0]


def test_invalid_or_incomplete_labels_are_not_bound():
    import copy

    from headroom.annotate import bind_stack_annotations

    original = evidence()
    good = annotate_stacks(
        Router([{"stack_id": "stk_a", "category": "activations", "label": "Saved activation"}]),
        original,
    )
    invalid = []
    for key, value in (("status", "failed"), ("complete", False), ("evidence_fingerprint", None)):
        invalid.append({**good, key: value})
    for rows in (
        [],
        good["annotations"] * 2,
        [{"stack_id": "stk_a", "category": "invented", "label": "x"}],
        [{"stack_id": "stk_a", "category": "activations", "label": "x" * 181}],
        [{"stack_id": "stk_a", "category": "activations", "label": "line1\nline2"}],
    ):
        invalid.append({**good, "annotations": rows})
    saved = copy.deepcopy(original)
    for value in invalid:
        bound = bind_stack_annotations(original, value, provenance="live")
        assert bound["annotation_delivery"]["status"] == "not_attached"
        assert "model_annotation" not in bound["analysis"]["peak_composition"][0]
        assert original == saved
