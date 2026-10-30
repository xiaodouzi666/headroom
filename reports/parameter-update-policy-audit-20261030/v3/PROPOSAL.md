# V3 proposal: missing source evidence stays unbound

Reviewable report-only proposal; not applied to headroom or tests. V1 and V2 proposals and raw receipts remain unchanged. The V2 preservation hashes were checked again after validation.

## Correction from V2

Source evidence collection at verify completion must not raise merely because an original/candidate file disappeared or became unreadable. bind_training_coverage_sources now catches OSError, ValueError and TypeError around path/contract inspection. It supplies a binding only when the returned contract is a mapping with an actual lowercase64hex source digest. Missing/invalid digests leave that role unbound; training coverage becomes unknown and no equivalence or coverage proof is invented.

The V2 semantic guard is unchanged: only actual updated-parameter element reduction across corresponding complete twenty logical boundaries supplies a strict violation of the existing parameter_policy. Catalog counts and first requires-grad flags remain informational. Removing eligible-but-never-updated optimizer members remains valid; 34-child optimizer-in-backward remains grouped by logical update.

REQUIRED_CHECKS, numerical policy, memory thresholds, update requirements, fixed-nine denominator, 6/9 gate, calls, retries and budget remain unchanged.

## Focused draft validation

175 cases passed under immutable v5 guard in20.26s:42 draft coverage tests (28 existingV2 plus14 new binding negatives), plus existing compare, verify runner, parameter, bounded-feedback and offload-reference focused tests. A report-only plugin loads the proposed helper/compare/runner in the pytest process; the production files are never replaced.

The initial all-focused run had175 pass and one immutable-guard denial. The old historical fixture test attempted an unredirected actual runs/lab-acceptance path. Its source and guard were left unchanged; the raw failure receipt is retained under initial-with-legacy-guard-block-*. That one test was explicitly deselected for the final eligible-focused run and is not claimed passed.

New negatives cover actual missing/chmod000 files, contract OSError/PermissionError/ValueError/TypeError, absent/invalid/nonhex/wronglength/nonstring digests, and nonmapping contract results. All remain unbound/unknown. The actual R14 update subset still rejects; unused requires-grad members, already-frozen redundant members, flattening and valid optimizer-in-backward remain non-rejections.

No model, GPU, Docker, public deployment or production-ledger action was performed. proposal.diff passed git apply --check only, not application. Exact hashes and scope are in proposal-verification.json; v2-to-v3-helper.diff isolates this safety correction.
