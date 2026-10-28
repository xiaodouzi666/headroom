"""Read a bounded initial-diagnosis/evidence binding, without routes or model access."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from headroom.api.security import RUN_ID, artifact_relative, open_regular
from headroom.api.verified import Diagnosis, DiagnosisBinding, EvidenceStack

MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_CALLS = 16


def _read(root, relative, limit):
    with open_regular(root, relative, max_bytes=limit) as handle:
        return handle.read()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _clean(value, project):
    value = str(value).replace(str(project), "<project>")
    value = re.sub(r"/(?:home|Users)/[^/\s]+", "<user>", value)
    if re.search(r"(?:sk-[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{12,}|Bearer\s+\S+)", value):
        raise ValueError("Credential-like content")
    return value


def _load(run_dir, database, project):
    run_dir, database, project = (Path(p).absolute() for p in (run_dir, database, project))
    if (
        any(".." in path.parts for path in (run_dir, database, project))
        or not RUN_ID.fullmatch(run_dir.name)
        or not run_dir.is_relative_to(project / "runs")
        or not database.is_relative_to(project / "runs")
        or any(p.is_symlink() for p in [run_dir, *run_dir.parents, database, *database.parents])
    ):
        return None
    # Prove a bounded regular DB file without creating it or migrating its schema.
    with open_regular(database.parent, database.name, max_bytes=1024 * 1024 * 1024):
        pass
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT json_extract(data_json,'$.run_dir') AS run_dir, "
            "json_extract(data_json,'$.provenance') AS provenance, "
            "json_extract(data_json,'$.before_evidence_paths') AS paths FROM runs WHERE id=?",
            (run_dir.name,),
        ).fetchone()
        if not row or row["run_dir"] != str(run_dir) or row["provenance"] != "live":
            return None
        paths = json.loads(row["paths"])
        locators = {"before_evidence_paths": paths}
        markdown_raw = _read(run_dir, artifact_relative(locators, "evidence.md"), 2 * 1024 * 1024)
        evidence_raw = _read(
            run_dir, artifact_relative(locators, "evidence.json"), 16 * 1024 * 1024
        )
        diagnosis_raw = _read(run_dir, "rounds/01/diagnosis.json", 1024 * 1024)
        diagnostic = json.loads(diagnosis_raw)
        if diagnostic.get("valid") is not True:
            return None
        analysis = json.loads(evidence_raw)["analysis"]
        markdown = markdown_raw.decode()
        event = db.execute(
            "SELECT created_at FROM events WHERE run_id=? AND kind='diagnose.done' "
            "AND json_extract(data_json,'$.round')=1 ORDER BY sequence DESC LIMIT 1",
            (run_dir.name,),
        ).fetchone()
        if not event:
            return None
        calls = db.execute(
            "SELECT length(CAST(data_json AS BLOB)) AS size, "
            "CASE WHEN length(CAST(data_json AS BLOB))<=? THEN data_json END AS payload "
            "FROM llm_calls WHERE run_id=? AND role='diagnose' AND created_at<=? "
            "ORDER BY id LIMIT ?",
            (MAX_RECORD_BYTES, run_dir.name, event["created_at"], MAX_CALLS + 1),
        ).fetchall()
        if len(calls) > MAX_CALLS or sum(r["size"] for r in calls) > MAX_REQUEST_BYTES:
            return None
        match = None
        for record in calls:
            if record["payload"] is None:
                return None
            call = json.loads(record["payload"])
            if call.get("outcome") != "response" or call.get("http_status") != 200:
                continue
            if call.get("model") != call.get("response_model") or not str(
                call.get("model", "")
            ).startswith("nvidia/"):
                continue
            capture = call.get("request_evidence", {})
            if capture.get("capture_point") != "httpx_pre_transport":
                continue
            payload = capture.get("payload", {})
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            if _sha(encoded) != capture.get("stored_payload_sha256"):
                continue
            for message in payload.get("messages", []):
                if message.get("role") != "user":
                    continue
                request = json.loads(message["content"])
                evidence = request.get("evidence_markdown", "")
                if not evidence.startswith(markdown):
                    continue
                suffix = evidence[len(markdown) :].strip()
                marker = "SEARCH STATE (trusted orchestration metadata):"
                if suffix.startswith(marker):
                    search = json.loads(suffix[len(marker) :])
                    if (
                        search.get("round") != 1
                        or search.get("previous_rounds") != []
                        or search.get("current_kept") is not None
                    ):
                        continue
                elif suffix:
                    continue
                match = capture
        if match is None:
            return None
    diagnosis = diagnostic["diagnosis"]

    def clean(value):
        return _clean(value, project)

    causes = [
        {
            k: clean(c[k]) if k in {"title", "category"} else c[k]
            for k in ["title", "category", "confidence", "evidence_refs"]
        }
        for c in diagnosis["root_causes"]
    ]
    refs = sorted({ref for cause in causes for ref in cause["evidence_refs"]})
    peak = {s["stack_id"]: s for s in analysis["peak_composition"]}
    hot = {s["stack_id"]: s for s in analysis["allocation_hot_paths"]}
    stacks = []
    for ref in refs:
        frames = analysis["stack_catalog"].get(ref)
        if not frames or (ref not in peak and ref not in hot):
            return None
        signature = json.dumps(frames, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if ref != "stk_" + _sha(signature.encode())[:16]:
            return None
        peak_row, hot_row = peak.get(ref), hot.get(ref)
        peak_bytes = hot_bytes = None
        if peak_row:
            fragment = (
                f"### {ref} — {peak_row.get('category', 'unknown')}\n\n"
                f"Bytes: {peak_row['bytes']}; live blocks: {peak_row.get('blocks', 'unknown')}"
            )
            if fragment not in markdown:
                return None
            peak_bytes = peak_row["bytes"]
        if hot_row:
            fragment = (
                f"### {ref}\n\nCumulative bytes: {hot_row['bytes']}; "
                f"allocations: {hot_row.get('allocations', 'unknown')}; "
                f"short-lived bytes: {hot_row.get('short_lived_bytes', 'unknown')}"
            )
            if fragment not in markdown:
                return None
            hot_bytes = hot_row["bytes"]
        stack = EvidenceStack.model_validate(
            {
                "id": ref,
                "peak_live_bytes": peak_bytes,
                "lifetime_allocated_bytes": hot_bytes,
                "frames": [
                    {
                        "filename": clean(f.get("filename", "")),
                        "name": clean(f.get("name", "")),
                        "line": f.get("line", 0),
                    }
                    for f in frames
                ],
            }
        )
        stacks.append(stack.model_dump())
    public_diagnosis = Diagnosis.model_validate(
        {
            "root_causes": causes,
            "needs_more_info": diagnosis["needs_more_info"],
            "notes": [clean(x) for x in diagnosis.get("notes", [])],
        }
    )
    binding = DiagnosisBinding.model_validate(
        {
            "round": 1,
            "stage": "baseline",
            "evidence_json_sha256": _sha(evidence_raw),
            "evidence_markdown_sha256": _sha(markdown_raw),
            "diagnosis_sha256": _sha(diagnosis_raw),
            "request_payload_sha256": match["stored_payload_sha256"],
            "request_wire_sha256": match["wire_body_sha256"],
        }
    )
    return {
        "diagnosis": public_diagnosis.model_dump(),
        "diagnosis_binding": binding.model_dump(),
        "stacks": stacks,
    }


def load_initial_diagnosis(run_dir, *, database, project_root):
    """Return bound initial diagnosis/stacks or None; never substitute a later diagnosis.

    The caller must authorize access to the run before calling. Reads three fixed
    artifacts (19 MiB maximum) and at most 16 captured calls (2 MiB each, 8 MiB total).
    No recursive directory reads, source execution, writes, or API calls occur.
    """
    try:
        return _load(run_dir, database, project_root)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        sqlite3.Error,
        ValidationError,
        RecursionError,
    ):
        return None
