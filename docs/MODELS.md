# Token Factory model probes — T0.4 prepared, live acceptance pending

Status on 2026-10-24: **OFFLINE TOOLING ONLY; accepted=false.** No authenticated catalogue, model call, price, context-limit measurement, credit balance or model capability has been verified by this work. No .env value was read. Do not interpret offline fixtures as NVIDIA/Nebius results.

## Candidate models and endpoints

The following identifiers and historical prices come from PLAN.md C.1 and are only probe candidates. Runtime catalogue IDs and account pricing must be checked before accepting them.

| Role | Candidate model ID | Plan price, input/output per 1M | Live status |
|---|---|---|---|
| Ultra | nvidia/Nemotron-3-Ultra-550b-a55b | $1.00 / $3.00 — unverified | not measured |
| Super | nvidia/nemotron-3-super-120b-a12b | $0.30 / $0.90 — unverified | not measured |
| Nano | nvidia/nvidia-nemotron-3-nano-30b-a3b | unknown | not measured |
| Lightning fallback | nvidia/Nemotron-3_5-Lightning | unknown | not measured |

Both catalogue endpoints are included in every execution plan:
- https://api.tokenfactory.us-central1.nebius.com/v1/models?verbose=true
- https://api.tokenfactory.nebius.com/v1/models?verbose=true

Paid probes use the selected official --base-url (default us-central1). Redirects and non-allowlisted endpoints are refused. Catalogue absence prevents dispatch to that model. No other LLM provider is used.

## Explicit model identifiers

The default IDs remain historical plan candidates for backwards compatibility. An operator can explicitly select a case-sensitive candidate without editing source:

~~~sh
.venv/bin/python scripts/probe_models.py --suite capabilities --roles nano \
  --model-id nano=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
~~~

This example is a dry-run only. The current public UI spelling above does not prove this account can invoke the model. Repeat `--model-id ROLE=EXACT_ID` for distinct roles; unknown roles, duplicate assignments, malformed IDs and non-NVIDIA identifiers are refused before credentials or pricing are read. Other roles and the original default62-item plan remain unchanged.

Actual dispatch still requires the exact ID in the authenticated catalogue for the selected `--base-url`, verified prices keyed by that same ID, all original execution/credit/budget gates and matching response identity. There is no case folding, alias substitution, fallback to the old ID's prices or automatic endpoint change. Reports include the selected role/ID mapping and refused model/endpoint. A selected model is not an accepted model capability.

Each probe invocation still uses one selected endpoint for its paid rows, and the application runtime still has a single global base URL. Different processing-region labels in the public UI do not establish different API URLs. Account-specific catalogue/access and any need for model-specific regional routing remain to be measured after key setup; no regional behavior was changed here.

## Offline plan and bounded execution

From /home/xiaodouzi/workspace/headroom:

~~~sh
.venv/bin/python scripts/probe_models.py
.venv/bin/python scripts/probe_models.py --suite capabilities --roles super
.venv/bin/python scripts/probe_models.py --suite long --long-input-tokens 64000
.venv/bin/python -m pytest tests/test_model_probe.py -q
~~~

Default execution prints a JSON plan only: zero network requests, no API-key lookup, no pricing-file read, no tokenizer construction and no report-file write. --help is also offline. The full plan has 62 requests: two catalogues, 4 models × 13 capability candidates, four Ultra long-input requests and four simultaneous Super requests.

The capability candidates for every model are:
- chat;
- JSON object, strict JSON schema and fenced JSON with tolerant parsing;
- a forced add(a=2,b=3) function call whose name and parsed arguments must match;
- reasoning on/off via chat_template_kwargs.enable_thinking;
- system first-line /think versus /no_think;
- reasoning_effort=high versus none;
- reasoning_budget=128 and max_thinking_tokens=128.

