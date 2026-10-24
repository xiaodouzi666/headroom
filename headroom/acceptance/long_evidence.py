"""One-capture, position-addressed allocator evidence for the separate T1.3 gate."""

import hashlib
import json
from pathlib import Path, PurePosixPath

from headroom.acceptance.common import file_record, read_bytes, read_json, write_json
from headroom.evidence import MAX_SNAPSHOT_BYTES, _tokens, build_evidence
from headroom.lab.runner import selected_capture_directory

MIN_EVIDENCE_TOKENS = 200_000
LOCAL_TARGET_TOKENS = 220_000
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_METADATA_BYTES = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def safe_directory(path):
    path = Path(path).absolute()
    if any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Credential paths are not capture artifacts")
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError("Capture directory symlinks are unsupported")
    if not path.is_dir():
        raise ValueError("Capture directory is unavailable")
    return path


def safe_relative(value):
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {".", ".."} or part.lower().startswith(".env") for part in path.parts)
    ):
        raise ValueError("Artifact must stay within its package")
    return str(path)


def capture_inputs(capture):
    root = safe_directory(capture)
    result = read_json(root / "result.json", MAX_METADATA_BYTES)
    manifest = read_json(root / "manifest.json", MAX_METADATA_BYTES)
    if (
        result.get("status") not in {"oom", "completed"}
        or result.get("capture_complete") is not True
        or result.get("cleanup_verified") is not True
        or result.get("env", {}).get("device") != "cuda"
        or manifest.get("device") != "cuda"
    ):
        raise ValueError("Complete preserved CUDA capture and verified cleanup required")
    artifacts = selected_capture_directory(root, result, manifest)
    pins = {}
    for name in ("result.json", "manifest.json"):
        pins[name] = file_record(root / name, MAX_METADATA_BYTES)
    files = manifest.get("source", {}).get("files", {})
    if not isinstance(files, dict) or not files:
        raise ValueError("Captured source hashes are required")
    for name, expected in files.items():
        relative = safe_relative(name)
        record = file_record(root / "source" / relative, 1024 * 1024)
        if record["sha256"] != expected.get("sha256"):
            raise ValueError("Captured source hash mismatch")
        pins["source/" + relative] = record
    snapshot = artifacts / "snapshot.json"
    pins[str(snapshot.relative_to(root))] = file_record(snapshot, MAX_SNAPSHOT_BYTES)
    selected_result = artifacts / "result.json"
    raw = read_json(selected_result, MAX_METADATA_BYTES)
    if raw.get("capture_complete") is not True:
        raise ValueError("Selected raw capture is incomplete")
    for key, value in raw.items():
        if key not in {"status", "reason", "shared_gpu"} and result.get(key) != value:
            raise ValueError("Selected raw capture does not match the host result")
    pins[str(selected_result.relative_to(root))] = file_record(selected_result, MAX_METADATA_BYTES)
    return root, snapshot, pins


def _records(snapshot):
    traces = snapshot.get("device_traces", [])
    if not isinstance(traces, list):
        raise TypeError("Allocator traces must be an array")
    for device, events in enumerate(traces):
        if not isinstance(events, list):
            raise TypeError("Allocator device trace must be an array")
        for index, event in enumerate(events):
            if isinstance(event, dict) and event.get("action") in {
                "alloc",
                "free_requested",
                "free_completed",
                "segment_alloc",
                "segment_free",
                "oom",
                "snapshot",
            }:
                yield f"/device_traces/{device}/{index}", event
    # Terminal blocks are a different source domain; never repeat a full segment
    # and its nested blocks, or synthesize events to hit a length threshold.
    segments = snapshot.get("segments", [])
    if not isinstance(segments, list):
        raise TypeError("Allocator segments must be an array")
    for index, segment in enumerate(segments):
        if isinstance(segment, dict):
            yield f"/segments/{index}", segment


