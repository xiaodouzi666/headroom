# R2 funding driver and independent auditor review

Read-only review found no blocking change to the original execution and acceptance gates. The driver preserves the old PLAN/manifest history, nine slots, source and full-quality bindings, clean/pushed commit, once-only execution, 0.6 USD per case, 480 seconds, six rounds, and both calibration gates. The s2 and checkpoint qualification functions are AST-identical to r1.

The lifetime runtime partition is now 14.17775754 USD. The daily limit remains 9.99964904 USD. This is a zero-sum transfer of the original unused external allocation within the existing 16 USD net work envelope. The 1.82224246 USD external known/retained debt, including 1.049344 USD whose actual amount is unknown, remains charged. The 10 USD judging and 0.89 USD rounding reserves remain separate.

The new profile's available_credit_usd and authorized_total_usd both describe the already-funded lifetime partition. They are not a live account-balance observation, and no displayed account balance is added to funding.

The new r2 auditor independently checks the funding equations and actual hashes of the old allocation/profile, new profile/helper, seven closed entrypoints and six preserved archives. Private reads are confined to those precise files; credentials and arbitrary cache paths remain unavailable. Its output uses the explicit reviewed_zero_sum_gift_partition gate instead of calling the increased runtime partition unchanged.

All **123 synthetic checks passed**, preserving the original **47** and adding **76** funding, closure, history, profile, daily-limit, UTC, type and missing-prerequisite checks. Ruff check and format check passed. An actual read-only audit call with no execution receipt refused before any campaign audit could be accepted.

The funding auditor was independently reviewed by the financial-research agent at its final SHA; no blocking issue was found. That reviewer did not rerun tests or perform a live audit.

A fresh read-only SQLite snapshot still contained **97 closed runs, 517 settled attempts and 6.600422176 USD of conservative charges**, with the exact funding projection unchanged. No new model attempt had occurred since the funding snapshot at this review point.

This cap/snapshot is specific to the r2 start. A future campaign needs a fresh complete history snapshot and cap; it cannot reuse this one after additional dispatches. Full regression, frozen sources and actual live results remain separate acceptance stages.

See funding-driver-auditor-review.json for exact source, receipt and ledger bindings, and funding-auditor-selftest-v1.json for the original test output. The review executed no provider request, GPU job, driver freeze/dispatch, ledger write, production change or old-auditor change.
