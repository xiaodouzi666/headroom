"""Read-only descriptions of the configured verifier; never repair instructions."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from headroom.verify.checkpoint import STRATEGY as CHECKPOINT_STRATEGY
from headroom.verify.offload import LEGACY_STRATEGY, STRATEGY, bind_original_baseline
from headroom.verify.pairing import source_contract
from headroom.verify.precision import observed_precision
from headroom.verify.reference_config import NumericalReference


def _contract(path):
    """Read only a bounded regular source; disclose hashes, never source text."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 131072:
                raise ValueError("Unbounded or non-regular source")
            data = handle.read(131073)
        if len(data) > 131072:
            raise ValueError("Source grew beyond its bound")
        result = source_contract(Path(path))
        digest = hashlib.sha256(data).hexdigest()
        if result.get("source_sha256") != digest:
            raise ValueError("Source changed during static inspection")
        return result
    except (OSError, ValueError, TypeError):
        return {"supported": None}


def _source_observation(contract):
    supported = contract.get("supported")
    return {
        "status": "supported"
        if supported is True
        else "unsupported"
        if supported is False
        else "unknown",
        "source_sha256": contract.get("source_sha256"),
        "normalized_contract_sha256": contract.get("contract_sha256"),
        "basis": "bounded static source inspection; no execution or equivalence proof",
    }


def numerical_reference_context(
    options,
    *,
    baseline,
    original_script,
    original_args,
    retained_script,
    required_steps=20,
    max_seconds=120,
    repository_mode=False,
    command_mode=False,
):
    """Report the selected protocol and existing preconditions, without running it.

    A supported retained source says nothing about a future patch. No manual
    candidate, scenario name, transform body, or successful reference is exposed.
    """
    options = (
        options
        if isinstance(options, NumericalReference)
        else NumericalReference.model_validate(options)
    )
    original = _contract(original_script)
    retained = _contract(retained_script)
    strategy = options.strategy
    explicit = strategy != LEGACY_STRATEGY
    is_oom = baseline.get("status") == "oom"
    capture = baseline.get("pairing_capture") or {}
    standalone = not command_mode
    original_supported = original.get("supported") is True
    protocol_source_supported = original_supported
    if strategy == CHECKPOINT_STRATEGY:
        protocol_source_supported = (
            original_supported
            and original.get("profile") == "s1"
            and original.get("checkpointed") is False
        )
    binding = (
        bind_original_baseline(baseline, original_script, original_args)
        if explicit and is_oom and standalone and original_supported and original_args is not None
        else {}
    )
    precision = observed_precision(baseline)
    observed_initialization = bool(capture.get("tensors")) and bool(
        capture.get("initial_parameters")
    )
    checks = {
        "original_oom_observed": is_oom,
        "standalone_script_execution": standalone,
        "original_source_supported_by_selected_protocol": protocol_source_supported,
        "original_source_and_argv_bound_to_capture": binding.get("valid") is True,
        "original_inputs_and_initial_parameters_captured": observed_initialization,
        "original_precision_known": precision in {"fp32", "bf16"},
        "reviewed_torch_runtime": str(baseline.get("env", {}).get("torch", "")).split("+")[0]
        == "2.5.1",
        "retained_source_has_reviewed_pairing_contract": retained.get("supported") is True,
        "retained_contract_matches_original": (
            original_supported
            and retained.get("supported") is True
            and retained.get("contract_sha256") == original.get("contract_sha256")
        ),
        "required_update_count_supported": strategy != CHECKPOINT_STRATEGY or required_steps == 20,
    }
    scope = "repository" if repository_mode else "standard"
    status = (
        "not_needed_completed_baseline"
        if baseline.get("status") == "completed"
        else "preconditions_observed_execution_unverified"
        if explicit and all(checks.values())
        else "unavailable_under_current_preconditions"
        if explicit
        else "legacy_discovery_not_run_by_context"
    )
    result = {
        "protocol": "headroom.numerical_reference_context.v1",
        "authority": "host_selected_verification_protocol_and_read_only_observations",
        "selected_strategy": strategy,
        "acceptance_scope": scope,
        "capability_status": status,
        "reference_execution_verified": None,
        "candidate_equivalence_verified": None,
        "required_logical_updates": required_steps,
        "reference_limits": {
            "max_seconds": options.max_seconds if options.max_seconds is not None else max_seconds,
            "subject_to_outer_job_deadline": True,
            "cpu_saved_tensor_limit_bytes": options.cpu_saved_tensor_limit_bytes
            if strategy == STRATEGY
            else None,
            "disk_saved_tensor_limit_bytes": options.disk_saved_tensor_limit_bytes
            if strategy == STRATEGY
            else None,
        },
        "original_source": _source_observation(original),
        "retained_source": _source_observation(retained),
        "original_precision": precision,
        "explicit_reference_preconditions": checks if explicit else None,
        "fallback_to_legacy": False if explicit else None,
        "repository_no_reference_exception_enabled": strategy == LEGACY_STRATEGY
        and repository_mode,
        "reference_scores_candidate_performance": False,
        "scalar_comparison": {
            "basis": "first_five_backward_scalars" if is_oom else "full_backward_scalar_series",
            "automatic_microbatch_aggregation": False,
            "automatic_loss_rescaling": False,
            "multiple_backwards_are_not_multiple_optimizer_updates": True,
            "bounds": "Existing observed-precision tolerance and policy remain authoritative; this context cannot override them.",
        },
        "limitations": [
            "This capability context does not run or certify a reference/candidate; null verification fields mean unknown here, not a failed or successful run.",
            "Static source support is not runtime input, initialization, precision, or numerical equivalence proof.",
            "Retained-source support does not establish support for a future candidate; each proposed edit is checked independently.",
            "Policy permission for batch/accumulation changes does not establish mathematical equivalence or verifier support.",
            "Same seed and equal parameter count alone do not prove identical workload or updated parameters.",
            "Reference existence, memory fit, cleanup, timing and numerical outcomes remain unverified until actual execution.",
        ],
    }
    if explicit:
        result["source_contract_boundary"] = {
            "kind": "reviewed_complete_normalized_program_ast",
            "active_for_this_oom_baseline": is_oom,
            "candidate_source_must_remain_within_reviewed_contract": True,
            "arbitrary_training_loop_or_objective_rewrites_supported": False,
            "microbatch_or_gradient_accumulation_rewrites_supported": False,
            "changed_batch_is_not_automatically_equivalent": True,
            "runtime_proof_required": [
                "same actual inputs",
                "same initial parameters",
                "same effective batch and objective",
                "complete logical updates",
                "known original/reference precision",
                "source/argv execution binding",
                "verified cleanup",
            ],
        }
        result["failure_behavior"] = (
            "Unavailable, unsupported, failed or incomplete explicit references cannot pass numerical acceptance or borrow the legacy repository exception."
        )
        result["reference_construction"] = (
            "A fixed reviewed non-reentrant transformation is derived from the original baseline source and argv, never from candidate source; this is transformed reference execution, not byte-for-byte original execution."
            if strategy == CHECKPOINT_STRATEGY
            else "Original baseline source and argv execute with lossless saved-tensor CPU or explicitly configured disk storage; the candidate is independently measured."
        )
    else:
        result["failure_behavior"] = (
            "A missing reference stays unavailable. Only the existing repository OOM/no-reference exception may apply; a provided failed reference or numerical change cannot use it."
        )
        result["reference_construction"] = (
            "A completed baseline is compared directly. An OOM baseline uses bounded discovery of an original-source smaller-batch reference; a smaller batch is not proof of the same workload."
        )
    return result
