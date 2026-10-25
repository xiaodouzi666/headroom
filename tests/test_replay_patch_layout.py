"""Production PatchEngine path layout, using synthetic temporary records only."""

import hashlib
import json
import sqlite3

import pytest
from test_repair_replay_curation import (
    fixture_run,
    guards,  # noqa: F401 - apply existing no-network guard
    saved_records,
    write,
)

from headroom.replay_curation import _allowed_asset, curate_repair_replays

ENGINE = "1" * 32
PATCH = "2" * 32


def relative(attempt=1, round_number=1):
    return (
        f"rounds/{round_number:02d}/patches/patch-engine-{ENGINE}/"
        f"attempt-{attempt}/patch-{PATCH}/patch.diff"
    )


@pytest.mark.parametrize("attempt", [1, 2, 3, 4])
@pytest.mark.parametrize("target_met", [True, False])
def test_exact_generated_nested_patch_is_eligible_without_curation(
    tmp_path, monkeypatch, attempt, target_met
):
    path = relative(attempt)
    run_id, source = fixture_run(tmp_path, target_met=target_met, patch_relative=path)
    before = saved_records(tmp_path, run_id)
    original_files = {
        str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    }

    def denied(*args, **kwargs):
        pytest.fail("Dry inspection must never mirror or publish assets")

    monkeypatch.setattr("headroom.replay_curation._mirror", denied)
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert result["eligible"] and not result["executed"], result
    record = result["runs"][0]
    assert record["verified_attempt_rounds"] == [1]
    assert record["target_met"] is target_met
    assert path in record["assets"]
    assert record["assets"][path]["sha256"] == original_files[path]
    assert not any("candidate/" in name or name.endswith(".pickle") for name in record["assets"])
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()
    assert {
        str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.rglob("*")
        if p.is_file()
    } == original_files


@pytest.mark.parametrize("round_number", [1, 2, 3, 4, 5, 6])
def test_only_supported_round_range(round_number):
    assert _allowed_asset(relative(4, round_number))


@pytest.mark.parametrize(
    "path",
    [
        relative(0),
        relative(5),
        relative(1, 0),
        relative(1, 7),
        relative().replace("attempt-1", "attempt-01"),
        relative().replace(ENGINE, "a" * 31),
        relative().replace(ENGINE, "A" * 32),
        relative().replace(PATCH, "g" * 32),
        relative().replace("patch-engine-", "other-engine-"),
        relative().replace("patch-" + PATCH, "other-" + PATCH),
        relative().replace("/patch.diff", "/candidate/train.py"),
        relative().replace("/patch.diff", "/snapshot.pickle"),
        relative().replace("/patch.diff", "/attempt-1-response.json"),
        relative().replace("/patch.diff", "/env.sh"),
        relative().replace("/patch.diff", "/.env"),
        relative().replace("/attempt-1/", "/../"),
        relative().replace("/attempt-1/", "//attempt-1/"),
        relative().replace("/attempt-1/", "/extra/attempt-1/"),
        "/" + relative(),
        relative().replace("/", "\\"),
    ],
)
def test_new_pattern_does_not_admit_other_files_or_ambiguous_layouts(path):
    assert not _allowed_asset(path)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("patch", "REPORT_PATCH_MISMATCH"),
        ("application", "PATCH_APPLICATION_RECORD_MISMATCH"),
        ("candidate_source", "PATCH_CANDIDATE_SOURCE_MISMATCH"),
        ("capture", "CANDIDATE_CAPTURE_MISMATCH"),
        ("missing_response", "REAL_MODEL_RESPONSE_RECORDS_MISSING"),
        ("no_verification", "NO_RECORDED_REPAIR_VERIFICATION"),
    ],
)
def test_nested_path_cannot_bypass_original_evidence_binding(tmp_path, mutation, reason):
    run_id, source = fixture_run(tmp_path, patch_relative=relative())
    if mutation == "patch":
        (source / relative()).write_text("unrelated diff")
    elif mutation == "application":
        file = source / "rounds/01/patch-result.json"
        doc = json.loads(file.read_text())
        doc["patch_path"] = str(source / "elsewhere/patch.diff")
        write(file, doc)
    elif mutation == "candidate_source":
        write(source / "rounds/01/lab/candidate/manifest.json", {"source_root": "/elsewhere"})
    elif mutation == "capture":
        file = source / "rounds/01/lab/candidate/result.json"
        doc = json.loads(file.read_text())
        doc["steps"] = 99
        write(file, doc)
    else:
        with sqlite3.connect(tmp_path / "runs/headroom.db") as db:
            if mutation == "missing_response":
                db.execute("DELETE FROM llm_calls WHERE run_id=? AND role='patcher'", (run_id,))
            else:
                db.execute("DELETE FROM rounds WHERE run_id=?", (run_id,))
        if mutation == "no_verification":
            file = source / "report.json"
            doc = json.loads(file.read_text())
            doc["rounds"] = []
            write(file, doc)
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert not result["eligible"] and not result["executed"]
    assert result["runs"][0]["reason"] == reason, result
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()


@pytest.mark.parametrize("provenance", ["recorded_baseline", "offline_fixture", "unknown"])
def test_nested_path_never_upgrades_baseline_only_provenance(tmp_path, provenance):
    run_id, _ = fixture_run(tmp_path, patch_relative=relative(), provenance=provenance)
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert result["runs"][0]["reason"] == "NOT_A_LIVE_REPAIR"
    assert not result["eligible"] and not result["executed"]
    assert saved_records(tmp_path, run_id) == before


@pytest.mark.parametrize("component", ["engine", "attempt", "patch", "leaf"])
def test_nested_layout_still_refuses_symlink_at_each_component(tmp_path, component):
    run_id, source = fixture_run(tmp_path, patch_relative=relative())
    patch = source / relative()
    location = {
        "engine": patch.parents[2],
        "attempt": patch.parents[1],
        "patch": patch.parent,
        "leaf": patch,
    }[component]
    outside = tmp_path / "outside"
    location.rename(outside)
    location.symlink_to(outside, target_is_directory=outside.is_dir())
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert not result["eligible"] and not result["executed"]
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()
