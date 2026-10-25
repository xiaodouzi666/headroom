"""Offline request-delivery tests for effective invocation and failed candidate bytes."""

import hashlib
import json

import pytest
from test_orchestrator import search_run

from headroom.diagnose import build_diagnosis_messages
from headroom.solver_context import (
    MAX_ARTIFACT_BYTES,
    MAX_DIFF_BYTES,
    MAX_SOLVER_CONTEXT_BYTES,
    candidate_context,
    candidate_evidence,
    execution_context,
    solver_prompt_context,
)
from headroom.verify.policy import merge_cli_changes


def request_payload(call):
    return json.loads(call["messages"][-1]["content"])


def fixture_artifacts(tmp_path, *, diff="--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-A\n+B\n"):
    relative = "rounds/01/patches/engine/attempt/patch.diff"
    patch = tmp_path / relative
    patch.parent.mkdir(parents=True)
    patch.write_text(diff)
    result = {
        "status": "rejected",
        "reason": "COMPILE_FAILED",
        "env_changes": {
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "NEBIUS_API_KEY": "SECRET_ENV",
        },
        "cli_changes": ["--batch_size=4"],
        "effective_cli": ["--batch_size=4", "--gradient_accumulation_steps=8"],
        "notes": ["DO_NOT_TRANSMIT_EXTRA_FIELD"],
        "attempts": [
            {
                "status": "rejected",
                "reason": "COMPILE_FAILED",
                "detail": "SyntaxError: invalid syntax",
                "policy_report": {
                    "issues": [
                        {"code": "BAD_SCOPE", "message": "statement outside its intended function"}
                    ]
                },
                "application_check": {
                    "files": [
                        {
                            "path": "train.py",
                            "before_sha256": "a" * 64,
                            "candidate_sha256": "b" * 64,
                        }
                    ]
                },
            }
        ],
    }
    (tmp_path / "rounds/01/patch-result.json").write_text(json.dumps(result))
    return {"number": 1, "patch": relative, "decision": "revert"}, patch


def test_both_real_model_requests_receive_rejected_diff_and_failed_checks(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "ENV_SECRET_MUST_NOT_APPEAR")
    monkeypatch.setenv("TAVILY_API_KEY", "OTHER_ENV_SECRET_MUST_NOT_APPEAR")
    plans = [
        {
            "before": "VALUE = 1\n",
            "after": "VALUE = 2\n",
            "checks": {"finite_candidate_losses": False, "parameter_count_unchanged": False},
            "verification_extra": {
                "completed": False,
                "parameter_count_before": 100,
                "parameter_count_after": 50,
                "loss_equivalence": "unknown",
            },
            "candidate_extra": {
                "status": "error",
                "steps": 1,
                "exception": {"type": "ValueError", "message": "non-finite candidate loss"},
            },
        },
        {"before": "VALUE = 1\n", "after": "VALUE = 3\n", "peak": 20, "target": True},
    ]
    result, store, calls, _, _ = search_run(
        tmp_path,
        plans,
        max_rounds=2,
        script_args=["--batch_size=32", "--gradient_accumulation_steps=1", "--compile=False"],
    )
    try:
        assert result["target_met"] and len(calls) == 4
        ultra = request_payload(calls[2])
        super_request = request_payload(calls[3])
        super_context = super_request["evidence_context"]
        assert ultra["execution_context"] == super_context["execution_context"]
        invocation = ultra["execution_context"]
        assert invocation["basis"] == "effective_retained_invocation"
        assert invocation["script_args"]["values"] == super_request["base_cli"]
        assert invocation["script_args"]["values"] == [
            "--batch_size=32",
            "--gradient_accumulation_steps=1",
            "--compile=False",
        ]
        assert invocation["script_args"]["complete"] is True
        assert invocation["selected_round"] is None
        assert ultra["candidate_evidence"] == super_context["candidate_evidence"]
        assert ultra["verification_feedback"] == super_context["verification_feedback"]
        candidate = ultra["candidate_evidence"][0]
        assert candidate["candidate_selected"] is False
        assert candidate["selected_after_round"] is None
        assert candidate["diff"]["available"] and not candidate["diff"]["truncated"]
        assert "-VALUE = 1" in candidate["diff"]["text"]
        assert "+VALUE = 2" in candidate["diff"]["text"]
        assert "VALUE = 2" not in super_request["sources"]["train.py"]["lines"][0]["text"]
        assert (
            candidate["diff"]["sha256"]
            == hashlib.sha256(candidate["diff"]["text"].encode()).hexdigest()
        )
        feedback = ultra["verification_feedback"][0]
        assert feedback["candidate"]["exception"]["message"] == "non-finite candidate loss"
        assert "finite_candidate_losses" in feedback["verification"]["failed_checks"]
        assert feedback["verification"]["parameter_count_before"] == 100
        assert feedback["verification"]["parameter_count_after"] == 50
        assert feedback["candidate_selected"] is False
        assert feedback["selected_after_round"]["basis"] == "original_baseline"
        serialized = json.dumps(calls)
        assert "ENV_SECRET_MUST_NOT_APPEAR" not in serialized
        assert "OTHER_ENV_SECRET_MUST_NOT_APPEAR" not in serialized
    finally:
        store.close()


