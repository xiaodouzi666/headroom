# Public-document update after the 29 October repair evaluation

This update changes README, DEVPOST, FEEDBACK and the summary above `Full campaign history` in RESULTS. It does not modify source code, scripts, frontend assets, recorded experiments, the original number manifest or the original historical suffix.

## Current measurements

The latest fixed-nine evaluation reached **1/9 memory targets**, with **5/9 valid correct first-cause diagnoses** and **7/9 raw category matches**. The raw category count includes two invalid diagnoses. These repair-campaign counts use the first saved diagnosis round, which can follow correction requests; the separate diagnosis-only comparison uses a stricter one-request design.

There are now eight recorded fixed-nine evaluations. Their historical union remains five distinct successful scenarios and the best single evaluation remains 3/9. This is below the unchanged 6/9 requirement.

The historical-selection rule is unchanged: lowest successful candidate peak, latest evaluation on a tie. The selected s4 source therefore changes from the 27 October run to `e8213706570e478f9845e49e24c2b54b` at source `6c7cde2`; its exact peaks are unchanged. The numerical comparison still covers five reference losses, while the candidate completed 20 optimizer updates.

Both additional s2 precision settings and the HF Trainer repair failed their requirements. The HF edit passed a static configuration check, which is distinct from hardware verification. No successful precision trade-off or new successful gallery card is reported.

The two CLI saved-snapshot checks each made one model request but produced no usable diagnosis or patch. Their public result fields are bound in the supplement without including uploaded source or raw prompts. Snapshot validation is still incomplete; the Web slot and Watch are outside this update.

## Costs and timing

The fixed-nine cost table contains only known partial actual-cost subtotals. Its eight rows sum to **USD 8.34721172**. The three additional precision/Trainer tests add a known partial subtotal of **USD 0.31689318** outside that table. Full actual totals remain unknown, and neither figure is the full project cost.

For the latest fixed nine, the known partial actual subtotal is **USD 0.65966386**. The separately recorded conservative amount **USD 0.68780824** is not relabelled as actual cost. For all twelve latest tests, the corresponding figures are **USD 0.97655704** known partial actual and **USD 1.01159284** conservative. The public cost table does not substitute the latter values for actual costs.

The newest nine-scenario wall-time sum is 852.41443751496263 seconds, displayed as **852.41**. Other existing displayed numerical values are unchanged. Recorded wall time includes orchestration and model calls, not just GPU compute.

## Versioned evidence and preservation

- [numbers-r7-v1.json](numbers-r7-v1.json) is an append-only supplement containing source-file hashes, JSON pointers, direct values and derived calculations.
- [numbers.json](numbers.json) remains the original seven-evaluation manifest, with SHA `c969deaee6ed37e52913fbf31e349bc4e519c6d7fa5fc25e16e30244dd79207e`.
- [results-before-r7-v1.md](results-before-r7-v1.md) preserves the preceding summary verbatim.
- The former latest-evaluation table remains under “Previous evaluation — 2026-10-27”.
- Everything from the original `## Full campaign history` marker onward is byte-identical, SHA `28a8267e6d6eda7b22012f9bba1cd3575f966530cf088c8558336cdd17c4b407`.
- [document-check-r7-v1.json](document-check-r7-v1.json) records the actual current document hashes, focused number checks, link checks and terminology checks.

## Minimal numeric-checker follow-up

The existing `scripts/verify_public_numbers.py` is deliberately unchanged while live work uses frozen source pins. Its default manifest still describes the earlier latest evaluation, so its old passing receipt does not validate the refreshed documents.

The smallest follow-up is to add an explicit versioned supplement argument, verify its base-manifest SHA and every direct source hash/pointer, then overlay only the latest summary and changed historical selection. Keep old manifests and receipts readable. Derive the eight-evaluation count, historical union and best single score from their bound rows; do not accept a free-form numeric allowlist.

Extend summary parsing to distinguish “raw first-category matches” from “valid correct first-cause diagnoses”, bind both to separate fields, and retain the nine-case denominator. Check that the tied s4 selection names the latest successful run without changing its five-loss comparison into a 20-loss claim.

The existing README/DEVPOST memory, token and diagnosis-comparison scopes can be reused. Add bounded checks for the RESULTS summary tables and known-partial cost totals, while excluding the preserved historical suffix from rewriting. FEEDBACK's dated observations require their own explicit source scopes; they must not be validated merely because the same number appears elsewhere.

Meaningful future negative checks should modify actual document bytes, a supplement source/hash, a scope and the raw-versus-valid count, proving that each mismatch fails. Do not change scripts or regenerate earlier receipts until the source freeze is lifted.

No video URL was invented; `{{VIDEO_URL}}` remains. No commit, push, model request, GPU run, pool change or publication action was performed for this documentation update.
