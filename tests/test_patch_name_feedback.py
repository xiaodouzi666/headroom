"""Synthetic offline feedback checks; no API, GPU or production database access."""

import copy
import hashlib
import json
import os
import socket
from pathlib import Path

import pytest
from test_patch import mock_router, proposal

from headroom import patch
from headroom import patch_feedback as feedback


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No live network in synthetic name-feedback fixtures")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def fixture(root, source="value = missing\n", name="train.py", detail=None):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source)
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    return {
        "candidate_root": root,
        "changed_files": (name,),
        "reason": "NEW_UNDEFINED_NAME",
        "detail": detail or name + ":1:9 F821 Undefined name `missing`",
        "application_check": {
            "protocol": "headroom.exact_application.v1",
            "verified": True,
            "files": [
                {
                    "path": name,
                    "before_sha256": "1" * 64,
                    "expected_sha256": sha,
                    "candidate_sha256": sha,
                    "bytes": len(raw),
                    "hunks": 1,
                }
            ],
        },
    }


def unavailable(value):
    assert value["status"] == "unavailable"
    assert value["diagnostics"] == []


def test_bound_actual_candidate_is_read_only_and_never_executed(tmp_path):
    source = 'raise RuntimeError("must never run")\nvalue = missing\nlast = 3\n'
    kwargs = fixture(tmp_path, source, detail="train.py:2:9 F821 Undefined name `missing`")
    original = (tmp_path / "train.py").read_bytes()
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "complete"
    assert result["coordinate_space"] == "rejected_candidate"
    assert result["original_source_span_ids"] is False
    assert result["omitted_diagnostic_count"] == 0
    item = result["diagnostics"][0]
    assert item["candidate_sha256"] == hashlib.sha256(original).hexdigest()
    assert item["line"] == 2 and item["column"] == 9 and item["name"] == "missing"
    assert [x["line"] for x in item["excerpt"]] == [1, 2, 3]
    assert item["excerpt"][1]["text"] == "value = missing"
    assert (tmp_path / "train.py").read_bytes() == original


def test_unicode_character_columns_agree_with_real_ruff(tmp_path):
    from headroom.patch_names import _lint

    source = 'label = "界"; value = missing\n'
    records = _lint(source, "train.py")
    assert len(records) == 1
    r = records[0]
    detail = f"train.py:{r['row']}:{r['column']} F821 {r['message']}"
    kwargs = fixture(tmp_path, source, detail=detail)
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "complete"
    assert result["diagnostics"][0]["column"] == source.index("missing") + 1


@pytest.mark.parametrize(
    "change",
    [
        lambda k: k.update(reason="COMPILE_FAILED"),
        lambda k: k.update(reason=None),
    ],
)
def test_other_rejection_never_reads_candidate(tmp_path, monkeypatch, change):
    kwargs = fixture(tmp_path)
    change(kwargs)
    monkeypatch.setattr(feedback, "_read_bytes", lambda *_: pytest.fail("must not read"))
    assert feedback.rejected_name_feedback(**kwargs)["status"] == "not_applicable"


@pytest.mark.parametrize(
    "change",
    [
        lambda k: k.update(candidate_root=None),
        lambda k: k.update(detail=None),
        lambda k: k.update(detail=""),
        lambda k: k.update(detail="x" * 2001),
        lambda k: k.update(detail="界" * 700),
        lambda k: k.update(detail="train.py:1:9 F821 Undefined name `missing"),
        lambda k: k.update(detail="train.py:1:9 F822 Undefined name `missing`"),
        lambda k: k.update(detail="train.py:0:9 F821 Undefined name `missing`"),
        lambda k: k.update(detail="train.py:1:9 F821 Undefined name `not-a-name`"),
        lambda k: k.update(application_check=None),
        lambda k: k["application_check"].update(verified=False),
        lambda k: k["application_check"].update(verified=1),
        lambda k: k["application_check"].update(protocol="foreign"),
        lambda k: k["application_check"].update(files=[]),
        lambda k: k["application_check"]["files"].append(
            copy.deepcopy(k["application_check"]["files"][0])
        ),
        lambda k: k["application_check"]["files"][0].update(expected_sha256="A" * 64),
        lambda k: k["application_check"]["files"][0].update(candidate_sha256="f" * 64),
        lambda k: k["application_check"]["files"][0].update(bytes=True),
        lambda k: k["application_check"]["files"][0].update(bytes=1),
        lambda k: k.update(changed_files=("other.py",)),
        lambda k: k.update(changed_files={"train.py"}),
    ],
)
def test_missing_invalid_or_mismatched_binding_rejected(tmp_path, change):
    kwargs = fixture(tmp_path)
    change(kwargs)
    unavailable(feedback.rejected_name_feedback(**kwargs))


