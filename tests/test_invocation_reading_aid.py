"""Lexical argv visibility is neither target configuration nor a repair answer."""

import copy
import json

from headroom.diagnose import build_diagnosis_messages
from headroom.solver_context import invocation_reading_aid, prompt_arguments, solver_prompt_context


def context(args):
    return {
        "script": "training/entry.py",
        "script_args": prompt_arguments(args),
        "execution_argv": prompt_arguments(["/usr/bin/python3", "training/entry.py", *args]),
    }


def test_only_equals_assignments_are_split_with_original_indices_and_order():
    view = invocation_reading_aid(
        context(
            [
                "--width=7",
                "--width=9",
                "--switch",
                "--depth",
                "2",
                "positional",
                "--empty=",
                "--label=a=b",
            ]
        )
    )
    assert view["assignments"] == [
        {"index": 0, "option": "--width", "value": "7", "token": "--width=7"},
        {"index": 1, "option": "--width", "value": "9", "token": "--width=9"},
        {"index": 6, "option": "--empty", "value": "", "token": "--empty="},
        {"index": 7, "option": "--label", "value": "a=b", "token": "--label=a=b"},
    ]
    assert [item["index"] for item in view["unsupported_tokens"]] == [2, 3, 4, 5]
    assert view["target_effective_configuration"] == "unverified"
    assert view["script_args_complete"] is True
    assert view["view_complete"] is True


def test_launch_executable_is_not_relabelled_as_the_script_entrypoint():
    view = invocation_reading_aid(context(["--width=7"]))
    assert view["launch_argv_first_token"] == "/usr/bin/python3"
    assert view["recorded_script_entrypoint"] == "training/entry.py"
    assert view["assignments"][0]["index"] == 0
    assert "do not assume" in view["launch_scope"]


def test_secrets_remain_unknown_and_never_enter_readable_assignments():
    value = context(["--api-key=canary-inline", "--password", "canary-space", "--width=7"])
    view = invocation_reading_aid(value)
    assert [item["token"] for item in view["assignments"]] == ["--width=7"]
    assert view["unknown_token_indices"] == [0, 1, 2]
    assert not view["script_args_complete"]
    assert "canary" not in json.dumps(view)


def test_reading_aid_redacts_even_if_input_claims_unredacted_metadata():
    value = context([])
    value["script_args"]["values"] = ["--api-key=canary"]
    value["execution_argv"]["values"] = ["--api-key=canary"]
    view = invocation_reading_aid(value)
    assert not view["assignments"]
    assert view["launch_argv_first_token"] is None
    assert "canary" not in json.dumps(view)


def test_truncated_tail_is_not_reconstructed_from_source_defaults():
    value = context(["--width=7"])
    value["script_args"].update(complete=False, omitted_count=3)
    view = invocation_reading_aid(value)
    assert view["source_omitted_tokens"] == 3
    assert not view["script_args_complete"]
    assert len(view["assignments"]) == 1


def test_missing_redaction_metadata_keeps_values_unknown():
    value = context(["--width=7"])
    del value["script_args"]["redacted_positions"]
    view = invocation_reading_aid(value)
    assert not view["assignments"]
    assert view["unknown_token_indices"] == [0]
    assert not view["script_args_complete"]


def test_view_wire_bound_marks_omissions_and_keeps_a_contiguous_prefix():
    view = invocation_reading_aid(context(["--label=" + "界" * 300] * 8))
    assert len(json.dumps(view, ensure_ascii=True).encode()) <= 4096
    assert not view["view_complete"]
    assert view["view_omitted_visible_tokens"] > 0
    assert [item["index"] for item in view["assignments"]] == list(range(len(view["assignments"])))


def test_view_precedes_long_source_and_does_not_change_original_tokens():
    value = context(["--width=7", "--width=9"])
    before = copy.deepcopy(value)
    messages = build_diagnosis_messages(
        "LONG SOURCE DEFAULT width=100", goal="reclaim", policy={}, execution_context=value
    )
    user = messages[1]["content"]
    assert user.index('"invocation_reading_aid"') < user.index('"evidence_markdown"')
    parsed = json.loads(user)
    assert parsed["execution_context"] == value == before
    assert parsed["invocation_reading_aid"]["assignments"][1]["value"] == "9"
    shared = solver_prompt_context(execution_context=value)
    assert "invocation_reading_aid" in shared
    assert len(json.dumps(shared, ensure_ascii=True).encode()) <= 64 * 1024


def test_direct_script_launch_is_not_inferred_to_be_an_interpreter():
    value = context([])
    value["execution_argv"] = prompt_arguments(["training/entry.py"])
    view = invocation_reading_aid(value)
    assert view["launch_argv_first_token"] == view["recorded_script_entrypoint"]
    assert "directly executable script" in view["launch_scope"]


def test_truncated_script_entrypoint_remains_unknown_in_compact_view():
    value = context([])
    value["truncated_fields"] = ["script"]
    view = invocation_reading_aid(value)
    assert view["recorded_script_entrypoint"] is None
    assert not view["recorded_script_entrypoint_complete"]


def test_invalid_truncation_metadata_does_not_promote_entrypoint_to_complete():
    value = context([])
    value["truncated_fields"] = None
    view = invocation_reading_aid(value)
    assert view["recorded_script_entrypoint"] is None
    assert not view["recorded_script_entrypoint_complete"]
