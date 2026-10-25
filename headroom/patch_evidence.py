"""Private bounded evidence for patch-model responses; never executable input."""

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

MAX_RESPONSE_ARTIFACT_BYTES = 256 * 1024


def _text(value):
    return value[:256] if isinstance(value, str) else None


def _content(value):
    if not isinstance(value, str):
        return None
    raw = value.encode("utf-8")
    return {
        "text": value,
        "utf8_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "truncated": False,
    }


def _protocol(record):
    return {
        "role": _text(record.role),
        "model": _text(record.model),
        "response_model": _text(record.response_model),
        "attempt": record.attempt,
        "outcome": _text(record.outcome),
        "http_status": record.http_status,
        "usage": asdict(record.usage) if record.usage is not None else None,
        "cost": record.cost.as_dict(),
        "elapsed_seconds": record.elapsed_seconds,
    }


def _directory_fd(path):
    """Pin each absolute directory without following any ancestor symlink."""
    path = Path(path).absolute()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if part in {".", ".."}:
                raise ValueError("Invalid private artifact directory")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
            raise ValueError("Private response directory must have mode 0700")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _publish(path, payload):
    """Atomic exclusive publication, private from creation; no existing file overwritten."""
    path = Path(path)
    if not re.fullmatch(r"attempt-[1-4]-response\.json", path.name):
        raise ValueError("Invalid response artifact name")
    fd = _directory_fd(path.parent)
    temporary = "." + path.name + "." + uuid4().hex + ".tmp"
    owned = False
    try:
        output = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        owned = True
        with os.fdopen(output, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path.name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
    finally:
        try:
            if owned:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)


def save_patch_response(
    path,
    response=None,
    *,
    error=None,
    records=(),
    normalized_proposal=None,
    normalization_metadata=None,
    wire_schema=None,
):
    """Persist visible output verbatim or bounded prefixes, not hidden reasoning/requests."""
    records = tuple(records)
    parsed = getattr(response, "parsed", None)
    parsed_raw = (
        json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode()
        if parsed is not None
        else None
    )
    normalized_raw = (
        json.dumps(normalized_proposal, ensure_ascii=False, allow_nan=False).encode()
        if normalized_proposal is not None
        else None
    )
    normalized_diff = (
        normalized_proposal.get("diff") if isinstance(normalized_proposal, dict) else None
    )
    if normalization_metadata is not None:
        metadata_raw = json.dumps(normalization_metadata, allow_nan=False).encode()
        if len(metadata_raw) > 64 * 1024:
            raise ValueError("Patch normalization metadata exceeds its evidence bound")
    anchored = isinstance(parsed, dict) and "edits" in parsed
    schema = wire_schema or (normalization_metadata or {}).get("schema")
    span_wire = schema == "source_span_edits_v1"
    record = {
        "schema_version": 4 if span_wire else 3,
        "wire_schema": schema,
        "content_is_untrusted_data": True,
        "response_available": response is not None,
        "visible": _content(response.text) if response is not None else None,
        "parsed": parsed,
        "parsed_utf8_bytes": len(parsed_raw) if parsed_raw is not None else None,
        "parsed_sha256": hashlib.sha256(parsed_raw).hexdigest() if parsed_raw is not None else None,
        "parsed_omitted": False,
        "diff": _content(parsed.get("diff")) if isinstance(parsed, dict) else None,
        "normalized_proposal": normalized_proposal,
        "normalized_proposal_utf8_bytes": len(normalized_raw)
        if normalized_raw is not None
        else None,
        "normalized_proposal_sha256": (
            hashlib.sha256(normalized_raw).hexdigest() if normalized_raw is not None else None
        ),
        "normalized_proposal_omitted": False,
        "normalized_diff": _content(normalized_diff),
        "normalization": {
            "status": "applied" if normalized_proposal is not None else "not_applied",
            "algorithm": (
                "source_span_lines_v1"
                if span_wire
                else "source_anchored_lines_v1"
                if anchored
                else "diff_lines_join_lf_v1"
            )
            if normalized_proposal is not None
            else None,
            "source_field": ("edits" if anchored else "diff_lines")
            if normalized_proposal is not None
            else None,
            "source_binding": normalization_metadata,
            "source_parsed_sha256": (
                hashlib.sha256(parsed_raw).hexdigest() if parsed_raw is not None else None
            ),
            "line_count": (
                (normalized_diff.count("\n") if anchored else len(parsed["diff_lines"]))
                if normalized_proposal is not None and isinstance(parsed, dict)
                else None
            ),
            "terminal_lf": bool(normalized_diff) if normalized_proposal is not None else None,
            "output_proposal_sha256": (
                hashlib.sha256(normalized_raw).hexdigest() if normalized_raw is not None else None
            ),
            "output_diff_sha256": (
                hashlib.sha256(normalized_diff.encode()).hexdigest()
                if isinstance(normalized_diff, str)
                else None
            ),
        },
        "model": _text(response.model) if response is not None else None,
        "response_model": _text(response.response_model) if response is not None else None,
        "finish_reason": _text(response.finish_reason) if response is not None else None,
        "usage": asdict(response.usage) if response is not None and response.usage else None,
        "cost": response.cost.as_dict() if response is not None else None,
        "validation": "failed" if error is not None else "schema_passed",
        "error_type": type(error).__name__ if error is not None else None,
        "validation_reason": _text(getattr(error, "reason", None)),
        "protocol_records": [_protocol(item) for item in records[:6]],
        "protocol_record_count": len(records),
        "protocol_records_omitted": max(0, len(records) - 6),
        "financial_status_authority": "Store and BudgetLedger; protocol records do not assert settlement",
    }

    def encoded():
        return (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()

    if len(encoded()) > MAX_RESPONSE_ARTIFACT_BYTES:
        record["parsed_omitted"] = parsed is not None
        record["parsed"] = None
        record["normalized_proposal_omitted"] = normalized_proposal is not None
        record["normalized_proposal"] = None
    if len(encoded()) > MAX_RESPONSE_ARTIFACT_BYTES:
        for key in ("visible", "diff", "normalized_diff"):
            blob = record[key]
            if blob is not None:
                blob["text"] = ""
                blob["truncated"] = blob["utf8_bytes"] != 0
        if len(encoded()) > MAX_RESPONSE_ARTIFACT_BYTES:
            raise ValueError("Patch response metadata exceeds private artifact limit")
        # Each prefix retains its own full hash and explicit wire/normalized origin.
        for key, value in (
            ("normalized_diff", normalized_diff),
            ("diff", parsed.get("diff") if isinstance(parsed, dict) else None),
            ("visible", response.text if response is not None else None),
        ):
            blob = record[key]
            if blob is None:
                continue
            raw = value.encode("utf-8")
            low, high = 0, min(len(raw), MAX_RESPONSE_ARTIFACT_BYTES // 4)
            while low < high:
                middle = (low + high + 1) // 2
                blob["text"] = raw[:middle].decode("utf-8", errors="ignore")
                if len(encoded()) <= MAX_RESPONSE_ARTIFACT_BYTES:
                    low = middle
                else:
                    high = middle - 1
            blob["text"] = raw[:low].decode("utf-8", errors="ignore")
            blob["truncated"] = len(blob["text"].encode()) < len(raw)
    payload = encoded()
    if len(payload) > MAX_RESPONSE_ARTIFACT_BYTES:
        raise ValueError("Patch response exceeds private artifact limit")
    _publish(path, payload)
    return str(path)
