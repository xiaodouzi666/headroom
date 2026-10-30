# R9 fixed-nine review — 2026-10-30

**R9 finished all nine scenarios: 0/9 memory targets, below the unchanged 6/9 requirement.**
Raw first-category matches were 7/9, valid-and-correct first diagnoses 6/9,
and ready diagnoses 0/9. s5 and nanoGPT truth remain unverified; they never
count as correct or incorrect. Improving response validity is not a completed
automatic repair or overall acceptance.

Campaign: runs/final48-f3-retry/execution-r9-20261030/campaign.json
SHA256: d1379002f4804d5a9ef935a12e30bb4141463719214140686bf05be8043dd371
Source commit: 5817a723df82bf9596397f9ae95598925088f1e0.
The campaign is finished, executed_cells=9 and stop_reason=null. The first
eight ended needs_human; nanoGPT ended failed with a saved pipeline
ResponseValidationError. All nine retained target=false. This review only
reads saved evidence and did not run a model or GPU job.

## Per-scenario outcome

| Scenario | Terminal status | First diagnosis valid | Ready | Target |
|---|---|---|---|---|
| s1_batch_too_big | needs_human | true | false | false |
| s2_capacity_v2 | needs_human | true | false | false |
| s3_eval_no_grad_missing | needs_human | true | false | false |
| s4_loss_accumulation_graph | needs_human | true | false | false |
| s5_fragmentation_varlen | needs_human | true | false | false |
| s6_full_vocab_logits_fp32 | needs_human | false | false | false |
| s7_frozen_params_optimizer_state | needs_human | true | false | false |
| s8_two_models_resident | needs_human | true | false | false |
| nanogpt | failed | unknown | unknown | false |

Seven of the eight saved first diagnoses are valid but need more information.
s6 remains invalid because the proposed chunked cross-entropy step was rejected
as NUMERICS_CHANGE_FORBIDDEN under its original policy. nanoGPT has no saved
first-round diagnosis and the report states Pipeline failed:
ResponseValidationError; the absence of that artifact is not a valid diagnosis.
No policy, target, threshold or old result was changed.

## Costs and remaining allocation

For R9 alone, exact actual total remains **null**. Known actual subtotal is
USD 0.552812364 and the resolved charged total is USD 0.571730364.
Six runs have incomplete actual costs; no run has unresolved conservative
charge. These values are distinct and must not be combined or called a final
provider bill.

Saved terminal accounting: original F3 cap USD 4, cumulative charged
USD 2.611614004, remaining USD 1.388385996. Original F48 cumulative charged
USD 3.913980116, remaining USD 2.516019884. all_costs_resolved=true.
This is campaign accounting, not a fresh provider-account balance query.
The historical R7 and R8 costs/results remain unchanged.

## Nano annotation review

The original eight synthetic scenarios produced 7/8 complete, exact saved
stack-ID sets. Eight fingerprints match their original evidence captures.
s2 failed with missing_duplicate_or_unrecognized_stack; its saved artifact
contains zero accepted annotations, so this review cannot identify which
underlying ID-set subcase occurred. A matching fingerprint alone does not
establish a complete result.

Heuristic agreement for s1 through s8 is:
0.125, null, 0.15384615384615385, 0.5, 0, 0,
0.2222222222222222, 0.18181818181818182.
Thus **0/8 reaches 80%**. nanoGPT is separate: complete, matching IDs/fingerprint,
agreement 0.6666666666666666. It does not enlarge the denominator.
The preserved R7 and R8 complete-set results are respectively 5/8 and 8/8;
neither historical result was overwritten. Exact-ID coverage measures
structure, not correctness, and heuristic agreement is not adjudicated truth.

## Review artifacts and publication boundary

- summary.json: fixed-nine outcomes and independent raw/valid/ready counts.
- projection-receipt.json: bounded source/output hashes and recheck evidence.
- nano-review.json: per-run source hashes, saved stack IDs and fingerprints.
- staging/: review-only public projection; not installed into production.
- ../f3-retry-20261030/r9-summary-execution.json: exact read-only command,
  exit 0 and elapsed 1.167 seconds.

The R9 summary script is the reviewed R8 algorithm with revision/title/path
labels changed only. A separate publication plan preserves every current
public registry entry and puts R9 first. No source registry, runtime publication
directory or service was changed by this review.
