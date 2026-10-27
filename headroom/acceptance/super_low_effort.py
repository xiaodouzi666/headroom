"""One reviewed low-effort request; no execution or profile promotion on import.

This module must be independently reviewed and frozen before live use. A passing
sample proves usable request/output compatibility, not provider recognition or a
reduction in reasoning tokens.
"""

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from headroom.acceptance.common import acceptance_run, file_record, read_json, write_json
from headroom.config import SUPER_MODEL
from headroom.llm.client import low_effort_probe_fingerprint
from headroom.patch_spans import SourceSpanProposal, normalize_span_edits, source_span_document
from headroom.runtime import PROJECT_ROOT, read_live_profile

SCOPE = "super_low_effort_schema_code_probe_v1"
MAX_COMPLETION = 4000
MAX_NET_RESERVATION = Decimal("0.0823")
SOURCE_NAME = "example.py"
CODE_FILES = (
    "headroom/config.py",
    "headroom/llm/client.py",
    "headroom/llm/router.py",
    "headroom/runtime.py",
    "headroom/acceptance/common.py",
    "headroom/acceptance/super_low_effort.py",
    "headroom/patch_spans.py",
    "headroom/budget.py",
    "headroom/ledger_path.py",
    "headroom/llm/cost.py",
    "headroom/llm/request_audit.py",
    "headroom/store/db.py",
)
SOURCE = (
    "def average(values):\n"
    "    total = 0.0\n"
    "    for value in values:\n"
    "        total += value\n"
    "    return total / len(values)\n"
)


def _sdk_body(profile, messages):
    schema = SourceSpanProposal.model_json_schema()
    routed = [
        {
            "role": "system",
            "content": (
                "Return only valid JSON matching this schema, without markdown or commentary.\n"
                + json.dumps(schema, ensure_ascii=False, allow_nan=False)
            ),
        },
        *messages,
    ]
    return {
        "model": SUPER_MODEL,
        "messages": routed,
        "max_completion_tokens": MAX_COMPLETION,
        "timeout": profile.models["super"].timeout_seconds,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "headroom_response", "schema": schema},
        },
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}},
    }


def _profile_bound(profile, body):
    model = profile.runtime_config().model_for("patcher")
    if model.model_id != SUPER_MODEL or model.output_cap_field != "max_completion_tokens":
        raise ValueError("Probe requires the exact reviewed Super identity and output cap")
    bound = profile.models["super"].billing.upper_usd(model, body)
    if bound > MAX_NET_RESERVATION:
        raise ValueError("Probe reservation exceeds its frozen net ceiling")
    return bound


def prepare_low_effort_probe(directory, profile_path, *, daily_limit_usd):
    """Write source/manifest only. This does not read credentials or send requests."""
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_root = directory / "source"
    source_root.mkdir(mode=0o700)
    (source_root / SOURCE_NAME).write_text(SOURCE, encoding="utf-8")
    profile_path = Path(profile_path).resolve()
    old_hash = file_record(profile_path, 256 * 1024)["sha256"]
    profile = read_live_profile(profile_path)
    if file_record(profile_path, 256 * 1024)["sha256"] != old_hash:
        raise ValueError("Profile changed while preparing the probe")
    messages = [
        {
            "role": "system",
            "content": (
                "Produce one source-bound code edit. Preserve the existing iteration "
                "and nonempty-input behavior. Return the requested JSON only."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": "Make average([]) return 0.0 by adding an early empty-input guard.",
                    "sources": {SOURCE_NAME: source_span_document(source_root, SOURCE_NAME)},
                    "constraints": {
                        "allowed_paths": [SOURCE_NAME],
                        "env_changes": {},
                        "cli_changes": [],
                        "no_new_imports": True,
                    },
                },
                allow_nan=False,
            ),
        },
    ]
    body = _sdk_body(profile, messages)
    manifest = {
        "scope": SCOPE,
        "prepared_dir": str(directory),
        "profile_path": str(profile_path),
        "profile_sha256": old_hash,
        "request_sha256": low_effort_probe_fingerprint(body),
        "messages": messages,
        "source_files": {
            name: file_record(PROJECT_ROOT / name, 2 * 1024 * 1024) for name in CODE_FILES
        },
        "source": file_record(source_root / SOURCE_NAME, 64 * 1024),
        "source_name": SOURCE_NAME,
        "reservation_upper_usd": str(_profile_bound(profile, body)),
        "run_limit_usd": str(MAX_NET_RESERVATION),
        "daily_limit_usd": str(daily_limit_usd),
        "max_completion_tokens": MAX_COMPLETION,
        "sdk_retries": 0,
        "client_retries": 0,
        "maximum_dispatches": 1,
        "promote_profile": False,
    }
    write_json(directory / "prepared.json", manifest)
    # Root must independently review the source diff, request, profile, price,
    # current pool/halts, and R4 terminal state, then create a separate receipt.
    write_json(
        directory / "freeze-template.json",
        {
            "scope": SCOPE,
            "reviewed": False,
            "r4_terminal": False,
            "prepared_sha256": file_record(directory / "prepared.json", 256 * 1024)["sha256"],
            "profile_sha256": old_hash,
            "request_sha256": manifest["request_sha256"],
            "run_limit_usd": manifest["run_limit_usd"],
            "daily_limit_usd": manifest["daily_limit_usd"],
            "source_revision": "ROOT_MUST_FILL",
            "reviewer": "ROOT_MUST_FILL",
        },
    )
    return manifest


