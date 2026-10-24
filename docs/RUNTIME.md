# Runtime and spending gates

The application starts without any API key. It saves a partial report with `needs_human` before GPU or research work when a reviewed Nebius profile is missing. Offline tests inject an HTTP MockTransport and never establish live model capability or pricing.

Live work requires all of the following:

1. A regular, private `.env` (mode 0600) on the server containing `NEBIUS_API_KEY`. Never paste keys into chat, logs, UI forms, or Git.
2. T0.4 evidence for actual model IDs, strict response identities, features and prices on the official Token Factory endpoint.
3. Confirmed available credit and an explicit authorized total spending amount.
4. A reviewed `.cache/tokenfactory-runtime.json` matching `headroom.runtime.LiveProfile`.

A profile is an operator-reviewed record, not a self-verifying assertion. Do not set its verified flags merely to bypass preflight. The default `verified_provider_bound` mode needs a proven input token ceiling for its permitted prompt byte domain. The explicitly selected `local_estimate` mode below uses a local estimate with risk margins instead, and cannot promise a hard spending ceiling. Both require reviewed output-token limit semantics that include billed reasoning and verified current prices. An approximate tiktoken count is not a spending guarantee. Profiles and keys stay ignored. No live profile has been enabled by the development tests.


Each model's `output_cap_field` within `billing` explicitly selects `max_tokens`
(the backwards-compatible default) or `max_completion_tokens`. The existing
`billing.max_completion_tokens` numeric value is the maximum allowed output
count, regardless of which wire field is selected. For example, this fragment
selects the field used by the separate minimal Super/Nano probes; it is not a
complete or enabled live profile:

~~~json
{
  "output_cap_field": "max_completion_tokens",
  "max_completion_tokens": 128
}
~~~

The profile forwards the selected field into `ModelSpec`. Before every attempt,
the guard rejects a different field, two simultaneous top-level cap fields, or
a cap hidden in SDK `extra_body`. It reserves against the selected request count
and saves both the field and count with the pending call. After the response,
the same count bounds all `usage.completion_tokens`, including reasoning; an
overrun invalidates the bound and stops further paid dispatch even if the dollar
cost remains below the reservation. Omitted fields in existing profiles still
select `max_tokens`; the operator must select and substantiate the new field
explicitly for each model.

The [official Chat API reference](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)
defines `max_completion_tokens` as including visible output and reasoning.
Separate Super/Nano probes used this field on 2026-10-24 and returned matching
identities, a stop finish, and usage within 128 tokens:
`runs/model-probes/20261024T102428Z-minimal-3b44464e/report.json`. This supports
their minimal cap-field integration; it does not establish Ultra capabilities,
long-context correctness, full T0.4 acceptance, or permission for application
repair/evaluation. No live runtime profile is created by this code change.

## Accounting

The SQLite budget ledger reserves each run's cap against the daily and authorized-total budgets. Each actual network attempt reserves an explicitly labeled provider bound or local estimate before dispatch. Successful known usage settles that reservation. Missing usage, network errors and interrupted attempts retain unknown actual charges and block every later dispatch through the same ledger, including other open runs and after restart. Unknown is never displayed as zero or as a proven finite maximum debt.

The default CLI run cap is 0.6 USD and daily cap is 12 USD. Environment caps `HEADROOM_RUN_BUDGET_USD` and `HEADROOM_DAILY_BUDGET_USD` can only lower a request's caps. The confirmed authorized total is a separate all-time admission limit, including across day boundaries. An estimated admission can overshoot its reservation and therefore cannot guarantee actual provider charges remain below that limit. Nano annotations share a 0.02 USD per-run sub-budget across retries. A response identity mismatch or violated billing bound halts further billable work.

These local controls govern this application only. They are not a guarantee about Nebius account charges made elsewhere. A card top-up is not an account-level spending cap.

## Billing while promotional approval is pending

Nebius ordinary Token Factory billing is separate from Builders or hackathon promotional approval. If only promotional approval is pending, an ordinarily onboarded account can use paid billing and an API key first. Account verification restrictions still apply. Current billing may allow a negative balance followed by automatic card charges; a 25 USD top-up does not cap total spending at 25 USD.

