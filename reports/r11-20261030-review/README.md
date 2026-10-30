# R11 partial live check — 2026-10-30

R11 stopped automatically at the original F3 full-run admission limit. Two scenarios ran; seven remain not_run/unknown. The fixed denominator stays nine and the threshold stays six: selected targets **0/9**, valid-and-ready first-round diagnoses **1/9**. This is not a completed nine-case regression.

- s1: the real initial + prerequisite_review diagnosis became valid and ready; a generated gradient-accumulation candidate completed 20 updates. Observed CUDA allocation peak fell from 24.750424064 GB to 17.112406528 GB (30.8601%). It was correctly reverted because the pinned numerical pairing recognizer did not support the generated candidate, leaving equivalent-input/batch/objective comparison unavailable. Round 2 still needed evidence after its permitted prerequisite review. No success is claimed.
- s2: both real diagnosis responses fit the compact schema, but validation_repair did not resolve EVIDENCE_AVAILABILITY_CONTRADICTED: the model declared a missing helper against visible source. No patch executed.
- The six Ultra diagnosis completions used 727/633/964/786/916/1010 tokens under the unchanged 2000-token cap, with zero saved response-validation failures. No truncated structured diagnosis was observed. Direct raw finish_reason is not retained for these calls; the router rejects length/content_filter before validation.
- Ten real provider calls were recorded (2 Nano, 6 Ultra, 2 Super), all HTTP 200 and settled. Charged upper-bound total is **$0.19949560**; known actual subtotal is **$0.19422496**. Exact total remains unknown because two Nano calls have bounded billing.
- Both worker cleanups were verified, both finished under their 480-second wall limits. F3 charged $3.459126760 / cap $4, leaving $0.540873240 (less than the required $0.60 full-run admission). FINAL48 has $1.588313628 remaining. No additional pool, transfer, request, retry or GPU job was created by the report auditor.

`summary.json`, `projection-receipt.json` and `staging/` were generated with the previous R10 projector by label substitutions only. The inverse substitution reproduces the original script byte-for-byte. The existing API reader and product projection retain exactly nine rows and correctly count only two attempted runs. Nothing here was published.

Detailed immutable source hashes, request modes, call metadata, cleanup and cost receipts are in `terminal-audit.json`.
