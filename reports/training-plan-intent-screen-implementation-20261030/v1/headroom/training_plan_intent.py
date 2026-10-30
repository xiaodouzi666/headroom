"""Narrow existing-policy intent feedback from bound complete original updates.

This is not source verification, optimizer authentication or a candidate proof.
Ambiguous intent or incomplete original coverage leaves downstream gates alone.
"""

import re
from collections.abc import Mapping

from headroom.observation_feedback import bound_optimizer_observation

_CLAUSE_BREAK = re.compile(r"[;!?\n]|\.(?!\w)")
_NON_ACTION = re.compile(
    r"\b(?:prior|previous|rejected|forbidden|invalid|incorrect|hypothetical|example|if|unless|conditional|might|could|consider)\b"
    r"|\bnot\s+(?:proposed|selected|recommended|the\s+plan)\b"
    r"|\b(?:do\s+not|never|avoid)\s+(?:choose|use|include|propose|apply|recommend)\s+[`\'\"]",
    re.IGNORECASE,
)
_ACTION = re.compile(
    r"\b(?:set|setting|add|adding|call|calling|use|using|apply|applying)\b", re.IGNORECASE
)
_FALSE = re.compile(r"\brequires_grad(?:_\s*\(\s*False\s*\)|\s*=\s*False)", re.IGNORECASE)
_FREEZE = re.compile(
    r"\b(?:freeze|freezing)\s+(?:[\w.]+\s+){0,5}(?:parameters?|weights)\b", re.IGNORECASE
)
_EXCLUDE = re.compile(
    r"\b(?:exclude|excluding|remove|removing|omit|omitting)\s+"
    r"(?:[\w.]+\s+){0,6}(?:parameters?|weights)\s+from\s+"
    r"(?:the\s+)?optimizer(?:\s+state)?\b",
    re.IGNORECASE,
)
_HEAD_ONLY = re.compile(
    r"\b(?:pass|passing|supply|supplying)\s+only\s+[\w.]+\.parameters\s*\(\s*\)"
    r"\s+to\s+(?:the\s+)?(?:optimizer|AdamW|Adam|SGD)\b|"
    r"\b(?:train|training|update|updating)\s+only\s+(?:the\s+)?"
    r"(?:head|classifier|adapter)(?:\s+parameters?)?\b",
    re.IGNORECASE,
)
_STOP = re.compile(
    r"\b(?:stop|stopping|cease|ceasing)\s+updating\s+"
    r"(?:[\w.]+\s+){0,6}(?:parameters?|weights)\b",
    re.IGNORECASE,
)
_MEMORY_OBJECT = re.compile(
    r"\s+(?:gradients?|buffers?|state|references?|metadata)\b", re.IGNORECASE
)


def _positive(clause, match, negation_pattern):
    if _NON_ACTION.search(clause):
        return False
    prefix = re.sub(r"[\`\'\"(]+\s*$", "", clause[: match.start()])
    negation = negation_pattern.search(prefix)
    return not (
        negation is not None and negation_pattern.search(prefix[: negation.start()]) is None
    )


def _intent(description, negation_pattern):
    if type(description) is not str or len(description) > 16384:
        return None
    freeze = exclude = False
    for clause in _CLAUSE_BREAK.split(description):
        for match in _STOP.finditer(clause):
            if not _MEMORY_OBJECT.match(clause, match.end()) and _positive(
                clause, match, negation_pattern
            ):
                return "explicit_stop_updating_parameters"
        for match in _FREEZE.finditer(clause):
            if not _MEMORY_OBJECT.match(clause, match.end()) and _positive(
                clause, match, negation_pattern
            ):
                freeze = True
        for match in _FALSE.finditer(clause):
            # A source fact or an isolated code token is not a proposed action.
            actions = list(_ACTION.finditer(clause[: match.start()]))
            if (
                actions
                and match.start() - actions[-1].end() <= 128
                and _positive(clause, actions[-1], negation_pattern)
            ):
                freeze = True
        for pattern in (_EXCLUDE, _HEAD_ONLY):
            if any(
                _positive(clause, match, negation_pattern) for match in pattern.finditer(clause)
            ):
                exclude = True
    return "explicit_freeze_and_optimizer_exclusion" if freeze and exclude else None