Official sources checked on 2026-10-24:
- [Current Token Factory billing](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new)
- [Token Factory quickstart](https://docs.tokenfactory.nebius.com/quickstart)
- [Builders terms](https://nebius.com/builders-terms-and-conditions)
- [Hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules)

The user's billing question is not authorization to pay or to use paid models. The current implementation remains disabled until the missing account/usage gates are verified.


## Earlier runtime review on 2026-10-24

The later admission/unknown-charge changes below supersede this review's use of
"upper bound" for every reservation and its retry behavior after unknown billing.

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


## Explicit local estimate admission (offline-verified foundation)

Existing profiles omit `billing.mode` and retain `verified_provider_bound`; the
old strict calculation and selected output-cap field are unchanged. An estimate
must use the distinct `LocalEstimateAdmission` schema. Neither its presence nor
its risk acknowledgement enables live use or grants spending permission. Existing
`live_enabled`, credit confirmation, reviewed prices/output caps and authorized
total checks still apply. This change creates no runtime profile and does not
expand the user's existing $0.10 trial connectivity-only authorization.

This is a **partial configuration fragment**, not an enabled profile. Every value
and its risk margin needs review for the intended request; the sample multiplier
and allowance are not a calibrated provider guarantee:

~~~json
{
  "mode": "local_estimate",
  "tokenizer_assets_dir": "/absolute/local/tokenizer-assets",
  "token_multiplier": "2",
  "additive_tokens": 1024,
  "max_prompt_utf8_bytes": 1000000,
  "max_completion_tokens": 4000,
  "output_cap_field": "max_completion_tokens",
  "output_cap_includes_reasoning": true,
  "output_cap_verified": true,
  "output_cap_evidence": "reference to separately reviewed output-cap evidence",
  "risk_acknowledged": true,
  "evidence": "reference to reviewed estimation policy and its limitations"
}
~~~

Only the Ultra role and exact pinned `nvidia/Nemotron-3-Ultra-550b-a55b` model ID
support this mode. Super/Nano remain strict. The estimator sees the **final**
client SDK payload before each request, including router-added schema text,
messages, tools and template switches. It reuses `PromptAuditor` without changing
that tool's diagnostic-only claims. It never uses evidence-only cl100k counts as
billable input. The request must fit the explicit byte domain and local template
length. Provider-only fields (including `response_format`, reasoning budgets,
reasoning effort and tool choice) and ignored historical tool IDs are refused.
Unknown fields and multimodal inputs are refused by the existing auditor.

Consequently a profile selecting native `json_object` or `json_schema` output
will reject that request in local-estimate mode. The current supported structured
route is the router's **text fallback**, which includes the schema in a system
message. This does not claim native structured output is unsupported by Nebius;
feature evidence remains separate, and the runtime does not silently change the
selected JSON or reasoning method just to pass admission.

The local estimate reservation uses exact Decimal arithmetic:

`estimated_input = ceil(local_template_tokens * token_multiplier) + additive_tokens`

`reservation = (estimated_input * max(input_price, cached_input_price) + output_cap * output_price) / 1000000`

The multiplier must be a decimal string greater than one, and the additive token
allowance must be positive. These are explicit risk margins, not proof of a
provider tokenizer/template match. A saved call includes `admission_kind`, the
reservation, local count, margins, hashes and tokenizer revision. The request hash
and byte count describe the normalized SDK argument domain (including transport
controls such as timeout), not byte-for-byte HTTP serialization; the template
count covers only the rendered input. It does not save
prompt content or the private tokenizer directory. In estimate mode
`provider_cost_upper_usd` and `provider_prompt_token_ceiling` remain null. Actual
cost still comes only from returned usage and reviewed pricing. Usage summaries
add `admission_counts` without including estimates in actual-cost totals. Reports
label local estimates as reservations that may be exceeded.

### Dependencies and already-local assets

No package or asset download runs during admission. `pyproject.toml` already
pins `transformers==4.46.3`; its existing locked dependencies supply
`tokenizers==0.20.3` and `jinja2==3.1.6` in the validated environment. No dependency
change was needed. Optional tokenizer imports occur only when an estimate is
requested, so legacy strict use does not load tokenizer assets.

`tokenizer_assets_dir` must be an absolute, existing local directory containing
`tokenizer.json`, `tokenizer_config.json`, and `chat_template.jinja`. The approved
cache layout is `.cache/tokenizers/nemotron-3-ultra/<TOKENIZER_REVISION>` beneath
the server project, resolved to an absolute path by the operator. The revision
and SHA-256 values are fixed in `headroom/llm/preflight.py`. Files must be regular,
bounded files and match those hashes; missing files, symlinks, FIFOs, modified
assets or unavailable dependencies stop admission before dispatch. The loader
does not use `AutoTokenizer`, model weights, remote code, credentials or network.
The first successful load is reused in memory for that runtime; later file edits
do not alter the already verified tokenizer instance.

### Durable unknown-charge rule and dispatch boundary

All live admission modes now halt on **unknown actual billing**, including a
response with missing/invalid usage, network/SDK failure, interruption, and
ordinary 429/5xx without verified zero-charge evidence. Such errors are not
assumed free. A pending reservation also blocks other requests through the same
ledger. This deliberately limits the older automatic retry policy: a later
attempt cannot be dispatched until the prior charge is known. Legacy unknown
rows are retained and treated as blocking during migration/read-only status;
they are never reset because the day changed or a process restarted.

`reserve`, global pending/unknown checks, and new commitments share SQLite
`BEGIN IMMEDIATE` transactions. Actual settlement, reservation adjustment and
halt on unknown/overrun share one transaction. An estimate overrun records the
full actual amount, even beyond a run limit, then halts all later calls. Output
cap violations still halt in both modes even if the dollar total fits.

Before the SDK is called, the runtime saves a pending call and atomically marks
its attempt for dispatch, checking that the run is still open. A cancellation
is releasable only while the attempt remains explicitly undispatched. Once that
mark commits, interruption before SDK entry is conservatively retained as
pending because dispatch cannot be disproved. No timeout or restart releases it.
If the separate call store fails after a response, the authoritative budget
ledger retains the settled actual fee and blocks further work for accounting
review. Reconciliation requires evidence and a separate reviewed procedure;
this change adds no automatic reset or release of uncertain charges.