def test_selected_source_stays_separate_from_rejected_candidate(tmp_path):
    plans = [
        {"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 25},
        {"before": "VALUE = 2\n", "after": "VALUE = 3\n", "checks": {"loss_tolerance": False}},
        {"before": "VALUE = 2\n", "after": "VALUE = 4\n", "peak": 20, "target": True},
    ]
    result, store, calls, _, _ = search_run(tmp_path, plans, max_rounds=3)
    try:
        assert result["target_met"]
        ultra, patcher = request_payload(calls[4]), request_payload(calls[5])
        assert ultra["execution_context"]["selected_round"] == 1
        assert patcher["evidence_context"]["candidate_evidence"] == ultra["candidate_evidence"]
        candidate = ultra["candidate_evidence"][1]
        assert candidate["candidate_selected"] is False and candidate["selected_after_round"] == 1
        assert "+VALUE = 3" in candidate["diff"]["text"]
        assert patcher["sources"]["train.py"]["lines"][0]["text"] == "VALUE = 2"
    finally:
        store.close()


def test_structural_failure_and_whitelisted_changes_are_not_lost(tmp_path):
    row, _ = fixture_artifacts(tmp_path)
    result = candidate_evidence(tmp_path, row, selected_round=None)
    assert result["patch_result_available"] is True
    assert result["last_attempt"]["detail"] == "SyntaxError: invalid syntax"
    assert result["last_attempt"]["policy_issues"][0]["code"] == "BAD_SCOPE"
    assert result["effective_cli"]["values"] == [
        "--batch_size=4",
        "--gradient_accumulation_steps=8",
    ]
    assert result["env_changes"] == {"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"}
    assert result["application_files"][0]["candidate_sha256"] == "b" * 64
    assert "SECRET_ENV" not in json.dumps(result)
    assert "DO_NOT_TRANSMIT_EXTRA_FIELD" not in json.dumps(result)


@pytest.mark.parametrize(
    "kind", ["diff_link", "directory_link", "result_link", "outside", "traversal"]
)
def test_unowned_or_linked_artifact_never_becomes_delivered_content(tmp_path, kind):
    row, patch = fixture_artifacts(tmp_path)
    external = tmp_path.parent / (tmp_path.name + "-outside.txt")
    external.write_text("OUTSIDE_ARTIFACT_MUST_NOT_LEAK")
    if kind == "diff_link":
        patch.unlink()
        patch.symlink_to(external)
    elif kind == "directory_link":
        patch.unlink()
        patch.parent.rmdir()
        patch.parent.symlink_to(tmp_path.parent, target_is_directory=True)
    elif kind == "result_link":
        result_path = tmp_path / "rounds/01/patch-result.json"
        result_path.unlink()
        result_path.symlink_to(external)
    elif kind == "outside":
        row["patch"] = str(external)
    else:
        row["patch"] = "rounds/01/patches/../../../outside.txt"
    result = candidate_evidence(tmp_path, row, selected_round=None)
    if kind == "result_link":
        assert result["patch_result_available"] is False
    else:
        assert result["diff"]["available"] is False
    assert "OUTSIDE_ARTIFACT_MUST_NOT_LEAK" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["diff", "patch_result"])
