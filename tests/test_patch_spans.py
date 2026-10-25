"""Offline original-span IDs: real static Git/application, no workload or live service."""

import hashlib
import json

import pytest
from pydantic import ValidationError
from test_patch_edits import git_apply, offline_guard, put  # noqa: F401

from headroom.patch import MAX_SOURCE_CONTEXT_BYTES, _source_context
from headroom.patch_edits import SourceAnchoredProposal, normalize_anchored_edits
from headroom.patch_spans import (
    MAX_EDITS,
    SCHEMA_NAME,
    SourceSpanProposal,
    normalize_span_edits,
    source_span_document,
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def edit(data, start=1, end=1, new=("x = 2",), path="module.py"):
    return {
        "path": path,
        "source_sha256": digest(data),
        "start_id": f"L{start:06d}",
        "end_id": f"L{end:06d}",
        "new_lines": list(new),
    }


def proposal(edits=(), **extra):
    return {"edits": list(edits), "env_changes": {}, "cli_changes": [], "notes": [], **extra}


def test_new_schema_is_distinct_and_does_not_use_unverified_pattern_keyword():
    schema = SourceSpanProposal.model_json_schema()
    assert schema["title"] == SCHEMA_NAME == "source_span_edits_v1"
    fields = schema["$defs"]["SourceSpanEdit"]["properties"]
    assert set(fields) == {"path", "source_sha256", "start_id", "end_id", "new_lines"}
    assert "pattern" not in json.dumps(schema)
    assert SourceAnchoredProposal.model_json_schema()["title"] == "source_anchored_edits_v1"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("terminal", [True, False])
def test_document_and_real_apply_preserve_original_bytes(tmp_path, newline, terminal):
    original = (
        newline.join(["def answer():", "    return 1", "", "marker = '字'"])
        + (newline if terminal else "")
    ).encode()
    expected = original.replace(b"return 1", b"return 2")
    path = put(tmp_path, "module.py", original)
    doc = source_span_document(tmp_path, "module.py")
    assert doc == {
        "path": "module.py",
        "source_sha256": digest(original),
        "lines": [
            {"id": f"L{n:06d}", "text": s}
            for n, s in enumerate(["def answer():", "    return 1", "", "marker = '字'"], 1)
        ],
        "newline": newline,
        "terminal_newline": terminal,
        "utf8_bytes": len(original),
    }
    converted = normalize_span_edits(proposal([edit(original, 2, 2, ["    return 2"])]), tmp_path)
    assert path.read_bytes() == original
    binding = converted.metadata["files"][0]
    assert binding["expected_sha256"] == digest(expected)
    span = binding["edits"][0]
    assert span["start_line"] == span["end_line"] == 2
    assert original[span["start_byte"] : span["end_byte"]] == ("    return 1" + newline).encode()
    assert span["old_sha256"] == digest(original[span["start_byte"] : span["end_byte"]])
    git_apply(tmp_path, converted.proposal["diff"])
    assert path.read_bytes() == expected


def test_repeated_identical_lines_are_selected_by_actual_original_id(tmp_path):
    original = b"first = 1\nsame = 2\nsecond = 3\nsame = 2\n"
    put(tmp_path, "module.py", original)
    converted = normalize_span_edits(proposal([edit(original, 4, 4, ["same = 9"])]), tmp_path)
    git_apply(tmp_path, converted.proposal["diff"])
    assert (tmp_path / "module.py").read_bytes() == b"first = 1\nsame = 2\nsecond = 3\nsame = 9\n"
    put(tmp_path, "module.py", original)
    # Historical text-anchor converter keeps its previous ambiguity rejection.
    with pytest.raises(ValueError, match="not unique"):
        normalize_anchored_edits(
            proposal(
                [
                    {
                        "path": "module.py",
                        "source_sha256": digest(original),
                        "old_lines": ["same = 2"],
                        "new_lines": ["same = 9"],
                    }
                ]
            ),
            tmp_path,
        )


def test_all_ranges_use_original_coordinates_with_insertions_and_deletions(tmp_path):
    original = b"a = 1\nb = 2\nc = 3\nd = 4\n"
    put(tmp_path, "module.py", original)
    changes = [edit(original, 4, 4, []), edit(original, 1, 1, ["a = 1", "added = 5"])]
    converted = normalize_span_edits(proposal(changes), tmp_path)
    git_apply(tmp_path, converted.proposal["diff"])
    assert (tmp_path / "module.py").read_bytes() == b"a = 1\nadded = 5\nb = 2\nc = 3\n"
    assert [e["start_line"] for e in converted.metadata["files"][0]["edits"]] == [1, 4]


@pytest.mark.parametrize(("start", "end"), [(0, 1), (1, 999), (2, 1), (3, 3)])
def test_absent_reversed_or_zero_width_ranges_refuse_without_guess(tmp_path, start, end):
    original = b"x = 1\ny = 2\n"
    put(tmp_path, "module.py", original)
    with pytest.raises(ValueError):
        normalize_span_edits(proposal([edit(original, start, end)]), tmp_path)
    assert (tmp_path / "module.py").read_bytes() == original


@pytest.mark.parametrize("bad", ["1", "", "L1", "L000001:L000002", "L000001\n", 1, None])
def test_noncanonical_id_refused_locally(bad):
    value = edit(b"x = 1\n")
    value["start_id"] = bad
    with pytest.raises(ValidationError):
        SourceSpanProposal(**proposal([value]))


@pytest.mark.parametrize(
    "new",
    [
        ["x=1\ny=2"],
        ["x=1\ry=2"],
        ["L000001: x = 2"],
        ["L000001 | x = 2"],
        ["0001: x = 2"],
        ["\x00"],
        [1],
        "x",
    ],
)
def test_line_separators_display_ids_and_types_never_become_source(new):
    value = edit(b"x = 1\n")
    value["new_lines"] = new
    with pytest.raises(ValidationError):
        SourceSpanProposal(**proposal([value]))


@pytest.mark.parametrize(("left", "right"), [((1, 2), (2, 3)), ((2, 2), (2, 2))])
def test_duplicate_or_overlapping_ranges_rejected(tmp_path, left, right):
    data = b"a\nb\nc\n"
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match="overlapping"):
        normalize_span_edits(proposal([edit(data, *left), edit(data, *right)]), tmp_path)


