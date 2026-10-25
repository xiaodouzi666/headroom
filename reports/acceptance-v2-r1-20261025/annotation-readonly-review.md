# R1 Nano annotation read-only review — 2026-10-25

This report covers only the eight synthetic cases from the completed r1 campaign. nanoGPT is excluded from this eight-case annotation check. No model or GPU call was made, no label was changed, and heuristic answers were not sent to Nano.

All eight annotation fingerprints match their saved evidence. The actual stored HTTP request copies pass their payload-hash checks and contain exactly the selected stack IDs and the final twelve frames of each selected stack. Coverage is **119/119 requested stacks**, rather than every stack in the full allocator catalogue (197 stacks across the eight captures). Annotation completion therefore does not mean classification quality passed.

## Agreement and cost

The original heuristic-agreement metric scores only selected stacks with a known heuristic category. Its aggregate is **7/79 = 8.86%**. If unknown-to-unknown matches are included, the all-selected exact-label agreement is **29/119 = 24.37%**. The conservative known-match fraction over all selected stacks is **7/119 = 5.88%**. These are comparisons against a heuristic, not independently verified semantic ground truth; they must not be described as true classification accuracy. No case reaches 80% known-category agreement.

| Case | Returned/requested | Known-heuristic matches | All-selected matches including unknown | Full-known became suffix-unknown | Conservative cost bound |
| --- | --- | --- | --- | --- | --- |
| s1_batch_too_big | 10/10 | 2/8 | 2/10 | 6 | $0.00032214 |
| s2_capacity_v2 | 14/14 | 0/11 | 3/14 | 2 | $0.00054396 |
| s3_eval_no_grad_missing | 18/18 | 1/13 | 6/18 | 7 | $0.0006693 |
| s4_loss_accumulation_graph | 15/15 | 2/10 | 6/15 | 7 | $0.0005001 |
| s5_fragmentation_varlen | 17/17 | 0/11 | 0/17 | 4 | $0.00059778 |
| s6_full_vocab_logits_fp32 | 15/15 | 0/6 | 0/15 | 5 | $0.00044916 |
| s7_frozen_params_optimizer_state | 16/16 | 0/9 | 7/16 | 2 | $0.00055632 |
| s8_two_models_resident | 14/14 | 2/11 | 5/14 | 4 | $0.00051372 |

The eight conservative Nano charges total **$0.00415248**. Every case is below $0.02. These are verified retained upper-bound charges: actual total charges remain unknown because the corresponding accounting detail is missing. Unknown actual cost has not been replaced by zero or released. The cost condition passes on its certified bound; the agreement condition does not pass.

## What the frame crop removes

All 119 selected stacks had more than twelve frames. Reapplying the same unchanged origin classifier to full frames and the actual sent suffix changes 43 classifications: **37 known origins become unknown**, while **6 optimizer-state origins become temporaries**. Thus the crop demonstrably removes information used by the existing classifier. In s3, all 18 requested labels are present, but only 1/13 known categories agrees; seven full-stack activation origins become unknown when only the transmitted suffix is classified.

This comparison does not establish that cropping caused every model disagreement. Some disagreeing stacks retain a known suffix category, the heuristic itself is fallible, and no controlled live ablation was performed. The evidence supports reviewing frame selection as a generic input-quality issue. Any future design should preserve informative caller/library frames under a clear bound and evaluate independent labels; supplying heuristic answers to the model merely to increase agreement would invalidate the comparison.

## Provenance and limits

- Campaign: `runs/evaluation/live/20261025T095016638167Z-ad191318/campaign.json`.
- Campaign SHA-256: `adbd14593d9760c30b8d6caac0ef4836e1b3e2949dab55c967c4ef7b763076b9`.
- Private metadata-only review receipt SHA-256: `d53e33e019ac592f426ef172fe8374c024cff9d39fb93d610b4eca89006eefb0`.
- The inspected annotation and classifier source hashes matched the completed r1 independent audit before calculation.
- No raw prompt, frame list, source body, hidden reasoning, private database, or credential is copied into this report.

These observations do not alter MVP target scores or certify the full original plan.
