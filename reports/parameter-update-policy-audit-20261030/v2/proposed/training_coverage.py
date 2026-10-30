"""Observe narrowed training coverage; never infer numerical equivalence from totals."""

from collections.abc import Mapping
from pathlib import Path

from headroom.optimizer_observations import runtime_optimizer_observations
from headroom.verify.pairing import source_contract


def bind_training_coverage_sources(baseline, baseline_script, candidate, candidate_script):
    """Digest the caller-owned original/candidate sources without executing either.

    These are local cooperative capture bindings, not remote attestation. Missing
    original source remains unbound; a candidate must not supply its own binding.
    """
    result = {}
    for role, capture, script in (
        ("baseline", baseline, baseline_script),
        ("candidate", candidate, candidate_script),
    ):
        if script is None or not isinstance(capture, Mapping):
            continue
        contract = source_contract(Path(script))
        result[role] = {
            "run_id": capture.get("run_id"),
            "source_sha256": contract.get("source_sha256"),
        }
    return result


def training_coverage_evidence(baseline, candidate, source_bindings=None, *, required_steps=20):
    """Compare actual updated elements only for two complete bound 20-update runs.

    Parameter IDs are process local. Compare element totals within each logical
    update, never IDs or optimizer object/call counts across processes. Equal
    totals do not certify equal parameter identities, state, objective or values.
    """
    evidence = {
        "schema": "headroom.training_coverage.v1",
        "status": "unknown",
        "not_reduced": None,
        "numerical_equivalence_proven": False,
        "scope": "cooperative source/run-bound actual updated element coverage",
    }

    def unknown(reason):
        return {**evidence, "reason": reason}

    if type(required_steps) is not int or required_steps != 20:
        return unknown("this observation requires twenty complete logical updates")
    bindings = source_bindings if isinstance(source_bindings, Mapping) else {}
    measured = {}
    for role, capture in (("baseline", baseline), ("candidate", candidate)):
        binding = bindings.get(role)
        if not (
            isinstance(capture, Mapping)
            and isinstance(binding, Mapping)
            and capture.get("protocol") == "headroom.lab.v1"
            and capture.get("status") == "completed"
            and capture.get("capture_complete") is True
            and capture.get("cleanup_verified") is True
            and type(capture.get("steps")) is int
            and capture["steps"] == required_steps
            and binding.get("run_id") == capture.get("run_id")
            and capture.get("parameter_count_complete") is True
            and capture.get("parameter_count_source") == "lab_module_parameter_hooks"
        ):
            return unknown(role + " complete execution or caller source/run binding unavailable")
        # Reuse all bounded catalog, logical sequence, membership/type and source
        # checks. The expected digest comes from caller-owned source bytes.
        summary = runtime_optimizer_observations(
            capture,
            [{"path": "host-bound-entrypoint", "sha256": binding.get("source_sha256")}],
            script="host-bound-entrypoint",
        )
        if summary.get("status") != "observed":
            return unknown(role + " complete source-bound optimizer observations unavailable")
        parameters, updates = summary["parameters"], summary["updates"]
        if not (
            updates["recorded_logical_updates"] == required_steps
            and updates["complete_update_set_records"] == required_steps
            and parameters["catalog_entries"] > 0
            and parameters["registered_parameter_numel"] is not None
        ):
            return unknown(role + " actual catalog or twenty complete update sets unavailable")
        observation = capture["optimizer_update_observation"]
        by_id = {item["id"]: item["numel"] for item in observation["parameter_catalog"]}
        # The reused summary has already rejected duplicates, unknown IDs,
        # oversized sets and incomplete records; sum unique IDs per boundary.
        updated_numel = [
            sum(by_id[identity] for identity in record["updated_parameter_ids"])
            for record in capture["step_records"]
        ]
        measured[role] = {
            "run_id": summary["selected_run_id"],
            "source_sha256": summary["source_sha256"],
            "catalog_numel": parameters["catalog_numel"],
            "requires_grad_true_numel": parameters["requires_grad_true_numel"],
            "updated_numel_per_logical_update": updated_numel,
        }
    before, after = measured["baseline"], measured["candidate"]
    # Catalog membership and first-observation requires_grad flags are not
    # full-model eligibility. They may narrow when unused optimizer members
    # are removed without changing any actual update. Keep them informational.
    reduced = []
    narrowed_updates = [
        number
        for number, (left, right) in enumerate(
            zip(
                before["updated_numel_per_logical_update"],
                after["updated_numel_per_logical_update"],
                strict=True,
            ),
            1,
        )
        if right < left
    ]
    if narrowed_updates:
        reduced.append("updated_numel_per_logical_update")
    evidence.update(
        status="reduced" if reduced else "no_reduction_observed",
        not_reduced=not reduced,
        measurements=measured,
        reduced_fields=reduced,
        narrowed_logical_updates=narrowed_updates,
    )
    if reduced:
        before_catalog = before["catalog_numel"]
        before_trainable = before["requires_grad_true_numel"]
        after_catalog = after["catalog_numel"]
        after_trainable = after["requires_grad_true_numel"]
        before_update = before["updated_numel_per_logical_update"]
        after_update = after["updated_numel_per_logical_update"]
        evidence["feedback"] = (
            "TRAINING_COVERAGE_REDUCED: source-bound 20-update captures show catalog/first-flag "
            f"elements {before_catalog}/{before_trainable} -> "
            f"{after_catalog}/{after_trainable}; updated elements per "
            f"logical boundary {min(before_update)}..{max(before_update)} -> "
            f"{min(after_update)}..{max(after_update)}. Strict policy forbids freezing or dropping "
            "parameter updates; choose a repair preserving the original training coverage. "
            "Precision permission does not authorize this reduction."
        )
    else:
        evidence["feedback"] = (
            "No reduction in observed actual update-element coverage; catalog and first flags do "
            "not prove full-model eligibility, identical parameter sets or numerical equivalence."
        )
    return evidence
