"""Availability scope adds no execution fact, reference support or acceptance."""

import copy
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_reference_context import bound_baseline, context
from test_verify_checkpoint_reference import SCRIPT

from headroom.solver_context import (
    MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES,
    MAX_SOLVER_CONTEXT_BYTES,
    solver_prompt_context,
)
from headroom.verify.reference_config import NumericalReference

SCOPE_KEY = "original_baseline_availability_scope"


@pytest.fixture
def old_context_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "reports/reference-sequence-scope-20261030/before/reference_context.py.txt"
    )
    loader = importlib.machinery.SourceFileLoader("owned_reference_context_before_scope", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


def unchanged_except_scope(new, old):
    value = copy.deepcopy(new)
    added = value["comparison_reference"].pop(SCOPE_KEY)
    assert value == old
    assert isinstance(added, str) and len(added.encode()) < 512
    assert "complete original numerical-comparison series" in added
    assert "not existence or status of the captured original execution" in added
    assert "creates no usable reference" in added
    assert "unsupported requirements remain unresolved" in added


@pytest.mark.parametrize("steps", [0, 12])
@pytest.mark.parametrize(
    "strategy", ["original_saved_tensor_offload", "original_workload_checkpoint"]
)
def test_known_captured_oom_remains_oom_while_complete_numeric_series_stays_unknown(
    tmp_path, old_context_module, steps, strategy
):
    baseline = bound_baseline(tmp_path)
    baseline["steps"] = steps
    original = copy.deepcopy(baseline)
    options = NumericalReference(strategy=strategy, max_seconds=480)
    new = context(baseline, options=options)
    old = old_context_module.numerical_reference_context(
        options, baseline=baseline, original_script=SCRIPT, original_args=[], retained_script=SCRIPT
    )
    unchanged_except_scope(new, old)
    assert baseline == original and baseline["status"] == "oom" and baseline["steps"] == steps
    observed = new["comparison_reference"]["original_baseline"]
    assert observed == old["comparison_reference"]["original_baseline"]
    assert observed["status"] == "unknown"
    assert observed["run_id"] is None and observed["source_and_argv_bound"] is False
    assert observed["observed_logical_updates"] is None
    assert new["capability_status"] == "preconditions_observed_execution_unverified"
    assert all(new["explicit_reference_preconditions"].values())
    assert new["reference_execution_verified"] is None
    assert new["candidate_equivalence_verified"] is None


def test_unsupported_source_stays_unsupported_and_reference_unverified(
    tmp_path, old_context_module
):
    baseline = bound_baseline(tmp_path)
    unsupported = tmp_path / "unsupported.py"
    unsupported.write_text("pass\n")
    options = NumericalReference(strategy="original_saved_tensor_offload")
    new = context(
        baseline, options=options, original_script=unsupported, retained_script=unsupported
    )
    old = old_context_module.numerical_reference_context(
        options,
        baseline=baseline,
        original_script=unsupported,
        original_args=[],
        retained_script=unsupported,
    )
    unchanged_except_scope(new, old)
    assert new["original_source"]["status"] == "unsupported"
    assert new["capability_status"] == "unavailable_under_current_preconditions"
    assert not all(new["explicit_reference_preconditions"].values())
    assert new["reference_execution_verified"] is None
    assert new["candidate_equivalence_verified"] is None


def test_missing_source_does_not_gain_binding_or_completed_sequence(tmp_path, old_context_module):
    baseline = bound_baseline(tmp_path)
    absent = tmp_path / "missing.py"
    options = NumericalReference(strategy="original_workload_checkpoint")
    new = context(baseline, options=options, original_script=absent, retained_script=absent)
    old = old_context_module.numerical_reference_context(
        options, baseline=baseline, original_script=absent, original_args=[], retained_script=absent
    )
    unchanged_except_scope(new, old)
    assert new["original_source"]["status"] == "unknown"
    assert new["comparison_reference"]["original_baseline"]["status"] == "unknown"
    assert new["comparison_reference"]["original_baseline"]["source_and_argv_bound"] is False
    assert new["reference_execution_verified"] is None


def test_original_context_and_shared_solver_limits_are_unchanged(tmp_path):
    value = context(bound_baseline(tmp_path))
    assert MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES == 12 * 1024
    assert MAX_SOLVER_CONTEXT_BYTES == 64 * 1024
    assert (
        len(json.dumps(value, ensure_ascii=True).encode()) <= MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES
    )
    combined = solver_prompt_context(numerical_reference_context=value)
    assert combined["numerical_reference_context"] == value
    assert len(json.dumps(combined, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    with pytest.raises(ValueError, match="numerical_reference_context"):
        solver_prompt_context(
            numerical_reference_context={"x": "x" * MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES}
        )
