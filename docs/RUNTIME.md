# Runtime and spending gates

The application starts without any API key. It saves a partial report with `needs_human` before GPU or research work when a reviewed Nebius profile is missing. Offline tests inject an HTTP MockTransport and never establish live model capability or pricing.

Live work requires all of the following:

1. A regular, private `.env` (mode 0600) on the server containing `NEBIUS_API_KEY`. Never paste keys into chat, logs, UI forms, or Git.
2. T0.4 evidence for actual model IDs, strict response identities, features and prices on the official Token Factory endpoint.
3. Confirmed available credit and an explicit authorized total spending amount.
4. A reviewed `.cache/tokenfactory-runtime.json` matching `headroom.runtime.LiveProfile`.

A profile is an operator-reviewed record, not a self-verifying assertion. Do not set its verified flags merely to bypass preflight. Each model needs a proven input token ceiling for its permitted prompt byte domain, output-token limit semantics that include billed reasoning, and verified current prices. An approximate tiktoken count is not a spending guarantee. Profiles and keys stay ignored. No live profile has been enabled by the development tests.

## Accounting

The SQLite budget ledger reserves each run's cap against the daily and authorized-total budgets. Each actual network attempt, including a retry, reserves a conservative price bound before dispatch. Successful known usage settles that reservation; missing usage, network errors and interrupted attempts retain an unknown charge with its conservative bound. Unknown is never displayed as zero.

The default CLI run cap is 0.6 USD and daily cap is 12 USD. Environment caps `HEADROOM_RUN_BUDGET_USD` and `HEADROOM_DAILY_BUDGET_USD` can only lower a request's caps. The verified authorized-total balance is a separate all-time ceiling, including across day boundaries. Nano annotations share a 0.02 USD per-run sub-budget across retries. A response identity mismatch or violated billing bound halts further billable work.

These local controls govern this application only. They are not a guarantee about Nebius account charges made elsewhere. A card top-up is not an account-level spending cap.

## Billing while promotional approval is pending

Nebius ordinary Token Factory billing is separate from Builders or hackathon promotional approval. If only promotional approval is pending, an ordinarily onboarded account can use paid billing and an API key first. Account verification restrictions still apply. Current billing may allow a negative balance followed by automatic card charges; a 25 USD top-up does not cap total spending at 25 USD.

Official sources checked on 2026-10-24:
- [Current Token Factory billing](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new)
- [Token Factory quickstart](https://docs.tokenfactory.nebius.com/quickstart)
- [Builders terms](https://nebius.com/builders-terms-and-conditions)
- [Hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules)

The user's billing question is not authorization to pay or to use paid models. The current implementation remains disabled until the missing account/usage gates are verified.


## Independent runtime review on 2026-10-24

Direct `build_live_runtime` construction now enforces the same live-enabled,
credit-confirmed and authorized-credit bounds as reading a profile from disk.
Each Ultra/Super/Nano role needs a distinct reviewed model ID; runtime billing
selects the canonical role, preventing an ambiguous ID from bypassing Nano's
0.02 USD sub-budget. These validations happen before reading the private key.

Per-attempt reservations use the greater verified ordinary/cached input price,
plus the requested completion cap. Budget and token-cost arithmetic preserve
supported decimal amounts beyond Python's default 28-digit context. Supported
prices/budget amounts are bounded in coefficient and exponent precision; no
float-based money is accepted. Actual provider token counts outside the reviewed
input/output ceiling halt further work even when the observed dollar amount
happens to fit the reserved total. An unknown cached-input price or mismatched
response model also invalidates the billing bound and halts further calls.

Every retry retains its own reservation and durable pending record. Interrupts,
unknown usage and SDK/transport failures retain unknown actual fees with their
reserved upper bound; the tests do not turn those attempts into zero-cost calls.
Nano retries share the same per-run two-cent ceiling. Optional annotations skip
an unverified prompt/billing domain rather than aborting the repair pipeline.
Annotations accept the actual evidence categories `grads` and `cache`; the
`gradients` alias normalizes to `grads` before agreement scoring. An annotation's
completion or heuristic agreement is not live eight-scenario accuracy acceptance.

The review changed runtime/budget/cost boundaries, repository preparation,
annotation mapping and the API integration. MockTransport and ASGI tests covered
authorization bypass, duplicate model identity, cached-price upper bounds,
provider cap violations, high-precision accounting, cancellation/retries,
nonblocking repository preparation, admission limits and download isolation.
The retained runs passed 83 focused tests plus 135 client/orchestrator/report
contract regressions, with Ruff clean. Details and paths are in API.md. This
review did not use real API credentials, send a model request, top up credit or
activate a reviewed live profile. T0.4 and the original live repair/accuracy/cost
acceptance gates remain pending.