def _validate_edit(parsed, source_root):
    proposal = SourceSpanProposal.model_validate(parsed, strict=True)
    if not proposal.edits or proposal.env_changes or proposal.cli_changes:
        raise ValueError("Probe requires a nonempty source-only edit")
    normalize_span_edits(proposal, source_root, allowed_source_paths=(SOURCE_NAME,))
    document = source_span_document(source_root, SOURCE_NAME)
    ids = {row["id"]: i for i, row in enumerate(document["lines"])}
    lines = [row["text"] for row in document["lines"]]
    for edit in sorted(proposal.edits, key=lambda e: ids[e.start_id], reverse=True):
        lines[ids[edit.start_id] : ids[edit.end_id] + 1] = edit.new_lines
    # Never execute generated code. This validates anchored edit and syntax only.
    candidate = "\n".join(lines) + "\n"
    ast.parse(candidate, filename=SOURCE_NAME)
    return hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def execute_low_effort_probe(
    prepared_dir,
    freeze_path,
    artifact_dir,
    *,
    expected_freeze_sha256,
    execute=False,
    live_authorized=False,
    project_root=PROJECT_ROOT,
    transport=None,
    env_file=None,
):
    """One frozen probe using the existing shared ledger and runtime callbacks."""
    if execute is not True or live_authorized is not True:
        raise ValueError("Explicit execution and live authorization are required")
    if file_record(freeze_path, 256 * 1024)["sha256"] != expected_freeze_sha256:
        raise ValueError("Root freeze receipt hash differs")
    freeze = read_json(freeze_path, 256 * 1024)
    prepared_dir = Path(prepared_dir).resolve()
    manifest_path = prepared_dir / "prepared.json"
    manifest = read_json(manifest_path, 256 * 1024)
    if (
        freeze.get("scope") != SCOPE
        or freeze.get("reviewed") is not True
        or freeze.get("r4_terminal") is not True
        or freeze.get("prepared_sha256") != file_record(manifest_path, 256 * 1024)["sha256"]
        or any(
            freeze.get(key) != manifest.get(key)
            for key in ("profile_sha256", "request_sha256", "run_limit_usd", "daily_limit_usd")
        )
        or freeze.get("source_revision") in (None, "", "ROOT_MUST_FILL")
        or freeze.get("reviewer") in (None, "", "ROOT_MUST_FILL")
        or manifest.get("scope") != SCOPE
        or manifest.get("prepared_dir") != str(prepared_dir)
        or manifest.get("max_completion_tokens") != MAX_COMPLETION
        or manifest.get("maximum_dispatches") != 1
        or manifest.get("run_limit_usd") != str(MAX_NET_RESERVATION)
    ):
        raise ValueError("Missing or inconsistent root freeze receipt")
    if manifest.get("source_files") != {
        name: file_record(PROJECT_ROOT / name, 2 * 1024 * 1024) for name in CODE_FILES
    }:
        raise ValueError("Probe implementation changed after preparation")
    profile_path = Path(manifest["profile_path"])
    if file_record(profile_path, 256 * 1024)["sha256"] != manifest["profile_sha256"]:
        raise ValueError("Profile changed after the probe freeze")
    source_root = prepared_dir / "source"
    if file_record(source_root / SOURCE_NAME, 64 * 1024) != manifest["source"]:
        raise ValueError("Probe source changed after preparation")
    profile = read_live_profile(profile_path)
    body = _sdk_body(profile, manifest["messages"])
    if low_effort_probe_fingerprint(body) != manifest["request_sha256"]:
        raise ValueError("Probe request/schema changed after preparation")
    if str(_profile_bound(profile, body)) != manifest["reservation_upper_usd"]:
        raise ValueError("Probe billing bound changed")
    # A process-local client counter is insufficient across restarts/concurrency.
    # This claim is never automatically removed, even before/after a local error.
    # Any retry requires a newly reviewed preparation, not reuse of this freeze.
    claim_path = prepared_dir / ".dispatch-claim.json"
    try:
        with claim_path.open("x", encoding="utf-8") as handle:
            claim_path.chmod(0o600)
            json.dump(
                {
                    "scope": SCOPE,
                    "freeze_sha256": expected_freeze_sha256,
                    "request_sha256": manifest["request_sha256"],
                    "profile_sha256": manifest["profile_sha256"],
                    "artifact_dir": str(Path(artifact_dir).resolve()),
                    "state": "claimed_before_admission_not_proof_of_dispatch",
                },
                handle,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
    except FileExistsError:
        raise ValueError("Frozen capability probe was already claimed") from None
    report = {
        "scope": SCOPE,
        "provenance": None,
        "accepted": False,
        "dispatch_claim": str(claim_path),
        "verdict": "not_started",
        "profile_sha256": manifest["profile_sha256"],
        "base_url": profile.base_url,
        "profile_model_compatibility": profile.models["super"].model_dump(exclude={"capabilities"}),
        "freeze_sha256": expected_freeze_sha256,
        "request_sha256": manifest["request_sha256"],
        "server_recognition_verified": False,
        "relative_reasoning_reduction_verified": False,
        "quality_generalization_verified": False,
        "auto_promoted": False,
    }
    artifact_dir = Path(artifact_dir)
    try:
        with acceptance_run(
            case_id=SCOPE,
            artifact_dir=artifact_dir,
            profile_path=profile_path,
            run_limit_usd=manifest["run_limit_usd"],
            daily_limit_usd=manifest["daily_limit_usd"],
            execute=True,
            live_authorized=True,
            project_root=project_root,
            transport=transport,
            env_file=env_file,
            max_http_retries=0,
            low_effort_probe_request_sha256=manifest["request_sha256"],
        ) as session:
            report["provenance"] = session.provenance
            report["ledger_path"] = str(
                Path(session.budget.path).resolve().relative_to(Path(project_root).resolve())
            )
            report["store_path"] = str(
                session.store.path.resolve().relative_to(Path(project_root).resolve())
            )
            if (
                report["ledger_path"] != ".cache/budget.db"
                or report["store_path"] != "runs/acceptance/headroom.db"
            ):
                raise ValueError(
                    "Capability probe must use the original shared ledger and acceptance Store"
                )
            result = session.router.chat(
                "patcher",
                manifest["messages"],
                SourceSpanProposal,
                reasoning=True,
                low_effort=True,
                max_tokens=MAX_COMPLETION,
            )
            usage = result.usage
            if (
                result.finish_reason != "stop"
                or not result.text.strip()
                or result.attempts != 1
                or usage is None
                or type(usage.reasoning_tokens) is not int
                or not 0 < usage.reasoning_tokens <= usage.completion_tokens <= MAX_COMPLETION
                or result.tool_calls
            ):
                raise ValueError("Probe did not produce the required complete structured response")
            # Unlike permissive extraction, demand a whole plain JSON document.
            if json.loads(result.text) != result.parsed:
                raise ValueError("Probe visible content is not one complete plain JSON document")
            candidate_hash = _validate_edit(result.parsed, source_root)
            calls = session.store.llm_calls(session.run_id)
            if len(calls) != 1:
                raise ValueError("Probe did not record exactly one request")
            call = calls[0]
            wire = (call.get("request_evidence") or {}).get("payload")
            if (
                type(wire) is not dict
                or low_effort_probe_fingerprint(wire) != manifest["request_sha256"]
                or wire.get("chat_template_kwargs") != {"enable_thinking": True, "low_effort": True}
                or wire.get("max_completion_tokens") != MAX_COMPLETION
                or call.get("settled") is not True
                or call.get("billing_status") not in {"known", "bounded"}
            ):
                raise ValueError("Probe wire or accounting evidence is incomplete")
            write_json(artifact_dir / "visible-proposal.json", result.parsed)
            report.update(
                accepted=True,
                verdict="request_combination_usable_in_one_sample",
                run_id=session.run_id,
                call_id=call["id"],
                budget_attempt_id=call["budget_attempt_id"],
                response_model=result.response_model,
                finish_reason=result.finish_reason,
                reasoning_tokens=usage.reasoning_tokens,
                completion_tokens=usage.completion_tokens,
                prompt_tokens=usage.prompt_tokens,
                candidate_sha256=candidate_hash,
                billing_status=call["billing_status"],
            )
    except BaseException as error:
        report.update(accepted=False, verdict="failed_or_blocked", error_type=type(error).__name__)
        raise
    finally:
        # Acceptance context owns unknown-charge retention and all halt behavior.
        # Never translate missing cost/usage to zero, release reservations, or clear halts.
        if artifact_dir.is_dir():
            write_json(artifact_dir / "capability-report.json", report)
    return report
