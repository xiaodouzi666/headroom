"""Offline live-shaped records only: no tests contact a provider or execute a target."""

import builtins
import hashlib
import io
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from headroom.api.app import ApiSettings, create_app
from headroom.replay_curation import MANIFEST, curate_repair_replays
from headroom.report import generate_report
from headroom.store.db import Store


@pytest.fixture(autouse=True)
def guards(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Real DNS/INET is forbidden")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    for module in (builtins, io, os):
        original = module.open

        def guarded(path, *args, _original=original, **kwargs):
            if isinstance(path, (str, Path)) and any(
                part.startswith(".env") for part in Path(path).parts
            ):
                raise AssertionError("No credential reads")
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)
    monkeypatch.delenv("HEADROOM_RUNTIME_PROFILE", raising=False)
    monkeypatch.delenv("HEADROOM_PUBLIC_HOST", raising=False)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def fixture_run(
    tmp_path,
    *,
    run_id="a" * 32,
    target_met=True,
    provenance="live",
    in_jobs=False,
    call_roles=("diagnose", "patcher"),
    patch_call_overrides=None,
    patch_relative="rounds/01/patches/attempt-01/patch.diff",
):
    """Synthetic records shaped like one fully saved live attempt, not live evidence."""
    runs = tmp_path / "runs"
    source = runs / ("jobs" if in_jobs else "campaign/jobs") / run_id
    before_dir = source / "lab/baseline"
    after_dir = source / "rounds/01/lab/candidate"
    baseline = {
        "run_id": "b" * 32,
        "run_dir": str(before_dir),
        "status": "oom",
        "capture_complete": True,
        "cleanup_verified": True,
        "peak_allocated_bytes": 24_000_000_000,
        "steps": 0,
        "loss_series": [],
        "env": {"device": "cuda"},
        "gpu_observation_complete": True,
    }
    after = {
        "run_id": "c" * 32,
        "run_dir": str(after_dir),
        "status": "completed" if target_met else "oom",
        "capture_complete": True,
        "cleanup_verified": True,
        "peak_allocated_bytes": 20_000_000_000,
        "steps": 20 if target_met else 0,
        "loss_series": [1.0, 0.9],
        "env": {"device": "cuda"},
    }
    write(before_dir / "result.json", baseline)
    write(after_dir / "result.json", after)
    patch = source / patch_relative
    patch.parent.mkdir(parents=True)
    patch.write_text("--- a/train.py\n+++ b/train.py\n@@ -1 +1 @@\n-X = 1\n+X = 2\n")
    candidate_source = patch.parent / "candidate"
    candidate_source.mkdir()
    (candidate_source / "train.py").write_text("do not copy source")
    (before_dir / "snapshot.pickle").write_bytes(b"never load or copy")
    write(
        source / "rounds/01/patch-result.json",
        {
            "status": "applied",
            "patch_path": str(patch),
            "candidate_dir": str(candidate_source),
        },
    )
    write(after_dir / "manifest.json", {"source_root": str(candidate_source), "device": "cuda"})
    verification = {
        "completed": target_met,
        "peak_before": 24.0,
        "peak_after": 20.0,
        "reduction_pct": 16.666,
        "target_met": target_met,
        "loss_equivalence": "identical" if target_met else "n/a",
        "checks": {"numerical_acceptance": target_met},
        "notes": [],
        "after": after,
    }
    write(source / "rounds/01/verification.json", verification)
    # A simple display asset is copied byte-for-byte; it represents no new measurement.
    (source / "patch.diff").write_bytes(patch.read_bytes())
    (source / "report-placeholder").write_text("must not be mirrored")
    selected_assets = {
        "patch": "configurations/round-01/patch.diff",
        "env": "configurations/round-01/env.sh",
        "cli": "configurations/round-01/cli.json",
        "manifest": "configurations/round-01/manifest.json",
    }
    if target_met:
        for relative, raw in (
            (selected_assets["patch"], patch.read_bytes()),
            (selected_assets["env"], b"# synthetic fixture\n"),
            (selected_assets["cli"], b"[]\n"),
        ):
            file = source / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        write(source / selected_assets["manifest"], {"run_id": run_id, "round": 1})
        (source / "env.sh").write_bytes((source / selected_assets["env"]).read_bytes())
        (source / "cli.json").write_bytes((source / selected_assets["cli"]).read_bytes())
    data = {
        "run_id": run_id,
        "status": "completed" if target_met else "failed",
        "target": "fix-oom",
        "target_met": target_met,
        "provenance": provenance,
        "run_dir": str(source),
        "baseline": baseline,
        "after": after,
        "kept": {"round": 1, "artifacts": selected_assets} if target_met else None,
    }
    store = Store(runs / "headroom.db")
    try:
        store.create_run(run_id, data)
        store.add_event(run_id, "run.started", {"provenance": provenance, "target": "fix-oom"})
        for kind in ("diagnose.done", "patch.applied", "verify.done"):
            values = {"round": 1}
            if kind == "verify.done":
                values.update(
                    target_met=target_met, loss_equivalence=verification["loss_equivalence"]
                )
            store.add_event(run_id, kind, values)
        for role in call_roles:
            store.add_llm_call(
                run_id,
                {
                    "role": role,
                    "model": "nvidia/fixture-model",
                    "response_model": "nvidia/fixture-model",
                    "outcome": "response",
                    "http_status": 200,
                    "settled": True,
                    "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                    "cost": {"usd": "0.001", "status": "known"},
                    "cost_usd": "0.001",
                    **(patch_call_overrides or {} if role != "diagnose" else {}),
                },
            )
        store.add_round(
            run_id,
            {
                "number": 1,
                "verification": verification,
                "patch": patch_relative,
                "keep": target_met,
                "target_met": target_met,
            },
        )
        generate_report(
            source,
            store.get_run(run_id),
            rounds=store.rounds(run_id),
            verification=verification,
            usage=store.usage(run_id),
            artifacts={"patch": patch_relative},
        )
        store.add_event(run_id, "report.written", {"report": "report.md"})
        store.add_event(
            run_id, "run.done" if target_met else "run.failed", {"target_met": target_met}
        )
    finally:
        store.close()
    return run_id, source


