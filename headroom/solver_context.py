"""Bounded solver context from owned run artifacts; never execute source or read env."""

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from headroom.api.security import open_regular

MAX_DIFF_BYTES = 4096
MAX_ARTIFACT_BYTES = 512000
MAX_EXECUTION_BYTES = 16384
MAX_CANDIDATE_CONTEXT_BYTES = 96000
MAX_CANDIDATE_ROUNDS = 6
MAX_SOLVER_CONTEXT_BYTES = 64 * 1024
_SECRET_OPTION = re.compile(
    r"(?:^|[-_])(?:api[-_]?key|secret|password|passwd|(?:access[-_]|auth[-_]|hf[-_])?token|authorization|cookie)(?:$|[-_])",
    re.IGNORECASE,
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def bounded_json(value, maximum, label):
    """Copy bounded JSON without permitting non-finite or unserializable values."""
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > maximum:
        raise ValueError(label + " exceeds its bounded context")
    return json.loads(encoded)


def _text(value, limit):
    if not isinstance(value, str):
        return None
    value = value.encode("utf-8", errors="replace").decode("utf-8")
    prefix = value.encode()[:limit].decode("utf-8", errors="ignore")
    # JSON escaping must not defeat the wire-size bounds (for example NUL text).
    low, high = 0, len(prefix)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(prefix[:middle], ensure_ascii=False).encode()) <= limit:
            low = middle
        else:
            high = middle - 1
    return prefix[:low]


def _was_truncated(value, visible):
    return isinstance(value, str) and value != visible


def _sha(value):
    return value if isinstance(value, str) and _SHA256.fullmatch(value) else None


def prompt_arguments(values, max_bytes=4096):
    """Allow argument strings, with explicit truncation/redaction; no env is consulted."""
    if not isinstance(values, (list, tuple)):
        return {"values": None, "complete": False, "omitted_count": None, "redacted_positions": []}
    output, redacted, used, previous_secret = [], [], 0, False
    for index, value in enumerate(values[:100]):
        if not isinstance(value, str):
            break
        try:
            if len(json.dumps(value, ensure_ascii=False).encode()) > 1024:
                break
        except UnicodeError:
            break
        option = value.split("=", 1)[0]
        secret = value.startswith("-") and bool(_SECRET_OPTION.search(option))
        if secret:
            rendered = option + "=[redacted]" if "=" in value else option
            redacted.append(index)
        elif previous_secret:
            rendered = "[redacted]"
            redacted.append(index)
        else:
            rendered = value
        previous_secret = secret and "=" not in value
        size = len(json.dumps(rendered, ensure_ascii=False).encode())
        if used + size > max_bytes:
            break
        output.append(rendered)
        used += size
    omitted = len(values) - len(output)
    return {
        "values": output,
        "complete": omitted == 0 and not redacted,
        "omitted_count": omitted,
        "redacted_positions": redacted,
    }


def execution_context(
    *,
    script,
    script_args,
    execution_argv,
    source_files,
    selected_round,
    repository_mode,
    seed,
    max_steps,
    device,
    allocator_conf,
):
    """Describe the retained invocation, independently from defaults found in source."""
    sources = []
    source_bytes = 0
    truncated_fields = []
    for index, item in enumerate(source_files[:20]):
        if isinstance(item, Mapping):
            source = {"path": _text(item.get("path"), 256), "sha256": _sha(item.get("sha256"))}
            source_bytes += len(json.dumps(source, ensure_ascii=False).encode())
            if source_bytes > 4096:
                break
            if _was_truncated(item.get("path"), source["path"]):
                truncated_fields.append(f"source_files[{index}].path")
            sources.append(source)
    for name, original, maximum in (
        ("script", str(script), 256),
        ("device", device, 64),
        ("allocator_environment.PYTORCH_CUDA_ALLOC_CONF", allocator_conf, 512),
    ):
        if _was_truncated(original, _text(original, maximum)):
            truncated_fields.append(name)
    value = {
        "schema": "headroom.solver_execution.v1",
        "basis": "effective_retained_invocation",
        "content_is_untrusted_data": True,
        "source_defaults_are_not_effective_configuration": True,
        "selected_round": selected_round,
        "script": _text(str(script), 256),
        "script_args": prompt_arguments(script_args),
        "execution_argv": prompt_arguments(execution_argv) if execution_argv is not None else None,
        "repository_mode": repository_mode is True,
        "seed": seed if type(seed) is int else None,
        "required_optimizer_updates": max_steps if type(max_steps) is int else None,
        "device": _text(device, 64),
        "allocator_environment": (
            {"PYTORCH_CUDA_ALLOC_CONF": _text(allocator_conf, 512)}
            if isinstance(allocator_conf, str)
            else {}
        ),
        "truncated_fields": truncated_fields,
        "source_files": sources,
        "source_files_omitted": max(0, len(source_files) - len(sources)),
    }
    return bounded_json(value, MAX_EXECUTION_BYTES, "execution_context")