def training_update_rejection_trigger(description, evidence, policy, *, negation_pattern):
    """Return only typed, already-supplied trigger data; never edit a diagnosis."""
    if not isinstance(policy, Mapping) or policy.get("allow_model_change") is not False:
        return None
    if not isinstance(evidence, Mapping) or not isinstance(evidence.get("sources"), (list, tuple)):
        return None
    context = evidence.get("execution_context")
    if not isinstance(context, Mapping) or "selected_round" not in context:
        return None
    required = context.get("required_optimizer_updates")
    # Deliberately narrow first screen. Other requested lengths retain the
    # original source/runtime policy checks without this extra prose predicate.
    if type(required) is not int or required != 20:
        return None
    run_id = evidence.get("run_id")
    if type(run_id) is not str or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        return None
    observed = bound_optimizer_observation(
        context, selected_run_id=run_id, sources=evidence["sources"]
    )
    if observed is None or "selected_round" not in observed or observed.get("status") != "observed":
        return None
    if any(
        observed.get(key) is not True
        for key in (
            "capture_complete",
            "reported_complete",
            "logical_boundary_complete",
            "parameter_update_sets_complete",
            "optimizer_call_counts_consistent",
        )
    ):
        return None
    parameters, updates = observed.get("parameters"), observed.get("updates")
    if not isinstance(parameters, Mapping) or not isinstance(updates, Mapping):
        return None
    names = (
        "catalog_entries",
        "catalog_numel",
        "registered_parameter_numel",
        "requires_grad_true_entries",
        "requires_grad_true_numel",
        "requires_grad_false_entries",
        "requires_grad_false_numel",
    )
    if any(
        type(parameters.get(key)) is not int or not 0 <= parameters[key] < 2**63 for key in names
    ):
        return None
    entries, numel = parameters["catalog_entries"], parameters["catalog_numel"]
    if not (
        entries > 0
        and numel > 0
        and parameters["registered_parameter_numel"] == numel
        and parameters.get("catalog_numel_matches_registered_count") is True
        and parameters["requires_grad_true_entries"] == entries
        and parameters["requires_grad_true_numel"] == numel
        and parameters["requires_grad_false_entries"]
        == parameters["requires_grad_false_numel"]
        == 0
    ):
        return None
    if type(observed.get("logical_updates")) is not int or observed["logical_updates"] != required:
        return None
    for key in (
        "recorded_logical_updates",
        "complete_update_set_records",
        "all_catalog_updated_records",
    ):
        if type(updates.get(key)) is not int or updates[key] != required:
            return None
    if updates.get("all_catalog_parameters_updated_each_record") is not True:
        return None
    for key, expected in (
        ("updated_entries_per_complete_record_range", entries),
        ("updated_numel_per_complete_record_range", numel),
    ):
        value = updates.get(key)
        if (
            type(value) is not list
            or len(value) != 2
            or any(type(n) is not int or n != expected for n in value)
        ):
            return None
    calls, successful = (
        observed.get("optimizer_step_calls"),
        observed.get("successful_optimizer_step_calls"),
    )
    if (
        type(calls) is not int
        or type(successful) is not int
        or not required <= successful <= calls <= 65536
    ):
        return None
    criterion = _intent(description, negation_pattern)
    if criterion is None:
        return None
    return {
        "basis": "existing_model_change_policy_and_selected_complete_update_observation",
        "criterion": criterion,
        "selected_run_id": run_id,
        "selected_round": context["selected_round"],
        "source_sha256": observed["source_sha256"],
        "required_optimizer_updates": required,
        "catalog_entries": entries,
        "catalog_numel": numel,
        "registered_parameter_numel": numel,
        "requires_grad_true_entries": entries,
        "requires_grad_true_numel": numel,
        "all_catalog_updated_records": required,
        "updated_numel_per_complete_record_range": [numel, numel],
        "scope": "Selected original cooperative capture only; no native authentication or candidate equivalence proof.",
    }