def saved_records(root, run_id):
    with sqlite3.connect(root / "runs/headroom.db") as connection:
        return {
            table: connection.execute(
                f"SELECT * FROM {table} WHERE " + ("id=?" if table == "runs" else "run_id=?"),
                (run_id,),
            ).fetchall()
            for table in ("runs", "rounds", "events", "llm_calls")
        }


def test_default_is_readonly_and_execute_mirrors_exact_assets(tmp_path):
    run_id, source = fixture_run(tmp_path)
    before = saved_records(tmp_path, run_id)
    report_hash = hashlib.sha256((source / "report.json").read_bytes()).hexdigest()
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert result["eligible"] and not result["executed"], result
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()
    assert not (source / MANIFEST).exists()

    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert result["executed"]
    mirror = tmp_path / "runs/jobs" / run_id
    manifest = json.loads((mirror / MANIFEST).read_text())
    for relative, record in manifest["assets"].items():
        assert (mirror / relative).read_bytes() == (source / relative).read_bytes()
        assert hashlib.sha256((mirror / relative).read_bytes()).hexdigest() == record["sha256"]
    assert not list(mirror.rglob("train.py"))
    assert not list(mirror.rglob("snapshot.pickle"))
    assert not (mirror / "report-placeholder").exists()
    assert len(manifest["source_evidence"]) == 4
    for relative, record in manifest["source_evidence"].items():
        assert (
            hashlib.sha256((tmp_path / "runs" / relative).read_bytes()).hexdigest()
            == record["sha256"]
        )
    after = saved_records(tmp_path, run_id)
    assert all(after[key] == before[key] for key in ("rounds", "events", "llm_calls"))
    assert hashlib.sha256((source / "report.json").read_bytes()).hexdigest() == report_hash
    payload = json.loads(after["runs"][0][-1])
    assert payload["public_replay"] is True
    assert payload["target_met"] is True and payload["provenance"] == "live"
    repeated = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert repeated["executed"]
    assert saved_records(tmp_path, run_id) == after


