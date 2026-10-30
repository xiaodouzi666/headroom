# S2 observational pairing — implementation and CPU evidence

This closes the missing source-contract adapter identified in R7's first-three failure analysis. Only new captures can obtain the added observations. No historical result, source fixture, policy threshold, campaign score or numerical acceptance rule was changed.

## Supported source and edits

The adapter separately pins the complete normalized AST of:

| Profile | Original source SHA-256 |
| --- | --- |
| s2_capacity_v2 | 9565acfbcfc2f1eefd982c80be7ce943e09828578b9b44c3d70342bc82bf7f4c |
| s2_fp32_adamw_1b | bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b |

The new optimizer normalization accepts only the existing single `torch.optim.AdamW(model.parameters(), lr=1e-4, foreach=True)` call with its literal `foreach` changed to `False`. The rest of the program must match its reviewed AST.

The existing checkpoint normalization also applies to these two profiles: exactly the pinned `block(hidden)` call may become the imported checkpoint call with `use_reentrant=False` and absent or explicitly true `preserve_rng_state`. Both changes may be combined. The pre-existing literal loss.backward(retain_graph=True/False) normalization also remains applicable; it preserves the single backward call, and does not accept a second backward or a changed loss expression. Ordinary comments/formatting are ignored by AST comparison. No optimizer parameters, learning rate, weight decay, precision, objective, input construction, model dimensions, outer update loop or accumulation changes are normalized.

The source contract alone is not observed execution. The existing initialization tracer fingerprints actual inputs, targets and initial parameters; the existing forward/backward and successful optimizer hooks associate the actual optimizer object with one root forward and one backward per update. The solver's existing runtime-input projection now accepts these new, source-bound captures without a separate inference from defaults.

The original and capacity-v2 profiles remain distinct. A capture from one is not a pairing proof for the other. The objective label correctly identifies AdamW rather than the previous SGD-only label. Objective pairing is not a proof that all subsequent parameter or optimizer-state bits are identical.

## Bounded initialization hashing

A simple new AST pin was insufficient: the previous 512 MiB total hash limit cannot cover s2's roughly one-billion-parameter initialization. The two s2 contracts now permit at most 6 GiB total actual tensor bytes, with 4 MiB maximum host-copy chunks and a 60-second aggregate initialization-hash time check before and after each chunk. Other profiles retain the 512 MiB total limit.

Non-contiguous initial tensors are unsupported instead of making an unbounded contiguous copy. No full multi-GiB host byte string is materialized. The time check cannot interrupt a single blocked tensor transfer; the outer Lab deadline and process supervision remain the hard containment boundary. The initialization hash time continues to be excluded once from optimizer step intervals, while end-to-end wall time still includes it.

A real CPU 8 MiB + 4 byte test observed copies of 4,194,304 / 4,194,304 / 4 bytes, 0.017136 seconds elapsed, and 4,195,089 bytes of peak Python-traced allocations. This is not a whole-process RSS measurement or a benchmark of the full-size GPU workload. Tests separately exercise total-byte rejection and timeout rejection without allocating 6 GiB.

## Verification

- Existing and new non-Docker pairing cases: **55 passed, 9 deselected in 2.49s**.
- Five selected actual CPU cases: **5 passed, 30 deselected in 42.84s**. These comprise the bounded hashing measurement and four scenario/edit combinations, with **eight actual tiny CPU Docker captures**.
- The groups are disjoint: 60 selected test cases in total. Earlier development runs are not added.
- Ruff check / format check and scoped git diff --check passed.
- Network and GPU initialization are denied in the new test module; Docker targets use the existing no-network CPU Lab. No model, provider, GPU or production-budget action occurred.

For both source versions, each baseline and candidate completed 20 optimizer updates and recorded 20 loss scalars. Input fingerprints, initial-parameter fingerprints, objective and effective batch paired. All four CPU comparisons had identical recorded bits for all 20 finite loss scalars. The optimizer-update evidence also recorded complete parameter-update sets. Cleanup was verified for all eight containers.

This establishes small CPU instrumentation behavior. It does not establish the real 22 GB target, full-size initialization cost, GPU throughput, GPU scalar equality, successful automatic repair, or either F3 s2 numerical tier. Existing numerical and throughput validation still decides those outcomes.

The source hashes, unique run IDs, result-file hashes, all four comparisons and hashing measurement are recorded in receipt.json. Raw artifacts are retained under reports/runs/s2-pairing-20261030-v1/. The initial import-order lint failure is preserved in ruff.log; ruff-final.log records the corrected result.

## Still unsupported

- Optimizer-in-backward / per-parameter optimizers: the existing logical-update observer may count complete updates, but this source adapter deliberately cannot pair that changed optimizer identity or update schedule.
- BF16, autocast, optimizer state precision changes, fused optimizers, altered hyperparameters, microbatching / gradient accumulation and arbitrary extra source edits.
- Arbitrary scripts, wrapper-command mode, incomplete captures and deliberate hook tampering.
- Historical s2 captures whose contract was unsupported. Their complete=false and empty updates remain unchanged and are regression-tested as unobserved.

Lossless saved-tensor offload remains an existing explicit reference mode. New s2 source recognition can satisfy that mode's source-contract prerequisite, but still requires original-baseline binding and all existing reference checks; this change does not enable or run it automatically. The specialized checkpoint-reference transformer remains restricted to s1.

## Next real verification (not executed here)

After the root operator permits a new GPU capture, this invokes the normal Lab with the unchanged capacity-v2 source and original workload; no model API is involved:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from headroom.lab.runner import run_script

result = run_script(
    Path("scenarios/s2_capacity_v2/train.py"),
    script_args=["--seed", "1337", "--steps", "20"],
    run_root=Path("runs/s2-pairing-new-capture-20261030"),
    device="cuda", seed=1337, max_steps=20, max_seconds=480,
    allocator_conf="expandable_segments:True",
)
print(json.dumps({
    "run_id": result["run_id"],
    "status": result["status"],
    "steps": result.get("steps"),
    "pairing_complete": result.get("pairing_capture", {}).get("complete"),
    "cleanup_verified": result.get("cleanup_verified"),
    "run_dir": result["run_dir"],
}))
PY
```

Expected evidence is a fresh complete capture with actual inputs/targets, initial-parameter hashes, 20 associated updates, complete update-set observations and verified cleanup. Any timeout, hash-limit failure or incomplete update observation stays unverified. A later candidate must pass the unchanged comparison against this same original workload; no existing R7 result should be rescored or overwritten.

Independent read-only review by frontend_browser_checks passed against the frozen pairing.py SHA in receipt.json; the reviewer did not execute tests, models or GPU work.
