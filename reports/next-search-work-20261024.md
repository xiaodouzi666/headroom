# Remaining original-plan development: bounded Pareto exploration

This is a read-only implementation audit, not completed work or changed acceptance.

The current orchestrator stops after the first kept target_met configuration.
PLAN C.5 explicitly says to stop at the target (four rounds); T2.1 expands search
to six rounds and multiple independently patched Pareto configurations. Preserve
the current default and add an explicit bounded_pareto mode rather than silently
removing the original stopping rule.

Minimal remaining work:
- Thread until_target/bounded_pareto through FixRequest, CLI/YAML/API and reports.
- In bounded mode continue after the first target hit, within the same money,
  time, round and numerical policy limits. Retain a prior successful result if a
  later exploration is reverted or budget stops the search.
- Record baseline_target_met, first_target_met_round and search_stop_reason.
- Reuse genuine non-dominated filtering and independent cumulative patches;
  never count duplicate, reverted or unverified configurations as extra tiers.
- Verify with offline provider fixtures: target first reached in round one,
  later useful/reverted rounds, budget stop after success, and hard precision policy.

The current s2 model has 8,593,604,608 bytes of fp32 AdamW moments. Its 40% gate
implies peak <=21.48401152 GB, already below 22 GB. The separate foreach=False
diagnostic does not solve that joint constraint. A versioned, pending calibration
candidate must satisfy both constraints with real measurements while preserving
the current scenario and historical failures. Different source versions cannot
be combined as repair before/after evidence.

Default precision policy still forbids numerical change. A bounded search mode
cannot silently authorize the bf16 tier named elsewhere in T2.1. No model calls,
GPU workloads, policy changes or PLAN edits were performed for this audit.
