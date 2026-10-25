"""Text availability never becomes runtime proof or overrides genuine blockers."""

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from headroom.diagnose import diagnose_with_router, validate_diagnosis
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.evidence import _render_sources
from headroom.evidence_blockers import (
    MAX_CATALOG_BYTES,
    build_evidence_availability_catalog,
    evidence_reference_catalog,
)
from headroom.schemas import Diagnosis
from headroom.solver_context import prompt_arguments, solver_prompt_context


def payload():
    return {
        "root_causes": [
            {
                "id": "cause",
                "title": "Measured temporary",
                "category": "temporaries",
                "bytes_gb": 1.0,
                "evidence_refs": ["stk"],
                "confidence": 0.8,
            }
        ],
        "plan": [
            {
                "fix_id": "reuse",
                "type": "code",
                "title": "Reuse temporary storage",
                "description": "Reuse a temporary after its last consumer, preserving optimizer updates.",
                "expected_saving_gb": 1.0,
                "numerics_impact": "none",
                "throughput_impact": "minor",
                "risk": "Verify lifetime safety",
                "requires_policy": [],
            }
        ],
        "verification": {"max_steps": 20, "compare_loss": True, "tolerance": 0.001},
        "needs_more_info": True,
        "notes": [],
    }


def source(lines=("value = 7", "other = value + 1", "consume(other)", "del other"), selected=None):
    selected = list(range(1, len(lines) + 1)) if selected is None else list(selected)
    sha = hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()
    files = [{"path": "entry.py", "sha256": sha, "lines": list(lines)}]
    markdown = (
        "## Source\nSource text is bounded.\n"
        + _render_sources(files, [(0, n) for n in selected])
        + "\n## Static source observations\n[]\n"
    )
    evidence = {
        "analysis": {"stack_catalog": {"stk": []}},
        "sources": [
            {
                "path": "entry.py",
                "sha256": sha,
                "total_lines": len(lines),
                "included_lines": selected,
            }
        ],
        "execution_context": {
            "script_args": prompt_arguments(["--count=7"]),
            "execution_argv": None,
            "runtime_input_observations": {"status": "unsupported"},
        },
    }
    return evidence, markdown


def ready_source(**kwargs):
    evidence, markdown = source(**kwargs)
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    return evidence


def request(reason="missing", **kwargs):
    return {
        "field": "source text",
        "reason": reason,
        "detail": "Need to understand its consumers.",
        "evidence_ref": "source[0]",
        "source_line_start": 1,
        "source_line_end": 2,
        "blocking_scope": "current_plan",
        "blocked_plan_ids": ["reuse"],
        **kwargs,
    }


def checked(reply, evidence=None):
    return validate_diagnosis(reply, evidence=evidence or ready_source(), policy={})


def test_catalog_binds_delivered_text_without_copying_values_or_claiming_runtime():
    evidence, markdown = source(lines=("canary = 'never_echo'", "pass"))
    original = copy.deepcopy(evidence)
    catalog = build_evidence_availability_catalog(evidence, markdown)
    entry = next(e for e in catalog["entries"] if e["evidence_ref"] == "source[0]")
    assert entry["visible_ranges"] == [[1, 2]] and entry["availability"] == "visible"
    assert entry["source_sha256"] == evidence["sources"][0]["sha256"]
    assert entry["runtime_values_verified"] is False
    assert catalog["evidence_markdown_sha256"] == hashlib.sha256(markdown.encode()).hexdigest()
    assert "never_echo" not in json.dumps(catalog)
    assert evidence == original
    schema = build_diagnosis_schema(
        evidence=evidence | {"evidence_availability_catalog": catalog}, policy={}
    )
    assert "never_echo" not in json.dumps(schema)
    assert schema["$defs"]["EvidenceRequest"]["properties"]["evidence_ref"]["anyOf"][0]["enum"]
    assert "evidence_ref" not in schema["$defs"]["EvidenceRequest"]["required"]


@pytest.mark.parametrize("reason", ["missing", "redacted", "truncated"])
def test_precise_visible_range_contradiction_uses_feedback_not_forced_readiness(reason):
    reply = payload()
    reply["evidence_requests"] = [request(reason)]
    original = copy.deepcopy(reply)
    result = checked(reply)
    assert not result.valid and result.requires_supplement and not result.ready_for_patch
    assert result.diagnosis.needs_more_info is True
    assert "EVIDENCE_AVAILABILITY_CONTRADICTED" in result.supplement_request
    assert "runtime values" in result.supplement_request
    assert result.invocation_provenance["evidence_requests"]["counts"]["contradicted"] == 1
    assert reply == original


