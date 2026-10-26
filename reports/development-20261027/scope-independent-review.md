# Independent applicability review

Review date: 2026-10-27 (Asia/Shanghai). Offline only; no model, GPU, budget-ledger or historical artifact mutation.

## Confirmed issues and fixes

Small synthetic archive probes reproduced these issues before the fixes:

1. A fully observed candidate with 100% measured slowdown against the 25% limit returned unknown instead of preserving a tested failure. A terminal error with 20 recorded updates also returned unknown. Both are now recorded as tested failures; timing becomes a failure only with finite paired timing, clear GPU observations and matching GPU hardware. Missing timing or GPU observations remain unknown. Host-load limitations remain explicit.
2. Missing allocator observations were indistinguishable from an explicitly observed null. Removing CUBLAS_WORKSPACE_CONFIG from both runs also permitted a pass. Both environment keys must now be present and contain null or text; absence is unknown, malformed values are rejected.
3. A request for max_seconds=999 or device=cpu could pass against archived 120-second CUDA Lab manifests. The requested execution limits and device are now validated against both manifests and included in the query context. Missing controls remain unknown.
4. Scope output had no final byte limit although its loader accepts at most 2 MiB. The builder now checks the exact pretty-serialized CLI output size before returning, so an oversized scope does not leave a newly created unreadable file.

The review also checked exact canonical type matching, failure dominance, unknown observations blocking unanimous success, and source-tree changes beyond declared patch files.

## Validation and handoff

- Original scope tests plus new independent regression file: **64 passed in 2.27 seconds** with the existing offline guard.
- An initial Ruff run reported test import ordering and a loop-variable binding warning. Those test-only issues were fixed; the final Ruff check, format and diff checks pass. The focused test log predates these two test-only cleanup edits; root's final integrated regression owns final-source qualification.
- New tests: tests/test_repair_scope_review.py.
- Updated implementation: headroom/verify/applicability.py.
- Log: scope-review-tests.log.

This adds no new repair campaign, MVP success, general equivalence proof, new dataset, paid call, or deployment. Source and archive trust limitations remain.
