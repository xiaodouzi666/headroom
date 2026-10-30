# Proposed enforcement of the existing training-update contract

This is a reviewable report-only patch, not an applied implementation. R15 headroom/tests remain unchanged at 964b658.

The existing prompt contract already forbids freezing trainable parameters or replacing full updates by a subset without explicit objective authorization. Registered model size does not detect that violation. The proposal routes a known measured violation through the existing parameter_policy gate; REQUIRED_CHECKS, the fixed-nine denominator, 6/9 threshold, numerical policy, twenty-update rule and budget/call limits are unchanged.

## Proposed mechanism

verify_script supplies host-built run/source digest bindings from the actual original and candidate source files. The helper reuses runtime_optimizer_observations catalog, record, source digest, membership, sequence and bound checks. Both baseline and candidate must be complete, cleaned, source/run-bound executions with twenty complete logical update records. Unsupported named-input AST profiles do not suppress independent observed optimizer facts, and source digest presence is not mathematical equivalence.

The helper compares observed trainable element totals and each logical update's unique parameter-element total. If either narrows, strict allow_model_change=false makes the existing parameter_policy false. The existing search hard-check rejects the candidate within the same finite six rounds. A concrete note at the front of the existing feedback notes gives before/after optimizer/trainable/update elements and instructs a coverage-preserving alternative. No new model call, retry, source mutation, forced flag clearing or third request is introduced.

The optimizer catalog total is supporting information, not an independent veto: removing already-frozen parameters that were never updated is legitimate. Counting optimizer instances or raw step calls would falsely reject AdamWInBackward, so the proposal uses the existing grouped logical boundary and union of actual unique parameters. It also permits lossless flattening with unchanged element coverage.

## Policy and unknown boundaries

Precision/BF16 permission and batch/accumulation permission do not authorize narrowing parameter updates. The proposed strict-only rejection applies when allow_model_change=false. It does not use allow_model_change=true as automatic objective authorization; existing explicit permission and MODEL_CHANGE_APPROVED checks continue, and no broader objective-authorization schema is added.

Missing bindings, partial captures, malformed catalogs, unobserved update sets and zero-step original OOM remain unknown. The proposal deliberately leaves existing acceptance behavior for absent coverage unchanged: it does not add a new universal mandatory check, and it never calls unknown coverage verified. Completed original-workload-reference coverage for an OOM baseline is a possible later extension requiring separate review, not included here.

These are cooperative observations, not adversarial attestation. First-observation requires_grad flags are not a full time series. Cross-process p00001 tokens cannot be equated, and equal aggregate elements cannot prove identical parameter sets, optimizer state or values. The existing loss/input/reference gates remain required.

## Evidence and validation

The original R14 s7 total registered elements stayed 1,075,970,304, while its actual optimizer/trainable/update coverage fell to 2,097,408 across all twenty updates. Its existing loss gate already rejected it; the fixture does not add a success. The proposal rejects an equivalent synthetic narrowing even when registered count and recorded scalar losses happen to match.

27 report-only draft cases passed under immutable v5 guard in 0.79s, with no models, GPU, Docker or production database. They include the real R14 projection, incomplete/source/run negative cases, 34-child grouping, already-frozen member removal, flattening, precision permission, and actual bounded feedback transport. Raw receipts, source pins and exact proposed file hashes are in proposal-verification.json. proposal.diff is for review/application after the R15 source freeze is lifted; it has not been applied.