def prepare_long_evidence(capture, output_dir):
    """No runtime/profile/key access. All token counts are local estimates."""
    root, snapshot_path, pins = capture_inputs(capture)
    output = Path(output_dir).absolute()
    if output == root or output.is_relative_to(root):
        raise ValueError("Preparation must not modify its original capture")
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    # C4 remains governed by its existing 150k budget; this additional package is
    # exclusively the original T1.3 long-input acceptance, never a repair prompt.
    summary = build_evidence(root, budget=150000, output_dir=output / "c4")
    summary_bytes = read_bytes(Path(summary["evidence_md"]), MAX_PACKAGE_BYTES)
    summary_text = summary_bytes.decode("utf-8")
    snapshot = read_json(snapshot_path, MAX_SNAPSHOT_BYTES)
    if not isinstance(snapshot, dict):
        raise TypeError("CUDA snapshot must be an object")
    content_parts, displayed, index_rows, seen = [summary_text], [summary_text], [], set()
    estimate = _tokens(summary_text)
    content_bytes = len(summary_bytes)
    omitted_duplicates = 0
    next_full_check = LOCAL_TARGET_TOKENS
    for pointer, value in _records(snapshot):
        raw = canonical(value)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        if digest in seen:
            omitted_duplicates += 1
            continue
        seen.add(digest)
        part = "\n\n" + raw
        header = f"\n\nAllocator source snapshot.json#{pointer}; canonical_sha256={digest}\n"
        if content_bytes + len((header + raw).encode()) > MAX_PACKAGE_BYTES - 65536:
            break
        content_parts.append(part)
        displayed.append(header + raw)
        content_bytes += len((header + raw).encode())
        estimate += _tokens(part)
        index_rows.append(
            {"pointer": pointer, "sha256": digest, "canonical_bytes": len(raw.encode())}
        )
        # Whole-document checks happen only at increasing token milestones,
        # never once per appended record. Per-record hashing/tokenizing is linear.
        if estimate >= next_full_check:
            exact = _tokens("".join(content_parts))
            if exact >= LOCAL_TARGET_TOKENS:
                break
            estimate = exact
            next_full_check = max(LOCAL_TARGET_TOKENS, exact + 4096)
    text = "".join(displayed)
    content_tokens = _tokens("".join(content_parts))
    prompt_tokens = _tokens(text)
    (output / "evidence.txt").write_text(text, encoding="utf-8")
    (output / "evidence.txt").chmod(0o600)
    write_json(output / "records.json", index_rows)
    # Detect source mutation during preparation, including the original snapshot.
    for name, expected in pins.items():
        if file_record(root / name, MAX_SNAPSHOT_BYTES) != expected:
            raise ValueError("Capture changed during preparation")
    files = {
        name: file_record(output / name, MAX_PACKAGE_BYTES)
        for name in ("evidence.txt", "records.json", "c4/evidence.md", "c4/evidence.json")
    }
    return {
        "status": "ready" if content_tokens >= MIN_EVIDENCE_TOKENS else "pending",
        "reason": None
        if content_tokens >= MIN_EVIDENCE_TOKENS
        else "INSUFFICIENT_UNIQUE_CAPTURE_EVIDENCE",
        "capture_root": str(root),
        "selected_snapshot": str(snapshot_path.relative_to(root)),
        "capture_pins": pins,
        "files": files,
        "record_count": len(index_rows),
        "duplicate_records_omitted": omitted_duplicates,
        "tokenizer": "cl100k_base",
        "evidence_content_tokens_local_estimate": content_tokens,
        "evidence_with_locators_tokens_local_estimate": prompt_tokens,
        "provider_prompt_tokens": None,
        "provider_token_bound": None,
        "content_count_scope": "C4 summary plus unique canonical original allocator records; locator/hash headers excluded",
        "limitations": [
            "Local tokenization is not the provider tokenizer, a billing bound, or proof of a live 200k call.",
            "Preserved capture files are checked for consistency, not authenticated against a malicious producer.",
        ],
    }


def verify_long_evidence(document, directory):
    root = safe_directory(document["capture_root"])
    for name, expected in document["capture_pins"].items():
        if file_record(root / safe_relative(name), MAX_SNAPSHOT_BYTES) != expected:
            raise ValueError("Original capture changed after preparation")
    for name, expected in document["files"].items():
        if file_record(Path(directory) / safe_relative(name), MAX_PACKAGE_BYTES) != expected:
            raise ValueError("Prepared evidence changed after preparation")
    # Re-run selection and source bindings; no global profile or credential access.
    _, selected, current = capture_inputs(root)
    if (
        current != document["capture_pins"]
        or str(selected.relative_to(root)) != document["selected_snapshot"]
    ):
        raise ValueError("Capture selection changed after preparation")
    text = read_bytes(Path(directory) / "evidence.txt", MAX_PACKAGE_BYTES).decode("utf-8")
    if (
        document.get("status") != "ready"
        or document.get("evidence_content_tokens_local_estimate", 0) < MIN_EVIDENCE_TOKENS
    ):
        raise ValueError("Insufficient genuine evidence; Ultra execution remains pending")
    return text
