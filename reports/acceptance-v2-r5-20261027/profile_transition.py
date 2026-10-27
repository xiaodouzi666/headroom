"""Read-only capability transition proof; never edits funding, profile or ledger.

This isolated helper validates immutable artifacts only. The caller must first
run unchanged funding validation, then call the normal runtime loader after this
check. Passing this helper alone neither authorizes spend nor proves a live probe.
"""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

R4_BASE_PROFILE_PATH = ".cache/tokenfactory-runtime-v2-r2.json"
R4_BASE_PROFILE_SHA256 = "0a55810841198ed0821653a6690542b2e43eead3f73885e77dcb748fc57bd1e9"
MAX_ARTIFACT_BYTES = 1024 * 1024
ALLOWED_PATHS = (
    "models.super.capabilities.low_effort_method",
    "models.super.capabilities.low_effort_evidence",
    "models.super.capabilities.low_effort_evidence_sha256",
)
FIELDS = tuple(path.rsplit(".", 1)[1] for path in ALLOWED_PATHS)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")
_RECEIPT_KEYS = {
    "kind",
    "base_profile_path",
    "base_profile_sha256",
    "new_profile_path",
    "new_profile_sha256",
    "funding_transition_path",
    "funding_transition_sha256",
    "low_effort_probe_receipt_path",
    "low_effort_probe_receipt_sha256",
    "allowed_paths",
    "changes",
    "base_projection_sha256",
    "new_projection_sha256",
    "financial_or_ledger_changes",
    "reviewed_source_revision",
    "reviewer",
    "review_time",
}


class TransitionInvalid(ValueError):
    """Static error only: deliberately never echo artifacts or their contents."""


@dataclass(frozen=True)
class TransitionPins:
    # Freeze these from the independently reviewed receipt, never from active
    # untrusted profile bytes or a freshly recomputed hash during dispatch.
    transition_receipt_path: str
    transition_receipt_sha256: str
    new_profile_path: str
    new_profile_sha256: str
    funding_transition_path: str
    funding_transition_sha256: str
    low_effort_probe_receipt_path: str
    low_effort_probe_receipt_sha256: str


@dataclass(frozen=True)
class _Number:
    token: str


def _fail():
    raise TransitionInvalid("Runtime capability transition validation failed")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def _forbidden_constant(_value):
    _fail()


def _parse(raw):
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_int=_Number,
        parse_float=_Number,
        parse_constant=_forbidden_constant,
    )


