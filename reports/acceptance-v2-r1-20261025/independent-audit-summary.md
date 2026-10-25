# R1 independent acceptance summary — 2026-10-25

The completed r1 campaign attains **3/9 memory targets** (s3, s4, s8) and **5/9 valid correct first causes**, with four first-cause results unknown. It has not demonstrated the original six-of-nine MVP pass line, so this result does not qualify Phase 2. Historical successes and human controls are not included.

The nine installed-CLI invocation chains are verified. Exit codes are three zeroes, two 78s, and four 1s. s1/s5 request additional evidence; s2/s6/s7/nanoGPT end with ResponseValidationError. s2 preserves a completed, numerically accepted candidate with only a 1.55% memory reduction before its later diagnosis fails. nanoGPT has an uncompleted candidate before its later response-validation failure. Missing later patch artifacts remain unknown; they are not silently replaced by an earlier successful round.

All **293** tested, reviewed, and executing source hashes match. The tested-to-committed HEAD transition is recorded as identical sources; execution used `aa42ef502c2eb6e361b1f8e904d4dbfdeb354d8c`. Source/manifest/campaign bindings, all nine cost and 480-second bounds, cleanup, unchanged gift pool, and historical finance preservation were checked. Audit read errors and changed artifacts are empty. This does not make the failed/unknown per-run and original-plan gates pass.

## Actual request and usage evidence

The SHA-checked local prepared-body copies show all **13 Ultra diagnosis requests** explicitly enable thinking with `max_completion_tokens=8192`, and all **5 Super patcher requests** explicitly enable thinking with `max_completion_tokens=4000`. Their recorded reasoning-token totals are **58,350** and **7,264** respectively, with no unknown token counts in these two groups. Four Ultra requests reach their completion cap. Store rows do not persist finish reason, so the audit cannot classify these as length finishes; reaching the cap alone is not such proof.

The complete campaign also contains **9 Nano annotation calls** and **2 separate Super research/tool calls**. The two research/tool calls use `max_completion_tokens=2000`, omit the explicit thinking field, and report 16 and 23 reasoning tokens. They are outside the patcher group's 4000-token contract; the missing thinking field remains unknown. Thus the 18 diagnosis/patcher attempts must not be presented as all 29 model calls. Patch response artifacts separately persist finish reason, but the Store-only reasoning audit does not read them.

Several contracts changed together in this revision. The new outcome cannot be attributed solely to reasoning, and no controlled causal comparison was performed.

## Finance

The 29 attempts contain **$0.79450272** known actual charges plus **$0.00475308** retained unknown charges, for **$0.79925580** conservatively charged. Actual total cost remains unknown. The same cumulative $9.99964904 pool has **$3.399226864 remaining**. Pending and unresolved entries are zero; historical unknown charges and the separate retained external probe debt remain preserved. These are project accounting records, not a provider invoice or card-charge receipt. No recharge occurred in this audit.

## Immutable raw receipts

- `independent-audit.json`: SHA-256 `e40bd44e04bad245e7b593586105ae85103762df3c734b2a346fee32689b27b1`.
- `reasoning-wire-audit.json`: SHA-256 `9c45c781d4bb470bb74816fdd726ac63c9a7e62d15f1b7210eca72b2961fb038`.

Both raw receipts remain private, mode 0600, with exact-path Git exclusions. Publication projection is handled separately without rewriting these bytes. See `annotation-readonly-review.md` for the separate eight-synthetic-case annotation check. This audit performed zero model calls, GPU runs, credential reads, or ledger writes.

Public, reversible views: [acceptance audit](independent-audit-public.json) and [request/usage audit](reasoning-wire-audit-public.json).
