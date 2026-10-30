"""Snapshot intent protocol: model explanations, host-derived cited peak quantities."""

from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal

from jsonschema import Draft202012Validator

from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.snapshot_grounding import canonical_peak_table

SNAPSHOT_INTENT_PROTOCOL = "headroom.snapshot-intent.v1"
QUANTITY_SOURCE = "cited_peak_stack_sum_v1"
MAX_SCHEMA_BYTES = 16 * 1024
QUANTITY_PROVENANCE = (
    "Memory sizes are calculated from the cited stacks in this reconstructed capture. "
    "The model supplies explanations. These figures do not prove the cause, savings, "
    "or a new GPU result. Groups can overlap and should not be added together."
)


class SnapshotIntentError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def _table(evidence):
    return canonical_peak_table(
        evidence.get("analysis", {}),
        evidence.get("presentation", {}).get("peak_stack_ids", []),
    )


def build_snapshot_intent_schema(*, evidence, policy):
    """Narrow the request schema; root-cause bytes are forbidden, never overwritten."""
    rows = _table(evidence)["rows"]
    if not rows:
        raise SnapshotIntentError("SNAPSHOT_INTENT_NO_VISIBLE_PEAK")
    schema = build_diagnosis_schema(evidence=evidence, policy=policy)
    schema["title"] = "SnapshotDiagnosisIntent"
    cause = schema["$defs"]["RootCause"]
    cause["properties"].pop("bytes_gb")
    cause["required"].remove("bytes_gb")
    cause["additionalProperties"] = False
    cause["properties"]["evidence_refs"]["items"]["enum"] = sorted(row["stack_id"] for row in rows)
    schema["properties"]["root_causes"]["maxItems"] = 3
    qualitative = (
        "Qualitative prose only: no numeric memory amounts or units such as GB/GiB/MB/MiB/bytes. "
        "The host displays cited peak-stack quantities. Retain genuine unknowns."
    )
    cause["properties"]["title"]["description"] = qualitative
    schema["properties"]["notes"]["items"]["description"] = qualitative
    for field in ("title", "description", "risk"):
        schema["$defs"]["PlanStep"]["properties"][field]["description"] = qualitative
    schema["$defs"]["EvidenceRequest"]["properties"]["reason"]["description"] = (
        "Follow evidence_availability_catalog: visible supplied code is not missing. "
        "Its runtime meaning may be ambiguous; execution values may remain unknown. "
        "Do not remove a real blocker or claim its value is known."
    )
    schema["$defs"]["EvidenceRequest"]["properties"]["detail"]["description"] = qualitative
    if len(json.dumps(schema, ensure_ascii=True).encode()) > MAX_SCHEMA_BYTES:
        raise SnapshotIntentError("SNAPSHOT_INTENT_SCHEMA_TOO_LARGE")
    return schema


def derive_snapshot_diagnosis(intent, *, evidence, policy):
    """Validate locally, derive only the absent field, and retain auditable provenance.

    This function never accepts and repairs a model-authored bytes_gb value.
    Existing Diagnosis validation still runs after derivation.
    """
    schema = build_snapshot_intent_schema(evidence=evidence, policy=policy)
    if any(Draft202012Validator(schema).iter_errors(intent)):
        raise SnapshotIntentError("SNAPSHOT_INTENT_SCHEMA_REJECTED")
    # Finite canonical JSON is also required before copying or deriving anything.
    try:
        intent_sha = _hash(intent)
    except (ValueError, TypeError, OverflowError):
        raise SnapshotIntentError("SNAPSHOT_INTENT_SCHEMA_REJECTED") from None
    rows = {row["stack_id"]: row for row in _table(evidence)["rows"]}
    diagnosis = copy.deepcopy(intent)
    derivations = []
    used = set()
    overlapping = set()
    for cause in diagnosis["root_causes"]:
        refs = list(dict.fromkeys(cause["evidence_refs"]))
        counts = [{"stack_id": ref, "peak_bytes": rows[ref]["peak_bytes"]} for ref in refs]
        count = sum(row["peak_bytes"] for row in counts)
        decimal_gb = f"{count // 1_000_000_000}.{count % 1_000_000_000:09d}"
        published = float(decimal_gb)
        # Preserve the shared numeric schema without silently losing byte precision.
        if (
            not Decimal(str(published)).is_finite()
            or abs(Decimal(str(published)) * 1_000_000_000 - count) > 1
        ):
            raise SnapshotIntentError("SNAPSHOT_INTENT_QUANTITY_UNREPRESENTABLE")
        cause["bytes_gb"] = published
        derivations.append(
            {
                "cause_id": cause["id"],
                "unique_references": counts,
                "cited_peak_bytes": count,
                "decimal_GB": decimal_gb,
                "derived_field": "bytes_gb",
            }
        )
        overlapping.update(used.intersection(refs))
        used.update(refs)
    provenance = {
        "protocol": SNAPSHOT_INTENT_PROTOCOL,
        "intent_sha256": intent_sha,
        "snapshot_sha256": evidence.get("snapshot_sha256"),
        "basis": "deduplicated referenced visible peak_composition bytes",
        "causal_contribution_verified": False,
        "native_peak_counter_verified": False,
        "hardware_verification": "not_run",
        "derivations": derivations,
        "overlapping_cause_refs": sorted(overlapping),
        "cross_cause_totals_permitted": False,
        "derived_diagnosis_sha256": _hash(diagnosis),
    }
    return diagnosis, provenance
