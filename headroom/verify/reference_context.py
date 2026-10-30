"""Read-only descriptions of the configured verifier; never repair instructions."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path, PurePosixPath

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


def _completed_baseline_observation(
    baseline, original, original_args, required_steps, command_mode
):
    """Describe a preserved completed run; this does not certify a candidate."""
    from headroom.lab.runner import read_artifact_json, selected_capture_directory

    result = {
        "status": "unknown",
        "reason": "completed original-baseline execution has not been bound",
        "run_id": None,
        "source_and_argv_bound": False,
        "required_logical_updates": required_steps,
        "observed_logical_updates": None,
        "capture_complete": None,
        "cleanup_verified": None,
        "precision": "unknown",
        "loss_scalar_count": None,
        "loss_scalar_count_matches_logical_updates": None,
        "observed_updated_parameter_tensors_per_step": None,
        "candidate_input_pairing_verified": None,
        "scope": "Preserved original execution and scalar-series availability only; not candidate equivalence or model semantics.",
    }
    if baseline.get("status") != "completed":
        result["reason"] = "original baseline is not completed"
        return result
    try:
        if command_mode or type(required_steps) is not int or required_steps < 1:
            raise ValueError("Unsupported execution or step contract")
        if type(original_args) not in (list, tuple) or not all(
            type(arg) is str for arg in original_args
        ):
            raise ValueError("Original argv unavailable")
        run_id = baseline.get("run_id")
        if (
            type(run_id) is not str
            or len(run_id) != 32
            or any(char not in "0123456789abcdef" for char in run_id)
        ):
            raise ValueError("Original run identity unavailable")
        directory = Path(baseline["run_dir"])
        if directory.name != run_id:
            raise ValueError("Original run identity differs")
        manifest = read_artifact_json(directory / "manifest.json")
        host = read_artifact_json(directory / "result.json")
        capture_directory = selected_capture_directory(directory, baseline, manifest)
        capture = read_artifact_json(capture_directory / "result.json")
        fields = (
            "protocol",
            "capture_complete",
            "finalization_incomplete",
            "steps",
            "loss_series",
            "step_records",
            "optimizer_update_observation",
            "precision_observation",
            "env",
        )
        if any(
            baseline.get(field) != host.get(field) or baseline.get(field) != capture.get(field)
            for field in fields
        ):
            raise ValueError("Host and selected capture differ")
        if (
            host.get("run_id") != run_id
            or Path(host.get("run_dir", "")) != directory
            or host.get("status") != "completed"
            or capture.get("status") != "completed"
            or host.get("cleanup_verified") is not True
            or baseline.get("cleanup_verified") is not True
            or baseline.get("protocol") != "headroom.lab.v1"
            or baseline.get("capture_complete") is not True
            or baseline.get("finalization_incomplete") is not False
        ):
            raise ValueError("Incomplete original execution")
        command = manifest.get("command")
        if type(command) is not list or not all(type(arg) is str for arg in command):
            raise ValueError("Missing preserved wrapper command")
        split = command.index("--") if "--" in command else len(command)
        wrapper = command[:split]
        recorded_args = command[split + 1 :] if split < len(command) else []
        if (
            wrapper[1:3] != ["-m", "headroom.lab.run_target"]
            or wrapper.count("--script") != 1
            or recorded_args != list(original_args)
        ):
            raise ValueError("Preserved standalone command/argv differs")
        relative = PurePosixPath(wrapper[wrapper.index("--script") + 1]).relative_to("/source")
        if not relative.parts or ".." in relative.parts:
            raise ValueError("Unsafe preserved source path")
        entry = manifest["source"]["files"][str(relative)]
        preserved = _contract(directory / "source" / str(relative))
        source_hash = original.get("source_sha256")
        if (
            type(source_hash) is not str
            or len(source_hash) != 64
            or entry.get("sha256") != source_hash
            or preserved.get("source_sha256") != source_hash
        ):
            raise ValueError("Original executed source differs")
        updates = baseline.get("optimizer_update_observation") or {}
        steps, records = baseline.get("steps"), baseline.get("step_records")
        losses = baseline.get("loss_series")
        if (
            type(steps) is not int
            or steps < required_steps
            or updates.get("protocol") != "headroom.optimizer_updates.v1"
            or updates.get("complete") is not True
            or updates.get("logical_boundary_complete") is not True
            or type(updates.get("logical_updates")) is not int
            or updates["logical_updates"] != steps
            or type(records) is not list
            or len(records) != steps
            or any(
                type(record) is not dict
                or type(record.get("step")) is not int
                or record["step"] != index
                for index, record in enumerate(records, 1)
            )
            or type(losses) is not list
            or len(losses) != steps
            or not all(type(value) in (int, float) and math.isfinite(value) for value in losses)
        ):
            raise ValueError("Logical-update or scalar-series evidence incomplete")
        precision = observed_precision(baseline)
        if precision not in {"fp32", "bf16"}:
            raise ValueError("Original precision unknown")
        counts = []
        if updates.get("parameter_update_sets_complete") is True:
            for record in records:
                identities = record.get("updated_parameter_ids")
                if (
                    record.get("parameter_update_coverage_complete") is not True
                    or type(identities) is not list
                    or not identities
                    or any(type(identity) is not str for identity in identities)
                    or len(set(identities)) != len(identities)
                ):
                    counts = []
                    break
                counts.append(len(identities))
        result.update(
            status="observed",
            reason="Preserved completed original source/argv, logical updates and scalar losses are available",
            run_id=run_id,
            source_sha256=source_hash,
            source_and_argv_bound=True,
            observed_logical_updates=steps,
            capture_complete=True,
            cleanup_verified=True,
            precision=precision,
            loss_scalar_count=len(losses),
            loss_scalar_count_matches_logical_updates=True,
            observed_updated_parameter_tensors_per_step=(
                {"minimum": min(counts), "maximum": max(counts)} if counts else None
            ),
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
        result["reason"] = (
            "Preserved completed original-baseline evidence is incomplete or inconsistent"
        )
    return result


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
    completed_baseline = _completed_baseline_observation(
        baseline, original, original_args, required_steps, command_mode
    )
    completed_observed = completed_baseline["status"] == "observed"
    status = (
        "not_needed_completed_baseline"
        if completed_observed
        else "completed_baseline_evidence_unverified"
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
        "configured_strategy_application": "Only used to construct a separate reference when the original baseline OOMs",
        "comparison_reference": {
            "kind": "completed_original_baseline"
            if completed_observed
            else "oom_reference_required"
            if is_oom
            else "unverified",
            "separate_reference_required": False
            if completed_observed
            else True
            if is_oom
            else None,
            "original_baseline": completed_baseline,
            "original_baseline_availability_scope": (
                "The nested original_baseline status and null/false fields describe only "
                "availability of a complete original numerical-comparison series here, "
                "not existence or status of the captured original execution. They do not "
                "negate separately supplied observed OOM/partial execution or source-binding "
                "facts. This clarification creates no usable reference, compatible capability "
                "or candidate-equivalence proof; unsupported requirements remain unresolved."
            ),
            "candidate_equivalence_verified": None,
        },
        "acceptance_scope": scope,
        "capability_status": status,
        "reference_execution_verified": None,
        "reference_execution_verified_scope": "A separate discovered/transformed reference only; null does not negate an observed completed original baseline above",
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
            "No separate reference is run by this context. An observed completed original baseline above is distinct from unverified candidate pairing and equivalence.",
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
        if (
            retained.get("supported") is True
            and original.get("supported") is True
            and retained.get("contract_sha256") == original.get("contract_sha256")
            and original.get("profile") == "s1"
        ):
            result["source_contract_boundary"]["reviewed_edit_families"] = [
                {
                    "kind": "non_reentrant_activation_checkpoint",
                    "scope": "existing unchanged per-block module call only",
                    "api": "torch.utils.checkpoint.checkpoint",
                    "requirements": [
                        "use_reentrant=False",
                        "default RNG preservation or preserve_rng_state=True",
                        "top-level single-name direct checkpoint import or fully qualified module import without aliases",
                        "no custom context_fn, changed arguments, wrappers, or other keyword options",
                        "entire remaining normalized program must match the reviewed original contract",
                    ],
                }
            ]
            result["source_contract_boundary"]["preserve"] = [
                "original input tensors and initialization",
                "batch, full training loop, objective and optimizer",
                "one training root forward and one backward per logical update",
                "precision and all other program semantics",
            ]
            result["source_contract_boundary"]["candidate_support"] = (
                "Describes a verifier capability, not a proposed repair or success guarantee. "
                "Every actual candidate is independently checked; public checkpoint variants "
                "outside these exact constraints remain unsupported."
            )
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
    # Optional source-coordinate projection; no new supported edit family.
    # The enclosing verifier context keeps its original 12 KiB ceiling.
    try:
        from headroom.patch_spans import source_span_document
        from headroom.verify.reference_callsites import checkpoint_callsite_reading_aid

        if (
            strategy == CHECKPOINT_STRATEGY
            and is_oom
            and original.get("supported") is True
            and retained.get("supported") is True
            and original.get("source_sha256") == retained.get("source_sha256")
        ):
            script = Path(retained_script)
            document = source_span_document(script.parent, script.name)
            aid = checkpoint_callsite_reading_aid(document, result)
            if aid is not None:
                enriched = dict(result, reviewed_checkpoint_callsites=aid)
                if (
                    len(json.dumps(enriched, ensure_ascii=True, allow_nan=False).encode())
                    <= 12 * 1024
                ):
                    result = enriched
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        pass
    return result
