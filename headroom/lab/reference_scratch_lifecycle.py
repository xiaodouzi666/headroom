"""Host-owned lifetime of a reference-only quota broker, separate from /out."""

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

SOCKET_DESTINATION = "/run/headroom-reference-scratch.sock"


def _write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def descriptor(directory, broker, max_bytes):
    evidence = broker.evidence()
    root = Path(directory) / "reference-scratch"
    if (
        evidence.get("schema") != "headroom.reference-scratch.v1"
        or Path(evidence.get("root", "/")) != root
        or Path(evidence.get("socket_path", "/")) != Path(broker.socket_path)
        or evidence.get("nonce") != broker.nonce
        or not isinstance(broker.nonce, str)
        or re.fullmatch(r"[0-9a-f]{32}", broker.nonce) is None
        or evidence.get("max_bytes") != max_bytes
        or evidence.get("owner_pid") != os.getpid()
    ):
        raise ValueError("Reference scratch ownership descriptor mismatch")
    return {
        key: evidence[key]
        for key in (
            "schema",
            "nonce",
            "root",
            "socket_path",
            "max_bytes",
            "owner_pid",
            "owner_process_identity",
        )
    }


@contextmanager
def managed_reference_scratch(directory, max_bytes, state):
    """No service for ordinary captures; every positive reference has a unique broker."""
    if not max_bytes:
        yield None
        return
    from headroom.lab.reference_scratch import ReferenceScratchBroker
    from headroom.verify.offload_disk import validate_disk_limit

    validate_disk_limit(max_bytes)
    directory = Path(directory)
    broker = ReferenceScratchBroker(directory / "reference-scratch", max_bytes)
    expected = None
    try:
        broker.start()
        intent = descriptor(directory, broker, max_bytes)
        manifest = json.loads((directory / "manifest.json").read_text())
        if "owned_reference_scratch" in manifest:
            raise ValueError("Reference scratch intent already exists")
        manifest["owned_reference_scratch"] = intent
        _write(directory / "manifest.json", manifest)
        expected = intent
        state.update(expected, request_verified=True, cleanup_verified=False)
        yield Path(broker.socket_path)
    finally:
        error = None
        try:
            broker.close()
        except (OSError, ValueError, RuntimeError) as exc:
            error = type(exc).__name__
        try:
            final = broker.evidence()
            matched = expected is not None and all(final.get(k) == v for k, v in expected.items())
            state.clear()
            state.update(final)
            state["request_verified"] = matched
            state["cleanup_verified"] = (
                matched
                and error is None
                and final.get("cleanup_verified") is True
                and final.get("live_reserved_bytes") == 0
                and final.get("live_objects") == 0
            )
            if error is not None:
                state["cleanup_error_type"] = error
        except (OSError, ValueError, RuntimeError, TypeError) as exc:
            state.clear()
            state.update(
                request_verified=False,
                cleanup_verified=False,
                cleanup_error_type=type(exc).__name__,
            )
        _write(directory / "reference-scratch-host.json", state)


def recover_reference_scratch(directory, manifest):
    """Only after the caller has stopped its owned target; never delete a foreign path."""
    expected = manifest.get("owned_reference_scratch")
    if expected is None:
        return True
    if not isinstance(expected, dict):
        return False
    directory = Path(directory)
    root = directory / "reference-scratch"
    if (
        expected.get("schema") != "headroom.reference-scratch.v1"
        or expected.get("root") != str(root)
        or not isinstance(expected.get("nonce"), str)
        or re.fullmatch(r"[0-9a-f]{32}", expected["nonce"]) is None
        or type(expected.get("max_bytes")) is not int
        or expected["max_bytes"] <= 0
        or root.is_symlink()
    ):
        return False
    from headroom.lab.reference_scratch import cleanup_owned_scratch

    result = cleanup_owned_scratch(root, expected_nonce=expected["nonce"])
    return (
        result.get("cleanup_verified") is True
        and result.get("live_reserved_bytes") == 0
        and result.get("live_objects") == 0
    )
