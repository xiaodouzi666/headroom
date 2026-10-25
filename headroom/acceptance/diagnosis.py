"""T1.4 diagnosis-only acceptance from explicitly selected, preserved CUDA captures.

Preparation is offline. Execution uses the shared acceptance runtime, and never
starts Lab, repairs, research, annotations, or diagnosis supplements.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal, localcontext
from pathlib import Path
from types import SimpleNamespace

import httpx

from headroom import budget as budget_module
from headroom import diagnose as diagnosis_module
from headroom import (
    diagnosis_protocol,
    diagnosis_schema,
    evidence_blockers,
    ledger_path,
    schemas,
    solver_context,
)
from headroom.acceptance import common as common_module
from headroom.acceptance.common import (
    acceptance_run,
    file_record,
    read_bytes,
    read_json,
    write_json,
)
from headroom.budget import money
from headroom.config import ULTRA_MODEL
from headroom.diagnose import (
    DIAGNOSIS_MAX_COMPLETION_TOKENS,
    PROMPT_PATH,
    build_diagnosis_messages,
    diagnose_with_router,
)
from headroom.diagnosis_schema import build_diagnosis_schema
from headroom.evidence import MAX_SNAPSHOT_BYTES, _main_source, _tokens, build_evidence
from headroom.evidence_blockers import build_evidence_availability_catalog
from headroom.lab.runner import read_capture, selected_capture_directory
from headroom.lab.snapshot_codec import read_snapshot_artifact
from headroom.llm.router import ResponseValidationError
from headroom.orchestrator import Policy, _required_reduction
from headroom.runtime import PROJECT_ROOT

SCENARIO_IDS = (
    "s1_batch_too_big",
    "s2_fp32_adamw_1b",
    "s3_eval_no_grad_missing",
    "s4_loss_accumulation_graph",
    "s5_fragmentation_varlen",
    "s6_full_vocab_logits_fp32",
    "s7_frozen_params_optimizer_state",
    "s8_two_models_resident",
)
SCHEMA = "headroom.diagnosis-acceptance.v1"
ACTUAL_CALL_LIMIT_USD = Decimal("0.35")
REQUIRED_MATCHES = 6
MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_ARTIFACT_BYTES = 256 * 1024
# Bind the actual imported request builders, not paths inside a fixture project.
# Older preparation packages without these pins must be prepared afresh.
REQUEST_IMPLEMENTATION_PATHS = {
    "acceptance/diagnosis.py": Path(__file__),
    "diagnose.py": Path(diagnosis_module.__file__),
    "diagnosis_protocol.py": Path(diagnosis_protocol.__file__),
    "diagnosis_schema.py": Path(diagnosis_schema.__file__),
    "evidence_blockers.py": Path(evidence_blockers.__file__),
    "schemas.py": Path(schemas.__file__),
    "solver_context.py": Path(solver_context.__file__),
    "ledger_path.py": Path(ledger_path.__file__),
    "budget.py": Path(budget_module.__file__),
    "acceptance/common.py": Path(common_module.__file__),
}


class DiagnosisAcceptanceRefused(ValueError):
    """Fixed, nonsecret refusal codes; never interpolate provider exceptions."""


def _require(condition, code):
    if not condition:
        raise DiagnosisAcceptanceRefused(code)


def _regular_directory(path):
    path = Path(path).absolute()
    _require(not any(part.startswith(".env") for part in path.parts), "SECRET_PATH_FORBIDDEN")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        _require(not current.is_symlink(), "DIRECTORY_SYMLINK_FORBIDDEN")
    _require(path.is_dir(), "DIRECTORY_MISSING")
    return path


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json_digest(value):
    return _digest(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())


def _project_inputs(root):
    """Truth comes from the maintained original fixture documents, never the model."""
    manifest_path = root / "eval/mvp_phase1.yaml"
    index_path = root / "scenarios/INDEX.yaml"
    manifest = read_json(manifest_path, max_bytes=MAX_METADATA_BYTES)
    index = read_json(index_path, max_bytes=MAX_METADATA_BYTES)
    cases = {row["id"]: row for row in manifest["scenarios"] if row["id"] in SCENARIO_IDS}
    indexed = {row["id"]: row for row in index["scenarios"] if row["id"] in SCENARIO_IDS}
    _require(len(cases) == len(indexed) == 8, "ORIGINAL_EIGHT_CASES_REQUIRED")
    pins = {
        "eval/mvp_phase1.yaml": file_record(manifest_path, max_bytes=MAX_METADATA_BYTES),
        "scenarios/INDEX.yaml": file_record(index_path, max_bytes=MAX_METADATA_BYTES),
        "diagnosis_prompt": file_record(PROMPT_PATH, max_bytes=MAX_METADATA_BYTES),
    }
    pins.update(
        {
            "request_implementation/" + name: file_record(path, max_bytes=MAX_METADATA_BYTES)
            for name, path in REQUEST_IMPLEMENTATION_PATHS.items()
        }
    )
    for case_id in SCENARIO_IDS:
        case, entry = cases[case_id], indexed[case_id]
        _require(case["script"] == f"scenarios/{case_id}/train.py", "SCENARIO_SOURCE_CHANGED")
        _require(entry["script"] == case["script"], "INDEX_SOURCE_DISAGREEMENT")
        _require(entry["root_cause"] == case["ground_truth"], "TRUTH_METADATA_DISAGREEMENT")
        script = root / case["script"]
        _regular_directory(script.parent)
        source = file_record(script, max_bytes=1024 * 1024)
        _require(source["sha256"] == case["source_sha256"], "CANONICAL_SOURCE_HASH_MISMATCH")
        _require(source["sha256"] == entry["gpu_source_sha256"], "INDEX_SOURCE_HASH_MISMATCH")
        pins[case["script"]] = source
        readme = root / f"scenarios/{case_id}/README.md"
        pins[f"scenarios/{case_id}/README.md"] = file_record(readme, max_bytes=MAX_METADATA_BYTES)
    return cases, pins


def _capture_inputs(path, case):
    """Validate original source/configuration and hash evidence without running code."""
    root = _regular_directory(path)
    result = read_capture(root / "result.json")
    manifest = read_json(root / "manifest.json", max_bytes=MAX_METADATA_BYTES)
    _require(result.get("capture_complete") is True, "INCOMPLETE_CAPTURE")
    _require(result.get("cleanup_verified") is True, "CLEANUP_UNVERIFIED")
    _require(result["status"] == case["expected_baseline"], "BASELINE_STATUS_MISMATCH")
    _require(manifest.get("device") == result["env"].get("device") == "cuda", "CUDA_REQUIRED")
    _require(
        manifest.get("max_steps") == result["env"].get("max_steps") == 20,
        "TWENTY_STEP_CONFIG_REQUIRED",
    )
    if result["status"] == "completed":
        _require(result["steps"] == 20, "COMPLETED_CAPTURE_REQUIRES_TWENTY_STEPS")
    _require(_main_source(manifest) == "train.py", "ORIGINAL_ENTRYPOINT_REQUIRED")
    command = manifest.get("command", [])
    _require(
        isinstance(command, list)
        and command[1:3] == ["-m", "headroom.lab.run_target"]
        and (command[command.index("--") + 1 :] if "--" in command else [])
        == case.get("script_args", []),
        "ORIGINAL_SCENARIO_ARGUMENTS_REQUIRED",
    )
    artifacts = selected_capture_directory(root, result, manifest)
    raw = read_capture(artifacts / "result.json")
    _require(raw.get("capture_complete") is True, "INCOMPLETE_RAW_CAPTURE")
    _require(raw["status"] == result["status"], "RAW_CAPTURE_STATUS_MISMATCH")
    for key, value in raw.items():
        if key not in {"status", "reason", "shared_gpu"}:
            _require(result.get(key) == value, "CAPTURE_RESULT_BINDING_MISMATCH")
    source = file_record(root / "source/train.py", max_bytes=1024 * 1024)
    _require(
        source["sha256"]
        == manifest["source"]["files"]["train.py"]["sha256"]
        == case["source_sha256"],
        "CAPTURE_SOURCE_HASH_MISMATCH",
    )
    snapshot = read_snapshot_artifact(artifacts / "snapshot.json", MAX_SNAPSHOT_BYTES)
    _require(
        isinstance(snapshot, dict)
        and isinstance(snapshot.get("device_traces"), list)
        and any(snapshot["device_traces"]),
        "CUDA_SNAPSHOT_HISTORY_REQUIRED",
    )
    pins = {
        "result.json": file_record(root / "result.json", max_bytes=MAX_DOCUMENT_BYTES),
        "manifest.json": file_record(root / "manifest.json", max_bytes=MAX_METADATA_BYTES),
        "source/train.py": source,
    }
    for name in ("result.json", "env.json", "snapshot.json"):
        leaf = artifacts / name
        pins[str(leaf.relative_to(root))] = file_record(
            leaf, max_bytes=MAX_SNAPSHOT_BYTES if name == "snapshot.json" else MAX_DOCUMENT_BYTES
        )
    _require(
        result.get("run_id") == raw.get("run_id", result.get("run_id")), "CAPTURE_RUN_ID_MISMATCH"
    )
    return root, result, manifest, pins


def _truth_record(root, case, destination):
    readme_path = root / f"scenarios/{case['id']}/README.md"
    readme = read_bytes(readme_path, max_bytes=MAX_METADATA_BYTES)
    (destination / "README.truth.md").write_bytes(readme)
    verified = (
        case.get("truth_status") in {"authored", "verified"} and case["id"] != SCENARIO_IDS[4]
    )
    return {
        "declared_category": case["ground_truth"],
        "truth_status": case.get("truth_status"),
        "scoreable_category": case["ground_truth"] if verified else None,
        "readme_path": str(readme_path),
        "readme_sha256": _digest(readme),
        "readme_copy": "README.truth.md",
        "basis": "Exact manifest category checked against the original INDEX; accompanying README is retained verbatim.",
        "limitations": (
            [
                "Harmful fragmentation is unconfirmed; reserved minus allocated includes cache. No automatic adjudication."
            ]
            if case["id"] == SCENARIO_IDS[4]
            else [
                "Authored fixture intent is the scoring reference, not a new causal proof from the model."
            ]
        ),
    }


def _prepared_request(evidence, markdown, *, goal, policy, required_saving_gb):
    """Derive the same bounded request context from the frozen evidence bytes.

    The source document remains unchanged. Preparation, revalidation and dispatch
    use this one adapter and the same catalogue/message builders as diagnosis.
    """
    document = dict(evidence)
    document["evidence_availability_catalog"] = build_evidence_availability_catalog(
        document, markdown
    )
    messages = build_diagnosis_messages(
        markdown,
        goal=goal,
        policy=policy,
        required_saving_gb=required_saving_gb,
        execution_context=document.get("execution_context"),
        candidate_evidence=document.get("candidate_evidence"),
        numerical_reference_context=document.get("numerical_reference_context"),
        evidence_availability_catalog=document["evidence_availability_catalog"],
    )
    return document, messages


def prepare_diagnosis_acceptance(
    captures, output_dir, *, project_root=PROJECT_ROOT, evidence_budget=150000
):
    """Prepare eight rows, including missing/invalid rows, without key/profile/network access."""
    _require(isinstance(captures, Mapping), "CAPTURES_MAPPING_REQUIRED")
    _require(not set(captures) - set(SCENARIO_IDS), "UNKNOWN_SCENARIO_ID")
    _require(
        type(evidence_budget) is int and 1 <= evidence_budget <= 150000, "EVIDENCE_BUDGET_INVALID"
    )
    root = _regular_directory(project_root)
    cases, project_pins = _project_inputs(root)
    output = Path(output_dir).absolute()
    destination = output.resolve()
    protected = [root / f"scenarios/{case_id}" for case_id in SCENARIO_IDS]
    protected.extend(Path(value) for value in captures.values() if isinstance(value, (str, Path)))
    _require(
        not any(destination.is_relative_to(path.resolve()) for path in protected),
        "OUTPUT_MUST_NOT_MODIFY_ORIGINAL_CAPTURE_OR_SOURCE",
    )
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {
        "schema": SCHEMA,
        "mode": "prepare",
        "accepted": False,
        "live_executed": False,
        "project_root": str(root),
        "project_inputs": project_pins,
        "evidence_budget": evidence_budget,
        "policy": Policy().model_dump(),
        "thresholds": {"required_matches": 6, "denominator": 8, "actual_call_limit_usd": "0.35"},
        "rows": [],
        "limitations": [
            "Preparation checks existing artifacts; it does not authenticate hostile target-generated evidence or call a model."
        ],
        "messages_hash_scope": "messages.json is before the router adds the schema; it is not a wire-request hash.",
    }
    for case_id in SCENARIO_IDS:
        case = cases[case_id]
        directory = output / "cases" / case_id
        directory.mkdir(parents=True)
        row = {
            "scenario_id": case_id,
            "status": "missing",
            "capture": None,
            "capture_inputs": None,
            "truth": _truth_record(root, case, directory),
            "target": case["target"],
            "first_cause_match": None,
            "accepted": False,
        }
        report["rows"].append(row)
        if case_id in captures:
            try:
                capture, result, _, pins = _capture_inputs(captures[case_id], case)
                row.update(capture=str(capture), capture_inputs=pins)
                evidence = build_evidence(
                    capture, budget=evidence_budget, output_dir=directory / "evidence"
                )
                document = read_json(
                    directory / "evidence/evidence.json", max_bytes=MAX_DOCUMENT_BYTES
                )
                catalog = document.get("analysis", {}).get("stack_catalog")
                _require(
                    isinstance(catalog, dict) and bool(catalog), "RUNTIME_STACK_CATALOG_REQUIRED"
                )
                _require(not document.get("source_warnings"), "SOURCE_EVIDENCE_INCOMPLETE")
                markdown = read_bytes(
                    directory / "evidence/evidence.md", max_bytes=MAX_DOCUMENT_BYTES
                ).decode()
                _require(
                    _tokens(markdown) == evidence["token_count"] <= evidence_budget,
                    "EVIDENCE_TOKEN_COUNT_MISMATCH",
                )
                required = _required_reduction(result, case["target"], reclaim_reduction_pct=30)
                _, messages = _prepared_request(
                    document,
                    markdown,
                    goal=case["target"],
                    policy=report["policy"],
                    required_saving_gb=required,
                )
                write_json(directory / "messages.json", messages)
                _require(
                    _capture_inputs(capture, case)[3] == pins, "CAPTURE_CHANGED_DURING_PREPARE"
                )
                row.update(
                    status="ready",
                    reason=None,
                    capture_summary={
                        key: result.get(key)
                        for key in (
                            "run_id",
                            "status",
                            "capture_complete",
                            "cleanup_verified",
                            "steps",
                            "peak_allocated_bytes",
                            "peak_reserved_bytes",
                            "shared_gpu",
                            "gpu_observation_complete",
                        )
                    },
                    evidence_tokens=evidence["token_count"],
                    evidence_quality={
                        "history_complete": document["analysis"]
                        .get("header", {})
                        .get("history_complete"),
                        "peak_is_exact": document["analysis"]
                        .get("header", {})
                        .get("peak_is_exact"),
                        "warnings": document["analysis"].get("header", {}).get("warnings", []),
                    },
                    token_count_domain="cl100k_base evidence.md only; not server billed input",
                    stack_ids=sorted(catalog),
                    prepared_files={
                        name: file_record(directory / name, max_bytes=MAX_DOCUMENT_BYTES)
                        for name in (
                            "evidence/evidence.md",
                            "evidence/evidence.json",
                            "messages.json",
                            "README.truth.md",
                        )
                    },
                    required_saving_gb=required,
                    required_saving_basis=(
                        "Original default reclaim target: 30% of this completed baseline peak."
                        if required is not None
                        else "Unknown: an OOM peak or failed request does not establish memory needed to finish."
                    ),
                    reclaim_reduction_pct=30,
                )
            except (OSError, ValueError, TypeError, KeyError) as error:
                row.update(
                    status="invalid",
                    reason=str(error)
                    if isinstance(error, DiagnosisAcceptanceRefused)
                    else type(error).__name__,
                )
        write_json(output / "preparation.json", report)
    report["ready_count"] = sum(row["status"] == "ready" for row in report["rows"])
    report["ready_for_execution"] = report["ready_count"] == 8
    report["preparation_digest"] = _json_digest(report)
    write_json(output / "preparation.json", report)
    return report


def _verify_preparation(path):
    package = _regular_directory(Path(path).parent)
    prepared = read_json(path, max_bytes=MAX_DOCUMENT_BYTES)
    _require(
        isinstance(prepared, dict) and prepared.get("schema") == SCHEMA,
        "PREPARATION_SCHEMA_INVALID",
    )
    digest = prepared.get("preparation_digest")
    _require(
        digest
        == _json_digest(
            {key: value for key, value in prepared.items() if key != "preparation_digest"}
        ),
        "PREPARATION_CHANGED",
    )
    _require(prepared.get("ready_for_execution") is True, "EIGHT_READY_CAPTURES_REQUIRED")
    _require(
        [row.get("scenario_id") for row in prepared["rows"]] == list(SCENARIO_IDS),
        "ORIGINAL_EIGHT_CASES_REQUIRED",
    )
    root = _regular_directory(prepared["project_root"])
    cases, project_pins = _project_inputs(root)
    _require(project_pins == prepared["project_inputs"], "PROJECT_INPUTS_CHANGED")
    _require(prepared["policy"] == Policy().model_dump(), "DEFAULT_POLICY_REQUIRED")
    for row in prepared["rows"]:
        case_id = row["scenario_id"]
        _require(row["status"] == "ready", "EIGHT_READY_CAPTURES_REQUIRED")
        _, captured_result, _, capture_pins = _capture_inputs(row["capture"], cases[case_id])
        _require(capture_pins == row["capture_inputs"], "CAPTURE_CHANGED_AFTER_PREPARE")
        _require(
            row["required_saving_gb"]
            == _required_reduction(
                captured_result, cases[case_id]["target"], reclaim_reduction_pct=30
            )
            and row.get("reclaim_reduction_pct") == 30,
            "REQUIRED_SAVING_CHANGED",
        )
        directory = package / "cases" / case_id
        for name in (
            "evidence/evidence.md",
            "evidence/evidence.json",
            "messages.json",
            "README.truth.md",
        ):
            _require(
                file_record(directory / name, max_bytes=MAX_DOCUMENT_BYTES)
                == row["prepared_files"][name],
                "PREPARED_EVIDENCE_CHANGED",
            )
        markdown, document, messages = _case_payload(package, row)
        _, expected_messages = _prepared_request(
            document,
            markdown,
            goal=cases[case_id]["target"],
            policy=prepared["policy"],
            required_saving_gb=row["required_saving_gb"],
        )
        _require(messages == expected_messages, "DIAGNOSIS_REQUEST_CHANGED")
    return package, prepared


def _score(row, checked, snapshot):
    diagnosis = checked.diagnosis.model_dump() if checked.diagnosis is not None else None
    causes = diagnosis["root_causes"] if diagnosis else []
    catalog = set(row["stack_ids"])
    refs = [
        {
            "cause_id": cause["id"],
            "references": cause["evidence_refs"],
            "valid_stack_ids": [ref for ref in cause["evidence_refs"] if ref in catalog],
            "invalid_references": [ref for ref in cause["evidence_refs"] if ref not in catalog],
        }
        for cause in causes
    ]
    references_valid = bool(refs) and all(
        item["valid_stack_ids"] and not item["invalid_references"] for item in refs
    )
    first = causes[0]["category"] if causes else None
    expected = row["truth"]["scoreable_category"]
    match = first == expected if first is not None and expected is not None else None
    calls = snapshot["calls"]
    usage = snapshot["usage"]
    identity_valid = (
        len(calls) == 1
        and calls[0].get("outcome") == "response"
        and calls[0].get("model") == ULTRA_MODEL
        and calls[0].get("response_model") == ULTRA_MODEL
    )
    cost = usage.get("total_cost_usd")
    within_cost = money(cost) <= ACTUAL_CALL_LIMIT_USD if cost is not None else None
    complete = (
        checked.valid
        and not checked.requires_supplement
        and diagnosis is not None
        and not diagnosis["needs_more_info"]
    )
    return {
        "diagnosis": diagnosis,
        "diagnosis_valid": checked.valid,
        "issues": [asdict(issue) for issue in checked.issues],
        "requires_supplement": checked.requires_supplement,
        "supplement_executed": False,
        "actual_stack_references": refs,
        "references_valid": bool(references_valid),
        "first_cause": first,
        "expected_category": expected,
        "first_cause_match": match,
        "match_basis": "Exact first root_causes category equals the frozen manifest category; unknown truth remains null. No text/heuristic remapping.",
        "response_identity_valid": identity_valid,
        "actual_cost_within_035": within_cost,
        "complete_diagnosis": complete,
        "row_pass": complete
        and references_valid
        and match is True
        and identity_valid
        and within_cost is True,
    }


def _case_payload(package, row):
    """Use the exact bytes hashed now, not an earlier validation followed by a reread."""
    directory = package / "cases" / row["scenario_id"]
    values = {}
    for name in ("evidence/evidence.md", "evidence/evidence.json", "messages.json"):
        data = read_bytes(directory / name, max_bytes=MAX_DOCUMENT_BYTES)
        _require(
            {"bytes": len(data), "sha256": _digest(data)} == row["prepared_files"][name],
            "PREPARED_EVIDENCE_CHANGED",
        )
        values[name] = data
    return (
        values["evidence/evidence.md"].decode(),
        json.loads(values["evidence/evidence.json"]),
        json.loads(values["messages.json"]),
    )


def _save_response(path, response, *, validation_error=None):
    """Private, bounded assistant-content evidence; never request headers or reasoning text."""
    raw = response.text.encode("utf-8")
    record = {
        "model": response.model,
        "response_model": response.response_model,
        "text": response.text,
        "text_utf8_bytes": len(raw),
        "text_sha256": _digest(raw),
        "text_truncated": False,
        "parsed": getattr(response, "parsed", None),
        "parsed_omitted": False,
        "finish_reason": response.finish_reason,
        "usage": asdict(response.usage) if response.usage is not None else None,
        "cost": response.cost.as_dict(),
        "elapsed_seconds": response.elapsed_seconds,
        "validation": "failed" if validation_error is not None else "passed",
        "validation_reason": validation_error.reason if validation_error is not None else None,
        "content_is_untrusted_data": True,
    }

    def serialized_size():
        return (
            len(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))
            + 1
        )

    if serialized_size() > MAX_RESPONSE_ARTIFACT_BYTES:
        record["parsed_omitted"] = record["parsed"] is not None
        record["parsed"] = None
    if serialized_size() > MAX_RESPONSE_ARTIFACT_BYTES:
        record["text_truncated"] = True
        low, high = 0, len(raw)
        while low < high:
            middle = (low + high + 1) // 2
            record["text"] = raw[:middle].decode("utf-8", errors="ignore")
            if serialized_size() <= MAX_RESPONSE_ARTIFACT_BYTES:
                low = middle
            else:
                high = middle - 1
        record["text"] = raw[:low].decode("utf-8", errors="ignore")
        _require(serialized_size() <= MAX_RESPONSE_ARTIFACT_BYTES, "RESPONSE_METADATA_TOO_LARGE")
    write_json(path, record)


def _prepared_router(router, expected_messages, response_path, *, evidence, policy):
    # Build independently from the revalidated frozen case, not the caller's schema.
    expected_schema = json.dumps(
        build_diagnosis_schema(evidence=evidence, policy=policy),
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    )
    calls = 0

    def chat(role, messages, schema, *, max_tokens, reasoning):
        nonlocal calls
        _require(
            calls == 0
            and role == "diagnose"
            and max_tokens == DIAGNOSIS_MAX_COMPLETION_TOKENS
            and reasoning is True,
            "ONLY_ONE_PREPARED_DIAGNOSIS_ALLOWED",
        )
        _require(messages == expected_messages, "DIAGNOSIS_REQUEST_CHANGED")
        try:
            actual_schema = json.dumps(schema, sort_keys=True, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise DiagnosisAcceptanceRefused("DIAGNOSIS_SCHEMA_CHANGED") from None
        _require(
            isinstance(schema, dict) and actual_schema == expected_schema,
            "DIAGNOSIS_SCHEMA_CHANGED",
        )
        calls += 1
        try:
            response = router.chat(
                role, messages, schema, max_tokens=max_tokens, reasoning=reasoning
            )
        except ResponseValidationError as error:
            if error.response is not None:
                _save_response(response_path, error.response, validation_error=error)
            raise
        _save_response(response_path, response)
        return response

    return SimpleNamespace(chat=chat)


def _financial_checks(snapshot):
    """The same post-finalization checks apply to valid and rejected structured output."""
    calls = snapshot.get("calls")
    usage = snapshot.get("usage")
    budget = snapshot.get("budget")
    identity = (
        isinstance(calls, list)
        and len(calls) == 1
        and calls[0].get("outcome") == "response"
        and calls[0].get("http_status") == 200
        and calls[0].get("model") == ULTRA_MODEL
        and calls[0].get("response_model") == ULTRA_MODEL
        and calls[0].get("settled") is True
    )
    cost = usage.get("total_cost_usd") if isinstance(usage, dict) else None
    within_cost = money(cost) <= ACTUAL_CALL_LIMIT_USD if cost is not None else None
    clear = (
        isinstance(budget, dict)
        and budget.get("unknown_attempts") == 0
        and budget.get("pending_attempts") == 0
        and budget.get("total_actual_usd") is not None
        and budget.get("halt_reason") is None
        and budget.get("billing_bound_unresolved") is False
        and budget.get("dispatch_blocked") is False
        and budget.get("run_budget_exceeded") is False
        and budget.get("status") == "closed"
        and snapshot.get("cleanup_errors") == []
        and cost is not None
        and money(budget["total_actual_usd"]) == money(cost)
    )
    if not isinstance(usage, dict):
        reason = "ACCOUNTING_UNAVAILABLE"
    elif usage.get("complete") is not True or usage.get("unknown_cost_calls") != 0 or cost is None:
        reason = "UNKNOWN_BILLING"
    elif not identity:
        reason = "RESPONSE_IDENTITY_OR_CALL_COUNT_INVALID"
    elif within_cost is not True:
        reason = "ACTUAL_CALL_COST_EXCEEDS_035"
    elif not clear:
        reason = "LEDGER_NOT_CLEAR"
    else:
        reason = None
    return {
        "response_identity_valid": bool(identity),
        "actual_cost_within_035": within_cost,
        "ledger_clear": bool(clear),
    }, reason


def execute_diagnosis_acceptance(
    prepared_path,
    *,
    profile_path,
    run_limit_usd,
    campaign_limit_usd,
    daily_limit_usd,
    min_case_interval_seconds=0,
    execute=False,
    live_authorized=False,
    transport=None,
    env_file=None,
):
    """Explicit execution only. Unknown charges stop the batch and remain in the shared ledger."""
    _require(execute is True and live_authorized is True, "EXPLICIT_LIVE_AUTHORIZATION_REQUIRED")
    _require(
        transport is None or isinstance(transport, httpx.MockTransport),
        "ONLY_OFFLINE_MOCK_TRANSPORT_ALLOWED",
    )
    _require(
        type(min_case_interval_seconds) in {int, float}
        and 0 <= min_case_interval_seconds <= 60
        and math.isfinite(min_case_interval_seconds),
        "CASE_INTERVAL_MUST_BE_FINITE_0_TO_60_SECONDS",
    )
    run_cap, campaign_cap = money(run_limit_usd), money(campaign_limit_usd)
    _require(
        run_cap > 0 and campaign_cap > 0 and money(daily_limit_usd) > 0, "POSITIVE_BUDGETS_REQUIRED"
    )
    package, prepared = _verify_preparation(prepared_path)
    _require(
        package.is_relative_to(Path(prepared["project_root"]) / "runs"),
        "PRIVATE_RUNS_DIRECTORY_REQUIRED",
    )
    execution = package / "execution"
    execution.mkdir(mode=0o700, exist_ok=False)
    provenance = "offline_fixture" if transport is not None else "live"
    result = {
        "schema": SCHEMA,
        "mode": "execute",
        "provenance": provenance,
        "preparation_digest": prepared["preparation_digest"],
        "accepted": False,
        "admission_cap_per_case_usd": str(run_cap),
        "campaign_admission_limit_usd": str(campaign_cap),
        "actual_acceptance_limit_per_call_usd": "0.35",
        "diagnosis_max_completion_tokens": DIAGNOSIS_MAX_COMPLETION_TOKENS,
        "diagnosis_reasoning": True,
        "min_case_interval_seconds": min_case_interval_seconds,
        "rows": [],
        "stop_reason": None,
        "first_cause_matches": 0,
        "denominator": 8,
        "required_matches": 6,
        "known_cost_usd": "0",
        "total_cost_usd": "0",
        "limitations": [
            "Mock transport is never live acceptance.",
            "A local-estimate profile does not provide a hard provider spending ceiling.",
        ],
    }
    write_json(execution / "result.json", result)
    known = Decimal(0)
    all_costs_known = True
    last_case_started = None
    execution_started = time.monotonic()
    for prepared_row in prepared["rows"]:
        case_id = prepared_row["scenario_id"]
        row = {
            "scenario_id": case_id,
            "status": "not_executed",
            "first_cause_match": None,
            "row_pass": False,
            "truth": prepared_row["truth"],
            "capture": prepared_row["capture"],
        }
        result["rows"].append(row)
        if result["stop_reason"] is not None:
            continue
        with localcontext() as decimal_context:
            decimal_context.prec = 256
            remaining = campaign_cap - known
        if remaining <= 0:
            result["stop_reason"] = "CAMPAIGN_BUDGET_EXHAUSTED"
            continue
        cap = min(run_cap, remaining)
        active = None
        case_error = None
        started = None
        wait_started = time.monotonic()
        try:
            if last_case_started is not None:
                while (
                    delay := last_case_started + min_case_interval_seconds - time.monotonic()
                ) > 0:
                    time.sleep(delay)
            started = time.monotonic()
            last_case_started = started
            row["case_start_offset_seconds"] = started - execution_started
            markdown, document, expected_messages = _case_payload(package, prepared_row)
            document, rebuilt_messages = _prepared_request(
                document,
                markdown,
                goal=prepared_row["target"],
                policy=prepared["policy"],
                required_saving_gb=prepared_row["required_saving_gb"],
            )
            _require(rebuilt_messages == expected_messages, "DIAGNOSIS_REQUEST_CHANGED")
            with acceptance_run(
                case_id="diagnosis-" + case_id,
                artifact_dir=execution / case_id,
                profile_path=profile_path,
                run_limit_usd=str(cap),
                daily_limit_usd=daily_limit_usd,
                execute=execute,
                live_authorized=live_authorized,
                project_root=prepared["project_root"],
                transport=transport,
                env_file=env_file,
            ) as active:
                _require(
                    active.bundle.client.config.model_for("diagnose").model_id == ULTRA_MODEL,
                    "EXACT_ULTRA_ROLE_REQUIRED",
                )
                _require(
                    prepared_row["evidence_tokens"] <= active.bundle.evidence_token_budget,
                    "REVIEWED_EVIDENCE_BUDGET_EXCEEDED",
                )
                checked = diagnose_with_router(
                    _prepared_router(
                        active.router,
                        expected_messages,
                        execution / case_id / "model-response.json",
                        evidence=document,
                        policy=prepared["policy"],
                    ),
                    markdown,
                    evidence=document,
                    goal=prepared_row["target"],
                    policy=prepared["policy"],
                    required_saving_gb=prepared_row["required_saving_gb"],
                    max_supplements=0,
                )
                snapshot = active.snapshot()
                row.update(
                    _score(prepared_row, checked, snapshot), status="responded", runtime=snapshot
                )
                write_json(execution / case_id / "diagnosis.json", row)
                active.store.update_run(active.run_id, status="completed", acceptance_case=case_id)
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - persist sanitized partial acceptance
            case_error = error
            row.update(status="failed", error_type=type(error).__name__)
            if isinstance(error, ResponseValidationError):
                row["validation_reason"] = error.reason
            if isinstance(error, DiagnosisAcceptanceRefused):
                row["reason"] = str(error)
            result["stop_reason"] = (
                str(error)
                if isinstance(error, DiagnosisAcceptanceRefused)
                else type(error).__name__
            )
        receipt = execution / case_id / "runtime.json"
        if receipt.exists():
            row["runtime_receipt"] = str(receipt)
            try:
                row["runtime"] = read_json(receipt, max_bytes=MAX_DOCUMENT_BYTES)
            except (OSError, ValueError, TypeError):
                row["accounting_available"] = False
                row.pop("runtime", None)
        now = time.monotonic()
        row["interval_wait_seconds"] = (started if started is not None else now) - wait_started
        row["elapsed_seconds"] = now - started if started is not None else 0.0
        snapshot = row.get("runtime", {})
        usage = snapshot.get("usage") or {}
        total = usage.get("total_cost_usd")
        if active is not None and not isinstance(snapshot.get("usage"), dict):
            # A failed final receipt write must not turn possibly dispatched work into $0.
            row["accounting_available"] = False
            all_costs_known = False
            result["stop_reason"] = "ACCOUNTING_UNAVAILABLE"
        if usage.get("unknown_cost_calls", 0) or (snapshot.get("calls") and total is None):
            all_costs_known = False
            result["stop_reason"] = "UNKNOWN_BILLING"
        if usage.get("known_cost_usd") is not None:
            with localcontext() as decimal_context:
                decimal_context.prec = 256
                known += money(usage["known_cost_usd"])
        if (
            snapshot.get("calls")
            or case_error is None
            or isinstance(case_error, ResponseValidationError)
        ):
            financial, financial_reason = _financial_checks(snapshot)
            row.update(financial)
            row["row_pass"] = row["row_pass"] and financial_reason is None
            if financial_reason is not None:
                result["stop_reason"] = financial_reason
            elif isinstance(case_error, ResponseValidationError):
                # A known-billed invalid answer fails this case, not the independent next one.
                result["stop_reason"] = None
                row["continued_after_validation_failure"] = True
        if known > campaign_cap:
            result["stop_reason"] = "ACTUAL_CAMPAIGN_COST_EXCEEDED"
        result["known_cost_usd"] = str(known)
        result["total_cost_usd"] = str(known) if all_costs_known else None
        if (execution / case_id).is_dir():
            write_json(execution / case_id / "diagnosis.json", row)
        write_json(execution / "result.json", result)
    matches = sum(row.get("first_cause_match") is True for row in result["rows"])
    complete = len(result["rows"]) == 8 and all(
        row["status"] == "responded" for row in result["rows"]
    )
    structural = complete and all(
        row.get("complete_diagnosis")
        and row.get("references_valid")
        and row.get("response_identity_valid")
        and row.get("actual_cost_within_035") is True
        for row in result["rows"]
    )
    result.update(
        first_cause_matches=matches, complete=complete, structural_gates_passed=bool(structural)
    )
    result["accepted"] = (
        provenance == "live"
        and structural
        and matches >= REQUIRED_MATCHES
        and result["stop_reason"] is None
    )
    result["fixture_gates_passed"] = (
        provenance == "offline_fixture"
        and structural
        and matches >= REQUIRED_MATCHES
        and result["stop_reason"] is None
    )
    write_json(execution / "result.json", result)
    return result
