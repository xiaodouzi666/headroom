"""Bounded solver context from owned run artifacts; never execute source or read env."""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

from headroom.api.security import open_regular
from headroom.operator_capabilities import MAX_CATALOG_BYTES, runtime_operator_catalog
from headroom.retained_state import retained_state_reading_aid
from headroom.verify.candidate_preflight import SCHEMA as PREFLIGHT_SCHEMA
from headroom.verify.candidate_preflight import reference_family_reading_aid

MAX_DIFF_BYTES = 4096
MAX_ARTIFACT_BYTES = 512000
MAX_EXECUTION_BYTES = 16384
MAX_CANDIDATE_CONTEXT_BYTES = 96000
MAX_CANDIDATE_ROUNDS = 6
MAX_SOLVER_CONTEXT_BYTES = 64 * 1024
MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES = 12 * 1024
MAX_EVIDENCE_AVAILABILITY_CONTEXT_BYTES = 8 * 1024
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


def invocation_observation(context, source, index=None):
    """Resolve only literal visible argv tokens, without running/parsing target code.

    Complete argv does not establish the target's effective configuration. Unknown
    fields, truncated tails, and redacted positions cannot disprove a model's claim.
    """
    if source not in ("script_args", "execution_argv") or not isinstance(context, Mapping):
        return "unsupported", None
    arguments = context.get(source)
    if not isinstance(arguments, Mapping):
        return "unsupported", None
    values = arguments.get("values")
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        return "unsupported", None
    redacted = arguments.get("redacted_positions")
    if not isinstance(redacted, list) or any(type(i) is not int for i in redacted):
        return "unverified", None
    complete = (
        arguments.get("complete") is True and arguments.get("omitted_count") == 0 and not redacted
    )
    if index is None:
        return ("available", None) if complete else ("unverified", None)
    if type(index) is not int or index < 0:
        return "unsupported", None
    if index in redacted:
        return "unverified", None
    if index < len(values):
        return "available", values[index]
    return ("absent", None) if complete else ("unverified", None)


def invocation_reading_aid(context):
    """A bounded lexical view; never parse CLI semantics or select duplicate winners."""
    context = context if isinstance(context, Mapping) else {}
    arguments = context.get("script_args")
    arguments = arguments if isinstance(arguments, Mapping) else {}
    visible = prompt_arguments(arguments.get("values"))
    values = visible["values"] or []
    original_redacted = arguments.get("redacted_positions")
    redaction_known = isinstance(original_redacted, list) and all(
        type(index) is int and index >= 0 for index in original_redacted
    )
    redacted = set(visible["redacted_positions"])
    if redaction_known:
        redacted.update(original_redacted)
    original_omitted = arguments.get("omitted_count")
    if type(original_omitted) is not int or not 0 <= original_omitted <= 1000000:
        original_omitted = None
    first_state, first = invocation_observation(context, "execution_argv", 0)
    first_safe = prompt_arguments([first]) if first_state == "available" else None
    first_visible = _text(first, 256) if first_safe is not None and first_safe["complete"] else None
    script = _text(context.get("script"), 256)
    truncated_fields = context.get("truncated_fields", [])
    script_complete = (
        isinstance(context.get("script"), str)
        and script == context["script"]
        and isinstance(truncated_fields, list)
        and "script" not in truncated_fields
    )
    aid = {
        "schema": "headroom.literal_invocation_view.v2",
        "basis": "visible_script_args_tokens_only",
        "target_effective_configuration": "unverified",
        "recorded_script_entrypoint": script if script_complete else None,
        "recorded_script_entrypoint_complete": script_complete,
        "launch_argv_first_token": first_visible,
        "launch_token_complete": first_visible is not None and first_visible == first,
        "launch_scope": "execution_argv[0] is the first launch token: interpreter, launcher or directly executable script; do not assume it equals the recorded script entrypoint",
        "assignments": [],
        "unsupported_tokens": [],
        "unknown_token_indices": [],
        "script_args_complete": (
            arguments.get("complete") is True
            and visible["complete"] is True
            and original_omitted == 0
            and redaction_known
            and not redacted
        ),
        "source_omitted_tokens": original_omitted,
        "bounded_input_omitted_tokens": visible["omitted_count"],
        "view_complete": True,
        "view_omitted_visible_tokens": 0,
        "interpretation": "Only --name=value is split lexically; values stay strings. Repeats retain original indices/order; no precedence, space-option, boolean or target parser semantics inferred.",
    }
    pattern = re.compile(r"^--([A-Za-z_][A-Za-z0-9_.-]*)=([\s\S]*)$")
    for index, token in enumerate(values):
        if not redaction_known or index in redacted or "[redacted]" in token:
            field, item = "unknown_token_indices", index
        else:
            reference = {"source": "script_args", "evidence_ref": f"script_args[{index}]"}
            match = pattern.fullmatch(token)
            if match:
                field, item = (
                    "assignments",
                    {
                        **reference,
                        "index": index,
                        "option": "--" + match[1],
                        "value": match[2],
                        "token": token,
                    },
                )
            else:
                field, item = "unsupported_tokens", {**reference, "index": index, "token": token}
        aid[field].append(item)
        if len(json.dumps(aid, ensure_ascii=True, allow_nan=False).encode()) > 4000:
            aid[field].pop()
            aid["view_complete"] = False
            aid["view_omitted_visible_tokens"] = len(values) - index
            break
    # Reserve above leaves room for bounded omission counts. No raw secret value
    # or redacted token is copied into the reading aid.
    return bounded_json(aid, 4096, "invocation_reading_aid")