A successful HTTP response alone does not establish reasoning toggle or token-budget enforcement. Those rows remain unknown with observed reasoning/usage details until reviewed; malformed JSON, wrong tools, truncation and refusal are not successes. Fenced JSON maps to the application JSON_METHOD=text only after review; template/prefix/effort candidates correspond to chat_template_kwargs/system_prefix/reasoning_effort. The probe never mutates headroom/config.py.

Actual network execution requires all of:
1. --execute;
2. --allow-paid-requests and --credit-confirmed, backed by real operator authorization;
3. positive --budget-usd and --available-credit-usd sufficient to cover that cap;
4. --pricing-file containing verified current prices and provider-enforced token ceilings/cap behavior for every selected model;
5. NEBIUS_API_KEY already present in the caller environment; the tool never reads .env automatically or takes a key as an argument.

These CLI confirmations are preconditions, not a mechanism to grant oneself spending permission. Current account/key/credit prerequisites remain unmet. No live command has been executed.

Example pricing document structure (deliberately invalid until independently completed and verified):

~~~json
{
  "verified": false,
  "verified_at": null,
  "source": null,
  "output_caps_include_reasoning": false,
  "models": {
    "nvidia/nemotron-3-super-120b-a12b": {
      "input_usd_per_million": null,
      "output_usd_per_million": null,
      "prompt_token_ceiling": null,
      "output_cap_field": "max_tokens"
    }
  }
}
~~~

prompt_token_ceiling must be a verified maximum server-billable prompt-token count per request, not a cl100k guess. output_cap_field is max_tokens or max_completion_tokens, and the operator must verify that the cap includes billed reasoning tokens. Unknown prices or cap behavior fail closed. A pricing source/timestamp is required. No advertised catalogue price is automatically trusted or applied.

After account access, balance, current pricing, cap semantics and a concrete spending authorization are confirmed, the operator can supply those reviewed values:

~~~sh
.venv/bin/python scripts/probe_models.py \
  --execute --allow-paid-requests --credit-confirmed \
  --available-credit-usd "$CONFIRMED_CREDIT_USD" \
  --budget-usd "$APPROVED_CAP_USD" \
  --pricing-file docs/model-probe-prices.reviewed.json \
  --suite capabilities --roles super \
  --max-completion-tokens 256 --max-retries 0
~~~

This example does not authorize execution. Continue with separate long/concurrency suites only within the remaining authorized balance. Selected --suite options can be repeated. --roles applies to capability rows; long always uses Ultra, concurrency always uses four Super calls. --long-input-tokens selects planned 64000/200000/500000/900000 stages. A new --output-dir must not already exist. Default reports go to a unique runs/model-probes/<UTC>-<suffix>/report.json directory on the server.

## Budget and failure accounting

Before each logical request, the tool reserves:

(maximum billable prompt tokens × input price + maximum completion tokens × output price) / 1,000,000 × (1 + maximum retries).

All four concurrent requests are reserved together before any of them is dispatched. Reservation is protected by a lock. A successful call releases only unused reservation after valid actual usage is recorded. Missing/invalid usage, transport uncertainty and unsuccessful HTTP attempts conservatively retain that attempt's full upper bound. An unexpected transport failure retains the same charge and logs only its exception type.

Each request has an absolute wall-clock deadline (600 seconds for Ultra, 120 seconds for other models and catalogue calls), including continuously arriving SSE heartbeats. Retries are limited to 429/5xx, 0 by default and at most five, with delays 1/2/4/8/16 seconds. Each potential attempt is prepaid in the reservation. Unknown charges can exhaust the cap even when the provider may ultimately bill less. There is no automatic refund assumption for failed requests. Provider usage exceeding a verified ceiling marks a violation and blocks subsequent reservations. This guard depends on truthful, verified service-side price/cap information; it cannot impose a billing contract on the provider.

Actual request usage, known usage-based cost, conservative retained cost, status/refusal/error class, TTFT and elapsed time are recorded. Raw prompts, raw completions, authorization headers, error bodies, needles and API keys are not persisted. TTFT measures first text, reasoning or tool delta; ttft_content_ms separately measures first user-visible text. Both remain null when no such delta arrives. SDK automatic retries are avoided by using a small explicit HTTP streaming client.

