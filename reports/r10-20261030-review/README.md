# R10 fixed-nine review — 2026-10-30

R10 finished all nine scenarios: **0/9 memory targets**, below the unchanged internal threshold of 6/9. Raw first-category matches were **5/9**, validated correct first causes **4/9**, and ready diagnoses **0/9**. Source revision: 8f8701a. Unknown s5 and nanoGPT reference causes remain in the denominator and are not silently marked correct or incorrect.

The source campaign is `runs/final48-f3-retry/execution-r10-20261030/campaign.json`, SHA256 `39459b2cac6a68dc7666afc947bb4b949f116432da4fcdbd0434e1439c61de86`. The original projection algorithm was used unchanged except revision labels. Seven synthetic cases ended needs_human; s8 failed. nanoGPT ended failed. This review generated no model calls, GPU workloads or new evaluation results.

## Cost

For R10 alone, actual total remains null; known actual subtotal is USD 0.635661296, resolved conservative charged total USD 0.648017156. Four runs have incomplete exact actual usage; no charge is unresolved. Terminal original F3 charged USD 3.259631160, remaining USD 0.740368840; F48 remaining USD 1.868002728. These ledger figures are not a fresh provider balance or final invoice.

## Nano advisory labels

The fixed eight synthetic cases produced 8/8 complete sets, 8/8 exact saved ID sets, 8/8 matching fingerprints, and 0/8 at least 80% heuristic agreement. This agreement is not independent truth accuracy. nanoGPT remains a separate row. Detailed source artifact hashes and row outcomes are in nano-review.json. Earlier R7/R8/R9 results remain untouched.

## Publication

`staging/public-evaluations.json` contains only the new R10 registry entry. Merge it before the existing registry entries; do not replace the registry with this single-item file. The paired campaign is `staging/published-evaluations/r10-20261030.json`. The projection receipt preserves all source/output hashes and confirms no publication. Root owns the final public/runtime copy and Devpost update.
