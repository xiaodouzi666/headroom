"""Offline tests for truthful, bounded historical gallery preparation."""

import copy
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from headroom.api.diagnosis_evidence import MAX_CALLS, MAX_RECORD_BYTES, load_initial_diagnosis
from headroom.api.verified import VerifiedCatalog, load_verified

ROOT = Path(__file__).resolve().parents[1]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def catalog_document():
    return json.loads((ROOT / "public-evidence/verified-runs.json").read_text())


def test_real_catalog_preserves_measured_outcomes_and_limits(catalog_document):
    catalog = load_verified(ROOT / "public-evidence")
    assert catalog.publication_status == "prepared_not_enabled"
    assert sum(row.outcome == "target_met" for row in catalog.runs) == 4
    assert sum(row.outcome == "not_solved" for row in catalog.runs) == 2
    by_scenario = {row.scenario_id: row for row in catalog.runs}
    s3 = by_scenario["s3_eval_no_grad_missing"]
    assert (s3.before.peak_allocated_bytes, s3.after.peak_allocated_bytes) == (
        2435717632,
        648419840,
    )
    assert s3.verification.loss_equivalence == "identical"
    assert s3.verification.compared_loss_count == 20
    s4 = by_scenario["s4_loss_accumulation_graph"]
    assert s4.verification.compared_loss_count == 5
    assert s4.after.optimizer_updates == 20
    s2 = by_scenario["s2_capacity_v2"]
    assert s2.verification.loss_equivalence == "within_tol"
    assert s2.verification.max_loss_delta == 4.76837158203125e-7
    assert s2.verification.checks["same_inputs"] is None
    for row in catalog.runs:
        assert row.diagnosis_binding.round == 1
        assert row.diagnosis_binding.stage == "baseline"
        if row.outcome == "not_solved":
            assert row.after is None and row.selected_round is None
            assert row.last_attempt is not None and row.last_attempt.kept is False
    nano = next(row for row in catalog.runs if row.run_id == "416ccae0aa6c42f08cf928f50e9973ea")
    assert nano.last_attempt.candidate.optimizer_updates == 1
    assert nano.last_attempt.candidate.status == "oom"
    assert "patch" not in nano.downloads
    assert any("No code diff" in line for line in nano.limitations)
    encoded = json.dumps(catalog_document)
    assert "/home/" not in encoded and "/Users/" not in encoded
    assert '"budget"' not in encoded and '"request_evidence"' not in encoded


@pytest.mark.parametrize(
    "mutation",
    [
        "parameter",
        "false_success",
        "unresolved_ref",
        "private_field",
        "unsafe_url",
        "cross_run_path",
        "loss_count",
        "empty_patch",
    ],
)
def test_catalog_rejects_inconsistent_or_unsafe_public_data(catalog_document, mutation):
    doc = copy.deepcopy(catalog_document)
    first = doc["runs"][0]
    if mutation == "parameter":
        first["after"]["parameter_count"] -= 1
    elif mutation == "false_success":
        doc["runs"][-1]["outcome"] = "target_met"
    elif mutation == "unresolved_ref":
        first["diagnosis"]["root_causes"][0]["evidence_refs"] = ["stk_deadbeefdeadbeef"]
    elif mutation == "private_field":
        first["private_request"] = {"api_key": "must not be accepted"}
    elif mutation == "unsafe_url":
        doc["runs"][3]["sources"][0]["url"] = "https://user:password@example.com/"
    elif mutation == "cross_run_path":
        first["downloads"]["patch"]["path"] = "verified-assets/" + "0" * 32 + "/patch.diff"
    elif mutation == "empty_patch":
        first["downloads"]["patch"]["bytes"] = 0
        first["downloads"]["patch"]["sha256"] = digest(b"")
    else:
        first["verification"]["compared_loss_count"] = 5
    with pytest.raises((ValidationError, ValueError)):
        VerifiedCatalog.model_validate(doc)


def test_loader_rejects_asset_changes_and_symlinks(tmp_path):
    destination = tmp_path / "evidence"
    shutil.copytree(ROOT / "public-evidence", destination)
    doc = json.loads((destination / "verified-runs.json").read_text())
    path = destination / doc["runs"][0]["downloads"]["patch"]["path"]
    path.write_text("altered patch")
    with pytest.raises(ValueError, match="fingerprint"):
        load_verified(destination)
    path.unlink()
    path.symlink_to(ROOT / "public-evidence" / doc["runs"][0]["downloads"]["patch"]["path"])
    with pytest.raises((OSError, ValueError)):
        load_verified(destination)


