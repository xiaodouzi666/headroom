"""Select original loss tolerances from bounded Lab forward observations."""

from collections.abc import Mapping


def observed_precision(result):
    if not isinstance(result, Mapping):
        return "unknown"
    observed = result.get("precision_observation")
    env = result.get("env")
    if not isinstance(env, Mapping):
        return "unknown"
    if (
        result.get("protocol") != "headroom.lab.v1"
        or result.get("capture_complete") is not True
        or not isinstance(observed, Mapping)
        or observed.get("protocol") != "headroom.precision.v1"
        or observed.get("source") != "lab_runtime_precision_observer_v1"
        or observed.get("complete") is not True
        or observed.get("device") != env.get("device")
        or observed.get("errors") != {}
    ):
        return "unknown"
    precision, roots = observed.get("precision"), observed.get("root_modes")
    if precision not in {"fp32", "bf16"} or not isinstance(roots, Mapping):
        return "unknown"
    if (
        any(
            type(roots.get(name)) is not int or roots[name] < 0
            for name in ("fp32", "bf16", "unknown")
        )
        or roots[precision] <= 0
        or any(roots.get(name) != 0 for name in {"fp32", "bf16", "unknown"} - {precision})
    ):
        return "unknown"
    return precision


def derive_precision(baseline, candidate, reference=None):
    """Unknown/mixed evidence keeps the original FP32 bound, never loosens it.

    The candidate's observed BF16 mode may select 2e-2 only with a known
    comparison-side mode. Baseline-to-candidate change is independent of the
    dtype used for a tolerance; two BF16 runs are not a new precision change.
    """
    before, after = observed_precision(baseline), observed_precision(candidate)
    comparator = reference if baseline.get("status") == "oom" else baseline
    comparison_before = observed_precision(comparator)
    changed = None if "unknown" in (before, after) else before != after
    precision = (
        "bf16" if after == "bf16" and "unknown" not in (before, comparison_before) else "fp32"
    )
    notes = []
    if before == "unknown" or after == "unknown" or comparison_before == "unknown":
        notes.append(
            "Incomplete, mixed or unsupported precision observations do not relax the original FP32 loss bound."
        )
    if before == after == "bf16":
        notes.append(
            "Both baseline and candidate were observed using BF16; BF16 alone is not a new precision change."
        )
    if changed:
        notes.append(
            "Observed baseline-to-candidate forward precision changed; explicit numerical-change permission is required."
        )
    return {
        "source": "lab_runtime_precision_observer_v1",
        "before": before,
        "after": after,
        "comparison_before": comparison_before,
        "observed_change": changed,
        "comparison_precision": precision,
        "notes": notes,
        "limitations": "Observed Python-dispatched forward precision, not proof of every internal operator dtype or full workload equivalence.",
    }
