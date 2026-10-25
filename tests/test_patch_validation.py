"""Generic diff/application regressions, with no model or workload execution."""

import difflib
import json
import os
import subprocess

import pytest
from unidiff import PatchSet
from unidiff.errors import UnidiffParseError

from headroom.patch_validation import (
    MAX_DIAGNOSTIC_CHARS,
    bounded_structural_error,
    verify_exact_application,
)


def unified(before, after, name="train.py", context=3):
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="a/" + name,
            tofile="b/" + name,
            n=context,
        )
    )


def roots(tmp_path, before, after, name="train.py"):
    source, candidate = tmp_path / "source", tmp_path / "candidate"
    for root in (source, candidate):
        root.mkdir(exist_ok=True)
        (root / name).parent.mkdir(parents=True, exist_ok=True)
    if before is not None:
        (source / name).write_bytes(before.encode("utf-8"))
    (candidate / name).write_bytes(after.encode("utf-8"))
    return source, candidate


def expect_error(diff, source, candidate, code):
    with pytest.raises(ValueError) as caught:
        verify_exact_application(diff, source, candidate)
    detail = json.loads(str(caught.value))
    assert detail["code"] == code
    return detail


@pytest.mark.parametrize(
    ("diff", "code", "line", "prefix"),
    [
        ("--- a/train.py\n+++ b/train.py\n@@ -1,2 +1,2 @@\n x\n", "hunk_short", 5, None),
        ("--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\nx\n", "hunk_bad_prefix", 4, "x"),
        ("--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n+x\n+y\n", "hunk_long", 5, "+"),
        ("--- a/train.py\n+++ b/train.py\n@@ -1, +1 @@\n x\n", "invalid_hunk_header", 3, None),
    ],
)
def test_structural_diagnostics_include_location_and_counts(diff, code, line, prefix):
    result = json.loads(bounded_structural_error(diff, UnidiffParseError("private raw content")))
    assert result["code"] == code
    assert result["file"] == "train.py"
    assert result["line"] == line
    if prefix is not None:
        assert result["prefix"] == prefix
    if code != "invalid_hunk_header":
        assert result["hunk"] == 1
        assert "declared_old" in result and "observed_new" in result
    assert "private raw content" not in str(result)


def test_diagnostic_can_wrap_actual_unidiff_error():
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1,3 +1,3 @@\n a\n"
    with pytest.raises(UnidiffParseError) as caught:
        PatchSet(diff.splitlines(keepends=True))
    result = json.loads(bounded_structural_error(diff, caught.value))
    assert result["code"] == "hunk_short"
    assert result["observed_old"] == result["observed_new"] == 1
    assert result["declared_old"] == result["declared_new"] == 3


def test_diagnostic_does_not_echo_long_or_control_character_code():
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n!" + "\x1b" + "private" * 10000 + "\n"
    message = bounded_structural_error(diff, ValueError("also private" * 10000))
    assert len(message) <= MAX_DIAGNOSTIC_CHARS
    assert "private" not in message and "\x1b" not in message
    assert json.loads(message)["prefix"] == "!"


@pytest.mark.parametrize("diff", [None, "\x00", "x" * 512001, "\ud800"])
def test_diagnostic_bounds_invalid_input(diff):
    result = bounded_structural_error(diff, ValueError())
    assert len(result) <= MAX_DIAGNOSTIC_CHARS
    assert json.loads(result)["code"] in {"diff_must_be_text", "diff_bounds", "diff_not_utf8"}


def test_multifunction_context_changes_and_hash_receipts(tmp_path):
    before = "def first():\n    return 1\n\n\ndef second():\n    return 2\n"
    after = before.replace("return 1", "return 3").replace("return 2", "return 4")
    source, candidate = roots(tmp_path, before, after)
    receipt = verify_exact_application(unified(before, after, context=1), source, candidate)
    assert receipt["verified"]
    assert receipt["files"][0]["hunks"] == 2
    assert receipt["files"][0]["expected_sha256"] == receipt["files"][0]["candidate_sha256"]
    assert (source / "train.py").read_text() == before


def test_repeated_blocks_cannot_silently_move_edit(tmp_path):
    before = "block = 1\nrepeat = 2\n\nblock = 1\nrepeat = 2\n"
    intended = "block = 1\nrepeat = 2\n\nblock = 9\nrepeat = 2\n"
    wrong = "block = 9\nrepeat = 2\n\nblock = 1\nrepeat = 2\n"
    source, candidate = roots(tmp_path, before, wrong)
    detail = expect_error(
        unified(before, intended, context=1), source, candidate, "application_content_mismatch"
    )
    assert detail["expected_sha256"] != detail["candidate_sha256"]