@pytest.mark.parametrize(
    "detail",
    [
        "train.py:2:9 F821 Undefined name `missing`",
        "train.py:1:8 F821 Undefined name `missing`",
        "train.py:1:9 F821 Undefined name `other`",
        "train.py:1:1 F821 Undefined name `value`",
    ],
)
def test_wrong_or_nonload_candidate_location_rejected(tmp_path, detail):
    unavailable(feedback.rejected_name_feedback(**fixture(tmp_path, detail=detail)))


def test_changed_candidate_rejected_even_if_location_still_matches(tmp_path):
    kwargs = fixture(tmp_path)
    (tmp_path / "train.py").write_text("value = missing\n# changed after verification\n")
    unavailable(feedback.rejected_name_feedback(**kwargs))


@pytest.mark.parametrize("case", ["missing", "invalid_utf8", "oversized", "syntax_invalid"])
def test_unreadable_or_unparseable_candidate_rejected(tmp_path, case):
    kwargs = fixture(tmp_path)
    p = tmp_path / "train.py"
    if case == "missing":
        p.unlink()
    else:
        data = {
            "invalid_utf8": b"value = missing\n\xff",
            "oversized": b"#" * (2 * 1024 * 1024 + 1),
            "syntax_invalid": b"value = missing\n(\n",
        }[case]
        p.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        kwargs["application_check"]["files"][0].update(
            candidate_sha256=sha, expected_sha256=sha, bytes=len(data)
        )
    unavailable(feedback.rejected_name_feedback(**kwargs))


@pytest.mark.parametrize("name", ["../outside.py", "/tmp/outside.py", ".env.py", "x/../train.py"])
def test_protected_or_traversal_path_rejected(tmp_path, name):
    kwargs = fixture(tmp_path)
    kwargs.update(changed_files=(name,), detail=name + ":1:9 F821 Undefined name `missing`")
    kwargs["application_check"]["files"][0]["path"] = name
    unavailable(feedback.rejected_name_feedback(**kwargs))


@pytest.mark.parametrize("kind", ["leaf_symlink", "directory_symlink", "root_symlink", "fifo"])
def test_nonregular_or_symlink_candidate_rejected(tmp_path, kind):
    root = tmp_path / "candidate"
    root.mkdir()
    kwargs = fixture(root)
    if kind == "leaf_symlink":
        outside = tmp_path / "outside.py"
        outside.write_bytes((root / "train.py").read_bytes())
        (root / "train.py").unlink()
        (root / "train.py").symlink_to(outside)
    elif kind == "directory_symlink":
        (root / "sub").symlink_to(root, target_is_directory=True)
        kwargs.update(
            changed_files=("sub/train.py",), detail="sub/train.py:1:9 F821 Undefined name `missing`"
        )
        kwargs["application_check"]["files"][0]["path"] = "sub/train.py"
    elif kind == "root_symlink":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        kwargs["candidate_root"] = link
    else:
        (root / "train.py").unlink()
        os.mkfifo(root / "train.py")
    unavailable(feedback.rejected_name_feedback(**kwargs))


def test_credentials_anywhere_withhold_name_and_excerpt(tmp_path):
    secret = "OFFLINE_FAKE_SECRET_ONLY"
    kwargs = fixture(tmp_path, f'value = missing\n# distant\napi_key = "{secret}"\n')
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "partial"
    assert result["diagnostics"][0]["status"] == "withheld"
    serialized = json.dumps(result)
    assert secret not in serialized and "missing" not in serialized and "excerpt" not in serialized


def test_wire_line_and_diagnostic_bounds(tmp_path):
    source = "\n".join(f"value{i} = missing{i}  # " + "界" * 500 for i in range(20)) + "\n"
    details = "\n".join(
        f"train.py:{i + 1}:{len('value' + str(i) + ' = ') + 1} F821 Undefined name `missing{i}`"
        for i in range(20)
    )
    result = feedback.rejected_name_feedback(**fixture(tmp_path, source, detail=details))
    assert result["status"] == "partial"
    assert 0 < len(result["diagnostics"]) <= feedback.MAX_NAME_DIAGNOSTICS
    assert result["omitted_diagnostic_count"] > 0
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= feedback.MAX_NAME_FEEDBACK_BYTES
    assert all(len(x["excerpt"]) <= 3 for x in result["diagnostics"])
    assert any(y["truncated"] for x in result["diagnostics"] for y in x["excerpt"])


