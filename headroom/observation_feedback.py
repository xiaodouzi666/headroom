"""Repeat bounded, source/run-bound facts already supplied to a model; no I/O."""

import json
import re
from collections.abc import Mapping

from headroom.optimizer_observations import _OPTIMIZERS, _typed_group_option

MAX_OBSERVATION_FEEDBACK_BYTES = 2048
_RUN = re.compile(r"[0-9a-f]{32}")
_SHA = re.compile(r"[0-9a-f]{64}")
_SCOPE = "selected_run_cooperative_optimizer_capture_only"
_PREFIX = "execution_context.runtime_optimizer_observations"


def bound_optimizer_observation(context, *, selected_run_id=None, sources=None):
    """Match independent retained identities; this never authenticates a target."""
    if not isinstance(context, Mapping) or context.get("schema") != "headroom.solver_execution.v1":
        return None
    expected = context.get("selected_run_id") if selected_run_id is None else selected_run_id
    if type(expected) is not str or _RUN.fullmatch(expected) is None:
        return None
    context_run = context.get("selected_run_id")
    if context_run is not None and context_run != expected:
        return None
    observed = context.get("runtime_optimizer_observations")
    if not isinstance(observed, Mapping) or (
        observed.get("schema") != "headroom.runtime_optimizer_observations.v1"
        or observed.get("scope") != _SCOPE
        or observed.get("selected_run_id") != expected
        or observed.get("selected_round") != context.get("selected_round")
        or observed.get("source_binding")
        != "capture source digest matches retained entrypoint source"
    ):
        return None
    number = context.get("selected_round")
    if number is not None and (type(number) is not int or not 1 <= number <= 6):
        return None
    sha = observed.get("source_sha256")
    if type(sha) is not str or _SHA.fullmatch(sha) is None:
        return None
    for catalog in (context.get("source_files"), sources):
        if catalog is None and sources is None:
            continue
        if not isinstance(catalog, (list, tuple)) or len(catalog) > 64:
            return None
        if not any(isinstance(item, Mapping) and item.get("sha256") == sha for item in catalog):
            return None
    if not isinstance(context.get("source_files"), (list, tuple)):
        return None
    return observed


def _number(value):
    return type(value) is int and 0 <= value <= 2**63 - 1


def _small_values(mapping, numbers=(), flags=()):
    if not isinstance(mapping, Mapping):
        return {}
    return {
        key: mapping[key]
        for key in (*numbers, *flags)
        if key in mapping
        and (_number(mapping[key]) if key in numbers else type(mapping[key]) is bool)
    }


