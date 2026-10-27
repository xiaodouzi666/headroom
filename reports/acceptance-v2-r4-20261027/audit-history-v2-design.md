# Isolated R4 financial-history audit correction (v2)

Status: offline validation passed after R4 finished and parent authorized tests. Seven fixture-test methods including 60 table-driven mutation cases passed; all 123 preserved pure audit self-checks passed. No full live audit, SQLite reads, provider requests, GPU jobs, ledger changes, commits, or changes outside this isolated directory were made for this correction.

The original frozen audit is preserved at reports/acceptance-v2-r4-20261027/audit_mvp_v2.py, SHA256 8dfb2c23f0b5ddf357e577875a21c138498dd4d85f4f4295837ca89d377263b4. Its snapshot-equality gate compares the R4 cap with the older funding-transition snapshot and therefore falsely rejects legitimate accumulated history. This version neither rewrites that funding transition nor retrospectively changes R2/R3 audits or scores.

## Exact evidence chain

1. Original funding/R2 cap: 97 runs, 517 attempts, conservative net 6.600422176 USD; original projection f9d4bf5be24071521339832f3fa9b5902fcfc99105d8618576c9e61d985c2b41.
2. R2 adds exactly its pinned nine unique run identities / 56 attempts. Intermediate projection and all totals match R2 finance and R3 cap: 106 / 573 / 7.895203196 USD, eb877c8f41f0bd01ca15f78b544bf6299bf879b60df3129cf2d1e290621de93a.
3. R3 adds exactly its pinned nine distinct run identities / 59 attempts. Intermediate projection and all totals match the unchanged R3 finance: 115 / 632 / 9.211075556 USD, 81bc441e2f03e04253b8e70b186c992f98036ebfd8644f8b10dcd54a28951b6f.
4. Exact pinned ledger-before / ledger-after snapshots permit only the existing HTTP529 review: one run halt field, three attempt audit metadata fields, and one appended retention-review row. Every prior retention-review row and every other field must remain identical. Actual remains null and the complete 0.0822432 USD reservation remains charged. Receipt and its embedded canonical evidence are checked. The post-review projection is f49e445f91833e9fec512af46925d16bc6b7d25b5e64bc91f65a7e597065821c.
5. Every current pre-R4 run/attempt must exactly equal that post-review snapshot; current complete retention-review table must equal its two saved rows. R4 cap and preflight must bind the full count, projection, known/unknown amounts, charge-status counts, UTC-day subtotal, and original dispatch limits.
6. Final audit rereads the ledger, store, retention table, pinned evidence files and its own audit source for stability. Any missing/malformed/changed/unaccounted evidence rejects the chain.

Historical campaign score fields are never used. Raw historical artifacts are pinned, but only run identity and financial projections/totals are consumed. Remaining original money/source/score/denominator gates remain in place. No admission bound, target, cause truth, six-of-nine threshold, or user-approved budget changes.

## Files

- audit_mvp_v2_history_v2.py: isolated complete versioned audit. Existing equal-snapshot fixture path retained; a later snapshot requires the independently computed history chain. Current R4 main additionally requires the v2 chain gate.
- audit_mvp_v2_history_v2.diff: exact unified diff from original frozen audit.
- test_financial_history_v2.py: stdlib offline fixture tests; imports only isolated audit and stdlib, no runtime/helper imports. Fixed metadata snapshots are read; no credentials, calls table, DB, models or GPU.
- preparation-receipt.json: immutable historical receipt for the initial static-only preparation; its hashes describe that earlier version.
- validation-receipt.json and fixture-test-result.json: final tested source hashes and offline results.

The first fixture run exposed that three original funded diagnostic_probe_<UUID> runs predate campaign UUID naming. The fix explicitly admits only those three exact existing IDs, still verifies all their original rows against the funding snapshot, and rejects any other prefixed ID. It does not exclude old records or create a general prefix exemption.

## Required validation after GPU campaign is idle

Do not promote from AST success alone.

1. Independent review of exact diff, all fixed pins, narrow three-file cache allowlist, every permitted review difference, and unchanged original source. Confirm no raw request bodies/prompts are copied to output.
2. Run offline fixtures:
   .venv/bin/python -B .cache/r4-audit-fix-20261027/test_financial_history_v2.py
   It must accept the original complete chain, preserve inputs, reject missing/duplicate/altered old records, unexpected additions, changed money/actuals/limits, orphan attempts, malformed schemas, wrong intermediate/final projections, wrong review target/status/receipt/fields, extra reviews, missing old review records, omitted full target mapping, cap/preflight drift, and absent source pins. Score-only fixture changes cannot change the pure financial outcome; disk pin checks still reject altered real artifacts.
3. Run all preserved pure audit self-tests:
   .venv/bin/python -B .cache/r4-audit-fix-20261027/audit_mvp_v2_history_v2.py --self-test
4. Confirm the execution receipt has its final exact campaign hash and the campaign is finished, the driver/model processes are stopped, and ledger/store are stable. Verify the versioned audit itself has been reviewed and receipt hashes updated after any repairs. Use a fresh output filename; main intentionally refuses overwrite, and an exception can leave an empty output file.
5. Run full read-only versioned audit once:
   .venv/bin/python -B .cache/r4-audit-fix-20261027/audit_mvp_v2_history_v2.py --execution reports/acceptance-v2-r4-20261027/execution.json --output reports/acceptance-v2-r4-20261027/independent-audit-history-v2.json
6. Separately inspect complete_financial_history_chain_v2, reviewed_zero_sum_gift_partition, original_dispatch_daily_and_case_limits, historical_finance_preserved, ledger_clear, pool_not_exceeded, daily_pool_not_exceeded, ledger_stable, store_stable, retention_review_rows_stable, audit_source_stable, artifact_sources_stable and all finance transition checks. Process exit zero only means audit completed. Report target/cause counts and unknowns from the current nine slots, with financial gates separate. Do not equate a bounded retained charge with provider actual usage, card payment, or successful GPU repair.
7. Run the existing reasoning-wire audit only when its exact-nine/finished preconditions hold. It supplements local prepared-body evidence, not provider ingestion or money reconciliation.

If full execution reveals a mismatch, preserve the failed output and investigate the exact field; do not delete a gate, turn unknown into true, rewrite historical snapshots, or relax pins.
