# October 30 evaluation — R17

All nine scenarios completed their evaluation. **Three of nine met the configured
verification target: s3, s4 and s8.** The unchanged threshold is six of nine, so
this campaign did not pass. This is one new campaign; historical successes are
reported separately. See the [terminal audit](terminal-review.json) and
[independent qualification summary](final-qualification-summary.json).

| Case | Result | Evidence or remaining problem |
|---|---|---|
| s1: oversized batch | Not met | Six rounds ended in syntax, unsupported-reference-contract and diagnosis errors. No candidate GPU capture. |
| s2: AdamW capacity | Not met | Baseline completed 20 steps; diagnosis requested more evidence. |
| s3: evaluation autograd | Met | Candidate completed 20 steps; all 20 recorded scalars were identical and workload pairing matched. |
| s4: retained graphs | Met | Candidate and original-workload reference completed 20 steps; the formal comparison still covers only the first 5 backward scalars. |
| s5: variable lengths | Not met | Diagnosis requested launch/runtime evidence; no candidate executed. |
| s6: full-vocabulary logits | Not met | Evidence-range and numeric-policy declarations failed validation. |
| s7: optimizer parameters | Rejected | Two freeze candidates saved memory but reduced training coverage and changed losses. |
| s8: unused teacher | Met | Candidate completed 20 steps with identical recorded scalars; full workload pairing remains incomplete. |
| Pinned nanoGPT | Not met | Diagnosis requested more evidence; no qualifying repair. |

The s7 baseline updated 34 Parameters containing 1,075,970,304 elements per step.
Both freeze candidates updated only 2 Parameters containing 2,097,408 elements.
One retained all 34 optimizer-catalog entries while freezing 32. The coverage
guard rejected both through `parameter_policy=false` and
`training_coverage_not_reduced=false`; losses also changed. Neither contributes a
target success. [Source-bound rejection evidence](s7-qualification-review.json).

The s4 reference completed 20 original-workload updates using bounded disk offload.
Its peak spill was 44,302,792,560 bytes, within the 64 GiB limit. All 1,220 packed
tensors were unpacked, and host scratch/spill cleanup left zero live objects.
**The formal numerical basis remains the first 5 scalars.** Completed-baseline
throughput and training coverage remain unknown; reference memory and timing do
not score candidate performance.

## Calls and cost

There were **59 real model responses**: 9 annotations, 23 diagnoses, 21 patch
responses and 6 Super helper responses. All 23 diagnosis requests retained the
2,000-token cap with reasoning disabled. All calls settled; nine actual call
costs remain unknown and their conservative bounds remain occupied.

| Model-ledger amount | USD |
|---|---:|
| R17 conservative charge | 0.86369752 |
| R17 known actual subtotal | 0.83529898 |
| R17 exact actual total | Unknown |
| Development-pool remainder at R17 settlement | 1.167758000 |

These model-ledger amounts are not a provider invoice or a fresh account-balance
reading. The pool was not enlarged. At settlement there were no open, halted or
unresolved ledger entries.

## Source and cleanup

Source revision: `c21cf546e2559ac513836ba8f0d17dc4919fb02b`. Canonical preparation
and proposal hashes match the campaign. All 183 implementation and 30 input pins
matched at terminal review. The six workload fields and nine requests are exactly
equal to R16. The denominator, threshold, 20 updates, seed 1337, six-round maximum
and $0.60 per-case cap remain unchanged.

All 16 Lab wrappers recorded verified cleanup and clear GPU-after inventories.
All observed worker PIDs had exited; the service exited successfully. The
six-of-nine acceptance threshold remains unmet. This review changed no source,
raw run, threshold or historical result and created no model/GPU work. The
terminal auditor ran once after the campaign finished.