def _canonical(value):
    # Preserve numeric lexemes. Python's ordinary 1 == 1.0 == True comparison is
    # too weak for a complete unchanged-tree proof.
    if isinstance(value, _Number):
        return value.token
    if type(value) is dict:
        return (
            "{"
            + ",".join(
                json.dumps(key, ensure_ascii=False) + ":" + _canonical(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if type(value) is list:
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if type(value) is str or value is None or type(value) is bool:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    _fail()


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _projection_digest(value):
    return _digest(_canonical(value).encode("utf-8"))


def _relative(value):
    if type(value) is not str or not value or "\\" in value:
        _fail()
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or not path.parts
        or any(part in (".", "..") or part.lower().startswith(".env") for part in path.parts)
        or path.suffix != ".json"
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        _fail()
    return path.parts


def _read(root, relative, expected_sha):
    parts = _relative(relative)
    if type(expected_sha) is not str or not _SHA256.fullmatch(expected_sha):
        _fail()
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    directory = os.open(root, flags | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], flags, dir_fd=directory)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_ARTIFACT_BYTES:
                _fail()
            raw = handle.read(MAX_ARTIFACT_BYTES + 1)
    finally:
        os.close(directory)
    if len(raw) > MAX_ARTIFACT_BYTES or _digest(raw) != expected_sha:
        _fail()
    value = _parse(raw)
    if type(value) is not dict:
        _fail()
    return value, (info.st_dev, info.st_ino)


def _integer(value):
    if not isinstance(value, _Number) or not re.fullmatch(r"0|[1-9][0-9]*", value.token):
        _fail()
    return int(value.token)


def _capabilities(profile):
    models = profile.get("models")
    super_model = models.get("super") if type(models) is dict else None
    caps = super_model.get("capabilities") if type(super_model) is dict else None
    if type(caps) is not dict:
        _fail()
    return super_model, caps


def verify_transition(project_root, pins, *, probe_finance):
    """Return only hashes, booleans and the three exact allowed structural paths.

    All files are read bounded with no-follow traversal. No environment, network,
    database, write operation or runtime construction is used.
    """
    try:
        return _verify_transition(Path(project_root), pins, probe_finance)
    except TransitionInvalid:
        raise
    except (
        ImportError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        RecursionError,
        OverflowError,
    ):
        raise TransitionInvalid("Runtime capability transition validation failed") from None


def _verify_transition(root, pins, probe_finance):
    if type(pins) is not TransitionPins:
        _fail()
    links = {
        "base_profile": (R4_BASE_PROFILE_PATH, R4_BASE_PROFILE_SHA256),
        "new_profile": (pins.new_profile_path, pins.new_profile_sha256),
        "funding_transition": (pins.funding_transition_path, pins.funding_transition_sha256),
        "low_effort_probe_receipt": (
            pins.low_effort_probe_receipt_path,
            pins.low_effort_probe_receipt_sha256,
        ),
    }
    all_paths = [path for path, _ in links.values()] + [pins.transition_receipt_path]
    if len(set(all_paths)) != len(all_paths):
        _fail()
    documents, identities = {}, set()
    for name, (path, digest) in {
        **links,
        "transition_receipt": (pins.transition_receipt_path, pins.transition_receipt_sha256),
    }.items():
        document, identity = _read(root, path, digest)
        if identity in identities:
            _fail()
        documents[name] = document
        identities.add(identity)

    base, new = documents["base_profile"], documents["new_profile"]
    base_model, base_caps = _capabilities(base)
    _, new_caps = _capabilities(new)
    additions = dict(
        zip(
            FIELDS,
            (
                "chat_template_kwargs",
                pins.low_effort_probe_receipt_path,
                pins.low_effort_probe_receipt_sha256,
            ),
            strict=True,
        )
    )
    if any(field in base_caps for field in FIELDS):
        _fail()
    if any(
        type(new_caps.get(field)) is not str or new_caps[field] != value
        for field, value in additions.items()
    ):
        _fail()
    # Round-trip our strict canonical form for a deep copy without coalescing
    # number types/lexemes, missing keys, nulls or string formatting.
    projection = _parse(_canonical(new).encode("utf-8"))
    _, projected_caps = _capabilities(projection)
    for field in FIELDS:
        del projected_caps[field]
    if _canonical(base) != _canonical(projection):
        _fail()
    base_projection_sha = _projection_digest(base)
    new_projection_sha = _projection_digest(projection)

    receipt = documents["transition_receipt"]
    if set(receipt) != _RECEIPT_KEYS:
        _fail()
    if receipt["kind"] != "non_financial_capability_extension_v1":
        _fail()
    for name, (path, digest) in links.items():
        if receipt[name + "_path"] != path or receipt[name + "_sha256"] != digest:
            _fail()
    if receipt["allowed_paths"] != list(ALLOWED_PATHS):
        _fail()
    changes = [
        {"path": path, "before": {"missing": True}, "after": additions[field]}
        for path, field in zip(ALLOWED_PATHS, FIELDS, strict=True)
    ]
    if _canonical(receipt["changes"]) != _canonical(changes):
        _fail()
    if (
        receipt["base_projection_sha256"] != base_projection_sha
        or receipt["new_projection_sha256"] != new_projection_sha
        or receipt["financial_or_ledger_changes"] is not False
        or type(receipt["reviewed_source_revision"]) is not str
        or not _REVISION.fullmatch(receipt["reviewed_source_revision"])
        or type(receipt["reviewer"]) is not str
        or not receipt["reviewer"].strip()
        or len(receipt["reviewer"]) > 128
        or type(receipt["review_time"]) is not str
    ):
        _fail()
    reviewed_at = datetime.fromisoformat(receipt["review_time"])
    if reviewed_at.utcoffset() is None:
        _fail()

    probe = documents["low_effort_probe_receipt"]
    compatibility = {key: value for key, value in base_model.items() if key != "capabilities"}
    # The pinned production base explicitly includes all ProfileModel/BillingBound
    # defaults. Do not add defaults here: the complete reviewed context must match.
    reasoning = _integer(probe.get("reasoning_tokens"))
    completion = _integer(probe.get("completion_tokens"))
    if (
        probe.get("scope") != "super_low_effort_schema_code_probe_v1"
        or probe.get("provenance") != "live"
        or probe.get("profile_sha256") != R4_BASE_PROFILE_SHA256
        or probe.get("accepted") is not True
        or probe.get("verdict") != "request_combination_usable_in_one_sample"
        or probe.get("finish_reason") != "stop"
        or probe.get("response_model") != base_model.get("model_id")
        or probe.get("base_url") != base.get("base_url")
        or _canonical(probe.get("profile_model_compatibility")) != _canonical(compatibility)
        or not 0 < reasoning <= completion <= 4000
    ):
        _fail()

    _verify_finance_link(probe_finance, probe, pins)

    return {
        "valid": True,
        "probe_finance_verified": True,
        "before_ledger_sha256": probe_finance.before_ledger_sha256,
        "after_ledger_sha256": probe_finance.after_ledger_sha256,
        "transition_receipt_sha256": pins.transition_receipt_sha256,
        "base_profile_sha256": R4_BASE_PROFILE_SHA256,
        "new_profile_sha256": pins.new_profile_sha256,
        "funding_transition_sha256": pins.funding_transition_sha256,
        "low_effort_probe_receipt_sha256": pins.low_effort_probe_receipt_sha256,
        "base_projection_sha256": base_projection_sha,
        "new_projection_sha256": new_projection_sha,
        "full_projection_equal": True,
        "financial_or_ledger_changes": False,
        "allowed_paths": list(ALLOWED_PATHS),
    }


def _is_verified_probe_finance(value):
    # A lazy import keeps this boundary testable without importing live runtime.
    # Root must put the independently reviewed finance_chain module on sys.path.
    from finance_chain import is_verified_probe_finance

    return is_verified_probe_finance(value)


def _verify_finance_link(value, probe, pins):
    # A JSON marker saying live or verified cannot satisfy this interface.
    if _is_verified_probe_finance(value) is not True:
        _fail()
    if (
        value.schema != "headroom.verified-probe-finance.v1"
        or value.probe_receipt_sha256 != pins.low_effort_probe_receipt_sha256
        or value.base_profile_sha256 != R4_BASE_PROFILE_SHA256
        or value.store_path != "runs/acceptance/headroom.db"
        or value.ledger_path != ".cache/budget.db"
        or probe.get("store_path") != value.store_path
        or probe.get("ledger_path") != value.ledger_path
    ):
        _fail()
    for digest in (value.before_ledger_sha256, value.after_ledger_sha256):
        if type(digest) is not str or not _SHA256.fullmatch(digest):
            _fail()
    for field in ("run_id", "budget_attempt_id"):
        recorded = probe.get(field)
        verified = getattr(value, field)
        if (
            type(recorded) is not str
            or not recorded
            or len(recorded) > 128
            or type(verified) is not str
            or verified != recorded
        ):
            _fail()
    call_id = _integer(probe.get("call_id"))
    if type(value.call_id) is not int or value.call_id <= 0 or value.call_id != call_id:
        _fail()