def test_stale_file_wrong_path_and_unsupplied_file_fail_closed(tmp_path):
    data = b"x = 1\n"
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError, match="stale"):
        normalize_span_edits(proposal([edit(b"x = 0\n")]), tmp_path)
    with pytest.raises(ValueError, match="not included"):
        normalize_span_edits(proposal([edit(data)]), tmp_path, allowed_source_paths=())
    with pytest.raises(ValueError):
        normalize_span_edits(proposal([edit(data, path="../module.py")]), tmp_path)
    with pytest.raises(ValueError):
        normalize_span_edits(proposal([edit(data, path="new.py")]), tmp_path)


def test_symlink_components_and_mixed_line_endings_remain_refused(tmp_path):
    outside = tmp_path / "real"
    outside.mkdir()
    put(outside, "module.py", b"x = 1\n")
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        source_span_document(tmp_path, "linked/module.py")
    put(tmp_path, "mixed.py", b"a\r\nb\n")
    with pytest.raises(ValueError, match="mixed"):
        source_span_document(tmp_path, "mixed.py")


@pytest.mark.parametrize(("data", "new"), [(b"x\n", ["x"]), (b"x\n", []), (b"x", [""])])
def test_no_change_or_unrepresentable_terminal_property_refused(tmp_path, data, new):
    put(tmp_path, "module.py", data)
    with pytest.raises(ValueError):
        normalize_span_edits(proposal([edit(data, new=new)]), tmp_path)


def test_empty_file_has_no_invented_anchor(tmp_path):
    put(tmp_path, "module.py", b"")
    assert source_span_document(tmp_path, "module.py")["lines"] == []
    with pytest.raises(ValueError, match="not supplied"):
        normalize_span_edits(proposal([edit(b"")]), tmp_path)


def test_config_only_never_reads_any_source_and_retains_public_fields(tmp_path):
    value = proposal(
        env_changes={"PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True"},
        cli_changes=["--batch", "2"],
        notes=["not verified"],
    )
    result = normalize_span_edits(value, tmp_path / "missing")
    assert result.proposal == {"diff": "", **{k: v for k, v in value.items() if k != "edits"}}
    assert result.metadata["files"] == [] and result.metadata["schema"] == SCHEMA_NAME


def test_legacy_text_anchor_stays_compatible_but_never_implicitly_converts(tmp_path):
    original = b"x = 1\n"
    put(tmp_path, "module.py", original)
    old = {
        "path": "module.py",
        "source_sha256": digest(original),
        "old_lines": ["x = 1"],
        "new_lines": ["x = 2"],
    }
    assert normalize_anchored_edits(proposal([old]), tmp_path).proposal["diff"]
    with pytest.raises(ValidationError):
        normalize_span_edits(proposal([old]), tmp_path)


def test_bounds_revalidation_and_source_context_count_id_overhead(tmp_path):
    original = b"x = 1\n"
    put(tmp_path, "module.py", original)
    value = SourceSpanProposal(**proposal([edit(original)]))
    value.edits[0].start_id = "L99999999"
    with pytest.raises(ValueError):
        normalize_span_edits(value, tmp_path)
    with pytest.raises(ValidationError):
        SourceSpanProposal(**proposal([edit(original)] * (MAX_EDITS + 1)))
    with pytest.raises(ValidationError):
        SourceSpanProposal(**proposal([edit(original, new=["字" * 180000])]))
    doc = source_span_document(tmp_path, "module.py")
    context = _source_context(tmp_path, ["module.py"])
    assert context["source_bytes"] == len(original)
    assert context["source_document_json_bytes"] == len(json.dumps(doc, allow_nan=False).encode())
    assert context["source_document_json_bytes"] > context["source_bytes"]
    put(tmp_path, "large.py", b"x\n" * (MAX_SOURCE_CONTEXT_BYTES // 3))
    with pytest.raises(ValueError, match="no supported source"):
        _source_context(tmp_path, ["large.py"])


def test_legitimate_escapes_unicode_and_blank_lines_are_exact(tmp_path):
    original = b's = "\\\\n"\nblank = "\\u2028"\n\n'
    put(tmp_path, "module.py", original)
    replacement = ['s = "\\\\t"']
    result = normalize_span_edits(proposal([edit(original, 1, 1, replacement)]), tmp_path)
    git_apply(tmp_path, result.proposal["diff"])
    assert (tmp_path / "module.py").read_bytes() == original.replace(b"\\\\n", b"\\\\t")