def test_valid_header_rejects_unchanged_text_outside_hunk_modified(tmp_path):
    before, after = "a=1\nb=2\nc=3\n", "a=4\nb=2\nc=3\n"
    source, candidate = roots(tmp_path, before, "a=4\nb=2\nc=9\n")
    expect_error(
        unified(before, after, context=0), source, candidate, "application_content_mismatch"
    )


def test_context_must_match_at_exact_original_location(tmp_path):
    source, candidate = roots(tmp_path, "same\nwrong\nsame\n", "same\nwrong\nnew\n")
    diff = "--- a/train.py\n+++ b/train.py\n@@ -2 +2 @@\n-same\n+new\n"
    detail = expect_error(diff, source, candidate, "source_content_mismatch")
    assert detail["source_line"] == 2 and detail["prefix"] == "-"


@pytest.mark.parametrize(
    ("before", "after", "diff"),
    [
        ("a\nb\n", "a\nb\nc\n", "--- a/train.py\n+++ b/train.py\n@@ -2,0 +3 @@\n+c\n"),
        ("a\nb\n", "x\na\nb\n", "--- a/train.py\n+++ b/train.py\n@@ -0,0 +1 @@\n+x\n"),
        ("", "x\n", "--- a/train.py\n+++ b/train.py\n@@ -0,0 +1 @@\n+x\n"),
        ("a\nb\n", "a\n", "--- a/train.py\n+++ b/train.py\n@@ -2 +1,0 @@\n-b\n"),
        ("a\nb\n", "b\n", "--- a/train.py\n+++ b/train.py\n@@ -1 +0,0 @@\n-a\n"),
    ],
)
def test_explicit_eof_bof_and_deletion_positions_are_legal(tmp_path, before, after, diff):
    source, candidate = roots(tmp_path, before, after)
    assert verify_exact_application(diff, source, candidate)["verified"]


def test_zero_context_middle_insertion_cannot_drift_to_eof(tmp_path):
    before = "def one():\n    return 1\n\ndef two():\n    return 2\n"
    wrong = before + "# inserted\n"
    source, candidate = roots(tmp_path, before, wrong)
    diff = "--- a/train.py\n+++ b/train.py\n@@ -2,0 +3 @@\n+# inserted\n"
    expect_error(diff, source, candidate, "application_content_mismatch")


@pytest.mark.parametrize("new_position", [1, 4])
def test_wrong_target_coordinates_are_rejected(tmp_path, new_position):
    source, candidate = roots(tmp_path, "a\nb\n", "a\nx\nb\n")
    diff = f"--- a/train.py\n+++ b/train.py\n@@ -1,0 +{new_position} @@\n+x\n"
    expect_error(diff, source, candidate, "target_position_mismatch")


def test_overlapping_hunks_rejected(tmp_path):
    source, candidate = roots(tmp_path, "a\nb\n", "x\ny\n")
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-a\n+x\n@@ -1 +2 @@\n-a\n+y\n"
    expect_error(diff, source, candidate, "source_range_mismatch")


def test_multiple_files_and_new_file(tmp_path):
    source, candidate = roots(tmp_path, "a\n", "b\n")
    (candidate / "helper.py").write_text("answer=42\n")
    diff = unified("a\n", "b\n") + "--- /dev/null\n+++ b/helper.py\n@@ -0,0 +1 @@\n+answer=42\n"
    result = verify_exact_application(diff, source, candidate)
    assert [entry["path"] for entry in result["files"]] == ["train.py", "helper.py"]


def test_new_file_header_cannot_overwrite_existing(tmp_path):
    source, candidate = roots(tmp_path, "old\n", "new\n")
    diff = "--- /dev/null\n+++ b/train.py\n@@ -0,0 +1 @@\n+new\n"
    expect_error(diff, source, candidate, "added_file_already_exists")


@pytest.mark.parametrize(
    ("before", "after", "diff"),
    [
        (
            "old",
            "new",
            "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n\\ No newline at end of file\n",
        ),
        (
            "old",
            "new\n",
            "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-old\n\\ No newline at end of file\n+new\n",
        ),
        (
            "old\n",
            "new",
            "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-old\n+new\n\\ No newline at end of file\n",
        ),
        ("old\r\n", "new\r\n", "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-old\r\n+new\r\n"),
        (
            "名字 = '\u2028'\n",
            "名字 = '你好'\n",
            "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-名字 = '\u2028'\n+名字 = '你好'\n",
        ),
    ],
)
def test_utf8_crlf_and_explicit_no_final_newline(tmp_path, before, after, diff):
    source, candidate = roots(tmp_path, before, after)
    assert verify_exact_application(diff, source, candidate)["verified"]