def test_oversized_artifacts_are_unknown_not_read_as_complete(tmp_path, kind):
    row, patch = fixture_artifacts(tmp_path)
    target = patch if kind == "diff" else tmp_path / "rounds/01/patch-result.json"
    target.write_bytes(b"x" * (MAX_ARTIFACT_BYTES + 1))
    result = candidate_evidence(tmp_path, row, selected_round=None)
    if kind == "diff":
        assert result["diff"]["available"] is False
        assert result["diff"]["sha256"] is None
    else:
        assert result["patch_result_available"] is False


def test_truncated_utf8_diff_records_actual_hash_and_omitted_bytes(tmp_path):
    text = "--- a/train.py\n+++ b/train.py\n" + "解释" * 3000
    row, _ = fixture_artifacts(tmp_path, diff=text)
    result = candidate_evidence(tmp_path, row, selected_round=None)["diff"]
    assert result["available"] is True and result["truncated"] is True
    assert result["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result["included_bytes"] <= MAX_DIFF_BYTES
    assert result["included_bytes"] + result["omitted_bytes"] == len(text.encode())
    assert len(result["text"].encode()) == result["included_bytes"]


def test_missing_artifacts_remain_explicit_unknown(tmp_path):
    result = candidate_evidence(tmp_path, {"number": 1}, selected_round=None)
    assert result["patch_result_available"] is False
    assert result["diff"]["available"] is False and result["diff"]["text"] is None
    assert result["last_attempt"] is None and result["status"] is None


def test_execution_context_whitelists_fields_and_redacts_credential_options():
    value = execution_context(
        script="train.py",
        script_args=["--batch_size=32", "--api-key=DO_NOT_SEND", "--password", "ALSO_SECRET"],
        execution_argv=None,
        source_files=[{"path": "train.py", "sha256": "a" * 64, "env": {"PRIVATE": "NO_ENV"}}],
        selected_round=2,
        repository_mode=False,
        seed=1337,
        max_steps=20,
        device="cuda",
        allocator_conf=None,
    )
    assert value["script_args"]["values"] == [
        "--batch_size=32",
        "--api-key=[redacted]",
        "--password",
        "[redacted]",
    ]
    assert value["script_args"]["complete"] is False
    assert value["source_files"] == [{"path": "train.py", "sha256": "a" * 64}]
    assert all(
        secret not in json.dumps(value) for secret in ["DO_NOT_SEND", "ALSO_SECRET", "NO_ENV"]
    )


def test_oversized_argument_is_omitted_and_marked_unknown():
    value = execution_context(
        script="train.py",
        script_args=["--batch=4", "x" * 1025, "--later=1"],
        execution_argv=None,
        source_files=[],
        selected_round=None,
        repository_mode=False,
        seed=1,
        max_steps=20,
        device="cuda",
        allocator_conf=None,
    )
    assert value["script_args"] == {
        "values": ["--batch=4"],
        "complete": False,
        "omitted_count": 2,
        "redacted_positions": [],
    }


def test_context_boundaries_and_old_callers():
    old = request_payload(
        {"messages": build_diagnosis_messages("evidence", goal="reclaim", policy={})}
    )
    assert "execution_context" not in old and "candidate_evidence" not in old
    with pytest.raises(ValueError, match="at most six"):
        candidate_context([{}] * 7)
    with pytest.raises(ValueError, match="bounded"):
        candidate_context([{"text": "x" * 96001}])
    with pytest.raises(ValueError, match="bounded"):
        build_diagnosis_messages(
            "evidence", goal="reclaim", policy={}, execution_context={"text": "x" * 16385}
        )


def test_capture_requests_redact_cli_credentials_without_changing_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "ENV_CREDENTIAL_SENTINEL")
    args = [
        "--batch_size=32",
        "--gradient_accumulation_steps=1",
        "--compile=False",
        "--tokens_per_iter=32768",
        "--api-key=EQUALS_KEY_SENTINEL",
        "--token",
        "SPLIT_TOKEN_SENTINEL",
        "--password=EQUALS_PASSWORD_SENTINEL",
        "--secret",
        "SPLIT_SECRET_SENTINEL",
    ]
    result, store, calls, verifies, _ = search_run(
        tmp_path,
        [{"before": "VALUE = 1\n", "after": "VALUE = 2\n", "peak": 20, "target": True}],
        max_rounds=1,
        script_args=args,
    )
    try:
        assert result["target_met"] and len(calls) == 2
        ultra, patcher = request_payload(calls[0]), request_payload(calls[1])
        invocation = ultra["execution_context"]
        assert invocation == patcher["evidence_context"]["execution_context"]
        visible = invocation["script_args"]
        assert visible["values"][:4] == args[:4]
        assert visible["complete"] is False
        assert visible["redacted_positions"] == [4, 5, 6, 7, 8, 9]
        assert patcher["base_cli"] == visible["values"]
        assert patcher["base_cli_visibility"]["redacted_positions"] == visible["redacted_positions"]
        # Only prompt visibility changes: original args still reach candidate execution.
        assert verifies[0]["kwargs"]["script_args"] == tuple(merge_cli_changes(args, []))
        serialized = json.dumps(calls)
        for sentinel in (
            "ENV_CREDENTIAL_SENTINEL",
            "EQUALS_KEY_SENTINEL",
            "SPLIT_TOKEN_SENTINEL",
            "EQUALS_PASSWORD_SENTINEL",
            "SPLIT_SECRET_SENTINEL",
        ):
            assert sentinel not in serialized
    finally:
        store.close()


