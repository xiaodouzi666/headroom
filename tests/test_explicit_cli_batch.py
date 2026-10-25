"""Explicit host-argv arithmetic is checked before patch execution."""

import copy
import json
from pathlib import Path

import pytest
from test_patch import mock_router

from headroom.patch import PatchEngine, apply_proposal
from headroom.verify.policy import check_cli_changes, merge_cli_changes

BASE = ["--batch_size=18", "--gradient_accumulation_steps=3"]


def changes(batch="6", accumulation="12"):
    return [f"--batch_size={batch}", f"--gradient_accumulation_steps={accumulation}"]


@pytest.mark.parametrize(
    "base,overrides",
    [
        (BASE, changes()),
        (["--batch_size", "18", "--gradient_accumulation_steps", "3"], changes()),
        (BASE, ["--batch_size", "6", "--gradient_accumulation_steps", "12"]),
        (BASE, ["--batch_size=6"]),
        (BASE, ["--gradient_accumulation_steps=4"]),
    ],
)
def test_explicit_product_drift_is_rejected_without_rewriting_argv(base, overrides):
    original = copy.deepcopy((base, overrides))
    report = check_cli_changes(base, overrides)
    assert not report.allowed
    issue = next(i for i in report.issues if i.code == "EFFECTIVE_BATCH_CHANGED")
    assert "18 * 3 = 54" in issue.message
    assert "runtime equivalence remains unverified" in issue.message
    assert (base, overrides) == original
    assert report.requires_runtime_verification


@pytest.mark.parametrize(
    "overrides",
    [changes("6", "9"), changes("018", "003"), [], ["--foreach=False"]],
)
def test_preserved_explicit_product_only_passes_static_guard(overrides):
    report = check_cli_changes(BASE, overrides)
    assert report.allowed, report.issues
    assert report.requires_runtime_verification
    assert "runtime verification" in report.notes[0]


@pytest.mark.parametrize(
    "base,overrides",
    [
        (["--batch_size=18"], changes()),
        (["--gradient_accumulation_steps=3"], changes()),
        ([], changes()),
        (BASE + ["--micro_batch_size=2"], changes()),
        (BASE, changes() + ["--grad_accum_steps=5"]),
        (["--batch-size=18", "--gradient_accumulation_steps=3"], changes()),
        (["--BATCH_SIZE=18", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size=18.0", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size=0", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size=-18", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size=1_8", "--gradient_accumulation_steps=3"], changes()),
        (["--batch_size=１８", "--gradient_accumulation_steps=3"], changes()),
        (BASE, changes("6.0", "9")),
        (["--batch_size=" + "1" * 1001, "--gradient_accumulation_steps=3"], changes()),
    ],
)
def test_unsupported_or_ambiguous_input_does_not_infer_a_default_or_parser(base, overrides):
    report = check_cli_changes(base, overrides)
    assert "EFFECTIVE_BATCH_CHANGED" not in {i.code for i in report.issues}
    assert report.requires_runtime_verification


@pytest.mark.parametrize(
    "base,overrides",
    [
        (BASE + ["--batch_size=2"], changes()),
        (BASE + ["--batch-size=2"], changes()),
        (BASE, changes() + ["--batch_size=7"]),
    ],
)
def test_duplicate_flags_keep_existing_cli_invalid(base, overrides):
    report = check_cli_changes(base, overrides)
    assert not report.allowed and "CLI_INVALID" in {i.code for i in report.issues}


def test_preserving_product_does_not_bypass_batch_permission():
    report = check_cli_changes(BASE, changes("6", "9"), policy={"allow_batch_change": False})
    assert not report.allowed and "BATCH_CHANGE_FORBIDDEN" in {i.code for i in report.issues}


def test_candidate_is_merged_against_actual_retained_args_not_source_defaults():
    base = ["config.py", "--batch_size=18", "--gradient_accumulation_steps=3", "--compile=False"]
    report = check_cli_changes(base, ["--batch_size=6"])
    assert not report.allowed
    assert "6 * 3 = 18" in report.issues[0].message
    assert merge_cli_changes(base, changes("6", "9")) == [
        "config.py",
        "--batch_size",
        "6",
        "--gradient_accumulation_steps",
        "9",
        "--compile",
        "False",
    ]


def cli_proposal(overrides):
    return {"diff": "", "env_changes": {}, "cli_changes": overrides, "notes": []}


def test_apply_rejects_before_candidate_copy_compile_or_target_execution(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("raise AssertionError('must never execute target')\n")

    def denied(*args, **kwargs):
        pytest.fail("Rejected explicit CLI drift must stop before candidate preparation")

    monkeypatch.setattr("headroom.patch.copy_source", denied)
    result = apply_proposal(
        source, cli_proposal(changes()), work_root=tmp_path / "work", base_cli=BASE
    )
    assert not result.applied and result.reason == "EFFECTIVE_BATCH_CHANGED"
    assert not result.runtime_verified
    assert not Path(result.candidate_dir).exists()


def test_existing_finite_patch_repair_receives_precise_cli_error(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    original = "raise AssertionError('must never execute target')\n"
    (source / "train.py").write_text(original)
    requests = []
    router = mock_router([cli_proposal(changes()), cli_proposal(changes("6", "9"))], requests)
    try:
        result = PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "adjust_invocation"}, work_root=tmp_path / "work", base_cli=BASE
        )
    finally:
        router.client.close()
    assert result.applied and not result.runtime_verified and len(requests) == 2
    assert result.attempts[0].reason == "EFFECTIVE_BATCH_CHANGED"
    repair = json.loads(requests[1]["messages"][-1]["content"])["repair"]
    issue = next(i for i in repair["policy_issues"] if i["code"] == "EFFECTIVE_BATCH_CHANGED")
    assert "18 * 3 = 54" in issue["message"] and "6 * 12 = 72" in issue["message"]
    assert (source / "train.py").read_text() == original
    assert result.effective_cli == tuple(merge_cli_changes(BASE, changes("6", "9")))


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_repeated_product_drift_cannot_exceed_existing_repair_limit(tmp_path, limit):
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text("x = 1\n")
    requests = []
    router = mock_router([cli_proposal(changes())], requests)
    try:
        result = PatchEngine(router, max_repairs=limit).generate_and_apply(
            source, {"fix_id": "adjust_invocation"}, work_root=tmp_path / "work", base_cli=BASE
        )
    finally:
        router.client.close()
    assert not result.applied and len(requests) == limit + 1
    assert all(a.reason == "EFFECTIVE_BATCH_CHANGED" for a in result.attempts)
