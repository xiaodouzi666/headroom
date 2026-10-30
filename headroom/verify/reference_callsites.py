"""Source coordinates for an already-reviewed static family."""

import ast
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from headroom.verify.checkpoint import reviewed_block_callsite_nodes

MAX_CALLSITE_AID_BYTES = 1024


def checkpoint_callsite_reading_aid(document, context):
    """No I/O or repair selection; no new source family or execution proof."""
    if not isinstance(document, Mapping) or not isinstance(context, Mapping):
        return None
    boundary = context.get("source_contract_boundary")
    original, retained = context.get("original_source"), context.get("retained_source")
    if not all(isinstance(x, Mapping) for x in (boundary, original, retained)):
        return None
    if not (
        context.get("protocol") == "headroom.numerical_reference_context.v1"
        and context.get("selected_strategy") == "original_workload_checkpoint"
        and boundary.get("active_for_this_oom_baseline") is True
        and original.get("status") == retained.get("status") == "supported"
        and type(original.get("normalized_contract_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", original["normalized_contract_sha256"])
        and original.get("normalized_contract_sha256") == retained.get("normalized_contract_sha256")
        and original.get("source_sha256")
        == retained.get("source_sha256")
        == document.get("source_sha256")
    ):
        return None
    preconditions = context.get("explicit_reference_preconditions")
    if not (
        context.get("capability_status") == "preconditions_observed_execution_unverified"
        and boundary.get("candidate_source_must_remain_within_reviewed_contract") is True
        and isinstance(preconditions, Mapping)
        and bool(preconditions)
        and all(value is True for value in preconditions.values())
    ):
        return None
    families = boundary.get("reviewed_edit_families")
    if not isinstance(families, list) or not any(
        isinstance(x, Mapping) and x.get("kind") == "non_reentrant_activation_checkpoint"
        for x in families
    ):
        return None
    path = document.get("path")
    lines = document.get("lines")
    newline = document.get("newline")
    terminal = document.get("terminal_newline")
    if type(path) is not str:
        return None
    try:
        path_bytes = path.encode("utf-8")
    except UnicodeError:
        return None
    if not (
        type(path) is str
        and bool(path)
        and len(path_bytes) <= 512
        and not PurePosixPath(path).is_absolute()
        and ".." not in PurePosixPath(path).parts
        and not any(x.startswith(".env") for x in PurePosixPath(path).parts)
        and type(lines) is list
        and 0 < len(lines) <= 8192
        and newline in ("\n", "\r\n")
        and type(terminal) is bool
    ):
        return None
    for index, line in enumerate(lines, 1):
        if not (
            type(line) is dict
            and line.get("id") == f"L{index:06d}"
            and type(line.get("text")) is str
            and "\n" not in line["text"]
            and "\r" not in line["text"]
        ):
            return None
    source = newline.join(x["text"] for x in lines) + (newline if terminal else "")
    try:
        encoded = source.encode("utf-8")
    except UnicodeError:
        return None
    if len(encoded) > 131072 or hashlib.sha256(encoded).hexdigest() != document["source_sha256"]:
        return None
    try:
        sites = reviewed_block_callsite_nodes(ast.parse(source))
        result = {
            "schema": "headroom.reviewed_checkpoint_callsites.v1",
            "scope": "original_retained_source_static_coordinates_only",
            "source_sha256": document["source_sha256"],
            "entrypoint_name": PurePosixPath(path).name,
            "path_scope": (
                "Basename only. Resolve the exact source SHA in the supplied source-span "
                "documents; copy that document's path and original IDs. An ambiguous match "
                "does not identify an edit location."
            ),
            "sites": [
                {
                    "start_id": lines[node.lineno - 1]["id"],
                    "end_id": lines[node.end_lineno - 1]["id"],
                    "existing_call": ast.get_source_segment(source, node.value),
                    "family": "non_reentrant_activation_checkpoint",
                }
                for node in sites
            ],
            "boundary": (
                "Only the existing unchanged module call belongs to this reviewed family; "
                "a new wrapper method or moved forward body does not. "
                "Apply the unchanged exact requirements in source_contract_boundary."
            ),
            "reference_execution_verified": None,
            "candidate_equivalence_verified": None,
        }
        if (
            len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode())
            > MAX_CALLSITE_AID_BYTES
        ):
            return None
        return result
    except (
        ValueError,
        TypeError,
        SyntaxError,
        IndexError,
        KeyError,
        RecursionError,
        OverflowError,
    ):
        return None
