# R12 partial terminal review — 2026-10-30

R12 stopped after its first scenario with child_execution_or_cost_unverified. Only s1 ran; eight scenarios remain not_run. The fixed nine denominator and threshold six stay unchanged. Selected targets are **0/9**, diagnostic-model coverage **0/9**, and this is not a completed nine-case acceptance run.

A real s1 GPU baseline OOM was captured. The single real Nano annotation request then timed out, leaving input/output usage and exact charge unknown. diagnose.started occurred before admission; no Ultra diagnosis request was dispatched. No patch or candidate GPU execution occurred, and numerical verification was unavailable.

## Accounting boundary

The saved campaign incorrectly retains scope_charged=0, scope_actual=0, remaining=4.890504400 and all_costs_resolved=true. Those stale controller fields are preserved, not accepted as financial evidence.

The original new-pool ledger instead records one dispatched, settled-but-unknown attempt, retaining the full **$0.01644864 provider reservation**, actual=null and charge_status=unknown. Its run is closed with provider_charge_unknown. Arithmetic remaining is $4.874055760, but the unresolved charge blocks further dispatch. The reservation is not an asserted actual charge, and the exact cost is not zero.

## Source and cleanup evidence

All **174 implementation pins and 30 input pins** still match the prepared source. The baseline capture and saved worker timing both verify cleanup; the worker finished in 136.2 seconds under its 480-second limit. Current unit/process observations and raw hash-bound evidence are in terminal-review.json.

The review made no model request, GPU execution, retry, source edit, ledger mutation, charge review or publication. R12 uses an isolated Store at its execution directory; absence from the main Store is expected.
