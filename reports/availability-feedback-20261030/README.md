# R11 evidence-availability feedback and source-math repair

Actual retained run: `3c5683f9ff4c41febcdefb9a4687402c` (R11). The original diagnosis is retained unchanged. The focused fixture keeps its original diagnosis plus supplied visibility/execution metadata; it excludes the large source markdown and records the original diagnosis/request hashes.

## Reproduced before editing

The original answer declared `chunked_cross_entropy_availability` missing at `source[0]`, although this source reference was visible at lines 1–175. The host reported exactly one `EVIDENCE_AVAILABILITY_CONTRADICTED` at `/evidence_requests/1`. Text visibility does not establish availability of an equivalent helper or answer a semantic question. The saved `before-reproduction.json` records the unchanged host result: invalid, needs_more_info, and not ready. The two real R11 diagnosis requests had already used the allowed initial + validation_repair calls; this work did not add calls.

A separate substantive issue remains in the original model plan: it proposes cross-entropy for source that computes MSE. Merely changing `missing` to `ambiguous` cannot establish mathematical compatibility or remove the unresolved prerequisite. The old CE-specific prompt recipe was disproportionately concrete even though its applicability condition was already stated.

## Changes

- Validation feedback identifies the rejected `/evidence_requests/N/reason` scalar and explicitly distinguishes availability of cited text from existence of a feature or semantic answer. It tells the model that correcting the declaration does not resolve the prerequisite; existing size and credential withholding remain active.
- The existing compact diagnosis preamble requires loss-related candidates to name and preserve the actual original objective and normalization.
- The single temporaries paragraph in `diagnose.md` first requires matching the source producer, consumer, loss and reduction. CE-specific guidance applies only to an existing CE loss. Original precision permission, consumer lifetime, full-vocabulary CE normalization, host-selected numerical reference/tolerance and real-check requirements remain explicit.

No validator, readiness flag, response payload, historical result, call limit, token cap or spending rule was altered. The host does not fix the model answer.

## Offline evidence and limits

`focused-tests-final.log`: **35 passed in 1.19s**, under the existing guarded runner. Tests replay the real rejection and prove feedback includes the exact reason path without mutating the response. A hypothetical model reply changing only the reason remains needs_more_info and unready, with its original plan retained. Repeated invalid responses stop at two requests and retain max_tokens=2000/no-thinking. Existing credential/size withholding and prompt permission/normalization contracts pass. Ruff check, Ruff format check and git diff --check pass.

This is prompt/feedback behavior and unchanged-validator evidence, not proof a live model will choose an equivalent repair. It does not statically prove loss equivalence. No HTTP/provider/GPU call was made; live acceptance remains a separate parent-controlled step. Source hashes are in verification.json.
