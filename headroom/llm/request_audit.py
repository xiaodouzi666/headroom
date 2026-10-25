"""Bounded evidence from the prepared HTTP body, never headers or environment."""

import hashlib
import json
import re

MAX_CAPTURE_BYTES = 256 * 1024
_SECRET_KEY = re.compile(
    r"^(?:authorization|cookie|api[-_]?key|password|passwd|secret|access[-_]?token|auth[-_]?token)$",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")


def capture_request(body: bytes, *, secret_values=()):
    """Hash exact bytes; retain a bounded JSON copy with explicitly scoped redaction.

    This proves local pre-transport preparation, not delivery or provider ingestion.
    Arbitrary secrets embedded in source text cannot be recognized in general.
    """
    result = {
        "schema_version": 1,
        "capture_point": "httpx_pre_transport",
        "wire_body_sha256": hashlib.sha256(body).hexdigest(),
        "wire_body_utf8_bytes": len(body),
        "delivery_confirmed": False,
        "payload": None,
        "payload_status": "omitted_size",
        "redaction_scope": "runtime API credential, named secret fields, bearer values",
    }
    if len(body) > MAX_CAPTURE_BYTES:
        return result
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError
        secrets = tuple(value for value in secret_values if isinstance(value, str) and value)
        changed = False

        def clean(value):
            nonlocal changed
            if isinstance(value, str):
                original = value
                for secret in secrets:
                    value = value.replace(secret, "[redacted]")
                value = _BEARER.sub("Bearer [redacted]", value)
                changed |= value != original
                return value
            if isinstance(value, list):
                return [clean(item) for item in value]
            if isinstance(value, dict):
                output = {}
                for key, item in value.items():
                    safe_key = clean(key)
                    if _SECRET_KEY.fullmatch(key):
                        output[safe_key] = "[redacted]"
                        changed = True
                    else:
                        output[safe_key] = clean(item)
                return output
            return value

        payload = clean(payload)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        if len(encoded) > MAX_CAPTURE_BYTES:
            return result
        result.update(
            payload=payload,
            payload_status="redacted" if changed else "captured",
            stored_payload_sha256=hashlib.sha256(encoded).hexdigest(),
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        result["payload_status"] = "invalid_json"
    return result
