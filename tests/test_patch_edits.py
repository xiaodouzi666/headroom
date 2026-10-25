"""Offline exact-edit tests: generated diffs run only through static Git, never a workload."""

import ast
import builtins
import hashlib
import io
import json
import os
import socket
import sqlite3
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from headroom.patch_edits import (
    MAX_EDITS,
    MAX_FILE_BYTES,
    SCHEMA_NAME,
    SourceAnchoredProposal,
    normalize_anchored_edits,
    source_document,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch, tmp_path):
    def protected(value):
        if not isinstance(value, (str, bytes, os.PathLike)):
            return False
        path = Path(os.fsdecode(value)).resolve()
        if path.is_relative_to(tmp_path.resolve()):
            return False
        return (
            path.name == ".env"
            or path.is_relative_to(ROOT / ".cache")
            or path.is_relative_to(ROOT / "runs")
        )

    def wrap(original):
        def guarded(value, *args, **kwargs):
            if protected(value):
                raise PermissionError("Exact-edit tests cannot access real secrets or state")
            return original(value, *args, **kwargs)

        return guarded

    def denied(*_args, **_kwargs):
        raise PermissionError("Exact-edit tests deny real network and DNS")

    monkeypatch.setattr(builtins, "open", wrap(builtins.open))
    monkeypatch.setattr(io, "open", wrap(io.open))
    monkeypatch.setattr(os, "open", wrap(os.open))
    monkeypatch.setattr(sqlite3, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "OPENAI_API_KEY", "HF_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def edit(path, data, old, new):
    return {"path": path, "source_sha256": digest(data), "old_lines": old, "new_lines": new}


def proposal(edits=(), **extra):
    return {"edits": list(edits), "env_changes": {}, "cli_changes": [], "notes": [], **extra}


def put(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def git_apply(root, diff):
    command = [
        "/usr/bin/git",
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.attributesFile=/dev/null",
        "-c",
        "protocol.allow=never",
        "apply",
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CEILING_DIRECTORIES": str(root),
    }
    for args in (["--check", "-"], ["-"]):
        result = subprocess.run(
            [*command, *args],
            input=diff.encode(),
            cwd=root,
            env=env,
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stderr.decode()


def test_independent_guard_denies_network_secret_profile_and_ledger():
    for path in (
        ROOT / ".env",
        ROOT / ".cache/tokenfactory-runtime.json",
        ROOT / "runs/headroom.db",
    ):
        with pytest.raises(PermissionError):
            path.read_bytes()
    with pytest.raises(PermissionError):
        socket.getaddrinfo("example.invalid", 443)
    with pytest.raises(PermissionError):
        sqlite3.connect("file:" + str(ROOT / ".cache/budget.db") + "?mode=ro", uri=True)


def test_schema_and_configuration_contract():
    schema = SourceAnchoredProposal.model_json_schema()
    assert schema["title"] == SCHEMA_NAME
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {"edits", "env_changes", "cli_changes", "notes"}
    assert "pattern" not in json.dumps(schema)
    fields = schema["$defs"]["SourceAnchoredEdit"]["properties"]
    assert set(fields) == {"path", "source_sha256", "old_lines", "new_lines"}
    assert fields["old_lines"]["type"] == "array"
    value = SourceAnchoredProposal(**proposal(notes=["literal \\n stays literal"]))
    assert value.notes == ["literal \\n stays literal"]


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
@pytest.mark.parametrize("terminal", [False, True])
def test_real_git_preserves_line_endings_eof_and_expected_whole_file(tmp_path, ending, terminal):
    rows = [b"def value():", b"    result = 1", b"    return result"]
    data = ending.join(rows) + (ending if terminal else b"")
    path = put(tmp_path, "module.py", data)
    document = source_document(tmp_path, "module.py")
    assert document == {
        "path": "module.py",
        "source_sha256": digest(data),
        "text": data.decode(),
        "utf8_bytes": len(data),
        "newline": ending.decode(),
        "terminal_newline": terminal,
    }
    converted = normalize_anchored_edits(
        proposal([edit("module.py", data, ["    result = 1"], ["    result = 2"])]),
        tmp_path,
        allowed_source_paths={"module.py"},
    )
    assert path.read_bytes() == data
    assert converted.proposal["diff"].startswith("--- a/module.py\n+++ b/module.py\n@@")
    expected = data.replace(b"result = 1", b"result = 2")
    git_apply(tmp_path, converted.proposal["diff"])
    assert path.read_bytes() == expected
    ast.parse(path.read_bytes())
    item = converted.metadata["files"][0]
    assert item["source_sha256"] == digest(data)
    assert item["expected_sha256"] == digest(path.read_bytes())
    assert item["expected_bytes"] == len(expected)
    assert item["edits"] == [
        {
            "edit_index": 0,
            "start_line": 2,
            "end_line": 2,
            "start_byte": len(rows[0]) + len(ending),
            "end_byte": len(rows[0]) + len(rows[1]) + 2 * len(ending),
        }
    ]


def test_no_eof_newline_markers_are_standard_and_not_added_to_source(tmp_path):
    data = b"x = 1"
    path = put(tmp_path, "module.py", data)
    result = normalize_anchored_edits(
        proposal([edit("module.py", data, ["x = 1"], ["x = 2"])]), tmp_path
    )
    assert result.proposal["diff"].count("\\ No newline at end of file") == 2
    git_apply(tmp_path, result.proposal["diff"])
    assert path.read_bytes() == b"x = 2"


def test_multiple_edits_use_original_spans_not_sequential_rematching(tmp_path):
    data = b"a = 1\nb = 2\nc = 3\nd = 4\n"
    path = put(tmp_path, "module.py", data)
    result = normalize_anchored_edits(
        proposal(
            [
                edit("module.py", data, ["c = 3"], ["c = 30", "e = 5"]),
                edit("module.py", data, ["a = 1", "b = 2"], ["a = 10"]),
            ]
        ),
        tmp_path,
    )
    git_apply(tmp_path, result.proposal["diff"])
    assert path.read_bytes() == b"a = 10\nc = 30\ne = 5\nd = 4\n"
    assert result.metadata["files"][0]["expected_sha256"] == digest(path.read_bytes())
    assert [row["edit_index"] for row in result.metadata["files"][0]["edits"]] == [1, 0]


def test_insertion_retains_anchor_deletion_and_three_context_lines(tmp_path):
    data = b"a = 1\nb = 2\nc = 3\nd = 4\ne = 5\nf = 6\ng = 7\nh = 8\n"
    path = put(tmp_path, "module.py", data)
    result = normalize_anchored_edits(
        proposal([edit("module.py", data, ["d = 4", "e = 5"], ["d = 4", "inserted = 9"])]),
        tmp_path,
    )
    assert result.metadata["context_lines"] == 3
    assert "@@ -2,7 +2,7 @@" in result.proposal["diff"]
    git_apply(tmp_path, result.proposal["diff"])
    assert path.read_bytes() == data.replace(b"e = 5", b"inserted = 9")


def test_unicode_and_literal_escapes_are_never_normalized(tmp_path):
    data = 'name = "中国"\nvalue = "\\\\n"\n'.encode()
    path = put(tmp_path, "module.py", data)
    result = normalize_anchored_edits(
        proposal([edit("module.py", data, ['name = "中国"'], ['name = "日本"'])]), tmp_path
    )
    git_apply(tmp_path, result.proposal["diff"])
    assert path.read_bytes() == data.replace("中国".encode(), "日本".encode())


def test_unicode_line_separator_is_source_character_not_diff_boundary(tmp_path):
    data = 'text = "first\\u2028last"\n'.replace("\\u2028", "\u2028").encode()
    path = put(tmp_path, "module.py", data)
    result = normalize_anchored_edits(
        proposal([edit("module.py", data, [data.decode().rstrip("\n")], ['text = "changed"'])]),
        tmp_path,
    )
    git_apply(tmp_path, result.proposal["diff"])
    assert path.read_bytes() == b'text = "changed"\n'


def test_config_only_keeps_original_fields_and_never_reads_root(tmp_path):
    result = normalize_anchored_edits(
        proposal(
            env_changes={"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
            cli_changes=["--batch=1"],
            notes=["configuration only"],
        ),
        tmp_path / "not-created",
    )
    assert result.proposal == {
        "diff": "",
        "env_changes": {"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
        "cli_changes": ["--batch=1"],
        "notes": ["configuration only"],
    }
    assert result.metadata["files"] == [] and result.metadata["file_count"] == 0
    assert result.metadata["diff_sha256"] == digest(b"")


@pytest.mark.parametrize(
    "old,new",
    [
        ([], ["new"]),
        (["same"], ["same"]),
        (["has\nnewline"], ["new"]),
        (["old"], ["has\rCR"]),
        (["old"], ["has\r\nCRLF"]),
        (["old"], ["0001: new"]),
        (["0001: old"], ["new"]),
        (["old"], ["\x00"]),
        (["old"], ["\ud800"]),
        ("old", ["new"]),
        (["old"], "new"),
        ([1], ["new"]),
    ],
)
def test_wire_rejects_invalid_blocks_before_source_access(tmp_path, old, new):
    with pytest.raises(ValidationError):
        normalize_anchored_edits(
            proposal([edit("module.py", b"", old, new)]), tmp_path / "nonexistent"
        )


@pytest.mark.parametrize(
    "path",
    [
        "../module.py",
        "/tmp/module.py",
        "a//b.py",
        "./module.py",
        ".env",
        ".git/x.py",
        "sub/.env/x.py",
        "token.json",
        "a b.py",
        "x.sh",
    ],
)
def test_original_path_policy_rejects_unsafe_targets(tmp_path, path):
    with pytest.raises(ValidationError):
        normalize_anchored_edits(proposal([edit(path, b"x", ["x"], ["y"])]), tmp_path)


@pytest.mark.parametrize("hashed", ["A" * 64, "g" * 64, "0" * 63, True])
def test_hash_wire_is_strict(hashed):
    value = edit("module.py", b"x\n", ["x"], ["y"])
    value["source_sha256"] = hashed
    with pytest.raises(ValidationError):
        SourceAnchoredProposal(**proposal([value]))


@pytest.mark.parametrize(
    "data,old,reason",
    [
        (b"  old\n", ["old"], "exactly match"),
        (b"old\nold\n", ["old"], "not unique"),
        (b"x\nx\nx\n", ["x", "x"], "not unique"),
        (b"prefix old suffix\n", ["old"], "exactly match"),
        (b"value = '\\\\n'\n", ["value = '\n'"], "line items"),
    ],
)
def test_no_whitespace_substring_unescape_or_ambiguous_guess(tmp_path, data, old, reason):
    path = put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match=reason):
        normalize_anchored_edits(proposal([edit("module.py", data, old, ["new"])]), tmp_path)
    assert path.read_bytes() == data


def test_stale_hash_and_unsupplied_source_rejected(tmp_path):
    data = b"x = 1\n"
    path = put(tmp_path, "module.py", data)
    value = proposal([edit("module.py", data, ["x = 1"], ["x = 2"])])
    with pytest.raises(ValueError, match="not included"):
        normalize_anchored_edits(value, tmp_path, allowed_source_paths=set())
    path.write_bytes(b"x = 1\n# changed\n")
    with pytest.raises(ValueError, match="stale"):
        normalize_anchored_edits(value, tmp_path)


@pytest.mark.parametrize("second", [(["a"], ["x"]), (["a", "b"], ["x"])])
def test_duplicates_and_overlapping_original_ranges_rejected(tmp_path, second):
    data = b"a\nb\nc\n"
    path = put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match="duplicate or overlapping"):
        normalize_anchored_edits(
            proposal(
                [
                    edit("module.py", data, ["a"], ["new"]),
                    edit("module.py", data, *second),
                ]
            ),
            tmp_path,
        )
    assert path.read_bytes() == data


def test_combined_replacement_cannot_cancel_to_no_change(tmp_path):
    data = b"a\nb\n"
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match="combined edits make no change"):
        normalize_anchored_edits(
            proposal(
                [
                    edit("module.py", data, ["a"], []),
                    edit("module.py", data, ["b"], ["a", "b"]),
                ]
            ),
            tmp_path,
        )


@pytest.mark.parametrize("data", [b"a\r\nb\n", b"a\rb", b"\xff\n", b"a\x00b\n"])
def test_unsupported_original_bytes_rejected_without_guess(tmp_path, data):
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError):
        source_document(tmp_path, "module.py")
    with pytest.raises(ValueError):
        normalize_anchored_edits(proposal([edit("module.py", data, ["a"], ["new"])]), tmp_path)


def test_existing_file_only_and_symlink_ancestors_rejected(tmp_path):
    data = b"x\n"
    outside = put(tmp_path, "outside.py", data)
    (tmp_path / "link.py").symlink_to(outside)
    directory = tmp_path / "directory"
    directory.mkdir()
    (tmp_path / "alias").symlink_to(directory, target_is_directory=True)
    for path in ("missing.py", "link.py", "alias/module.py"):
        with pytest.raises(ValueError):
            normalize_anchored_edits(proposal([edit(path, data, ["x"], ["y"])]), tmp_path)


def test_nonregular_source_and_source_size_rejected(tmp_path):
    (tmp_path / "directory.py").mkdir()
    os.mkfifo(tmp_path / "fifo.py")
    put(tmp_path, "large.py", b"x" * (MAX_FILE_BYTES + 1))
    for path in ("directory.py", "fifo.py", "large.py"):
        with pytest.raises(ValueError):
            source_document(tmp_path, path)


def test_20_files_limit_and_deterministic_file_order(tmp_path):
    data = b"x = 1\n"
    values = []
    for number in range(20):
        name = f"files/a{number:02}.py"
        put(tmp_path, name, data)
        values.append(edit(name, data, ["x = 1"], ["x = 2"]))
    result = normalize_anchored_edits(proposal(list(reversed(values))), tmp_path)
    assert result.metadata["file_count"] == 20
    assert [item["path"] for item in result.metadata["files"]] == sorted(v["path"] for v in values)
    git_apply(tmp_path, result.proposal["diff"])
    assert all((tmp_path / value["path"]).read_bytes() == b"x = 2\n" for value in values)
    with pytest.raises(ValidationError, match="twenty"):
        SourceAnchoredProposal(**proposal([*values, edit("more.py", data, ["x"], ["y"])]))


def test_edits_and_aggregate_character_byte_limits():
    item = edit("module.py", b"x\n", ["x"], ["y"])
    with pytest.raises(ValidationError):
        SourceAnchoredProposal(**proposal([item] * (MAX_EDITS + 1)))
    for old, new in [(["a" * 256000], ["b" * 256000]), (["你" * 90000], ["新" * 90000])]:
        with pytest.raises(ValidationError, match="512000"):
            SourceAnchoredProposal(**proposal([edit("module.py", b"", old, new)]))


def test_generated_diff_limit_counts_context_headers_and_utf8(tmp_path):
    data = b"x" * 255990 + b"\n"
    put(tmp_path, "module.py", data)
    value = proposal([edit("module.py", data, ["x" * 255990], ["y" * 255990])])
    SourceAnchoredProposal(**value)
    with pytest.raises(ValueError, match="generated diff"):
        normalize_anchored_edits(value, tmp_path)


@pytest.mark.parametrize(
    "extra",
    [
        {"diff": ""},
        {"diff_lines": []},
        {"cli_changes": [True]},
        {"notes": ["x"] * 21},
        {"cli_changes": ["x"] * 61},
        {"env_changes": {"x": True}},
    ],
)
def test_original_config_schema_limits_and_no_legacy_guess(extra):
    with pytest.raises(ValidationError):
        SourceAnchoredProposal(**proposal(**extra))


def test_constructed_or_mutated_model_cannot_skip_validation(tmp_path):
    value = SourceAnchoredProposal(**proposal())
    value.edits = [{"path": "../bad.py"}]
    with (
        pytest.warns(UserWarning, match="Pydantic serializer warnings"),
        pytest.raises(ValidationError),
    ):
        normalize_anchored_edits(value, tmp_path)


@pytest.mark.parametrize("data,new", [(b"x\n", []), (b"x", ["x", ""])])
def test_terminal_newline_contract_rejects_unrepresentable_result(tmp_path, data, new):
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match="terminal newline"):
        normalize_anchored_edits(proposal([edit("module.py", data, ["x"], new)]), tmp_path)
