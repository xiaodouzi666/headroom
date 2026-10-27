"""Pure synthetic CLI feedback tests; no target execution or provider calls."""

import copy
import json
import socket

import pytest
from test_patch import mock_router, proposal

from headroom import patch
from headroom.patch_cli_feedback import cli_override_contract, rejected_cli_feedback
from headroom.verify.policy import PolicyIssue, check_cli_changes

ISSUE = PolicyIssue("CLI_OPTION_FORBIDDEN", "CLI override is outside memory/shape controls.")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No live network in CLI feedback fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def feedback(changes, **kwargs):
    return rejected_cli_feedback(
        changes,
        reason=kwargs.get("reason", "CLI_OPTION_FORBIDDEN"),
        issues=kwargs.get("issues", (ISSUE,)),
    )


def test_allowlist_is_descriptive_and_does_not_add_alias_or_permission():
    contract = cli_override_contract()
    assert "--accum-steps" not in contract["canonical_long_options"]
    for flag in ("--grad_accum_steps", "--grad-accum-steps", "--gradient_accumulation_steps"):
        assert flag in contract["canonical_long_options"]
        report = check_cli_changes([], [flag, "2"])
        assert not any(issue.code == "CLI_OPTION_FORBIDDEN" for issue in report.issues)
    assert "--max-steps" in contract["canonical_long_options"]
    assert any(
        issue.code == "TRAINING_TRUNCATED"
        for issue in check_cli_changes([], ["--max-steps", "1"]).issues
    )
    assert any(
        issue.code == "CLI_OPTION_FORBIDDEN"
        for issue in check_cli_changes([], ["--accum-steps", "2"]).issues
    )


@pytest.mark.parametrize(
    "changes", [["--accum-steps"], ["--accum-steps", "2"], ["--accum-steps=2"]]
)
def test_exact_rejected_flag_is_explained_without_changing_input(changes):
    original = copy.deepcopy(changes)
    value = feedback(changes)
    assert value["status"] == "complete"
    assert value["offending_flags"] == ["--accum-steps"]
    assert value["values_included"] is False
    assert changes == original


def test_accepted_names_and_values_do_not_appear_as_offenders():
    value = feedback(["--foreach", "False", "--odd-option", "PRIVATE_VALUE_MARKER"])
    assert value["offending_flags"] == ["--odd-option"]
    assert "PRIVATE_VALUE_MARKER" not in json.dumps(value)


@pytest.mark.parametrize(
    "changes",
    [
        ["--odd-option=PRIVATE_VALUE_MARKER"],
        ["--odd-option", "PRIVATE_VALUE_MARKER"],
        ["--api-key=PRIVATE_VALUE_MARKER"],
        ["--secret-PRIVATE_VALUE_MARKER", "x"],
        ["--nvapi-" + "a" * 40],
        ["--sk-proj-" + "a" * 40],
        ["--" + "a" * 99],
    ],
)
def test_values_and_credential_like_flag_names_are_not_rendered(changes):
    value = feedback(changes)
    encoded = json.dumps(value)
    assert "PRIVATE_VALUE_MARKER" not in encoded
    assert "a" * 40 not in encoded
    assert value["values_included"] is False
    if changes[0].startswith("--odd-option"):
        assert value["offending_flags"] == ["--odd-option"]
    else:
        assert value["offending_flags"] == []
        assert value["withheld_flag_count"] == 1
        assert value["status"] == "partial"


@pytest.mark.parametrize(
    "changes",
    [
        None,
        "not-argv",
        [1],
        ["--bad\nflag"],
        ["--x", "1", "--x", "2"],
        ["positional"],
        ["--x"] * 61,
        ["--x", "a" * 1001],
    ],
)
def test_malformed_evidence_does_not_echo_input_or_guess_offender(changes):
    value = feedback(changes)
    assert value["status"] == "unavailable"
    assert value["offending_flags"] == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reason": "CLI_INVALID"},
        {"reason": None},
        {"issues": ()},
        {"issues": (PolicyIssue("TRAINING_TRUNCATED", "anything"),)},
    ],
)
def test_unrelated_or_unbound_host_rejection_not_explained(kwargs):
    assert feedback(["--accum-steps"], **kwargs)["status"] == "not_applicable"


def test_contradictory_host_issue_remains_unavailable():
    assert feedback(["--foreach", "False"])["status"] == "unavailable"


def test_many_flags_are_bounded_and_omission_explicit():
    value = feedback(["--bad-option-" + str(i) for i in range(60)])
    assert len(value["offending_flags"]) == 20
    assert value["omitted_flag_count"] == 40
    assert value["status"] == "partial"
    assert len(json.dumps(value).encode()) < 8192


def test_real_patch_engine_carries_contract_then_exact_cli_error_and_rejects_repeated_bad_proposal(
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    bad = proposal(before, "x = 2\n", cli_changes=["--accum-steps"])
    requests = []
    router = mock_router([bad, bad], requests)
    try:
        result = patch.PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "synthetic-cli", "type": "code"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied
    assert [item.reason for item in result.attempts] == ["CLI_OPTION_FORBIDDEN"] * 2
    assert (source / "train.py").read_text() == before
    first = json.loads(requests[0]["messages"][-1]["content"])
    retry = json.loads(requests[1]["messages"][-1]["content"])
    assert first["cli_override_contract"] == cli_override_contract()
    assert retry["cli_override_contract"] == first["cli_override_contract"]
    assert retry["repair"]["candidate_cli"]["offending_flags"] == ["--accum-steps"]
    assert retry["repair"]["reason"] == "CLI_OPTION_FORBIDDEN"
    assert retry["repair"]["previous_proposal"]["cli_changes"] == ["--accum-steps"]


def test_existing_cli_guard_still_runs_before_syntax_check(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    before = "x = 1\n"
    (source / "train.py").write_text(before)
    value = patch.apply_proposal(
        source,
        proposal(before, "x = (\n", cli_changes=["--accum-steps"]),
        work_root=tmp_path / "work",
    )
    assert not value.applied and value.reason == "CLI_OPTION_FORBIDDEN"
    assert value.attempts[0].compile_exit_code is None
    assert [issue.code for issue in value.policy_report.issues] == ["CLI_OPTION_FORBIDDEN"]
