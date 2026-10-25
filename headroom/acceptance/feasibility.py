"""Offline algebra for fixed-state memory-share and capacity-repair requirements.

This audits the supplied constraints only. It does not infer optimizer state from
an optimizer name, rewrite acceptance rules, or certify a training result.
"""

from __future__ import annotations

import argparse
import json
from fractions import Fraction


def _bytes(value, name, *, positive=False):
    if value is not None and (type(value) is not int or value < (1 if positive else 0)):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a {qualifier} integer or None")
    return value


def _fraction(value):
    if not isinstance(value, str):
        raise TypeError("minimum_state_fraction must be an exact decimal or rational string")
    try:
        fraction = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError("minimum_state_fraction must be in (0, 1]") from error
    if not 0 < fraction <= 1:
        raise ValueError("minimum_state_fraction must be in (0, 1]")
    return fraction


def _ratio(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def audit_fixed_state_capacity(
    *,
    optimizer_state_bytes: int | None,
    minimum_state_fraction: str,
    fit_limit_bytes: int | None,
    observed_peak_bytes: int | None = None,
):
    """Check whether one integer-byte baseline peak could meet both requirements.

    The first requirement is state / peak >= minimum_state_fraction. The second
    is peak > fit_limit_bytes, necessary for demonstrating a capacity repair.
    State bytes must describe the same fixed fixture and peak accounting domain;
    a caller must independently establish that provenance. Missing measurements
    remain unknown. Compatible bounds do not establish an executable workload,
    the required number of search rounds, numerical equivalence, or acceptance.
    """
    state = _bytes(optimizer_state_bytes, "optimizer_state_bytes")
    limit = _bytes(fit_limit_bytes, "fit_limit_bytes", positive=True)
    peak = _bytes(observed_peak_bytes, "observed_peak_bytes", positive=True)
    fraction = _fraction(minimum_state_fraction)
    if state is not None and peak is not None and state > peak:
        raise ValueError("optimizer_state_bytes cannot exceed its observed allocated peak")

    ceiling = None if state is None else Fraction(state) / fraction
    largest_peak = None if ceiling is None else ceiling.numerator // ceiling.denominator
    missing = [
        name
        for name, value in (
            ("optimizer_state_bytes", state),
            ("fit_limit_bytes", limit),
        )
        if value is None
    ]
    if missing:
        status = "unknown"
        reason = "Missing input: " + ", ".join(missing)
    elif largest_peak <= limit:
        status = "incompatible"
        reason = (
            "Every integer-byte peak satisfying the state-share requirement "
            "already fits the capacity target."
        )
    else:
        status = "not_ruled_out"
        reason = (
            "At least one integer-byte peak can satisfy both inequalities; "
            "no real workload or repair outcome has been established."
        )

    observed_fraction = None if state is None or peak is None else Fraction(state, peak)
    return {
        "schema_version": "headroom.acceptance-feasibility.v1",
        "kind": "conditional_fixed_state_constraint_audit",
        "inputs": {
            "optimizer_state_bytes": state,
            "minimum_state_fraction": _ratio(fraction),
            "fit_limit_bytes": limit,
            "observed_peak_bytes": peak,
        },
        "assumptions": [
            "State bytes are fixed for the same fixture and allocated-peak accounting domain.",
            "Demonstrating capacity repair requires the baseline peak to exceed the fit limit.",
            "Byte counts and their provenance must be established independently.",
        ],
        "derivation": {
            "state_share_constraint": "optimizer_state_bytes / peak_bytes >= minimum_state_fraction",
            "capacity_repair_precondition": "peak_bytes > fit_limit_bytes",
            "exact_peak_upper_bound_bytes": None if ceiling is None else _ratio(ceiling),
            "largest_integer_peak_bytes": largest_peak,
            "first_integer_peak_above_fit_bytes": None if limit is None else limit + 1,
        },
        "compatibility": {"status": status, "reason": reason},
        "observed": {
            "state_fraction": None if observed_fraction is None else _ratio(observed_fraction),
            "state_share_requirement_met": (
                None if observed_fraction is None else observed_fraction >= fraction
            ),
            "baseline_already_fits": None if peak is None or limit is None else peak <= limit,
        },
        "acceptance_certified": False,
        "historical_results_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--optimizer-state-bytes", type=int)
    parser.add_argument("--minimum-state-fraction", required=True)
    parser.add_argument("--fit-limit-bytes", type=int)
    parser.add_argument("--observed-peak-bytes", type=int)
    args = parser.parse_args()
    try:
        report = audit_fixed_state_capacity(
            optimizer_state_bytes=args.optimizer_state_bytes,
            minimum_state_fraction=args.minimum_state_fraction,
            fit_limit_bytes=args.fit_limit_bytes,
            observed_peak_bytes=args.observed_peak_bytes,
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