def test_structural_failure_reaches_both_next_outer_round_requests(tmp_path):
    bad = {"before": "VALUE = 1\n", "after": "VALUE = (\n"}
    result, store, calls, verifies, _ = search_run(tmp_path, [bad, bad], max_rounds=2)
    try:
        assert not result["target_met"] and not verifies
        # Default repair budget remains unchanged: Ultra + four Super attempts per outer round.
        assert len(calls) == 10
        ultra, patcher = request_payload(calls[5]), request_payload(calls[6])
        candidate = ultra["candidate_evidence"][0]
        assert candidate == patcher["evidence_context"]["candidate_evidence"][0]
        assert candidate["candidate_selected"] is False
        assert candidate["selected_after_round"] is None
        assert candidate["status"] == "rejected"
        assert candidate["last_attempt"]["reason"] == "SOURCE_SYNTAX_INVALID"
        assert candidate["last_attempt"]["detail"] is None
        assert candidate["last_attempt"]["policy_issues"][0]["code"] == "SOURCE_SYNTAX_INVALID"
        assert candidate["last_attempt"]["policy_issues"][0]["path"] == "train.py"
        assert candidate["last_attempt"]["policy_issues"][0]["line"] == 1
        assert candidate["diff"]["available"] is True
        assert "+VALUE = (" in candidate["diff"]["text"]
        assert (
            ultra["verification_feedback"] == patcher["evidence_context"]["verification_feedback"]
        )
        assert ultra["verification_feedback"][0]["verification_available"] is False
        assert ultra["verification_feedback"][0]["candidate"] is None
    finally:
        store.close()


