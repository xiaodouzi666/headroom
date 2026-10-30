"""Owner-scoped snapshot uploads and public diagnosis projections; no raw-input downloads."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from starlette.requests import ClientDisconnect

from headroom.api.public_access import client_address, judge_authorized
from headroom.api.security import RUN_ID
from headroom.api.snapshot_queue import (
    RETENTION_SECONDS,
    TERMINAL,
    SnapshotAdmissionError,
    SnapshotQueue,
    directory_fd,
)
from headroom.schemas import Diagnosis
from headroom.snapshot_intent import QUANTITY_PROVENANCE, QUANTITY_SOURCE

LIMITS = {"snapshot": 50 * 1024 * 1024, "traceback": 256 * 1024, "source": 1024 * 1024}
FILENAMES = {"snapshot": "snapshot.pickle", "traceback": "traceback.txt", "source": "source.py"}
MAX_BODY_BYTES = sum(LIMITS.values()) + 64 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
UPLOAD_TIMEOUT_SECONDS = 30.0
AUTHENTICATED_UPLOAD_TIMEOUT_SECONDS = 120.0
VERIFICATION = {"status": "not_run", "message": "Not run — bring the patch to your GPU"}
DOWNLOADS = {
    "diagnosis_json": ("diagnosis.json", "application/json"),
    "diagnosis_markdown": ("diagnosis.md", "text/plain; charset=utf-8"),
    "patch": ("patch.diff", "text/plain; charset=utf-8"),
}
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
STACK = re.compile(r"stk_(?:[a-f0-9]{16}|[a-f0-9]{64})\Z")
ERRORS = {
    "invalid_snapshot",
    "snapshot_input_rejected",
    "diagnosis_unavailable",
    "budget_exceeded",
    "runtime_unavailable",
    "worker_error",
    "timeout",
}


class UploadError(ValueError):
    def __init__(self, message="Invalid snapshot upload", status=400):
        super().__init__(message)
        self.status = status


class SnapshotMultipart:
    """Stream at most three named parts directly into the private owned directory."""

    def __init__(self, directory, content_type):
        from python_multipart import MultipartParser
        from python_multipart.multipart import parse_options_header

        if len(content_type) > 1024:
            raise UploadError("Multipart content type exceeds upload limit", 413)
        media, options = parse_options_header(content_type)
        boundary = options.get(b"boundary", b"")
        if media != b"multipart/form-data" or not 1 <= len(boundary) <= 200:
            raise UploadError("Use multipart/form-data with a snapshot file")
        self.directory = directory_fd(directory)
        self.parse_options_header = parse_options_header
        self.seen = set()
        self.handle = None
        self.field = None
        self.size = 0
        self.header_bytes = 0
        self.headers = {}
        self.header_name = bytearray()
        self.header_value_buffer = bytearray()
        self.ended = False
        callbacks = {
            "on_part_begin": self.part_begin,
            "on_header_field": self.header_field,
            "on_header_value": self.header_value,
            "on_header_end": self.header_end,
            "on_headers_finished": self.headers_finished,
            "on_part_data": self.part_data,
            "on_part_end": self.part_end,
            "on_end": self.end,
        }
        self.parser = MultipartParser(boundary, callbacks, max_size=MAX_BODY_BYTES)

    def part_begin(self):
        if len(self.seen) >= 3 or self.handle is not None:
            raise UploadError("At most three upload fields are allowed")
        self.headers = {}
        self.header_name = bytearray()
        self.header_value_buffer = bytearray()
        self.header_bytes = 0
        self.field = None
        self.size = 0

    def _header(self, destination, data, start, end):
        self.header_bytes += end - start
        if self.header_bytes > 8192:
            raise UploadError("Multipart headers exceed upload limit", 413)
        destination.extend(data[start:end])

    def header_field(self, data, start, end):
        self._header(self.header_name, data, start, end)

    def header_value(self, data, start, end):
        self._header(self.header_value_buffer, data, start, end)

    def header_end(self):
        name = bytes(self.header_name).lower()
        if name in self.headers or name not in {b"content-disposition", b"content-type"}:
            raise UploadError("Unsupported or duplicate multipart header")
        self.headers[name] = bytes(self.header_value_buffer)
        self.header_name.clear()
        self.header_value_buffer.clear()

    def headers_finished(self):
        media, options = self.parse_options_header(self.headers.get(b"content-disposition", b""))
        name = options.get(b"name", b"")
        if media != b"form-data" or name not in {b"snapshot", b"traceback", b"source"}:
            raise UploadError("Only snapshot, traceback and source fields are accepted")
        self.field = name.decode("ascii")
        if self.field in self.seen:
            raise UploadError("Duplicate upload field")
        self.seen.add(self.field)
        # Browser filenames and MIME types are not trusted filesystem locations.
        descriptor = os.open(
            FILENAMES[self.field],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.directory,
        )
        self.handle = os.fdopen(descriptor, "wb")

    def part_data(self, data, start, end):
        if self.handle is None:
            raise UploadError()
        self.size += end - start
        if self.size > LIMITS[self.field]:
            raise UploadError(f"{self.field} exceeds upload limit", 413)
        self.handle.write(data[start:end])

    def part_end(self):
        if self.handle is None or self.size == 0:
            raise UploadError("Upload parts must not be empty")
        self.handle.close()
        self.handle = None
        if self.field != "snapshot":
            descriptor = os.open(
                FILENAMES[self.field], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.directory
            )
            with os.fdopen(descriptor, "rb") as stream:
                try:
                    stream.read(LIMITS[self.field] + 1).decode("utf-8")
                except UnicodeError:
                    raise UploadError("Traceback and source must be UTF-8 text") from None

    def end(self):
        self.ended = True

    def write(self, chunk):
        if self.ended and chunk.strip():
            raise UploadError("Trailing multipart data is not accepted")
        self.parser.write(chunk)

    def finish(self):
        self.parser.finalize()
        if not self.ended or self.handle is not None or "snapshot" not in self.seen:
            raise UploadError("A complete snapshot part is required")

    def close(self):
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        os.close(self.directory)


def _read_report(root, identifier):
    descriptor = directory_fd(Path(root) / identifier)
    try:
        handle = os.open(
            "public-report.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        with os.fdopen(handle, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_REPORT_BYTES:
                raise ValueError("Invalid public report")
            raw = stream.read(MAX_REPORT_BYTES + 1)
            if len(raw) > MAX_REPORT_BYTES:
                raise ValueError("Public report grew beyond its limit")
            return raw
    finally:
        os.close(descriptor)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate public field")
        result[key] = value
    return result


def _text(value, maximum=8000, *, allow_source_paths=False):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("Invalid public text")
    # Metadata must be redacted before binding; owner-only source diffs retain
    # literal data paths so the downloadable draft is not silently rewritten.
    secret = re.search(r"(?:sk-[A-Za-z0-9_-]{20,}|tvly-[A-Za-z0-9_-]{12,}|Bearer\s+\S+)", value)
    private_path = not allow_source_paths and re.search(
        r"/(?:home|Users|tmp|var|root|mnt|workspace|etc)/|[A-Za-z]:\\", value
    )
    if secret or private_path:
        raise ValueError("Private text is not publishable")
    return value


def _validate_text_tree(value):
    if isinstance(value, str):
        _text(value)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise ValueError("Public list exceeds limit")
        for item in value:
            _validate_text_tree(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _text(key, 160)
            _validate_text_tree(item)


def _count(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid public byte count")
    return value


def _evidence(value, diagnosis):
    if (
        not isinstance(value, dict)
        or set(value) != {"source", "snapshot_sha256", "analysis", "stacks", "diagnosis_binding"}
        or value["source"] != "uploaded_snapshot"
    ):
        raise ValueError("Invalid snapshot evidence")
    sha = value["snapshot_sha256"]
    binding = value["diagnosis_binding"]
    if not isinstance(sha, str) or not DIGEST.fullmatch(sha):
        raise ValueError("Invalid snapshot fingerprint")
    if diagnosis is None and binding is None:
        pass
    else:
        if (
            not isinstance(binding, dict)
            or set(binding)
            not in (
                {"snapshot_sha256", "evidence_json_sha256", "diagnosis_sha256"},
                {"snapshot_sha256", "evidence_json_sha256", "diagnosis_sha256", "quantity_source"},
            )
            or any(
                not isinstance(binding.get(key), str) or not DIGEST.fullmatch(binding[key])
                for key in ("snapshot_sha256", "evidence_json_sha256", "diagnosis_sha256")
            )
            or ("quantity_source" in binding and binding["quantity_source"] != QUANTITY_SOURCE)
            or binding["snapshot_sha256"] != sha
        ):
            raise ValueError("Invalid evidence binding")
        diagnostic_sha = hashlib.sha256(
            json.dumps(
                diagnosis,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        if binding["diagnosis_sha256"] != diagnostic_sha:
            raise ValueError("Diagnosis does not match bound evidence")
    analysis = value["analysis"]
    if not isinstance(analysis, dict) or set(analysis) != {
        "peak_allocated_bytes",
        "peak_is_exact",
        "category_bytes",
        "warnings",
    }:
        raise ValueError("Invalid evidence analysis")
    if analysis["peak_allocated_bytes"] is not None:
        _count(analysis["peak_allocated_bytes"])
    if type(analysis["peak_is_exact"]) is not bool:
        raise ValueError("Invalid peak certainty")
    categories = analysis["category_bytes"]
    if not isinstance(categories, dict) or len(categories) > 50:
        raise ValueError("Invalid peak categories")
    for name, count in categories.items():
        _text(name, 100)
        if count is not None:
            _count(count)
    if not isinstance(analysis["warnings"], list) or len(analysis["warnings"]) > 100:
        raise ValueError("Invalid analysis warnings")
    for warning in analysis["warnings"]:
        _text(warning)
    stacks = value["stacks"]
    if not isinstance(stacks, list) or len(stacks) > 200:
        raise ValueError("Invalid evidence stacks")
    ids = set()
    for item in stacks:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "peak_live_bytes", "lifetime_allocated_bytes", "frames"}
            or not isinstance(item["id"], str)
            or not STACK.fullmatch(item["id"])
        ):
            raise ValueError("Invalid evidence stack")
        if item["id"] in ids:
            raise ValueError("Duplicate evidence stack")
        ids.add(item["id"])
        for name in ("peak_live_bytes", "lifetime_allocated_bytes"):
            if item[name] is not None:
                _count(item[name])
        frames = item["frames"]
        if not isinstance(frames, list) or not 0 <= len(frames) <= 512:
            raise ValueError("Invalid stack frames")
        for frame in frames:
            if not isinstance(frame, dict) or set(frame) != {"filename", "name", "line"}:
                raise ValueError("Invalid stack frame")
            _text(frame["filename"], 2048)
            _text(frame["name"], 2048)
            if frame["line"] is not None:
                _count(frame["line"])
    if diagnosis:
        refs = {ref for cause in diagnosis["root_causes"] for ref in cause["evidence_refs"]}
        if not refs <= ids:
            raise ValueError("Unresolved diagnostic evidence")
    return value


def public_result(raw, *, identifier=None, status=None):
    value = json.loads(
        raw,
        object_pairs_hook=_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite public number")),
    )
    if isinstance(value, dict) and ("run_id" in value or "status" in value):
        report_id, report_status = value.get("run_id"), value.get("status")
        if (
            not isinstance(report_id, str)
            or not RUN_ID.fullmatch(report_id)
            or report_status not in TERMINAL
            or (identifier is not None and report_id != identifier)
            or (status is not None and report_status != status)
        ):
            raise ValueError("Public report job identity does not match")
        value = {key: item for key, item in value.items() if key not in {"run_id", "status"}}
    if (
        not isinstance(value, dict)
        or set(value)
        != {
            "kind",
            "provenance",
            "verification",
            "diagnosis",
            "evidence",
            "patch",
            "cost_usd",
            "error",
        }
        or value["kind"] != "snapshot_diagnosis"
        or value["verification"] != VERIFICATION
        or value["provenance"] not in {"live_model", "offline_fixture"}
    ):
        raise ValueError("Invalid public snapshot report")
    diagnosis = value["diagnosis"]
    if diagnosis is not None:
        Diagnosis.model_validate(diagnosis)
        _validate_text_tree(diagnosis)
    if value["evidence"] is not None:
        _evidence(value["evidence"], diagnosis)
    elif diagnosis is not None:
        raise ValueError("Diagnosis is missing evidence binding")
    patch = value["patch"]
    if (
        not isinstance(patch, dict)
        or set(patch) != {"status", "diff"}
        or patch["status"] not in {"unverified", "unavailable"}
        or (patch["status"] == "unavailable" and patch["diff"] is not None)
        or (patch["status"] == "unverified" and not isinstance(patch["diff"], str))
    ):
        raise ValueError("Invalid unverified patch")
    if patch["diff"] is not None:
        _text(patch["diff"], 1024 * 1024, allow_source_paths=True)
        if not patch["diff"].strip():
            raise ValueError("Empty patch is unavailable")
    cost = value["cost_usd"]
    if cost is not None and (
        type(cost) not in {int, float} or not math.isfinite(cost) or not 0 <= cost <= 100
    ):
        raise ValueError("Invalid diagnosis cost")
    if value["error"] is not None and value["error"] not in ERRORS:
        raise ValueError("Invalid diagnosis error")
    return value


def _markdown(result):
    lines = ["# Snapshot diagnosis", "", VERIFICATION["message"], ""]
    diagnosis = result["diagnosis"]
    if diagnosis:
        binding = (result.get("evidence") or {}).get("diagnosis_binding") or {}
        if binding.get("quantity_source") == QUANTITY_SOURCE:
            lines += [QUANTITY_PROVENANCE, ""]
        lines += ["## Root causes", ""]
        for cause in diagnosis["root_causes"]:
            lines += [
                f"- {cause['title']} ({cause['category']}); evidence: "
                + ", ".join(cause["evidence_refs"])
            ]
        lines += ["", "## Suggested plan", ""]
        for step in diagnosis["plan"]:
            lines += [f"- {step['title']}: {step['description']}"]
        lines += ["", *diagnosis["notes"]]
    if result["provenance"] == "offline_fixture":
        lines += ["", "Offline test fixture — no live model diagnosis."]
    if result["error"]:
        lines += ["", "Diagnosis could not be completed: " + result["error"]]
    if result["patch"]["status"] == "unverified":
        lines += ["", "A suggested patch is available. It has not been run on hardware."]
    return ("\n".join(lines) + "\n").encode()


def register_snapshot_routes(
    app, settings, *, worker=None, allocation_parent=None, public_allocation=None
):
    manager = SnapshotQueue(
        settings,
        worker=worker,
        allocation_parent=allocation_parent,
        public_allocation=public_allocation,
    )

    def owner(request):
        value = getattr(request.state, "owner", None)
        if not isinstance(value, str) or not DIGEST.fullmatch(value):
            raise HTTPException(401, "A browser session is required")
        return value

    def accessible(identifier, request):
        row = manager.row_for_owner(identifier, owner(request))
        if row is None:
            raise HTTPException(404, "Snapshot diagnosis not found")
        return row

    def result_for(row):
        if row["status"] not in TERMINAL:
            return None
        try:
            return public_result(
                _read_report(manager.root, row["id"]), identifier=row["id"], status=row["status"]
            )
        except (OSError, ValueError, TypeError, RecursionError, ValidationError):
            return None

    def artifacts(identifier, result):
        if result is None:
            return {}
        kinds = ["diagnosis_json", "diagnosis_markdown"]
        if result["patch"]["status"] == "unverified":
            kinds.append("patch")
        return {kind: {"url": f"/api/snapshots/{identifier}/download/{kind}"} for kind in kinds}

    async def reserve_upload(request_owner, ip, judge):
        # The storage census runs off the event loop. Cancellation must still
        # account for an admission that the thread may have just persisted.
        task = asyncio.create_task(
            asyncio.to_thread(manager.reserve, request_owner, ip, judge=judge)
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except (SnapshotAdmissionError, OSError, ValueError):
                    break
            if not task.cancelled() and task.exception() is None:
                identifier, _created = task.result()
                manager.fail_upload(identifier)
            raise

    @app.post("/api/snapshots", status_code=202)
    async def submit_snapshot(request: Request):
        # Both gates precede body access, admission, file creation and dispatch.
        if (
            not getattr(settings, "snapshot_submissions_enabled", False)
            or not settings.run_submissions_enabled
        ):
            raise HTTPException(503, "Snapshot analysis is temporarily paused.")
        judge = judge_authorized(settings, request)
        if settings.public_host and not judge:
            raise HTTPException(401, "A valid judge token is required for snapshot uploads")
        request_owner = owner(request)
        origin = request.headers.get("origin")
        if origin:
            try:
                same_origin = urlsplit(origin).netloc == request.url.netloc
            except ValueError:
                same_origin = False
            if not same_origin:
                raise HTTPException(403, "Cross-origin submissions are not allowed")
        ip = client_address(settings, request)
        length = request.headers.get("content-length")
        if length is not None:
            try:
                if not 0 < int(length) <= MAX_BODY_BYTES:
                    raise ValueError
            except ValueError:
                raise HTTPException(413, "Request exceeds upload limit") from None
        try:
            identifier, created = await reserve_upload(request_owner, ip, judge)
        except SnapshotAdmissionError as error:
            raise HTTPException(error.status, str(error), headers={"Retry-After": "60"}) from None
        parser = None
        try:
            parser = SnapshotMultipart(
                manager.root / identifier, request.headers.get("content-type", "")
            )
            total = 0
            upload_timeout = (
                AUTHENTICATED_UPLOAD_TIMEOUT_SECONDS if judge else UPLOAD_TIMEOUT_SECONDS
            )
            remaining = min(upload_timeout, created + manager.deadline - manager.clock())
            async with asyncio.timeout(max(0, remaining)):
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > MAX_BODY_BYTES:
                        raise UploadError("Request exceeds upload limit", 413)
                    parser.write(chunk)
                parser.finish()
            position = manager.finish_upload(identifier)
        except TimeoutError:
            manager.fail_upload(identifier, timeout=True)
            raise HTTPException(408, "Snapshot upload deadline exceeded") from None
        except SnapshotAdmissionError as error:
            manager.fail_upload(identifier)
            raise HTTPException(error.status, str(error)) from None
        except UploadError as error:
            manager.fail_upload(identifier)
            raise HTTPException(error.status, str(error)) from None
        except (OSError, ValueError, ClientDisconnect):
            manager.fail_upload(identifier)
            raise HTTPException(400, "Invalid snapshot upload") from None
        except asyncio.CancelledError:
            manager.fail_upload(identifier)
            raise
        finally:
            if parser:
                parser.close()
        return {
            "run_id": identifier,
            "status": "queued",
            "queue_position": position,
            "run_url": f"/api/snapshots/{identifier}",
        }

    @app.get("/api/snapshots/{identifier}")
    def snapshot_status(identifier: str, request: Request):
        row = accessible(identifier, request)
        result = result_for(row)
        return {
            "run_id": identifier,
            "status": row["status"],
            "created_at": datetime.fromtimestamp(row["created_at"], UTC).isoformat(),
            "expires_at": datetime.fromtimestamp(
                row["created_at"] + RETENTION_SECONDS, UTC
            ).isoformat(),
            "result": result,
            "artifacts": artifacts(identifier, result),
        }

    @app.get("/api/snapshots/{identifier}/download/{kind}")
    def snapshot_download(identifier: str, kind: str, request: Request):
        row = accessible(identifier, request)
        if kind not in DOWNLOADS:
            raise HTTPException(404, "Diagnosis artifact not found")
        result = result_for(row)
        if result is None or kind not in artifacts(identifier, result):
            raise HTTPException(404, "Diagnosis artifact unavailable")
        filename, media = DOWNLOADS[kind]
        if kind == "diagnosis_json":
            raw = (
                json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
            ).encode()
        elif kind == "diagnosis_markdown":
            raw = _markdown(result)
        else:
            raw = result["patch"]["diff"].encode()
        return Response(
            raw,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{identifier}-{filename}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    return manager
