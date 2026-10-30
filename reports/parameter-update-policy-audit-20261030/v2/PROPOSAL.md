# V2 proposal: enforce reduced actual optimizer update coverage

Report-only proposal. No headroom/tests changes or model/GPU runs were performed. Every v1 proposal and receipt remains byte-for-byte unchanged, with preservation hashes in v1-preservation-pins.json.

## Correction from v1

The optimizer catalog does not enumerate the full model's trainable eligibility. requires_grad_at_observation is only its first flag, not evidence that a parameter took part in any backward or update. A parameter may require gradients yet remain unused in the executed path. Removing such a redundant member can reduce catalog/trainable totals while preserving every actual update. V1 could incorrectly reject that legitimate repair.

V2 therefore uses only a decrease in actual updated-parameter element totals at a corresponding complete logical update boundary as its strict counterexample. Catalog size and first-flag trainable elements remain supporting observations in feedback and can never independently reject a candidate.

## Minimal implementation

As in v1, host-owned original/candidate source digests and run IDs bind the two complete cooperative Lab captures. runtime_optimizer_observations supplies the existing strict catalog, ID, sequence, membership, source/run and completeness validation. Both executions must contain twenty complete logical update records; missing/partial/zero-step OOM remains unknown. Each record's unique updated_parameter_ids is mapped to its own process-local catalog and summed in elements.

Only when actual updated elements decrease at one or more corresponding boundaries and allow_model_change=false does the existing parameter_policy become false. The existing search hard gate rejects it and sends the front-loaded concrete feedback through the existing same-six-round history. No REQUIRED_CHECKS entry, numerical/memory threshold, budget, call, retry or acceptance definition is added.

Raw optimizer object/step-call counts are not compared. A valid AdamWInBackward implementation with 34 native children, 680 calls and twenty full logical update unions remains acceptable. Removing already-frozen or still-requires-grad-but-never-updated members is not rejected when actual update coverage stays identical. Lossless flattening is not rejected merely because Parameter object count changes.

Precision/BF16 and batch/accumulation permission do not authorize dropping actual parameter updates. This is a strict-only guard; it does not replace existing explicit objective authorization or MODEL_CHANGE_APPROVED checks. Equal observed element totals are not a proof of equal parameter identities, optimizer state, values or objective. Hook observations are cooperative, not adversarial attestation; version-counter advancement does not prove a numerically nonzero change.

## Validation

28 v5-guarded report-only draft cases passed in 0.80s. The added counterexample has 238-to14 first-flag/catalog elements but 14-to14 actual updated elements at all twenty boundaries; it retains the original parameter_policy and is not rejected. The actual R14 s7 capture projection still shows 1,075,970,304-to2,097,408 updated elements and is rejected. Missing/malformed bindings, partial capture and zero-step OOM remain unknown. The unchanged valid34-child case and the concrete next-round feedback tests pass.

proposal.diff is for review only and has not been applied. Exact final source/draft hashes and raw receipts are recorded in proposal-verification.json. v1-to-v2-helper.diff isolates the semantic correction.