def test_maximum_distinct_files_is_bounded(tmp_path):
    kwargs = fixture(tmp_path)
    names, details, bindings = [], [], []
    for i in range(5):
        value = fixture(tmp_path, name=f"train{i}.py")
        names.append(value["changed_files"][0])
        details.append(value["detail"])
        bindings.extend(value["application_check"]["files"])
    kwargs.update(changed_files=tuple(names), detail="\n".join(details))
    kwargs["application_check"]["files"] = bindings
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "partial"
    assert len(result["diagnostics"]) == 3
    assert result["omitted_diagnostic_count"] == 2


def test_true_f821_reaches_excerpt_in_real_patchengine_flow(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    before, bad, good = "value = 1\n", "value = missing\n", "value = 2\n"
    (source / "train.py").write_text(before)
    calls = []
    router = mock_router([proposal(before, bad), proposal(before, good)], calls)
    try:
        result = patch.PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "synthetic-undefined-name"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert result.applied and len(calls) == 2 and len(result.attempts) == 2
    assert result.attempts[0].reason == "NEW_UNDEFINED_NAME"
    assert result.attempts[0].application_check["verified"] is True
    repair = json.loads(calls[1]["messages"][-1]["content"])["repair"]
    item = repair["candidate_names"]["diagnostics"][0]
    assert repair["candidate_names"]["status"] == "complete"
    assert item["excerpt"][0]["text"] == bad.rstrip()
    assert item["candidate_sha256"] == hashlib.sha256(bad.encode()).hexdigest()
    assert all(call["max_tokens"] == 4000 for call in calls)
    assert (source / "train.py").read_text() == before
    assert (Path(result.candidate_dir) / "train.py").read_text() == good
    assert result.runtime_verified is False


def test_name_feedback_exception_preserves_gate_and_request_limit(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise RuntimeError("private diagnostic detail")

    monkeypatch.setattr(patch, "rejected_name_feedback", fail)
    source = tmp_path / "source"
    source.mkdir()
    before, bad = "value = 1\n", "value = missing\n"
    (source / "train.py").write_text(before)
    calls = []
    router = mock_router([proposal(before, bad)], calls)
    try:
        result = patch.PatchEngine(router, max_repairs=1).generate_and_apply(
            source, {"fix_id": "synthetic-undefined-name"}, work_root=tmp_path / "work"
        )
    finally:
        router.client.close()
    assert not result.applied and len(calls) == 2 and len(result.attempts) == 2
    assert all(a.reason == "NEW_UNDEFINED_NAME" for a in result.attempts)
    content = calls[1]["messages"][-1]["content"]
    assert json.loads(content)["repair"]["candidate_names"]["status"] == "unavailable"
    assert "private diagnostic detail" not in content
    assert (source / "train.py").read_text() == before


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085", "\v", "\f"])
def test_unicode_separators_do_not_create_candidate_physical_lines(tmp_path, separator):
    from headroom.patch_names import _lint

    source = "# prefix" + separator + "suffix\nmissing\n"
    records = _lint(source, "train.py")
    assert len(records) == 1 and records[0]["row"] == 2
    r = records[0]
    kwargs = fixture(
        tmp_path, source, detail=f"train.py:{r['row']}:{r['column']} F821 {r['message']}"
    )
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "complete"
    item = result["diagnostics"][0]
    assert item["line"] == 2 and item["column"] == 1
    assert item["excerpt"][0]["text"] == "# prefix" + separator + "suffix"
    assert item["excerpt"][1] == {"line": 2, "text": "missing", "truncated": False}


@pytest.mark.parametrize("newline", ["\r\n", "\r"])
def test_python_universal_physical_newlines_match_ruff(tmp_path, newline):
    from headroom.patch_names import _lint

    source = "# first" + newline + "value = missing" + newline
    r = _lint(source, "train.py")[0]
    kwargs = fixture(
        tmp_path, source, detail=f"train.py:{r['row']}:{r['column']} F821 {r['message']}"
    )
    result = feedback.rejected_name_feedback(**kwargs)
    assert result["status"] == "complete"
    assert result["diagnostics"][0]["excerpt"][1]["text"] == "value = missing"
    assert result["diagnostics"][0]["line"] == 2