The ledger is for one invocation. There is no claim of a cross-process/daily account balance; the root application's separate budget control handles broader use. Do not run competing probes against the same authorized balance without accounting for both.

## Long-input interpretation

The Ultra staircase generates an approximately 64k/200k/500k/900k-token filler using cl100k_base and adds a unique final needle. The actual cl100k token count, UTF-8 byte count and SHA-256 are recorded; the prompt and needle are never written. tiktoken is loaded only after explicit live gating for a long probe. If its tokenizer cache is absent, tokenizer initialization can need network/cache access on azuki; dry-run and offline tests never initialize it.

Server usage.prompt_tokens is recorded separately from the cl100k approximation. Successful exact needle reproduction proves that particular request succeeded; it does not prove broad long-context reasoning quality, the model's exact tokenizer count in advance, or the absolute maximum supported input. The largest successful staircase input is a verified lower bound. The report does not manufacture ULTRA_MAX_INPUT_TOKENS or silently change the evidence budget.

Current measurements:

| Target cl100k input | Server prompt tokens | Needle | TTFT/elapsed | Cost | Result |
|---|---|---|---|---|---|
| 64k | unknown | not run | unknown | unknown | pending account/authorization |
| 200k | unknown | not run | unknown | unknown | pending account/authorization |
| 500k | unknown | not run | unknown | unknown | pending account/authorization |
| 900k | unknown | not run | unknown | unknown | pending account/authorization |

The report's accepted flag always remains false, including after every request succeeds. config_proposal.applied remains false. Root must review the evidence and capability semantics, reconcile the real maximum/lower bound, update the application configuration, and review at least five genuine FEEDBACK entries before independently marking T0.4 accepted.

## Remaining live acceptance steps

- Obtain approved account/key/credit prerequisites and current verified pricing/cap documentation.
- Inspect both live verbose catalogues; reconcile exact model IDs, deployment context limits and pricing.
- Execute the capability matrix with bounded requests and inspect real JSON/tools behavior; reason about unknown reasoning/budget observations rather than turning HTTP200 into capability proof.
- Run the full long staircase and four-way Super experiment; retain failures, 429s, latency and every charge.
- Populate at least three actual NVIDIA model prices and honest live capability tables here from the report.
- Add at least five actual Token Factory/model feedback observations.
- Root independently reviews results and updates model IDs, JSON/reasoning method and EVIDENCE_TOKEN_BUDGET=min(150k, 0.6×verified limit), accounting for the lower-bound distinction and plan changes if required.

Official references, checked during plan review:
- https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md
- https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/README.md
- https://github.com/nebius/token-factory-cookbook/tree/main/models/nemotron

The Ultra model page and catalogue previously disagreed on 1M versus 256K; neither is substituted for authenticated endpoint measurements.


## Test-isolation correction

During the AsyncClient deadline refactor on 2026-10-24, three transport tests retained an outdated Client monkeypatch and unintentionally attempted two chat requests and one catalogue request using only the fixed string offline-placeholder. No .env or real credential was accessed, no --execute command was run, and no successful authenticated model/capability/usage evidence was obtained. The observations were not saved, so their exact network outcome is unknown; they are not accepted live probes. This was reported to the root agent immediately.

The mock target was corrected and a file-wide autouse fixture now rejects real DNS resolution and socket connect/connect_ex/create_connection before any network operation. Final test results below refer only to reruns with that independent network guard in place.

### Preserved failed-round evidence

The observed terminal output of the unguarded refactor round was:

~~~text
................................FFF......... [100%]
FAILED tests/test_model_probe.py::test_http_transport_stream_usage_ttft_and_endpoint_without_network
FAILED tests/test_model_probe.py::test_http_transport_never_follows_redirect_or_reports_error_body
FAILED tests/test_model_probe.py::test_catalogue_verbose_query_and_actual_ids_without_network
3 failed, 41 passed in 2.21s
~~~