@pytest.fixture
def bound_run(tmp_path):
    run_id = "a" * 32
    run_dir = tmp_path / "runs" / "jobs" / run_id
    run_dir.mkdir(parents=True)
    frames = [{"filename": "/source/train.py", "line": 3, "name": "forward"}]
    stack = "stk_" + digest(json.dumps(frames, sort_keys=True, separators=(",", ":")).encode())[:16]
    markdown = (
        "# Captured evidence\n\n"
        f"### {stack} — activations\n\nBytes: 1234; live blocks: 1\n\n"
        f"### {stack}\n\nCumulative bytes: 2468; allocations: 2; short-lived bytes: 0\n"
    )
    evidence = {
        "analysis": {
            "stack_catalog": {stack: frames},
            "peak_composition": [
                {"stack_id": stack, "category": "activations", "bytes": 1234, "blocks": 1}
            ],
            "allocation_hot_paths": [
                {"stack_id": stack, "bytes": 2468, "allocations": 2, "short_lived_bytes": 0}
            ],
        }
    }
    (run_dir / "evidence/before").mkdir(parents=True)
    (run_dir / "evidence/before/evidence.md").write_text(markdown)
    (run_dir / "evidence/before/evidence.json").write_text(json.dumps(evidence))
    (run_dir / "rounds/01").mkdir(parents=True)
    diagnosis = {
        "valid": True,
        "diagnosis": {
            "root_causes": [
                {
                    "title": "Initial cause",
                    "category": "activations",
                    "confidence": 0.9,
                    "evidence_refs": [stack],
                }
            ],
            "needs_more_info": False,
            "notes": [],
        },
    }
    (run_dir / "rounds/01/diagnosis.json").write_text(json.dumps(diagnosis))
    # A different later diagnosis must never be paired with the old baseline.
    (run_dir / "diagnosis.json").write_text(json.dumps({"diagnosis": {"title": "Later cause"}}))
    database = tmp_path / "runs/headroom.db"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE runs(id TEXT, data_json TEXT);"
            "CREATE TABLE events(run_id TEXT, kind TEXT, sequence INTEGER,"
            "created_at TEXT, data_json TEXT);"
            "CREATE TABLE llm_calls(id INTEGER,run_id TEXT,role TEXT,created_at TEXT,data_json TEXT);"
        )
        db.execute(
            "INSERT INTO runs VALUES(?,?)",
            (
                run_id,
                json.dumps(
                    {
                        "run_dir": str(run_dir),
                        "provenance": "live",
                        "before_evidence_paths": {
                            "evidence.json": "evidence/before/evidence.json",
                            "evidence.md": "evidence/before/evidence.md",
                        },
                    }
                ),
            ),
        )
        db.execute(
            "INSERT INTO events VALUES(?,?,?,?,?)",
            (run_id, "diagnose.done", 2, "2026-01-01T00:00:02Z", '{"round":1}'),
        )
        payload = {
            "model": "nvidia/test",
            "messages": [
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "evidence_markdown": markdown
                            + "\nSEARCH STATE (trusted orchestration metadata):"
                            + '{"round":1,"previous_rounds":[],"current_kept":null}'
                        }
                    ),
                }
            ],
        }
        call = {
            "model": "nvidia/test",
            "response_model": "nvidia/test",
            "http_status": 200,
            "outcome": "response",
            "request_evidence": {
                "capture_point": "httpx_pre_transport",
                "payload": payload,
                "stored_payload_sha256": digest(
                    json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
                ),
                "wire_body_sha256": "b" * 64,
            },
        }
        db.execute(
            "INSERT INTO llm_calls VALUES(?,?,?,?,?)",
            (1, run_id, "diagnose", "2026-01-01T00:00:01Z", json.dumps(call)),
        )
    return tmp_path, run_dir, database


def test_initial_binding_uses_first_diagnosis_and_leaves_database_unchanged(bound_run):
    root, run_dir, database = bound_run
    before = database.read_bytes()
    result = load_initial_diagnosis(run_dir, database=database, project_root=root)
    assert result["diagnosis"]["root_causes"][0]["title"] == "Initial cause"
    assert result["stacks"][0]["peak_live_bytes"] == 1234
    assert result["stacks"][0]["lifetime_allocated_bytes"] == 2468
    assert database.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        "markdown",
        "bytes",
        "frames",
        "no_call",
        "call_limit",
        "record_limit",
        "symlink",
        "invalid_diagnosis",
    ],
)
def test_missing_or_changed_binding_fails_closed(bound_run, mutation):
    root, run_dir, database = bound_run
    evidence_path = run_dir / "evidence/before/evidence.json"
    if mutation == "markdown":
        (run_dir / "evidence/before/evidence.md").write_text("different evidence")
    elif mutation in {"bytes", "frames"}:
        evidence = json.loads(evidence_path.read_text())
        if mutation == "bytes":
            evidence["analysis"]["peak_composition"][0]["bytes"] += 1
        else:
            next(iter(evidence["analysis"]["stack_catalog"].values()))[0]["line"] += 1
        evidence_path.write_text(json.dumps(evidence))
    elif mutation in {"no_call", "call_limit", "record_limit"}:
        with sqlite3.connect(database) as db:
            if mutation == "no_call":
                db.execute("DELETE FROM llm_calls")
            elif mutation == "record_limit":
                db.execute("UPDATE llm_calls SET data_json=?", ("x" * (MAX_RECORD_BYTES + 1),))
            else:
                row = db.execute("SELECT * FROM llm_calls").fetchone()
                for i in range(MAX_CALLS):
                    db.execute("INSERT INTO llm_calls VALUES(?,?,?,?,?)", (i + 2, *row[1:]))
    elif mutation == "invalid_diagnosis":
        (run_dir / "rounds/01/diagnosis.json").write_text('{"valid":false}')
    else:
        raw = evidence_path.read_bytes()
        evidence_path.unlink()
        outside = root / "outside.json"
        outside.write_bytes(raw)
        evidence_path.symlink_to(outside)
    assert load_initial_diagnosis(run_dir, database=database, project_root=root) is None


@pytest.mark.parametrize("field", ["run_dir", "database", "project_root"])
def test_parent_traversal_is_refused_before_database_access(bound_run, monkeypatch, field):
    import headroom.api.diagnosis_evidence as module

    root, run_dir, database = bound_run
    paths = {"run_dir": run_dir, "database": database, "project_root": root}
    path = paths[field]
    paths[field] = path.parent / ".." / path.parent.name / path.name

    def forbidden(*args, **kwargs):
        pytest.fail("Traversal must be refused before database access")

    monkeypatch.setattr(module.sqlite3, "connect", forbidden)
    assert module.load_initial_diagnosis(**paths) is None
