"""Explicit curation of preserved repair runs; never execute or manufacture a repair."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
from decimal import Decimal, localcontext
from pathlib import Path

from headroom.api.security import ARTIFACTS, RUN_ID, artifact_relative, open_regular

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ASSETS_BYTES = 128 * 1024 * 1024
MANIFEST = "repair-replay-curation.json"
TERMINAL = {"completed", "failed", "timeout", "needs_human", "budget_exceeded"}


class CurationRefused(ValueError):
    """Fixed codes only; do not echo artifact content or database exceptions."""


def _require(condition, code):
    if not condition:
        raise CurationRefused(code)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()


def _json(raw):
    def reject(_):
        raise CurationRefused("NONFINITE_JSON")

    return json.loads(raw, parse_constant=reject)


def _root(path):
    path = Path(path).absolute()
    for ancestor in (path, *path.parents):
        _require(not ancestor.is_symlink(), "SYMLINK_DIRECTORY")
    _require(path.is_dir(), "DIRECTORY_MISSING")
    return path


def _read(runs, path):
    path = Path(path)
    _require(path.is_absolute() and path.is_relative_to(runs), "ARTIFACT_OUTSIDE_RUNS")
    relative = path.relative_to(runs).as_posix()
    _require(
        not any(part.lower().startswith(".env") for part in path.parts), "SECRET_PATH_FORBIDDEN"
    )
    with open_regular(runs, relative, max_bytes=MAX_FILE_BYTES) as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    _require(len(raw) <= MAX_FILE_BYTES, "ARTIFACT_TOO_LARGE")
    return raw


def _rows(connection, table, run_id, order, limit):
    # table/order are private literals, never CLI input.
    rows = connection.execute(
        f"SELECT * FROM {table} WHERE run_id=? ORDER BY {order} LIMIT ?", (run_id, limit + 1)
    ).fetchall()
    _require(len(rows) <= limit, "TOO_MANY_RECORDS")
    result = []
    for row in rows:
        values = dict(row)
        _require(len(values["data_json"].encode()) <= 8 * 1024 * 1024, "DATABASE_RECORD_TOO_LARGE")
        payload = _json(values.pop("data_json"))
        _require(isinstance(payload, dict), "INVALID_DATABASE_RECORD")
        result.append({**payload, **values})
    return result


def _allowed_asset(relative):
    if not isinstance(relative, str) or any(
        part in {"", ".", ".."} or part.lower().startswith(".env") for part in relative.split("/")
    ):
        return False
    patterns = (
        r"(report|pareto)\.(json|md)",
        r"(patch\.diff|env\.sh|cli\.json|annotations\.json)",
        r"evidence/(before|after)/(evidence(?:\.unannotated-[0-9a-f]{32})?\.(json|md)|timeline\.png)",
        r"rounds/0[1-6]/verification\.json",
        r"rounds/0[1-6]/patches/[A-Za-z0-9_-]+/patch\.diff",
        r"rounds/0[1-6]/evidence/(evidence\.(json|md)|timeline\.png)",
        r"configurations/round-0[1-6]/(patch\.diff|env\.sh|cli\.json|manifest\.json)",
    )
    return any(re.fullmatch(pattern, relative) for pattern in patterns)


def _inspection(connection, runs, run_id):
    stored = connection.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    _require(stored is not None, "RUN_NOT_FOUND")
    stored = dict(stored)
    _require(len(stored["data_json"].encode()) <= 8 * 1024 * 1024, "DATABASE_RECORD_TOO_LARGE")
    payload = _json(stored["data_json"])
    row = {**payload, **{k: v for k, v in stored.items() if k != "data_json"}, "run_id": run_id}
    _require(row.get("provenance") == "live", "NOT_A_LIVE_REPAIR")
    _require(row["status"] in TERMINAL, "RUN_NOT_TERMINAL")
    _require(not row.get("api_report_pending"), "REPORT_STILL_PENDING")
    _require(
        "api_worker_finished" not in row or row["api_worker_finished"] is True,
        "WORKER_NOT_FINISHED",
    )
    source = Path(row.get("run_dir", ""))
    _require(source.is_absolute() and source.is_relative_to(runs), "RUN_DIRECTORY_OUTSIDE_RUNS")
    _root(source)
    assets = {}
    source_evidence = {}

    def evidence_file(path):
        raw = _read(runs, path)
        source_evidence[Path(path).relative_to(runs).as_posix()] = {
            "bytes": len(raw),
            "sha256": _digest(raw),
        }
        return _json(raw)

    def asset(relative, *, optional=False):
        _require(_allowed_asset(relative), "ASSET_NOT_ALLOWLISTED")
        try:
            raw = _read(runs, source / relative)
        except FileNotFoundError:
            if optional:
                return None
            raise CurationRefused("REQUIRED_ARTIFACT_MISSING") from None
        assets[relative] = raw
        _require(sum(map(len, assets.values())) <= MAX_ASSETS_BYTES, "ASSET_SET_TOO_LARGE")
        return raw

    report = _json(asset("report.json"))
    asset("report.md")
    report_run = report.get("run", {})
    _require(report_run.get("run_id", report_run.get("id")) == run_id, "REPORT_RUN_ID_MISMATCH")
    for key in ("provenance", "status", "target", "target_met", "baseline", "after", "kept"):
        _require(report_run.get(key) == row.get(key), "REPORT_RUN_STATE_MISMATCH")
    _require(report.get("status") == row["status"], "REPORT_STATUS_MISMATCH")
    _require(report.get("summary", {}).get("target") == row.get("target"), "REPORT_TARGET_MISMATCH")
    _require(
        report.get("summary", {}).get("target_met") == row.get("target_met"),
        "REPORT_TARGET_RESULT_MISMATCH",
    )

    events = _rows(connection, "events", run_id, "sequence", 10000)
    _require(
        [event["sequence"] for event in events] == list(range(1, row["event_sequence"] + 1)),
        "EVENT_SEQUENCE_INCOMPLETE",
    )
    _require(
        any(
            event["kind"] == "run.started" and event.get("provenance") == "live" for event in events
        )
        and any(event["kind"] == "report.written" for event in events),
        "REPAIR_EVENTS_MISSING",
    )
    calls = _rows(connection, "llm_calls", run_id, "id", 200)
    valid_roles = {
        call["role"]
        for call in calls
        if call.get("outcome") == "response"
        and call.get("http_status") == 200
        and call.get("model") == call.get("response_model")
        and isinstance(call.get("model"), str)
        and call["model"].startswith("nvidia/")
        and isinstance(call.get("usage"), dict)
    }
    _require(
        "diagnose" in valid_roles and valid_roles & {"patch", "patch_fix"},
        "REAL_MODEL_RESPONSE_RECORDS_MISSING",
    )
    usage = report.get("usage", {})
    unknown = sum(call.get("cost_usd") is None for call in calls)
    with localcontext() as context:
        context.prec = 256
        known = sum(
            (Decimal(call["cost_usd"]) for call in calls if call.get("cost_usd") is not None),
            Decimal(0),
        )
    _require(known.is_finite() and known >= 0, "INVALID_COST_RECORD")
    _require(
        usage.get("calls") == len(calls)
        and usage.get("unknown_cost_calls") == unknown
        and Decimal(usage.get("known_cost_usd", "NaN")) == known
        and (
            usage.get("total_cost_usd") is None
            if unknown
            else Decimal(usage.get("total_cost_usd", "NaN")) == known
        ),
        "REPORT_USAGE_MISMATCH",
    )
    rounds = _rows(connection, "rounds", run_id, "number", 6)
    report_rounds = {item.get("number"): item for item in report.get("rounds", [])}
    _require(len(report_rounds) == len(rounds), "REPORT_ROUNDS_MISMATCH")
    verified = []
    for item in rounds:
        number = item["number"]
        _require(type(number) is int and 1 <= number <= 6, "INVALID_ROUND_NUMBER")
        shown = report_rounds.get(number, {})
        for key in ("verification", "patch", "keep", "target_met"):
            _require(shown.get(key) == item.get(key), "REPORT_ROUND_MISMATCH")
        verification = item.get("verification")
        if not isinstance(verification, dict) or not verification:
            continue
        relative = f"rounds/{number:02d}/verification.json"
        raw_verification = _json(asset(relative))
        # The orchestrator may append a fresh-evidence-unavailable note after saving
        # verification.json. Measurements/checks remain exactly the saved values.
        _require(
            {k: v for k, v in verification.items() if k != "notes"}
            == {k: v for k, v in raw_verification.items() if k != "notes"},
            "VERIFICATION_ARTIFACT_MISMATCH",
        )
        after = verification.get("after", {})
        _require(after.get("env", {}).get("device") == "cuda", "NOT_A_RECORDED_CUDA_ATTEMPT")
        capture_path = Path(after.get("run_dir", "")) / "result.json"
        capture = evidence_file(capture_path)
        for key in (
            "run_id",
            "status",
            "capture_complete",
            "peak_allocated_bytes",
            "loss_series",
            "steps",
        ):
            _require(capture.get(key) == after.get(key), "CANDIDATE_CAPTURE_MISMATCH")
        patch = item.get("patch")
        _require(
            isinstance(patch, str) and patch.startswith(f"rounds/{number:02d}/patches/"),
            "ROUND_PATCH_MISSING",
        )
        patch_bytes = asset(patch)
        _require(
            shown.get("diff_status") == "available"
            and shown.get("diff_sha256") == _digest(patch_bytes)
            and shown.get("diff") == patch_bytes.decode("utf-8"),
            "REPORT_PATCH_MISMATCH",
        )
        patch_result = evidence_file(source / f"rounds/{number:02d}/patch-result.json")
        _require(
            patch_result.get("status") == "applied"
            and patch_result.get("patch_path") == str(source / patch),
            "PATCH_APPLICATION_RECORD_MISMATCH",
        )
        capture_manifest = evidence_file(capture_path.with_name("manifest.json"))
        _require(
            capture_manifest.get("source_root") == patch_result.get("candidate_dir"),
            "PATCH_CANDIDATE_SOURCE_MISMATCH",
        )
        round_events = [event for event in events if event.get("round") == number]
        verified_events = [event for event in round_events if event["kind"] == "verify.done"]
        _require(
            len(verified_events) == 1
            and verified_events[0].get("target_met") == verification.get("target_met")
            and verified_events[0].get("loss_equivalence") == verification.get("loss_equivalence"),
            "VERIFICATION_EVENT_MISMATCH",
        )
        sequence = [event["kind"] for event in round_events]
        _require(
            "patch.applied" in sequence
            and "verify.done" in sequence
            and sequence.index("patch.applied") < sequence.index("verify.done"),
            "ROUND_EXECUTION_EVENTS_MISSING",
        )
        verified.append(number)
    _require(verified, "NO_RECORDED_REPAIR_VERIFICATION")
    kept = row.get("kept")
    _require(
        row.get("target_met") is not True or isinstance(kept, dict),
        "SUCCESS_WITHOUT_SELECTED_CONFIGURATION",
    )
    if isinstance(kept, dict):
        _require(kept.get("round") in verified, "SELECTED_ROUND_NOT_VERIFIED")
        for relative in kept.get("artifacts", {}).values():
            asset(relative)
        for name in ("configuration.json", "patch.diff", "env.sh", "cli.json"):
            asset(artifact_relative(row, name))
        selected = kept.get("artifacts", {})
        for name, key in (("patch.diff", "patch"), ("env.sh", "env"), ("cli.json", "cli")):
            _require(
                asset(name) == asset(selected.get(key)),
                "TOP_LEVEL_SELECTED_ASSET_MISMATCH",
            )
        _require(
            artifact_relative(row, "configuration.json") == selected.get("manifest"),
            "SELECTED_MANIFEST_PATH_MISMATCH",
        )
    baseline = row.get("baseline") or {}
    _require(baseline.get("env", {}).get("device") == "cuda", "BASELINE_NOT_CUDA")
    baseline_raw = evidence_file(Path(baseline.get("run_dir", "")) / "result.json")
    for key in (
        "run_id",
        "status",
        "capture_complete",
        "peak_allocated_bytes",
        "loss_series",
        "steps",
    ):
        _require(baseline_raw.get(key) == baseline.get(key), "BASELINE_CAPTURE_MISMATCH")

    for relative in report.get("artifacts", {}).values():
        asset(relative)
    downloads = {}
    for name in ARTIFACTS:
        try:
            relative = artifact_relative(row, name)
        except ValueError:
            continue
        if asset(relative, optional=True) is not None:
            downloads[name] = f"/api/runs/{run_id}/{name}"
    for point in report.get("pareto", {}).get("frontier", []):
        for relative in point.get("artifacts", {}).values():
            asset(relative)
    semantics = {key: row.get(key) for key in ("status", "target", "target_met", "provenance")}
    manifest = {
        "schema": "headroom.repair-replay-curation.v1",
        "run_id": run_id,
        "source_run_directory": str(source),
        "api_directory": str(runs / "jobs" / run_id),
        "semantics": semantics,
        "verified_attempt_rounds": verified,
        "events_sha256": _digest(_encoded(events)),
        "llm_calls_sha256": _digest(_encoded(calls)),
        "rounds_sha256": _digest(_encoded(rounds)),
        "assets": {
            key: {"bytes": len(raw), "sha256": _digest(raw)} for key, raw in sorted(assets.items())
        },
        "api_downloads": downloads,
        "source_evidence": source_evidence,
        "notes": [
            "Existing records are curated, not re-executed or certified.",
            "Original absolute paths remain provenance metadata; API downloads use canonical safe paths.",
            "Failed/unknown verification and target states remain unchanged.",
        ],
    }
    manifest["fingerprint"] = _digest(_encoded(manifest))
    return row, payload, assets, manifest


def _write_new(path, raw):
    # Open outside the cleanup scope: an existing file is never ours to remove.
    handle = path.open("xb")
    try:
        with handle:
            os.chmod(path, 0o600)
            handle.write(raw)
    except BaseException as error:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            error.add_note("The newly created partial curation file could not be removed.")
        raise


def _mirror(runs, source, run_id, assets, manifest):
    """Publish a complete allowlisted tree; never overwrite an existing file."""
    destination = runs / "jobs" / run_id
    if destination.exists():
        _root(destination)
        for relative, raw in assets.items():
            _require(_read(runs, destination / relative) == raw, "DESTINATION_CONFLICT")
        manifest_path = destination / MANIFEST
        if manifest_path.exists():
            _require(_json(_read(runs, manifest_path)) == manifest, "DESTINATION_MANIFEST_CONFLICT")
            return None
        _require(source == destination, "DESTINATION_WITHOUT_CURATION_MANIFEST")
        _write_new(manifest_path, _encoded(manifest) + b"\n")
        return manifest_path
    jobs = runs / "jobs"
    if jobs.exists():
        _root(jobs)
    else:
        jobs.mkdir(mode=0o700)
    # Reserve an exclusive directory. Visibility is granted only after all
    # files are complete and the database transaction commits.
    destination.mkdir(mode=0o700)
    try:
        for relative, raw in assets.items():
            path = destination / relative
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            _write_new(path, raw)
        _write_new(destination / MANIFEST, _encoded(manifest) + b"\n")
        return destination
    except BaseException:
        shutil.rmtree(destination)
        raise


def curate_repair_replays(run_ids, *, project_root=PROJECT_ROOT, execute=False):
    """Dry-run by default. Execute touches only explicit IDs and approved display copies."""
    _require(type(execute) is bool, "EXECUTE_MUST_BE_BOOLEAN")
    _require(
        isinstance(run_ids, (list, tuple))
        and 1 <= len(run_ids) <= 16
        and all(isinstance(item, str) and RUN_ID.fullmatch(item) for item in run_ids)
        and len(set(run_ids)) == len(run_ids),
        "EXPLICIT_UNIQUE_RUN_IDS_REQUIRED",
    )
    project = _root(project_root)
    runs = _root(project / "runs")
    database = runs / "headroom.db"
    # No Store construction: even default-mode migrations or DB creation are forbidden.
    with open_regular(runs, "headroom.db", max_bytes=1024 * 1024 * 1024):
        pass
    connection = sqlite3.connect(
        database.as_uri() + ("?mode=rw" if execute else "?mode=ro"), uri=True, timeout=5
    )
    connection.row_factory = sqlite3.Row
    created = []
    try:
        connection.execute("BEGIN IMMEDIATE" if execute else "BEGIN")
        inspections = []
        results = []
        for run_id in run_ids:
            try:
                checked = _inspection(connection, runs, run_id)
                inspections.append(checked)
                results.append(
                    {
                        "run_id": run_id,
                        "eligible": True,
                        **checked[3]["semantics"],
                        "fingerprint": checked[3]["fingerprint"],
                        "verified_attempt_rounds": checked[3]["verified_attempt_rounds"],
                        "assets": checked[3]["assets"],
                        "api_downloads": checked[3]["api_downloads"],
                    }
                )
            except (CurationRefused, OSError, ValueError, TypeError, KeyError) as error:
                results.append(
                    {
                        "run_id": run_id,
                        "eligible": False,
                        "reason": str(error)
                        if isinstance(error, CurationRefused)
                        else type(error).__name__,
                    }
                )
        eligible = all(item["eligible"] for item in results)
        if execute and eligible:
            for row, payload, assets, manifest in inspections:
                owned = _mirror(runs, Path(row["run_dir"]), row["run_id"], assets, manifest)
                if owned is not None:
                    created.append(owned)
                existing = payload.get("repair_replay_curation")
                _require(
                    not payload.get("public_replay") or existing == manifest,
                    "EXISTING_CURATION_CONFLICT",
                )
                payload.update(public_replay=True, repair_replay_curation=manifest)
                connection.execute(
                    "UPDATE runs SET data_json=? WHERE id=?",
                    (_encoded(payload).decode(), row["run_id"]),
                )
            connection.commit()
        else:
            connection.rollback()
        return {
            "mode": "execute" if execute else "dry_run",
            "eligible": eligible,
            "executed": execute and eligible,
            "runs": results,
            "new_model_calls": 0,
            "new_gpu_runs": 0,
            "events_rewritten": False,
        }
    except BaseException as error:
        rolled_back = False
        try:
            if connection.in_transaction:
                connection.rollback()
                rolled_back = not connection.in_transaction
        except BaseException:  # noqa: BLE001 - preserve the original exception and uncertain assets
            error.add_note("Curation rollback could not be confirmed.")
        if rolled_back:
            for path in reversed(created):
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
        elif created:
            # A commit may have succeeded before an exception was delivered.
            # Retain the audit manifest and assets rather than break public links.
            error.add_note(
                "Curation assets were retained because commit or rollback outcome "
                "cannot be reversed safely; inspect the same explicit run IDs."
            )
        raise
    finally:
        connection.close()