@pytest.mark.parametrize("provenance", ["offline_fixture", "recorded_baseline", "unknown"])
def test_baseline_and_fixture_rows_cannot_be_relabelled(tmp_path, provenance):
    run_id, _ = fixture_run(tmp_path, provenance=provenance)
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert not result["eligible"] and not result["executed"]
    assert result["runs"][0]["reason"] == "NOT_A_LIVE_REPAIR"
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("report_target", "REPORT_RUN_STATE_MISMATCH"),
        ("verification", "VERIFICATION_ARTIFACT_MISMATCH"),
        ("patch", "REPORT_PATCH_MISMATCH"),
        ("canonical_patch", "TOP_LEVEL_SELECTED_ASSET_MISMATCH"),
        ("missing_patch", "REQUIRED_ARTIFACT_MISSING"),
        ("source_manifest", "PATCH_CANDIDATE_SOURCE_MISMATCH"),
        ("missing_events", "EVENT_SEQUENCE_INCOMPLETE"),
        ("usage", "REPORT_USAGE_MISMATCH"),
    ],
)
def test_mismatched_evidence_is_refused_without_curation(tmp_path, mutation, reason):
    run_id, source = fixture_run(tmp_path)
    if mutation == "report_target":
        path = source / "report.json"
        doc = json.loads(path.read_text())
        doc["run"]["target_met"] = False
        write(path, doc)
    elif mutation == "verification":
        path = source / "rounds/01/verification.json"
        doc = json.loads(path.read_text())
        doc["target_met"] = False
        write(path, doc)
    elif mutation == "canonical_patch":
        (source / "patch.diff").write_text("stale unrelated selected patch")
    elif mutation in {"patch", "missing_patch"}:
        path = source / "rounds/01/patches/attempt-01/patch.diff"
        path.unlink() if mutation == "missing_patch" else path.write_text("different")
    elif mutation == "source_manifest":
        write(source / "rounds/01/lab/candidate/manifest.json", {"source_root": "/elsewhere"})
    elif mutation == "missing_events":
        with sqlite3.connect(tmp_path / "runs/headroom.db") as connection:
            connection.execute("DELETE FROM events WHERE run_id=? AND sequence=2", (run_id,))
    else:
        path = source / "report.json"
        doc = json.loads(path.read_text())
        doc["usage"]["total_cost_usd"] = "0"
        write(path, doc)
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert not result["executed"] and result["runs"][0]["reason"] == reason, result


def test_symlink_asset_never_follows_outside_file(tmp_path):
    run_id, source = fixture_run(tmp_path)
    outside = tmp_path / "private.txt"
    outside.write_text("private sentinel")
    path = source / "report.md"
    path.unlink()
    path.symlink_to(outside)
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert not result["executed"]
    assert outside.read_text() == "private sentinel"
    assert not (tmp_path / "runs/jobs").exists()


def test_existing_destination_conflict_is_not_overwritten(tmp_path):
    run_id, _ = fixture_run(tmp_path)
    destination = tmp_path / "runs/jobs" / run_id
    destination.mkdir(parents=True)
    (destination / "report.json").write_text("unrelated existing artifact")
    before = saved_records(tmp_path, run_id)
    with pytest.raises(ValueError):
        curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert (destination / "report.json").read_text() == "unrelated existing artifact"
    assert saved_records(tmp_path, run_id) == before


def test_batch_failure_rolls_back_flags_and_only_owned_mirrors(tmp_path, monkeypatch):
    import headroom.replay_curation as curation

    first, _ = fixture_run(tmp_path)
    second, _ = fixture_run(tmp_path, run_id="d" * 32)
    before = {key: saved_records(tmp_path, key) for key in (first, second)}
    original = curation._mirror

    def fail_second(runs, source, run_id, assets, manifest):
        if run_id == second:
            raise OSError("fixture copy failure")
        return original(runs, source, run_id, assets, manifest)

    monkeypatch.setattr(curation, "_mirror", fail_second)
    with pytest.raises(OSError):
        curate_repair_replays([first, second], project_root=tmp_path, execute=True)
    assert all(saved_records(tmp_path, key) == before[key] for key in before)
    assert not (tmp_path / "runs/jobs" / first).exists()
    assert not (tmp_path / "runs/jobs" / second).exists()