@pytest.mark.parametrize("kind", ["non_object", "nested_json", "surrogate_argument"])
def test_malformed_untrusted_patch_result_is_unknown_or_partial(tmp_path, kind):
    row, _ = fixture_artifacts(tmp_path)
    path = tmp_path / "rounds/01/patch-result.json"
    if kind == "non_object":
        path.write_text("[]")
    elif kind == "nested_json":
        path.write_text("[" * 2000 + "0" + "]" * 2000)
    else:
        path.write_text(json.dumps({"effective_cli": ["--batch=4", "\ud800", "--later=1"]}))
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    if kind == "surrogate_argument":
        assert candidate["patch_result_available"] is True
        assert candidate["effective_cli"]["values"] == ["--batch=4"]
        assert candidate["effective_cli"]["complete"] is False
        assert candidate["effective_cli"]["omitted_count"] == 2
    else:
        assert candidate["patch_result_available"] is False


def test_json_escaped_content_stays_bounded_with_explicit_omissions(tmp_path):
    row, _ = fixture_artifacts(tmp_path, diff="\x00" * 4096)
    path = tmp_path / "rounds/01/patch-result.json"
    result = json.loads(path.read_text())
    result.update(
        reason="\x00" * 512,
        env_changes={"PYTORCH_CUDA_ALLOC_CONF": "\x00" * 1024},
        cli_changes=["--option=" + "x" * 900] * 10,
        effective_cli=["--option=" + "x" * 900] * 10,
    )
    result["attempts"][-1].update(
        detail="\x00" * 2000,
        policy_report={"issues": [{"code": "\x00" * 128, "message": "\x00" * 512}] * 8},
        application_check={
            "files": [
                {"path": "\x00" * 512, "before_sha256": "a" * 64, "candidate_sha256": "b" * 64}
            ]
            * 8
        },
    )
    path.write_text(json.dumps(result))
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    assert candidate["patch_result_available"] is True
    assert candidate["diff"]["truncated"] is True
    assert candidate["last_attempt"]["detail_truncated"] is True
    assert candidate["last_attempt"]["policy_issues"][0]["truncated"] is True
    assert candidate["last_attempt"]["policy_issues_omitted"] == 4
    assert candidate["application_files_omitted"] == 4
    assert candidate["application_files"][0]["path_truncated"] is True
    assert "env_changes.PYTORCH_CUDA_ALLOC_CONF" in candidate["truncated_fields"]
    assert len(json.dumps(candidate, ensure_ascii=False).encode()) <= 16000


def test_execution_context_records_bounded_sources_and_launch_argv():
    argv = ["python", "train.py", "--batch_size=32", "--token", "ARGV_SECRET_SENTINEL"]
    value = execution_context(
        script="train.py",
        script_args=argv[2:],
        execution_argv=argv,
        source_files=[{"path": "x" * 500, "sha256": "a" * 64}] * 20,
        selected_round=None,
        repository_mode=True,
        seed=1337,
        max_steps=20,
        device="cuda",
        allocator_conf="x" * 1024,
    )
    assert value["execution_argv"]["values"][:3] == argv[:3]
    assert value["execution_argv"]["complete"] is False
    assert value["source_files_omitted"] > 0
    assert "allocator_environment.PYTORCH_CUDA_ALLOC_CONF" in value["truncated_fields"]
    assert "ARGV_SECRET_SENTINEL" not in json.dumps(value)
    assert len(json.dumps(value, ensure_ascii=False).encode()) <= 16384