Each failure was an AssertionError because the mock request list remained empty. The source at that moment patched httpx.Client while the production wrapper had switched to httpx.AsyncClient. It called the actual transport with the constant offline-placeholder bearer string. The intended endpoints were:
1. POST https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions
2. POST https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions
3. GET https://api.tokenfactory.us-central1.nebius.com/v1/models?verbose=true

A conservative verified time window is 2026-10-23T22:19:21.036567800Z–2026-10-23T22:21:57Z (Beijing 2026-10-24 06:19:21–06:21:57). The lower bound is this document's filesystem birth time before that round; the upper bound is the server UTC clock captured after the corrected guarded rerun. Exact request timestamps were not recorded.

The HTTP response codes, transport exception classes, timeout outcomes and response bodies of those three attempts were not retained; they are explicitly unknown. The observed test-level failure class is AssertionError. The evidence does not establish whether packets reached the service. No real key or .env value was read and no authenticated account quota or model capability was verified. Do not summarize the entire development round as zero network.

### Guarded final verification

After correcting AsyncClient mocks and adding a test-module autouse DNS/socket-denial fixture, the observed rerun was:

~~~text
All checks passed!
1 file reformatted, 1 file left unchanged
............................................ [100%]
44 passed in 0.12s
~~~

Commands: .venv/bin/ruff check scripts/probe_models.py tests/test_model_probe.py --fix; .venv/bin/ruff format scripts/probe_models.py tests/test_model_probe.py; .venv/bin/python -m pytest tests/test_model_probe.py -q.

Tests include exact native JSON versus fenced fallback, numeric schema types, tool arguments, pre-dispatch retry reservation, missing-usage retained charges, peer ceiling-violation retry stopping, actual four-worker fake concurrency, HTTP redirect rejection, verbose catalogue query, usage/TTFT parsing and a continuous-heartbeat absolute-deadline regression. The separate review agent is asked to re-run with an additional process-level network guard. T0.4 remains unaccepted.


## Response-model identity guard (latest revision, 2026-10-24)

Every JSON SSE event must carry the same explicit model identity, exactly matching the requested catalogue model ID. The transport records response_model, distinct response_model_ids and response_model_missing_events. No aliases are configured or implicitly accepted. SSE comments/heartbeats and the [DONE] sentinel are not identity-bearing JSON events.

Missing, conflicting or mismatched identity makes a successful HTTP response's capability result unknown. It cannot count as a successful long-input staircase run. Reported usage is retained as an observation, but requested-model pricing is not applied: actual_cost_usd is null, actual_known_usd is unchanged, and the dispatched attempt's original reservation remains occupied. Unsent retry reservations can be released because those attempts did not occur.

The ledger explicitly sets billing_bound_unresolved=true and halt_reason=response_model_identity_unverified. The retained requested-model reservation is no longer represented as a verified upper bound for whichever model actually served the response. All subsequent paid dispatch decisions, including peer retries, are refused; already-dispatched requests may finish. No successful capability or billing attribution is inferred from HTTP200, correct-looking JSON, a correct needle or numeric usage alone.

Non-successful HTTP 429/5xx responses without model output or usage retain the prior unknown-charge bounded-retry treatment. Any response carrying usage still requires verified identity before pricing; an identity anomaly halts further spending. Provider token-ceiling overruns remain a distinct provider_bound_violation.

The latest guarded test round after this fix was:

~~~text
All checks passed!
2 files reformatted
....................................................... [100%]
55 passed in 0.15s
~~~

New regressions cover missing/mismatched/conflicting/partially missing SSE identity, consistent matching identity, no cost attribution or reservation release on identity failure, refusal of later paid probes, and exclusion of a correct needle produced by the wrong model from context-limit evidence. The existing independent DNS/socket guard covers every test. The earlier dummy-token incident record above is intentionally retained and is not replaced by this later guarded result. T0.4 accepted remains false.