def invocation_reference_catalog(context):
    """Resolve only identities actually advertised in the bounded, redacted view.

    Unknown/redacted and view-truncated tokens have no reference. A lexical token
    identity does not establish parser semantics, precedence or a plan's validity.
    """
    view = invocation_reading_aid(context)
    return {
        item["evidence_ref"]: {
            "source": item["source"],
            "index": item["index"],
            "token": item["token"],
        }
        for field in ("assignments", "unsupported_tokens")
        for item in view[field]
    }


def runtime_input_observations(result, source_files, *, selected_round=None, required_steps=20):
    """Expose existing measured input/update facts, bound to the retained source.

    The existing pairing adapter has a narrow reviewed source contract. This
    function never derives dimensions from that contract or from source defaults.
    """
    from headroom.verify.pairing import CONTRACTS, PROTOCOL

    base = {
        "status": "unsupported",
        "scope": "captured_named_tensors_and_optimizer_updates_only",
        "target_effective_configuration": "unverified",
        "selected_round": selected_round,
    }

    def unknown(reason, status="unverified"):
        return {**base, "status": status, "reason": reason}

    if not isinstance(result, Mapping):
        return unknown("retained runtime result unavailable", "unsupported")
    capture = result.get("pairing_capture")
    if not isinstance(capture, Mapping) or capture.get("protocol") != PROTOCOL:
        return unknown("supported runtime input capture unavailable", "unsupported")
    contract = capture.get("source_contract")
    if not isinstance(contract, Mapping):
        return unknown("runtime source contract unavailable", "unsupported")
    profile = contract.get("profile")
    known = CONTRACTS.get(profile) if isinstance(profile, str) else None
    if (
        known is None
        or contract.get("supported") is not True
        or contract.get("contract_sha256") != known["digest"]
        or contract.get("tensor_names") != list(known["inputs"])
    ):
        return unknown("runtime source contract unsupported", "unsupported")
    source_sha = _sha(contract.get("source_sha256"))
    if not isinstance(source_files, (list, tuple)):
        return unknown("retained source catalog unavailable")
    pinned = {_sha(item.get("sha256")) for item in source_files if isinstance(item, Mapping)}
    if source_sha is None or source_sha not in pinned:
        return unknown("runtime input source does not match retained evidence source")
    run_id = result.get("run_id")
    if not isinstance(run_id, str) or not run_id or _text(run_id, 128) != run_id:
        return unknown("retained runtime run identity unavailable")
    base.update(selected_run_id=run_id, source_sha256=source_sha, protocol=PROTOCOL)
    updates = capture.get("updates")
    # Initialization precedes the first forward and survives a genuine OOM.
    # Never infer successful initialization merely from a partial hash dictionary.
    initialization_complete = result.get("capture_complete") is True and (
        capture.get("complete") is True
        or capture.get("reason") == "captured initialized tensors before training loop"
    )
    if not initialization_complete:
        return unknown("runtime initialization capture incomplete")
    tensors = capture.get("tensors")
    if not isinstance(tensors, Mapping):
        return unknown("runtime tensor metadata unavailable")
    observed = {}
    for name in known["inputs"]:
        tensor = tensors.get(name)
        if not isinstance(tensor, Mapping):
            return unknown("runtime tensor metadata incomplete")
        shape, dtype, digest = tensor.get("shape"), tensor.get("dtype"), _sha(tensor.get("sha256"))
        if not (
            isinstance(shape, list)
            and 1 <= len(shape) <= 16
            and all(type(dim) is int and 0 < dim <= 2**63 - 1 for dim in shape)
            and isinstance(dtype, str)
            and dtype
            and _text(dtype, 64) == dtype
            and digest is not None
        ):
            return unknown("runtime tensor metadata invalid")
        observed[name] = {"shape": shape, "dtype": dtype, "sha256": digest}
    base["initial_tensors"] = {
        "status": "observed",
        "basis": "actual named tensor fingerprints before the first training forward",
        "tensors": observed,
        "workload_equivalence_proven": False,
    }
    base["logical_updates"] = {
        "status": "unverified",
        "reason": "complete optimizer update association unavailable",
    }
    if (
        result.get("status") == "oom"
        and type(result.get("steps")) is int
        and result["steps"] == 0
        and updates == []
        and isinstance(result.get("optimizer_update_observation"), Mapping)
        and result["optimizer_update_observation"].get("logical_updates") == 0
        and type(result["optimizer_update_observation"].get("logical_updates")) is int
        and result["optimizer_update_observation"].get("optimizer_step_calls") == 0
        and type(result["optimizer_update_observation"].get("optimizer_step_calls")) is int
    ):
        base["logical_updates"] = {
            "status": "not_reached",
            "observed_optimizer_updates": 0,
            "reason": "OOM occurred before the first observed optimizer update",
        }
    if not (
        capture.get("complete") is True
        and type(required_steps) is int
        and 1 <= required_steps <= 10000
        and type(result.get("steps")) is int
        and result["steps"] == required_steps
        and isinstance(updates, list)
        and len(updates) == required_steps
    ):
        return bounded_json(
            unknown("runtime input/update coverage incomplete"),
            4096,
            "runtime_input_observations",
        )
    optimizer_input = known["inputs"][0]
    expected_batch = observed[optimizer_input]["shape"][0]
    for number, update in enumerate(updates, 1):
        if not isinstance(update, Mapping) or any(
            type(update.get(key)) is not int or update[key] != value
            for key, value in (
                ("step", number),
                ("effective_batch", expected_batch),
                ("training_forwards", 1),
                ("backwards", 1),
            )
        ):
            return unknown("runtime optimizer input association incomplete")
    base["logical_updates"] = {
        "status": "observed",
        "required_optimizer_updates": required_steps,
        "observed_optimizer_updates": len(updates),
        "optimizer_input_name": optimizer_input,
        "effective_batch_per_optimizer_update": expected_batch,
        "training_forwards_per_optimizer_update": 1,
        "backwards_per_optimizer_update": 1,
    }
    return bounded_json(
        {
            **base,
            "status": "observed",
            "required_optimizer_updates": required_steps,
            "observed_optimizer_updates": len(updates),
            "optimizer_input_name": optimizer_input,
            "effective_batch_per_optimizer_update": expected_batch,
            "training_forwards_per_optimizer_update": 1,
            "backwards_per_optimizer_update": 1,
            "tensors": observed,
            "limitations": [
                "Only the retained run and source are represented; this is not a reference/candidate equivalence check.",
                "Other named tensors were captured at initialization; their forward use is not separately counted.",
                "Pinned standalone adapter and cooperative target only; arbitrary runtime configuration remains unverified.",
            ],
        },
        4096,
        "runtime_input_observations",
    )


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
    runtime_result=None,
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
        "configuration_resolution": {
            "status": "unverified",
            "basis": "retained_invocation_not_target_runtime_state",
            "runtime_values_verified": False,
        },
        "selected_round": selected_round,
        "script": _text(str(script), 256),
        "script_args": prompt_arguments(script_args),
        "execution_argv": prompt_arguments(execution_argv) if execution_argv is not None else None,
        "repository_mode": repository_mode is True,
        "runtime_input_observations": runtime_input_observations(
            runtime_result, source_files, selected_round=selected_round, required_steps=max_steps
        ),
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