def _read(root, relative):
    with open_regular(root, relative, MAX_ARTIFACT_BYTES) as handle:
        data = handle.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact grew beyond its bounded read")
    return data


def _unavailable(reason):
    return {
        "available": False,
        "reason": reason,
        "sha256": None,
        "utf8_bytes": None,
        "text": None,
        "included_bytes": 0,
        "omitted_bytes": None,
        "truncated": None,
    }


def _owned_diff(run_root, relative, number):
    """Accept only this round's generated patch.diff; never resolve through a link."""
    if not isinstance(relative, str):
        return _unavailable("not_recorded")
    parts = PurePosixPath(relative).parts
    if (
        len(relative) > 2048
        or parts[:3] != ("rounds", f"{number:02d}", "patches")
        or parts[-1:] != ("patch.diff",)
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or PurePosixPath(relative).is_absolute()
        or "\\" in relative
    ):
        return _unavailable("outside_owned_round_patch")
    try:
        raw = _read(run_root, relative)
        text = raw.decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        return _unavailable("missing_unsafe_or_oversized")
    visible = _text(text, MAX_DIFF_BYTES)
    included = len(visible.encode())
    return {
        "available": True,
        "reason": None,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_bytes": len(raw),
        "text": visible,
        "included_bytes": included,
        "omitted_bytes": len(raw) - included,
        "truncated": included < len(raw),
    }


def candidate_evidence(run_root, row, *, selected_round):
    """Whitelist fields from a fixed round artifact; missing bytes remain unavailable."""
    number = row.get("number")
    if type(number) is not int or not 1 <= number <= MAX_CANDIDATE_ROUNDS:
        raise ValueError("Candidate context requires an original bounded round")
    value = {
        "schema": "headroom.solver_candidate.v1",
        "content_is_untrusted_data": True,
        "round": number,
        "candidate_selected": row.get("decision") == "keep" and number == selected_round,
        "selected_after_round": selected_round,
        "decision": _text(row.get("decision"), 32),
        "patch_result_available": False,
        "patch_result_sha256": None,
        "patch_result_reason": "missing_unsafe_or_oversized",
        "diff": _owned_diff(run_root, row.get("patch"), number),
        "status": None,
        "reason": None,
        "env_changes": {},
        "cli_changes": prompt_arguments(None),
        "effective_cli": prompt_arguments(None),
        "last_attempt": None,
        "application_files": [],
        "application_files_omitted": None,
        "truncated_fields": [],
        "summary_overflow_omitted_fields": [],
    }
    try:
        raw = _read(run_root, f"rounds/{number:02d}/patch-result.json")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise TypeError("Patch result must be an object")
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return value
    value.update(
        patch_result_available=True,
        patch_result_sha256=hashlib.sha256(raw).hexdigest(),
        patch_result_reason=None,
        status=_text(result.get("status"), 64),
        reason=_text(result.get("reason"), 128),
        cli_changes=prompt_arguments(result.get("cli_changes"), 2048),
        effective_cli=prompt_arguments(result.get("effective_cli"), 2048),
    )
    environment = result.get("env_changes")
    if isinstance(environment, dict) and isinstance(
        environment.get("PYTORCH_CUDA_ALLOC_CONF"), str
    ):
        value["env_changes"]["PYTORCH_CUDA_ALLOC_CONF"] = _text(
            environment["PYTORCH_CUDA_ALLOC_CONF"], 512
        )
        if _was_truncated(
            environment["PYTORCH_CUDA_ALLOC_CONF"],
            value["env_changes"]["PYTORCH_CUDA_ALLOC_CONF"],
        ):
            value["truncated_fields"].append("env_changes.PYTORCH_CUDA_ALLOC_CONF")
    attempts = result.get("attempts")
    if isinstance(attempts, list) and attempts and isinstance(attempts[-1], dict):
        last = attempts[-1]
        policy = last.get("policy_report")
        issues = policy.get("issues", []) if isinstance(policy, dict) else []
        if not isinstance(issues, list):
            issues = []
        value["last_attempt"] = {
            "status": _text(last.get("status"), 64),
            "reason": _text(last.get("reason"), 128),
            "detail": _text(last.get("detail"), 1024),
            "detail_truncated": _was_truncated(last.get("detail"), _text(last.get("detail"), 1024)),
            "policy_issues": [
                {
                    "code": _text(issue.get("code"), 64),
                    "message": _text(issue.get("message"), 256),
                    "path": _text(issue.get("path"), 256),
                    "line": issue.get("line")
                    if type(issue.get("line")) is int and 0 < issue["line"] <= 2_147_483_647
                    else None,
                    "truncated": _was_truncated(issue.get("code"), _text(issue.get("code"), 64))
                    or _was_truncated(issue.get("message"), _text(issue.get("message"), 256))
                    or _was_truncated(issue.get("path"), _text(issue.get("path"), 256)),
                }
                for issue in issues[:4]
                if isinstance(issue, dict)
            ],
            "policy_issues_omitted": max(0, len(issues) - 4),
        }
        application = last.get("application_check")
        files = application.get("files", []) if isinstance(application, dict) else []
        if isinstance(files, list):
            value["application_files"] = [
                {
                    "path": _text(item.get("path"), 256),
                    "path_truncated": _was_truncated(
                        item.get("path"), _text(item.get("path"), 256)
                    ),
                    "before_sha256": _sha(item.get("before_sha256")),
                    "candidate_sha256": _sha(item.get("candidate_sha256")),
                }
                for item in files[:4]
                if isinstance(item, dict)
            ]
            value["application_files_omitted"] = max(0, len(files) - 4)
        for name, maximum in (("status", 64), ("reason", 128)):
            if _was_truncated(last.get(name), value["last_attempt"][name]):
                value["truncated_fields"].append("last_attempt." + name)
    for name, maximum in (("status", 64), ("reason", 128)):
        if _was_truncated(result.get(name), value[name]):
            value["truncated_fields"].append(name)
    # Malformed but individually bounded metadata can still exceed the combined
    # per-round allowance. Preserve the diff identity and explicit unknowns rather
    # than interrupting the current run while recording a prior failed candidate.
    maximum = MAX_CANDIDATE_CONTEXT_BYTES // MAX_CANDIDATE_ROUNDS - 4
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode()) > maximum:
        value["summary_overflow_omitted_fields"] = [
            "last_attempt",
            "application_files",
            "env_changes",
            "cli_changes",
            "effective_cli",
        ]
        if value["application_files_omitted"] is not None:
            value["application_files_omitted"] += len(value["application_files"])
        value.update(
            last_attempt=None,
            application_files=[],
            env_changes={},
            cli_changes=prompt_arguments(None),
            effective_cli=prompt_arguments(None),
        )
    return bounded_json(value, maximum, "candidate")