@pytest.mark.parametrize("target_met", [True, False])
def test_historical_curated_marker_no_longer_publishes_through_api(tmp_path, target_met):
    run_id, source = fixture_run(tmp_path, target_met=target_met)
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert result["executed"], result
    before = saved_records(tmp_path, run_id)
    assets = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    settings = ApiSettings(
        project_root=tmp_path,
        db_path=tmp_path / "runs/headroom.db",
        run_root=tmp_path / "runs/jobs",
        web_dist=tmp_path / "no-web",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/replays").status_code == 404
        assert client.get("/api/runs").json()["runs"] == []
        for suffix in (
            "",
            "/events",
            "/report.json",
            "/report.md",
            "/patch.diff",
            "/configuration.json",
            "/configurations/round-01/patch.diff",
            "/snapshot.pickle",
            "/.env",
        ):
            assert client.get(f"/api/runs/{run_id}{suffix}").status_code == 404
    assert saved_records(tmp_path, run_id) == before
    assert {
        str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()
    } == assets


def test_no_database_creation_and_no_implicit_ids(tmp_path):
    from headroom.replay_curation import CurationRefused

    with pytest.raises(CurationRefused, match="EXPLICIT"):
        curate_repair_replays([], project_root=tmp_path)
    (tmp_path / "runs").mkdir()
    with pytest.raises(FileNotFoundError):
        curate_repair_replays(["a" * 32], project_root=tmp_path)
    assert not (tmp_path / "runs/headroom.db").exists()


@pytest.mark.parametrize("extra", [[], ["--execute"]])
def test_cli_requires_explicit_ids_and_defaults_to_readonly(monkeypatch, extra, capsys):
    import importlib.util

    script = Path(__file__).resolve().parents[1] / "scripts/curate_repair_replays.py"
    spec = importlib.util.spec_from_file_location("repair_curation_cli", script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    calls = []

    def curate(ids, *, execute):
        calls.append((ids, execute))
        return {"eligible": True, "executed": execute}

    monkeypatch.setattr(cli, "curate_repair_replays", curate)
    assert cli.main(["--run-id", "a" * 32, "--run-id", "b" * 32, *extra]) == 0
    assert calls == [(["a" * 32, "b" * 32], bool(extra))]
    assert json.loads(capsys.readouterr().out)["executed"] is bool(extra)
    with pytest.raises(SystemExit):
        cli.main(extra)


def test_any_ineligible_id_rejects_the_entire_explicit_batch(tmp_path):
    first, _ = fixture_run(tmp_path)
    second, _ = fixture_run(tmp_path, run_id="d" * 32, provenance="recorded_baseline")
    before = {run_id: saved_records(tmp_path, run_id) for run_id in (first, second)}
    result = curate_repair_replays([first, second], project_root=tmp_path, execute=True)
    assert not result["eligible"] and not result["executed"]
    assert all(saved_records(tmp_path, key) == before[key] for key in before)
    assert not (tmp_path / "runs/jobs").exists()


def test_existing_api_job_is_curated_in_place_without_copying_or_rewriting(tmp_path):
    run_id, source = fixture_run(tmp_path, in_jobs=True)
    before = {
        str(path.relative_to(source)): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert result["executed"]
    assert all((source / name).read_bytes() == raw for name, raw in before.items())
    assert (source / MANIFEST).is_file()
    assert not list((tmp_path / "runs/jobs").glob(".curation-*"))


@pytest.mark.parametrize("failure", [OSError, KeyboardInterrupt])
def test_commit_then_raise_preserves_published_assets(tmp_path, monkeypatch, failure):
    import headroom.replay_curation as curation

    run_id, source = fixture_run(tmp_path)
    original_connect = sqlite3.connect

    class CommitThenRaise(sqlite3.Connection):
        def commit(self):
            super().commit()
            raise failure("injected after commit")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            curation.sqlite3,
            "connect",
            lambda *args, **kwargs: original_connect(*args, factory=CommitThenRaise, **kwargs),
        )
        with pytest.raises(failure) as caught:
            curate_repair_replays([run_id], project_root=tmp_path, execute=True)

    payload = json.loads(saved_records(tmp_path, run_id)["runs"][0][-1])
    assert payload["public_replay"] is True
    mirror = tmp_path / "runs/jobs" / run_id
    assert (mirror / "report.json").read_bytes() == (source / "report.json").read_bytes()
    assert (mirror / MANIFEST).is_file()
    assert any("assets were retained" in note for note in caught.value.__notes__)
    assert curate_repair_replays([run_id], project_root=tmp_path, execute=True)["executed"]


def test_precommit_failure_rolls_back_and_removes_owned_mirror(tmp_path, monkeypatch):
    import headroom.replay_curation as curation

    run_id, _ = fixture_run(tmp_path)
    before = saved_records(tmp_path, run_id)
    original_connect = sqlite3.connect

    class CommitFailure(sqlite3.Connection):
        def commit(self):
            raise OSError("injected before commit")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            curation.sqlite3,
            "connect",
            lambda *args, **kwargs: original_connect(*args, factory=CommitFailure, **kwargs),
        )
        with pytest.raises(OSError, match="before commit"):
            curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs" / run_id).exists()


def test_unconfirmed_rollback_keeps_complete_audit_assets(tmp_path, monkeypatch):
    import headroom.replay_curation as curation

    run_id, _ = fixture_run(tmp_path)
    before = saved_records(tmp_path, run_id)
    original_connect = sqlite3.connect

    class UncertainTransaction(sqlite3.Connection):
        def commit(self):
            raise OSError("injected commit error")

        def rollback(self):
            raise sqlite3.OperationalError("injected rollback error")

    with monkeypatch.context() as patcher:
        patcher.setattr(
            curation.sqlite3,
            "connect",
            lambda *args, **kwargs: original_connect(*args, factory=UncertainTransaction, **kwargs),
        )
        with pytest.raises(OSError, match="commit error") as caught:
            curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert saved_records(tmp_path, run_id) == before  # Connection close aborted this fixture.
    mirror = tmp_path / "runs/jobs" / run_id
    assert (mirror / MANIFEST).is_file()
    assert any("rollback could not be confirmed" in note for note in caught.value.__notes__)
    assert curate_repair_replays([run_id], project_root=tmp_path, execute=True)["executed"]


@pytest.mark.parametrize("failure_stage", ["write", "chmod"])
def test_native_manifest_creation_failure_removes_only_new_partial_file(
    tmp_path, monkeypatch, failure_stage
):
    import headroom.replay_curation as curation

    run_id, source = fixture_run(tmp_path, in_jobs=True)
    before = saved_records(tmp_path, run_id)
    originals = {
        str(path.relative_to(source)): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    original_open = Path.open
    original_chmod = os.chmod

    class PartialWriter:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.handle.close()

        def write(self, raw):
            self.handle.write(raw[:7])
            self.handle.flush()
            raise OSError("injected partial manifest write")

    def failing_open(path, mode="r", *args, **kwargs):
        handle = original_open(path, mode, *args, **kwargs)
        if path == source / MANIFEST and mode == "xb":
            return PartialWriter(handle)
        return handle

    def failing_chmod(path, *args, **kwargs):
        if Path(path) == source / MANIFEST:
            raise OSError("injected manifest chmod failure")
        return original_chmod(path, *args, **kwargs)

    with monkeypatch.context() as patcher:
        if failure_stage == "write":
            patcher.setattr(Path, "open", failing_open)
        else:
            patcher.setattr(curation.os, "chmod", failing_chmod)
        with pytest.raises(OSError, match="injected"):
            curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert not (source / MANIFEST).exists()
    assert saved_records(tmp_path, run_id) == before
    assert all((source / relative).read_bytes() == raw for relative, raw in originals.items())
    assert curate_repair_replays([run_id], project_root=tmp_path, execute=True)["executed"]


def test_exclusive_write_failure_never_removes_preexisting_file(tmp_path):
    import headroom.replay_curation as curation

    path = tmp_path / MANIFEST
    path.write_bytes(b"preexisting manifest")
    with pytest.raises(FileExistsError):
        curation._write_new(path, b"replacement")
    assert path.read_bytes() == b"preexisting manifest"


@pytest.mark.parametrize("patch_role", ["patcher", "patch", "patch_fix"])
def test_production_and_legacy_patch_roles_are_eligible_without_writes(tmp_path, patch_role):
    run_id, _ = fixture_run(tmp_path, call_roles=("diagnose", patch_role))
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path)
    assert result["eligible"] is True and result["executed"] is False
    assert result["runs"][0]["verified_attempt_rounds"] == [1]
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()


@pytest.mark.parametrize(
    "call_roles,overrides",
    [
        (("diagnose",), None),
        (("patcher",), None),
        (("diagnose", "research"), None),
        (("diagnose", "PatchER"), None),
        (("diagnose", "patcher"), {"outcome": "not_dispatched"}),
        (("diagnose", "patcher"), {"http_status": 429}),
        (("diagnose", "patcher"), {"response_model": "nvidia/unrelated-model"}),
        (("diagnose", "patcher"), {"usage": None}),
    ],
)
def test_patcher_name_does_not_bypass_valid_response_requirements(tmp_path, call_roles, overrides):
    run_id, _ = fixture_run(tmp_path, call_roles=call_roles, patch_call_overrides=overrides)
    before = saved_records(tmp_path, run_id)
    result = curate_repair_replays([run_id], project_root=tmp_path, execute=True)
    assert result["eligible"] is False and result["executed"] is False
    assert result["runs"][0]["reason"] == "REAL_MODEL_RESPONSE_RECORDS_MISSING"
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs").exists()


def test_uncurated_campaign_stays_private_in_default_store(tmp_path):
    run_id, _ = fixture_run(tmp_path)
    before = saved_records(tmp_path, run_id)
    settings = ApiSettings(
        project_root=tmp_path,
        db_path=tmp_path / "runs/headroom.db",
        run_root=tmp_path / "runs/jobs",
        web_dist=tmp_path / "no-web",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/replays").status_code == 404
        for suffix in ("", "/events", "/report.json", "/patch.diff"):
            assert client.get(f"/api/runs/{run_id}{suffix}").status_code == 404
    assert saved_records(tmp_path, run_id) == before
    assert not (tmp_path / "runs/jobs" / run_id).exists()
