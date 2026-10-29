# Remaining CPU focused checks — 2026-10-29

The exact 23 CPU nodes left unverified by the closing-regression follow-up all passed on `ed731973a97a5d933321f9f3809e18d9f12fc78d`: **23 passed / 0 failed / 0 errors / 0 skipped**, pytest **213.78 s**, driver **214.531 s**, exit **0**. This is one bounded focused batch; no full regression was repeated and none of the prior 13 passed CPU representatives were selected.

## Scope and isolation

The node list is preserved verbatim in [targets.json](targets.json), sourced from [the earlier pending list](../final48h-closing-regression-20261029/cpu-not-rechecked.json). Every target's test body and the shared Docker/reference setup were inspected before execution. Tests use explicit CPU devices, temporary output/fixture roots, existing local runtime images, and Docker network `none`. The credentials-absence test uses synthetic canaries; it does not load real keys. CPU results do not count toward GPU repair acceptance.

The unchanged [v4 guard](../final48h-closing-regression-20261029/closing_guarded_v4.py), SHA-256 `eb54c81fac699d94f3b48d5f6802404220e41fc7b24a9a0da58a4be4733464cb`, passed parent and spawned-process negative probes before the batch and again at test startup. It denies real provider credentials, production databases/profiles, DNS/INET, GPU/privileged Docker options, networked containers, and service commands. Its existing three historical-JSON read redirects remain isolated temporary copies; this batch added no redirects or guard exceptions. See [guard-probe.log](guard-probe.log).

| Target group | Checks exercised |
|---|---|
| Optimizer controls (5) | 20 logical updates, exact parameter/state equivalence across three configurations, unsupported-use rejection |
| Deadline/finalization (6) | Soft timeout capture, swallowed signals, uncapturable targets, hard stop during serialization |
| Pairing (3) | s1/s3/s4 paired CPU controls, exact losses and invalid-pair rejection |
| Runner (3) | Seed determinism, 30-second timeout and child cleanup, canary absence/read-only source |
| Independent reference (3) | AdamW, HF Trainer CPU smoke and SGD through separate container controller |
| Checkpoint/verify/watch (3) | Transformed-source attestation, half-model rejection, supported flag/environment parity |

The driver removed provider environment bindings, disabled CUDA and automatic pytest plugin loading, disabled pytest's cache provider, and set a **600-second batch limit**. The original test thresholds and assertions were unchanged. Exact command, timestamps and hashes are in [receipt.json](receipt.json); [run-focused.py.txt](run-focused.py.txt) retains the executed driver as text so formatting tools do not rewrite evidence.

## Results and cleanup

- [focused.log](focused.log) and [focused.junit.xml](focused.junit.xml) are raw execution evidence; [case-results.json](case-results.json) maps all 23 exact nodes to outcomes and durations.
- [sources-before.json](sources-before.json) and [sources-after.json](sources-after.json) match across **436** production/test/configuration source entries. Docs/reports and runtime data are excluded from this code-stability comparison; parent documentation work can continue independently.
- **38** saved CPU Lab/reference result records, covering **38** distinct containers, report `cleanup_verified=true`. None of these containers remains in the post-run Docker inventory. [cleanup-evidence.json](cleanup-evidence.json) preserves relative artifact paths, hashes, run IDs and cleanup status.
- Before/after Docker name inventories match. No additional cleanup command was needed, and pre-existing containers were untouched.
- No provider/model calls, GPU jobs, production database/profile mutation, test edits, or production code changes were performed.

## Evidence boundaries

The original full-suite result remains **4182 passed / 185 failed / 18 errors** at its original revision; its failed receipt and logs are not overwritten or relabeled. The prior 13 CPU passes and these 23 passes are separate focused batches, not a new full-suite pass.

The two non-CPU guard-limited cases listed in [final-receipt.json](final-receipt.json) remain outside this batch and are not claimed reverified here. This batch also does not change R7 **1/9** against the **6/9** acceptance threshold, snapshot **0/2**, video/submission state, or other outstanding release requirements.