def supplied_runtime_observation(evidence, evidence_ref):
    """Copy only already-sent optimizer facts next to their scoped question."""
    if (
        not isinstance(evidence, Mapping)
        or type(evidence_ref) is not str
        or evidence_ref
        not in {
            _PREFIX,
            _PREFIX + ".parameters",
            _PREFIX + ".updates",
            _PREFIX + ".optimizer_group_hyperparameters",
        }
    ):
        return None
    if (
        type(evidence.get("run_id")) is not str
        or _RUN.fullmatch(evidence["run_id"]) is None
        or not isinstance(evidence.get("sources"), (list, tuple))
    ):
        return None
    observed = bound_optimizer_observation(
        evidence.get("execution_context"),
        selected_run_id=evidence.get("run_id"),
        sources=evidence.get("sources"),
    )
    if (
        observed is None
        or type(observed.get("status")) is not str
        or observed.get("status") not in {"observed", "partial", "unverified", "unsupported"}
    ):
        return None
    suffix = evidence_ref.removeprefix(_PREFIX).removeprefix(".")
    if suffix and not isinstance(observed.get(suffix), Mapping):
        return None
    result = {
        "schema": "headroom.separate_supplied_runtime_observation.v1",
        "basis": "repeat_of_already_supplied_scoped_observation_only",
        "status": observed["status"],
        "scope": observed["scope"],
        "selected_run_id": observed["selected_run_id"],
        "selected_round": observed.get("selected_round"),
        "source_sha256": observed["source_sha256"],
        "source_binding": observed["source_binding"],
        "native_optimizer_implementation_authenticated": False,
        "numerical_equivalence_proven": False,
        "resolves_prerequisite": False,
    }
    if observed["status"] not in {"observed", "partial"}:
        return result
    result.update(
        _small_values(
            observed,
            numbers=("optimizer_step_calls", "successful_optimizer_step_calls", "logical_updates"),
            flags=(
                "capture_complete",
                "reported_complete",
                "logical_boundary_complete",
                "parameter_update_sets_complete",
                "optimizer_call_counts_consistent",
            ),
        )
    )
    parameters = _small_values(
        observed.get("parameters"),
        numbers=(
            "catalog_entries",
            "catalog_numel",
            "requires_grad_true_entries",
            "requires_grad_true_numel",
            "requires_grad_false_entries",
            "requires_grad_false_numel",
            "registered_parameter_numel",
        ),
        flags=("catalog_numel_matches_registered_count",),
    )
    updates = _small_values(
        observed.get("updates"),
        numbers=(
            "recorded_logical_updates",
            "complete_update_set_records",
            "all_catalog_updated_records",
            "unrecognized_optimizer_class_records",
        ),
        flags=("all_catalog_parameters_updated_each_record",),
    )
    original_updates = observed.get("updates")
    if isinstance(original_updates, Mapping):
        classes = original_updates.get("optimizer_classes")
        if (
            isinstance(classes, list)
            and len(classes) <= 12
            and all(type(value) is str and value in _OPTIMIZERS for value in classes)
        ):
            updates["optimizer_classes"] = list(classes)
        for key in (
            "updated_entries_per_complete_record_range",
            "updated_numel_per_complete_record_range",
        ):
            value = original_updates.get(key)
            if (
                isinstance(value, list)
                and len(value) == 2
                and all(_number(n) for n in value)
                and value[0] <= value[1]
            ):
                updates[key] = list(value)
    if parameters:
        result["parameters"] = parameters
    if updates:
        result["updates"] = updates
    groups = observed.get("optimizer_group_hyperparameters")
    if (
        isinstance(groups, Mapping)
        and type(groups.get("status")) is str
        and groups["status"] in {"observed", "partial"}
    ):
        configurations = groups.get("configurations")
        clean = []
        if isinstance(configurations, list) and len(configurations) <= 8:
            for group in configurations:
                if not isinstance(group, Mapping):
                    break
                present = group.get("present")
                if (
                    not isinstance(present, Mapping)
                    or len(present) > 32
                    or not all(
                        type(key) is str
                        and key
                        in {
                            "lr",
                            "momentum",
                            "weight_decay",
                            "dampening",
                            "nesterov",
                            "betas",
                            "eps",
                            "amsgrad",
                            "maximize",
                            "foreach",
                            "fused",
                            "capturable",
                            "differentiable",
                        }
                        and _typed_group_option(value, sequence=key == "betas")
                        for key, value in present.items()
                    )
                ):
                    break
                clean.append({"present": dict(present)})
            if len(clean) == len(configurations):
                result["optimizer_group_hyperparameters"] = {
                    "status": groups["status"],
                    "configurations": clean,
                }
    # Optional repeated facts must fit their original feedback envelope. If a
    # complete component does not fit, omit it explicitly rather than assert a
    # truncated collection is complete. The original request still contains it.
    result["omitted_components"] = []
    for field in ("optimizer_group_hyperparameters", "parameters", "updates"):
        if (
            len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode())
            <= MAX_OBSERVATION_FEEDBACK_BYTES
        ):
            break
        if field in result:
            del result[field]
            result["omitted_components"].append(field)
    if (
        len(json.dumps(result, ensure_ascii=True, allow_nan=False).encode())
        > MAX_OBSERVATION_FEEDBACK_BYTES
    ):
        return None
    return result
