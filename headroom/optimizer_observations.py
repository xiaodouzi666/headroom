"""Bounded optimizer observations from a selected cooperative Lab capture.

Independent of the named-input adapter. No code, environment, weights or arbitrary
capture prose is read; these facts do not establish numerical equivalence.
"""

import json
import math
import re
from collections.abc import Mapping

MAX_OPTIMIZER_OBSERVATION_BYTES = 3072
_MAX_PARAMETERS = 65536
_MAX_UPDATES = 10000
_SHA = re.compile(r"[0-9a-f]{64}")
_RUN = re.compile(r"[0-9a-f]{32}")
_PARAMETER = re.compile(r"p[0-9]{5,6}")
_OPTIMIZERS = frozenset(
    {
        "torch.optim.adamw.AdamW",
        "torch.optim.adam.Adam",
        "torch.optim.sgd.SGD",
        "torch.optim.adagrad.Adagrad",
        "torch.optim.rmsprop.RMSprop",
        "torch.optim.adadelta.Adadelta",
        "torch.optim.adamax.Adamax",
        "torch.optim.asgd.ASGD",
        "torch.optim.radam.RAdam",
        "torch.optim.rprop.Rprop",
        "torch.optim.nadam.NAdam",
        "torch.optim.sparse_adam.SparseAdam",
    }
)


def _count(value, maximum=2**63 - 1):
    return value if type(value) is int and 0 <= value <= maximum else None


def _flag(value):
    return value if type(value) is bool else None


_GROUP_OPTION_NAMES = frozenset(
    {
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
        "initial_lr",
        "alpha",
        "rho",
        "lr_decay",
        "initial_accumulator_value",
        "lambd",
        "t0",
        "etas",
        "step_sizes",
        "momentum_decay",
        "decoupled_weight_decay",
    }
)


def _typed_group_option(value, *, sequence=False):
    if type(value) is not list or len(value) != 2:
        return False
    tag, item = value
    if type(tag) is not str:
        return False
    if tag in {"none", "unsupported"}:
        return item is None
    if tag == "bool":
        return type(item) is bool
    if tag == "int":
        return type(item) is int and -(2**63) <= item < 2**63
    if tag == "float":
        return type(item) is float and math.isfinite(item)
    return (
        sequence
        and tag in {"tuple", "list"}
        and type(item) is list
        and len(item) == 2
        and all(_typed_group_option(child) and child[0] in {"int", "float"} for child in item)
    )


