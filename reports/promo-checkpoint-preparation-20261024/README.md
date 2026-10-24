# Promo checkpoint preparation — 2026-10-24

Preparation is ready. Live execution is refused until the human grants this new checkpoint spending authorization. The previous 0.10 USD trial-connectivity authorization is unchanged. Promo arrival is not new spending permission.

## Artifacts

- pricing-reviewed.json: only exact Ultra and Super identifiers, fresh US catalogue prices and conservative whole-context input ceilings; max_completion_tokens includes visible and reasoning output under the official API contract.
- ultra-chat.plan.json, super-schema.plan.json, super-tools.plan.json: actual scripts/probe_models.py CLI dry-run outputs.
- matching request-audit.json files: actual production make_payload result, explicit zero retries and fixed per-call sub-budgets.
- official-review.json: source locations, catalogue hash, child-versus-root source review attribution, and unsupported claims.
- receipt.json: preparation result, hashes, independent network/credential guard results, and explicit execution refusal.

## Fixed allocations and limits

| Case | Output cap | Token reservation USD |
| --- | ---: | ---: |
| Ultra chat | 1024 | 1.051648 |
| Super native json_schema | 256 | 0.0788736 |
| Super tools format | 256 | 0.0788736 |
| Total | | 1.2093952 |

Proposed token allowance: 1.25 USD; proposed gross envelope: 2 USD, neither currently authorized. At the 21% Netherlands rate reported by root from official billing documentation, the 1.25 USD token allowance plus tax is 1.5125 USD; actual account treatment and transaction reconciliation remain separate. This is not an invoice or proof of a provider account-level spending cap.

The pricing file marks reviewed documentary pricing/bounds, not successful Ultra/schema/tools capabilities. Cached input is below ordinary input; probe calculation conservatively prices all prompt tokens at ordinary input price. New catalogue request/image/video/minute fee fields are zero. A nonzero or unknown new fee requires review before sending.

Each planned execution performs two official catalogue GETs and at most one inference POST. Tool probe requests only the add function signature; it does not call Tavily or run a tool loop. No long-input/concurrency/alternative-method request is included. Do not use suite all or batch these commands.

After authorization, use one request-audit.json cli_argv at a time, add explicit execute/allow-paid-requests/credit-confirmed and freshly confirmed available-credit-usd, and a unique new output directory. Credentials must be loaded only in that authorized invocation, never copied into these files. Review each resulting receipt before considering the next. Unknown usage or identity, invalid/truncated response, provider-bound violation, failed capability, credit/account/rate-limit error stops the checkpoint. Do not repeat a failed request or silently enlarge a sub-budget.

The probe ledger is per process, not the runtime SQLite ledger. These disjoint fixed allocations prevent each process taking the full 1.25 USD, but prior unknown charges still block later dispatch. No runtime profile was created. All existing runs and the original PLAN remain unchanged.

The actual preparation ran the original parser/main/validate_prices/make_payload under independent DNS/INET, real-project .env and credential-environment guards. All three dry-runs passed with zero guard attempts. No authenticated GET, inference request, Tavily call, GPU work or credential read occurred during this preparation. The input catalogue was the separately authorized root GET receipt.