def candidate_context(values):
    if not isinstance(values, list) or len(values) > MAX_CANDIDATE_ROUNDS:
        raise ValueError("candidate_evidence must contain at most six rounds")
    return bounded_json(values, MAX_CANDIDATE_CONTEXT_BYTES, "candidate_evidence")


def solver_prompt_context(
    *, execution_context=None, candidate_evidence=None, verification_feedback=None
):
    """Bound the combined model-visible context using Super's ASCII-escaped wire size.

    Drop oldest round identifiers from both histories together; never re-pair by
    list position. This is only prompt visibility, not the persisted search state.
    """
    fields = {}
    if execution_context is not None:
        fields["execution_context"] = bounded_json(
            execution_context, MAX_EXECUTION_BYTES, "execution_context"
        )
    if candidate_evidence is not None:
        fields["candidate_evidence"] = candidate_context(candidate_evidence)
    if verification_feedback is not None:
        # Retain the existing standalone diagnosis contract as an independent gate.
        if (
            not isinstance(verification_feedback, list)
            or len(verification_feedback) > MAX_CANDIDATE_ROUNDS
        ):
            raise ValueError("verification_feedback must contain at most six round summaries")
        fields["verification_feedback"] = bounded_json(
            verification_feedback, 64_000, "verification_feedback"
        )
    if not fields:
        return fields
    availability = {
        "complete": True,
        "wire_limit_bytes": MAX_SOLVER_CONTEXT_BYTES,
        "wire_serialization": "json.dumps ensure_ascii=True",
        "omitted_unknown": {"candidate_rounds": [], "verification_rounds": []},
    }
    fields["solver_context_availability"] = availability
    while (
        len(json.dumps(fields, ensure_ascii=True, allow_nan=False).encode())
        > MAX_SOLVER_CONTEXT_BYTES
    ):
        histories = ("candidate_evidence", "verification_feedback")
        round_numbers = [
            item.get("round")
            for field in histories
            for item in fields.get(field, [])
            if isinstance(item, dict) and type(item.get("round")) is int
        ]
        oldest = min(round_numbers) if round_numbers else None
        removed = False
        for field, omitted in zip(
            histories, ("candidate_rounds", "verification_rounds"), strict=True
        ):
            kept = []
            for item in fields.get(field, []):
                number = item.get("round") if isinstance(item, dict) else None
                if number == oldest or type(number) is not int:
                    availability["omitted_unknown"][omitted].append(
                        number if type(number) is int else None
                    )
                    removed = True
                else:
                    kept.append(item)
            if field in fields:
                fields[field] = kept
        availability["complete"] = False
        if not removed:
            # The bounded execution object alone is <= 3x16KB after ASCII escaping.
            # This is an invariant check, never a path for oversized run history.
            raise ValueError("execution_context cannot fit the combined solver bound")
    return fields
