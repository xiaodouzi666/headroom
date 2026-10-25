"""JSON indentation normalization preserves tokens and keeps parser admission limits."""

import json

import pytest

from headroom.acceptance import snapshot_compact as compact


@pytest.mark.parametrize(
    "value",
    [
        {"text": ' spaces  \t \\ " \n 汉字', "values": [1, -0.25, 1e-8, None, True, {}]},
        [[], {}, "  leading spaces", "\t", "\\n", "line\u2028separator"],
    ],
)
def test_normalization_preserves_json_values_and_original(tmp_path, value):
    source, target = tmp_path / "raw.json", tmp_path / "compact.json"
    raw = json.dumps(value, indent=12, ensure_ascii=False).encode()
    source.write_bytes(raw)
    record = compact.normalize(source, target)
    assert source.read_bytes() == raw
    assert target.stat().st_size < source.stat().st_size
    assert compact.verified_json(record) == value
    assert record["parse_limit_bytes"] == 512 * 1024 * 1024


@pytest.mark.parametrize(
    "raw",
    [
        b"1\n 2",
        b"tru\n e",
        b'{"x": "bad\n  string"}',
        b"[1,\n  NaN]",
        b'{"x":1}\n {"y":2}',
    ],
)
def test_invalid_json_cannot_become_valid_by_removing_indentation(tmp_path, raw):
    source, target = tmp_path / "raw.json", tmp_path / "compact.json"
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        compact.normalize(source, target)
    assert not target.exists() and source.read_bytes() == raw


def test_existing_artifacts_are_not_overwritten(tmp_path):
    source, target = tmp_path / "raw.json", tmp_path / "compact.json"
    source.write_text("{}")
    target.write_text("KEEP")
    with pytest.raises(FileExistsError):
        compact.normalize(source, target)
    assert target.read_text() == "KEEP"


@pytest.mark.parametrize("which", ["original_path", "normalized_path"])
def test_proof_is_recomputed_instead_of_trusting_a_boolean(tmp_path, which):
    source, target = tmp_path / "raw.json", tmp_path / "compact.json"
    source.write_text('{\n    "x": 1\n}')
    record = compact.normalize(source, target)
    path = source if which == "original_path" else target
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        compact.verified_json(record)


def test_output_limit_is_not_widened(tmp_path, monkeypatch):
    source, target = tmp_path / "raw.json", tmp_path / "compact.json"
    source.write_text('["' + "a" * 100 + '"]')
    monkeypatch.setattr(compact, "MAX_OUTPUT", 40)
    with pytest.raises(ValueError, match="parse limit"):
        compact.normalize(source, target)
    assert not target.exists()