def test_both_wire_requests_omit_old_rounds_as_paired_unknowns(tmp_path):
    after = "VALUE = 2\n# " + "界" * 2000 + "\n"
    plan = {
        "before": "VALUE = 1\n",
        "after": after,
        "checks": {"loss_tolerance": False},
        "verification_extra": {"notes": ["界" * 1000] * 8},
        "candidate_extra": {"exception": {"type": "ValueError", "message": "界" * 1000}},
    }
    result, store, calls, _, _ = search_run(tmp_path, [plan] * 6, max_rounds=6)
    fields = (
        "execution_context",
        "candidate_evidence",
        "verification_feedback",
        "solver_context_availability",
    )
    try:
        assert len(calls) == 12
        ultra = request_payload(calls[10])
        super_context = request_payload(calls[11])["evidence_context"]
        assert {key: ultra[key] for key in fields} == {key: super_context[key] for key in fields}
        availability = ultra["solver_context_availability"]
        assert availability["complete"] is False
        assert availability["omitted_unknown"]["candidate_rounds"]
        assert (
            availability["omitted_unknown"]["candidate_rounds"]
            == availability["omitted_unknown"]["verification_rounds"]
        )
        candidate_rounds = [item["round"] for item in ultra["candidate_evidence"]]
        assert candidate_rounds == [item["round"] for item in ultra["verification_feedback"]]
        assert candidate_rounds[-1] == 5
        for payload, ascii_mode in ((ultra, False), (super_context, True)):
            assert (
                len(
                    json.dumps(
                        {key: payload[key] for key in fields}, ensure_ascii=ascii_mode
                    ).encode()
                )
                <= MAX_SOLVER_CONTEXT_BYTES
            )
        assert result["search"]["rounds_executed"] == 6
    finally:
        store.close()


def test_combined_context_never_matches_candidates_by_list_position():
    result = solver_prompt_context(
        execution_context={"script_args": {"values": ["--batch=32"]}},
        candidate_evidence=[
            {"round": 1, "diff": "界" * 6000},
            {"round": 3, "diff": "界" * 6000},
        ],
        verification_feedback=[
            {"round": 2, "verification": {"passed": None, "failure": "\x00" * 5000}},
            {"round": 3, "verification": {"passed": False}},
        ],
    )
    assert len(json.dumps(result, ensure_ascii=True).encode()) <= MAX_SOLVER_CONTEXT_BYTES
    assert [item["round"] for item in result["candidate_evidence"]] == [3]
    assert [item["round"] for item in result["verification_feedback"]] == [3]
    assert result["verification_feedback"][0]["verification"]["passed"] is False
    omitted = result["solver_context_availability"]["omitted_unknown"]
    assert omitted["candidate_rounds"] == [1]
    assert omitted["verification_rounds"] == [2]


def test_maximal_hostile_candidate_metadata_is_omitted_without_aborting(tmp_path):
    row, _ = fixture_artifacts(tmp_path, diff="\x00" * 4096)
    path = tmp_path / "rounds/01/patch-result.json"
    result = json.loads(path.read_text())
    result.update(
        status="x" * 64,
        reason="x" * 128,
        cli_changes=["--password=ARG_SECRET"] * 100,
        effective_cli=["--password=ARG_SECRET"] * 100,
        env_changes={"PYTORCH_CUDA_ALLOC_CONF": "\x00" * 512},
    )
    result["attempts"][-1].update(
        status="x" * 64,
        reason="x" * 128,
        detail="\x00" * 1024,
        policy_report={
            "issues": [
                {
                    "code": "\x00" * 64,
                    "message": "\x00" * 256,
                    "path": "\x00" * 256,
                    "line": 10**2000,
                }
            ]
            * 4
        },
        application_check={
            "files": [
                {
                    "path": "\x00" * 256,
                    "before_sha256": "a" * 64,
                    "candidate_sha256": "b" * 64,
                }
            ]
            * 4
        },
    )
    path.write_text(json.dumps(result))
    candidate = candidate_evidence(tmp_path, row, selected_round=None)
    assert candidate["patch_result_available"] is True
    assert candidate["diff"]["available"] is True
    assert candidate["summary_overflow_omitted_fields"]
    assert candidate["last_attempt"] is None
    assert candidate["cli_changes"]["complete"] is False
    assert "ARG_SECRET" not in json.dumps(candidate)
    assert len(json.dumps(candidate, ensure_ascii=False).encode()) <= 15996
    assert len(candidate_context([candidate] * 6)) == 6