def candidate_outcome_stage(row, *, patch_status=None, patch_reason=None):
    """Label candidate facts from host-owned patch status/reason and capture only.

    Callers must not substitute model prose, row.reason, or retained state for the
    status/reason read from this round's owned patch-result artifact.
    """
    verification = row.get("verification")
    available = isinstance(verification, Mapping)
    result = {
        "stage": "candidate_verification_unavailable",
        "candidate_runtime_observed": None,
        "candidate_numerical_comparison": "unknown",
    }
    preflight = row.get("candidate_reference_preflight")
    if (
        isinstance(preflight, Mapping)
        and preflight.get("schema") == PREFLIGHT_SCHEMA
        and preflight.get("status") == "rejected"
        and preflight.get("execution_performed_by_preflight") is False
    ):
        result.update(
            stage="inconsistent_preflight_and_verification_evidence"
            if available
            else "reference_contract_rejected_before_execution",
            candidate_runtime_observed=None if available else False,
        )
        return result
    # This exact host F821 rejection returns before services.verify. Other
    # failed reasons do not establish whether candidate execution was attempted.
    failed_name_check = patch_status == "failed" and patch_reason == "NEW_UNDEFINED_NAME"
    if patch_status == "rejected" or failed_name_check:
        if available or (failed_name_check and verification is not None):
            result["stage"] = "inconsistent_patch_and_verification_evidence"
        else:
            result.update(stage="rejected_before_execution", candidate_runtime_observed=False)
        return result
    if not available:
        if patch_status == "applied":
            result["stage"] = "patch_applied_verification_unavailable"
        return result

    after = verification.get("after")
    after = after if isinstance(after, Mapping) else {}
    status = after.get("status")
    status = status if isinstance(status, str) else None
    # A runner allocates run_id before preparation; status/exception and even
    # a Docker execution dictionary do not establish that target capture ran.
    reason = after.get("reason")
    execution = after.get("execution")
    execution = execution if isinstance(execution, Mapping) else {}
    preparation_reasons = {
        "GPU_BUSY",
        "GPU_UNAVAILABLE",
        "PREPARATION_FAILED",
        "CONTAINER_CREATE_FAILED",
    }
    preparation_failure = any(
        isinstance(item, str) and item in preparation_reasons
        for item in (reason, execution.get("error"))
    )
    pid = after.get("pid")
    execution_status = after.get("execution_status")
    observed = (
        after.get("protocol") == "headroom.lab.v1"
        and type(pid) is int
        and 0 < pid <= 2_147_483_647
        and type(after.get("capture_complete")) is bool
        and isinstance(execution_status, str)
        and execution_status in {"completed", "oom", "error", "timeout"}
    )
    if preparation_failure:
        # PREPARATION_FAILED can also be a host failure while reading artifacts
        # after Docker returned. Absence of target evidence is not proof that
        # execution never started; contradictory fields are unknown as well.
        result["stage"] = (
            "inconsistent_preparation_and_capture_evidence"
            if observed
            else "runner_failure_without_target_capture"
        )
        return result
    if observed:
        result["candidate_runtime_observed"] = True
        if status in {"oom", "error", "failed", "timeout", "cancelled"}:
            result["stage"] = "candidate_execution_failed"
        elif verification.get("completed") is False:
            result["stage"] = "candidate_execution_incomplete"
        elif verification.get("completed") is True:
            result["stage"] = "candidate_execution_completed"
        else:
            result["stage"] = "candidate_execution_completion_unknown"
    else:
        result["stage"] = "verification_without_candidate_execution_evidence"
    checks = verification.get("checks")
    checks = checks if isinstance(checks, Mapping) else {}
    comparable = checks.get("loss_series_comparison_available")
    if comparable is True:
        result["candidate_numerical_comparison"] = "available"
    elif comparable is False:
        result["candidate_numerical_comparison"] = "unavailable"
    return result


