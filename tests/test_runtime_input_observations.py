"""Runtime facts are copied from captured tensors, never fixture answers/defaults."""

import copy
import json

import pytest

from headroom.diagnose import build_diagnosis_messages
from headroom.solver_context import (
    execution_context,
    runtime_input_observations,
    solver_prompt_context,
)
from headroom.verify.pairing import CONTRACTS, PROTOCOL


def source():
    return [{"path": "train.py", "sha256": "a" * 64}]


def result():
    names = CONTRACTS["s3"]["inputs"]
    return {
        "run_id": "retained-runtime-id",
        "steps": 20,
        "capture_complete": True,
        "pairing_capture": {
            "protocol": PROTOCOL,
            "complete": True,
            "source_contract": {
                "supported": True,
                "profile": "s3",
                "contract_sha256": CONTRACTS["s3"]["digest"],
                "source_sha256": "a" * 64,
                "tensor_names": list(names),
            },
            "tensors": {
                name: {
                    "shape": [3 if i < 2 else 9, 7],
                    "dtype": "torch.float32",
                    "sha256": "b" * 64,
                }
                for i, name in enumerate(names)
            },
            "updates": [
                {"step": i, "effective_batch": 3, "training_forwards": 1, "backwards": 1}
                for i in range(1, 21)
            ],
        },
    }


def test_actual_shapes_and_updates_are_distinguished_and_bound_to_retained_run():
    facts = runtime_input_observations(result(), source(), selected_round=2)
    assert facts["status"] == "observed"
    assert facts["selected_round"] == 2
    assert facts["selected_run_id"] == "retained-runtime-id"
    assert facts["source_sha256"] == "a" * 64
    assert facts["effective_batch_per_optimizer_update"] == 3
    assert facts["tensors"]["train_inputs"]["shape"] == [3, 7]
    assert facts["tensors"]["eval_inputs"]["shape"] == [9, 7]
    assert facts["observed_optimizer_updates"] == 20
    assert facts["target_effective_configuration"] == "unverified"


def test_source_from_different_candidate_cannot_fill_current_runtime_context():
    other = [{"path": "train.py", "sha256": "c" * 64}]
    facts = runtime_input_observations(result(), other)
    assert facts["status"] == "unverified"
    assert "tensors" not in facts


@pytest.mark.parametrize(
    "change",
    [
        "incomplete",
        "capture_incomplete",
        "nineteen",
        "unknown_profile",
        "bad_contract",
        "different_names",
        "bad_shape",
        "bad_step",
        "wrong_batch",
        "missing_run",
    ],
)
def test_incomplete_unsupported_or_inconsistent_runtime_metadata_remains_unknown(change):
    value = result()
    capture = value["pairing_capture"]
    if change == "incomplete":
        capture["complete"] = False
    elif change == "capture_incomplete":
        value["capture_complete"] = False
    elif change == "nineteen":
        value["steps"] = 19
        capture["updates"].pop()
    elif change == "unknown_profile":
        capture["source_contract"]["profile"] = "dynamic_target"
    elif change == "bad_contract":
        capture["source_contract"]["contract_sha256"] = "d" * 64
    elif change == "different_names":
        capture["source_contract"]["tensor_names"] = ["guessed_batch"]
    elif change == "bad_shape":
        capture["tensors"]["train_inputs"]["shape"] = [True, 7]
    elif change == "bad_step":
        capture["updates"][5]["step"] = 99
    elif change == "wrong_batch":
        capture["updates"][5]["effective_batch"] = 9
    elif change == "missing_run":
        value.pop("run_id")
    facts = runtime_input_observations(value, source())
    assert facts["status"] in ("unverified", "unsupported")
    assert "tensors" not in facts


def test_absent_runtime_never_falls_back_to_source_defaults():
    facts = runtime_input_observations(None, source())
    assert facts["status"] == "unsupported"
    assert "effective_batch_per_optimizer_update" not in facts


def test_shared_execution_context_carries_selected_runtime_facts_without_mutation():
    value = result()
    before = copy.deepcopy(value)
    context = execution_context(
        script="train.py",
        script_args=["--batch=9"],
        execution_argv=None,
        source_files=source(),
        selected_round=2,
        repository_mode=False,
        seed=1,
        max_steps=20,
        device="cpu",
        allocator_conf=None,
        runtime_result=value,
    )
    messages = build_diagnosis_messages(
        "evidence", goal="reclaim", policy={}, execution_context=context
    )
    visible = json.loads(messages[1]["content"])["execution_context"]
    assert visible["runtime_input_observations"]["effective_batch_per_optimizer_update"] == 3
    shared = solver_prompt_context(execution_context=context)
    assert shared["execution_context"] == visible
    assert value == before
