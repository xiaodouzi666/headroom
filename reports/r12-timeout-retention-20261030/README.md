# R12 single-timeout full-reservation retention proposal

R12 ended after one Nano annotation timeout. The target ledger retains the original 0.01644864 USD provider-bound reservation and unknown actual charge. The independent R12 store contains exactly one call, mapping to the same budget attempt. No Ultra call is present. Original campaign and report remain unchanged.

## Prepared, not applied

`proposal.json` is the read-only prepared timeout-specific receipt. Its exact SHA256 is recorded in `proposal-preparation.json`. This preparation made no provider/GPU call and verified every source file hash remained unchanged. The new default CLI also only prepares; applying requires the exact independently reviewed receipt hash and a named reviewer. Root owns the decision and execution. No real ledger migration or dispatch was performed here.

The full reservation is reproducible from the pre-dispatch verified bound: 262144 maximum input tokens at 0.06 USD/M plus 3000 capped completion tokens at 0.24 USD/M, including reasoning, with reviewed zero ancillary fees. The prepared wire payload has one non-streaming plain-text completion and reconstructs both captured wire and stored-payload hashes. Delivery is unconfirmed; this is not proof of an unsent or zero-cost request.

## Narrow manual exception

The new `billing_timeout_review` reuses the existing HTTP529 strict preparation/execute pattern, but requires exactly one run attempt and one corresponding persisted call, first-attempt outcome timeout, no HTTP status, no usage/response model/tokens/exact cost, and a closed provider_charge_unknown run. Every attempt must be settled, dispatched, verified_provider_bound, charge_status unknown, and retain its complete original upper charge. Model identity, request capture, output cap, prompt ceiling, tariff and zero ancillary fees must all agree. It cannot borrow the cached-usage or HTTP529 reasons.

BudgetLedger.review_retained accepts the explicit timeout reason only after regenerating the full proposal under its write lock and comparing it to the reviewed receipt. The ordinary pending/unknown dispatch gate is unchanged. Applying would only mark this existing full reservation reviewed_retained and record a receipt; actual_usd remains null, upper_usd/charged_usd remain unchanged, and historical calls/reports/campaign are not rewritten. Other unresolved runs stay blocked. There is no release, new cap, retry or recharge.

## Offline verification

123 tests passed in 5.98s under the guarded runner, including the new timeout cases and existing HTTP529, external-commitment and budget cases. Coverage includes exact successful retention, no automatic timeout retry, continued default blocking before review, singleton mapping, changed/absent/redacted request capture, mismatched caps/model/tariffs/fees, malformed run/attempt state, changed inputs after review, transaction-time call recheck, duplicate review, rollback and unrelated halted runs. Ruff check, Ruff format check and git diff --check pass. Initial logs retain fixture errors (timeout raises LLMError directly, unlike the HTTP529 retry path; the singleton mutation had no sibling row); they were fixed without weakening validation.

Important accounting boundary: original campaign.accounting is its stale startup snapshot (zero/resolved). The saved row and target ledger show retained 0.01644864 with unknown actual. Future accounting must read that ledger and exact store mapping; the raw R12 document must stay unchanged.