def candidate_capture_counts(row, *, patch_status=None, patch_reason=None):
    """Summarize recorded candidate quantities, without changing numerical gates.

    A recorded scalar is an argument seen at Tensor.backward entry, including
    nonfinite entries represented as None. It is not a successful backward or
    optimizer-update count. Prefix evidence does not establish training completion.
    """
    result = {
        "schema": "headroom.candidate_capture_counts.v1",
        "basis": "recorded_candidate_capture_only",
        "capture_complete": None,
        "backward_scalar_count": None,
        "backward_scalar_scope": "unavailable",
        "logical_update_count": None,
        "logical_update_scope": "unavailable",
    }
    stage = candidate_outcome_stage(row, patch_status=patch_status, patch_reason=patch_reason)
    if stage["candidate_runtime_observed"] is not True:
        return result
    after = row["verification"]["after"]
    complete = after["capture_complete"]
    result["capture_complete"] = complete
    scope = "finalized_capture" if complete else "captured_prefix"
    scalars = after.get("loss_series")

    def recorded_scalar(value):
        if value is None:
            return True
        if type(value) not in (int, float):
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False

    if (
        isinstance(scalars, list)
        and len(scalars) <= 1_000_000
        and all(recorded_scalar(value) for value in scalars)
    ):
        result.update(backward_scalar_count=len(scalars), backward_scalar_scope=scope)

    observation = after.get("optimizer_update_observation")
    observation = observation if isinstance(observation, Mapping) else {}
    steps, records = after.get("steps"), after.get("step_records")
    if (
        observation.get("protocol") == "headroom.optimizer_updates.v1"
        and observation.get("logical_boundary_complete") is True
        and type(steps) is int
        and 0 <= steps <= 10000
        and type(observation.get("logical_updates")) is int
        and observation["logical_updates"] == steps
        and isinstance(records, list)
        and len(records) == steps
        and all(
            isinstance(record, Mapping)
            and type(record.get("step")) is int
            and record["step"] == number
            for number, record in enumerate(records, 1)
        )
    ):
        result.update(logical_update_count=steps, logical_update_scope=scope)
    return result


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
        "outcome_stage": candidate_outcome_stage(row),
        "capture_counts": candidate_capture_counts(row),
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
        outcome_stage=candidate_outcome_stage(
            row, patch_status=result.get("status"), patch_reason=result.get("reason")
        ),
        capture_counts=candidate_capture_counts(
            row, patch_status=result.get("status"), patch_reason=result.get("reason")
        ),
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
    *,
    execution_context=None,
    candidate_evidence=None,
    verification_feedback=None,
    numerical_reference_context=None,
    evidence_availability_catalog=None,
):
    """Bound the combined model-visible context using Super's ASCII-escaped wire size.

    Drop oldest round identifiers from both histories together; never re-pair by
    list position. This is only prompt visibility, not the persisted search state.
    """
    fields = {
        "runtime_operator_catalog": bounded_json(
            runtime_operator_catalog(), MAX_CATALOG_BYTES, "runtime_operator_catalog"
        )
    }
    if evidence_availability_catalog is not None:
        fields["evidence_availability_catalog"] = bounded_json(
            evidence_availability_catalog,
            MAX_EVIDENCE_AVAILABILITY_CONTEXT_BYTES,
            "evidence_availability_catalog",
        )
    if numerical_reference_context is not None:
        fields["numerical_reference_context"] = bounded_json(
            numerical_reference_context,
            MAX_NUMERICAL_REFERENCE_CONTEXT_BYTES,
            "numerical_reference_context",
        )
    family_aid = reference_family_reading_aid(numerical_reference_context)
    if family_aid is not None:
        fields["reference_family_reading_aid"] = family_aid
    if execution_context is not None:
        fields["invocation_reading_aid"] = invocation_reading_aid(execution_context)
        fields["execution_context"] = bounded_json(
            execution_context, MAX_EXECUTION_BYTES, "execution_context"
        )
    if execution_context is not None or candidate_evidence is not None:
        fields["retained_state_reading_aid"] = retained_state_reading_aid(
            execution_context, candidate_evidence
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
            # Fixed capability metadata, bounded execution and lexical aid must fit together.
            # This is an invariant check, never a path for oversized run history.
            raise ValueError("execution_context cannot fit the combined solver bound")
    return fields