def _optimizer_group_options(raw, parameters, calls, constructor_returns):
    """Accept only bounded, typed metadata from the already source-bound run."""
    invalid = {"status": "unverified", "reason": "group metadata invalid or incomplete"}
    if raw is not None:
        try:
            if (
                len(
                    json.dumps(
                        raw,
                        ensure_ascii=True,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                > 65536
            ):
                return invalid
        except (TypeError, ValueError, OverflowError, RecursionError):
            return invalid
    if not isinstance(raw, Mapping) or raw.get("protocol") != "headroom.optimizer_group_options.v1":
        return "not_captured" if raw is None else invalid
    if (
        type(raw.get("complete")) is not bool
        or type(raw.get("stopped_at_limit_or_error")) is not bool
    ):
        return invalid
    events = raw.get("events")
    if (
        type(events) is not dict
        or set(events) != {"base_constructor_return", "step_pre"}
        or any(_count(value, 65536) is None for value in events.values())
        or events["step_pre"] != calls
        or events["base_constructor_return"] != constructor_returns
    ):
        return invalid
    configs, groups = raw.get("configurations"), raw.get("groups")
    if (
        type(configs) is not list
        or len(configs) > 64
        or type(groups) is not list
        or len(groups) > 256
    ):
        return invalid
    known = {}
    for item in configs:
        if type(item) is not dict:
            return invalid
        identity, present, extra = (
            item.get("id"),
            item.get("present"),
            item.get("unrecognized_option_keys"),
        )
        if (
            type(identity) is not str
            or re.fullmatch(r"c[0-9]{3}", identity) is None
            or identity in known
            or type(present) is not dict
            or set(present) - _GROUP_OPTION_NAMES
            or _count(extra, 64) is None
            or any(
                not _typed_group_option(value, sequence=name in {"betas", "etas", "step_sizes"})
                for name, value in present.items()
            )
        ):
            return invalid
        known[identity] = {
            "id": identity,
            "present": present,
            "unrecognized_option_keys": extra,
            "group_records": {"base_constructor_return": 0, "step_pre": 0},
        }
    members = 0
    seen = set()
    group_observations = {stage: 0 for stage in events}
    for record in groups:
        if type(record) is not dict:
            return invalid
        config, stage, pids = (
            record.get("config_id"),
            record.get("stage"),
            record.get("parameter_ids"),
        )
        first, last, count = (
            record.get("first_call"),
            record.get("last_call"),
            record.get("observations"),
        )
        if (
            type(config) is not str
            or config not in known
            or type(stage) is not str
            or stage not in events
            or type(record.get("optimizer_id")) is not str
            or re.fullmatch(r"o[0-9]{4}", record["optimizer_id"]) is None
            or _count(record.get("group_index"), 63) is None
            or type(pids) is not list
            or len(pids) > 8192
            or any(type(token) is not str or token not in parameters for token in pids)
            or len(set(pids)) != len(pids)
            or _count(first, 65536) is None
            or _count(last, 65536) is None
            or first > last
            or _count(count, 65536) is None
            or count < 1
            or count > events[stage]
            or (stage == "base_constructor_return" and (first != 0 or last != 0))
            or (stage == "step_pre" and (first < 1 or last > calls))
        ):
            return invalid
        key = (record["optimizer_id"], record["group_index"], stage, config, tuple(pids))
        if key in seen:
            return invalid
        seen.add(key)
        group_observations[stage] += count
        members += len(pids)
        if members > 16384:
            return invalid
        known[config]["group_records"][stage] += 1
    if raw["complete"] and any(
        not events[stage] <= group_observations[stage] <= events[stage] * 64 for stage in events
    ):
        return invalid
    used = [item for item in known.values() if sum(item["group_records"].values())]
    options_supported = all(
        item["unrecognized_option_keys"] == 0
        and all(value[0] != "unsupported" for value in item["present"].values())
        for item in used
    )
    summary = {
        "status": "observed"
        if used and raw["complete"] and not raw["stopped_at_limit_or_error"] and options_supported
        else "partial",
        "events": events,
        "configurations": used,
        "scope": "Actual present group values at base-constructor return or step-pre only; absent keys are not defaults. No completed-update or custom-step/closure-use proof.",
    }
    if len(json.dumps(summary, ensure_ascii=True, allow_nan=False).encode()) > 1024:
        return {
            "status": "unverified",
            "reason": "group metadata omitted at bounded context",
            "events": events,
        }
    return summary


def runtime_optimizer_observations(result, source_files, *, script, selected_round=None):
    """Summarize only the selected run and exact retained entrypoint source digest.

    The source digest is captured even when its named-input AST contract is
    unsupported. It is not an input/target pairing or authentication guarantee.
    """
    summary = {
        "schema": "headroom.runtime_optimizer_observations.v1",
        "status": "unsupported",
        "scope": "selected_run_cooperative_optimizer_capture_only",
        "selected_round": selected_round
        if type(selected_round) is int and 1 <= selected_round <= 6
        else None,
        "numerical_equivalence_proven": False,
        "input_coverage_proven": False,
        "optimizer_group_hyperparameters": "not_captured",
        "optimizer_classes_basis": "reported class tags, not authenticated optimizer implementations",
        "limitations": (
            "Observed Parameter identities/version changes and requires_grad flags, not "
            "objective equivalence, full workload coverage or target authentication. "
            "Filename/comments/intended labels do not override executed updates."
        ),
    }

    def unknown(reason, status="unverified"):
        summary.update(status=status, reason=reason)
        return summary

    if not isinstance(result, Mapping) or result.get("protocol") != "headroom.lab.v1":
        return unknown("selected Lab capture unavailable", "unsupported")
    observation = result.get("optimizer_update_observation")
    if (
        not isinstance(observation, Mapping)
        or observation.get("protocol") != "headroom.optimizer_updates.v1"
    ):
        return unknown("optimizer capture unavailable", "unsupported")
    pairing = result.get("pairing_capture")
    contract = pairing.get("source_contract") if isinstance(pairing, Mapping) else None
    digest = contract.get("source_sha256") if isinstance(contract, Mapping) else None
    run_id = result.get("run_id")
    matching_sources = (
        [item for item in source_files if isinstance(item, Mapping) and item.get("path") == script]
        if isinstance(source_files, (list, tuple)) and len(source_files) <= 64
        else []
    )
    if not (
        isinstance(digest, str)
        and _SHA.fullmatch(digest)
        and len(matching_sources) == 1
        and matching_sources[0].get("sha256") == digest
        and isinstance(run_id, str)
        and _RUN.fullmatch(run_id)
    ):
        return unknown("selected run or retained entrypoint source binding unavailable")
    summary.update(
        selected_run_id=run_id,
        source_sha256=digest,
        source_binding="capture source digest matches retained entrypoint source",
        capture_complete=_flag(result.get("capture_complete")),
        reported_complete=_flag(observation.get("complete")),
        logical_boundary_complete=_flag(observation.get("logical_boundary_complete")),
        parameter_update_sets_complete=_flag(observation.get("parameter_update_sets_complete")),
        optimizer_step_calls=_count(observation.get("optimizer_step_calls"), 65536),
        successful_optimizer_step_calls=_count(
            observation.get("successful_optimizer_step_calls"), 65536
        ),
        logical_updates=_count(observation.get("logical_updates"), _MAX_UPDATES),
    )
    catalog = observation.get("parameter_catalog")
    if not isinstance(catalog, list) or len(catalog) > _MAX_PARAMETERS:
        return unknown("parameter catalog unavailable or exceeds bounded limit")
    parameters = {}
    trainable_count = trainable_numel = frozen_count = frozen_numel = 0
    for item in catalog:
        if not isinstance(item, Mapping):
            return unknown("parameter catalog invalid")
        identity, numel = item.get("id"), _count(item.get("numel"))
        flag = _flag(item.get("requires_grad_at_observation"))
        if not (
            isinstance(identity, str)
            and _PARAMETER.fullmatch(identity)
            and identity not in parameters
            and numel is not None
            and flag is not None
        ):
            return unknown("parameter catalog incomplete or invalid")
        parameters[identity] = numel
        if flag:
            trainable_count += 1
            trainable_numel += numel
        else:
            frozen_count += 1
            frozen_numel += numel
    catalog_numel = sum(parameters.values())
    if catalog_numel > 2**63 - 1:
        return unknown("parameter catalog aggregate exceeds bounded limit")
    registered = (
        _count(result.get("parameter_count"))
        if result.get("parameter_count_complete") is True
        else None
    )
    summary["parameters"] = {
        "catalog_entries": len(parameters),
        "catalog_numel": catalog_numel,
        "requires_grad_true_entries": trainable_count,
        "requires_grad_true_numel": trainable_numel,
        "requires_grad_false_entries": frozen_count,
        "requires_grad_false_numel": frozen_numel,
        "registered_parameter_numel": registered,
        "catalog_numel_matches_registered_count": catalog_numel == registered
        if registered is not None
        else None,
        "scope": "catalogued optimizer parameters at observation, not named model layers",
    }
    records, steps = result.get("step_records"), _count(result.get("steps"), _MAX_UPDATES)
    if not isinstance(records, list) or len(records) > _MAX_UPDATES:
        return unknown("optimizer update records unavailable or exceed bounded limit")
    if steps is None or steps != len(records) or summary["logical_updates"] != steps:
        return unknown("logical update count and records disagree")
    classes, unknown_class_records = set(), 0
    complete_records = all_updated = 0
    updated_entries, updated_numel = [], []
    total_members = 0
    for number, record in enumerate(records, 1):
        if (
            not isinstance(record, Mapping)
            or type(record.get("step")) is not int
            or record["step"] != number
        ):
            return unknown("optimizer record sequence invalid")
        names = record.get("optimizer_classes")
        if not isinstance(names, list) or len(names) > 64:
            return unknown("optimizer class coverage unavailable")
        if any(not isinstance(name, str) or name not in _OPTIMIZERS for name in names):
            unknown_class_records += 1
        classes.update(name for name in names if isinstance(name, str) and name in _OPTIMIZERS)
        updated = record.get("updated_parameter_ids")
        if not isinstance(updated, list) or len(updated) > _MAX_PARAMETERS:
            return unknown("parameter update set unavailable or exceeds bounded limit")
        total_members += len(updated)
        if total_members > 65536:
            return unknown("combined parameter update sets exceed bounded limit")
        if any(
            not isinstance(identity, str) or identity not in parameters for identity in updated
        ) or len(set(updated)) != len(updated):
            return unknown("parameter update set invalid")
        complete = record.get("parameter_update_coverage_complete") is True
        complete_records += int(complete)
        all_updated += int(complete and set(updated) == parameters.keys())
        if complete:
            updated_entries.append(len(updated))
            updated_numel.append(sum(parameters[identity] for identity in updated))
    summary["updates"] = {
        "recorded_logical_updates": steps,
        "complete_update_set_records": complete_records,
        "all_catalog_updated_records": all_updated,
        "all_catalog_parameters_updated_each_record": all_updated == steps
        if steps and complete_records == steps
        else None,
        "updated_entries_per_complete_record_range": [min(updated_entries), max(updated_entries)]
        if updated_entries
        else None,
        "updated_numel_per_complete_record_range": [min(updated_numel), max(updated_numel)]
        if updated_numel
        else None,
        "optimizer_classes": sorted(classes),
        "unrecognized_optimizer_class_records": unknown_class_records,
        "scope": "completed observed updates" if steps else "no observed optimizer update",
    }
    calls, successful = summary["optimizer_step_calls"], summary["successful_optimizer_step_calls"]
    counts_consistent = (
        calls is not None and successful is not None and steps <= successful <= calls
    )
    summary["optimizer_call_counts_consistent"] = counts_consistent
    flags_complete = counts_consistent and all(
        summary[key] is True
        for key in (
            "capture_complete",
            "reported_complete",
            "logical_boundary_complete",
            "parameter_update_sets_complete",
        )
    )
    summary["status"] = (
        "observed" if flags_complete and steps and complete_records == steps else "partial"
    )
    initialization = observation.get("parameter_catalog_initialization")
    constructor_returns = (
        _count(initialization.get("successful_base_constructor_returns"), 65536)
        if isinstance(initialization, Mapping)
        else None
    )
    legacy_group_value = summary["optimizer_group_hyperparameters"]
    summary["optimizer_group_hyperparameters"] = _optimizer_group_options(
        observation.get("group_options"), parameters, calls, constructor_returns
    )
    if (
        len(json.dumps(summary, ensure_ascii=True, allow_nan=False).encode())
        > MAX_OPTIMIZER_OBSERVATION_BYTES
    ):
        summary["optimizer_group_hyperparameters"] = {
            "status": "unverified",
            "reason": "group metadata omitted at existing context bound",
        }
    if (
        len(json.dumps(summary, ensure_ascii=True, allow_nan=False).encode())
        > MAX_OPTIMIZER_OBSERVATION_BYTES
    ):
        summary["optimizer_group_hyperparameters"] = legacy_group_value
    if (
        len(json.dumps(summary, ensure_ascii=True, allow_nan=False).encode())
        > MAX_OPTIMIZER_OBSERVATION_BYTES
    ):
        return {
            "schema": summary["schema"],
            "status": "unverified",
            "reason": "optimizer summary exceeds bounded context",
            "numerical_equivalence_proven": False,
            "input_coverage_proven": False,
        }
    return summary
