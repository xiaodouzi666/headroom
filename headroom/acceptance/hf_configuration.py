"""Pure inspection of the pinned HF fixture's configuration repair surface.

This is a static shape check, not proof of model quality, equivalent training,
valid framework settings, or a successful hardware repair.
"""

import ast
import difflib
import hashlib
import math
from collections.abc import Mapping
from copy import deepcopy

MEMORY_ARGUMENTS = frozenset(
    {
        "per_device_train_batch_size",
        "gradient_accumulation_steps",
        "gradient_checkpointing",
        "gradient_checkpointing_kwargs",
        "bf16",
        "fp16",
        "optim",
        "optim_args",
    }
)
MAX_SOURCE_BYTES = 512 * 1024


def _sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _safe_value(node):
    if isinstance(node, ast.Constant):
        return type(node.value) in (bool, int, str, type(None)) or (
            type(node.value) is float and math.isfinite(node.value)
        )
    if isinstance(node, ast.Name):
        return node.id == "full"
    if isinstance(node, ast.Attribute):
        return (
            isinstance(node.value, ast.Name)
            and node.value.id == "args"
            and node.attr == "batch_size"
        )
    if isinstance(node, ast.BoolOp):
        return isinstance(node.op, (ast.Or, ast.And)) and all(
            _safe_value(value) for value in node.values
        )
    if isinstance(node, ast.IfExp):
        return all(_safe_value(value) for value in (node.test, node.body, node.orelse))
    if isinstance(node, ast.Dict):
        return all(
            isinstance(key, ast.Constant) and type(key.value) is str and _safe_value(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, (ast.List, ast.Tuple)):
        return all(_safe_value(value) for value in node.elts)
    return False


def _training_arguments(tree):
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TrainingArguments"
    ]
    if len(calls) != 1:
        raise ValueError("exactly_one_training_arguments_call_required")
    call = calls[0]
    names = [keyword.arg for keyword in call.keywords]
    if None in names or len(set(names)) != len(names):
        raise ValueError("expanded_or_duplicate_keywords")
    return call


def check_hf_configuration(
    before_sources: Mapping[str, str],
    after_sources: Mapping[str, str],
    *,
    expected_source_sha256: str,
    max_changed_lines: int = 15,
) -> dict:
    """Recognize memory-related TrainingArguments edits without executing code."""
    result = {
        "protocol": "headroom.hf-configuration.v1",
        "configuration_only": False,
        "changed_lines": None,
        "within_changed_line_limit": False,
        "accepted": False,
        "changed_arguments": [],
        "reasons": [],
        "scope": "Static configuration shape only; hardware, policy and numerical checks remain separate.",
    }
    reasons = result["reasons"]
    if type(max_changed_lines) is not int or not 0 < max_changed_lines <= 15:
        reasons.append("invalid_changed_line_limit")
        return result
    result["max_changed_lines"] = max_changed_lines
    if (
        not isinstance(before_sources, Mapping)
        or not isinstance(after_sources, Mapping)
        or set(before_sources) != {"train.py"}
        or set(after_sources) != {"train.py"}
    ):
        reasons.append("only_pinned_train_py_is_supported")
        return result
    before, after = before_sources["train.py"], after_sources["train.py"]
    if any(
        not isinstance(text, str) or len(text.encode()) > MAX_SOURCE_BYTES
        for text in (before, after)
    ):
        reasons.append("invalid_or_oversized_source")
        return result
    result["before_sha256"], result["after_sha256"] = _sha(before), _sha(after)
    if result["before_sha256"] != expected_source_sha256:
        reasons.append("original_source_hash_mismatch")
        return result
    changes = sum(
        i2 - i1 + j2 - j1
        for kind, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=before.splitlines(), b=after.splitlines(), autojunk=False
        ).get_opcodes()
        if kind != "equal"
    )
    result["changed_lines"] = changes
    result["within_changed_line_limit"] = 0 < changes <= max_changed_lines
    if not result["within_changed_line_limit"]:
        reasons.append("changed_line_limit_not_met")
    try:
        left, right = ast.parse(before), ast.parse(after)
        left_call, right_call = _training_arguments(left), _training_arguments(right)
        original = {kw.arg: ast.dump(kw.value) for kw in left_call.keywords}
        candidate = {kw.arg: ast.dump(kw.value) for kw in right_call.keywords}
        changed = sorted(
            name
            for name in set(original) | set(candidate)
            if original.get(name) != candidate.get(name)
        )
        result["changed_arguments"] = changed
        if not changed:
            reasons.append("no_configuration_change")
        if any(name not in MEMORY_ARGUMENTS for name in changed):
            reasons.append("outside_memory_configuration_surface")
        if any(kw.arg in changed and not _safe_value(kw.value) for kw in right_call.keywords):
            reasons.append("executable_or_unrecognized_configuration_value")
        masked_left, masked_right = deepcopy(left), deepcopy(right)
        for tree in (masked_left, masked_right):
            call = _training_arguments(tree)
            call.keywords = [kw for kw in call.keywords if kw.arg not in MEMORY_ARGUMENTS]
        if ast.dump(masked_left) != ast.dump(masked_right):
            reasons.append("code_outside_configuration_changed")
        result["configuration_only"] = bool(changed) and not any(
            reason != "changed_line_limit_not_met" for reason in reasons
        )
    except (SyntaxError, ValueError, RecursionError, TypeError) as error:
        reasons.append(
            str(error) if isinstance(error, ValueError) else "invalid_python_configuration"
        )
    result["accepted"] = result["configuration_only"] and result["within_changed_line_limit"]
    return result
