# Billing resolution and protocol-v2 repair round 4
User authorization on 2026-10-27: investigate and resolve the billing anomaly, continue remaining repairs, aim for at least 6/9 automatic target successes; gift credits only, no recharge or overspend.

The original fixed nine scenarios, 6/9 threshold, strict policy, six-round/480-second per-case limits and original source/measurement gates remain. Historical results are preserved; successes cannot be pooled. Public deployment remains deferred. The fixed-nine campaign finished. Independent reconstruction confirms 3/9 targets and 6/9 valid correct first causes; the repair threshold remains unmet.

The observed account balance was $20.49 on the authenticated Token Factory billing UI, refreshed during this turn. This is a point-in-time observation, not a per-request reconciliation. The HTTP 529 attempt retains $0.0822432 and unknown actual cost after an exact evidence review. Runtime lifetime allocation remains $14.17775754 net, daily $9.99964904, per case $0.60; no extra funding or judging reserve transfer.

## Billing resolution — completed before inference

The unique unresolved attempt is e5ef4dc6a56e4b629b932f6639dabc94, run 25c824097c84424ea31362ef43ebe47b, store call 596. All eleven calls and reservations in that closed run match bijectively. The captured plain-text, single-completion request reconstructs the exact 111512-byte wire body; its cap is max_completion_tokens=4000 and reviewed Super prices yield 262144*0.3/1e6 + 4000*0.9/1e6 = $0.0822432. SDK retries are disabled and the runtime gate prevents the custom retry from dispatching.

The exact receipt SHA 9fe0f381c706b103a692ca63e36ceb1f143660e6b8f01c7a431129a6934bea0f was independently reviewed before execution. Only target review metadata and its matching halt changed. All 632 attempt monetary records, all 596 historical call records, and lifetime/daily/per-run limits remained unchanged. The complete reservation stays charged conservatively; actual remains null. This proves a safe retained bound, not that HTTP 529 was free. See billing-resolution.json and billing-focused.log (63 guarded offline tests passed).

The current official [chat-completion API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion) describes max_completion_tokens as including visible output and reasoning, with n defaulting to one. Its [billing documentation](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new) describes balance consumption and card charging on negative balance/configured thresholds. No official per-request zero-charge policy for 529 was established. Therefore the positive credit cushion, unchanged conservative ledger limit, zero ancillary fees and unchanged judging/rounding reserves remain the financial controls. No payment or recharge action was performed.

## Candidate-feedback changes — software verification passed

The generic repairs distinguish static rejection, actual candidate execution and retained baseline state; expose bounded real syntax diagnostics; identify repeated candidate bytes despite changed notes; and make checkpoint granularity and optimizer-lifetime prerequisites explicit. No scenario answers, human-control patches or historical success numbers were placed in model inputs. Precision-intent validation distinguishes source facts from proposed dtype changes while retaining actual source/runtime/numerical checks. These are improvements to the repair process, not measured scenario successes.

Final unfiltered guarded regression: **3329 passed in 762.35 seconds**. All 320 source entries were unchanged before/after; original PLAN and guard hashes were unchanged. Receipt: `full-regression-20261027T000820Z-b8789fb8-receipt.json`. The earlier 3326-test receipt is retained but is superseded for qualification by this final receipt.

## Measured R4 outcome

Source commit: `cfeb67f14f6a4e90ce8b77ee6abb99dcdd9e99c8`. The campaign completed all nine slots in 1090.34 seconds; successes were s3, s4 and s8. No historical scores or human controls were pooled. The first-cause lower bound improved to 6/9, with three unknown; this does not satisfy the separate automatic-repair target of 6/9.

| Scenario | Result | Observed limitation |
|---|---|---|
| s1 | target unmet after six rounds | Setup-only edits, static rejections and a candidate with nonfinite loss |
| s2 | needs information | Model failed to resolve visible default fallback and overlooked an independent workspace option |
| s3 | target met | Original verification passed |
| s4 | target met | Original workload offload reference and candidate verification passed |
| s5 | needs information | Requested missing evidence; no successful candidate |
| s6 | needs information after two rounds | Chunked candidate reduced memory but failed original scalar/numerical checks |
| s7 | diagnosis output failed | HTTP 200; output reached 16384 tokens, reasoning 15632; exact parser reason was not persisted |
| s8 | target met | Original verification passed |
| nanoGPT | needs information after two rounds | Initial patch rejected; no successful candidate |

The financial audit reconstructs **$1.30208280 known actual subtotal + $0.02808822 retained unknown = $1.33017102 conservative campaign charge** across 58 settled ledger attempts. Nine annotator charges remain bounded rather than falsely exact. All historical records, allocations and reserves are preserved. Remaining runtime allocation is **$3.636510964 net** before further work. No recharge or unresolved billing halt occurred.

The original frozen audit is retained at `independent-audit-original.json`; its funding snapshot-equality gate incorrectly required the later R4 ledger to equal the initial funding snapshot. The versioned history audit proves the immutable baseline, exact R2/R3 additions and sole retained HTTP529 review, then binds the complete R4 preflight. It does not rewrite old audits or remove money gates. The wire audit covers 49 reasoning-capable attempts with zero recorded integrity issues; prepared-wire evidence does not independently prove provider ingestion.

Further repair remains authorized by the owner's current request. R5 preparation addresses atomic candidates, consistent failure stages, captured scalar counts, source/default interpretation and bounded model-output handling. Existing fixed-nine threshold, strict checks, model/output/attempt limits and funding caps remain. New changes do not count as measured repair success.
