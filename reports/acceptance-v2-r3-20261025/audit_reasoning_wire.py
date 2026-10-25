"""Read-only r3 prepared-request/usage audit; never publishes prompts or reasoning text."""

import argparse
import copy
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/acceptance-v2-r3-20261025"
EXECUTION = OUT / "execution.json"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CALLS = 2048
# The reviewed r2 profile uses this exact wire field, not a default/alias inference.
EXPECTED_CAP_FIELD = "max_completion_tokens"
CAP_FIELDS = {"max_tokens", "max_completion_tokens"}
EXPECTED_THINKING = {"diagnose": True, "patcher": False}
HEX = re.compile(r"[0-9a-f]{64}")
FINISH_REASONS = {"stop", "length", "tool_calls", "function_call", "content_filter"}
ROLES = {
    "diagnose": ("nvidia/Nemotron-3-Ultra-550b-a55b", 16384),
    "patcher": ("nvidia/nemotron-3-super-120b-a12b", 4000),
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bounded_json(path):
    require(path.is_file() and not path.is_symlink(), "missing or symbolic JSON input")
    require(path.stat().st_size <= MAX_JSON_BYTES, "JSON input exceeds size bound")
    raw = path.read_bytes()
    require(len(raw) <= MAX_JSON_BYTES, "JSON input grew beyond bound")
    value = json.loads(raw)
    require(isinstance(value, dict), "JSON object required")
    return value, digest(raw)


def nonnegative(value):
    return type(value) is int and value >= 0


def analyze_call(row):
    """Whitelist metadata only; missing persisted values remain unknown."""
    record = row["data"]
    role = row["role"]
    model, expected_cap = ROLES[role]
    problems = []
    if record.get("model") != row["model"] or record.get("role") != role:
        problems.append("store_identity_mismatch")
    if row["model"] != model:
        problems.append("unexpected_model")
    evidence = record.get("request_evidence")
    payload = None
    metadata_valid = None
    payload_valid = None
    state = "unknown"
    wire_hash = stored_hash = None
    if isinstance(evidence, dict):
        state = evidence.get("payload_status")
        if state not in {"captured", "redacted", "omitted_size", "invalid_json"}:
            state = "unknown"
        metadata_valid = (
            type(evidence.get("schema_version")) is int
            and evidence["schema_version"] == 1
            and evidence.get("capture_point") == "httpx_pre_transport"
            and bool(HEX.fullmatch(str(evidence.get("wire_body_sha256", ""))))
            and type(evidence.get("wire_body_utf8_bytes")) is int
            and evidence["wire_body_utf8_bytes"] > 0
            and evidence.get("delivery_confirmed") is False
        )
        if metadata_valid:
            wire_hash = evidence["wire_body_sha256"]
        else:
            problems.append("request_metadata_invalid")
        if state in {"captured", "redacted"}:
            candidate = evidence.get("payload")
            stored_hash = evidence.get("stored_payload_sha256")
            payload_valid = (
                isinstance(candidate, dict)
                and bool(HEX.fullmatch(str(stored_hash)))
                and len(canonical(candidate)) <= 256 * 1024
                and digest(canonical(candidate)) == stored_hash
            )
            if not payload_valid:
                problems.append("request_payload_invalid")
            elif metadata_valid:
                payload = candidate
        elif evidence.get("payload") is not None:
            problems.append("unexpected_uncaptured_payload")

    enabled = cap = cap_field = request_model_matches = None
    if payload is not None:
        request_model_matches = payload.get("model") == row["model"] == model
        if not request_model_matches:
            problems.append("request_model_mismatch")
        template = payload.get("chat_template_kwargs")
        value = template.get("enable_thinking") if isinstance(template, dict) else None
        enabled = value if type(value) is bool else None
        present_caps = CAP_FIELDS.intersection(payload)
        if len(present_caps) > 1:
            problems.append("conflicting_output_cap_fields")
        elif present_caps:
            cap_field = next(iter(present_caps))
            value = payload[cap_field]
            cap = value if type(value) is int and value > 0 else None
            if cap_field != EXPECTED_CAP_FIELD:
                problems.append("unexpected_output_cap_field")

    usage = record.get("usage")
    completion = reasoning = None
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        output = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        valid = all(nonnegative(x) for x in (prompt, output, total)) and total == prompt + output
        if valid:
            completion = output
            value = usage.get("reasoning_tokens")
            if value is None or (nonnegative(value) and value <= completion):
                reasoning = value
            else:
                problems.append("invalid_reasoning_token_count")
        else:
            problems.append("invalid_usage_totals")

    finish = record.get("finish_reason")
    finish = finish if isinstance(finish, str) and finish in FINISH_REASONS else None
    outcome = record.get("outcome")
    known_outcomes = {
        "response",
        "http_error",
        "timeout",
        "transport_error",
        "response_error",
        "interrupted",
        "not_dispatched",
    }
    outcome = outcome if isinstance(outcome, str) and outcome in known_outcomes else "unknown"
    return {
        "call_id": row["id"],
        "run_id": row["run_id"],
        "role": role,
        "model": row["model"] if row["model"] == model else "unexpected",
        "outcome": outcome,
        "request_capture_state": state,
        "request_metadata_valid": metadata_valid,
        "request_payload_valid": payload_valid,
        "request_model_matches": request_model_matches,
        "wire_body_sha256": wire_hash,
        "stored_payload_sha256": stored_hash if payload_valid else None,
        "enable_thinking": enabled,
        "expected_enable_thinking": EXPECTED_THINKING[role],
        "thinking_matches": None if enabled is None else enabled == EXPECTED_THINKING[role],
        "expected_output_cap_field": EXPECTED_CAP_FIELD,
        "observed_output_cap_field": cap_field,
        "expected_output_cap_tokens": expected_cap,
        "observed_output_cap_tokens": cap,
        "cap_field_matches": None if cap_field is None else cap_field == EXPECTED_CAP_FIELD,
        "cap_matches": None
        if cap is None
        else cap == expected_cap and cap_field == EXPECTED_CAP_FIELD,
        "completion_tokens": completion,
        "reasoning_tokens": reasoning,
        "finish_reason": finish,
        "finish_reason_basis": "persisted_call_field"
        if finish is not None
        else "not_persisted_or_unknown",
        "length_finish": None if finish is None else finish == "length",
        "completion_reached_request_cap": None
        if completion is None or cap is None
        else completion == cap,
        "integrity_issues": problems,
        "provider_delivery_or_ingestion_proven": False,
    }


def aggregate(rows):
    def counts(key, expected):
        return {
            "matching": sum(row[key] == expected for row in rows if row[key] is not None),
            "contradicted": sum(row[key] != expected for row in rows if row[key] is not None),
            "unknown": sum(row[key] is None for row in rows),
        }

    known_reasoning = [
        row["reasoning_tokens"] for row in rows if row["reasoning_tokens"] is not None
    ]
    unknown_reasoning = len(rows) - len(known_reasoning)
    return {
        "attempts": len(rows),
        "enable_thinking_true": counts("enable_thinking", True),
        "enable_thinking_expected": counts("thinking_matches", True),
        "enable_thinking_true_scope": "descriptive count only; use enable_thinking_expected for the role contract",
        "output_cap_expected": counts("cap_matches", True),
        "output_cap_field_expected": counts("cap_field_matches", True),
        "reasoning_tokens_known_subtotal": sum(known_reasoning) if known_reasoning else None,
        "reasoning_tokens_unknown_attempts": unknown_reasoning,
        "reasoning_tokens_total": sum(known_reasoning) if rows and not unknown_reasoning else None,
        "finish_reasons": dict(Counter(row["finish_reason"] or "unknown" for row in rows)),
        "length_finish": counts("length_finish", True),
        "completion_reached_cap": counts("completion_reached_request_cap", True),
        "outcomes": dict(Counter(row["outcome"] for row in rows)),
        "integrity_issue_attempts": sum(bool(row["integrity_issues"]) for row in rows),
    }


def audit(execution_path, campaign_path):
    require(execution_path.resolve() == EXECUTION, "only explicit r1 execution receipt accepted")
    execution, execution_sha = bounded_json(execution_path)
    require(execution.get("fixed_acceptance_denominator") == 9, "nine-case execution required")
    require(execution.get("completed_utc"), "completed execution receipt required")
    references = execution.get("campaigns")
    require(isinstance(references, list) and len(references) == 1, "one new campaign required")
    ref = references[0]
    require(isinstance(ref, dict), "campaign reference object required")
    relative = Path(ref.get("path", ""))
    require(not relative.is_absolute() and ".." not in relative.parts, "unsafe campaign path")
    expected_path = ROOT / relative
    require(
        campaign_path.resolve() == expected_path.resolve(),
        "explicit campaign does not match receipt",
    )
    require(
        expected_path.is_relative_to(ROOT / "runs/evaluation/live"), "live campaign path required"
    )
    campaign, campaign_sha = bounded_json(campaign_path)
    require(campaign_sha == ref.get("sha256"), "campaign receipt hash mismatch")
    require(campaign.get("status") == "finished", "unfinished campaign")
    cases = campaign.get("rows")
    require(isinstance(cases, list) and len(cases) == 9, "nine rows required")
    require(all(isinstance(row, dict) for row in cases), "invalid scenario row")
    # The approved manifest supplies the fixed scenario IDs; no historical result is read.
    manifest, manifest_sha = bounded_json(ROOT / "eval/mvp_phase1_v2.yaml")
    planned = manifest.get("scenarios", [])
    ids = [row.get("id") for row in planned if isinstance(row, dict)]
    require(len(ids) == 9 and len(set(ids)) == 9, "fixed nine manifest slots required")
    require(
        {row.get("scenario_id") for row in cases} == set(ids),
        "scenario set differs from manifest",
    )
    require(campaign.get("manifest_sha256") == manifest_sha, "campaign manifest hash mismatch")
    require(
        all(row.get("condition") == "full_ultra" for row in cases), "unexpected campaign condition"
    )
    run_ids = [row.get("run_id") for row in cases]
    require(
        all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{32}", x) for x in run_ids),
        "real run IDs required",
    )
    require(len(set(run_ids)) == 9, "duplicate run IDs")
    con = sqlite3.connect((ROOT / "runs/headroom.db").as_uri() + "?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only = ON")
        con.execute("BEGIN")
        placeholders = ",".join("?" for _ in run_ids)
        records = con.execute(
            f"SELECT id,run_id,model,role,data_json FROM llm_calls WHERE run_id IN ({placeholders}) ORDER BY id LIMIT ?",
            (*run_ids, MAX_CALLS + 1),
        ).fetchall()
        require(len(records) <= MAX_CALLS, "attempt count exceeds bound")
        observed = []
        selected = []
        for call_id, run_id, model, role, raw in records:
            require(
                isinstance(raw, str) and len(raw.encode()) <= 1024 * 1024,
                "call record exceeds bound",
            )
            observed.append([call_id, run_id, model, role, digest(raw.encode())])
            if role not in ROLES:
                continue
            data = json.loads(raw)
            require(isinstance(data, dict), "invalid call JSON")
            selected.append(
                analyze_call(
                    {"id": call_id, "run_id": run_id, "model": model, "role": role, "data": data}
                )
            )
        require(
            {row["run_id"] for row in selected} == set(run_ids),
            "not all nine runs have diagnosis/patch attempts",
        )
    finally:
        con.close()
    return {
        "schema": "headroom.reasoning_wire_audit.v2",
        "expected_enable_thinking_by_role": dict(EXPECTED_THINKING),
        "execution_sha256": execution_sha,
        "campaign_sha256": campaign_sha,
        "manifest_sha256": manifest_sha,
        "fixed_scenario_denominator": 9,
        "campaign_run_ids": run_ids,
        "all_roles_attempt_count": len(observed),
        "call_record_inventory_sha256": digest(canonical(observed)),
        "scope": "supplementary request and persisted usage audit; no acceptance score or billing recalculation",
        "request_evidence_boundary": "SHA-checked local httpx pre-transport copy, not provider ingestion proof",
        "finish_reason_boundary": "This audit reads Store call rows only. Patch response artifacts separately persist finish_reason; they are outside this audit. Missing Store fields stay unknown",
        "length_boundary": "Reaching max_tokens does not establish a length finish or explain parse failure",
        "causal_boundary": "Multiple contracts changed together; no accuracy change is attributed solely to reasoning",
        "hidden_reasoning_or_request_contents_copied": False,
        "new_provider_calls": 0,
        "new_gpu_runs": 0,
        "by_role": {
            role: aggregate([row for row in selected if row["role"] == role]) for role in ROLES
        },
        "attempts": selected,
    }


def self_test():
    payload = {
        "model": ROLES["diagnose"][0],
        "max_completion_tokens": 16384,
        "chat_template_kwargs": {"enable_thinking": True},
        "messages": [{"content": "PRIVATE_PROMPT"}],
    }
    captured = {
        "schema_version": 1,
        "capture_point": "httpx_pre_transport",
        "wire_body_sha256": "a" * 64,
        "wire_body_utf8_bytes": 100,
        "delivery_confirmed": False,
        "payload_status": "captured",
        "payload": payload,
        "stored_payload_sha256": digest(canonical(payload)),
    }
    row = {
        "id": 1,
        "run_id": "a" * 32,
        "model": payload["model"],
        "role": "diagnose",
        "data": {
            "role": "diagnose",
            "model": payload["model"],
            "outcome": "response",
            "request_evidence": captured,
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 16384,
                "total_tokens": 16386,
                "reasoning_tokens": 4096,
            },
            "reasoning_content": "PRIVATE_REASONING",
        },
    }
    checks = []

    def check(value):
        checks.append(bool(value))
        assert value

    result = analyze_call(row)
    check(result["enable_thinking"] is True and result["cap_matches"] is True)
    check(result["reasoning_tokens"] == 4096)
    check(result["completion_reached_request_cap"] is True and result["length_finish"] is None)
    check("PRIVATE" not in json.dumps(result))
    check(aggregate([result])["reasoning_tokens_total"] == 4096)
    for field, value in [
        ("reasoning_tokens", None),
        ("reasoning_tokens", True),
        ("reasoning_tokens", 16385),
    ]:
        changed = copy.deepcopy(row)
        changed["data"]["usage"][field] = value
        check(analyze_call(changed)["reasoning_tokens"] is None)
    changed = copy.deepcopy(row)
    changed["data"]["usage"]["reasoning_tokens"] = 0
    check(analyze_call(changed)["reasoning_tokens"] == 0)
    changed = copy.deepcopy(row)
    changed["data"]["finish_reason"] = "length"
    check(analyze_call(changed)["length_finish"] is True)
    changed = copy.deepcopy(row)
    changed["data"]["request_evidence"]["stored_payload_sha256"] = "b" * 64
    check(analyze_call(changed)["enable_thinking"] is None)
    changed = copy.deepcopy(row)
    changed["data"].pop("request_evidence")
    check(analyze_call(changed)["observed_output_cap_tokens"] is None)
    check(aggregate([analyze_call(changed)])["enable_thinking_true"]["unknown"] == 1)
    changed = copy.deepcopy(row)
    changed["data"].pop("usage")
    check(aggregate([analyze_call(changed)])["reasoning_tokens_total"] is None)
    check(aggregate([])["reasoning_tokens_total"] is None)
    for role, (model, cap) in ROLES.items():
        changed = copy.deepcopy(row)
        changed.update(role=role, model=model)
        changed["data"].update(role=role, model=model)
        evidence = changed["data"]["request_evidence"]
        body = evidence["payload"]
        body.update(model=model, max_completion_tokens=cap)
        evidence["stored_payload_sha256"] = digest(canonical(body))
        check(analyze_call(changed)["cap_matches"] is True)
        for value in (True, False):
            body["chat_template_kwargs"]["enable_thinking"] = value
            evidence["stored_payload_sha256"] = digest(canonical(body))
            actual = analyze_call(changed)
            check(actual["enable_thinking"] is value)
            check(actual["expected_enable_thinking"] is EXPECTED_THINKING[role])
            check(actual["thinking_matches"] is (value == EXPECTED_THINKING[role]))
            summary = aggregate([actual])
            check(
                summary["enable_thinking_expected"]["matching"]
                == int(value == EXPECTED_THINKING[role])
            )
            check(summary["enable_thinking_true"]["matching"] == int(value))
        for value in (None, 0, "false"):
            body["chat_template_kwargs"]["enable_thinking"] = value
            evidence["stored_payload_sha256"] = digest(canonical(body))
            actual = analyze_call(changed)
            check(actual["thinking_matches"] is None)
            check(aggregate([actual])["enable_thinking_expected"]["unknown"] == 1)
        body.pop("chat_template_kwargs")
        evidence["stored_payload_sha256"] = digest(canonical(body))
        check(analyze_call(changed)["thinking_matches"] is None)
    changed = copy.deepcopy(row)
    evidence = changed["data"]["request_evidence"]
    evidence["payload"]["max_completion_tokens"] = 4000
    evidence["stored_payload_sha256"] = digest(canonical(evidence["payload"]))
    check(analyze_call(changed)["cap_matches"] is False)
    evidence["payload"]["max_completion_tokens"] = True
    evidence["stored_payload_sha256"] = digest(canonical(evidence["payload"]))
    check(analyze_call(changed)["observed_output_cap_tokens"] is None)
    evidence["capture_point"] = "not_transport"
    check(analyze_call(changed)["enable_thinking"] is None)
    changed = copy.deepcopy(row)
    changed["data"]["request_evidence"]["payload_status"] = "redacted"
    check(analyze_call(changed)["enable_thinking"] is True)
    changed = copy.deepcopy(row)
    changed["data"]["finish_reason"] = "PRIVATE_REASONING"
    check(analyze_call(changed)["finish_reason"] is None)
    # Recognize the legacy spelling, but never accept it as the reviewed profile field.
    changed = copy.deepcopy(row)
    evidence = changed["data"]["request_evidence"]
    body = evidence["payload"]
    body["max_tokens"] = body.pop("max_completion_tokens")
    evidence["stored_payload_sha256"] = digest(canonical(body))
    result = analyze_call(changed)
    check(result["observed_output_cap_field"] == "max_tokens")
    check(result["observed_output_cap_tokens"] == 16384 and result["cap_matches"] is False)
    check("unexpected_output_cap_field" in result["integrity_issues"])
    body.pop("max_tokens")
    evidence["stored_payload_sha256"] = digest(canonical(body))
    check(analyze_call(changed)["cap_matches"] is None)
    for second_value in (16384, 4000):
        body.update(max_tokens=second_value, max_completion_tokens=16384)
        evidence["stored_payload_sha256"] = digest(canonical(body))
        result = analyze_call(changed)
        check(result["observed_output_cap_tokens"] is None and result["cap_matches"] is None)
        check("conflicting_output_cap_fields" in result["integrity_issues"])
    try:
        audit(OUT / "missing-execution.json", ROOT / "missing-campaign.json")
    except ValueError:
        check(True)
    else:
        check(False)
    return {
        "self_test": "passed",
        "checks": len(checks),
        "new_provider_calls": 0,
        "new_gpu_runs": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--execution", type=Path)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        require(
            args.execution is None and args.campaign is None and args.output is None,
            "self-test cannot use live inputs",
        )
        print(json.dumps(self_test(), indent=2))
        return
    require(
        args.execution is not None and args.campaign is not None and args.output is not None,
        "explicit completed r3 execution, campaign and fresh output required",
    )
    require(args.output.parent.resolve() == OUT, "output must be in r3 report directory")
    result = audit(args.execution, args.campaign)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "attempts": len(result["attempts"]),
                "integrity_issue_attempts": sum(
                    bool(row["integrity_issues"]) for row in result["attempts"]
                ),
            }
        )
    )
    raise SystemExit(int(any(row["integrity_issues"] for row in result["attempts"])))


if __name__ == "__main__":
    main()
