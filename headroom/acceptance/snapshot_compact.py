"""Lossless indentation removal for saved JSON; the 512 MiB parse limit is unchanged."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from headroom.acceptance.common import file_record, read_json
from headroom.api.security import open_regular

MAX_INPUT = 768 * 1024 * 1024
MAX_OUTPUT = 512 * 1024 * 1024
MAX_LINE = 4 * 1024 * 1024
METHOD = "remove-leading-space-tab-per-line.v1"


def transformation_record(source: Path, *, writer=None) -> dict:
    """Keep line endings/all other bytes, so strings and bare-token boundaries survive.

    Valid JSON strings cannot contain a bare newline. An invalid multiline string
    retains that newline and is still rejected by the ordinary JSON parser.
    Unlike arbitrary whitespace deletion, this cannot turn '1\\n 2' into '12'.
    """
    source = Path(source)
    raw_digest, output_digest = hashlib.sha256(), hashlib.sha256()
    raw_size = output_size = 0
    with open_regular(source.parent, source.name, max_bytes=MAX_INPUT) as stream:
        while line := stream.readline(MAX_LINE + 1):
            if len(line) > MAX_LINE:
                raise ValueError("JSON line exceeds bounded transformation size")
            raw_size += len(line)
            if raw_size > MAX_INPUT:
                raise ValueError("Saved snapshot exceeds transformation input bound")
            changed = line.lstrip(b" \t")
            output_size += len(changed)
            if output_size > MAX_OUTPUT:
                raise ValueError("Deindented JSON still exceeds the unchanged parse limit")
            raw_digest.update(line)
            output_digest.update(changed)
            if writer is not None:
                writer.write(changed)
    return {
        "method": METHOD,
        "original_bytes": raw_size,
        "original_sha256": raw_digest.hexdigest(),
        "normalized_bytes": output_size,
        "normalized_sha256": output_digest.hexdigest(),
        "parse_limit_bytes": MAX_OUTPUT,
    }


def normalize(source: Path, destination: Path) -> dict:
    source, destination = Path(source).resolve(strict=True), Path(destination)
    if destination.exists() or source == destination.resolve():
        raise FileExistsError("Normalization never overwrites an existing artifact")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name("." + destination.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as output:
            record = transformation_record(source, writer=output)
        # Only the smaller file is parsed, with the same bound as production evidence.
        read_json(temporary, MAX_OUTPUT)
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return record | {
        "original_path": str(source),
        "normalized_path": str(destination.resolve()),
        "json_semantics": "unchanged; only leading line indentation removed",
        "original_preserved": True,
        "repair_score_eligible": False,
    }


def verified_json(record: dict):
    """Recompute from original bytes; a stored 'valid' or 'passed' flag is insufficient."""
    if record.get("method") != METHOD or record.get("parse_limit_bytes") != MAX_OUTPUT:
        raise ValueError("Unsupported JSON normalization proof")
    original, normalized = Path(record["original_path"]), Path(record["normalized_path"])
    recomputed = transformation_record(original)
    if any(record.get(key) != value for key, value in recomputed.items()):
        raise ValueError("Original/transformation proof mismatch")
    saved = file_record(normalized, MAX_OUTPUT)
    if (
        saved["sha256"] != record["normalized_sha256"]
        or saved["bytes"] != record["normalized_bytes"]
    ):
        raise ValueError("Normalized snapshot changed")
    return read_json(normalized, MAX_OUTPUT)


def write_proof(path: Path, record: dict) -> None:
    with Path(path).open("x") as output:
        json.dump(record, output, indent=2, allow_nan=False)
        output.write("\n")
