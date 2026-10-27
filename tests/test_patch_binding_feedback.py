"""Host binding explanation fixtures; no target execution or live service."""

import ast
import copy
import hashlib
import json
import socket
from dataclasses import asdict

import pytest

from headroom.patch_binding_feedback import (
    MAX_BINDING_FEEDBACK_BYTES,
    rejected_model_binding_feedback,
)
from headroom.verify.policy import PolicyIssue, _bindings, check_source_changes

OLD = "def emit(**kwargs): pass\nlength = 8\nemit(sequence_length=length)\n"
NEW = OLD + "emit(sequence_length=length)\n"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("No network in isolated binding feedback tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


def fixture(tmp_path, old=OLD, new=NEW):
    source, candidate = tmp_path / "source", tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    (source / "train.py").write_bytes(old.encode())
    (candidate / "train.py").write_bytes(new.encode())
    receipt = {
        "protocol": "headroom.exact_application.v1",
        "verified": True,
        "files": [
            {
                "path": "train.py",
                "before_sha256": hashlib.sha256(old.encode()).hexdigest(),
                "expected_sha256": hashlib.sha256(new.encode()).hexdigest(),
                "candidate_sha256": hashlib.sha256(new.encode()).hexdigest(),
                "bytes": len(new.encode()),
            }
        ],
    }
    report = check_source_changes({"train.py": old}, {"train.py": new})
    return source, candidate, receipt, report


def explain(parts, **extra):
    source, candidate, receipt, report = parts
    args = {
        "reason": "MODEL_CHANGED",
        "issues": report.issues,
        "application_check": receipt,
    } | extra
    return rejected_model_binding_feedback(source, candidate, ("train.py",), **args)


def test_duplicate_keyword_explains_exact_guard_input_without_accepting_it(tmp_path):
    parts = fixture(tmp_path)
    report_before = asdict(parts[3])
    value = explain(parts)
    assert value["status"] == "complete"
    assert value["gate_changed"] is False and value["model_equivalence_proven"] is False
    item = value["diagnostics"][0]
    assert item["key"] == "sequence_length"
    assert item["before"]["binding_count"] == 1 and item["after"]["binding_count"] == 2
    assert [x["origin"]["line"] for x in item["after"]["entries"]] == [3, 4]
    assert all(x["origin"]["enclosing_call"] == "emit" for x in item["after"]["entries"])
    assert all(x["origin"]["kind"] == "keyword_argument" for x in item["after"]["entries"])
    assert item["after"]["entries"][1]["origin"]["excerpt"] == "emit(sequence_length=length)"
    assert asdict(parts[3]) == report_before
    assert not parts[3].allowed
    assert (parts[1] / "train.py").read_text() == NEW


def test_real_constructor_growth_remains_rejected_and_located(tmp_path):
    old, new = "x = nn.Linear(4, 8)\n", "x = nn.Linear(4, 16)\n"
    parts = fixture(tmp_path, old, new)
    result = explain(parts)
    assert not parts[3].allowed and parts[3].issues[0].code == "MODEL_CHANGED"
    item = result["diagnostics"][0]
    assert item["key"] == "constructor:nn.Linear:0:1"
    assert item["before"]["entries"][0]["resolved_number"] == 8.0
    assert item["after"]["entries"][0]["resolved_number"] == 16.0
    origin = item["after"]["entries"][0]["origin"]
    assert origin["kind"] == "constructor_argument" and origin["column"] == 18
    assert origin["enclosing_call"] == "nn.Linear"


@pytest.mark.parametrize(
    "source",
    [
        "width = 8\n",
        "width, depth = (8, 2) if tiny else (16, 4)\n",
        "x = nn.Linear(8, 16)\n",
        "configure(width=8)\n",
        "config = {'width': 8}\n",
        "parser.add_argument('--width', default=8)\n",
        "for step in range(20): pass\n",
    ],
)
def test_optional_origins_preserve_binding_values_and_real_nodes(source):
    tree = ast.parse(source)
    original = ast.dump(tree, include_attributes=True)
    origins = {}
    assert _bindings(tree) == _bindings(tree, origins=origins)
    assert ast.dump(tree, include_attributes=True) == original
    assert origins
    assert all(
        origin is None or origin["line"] == 1 for entries in origins.values() for origin in entries
    )
    assert all(len(origins[key]) == len(value) for key, value in _bindings(tree).items())


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\u0085", "\v", "\f"])
def test_physical_lines_and_unicode_columns_are_real(tmp_path, newline, separator):
    prefix = f"# {separator}same physical line{newline}"
    old = prefix + f"width = 8{newline}"
    new = prefix + f"标签 = 1; width = 16{newline}"
    parts = fixture(tmp_path, old, new)
    item = explain(parts)["diagnostics"][0]
    origin = item["after"]["entries"][0]["origin"]
    assert origin["line"] == 2 and origin["column"] == 9
    assert origin["excerpt"] == "标签 = 1; width = 16"


@pytest.mark.parametrize("field", ["before_sha256", "expected_sha256", "candidate_sha256", "bytes"])
def test_exact_source_and_candidate_receipt_mismatch_withholds_all(tmp_path, field):
    parts = fixture(tmp_path)
    receipt = copy.deepcopy(parts[2])
    receipt["files"][0][field] = 999 if field == "bytes" else "0" * 64
    assert explain(parts, application_check=receipt)["diagnostics"] == []


@pytest.mark.parametrize("side", [0, 1])
def test_changed_source_bytes_or_symlink_cannot_supply_locations(tmp_path, side):
    parts = fixture(tmp_path)
    file = parts[side] / "train.py"
    outside = tmp_path / "elsewhere.py"
    file.rename(outside)
    file.symlink_to(outside)
    assert explain(parts)["diagnostics"] == []


@pytest.mark.parametrize("reason", [None, "MODEL_SHRUNK", "MODEL_CHANGED ", "SYNTAX_INVALID"])
def test_other_reasons_are_not_applicable(tmp_path, reason):
    assert explain(fixture(tmp_path), reason=reason)["status"] == "not_applicable"


@pytest.mark.parametrize(
    "issues",
    [
        (),
        (PolicyIssue("MODEL_CHANGED", "different guard message", "train.py"),),
        (PolicyIssue("MODEL_CHANGED", "Model shape must remain unchanged.", "other.py"),),
        (
            {
                "code": "MODEL_CHANGED",
                "message": "Model shape must remain unchanged.",
                "path": "train.py",
            },
        ),
    ],
)
def test_missing_or_unmatched_host_issue_is_not_invented(tmp_path, issues):
    value = explain(fixture(tmp_path), issues=issues)
    assert value["diagnostics"] == [] and value["status"] == "unavailable"


def test_unchanged_binding_does_not_justify_fabricated_host_issue(tmp_path):
    parts = fixture(tmp_path, OLD, OLD)
    issues = (PolicyIssue("MODEL_CHANGED", "Model shape must remain unchanged.", "train.py"),)
    assert explain(parts, issues=issues)["diagnostics"] == []


@pytest.mark.parametrize("side", [0, 1])
def test_credentials_in_either_version_withhold_binding_expressions(tmp_path, side):
    old, new = OLD, NEW
    secret = 'api_key = "OFFLINE_FAKE_SECRET_ONLY"\n'
    old = secret + old if side == 0 else old
    new = secret + new if side == 1 else new
    value = explain(fixture(tmp_path, old, new))
    assert value["status"] == "partial"
    assert value["diagnostics"][0]["status"] == "withheld"
    assert "OFFLINE_FAKE_SECRET_ONLY" not in json.dumps(value)
    assert "expression_ast" not in json.dumps(value)


def test_missing_origin_stays_unknown_not_a_fabricated_line(tmp_path, monkeypatch):
    import headroom.patch_binding_feedback as feedback

    original = feedback._bindings

    def missing_origins(tree, *, origins):
        return original(tree)

    monkeypatch.setattr(feedback, "_bindings", missing_origins)
    value = explain(fixture(tmp_path))
    assert value["status"] == "partial"
    assert value["diagnostics"][0]["before"]["entries"][0]["origin"] is None


def test_feedback_size_and_repeated_entries_are_bounded(tmp_path):
    old = "\n".join(f"f(sequence_length=x{i})" for i in range(80)) + "\n"
    new = old + "f(sequence_length=another)\n"
    value = explain(fixture(tmp_path, old, new))
    item = value["diagnostics"][0]
    assert value["status"] == "partial"
    assert item["before"]["binding_count"] == 80
    assert len(item["before"]["entries"]) == 3
    assert item["before"]["entries_omitted"] == 77
    assert len(json.dumps(value, ensure_ascii=False).encode()) <= MAX_BINDING_FEEDBACK_BYTES


def test_patch_repair_payload_explains_rejection_without_relaxing_gate(tmp_path):
    from test_patch import mock_router, proposal

    from headroom.patch import PatchEngine

    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text(OLD)
    calls = []
    router = mock_router([proposal(OLD, NEW)] * 4, calls)
    try:
        result = PatchEngine(router).generate_and_apply(
            source,
            {"fix_id": "generic", "type": "code", "title": "Fixture", "description": "Fixture"},
            work_root=tmp_path / "patches",
        )
    finally:
        router.client.close()
    assert not result.applied and result.reason == "MODEL_CHANGED"
    assert len(calls) == 4
    repair = json.loads(calls[1]["messages"][-1]["content"])["repair"]
    assert repair["reason"] == "MODEL_CHANGED"
    detail = repair["candidate_model_bindings"]
    assert detail["diagnostics"][0]["key"] == "sequence_length"
    assert detail["gate_changed"] is False
    assert (source / "train.py").read_text() == OLD


@pytest.mark.parametrize("change", ["protocol", "verified", "duplicate", "non_mapping", "missing"])
def test_invalid_application_receipt_cannot_create_binding_details(tmp_path, change):
    parts = fixture(tmp_path)
    receipt = copy.deepcopy(parts[2])
    if change == "protocol":
        receipt["protocol"] = "other"
    elif change == "verified":
        receipt["verified"] = "true"
    elif change == "duplicate":
        receipt["files"].append(copy.deepcopy(receipt["files"][0]))
    elif change == "non_mapping":
        receipt["files"] = [None]
    else:
        receipt["files"] = []
    value = explain(parts, application_check=receipt)
    assert value["status"] == "unavailable" and value["diagnostics"] == []


def test_many_changed_keys_stop_at_serialized_byte_bound(tmp_path):
    from headroom.verify.policy import MODEL_KEYS

    old = "\n".join(f"{key} = old_value" for key in sorted(MODEL_KEYS)) + "\n"
    new = "\n".join(f"{key} = new_value" for key in sorted(MODEL_KEYS)) + "\n"
    value = explain(fixture(tmp_path, old, new))
    assert value["status"] == "partial" and value["bindings_omitted"] > 0
    assert len(json.dumps(value, ensure_ascii=False).encode()) <= MAX_BINDING_FEEDBACK_BYTES


def test_feedback_exception_preserves_existing_rejection_and_repair_limit(tmp_path, monkeypatch):
    from test_patch import mock_router, proposal

    from headroom.patch import PatchEngine

    def unavailable(*args, **kwargs):
        raise ValueError("synthetic error that must not leak")

    monkeypatch.setattr("headroom.patch.rejected_model_binding_feedback", unavailable)
    source = tmp_path / "source"
    source.mkdir()
    (source / "train.py").write_text(OLD)
    calls = []
    router = mock_router([proposal(OLD, NEW)] * 4, calls)
    try:
        result = PatchEngine(router).generate_and_apply(
            source, {"fix_id": "generic"}, work_root=tmp_path / "patches"
        )
    finally:
        router.client.close()
    assert not result.applied and result.reason == "MODEL_CHANGED" and len(calls) == 4
    repair = json.loads(calls[1]["messages"][-1]["content"])["repair"]
    assert repair["candidate_model_bindings"]["status"] == "unavailable"
    assert "synthetic error" not in json.dumps(repair["candidate_model_bindings"])


def test_unexplained_second_host_issue_does_not_claim_complete_feedback(tmp_path):
    parts = fixture(tmp_path)
    source, candidate, receipt, report = parts
    unchanged = b"width = 8\n"
    for root in (source, candidate):
        (root / "other.py").write_bytes(unchanged)
    sha = hashlib.sha256(unchanged).hexdigest()
    receipt["files"].append(
        {
            "path": "other.py",
            "before_sha256": sha,
            "expected_sha256": sha,
            "candidate_sha256": sha,
            "bytes": len(unchanged),
        }
    )
    issues = report.issues + (
        PolicyIssue("MODEL_CHANGED", "Model shape must remain unchanged.", "other.py"),
    )
    value = rejected_model_binding_feedback(
        source,
        candidate,
        ("train.py", "other.py"),
        reason="MODEL_CHANGED",
        issues=issues,
        application_check=receipt,
    )
    assert value["status"] == "partial" and value["files_without_matching_binding"] == 1
    assert len(value["diagnostics"]) == 1 and value["diagnostics"][0]["path"] == "train.py"
