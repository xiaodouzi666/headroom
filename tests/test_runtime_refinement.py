"""Offline refinement guard tests; saved metadata never counts as a new repair."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from headroom import runtime_refinement as M

BASE = Path(__file__).parent


def original():
    fixture = json.loads((BASE / "fixtures/runtime-error-r15-s4.json").read_text())
    checked = SimpleNamespace(**fixture["diagnosis_flags"])
    return checked, fixture["row"], fixture["patch"], fixture["failure"]


def eligible(checked, row, patch, failure):
    return M.refinement_eligible(checked, row, patch, failure)


def test_actual_saved_r15_python_consumer_error_is_eligible_only_for_new_work():
    args = original()
    before = copy.deepcopy(args[1:])
    assert eligible(*args)
    assert args[1:] == before


@pytest.mark.parametrize(
    "change",
    [
        "not_ready",
        "invalid",
        "supplement",
        "kept",
        "static_policy",
        "cli_changed",
        "env_changed",
        "completed",
        "loss_changed",
        "precision_changed",
        "parameter_changed",
        "policy_changed",
        "capture_partial",
        "cleanup_unknown",
        "artifact_cleanup_unknown",
        "oom",
        "timeout",
        "preparation",
        "cuda_assert",
        "trace_partial",
        "trace_missing",
        "foreign_run",
        "pid_missing",
        "preparation_failure",
    ],
)
def test_unsafe_semantic_unknown_or_nonimplementation_failures_never_use_fast_path(change):
    checked, row, patch, failure = original()
    v, after = row["verification"], row["verification"]["after"]
    if change == "not_ready":
        checked.ready_for_patch = False
    elif change == "invalid":
        checked.valid = False
    elif change == "supplement":
        checked.requires_supplement = True
    elif change == "kept":
        row["decision"] = "keep"
    elif change == "static_policy":
        patch["policy_report"]["allowed"] = False
    elif change == "cli_changed":
        patch["cli_changes"] = ["--batch=2"]
    elif change == "env_changed":
        patch["env_changes"] = {"PYTORCH_CUDA_ALLOC_CONF": "backend:cudaMallocAsync"}
    elif change == "completed":
        v["completed"] = True
    elif change == "loss_changed":
        v["loss_equivalence"] = "changed"
    elif change == "precision_changed":
        v["numerics_changed"] = True
    elif change == "parameter_changed":
        v["checks"]["parameter_count_unchanged"] = False
    elif change == "policy_changed":
        v["checks"]["numerics_policy"] = False
    elif change == "capture_partial":
        after["capture_complete"] = False
    elif change == "cleanup_unknown":
        after["cleanup_verified"] = None
    elif change == "artifact_cleanup_unknown":
        after["execution"]["artifact_cleanup"]["cleanup_verified"] = False
    elif change in {"oom", "timeout", "preparation"}:
        after["status"] = change
    elif change == "cuda_assert":
        after["exception"]["type"] = failure["exception_type"] = "RuntimeError"
    elif change == "trace_partial":
        failure["trace_complete"] = False
    elif change == "trace_missing":
        failure["source_frames"] = []
    elif change == "foreign_run":
        failure["run_id"] = "f" * 32
    elif change == "pid_missing":
        after.pop("pid")
    elif change == "preparation_failure":
        after["reason"] = "PREPARATION_FAILED"
    assert not eligible(checked, row, patch, failure)


def test_full_failed_diff_and_runtime_frames_are_bounded_and_not_mutated():
    _, row, _, failure = original()
    context = M.refinement_context(
        failure, row["candidate_evidence"], failed_round=1, origin_round=1
    )
    assert context["failure"]["source_frames"][-1]["line"] == 114
    assert len(json.dumps(context).encode()) <= M.MAX_CONTEXT_BYTES
    candidate = copy.deepcopy(row["candidate_evidence"])
    candidate["diff"]["truncated"] = True
    assert M.refinement_context(failure, candidate, failed_round=1, origin_round=1) is None
    candidate["diff"]["truncated"] = False
    candidate["diff"]["text"] = "x" * 20000
    assert M.refinement_context(failure, candidate, failed_round=1, origin_round=1) is None


def state_fixture(tmp_path):
    job = tmp_path / "job"
    run = job / "lab" / ("b" * 32)
    source = run / "source"
    source.mkdir(parents=True)
    raw = b"VALUE = 1\n"
    (source / "entry.py").write_bytes(raw)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "source": {
                    "files": {
                        "entry.py": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
                    }
                }
            }
        )
    )
    evidence = job / "evidence.json"
    evidence.write_text('{"measured":true}\n')
    settings = {
        "selected_run_id": "b" * 32,
        "policy": {"allow_numerics_change": False},
        "target": "fix-oom",
        "seed": 1,
        "max_steps": 20,
    }
    return job, source, evidence, settings


def test_contract_binds_complete_source_evidence_configuration_and_selected_run(tmp_path):
    job, source, evidence, settings = state_fixture(tmp_path)
    fingerprint = M.contract_fingerprint
    args = (job, source, ["entry.py"], [evidence], settings)
    expected = fingerprint(*args)
    assert isinstance(expected, str) and len(expected) == 64
    changed = copy.deepcopy(settings)
    changed["policy"]["allow_numerics_change"] = True
    assert fingerprint(job, source, ["entry.py"], [evidence], changed) != expected
    evidence.write_text('{"measured":false}\n')
    assert fingerprint(*args) != expected
    (source / "entry.py").write_text("VALUE = 2\n")
    assert fingerprint(*args) is None


def test_omitted_extra_file_symlink_or_nonoriginal_tree_disables_reuse(tmp_path):
    job, source, evidence, settings = state_fixture(tmp_path)
    fingerprint = M.contract_fingerprint
    args = (job, source, ["entry.py"], [evidence], settings)
    (source / "unlisted.py").write_text("MISSING = 1\n")
    assert fingerprint(*args) is None
    (source / "unlisted.py").unlink()
    saved = (source / "entry.py").read_bytes()
    (source / "entry.py").unlink()
    outside = tmp_path / "outside.py"
    outside.write_bytes(saved)
    (source / "entry.py").symlink_to(outside)
    assert fingerprint(*args) is None
    assert fingerprint(job, tmp_path, ["entry.py"], [evidence], settings) is None


@pytest.mark.parametrize(
    "content",
    ['{"source":null}', '{"source":[]}', '{"source":' + "[" * 1100 + "0" + "]" * 1100 + "}"],
)
def test_bad_optional_manifest_disables_reuse_without_breaking_normal_flow(tmp_path, content):
    job, source, evidence, settings = state_fixture(tmp_path)
    (source.parent / "manifest.json").write_text(content)
    assert M.contract_fingerprint(job, source, ["entry.py"], [evidence], settings) is None


def test_malformed_optional_execution_status_does_not_raise():
    checked, row, patch, failure = original()
    row["verification"]["after"]["status"] = []
    assert not eligible(checked, row, patch, failure)