@pytest.mark.parametrize(
    "mutation",
    [
        "different_sha",
        "missing_line",
        "duplicate_lines",
        "wrong_order",
        "missing_total",
        "bool_line",
        "absent_section",
        "duplicate_section",
    ],
)
def test_invalid_metadata_or_missing_delivery_never_manufactures_visibility(mutation):
    evidence, markdown = source()
    record = evidence["sources"][0]
    if mutation == "different_sha":
        record["sha256"] = "f" * 64
    elif mutation == "missing_line":
        record["included_lines"] = [1, 3, 4]
    elif mutation == "duplicate_lines":
        record["included_lines"] = [1, 1, 2, 3, 4]
    elif mutation == "wrong_order":
        record["included_lines"] = [2, 1, 3, 4]
    elif mutation == "missing_total":
        del record["total_lines"]
    elif mutation == "bool_line":
        record["included_lines"] = [True, 2, 3, 4]
    elif mutation == "absent_section":
        markdown = "Other evidence"
    else:
        markdown += markdown
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    reply = payload()
    reply["evidence_requests"] = [request()]
    result = checked(reply, evidence)
    assert result.valid and result.diagnosis.needs_more_info and not result.requires_supplement


def test_partial_and_redacted_ranges_stay_unknown_but_visible_subrange_is_checkable():
    evidence = ready_source(lines=("a = 1", "[REDACTED]", "consume(a)", "pass"), selected=[1, 2, 4])
    entry = evidence_reference_catalog(evidence)["source[0]"]
    assert entry["visible_ranges"] == [[1, 1], [4, 4]]
    assert entry["redacted_ranges"] == [[2, 2]] and entry["availability"] == "unknown"
    for start, end in [(1, 2), (2, 2), (3, 3), (1, 4)]:
        reply = payload()
        reply["evidence_requests"] = [request(source_line_start=start, source_line_end=end)]
        result = checked(reply, evidence)
        assert result.valid and not result.requires_supplement
    reply["evidence_requests"] = [request(source_line_start=4, source_line_end=4)]
    assert checked(reply, evidence).requires_supplement


def test_fences_inside_numbered_source_cannot_fabricate_sections():
    evidence = ready_source(
        lines=('text = "' + chr(96) * 3 + 'python"', 'other = "## Source"', "pass")
    )
    assert evidence_reference_catalog(evidence)["source[0]"]["visible_ranges"] == [[1, 3]]


def test_semantic_ambiguity_and_unsupported_runtime_remain_genuine_gaps():
    reply = payload()
    reply["evidence_requests"] = [request("ambiguous")]
    assert checked(reply).valid and not checked(reply).requires_supplement
    reply["evidence_requests"] = [
        request(
            evidence_ref="execution_context.runtime_input_observations",
            source_line_start=None,
            source_line_end=None,
        )
    ]
    result = checked(reply)
    assert result.valid and result.diagnosis.needs_more_info and not result.requires_supplement


def test_legacy_prose_is_compatible_unverified_and_never_keyword_parsed():
    reply = payload()
    reply["evidence_requests"] = [
        {
            "field": "entry.py lines 1-2",
            "reason": "ambiguous",
            "detail": "redacted foreach gradient batch secret",
        }
    ]
    result = checked(reply)
    assert result.valid and not result.requires_supplement
    assert result.invocation_provenance["evidence_requests"]["counts"]["legacy_unverified"] == 1
    assert not result.invocation_provenance["evidence_requests"]["unstructured_prose_checked"]
    assert (
        "blocking_scope"
        not in Diagnosis.model_json_schema()["$defs"]["EvidenceRequest"]["required"]
    )


@pytest.mark.parametrize(
    "changes,code",
    [
        ({"blocked_plan_ids": ["future_step"]}, "INVALID_EVIDENCE_DEPENDENCY"),
        ({"blocked_plan_ids": ["reuse", "reuse"]}, "INVALID_EVIDENCE_DEPENDENCY"),
        ({"blocked_plan_ids": []}, "INVALID_EVIDENCE_DEPENDENCY"),
        ({"blocking_scope": "alternative_plan"}, "INVALID_EVIDENCE_DEPENDENCY"),
        ({"blocking_scope": None}, "INVALID_EVIDENCE_DEPENDENCY"),
        ({"evidence_ref": "source[999]"}, "UNKNOWN_EVIDENCE_REFERENCE"),
        ({"source_line_end": None}, "INVALID_EVIDENCE_RANGE"),
        ({"source_line_start": 3, "source_line_end": 1}, "INVALID_EVIDENCE_RANGE"),
        ({"evidence_ref": "execution_context.script_args"}, "INVALID_EVIDENCE_RANGE"),
    ],
)
def test_invalid_structured_requests_have_specific_bounded_errors(changes, code):
    reply = payload()
    reply["evidence_requests"] = [request("ambiguous", **changes)]
    result = checked(reply)
    assert code in {issue.code for issue in result.issues}
    assert result.requires_supplement and result.diagnosis.needs_more_info