def test_no_newline_marker_cannot_hide_a_midfile_join(tmp_path):
    source, candidate = roots(tmp_path, "a\nb\n", "xb\n")
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-a\n+x\n\\ No newline at end of file\n"
    expect_error(diff, source, candidate, "no_newline_not_at_eof")


@pytest.mark.parametrize("name", ["../outside.py", ".env.py", ".git/hooks.py"])
def test_protected_paths_rejected(tmp_path, name):
    source, candidate = roots(tmp_path, "a\n", "b\n")
    diff = f"--- a/{name}\n+++ b/{name}\n@@ -1 +1 @@\n-a\n+b\n"
    expect_error(diff, source, candidate, "unsafe_target_path")


def test_candidate_symlink_and_fifo_are_not_followed(tmp_path):
    source, candidate = roots(tmp_path, "a\n", "b\n")
    diff = unified("a\n", "b\n")
    (candidate / "train.py").unlink()
    (candidate / "train.py").symlink_to(source / "train.py")
    with pytest.raises(ValueError, match="symbolic link"):
        verify_exact_application(diff, source, candidate)
    (candidate / "train.py").unlink()
    os.mkfifo(candidate / "train.py")
    expect_error(diff, source, candidate, "file_bounds_or_type")


def test_diff_does_not_execute_python(tmp_path):
    marker = tmp_path / "executed"
    before = "x=1\n"
    after = f"raise RuntimeError({str(marker)!r})\n"
    source, candidate = roots(tmp_path, before, after)
    assert verify_exact_application(unified(before, after), source, candidate)["verified"]
    assert not marker.exists()


def test_real_git_direct_fallback_can_pass_when_application_is_exact(tmp_path):
    before, after = "first=1\nsecond=2\n", "first=3\nsecond=2\n"
    source, candidate = roots(tmp_path, before, before)
    diff = unified(before, after)
    env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    for args in (["init", "--quiet", "--template="], ["add", "--all"]):
        subprocess.run(["git", *args], cwd=candidate, env=env, check=True, capture_output=True)
    applied = subprocess.run(
        ["git", "apply", "--3way", "-"],
        cwd=candidate,
        env=env,
        input=diff,
        text=True,
        capture_output=True,
        check=False,
    )
    assert applied.returncode == 0
    assert verify_exact_application(diff, source, candidate)["verified"]


def test_later_hunk_positions_account_for_prior_insertions(tmp_path):
    before = "a\nb\nc\nd\ne\n"
    after = "a\nu\nv\nb\nc\ne\n"
    source, candidate = roots(tmp_path, before, after)
    receipt = verify_exact_application(unified(before, after, context=0), source, candidate)
    assert receipt["files"][0]["hunks"] == 2


def test_actual_git_zero_context_drift_is_detected_without_executing_source(tmp_path):
    before = "def first():\n    return 1\n\ndef second():\n    return 2\n"
    source, candidate = roots(tmp_path, before, before)
    diff = "--- a/train.py\n+++ b/train.py\n@@ -2,0 +3 @@\n+# intended between functions\n"
    env = {"PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
    for args in (["init", "--quiet", "--template="], ["add", "--all"]):
        subprocess.run(["git", *args], cwd=candidate, env=env, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "apply", "--3way", "-"],
        cwd=candidate,
        env=env,
        input=diff,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    # This installed Git accepts the zero-context hunk at EOF. Merely observing
    # exit 0 is insufficient; the declared location must still be enforced.
    assert (candidate / "train.py").read_text() == before + "# intended between functions\n"
    expect_error(diff, source, candidate, "application_content_mismatch")


def test_no_newline_context_marker_preserves_unchanged_eof(tmp_path):
    before, after = "a\nlast", "b\nlast"
    source, candidate = roots(tmp_path, before, after)
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1,2 +1,2 @@\n-a\n+b\n last\n\\ No newline at end of file\n"
    assert verify_exact_application(diff, source, candidate)["verified"]


def test_duplicate_and_unpaired_no_newline_markers_are_rejected(tmp_path):
    source, candidate = roots(tmp_path, "a", "b")
    diff = "--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n\\ No newline at end of file\n-a\n+b\n"
    expect_error(diff, source, candidate, "unexpected_no_newline_marker")
