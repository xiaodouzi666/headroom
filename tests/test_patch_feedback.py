"""Offline rejected-byte feedback tests; no target execution or live model calls."""

import hashlib
import json
import socket
from pathlib import Path

import pytest
from test_patch import mock_router, proposal

from headroom.patch import PatchEngine
from headroom.patch_feedback import (
    MAX_SYNTAX_FEEDBACK_BYTES,
    candidate_content_fingerprint,
    rejected_syntax_feedback,
)
from headroom.verify.policy import PolicyIssue


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No network in patch feedback tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def syntax_feedback(root, names=("train.py",), **kwargs):
    issues = tuple(PolicyIssue("SYNTAX_INVALID", "old generic message", name) for name in names)
    return rejected_syntax_feedback(root, names, reason="SYNTAX_INVALID", issues=issues, **kwargs)


def test_actual_candidate_syntax_and_compile_only(tmp_path):
    source = 'raise RuntimeError("must never execute")\nx = fbroken {1}\ny = 3\n'
    (tmp_path / "train.py").write_text(source)
    report = syntax_feedback(tmp_path)
    item = report["diagnostics"][0]
    assert report["coordinate_space"] == "rejected_candidate"
    assert item["candidate_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert item["status"] == "syntax_error"
    assert item["message"] == "invalid syntax"
    assert item["line"] == 2 and item["column"] > 1
    assert item["excerpt"][1]["text"] == "x = fbroken {1}"
    assert item["excerpt"][1]["line"] == 2
    assert report["omitted_file_count"] == 0


def test_compile_semantic_error_also_has_feedback(tmp_path):
    (tmp_path / "train.py").write_text("return 1\n")
    report = rejected_syntax_feedback(tmp_path, ("train.py",), reason="COMPILE_FAILED")
    assert report["diagnostics"][0]["message"] == "'return' outside function"


def test_credential_like_source_is_withheld(tmp_path):
    (tmp_path / "train.py").write_text('api_key = "OFFLINE_FAKE_SECRET_ONLY"\nx = (\n')
    report = syntax_feedback(tmp_path)
    item = report["diagnostics"][0]
    assert item["status"] == "withheld" and "excerpt" not in item and "message" not in item
    assert "OFFLINE_FAKE_SECRET_ONLY" not in json.dumps(report)


def test_nonchanged_and_symlink_paths_are_not_read(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("x = (\n")
    root = tmp_path / "candidate"
    root.mkdir()
    (root / "train.py").symlink_to(outside)
    assert syntax_feedback(root)["diagnostics"] == []
    assert (
        rejected_syntax_feedback(
            root,
            ("unrelated.py",),
            reason="SYNTAX_INVALID",
            issues=(PolicyIssue("SYNTAX_INVALID", "", "../outside.py"),),
        )["diagnostics"]
        == []
    )


def test_feedback_has_file_line_and_wire_bounds(tmp_path):
    names = tuple(f"train{i}.py" for i in range(6))
    for name in names:
        (tmp_path / name).write_text("x = fbroken {" + "界" * 4000 + "}\n")
    report = syntax_feedback(tmp_path, names)
    assert len(report["diagnostics"]) <= 3
    assert report["omitted_file_count"] >= 3
    assert len(json.dumps(report, ensure_ascii=False).encode()) <= MAX_SYNTAX_FEEDBACK_BYTES
    assert all(
        len(item["excerpt"]) <= 3 and item["excerpt"][0]["truncated"]
        for item in report["diagnostics"]
    )


def test_notes_and_span_metadata_do_not_change_candidate_fingerprint():
    metadata = {
        "files": [
            {"path": "train.py", "expected_sha256": "a" * 64, "expected_bytes": 4, "edits": []}
        ]
    }
    candidate = {"diff": "ignored presentation", "env_changes": {}, "cli_changes": [], "notes": []}
    before = candidate_content_fingerprint(metadata, candidate)
    candidate["notes"] = ["It is fixed now"]
    metadata["files"][0]["edits"] = ["different span presentation"]
    assert candidate_content_fingerprint(metadata, candidate) == before
    metadata["files"][0]["expected_sha256"] = "b" * 64
    assert candidate_content_fingerprint(metadata, candidate) != before
    metadata["files"][0]["expected_sha256"] = "a" * 64
    candidate["cli_changes"] = ["--batch", "2"]
    assert candidate_content_fingerprint(metadata, candidate) != before


def test_repeated_invalid_candidate_feedback_repairs_against_original(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    before = 'def forward(length):\n    assert length <= 4, f"length={length}"\n    return length\n'
    bad = before.replace('f"length={length}"', "flength={length}")
    good = before.replace("return length", "return length + 1")
    (source / "train.py").write_text(before)
    calls = []
    router = mock_router(
        [
            proposal(before, bad),
            proposal(before, bad, notes=["Corrected the syntax now"]),
            proposal(before, good),
        ],
        calls,
    )
    try:
        result = PatchEngine(router, max_repairs=2).generate_and_apply(
            source, {"fix_id": "generic-quote-fixture"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(calls) == len(result.attempts) == 3
    first = json.loads(calls[1]["messages"][-1]["content"])["repair"]
    repeated = json.loads(calls[2]["messages"][-1]["content"])["repair"]
    assert first["candidate_content"]["prior_rejected_attempts"] == []
    assert repeated["candidate_content"]["prior_rejected_attempts"] == [1]
    assert repeated["candidate_content"]["notes_excluded"] is True
    assert first["candidate_content"]["sha256"] == repeated["candidate_content"]["sha256"]
    diagnostic = repeated["candidate_syntax"]["diagnostics"][0]
    assert diagnostic["line"] == 2 and "syntax" in diagnostic["message"]
    assert diagnostic["excerpt"][1]["text"] == "    assert length <= 4, flength={length}"
    assert (source / "train.py").read_text() == before
    assert (Path(result.candidate_dir) / "train.py").read_text() == good
    assert result.runtime_verified is False


def test_normalized_validation_failure_does_not_reuse_prior_candidate(tmp_path, monkeypatch):
    import headroom.patch as patch_module

    source = tmp_path / "source"
    source.mkdir()
    before, bad, good = "value = 1\n", "value = (\n", "value = 2\n"
    (source / "train.py").write_text(before)
    original = patch_module.normalize_span_edits
    conversions = 0

    def invalid_second(*args, **kwargs):
        nonlocal conversions
        conversion = original(*args, **kwargs)
        conversions += 1
        if conversions == 2:
            conversion.proposal["unexpected_invalid_field"] = True
        return conversion

    monkeypatch.setattr(patch_module, "normalize_span_edits", invalid_second)
    calls = []
    router = mock_router(
        [proposal(before, bad), proposal(before, bad), proposal(before, good)], calls
    )
    try:
        result = PatchEngine(router, max_repairs=2).generate_and_apply(
            source, {"fix_id": "generic-validation-fixture"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(calls) == 3
    failure = json.loads(calls[2]["messages"][-1]["content"])["repair"]
    assert failure["reason"] == "SOURCE_EDIT_REJECTED"
    assert "candidate_content" not in failure
    assert (source / "train.py").read_text() == before


def test_feedback_failure_preserves_original_rejection_and_repair_limit(tmp_path, monkeypatch):
    import headroom.patch as patch_module

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("private diagnostic exception must not enter prompt")

    monkeypatch.setattr(patch_module, "rejected_syntax_feedback", unavailable)
    source = tmp_path / "source"
    source.mkdir()
    before, bad, good = "value = 1\n", "value = (\n", "value = 2\n"
    (source / "train.py").write_text(before)
    calls = []
    router = mock_router([proposal(before, bad), proposal(before, good)], calls)
    try:
        result = PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "generic-diagnostic-failure"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(calls) == 2
    content = calls[1]["messages"][-1]["content"]
    failure = json.loads(content)["repair"]
    assert failure["reason"] == "SOURCE_SYNTAX_INVALID"
    assert failure["candidate_syntax"]["status"] == "unavailable"
    assert "private diagnostic exception" not in content
    assert result.attempts[0].reason == "SOURCE_SYNTAX_INVALID"


def test_oversized_source_is_not_sent_to_parser(tmp_path, monkeypatch):
    import headroom.patch_feedback as feedback_module
    from headroom.patch_edits import MAX_FILE_BYTES

    def denied(*_args, **_kwargs):
        pytest.fail("Oversized candidate must not reach Python parser")

    monkeypatch.setattr(feedback_module, "compile", denied, raising=False)
    (tmp_path / "train.py").write_bytes(b"#" * (MAX_FILE_BYTES + 1))
    assert syntax_feedback(tmp_path)["diagnostics"] == []