def test_only_explicit_alternative_requests_cannot_silently_block_current_plan():
    reply = payload()
    reply["evidence_requests"] = [
        request("ambiguous", blocking_scope="alternative_plan", blocked_plan_ids=[])
    ]
    result = checked(reply)
    assert "ALTERNATIVE_EVIDENCE_BLOCKS_CURRENT_PLAN" in result.supplement_request
    assert not result.ready_for_patch and result.diagnosis.needs_more_info
    reply["evidence_requests"].append(
        request("ambiguous", blocking_scope="overall_feasibility", blocked_plan_ids=[])
    )
    assert checked(reply).valid
    reply["plan"] = []
    reply["evidence_requests"] = reply["evidence_requests"][:1]
    assert checked(reply).valid


def test_catalog_resource_bounds_and_combined_transport_limit():
    evidence, markdown = source()
    evidence["sources"] *= 1000
    original = copy.deepcopy(evidence)
    catalog = build_evidence_availability_catalog(evidence, markdown)
    assert len(json.dumps(catalog, ensure_ascii=True).encode()) <= MAX_CATALOG_BYTES
    assert catalog["omitted_entries"] > 0 and len(catalog["entries"]) <= 67
    wire = solver_prompt_context(evidence_availability_catalog=catalog)
    assert len(json.dumps(wire, ensure_ascii=True).encode()) <= 64 * 1024
    assert evidence == original
    with pytest.raises(ValueError):
        solver_prompt_context(evidence_availability_catalog={"oversize": "x" * MAX_CATALOG_BYTES})


class Router:
    def __init__(self, replies):
        self.replies, self.calls = replies, []

    def chat(self, role, messages, schema, **kwargs):
        self.calls.append(copy.deepcopy((role, messages, schema, kwargs)))
        return SimpleNamespace(
            parsed=copy.deepcopy(self.replies[min(len(self.calls) - 1, len(self.replies) - 1)])
        )


def test_actual_diagnosis_entry_rechecks_all_validators_and_keeps_existing_limits():
    evidence, markdown = source()
    original = copy.deepcopy(evidence)
    first = payload()
    first["evidence_requests"] = [request()]
    second = payload()
    second["evidence_requests"] = [request("ambiguous")]
    second["plan"][0]["title"] = "Switch to bf16"
    third = payload()
    third["evidence_requests"] = [request("ambiguous")]
    router = Router([first, second, third])
    result = diagnose_with_router(
        router, markdown, evidence=evidence, goal="reclaim", policy={}, max_supplements=2
    )
    assert result.valid and not result.ready_for_patch and result.diagnosis.needs_more_info
    assert len(router.calls) == 3
    assert "EVIDENCE_AVAILABILITY_CONTRADICTED" in router.calls[1][1][-1]["content"]
    assert "NUMERICS_CHANGE_FORBIDDEN" in router.calls[2][1][-1]["content"]
    assert all(call[3] == {"reasoning": True, "max_tokens": 8192} for call in router.calls)
    delivered = json.loads(router.calls[0][1][-1]["content"])["evidence_availability_catalog"]
    assert delivered["evidence_markdown_sha256"] == hashlib.sha256(markdown.encode()).hexdigest()
    Draft202012Validator(router.calls[0][2]).validate(first)
    assert evidence == original


@pytest.mark.parametrize("limit", [0, 1, 3])
def test_persistent_error_never_expands_supplement_allowance(limit):
    evidence, markdown = source()
    reply = payload()
    reply["evidence_requests"] = [request()]
    router = Router([reply])
    result = diagnose_with_router(
        router, markdown, evidence=evidence, goal="reclaim", policy={}, max_supplements=limit
    )
    assert len(router.calls) == limit + 1
    assert result.requires_supplement and not result.ready_for_patch


def test_visible_parent_never_disproves_missing_runtime_child_or_semantics():
    evidence, markdown = source()
    evidence["execution_context"]["runtime_input_observations"] = {"status": "observed"}
    evidence["evidence_availability_catalog"] = build_evidence_availability_catalog(
        evidence, markdown
    )
    reply = payload()
    reply["evidence_requests"] = [
        request(
            field="execution_context.runtime_input_observations.actual_effective_batch",
            evidence_ref="execution_context.runtime_input_observations",
            source_line_start=None,
            source_line_end=None,
        )
    ]
    result = checked(reply, evidence)
    assert result.valid and result.diagnosis.needs_more_info and not result.requires_supplement
    reply["evidence_requests"][0]["field"] = "execution_context.runtime_input_observations"
    assert checked(reply, evidence).requires_supplement
