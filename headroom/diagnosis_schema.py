"""Pure request constraints derived from the current evidence and permitted policy.

This narrows a fresh copy of the public Diagnosis schema. It neither changes the
historical schema nor replaces post-response evidence/policy validation.
"""

import copy
import json
from collections.abc import Mapping
from typing import Any

from headroom.evidence_blockers import evidence_reference_catalog
from headroom.schemas import Diagnosis
from headroom.solver_context import invocation_reference_catalog


class DiagnosisSchemaError(ValueError):
    """The request constraints cannot be safely constructed from these inputs."""


def _identifier(value: Any, *, kind: str) -> str:
    # Nonempty schema strings are stripped by the Pydantic contract; rejecting
    # padded keys avoids advertising an identity that would change on validation.
    if not isinstance(value, str) or not value or value.strip() != value:
        raise DiagnosisSchemaError(f"{kind} identifiers must be nonempty unpadded strings")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        raise DiagnosisSchemaError(f"{kind} identifiers must be valid UTF-8") from None
    return value


def build_diagnosis_schema(*, evidence: Mapping[str, Any], policy: Mapping[str, Any]) -> dict:
    """Constrain references/permissions without modifying evidence, policy or Diagnosis.

    Both the full evidence bundle and its direct analysis mapping are accepted,
    matching validate_diagnosis. Stack frames and other evidence content never
    enter the schema. A policy permission is enabled only by the boolean True;
    truthy numbers/strings do not grant permission. No scenario truth is used.
    Invalid or missing inputs fail before the caller can dispatch its request.
    """
    if not isinstance(evidence, Mapping):
        raise DiagnosisSchemaError("Evidence must be a mapping with a runtime stack catalog")
    analysis = evidence.get("analysis", evidence)
    catalog = analysis.get("stack_catalog") if isinstance(analysis, Mapping) else None
    if not isinstance(catalog, Mapping) or not catalog:
        raise DiagnosisSchemaError("Runtime stack catalog must be a nonempty mapping")
    references = sorted(_identifier(key, kind="Stack") for key in catalog)
    if not isinstance(policy, Mapping):
        raise DiagnosisSchemaError("Policy must be a mapping")
    permissions = []
    for key, value in policy.items():
        key = _identifier(key, kind="Policy")
        if value is True:
            permissions.append(key)
    permissions.sort()

    schema = copy.deepcopy(Diagnosis.model_json_schema())
    try:
        invocation_refs = schema["properties"]["invocation_refs"]
        identities = sorted(invocation_reference_catalog(evidence.get("execution_context")))
        if identities:
            invocation_refs["items"]["enum"] = identities
        else:
            invocation_refs["maxItems"] = 0
        definitions = schema["$defs"]
        evidence_ref = definitions["EvidenceRequest"]["properties"]["evidence_ref"]
        identities = sorted(evidence_reference_catalog(evidence))
        evidence_ref["anyOf"] = (
            [{"type": "string", "enum": identities}, {"type": "null"}]
            if identities
            else [{"type": "null"}]
        )
        refs = definitions["RootCause"]["properties"]["evidence_refs"]
        steps = definitions["PlanStep"]["properties"]
        required = steps["requires_policy"]
        refs["items"]["enum"] = references
        if permissions:
            required["items"]["enum"] = permissions
        else:
            # Empty enum is not valid JSON Schema. An empty array is the only
            # valid request when no permission is enabled.
            required["maxItems"] = 0
        if policy.get("allow_numerics_change") is not True:
            steps["numerics_impact"]["enum"] = ["none"]
        # Keep a JSON-safe wire contract. Never stringify unexpected objects or
        # permit nonfinite numbers; no raw input is included in failure messages.
        json.dumps(schema, ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise DiagnosisSchemaError(
            "Diagnosis request schema is not a valid JSON contract"
        ) from None
    return schema
