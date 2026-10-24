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
