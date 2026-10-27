# Token Factory model probes — T0.4 reviewed and accepted

## Current runtime update — 2026-10-27 R5/R6

The active R5 profile enables the single-sample-verified Super thinking-plus-low-effort combination, with its exact shared-ledger probe receipt and unchanged prices/limits. It adds only three capability evidence fields to the original funding profile; see [R5 evidence](../reports/acceptance-v2-r5-20261027/README.md).

The R6 implementation keeps the initial Ultra diagnosis thinking-enabled. Only a first truncated/length response under the default 16384-token cap may use its one existing supplement with thinking disabled, using the previously reviewed Ultra template control. Other protocols/errors and all schema/policy/financial checks retain their prior behavior. Requested modes and bounded validation failures are public metadata; no hidden reasoning is copied. Full backend regression passes, but complex live recovery efficacy is not yet measured. The historical probe snapshots below retain their original dates and acceptance boundaries.

Status on 2026-10-25 (Asia/Shanghai): all 60 original inference probes have now been executed: 52 capability samples, four Ultra long-input samples and four concurrent Super calls. This includes failures and unverified controls, not 60 successful capabilities. **Full T0.4 accepted=false pending root's installed-configuration/evidence-budget review and final acceptance receipt.** Nano tool generation failed, /no_think did not disable reasoning, Lightning exceeded both requested 128-token reasoning parameters, and the 900k Ultra sample returned HTTP 429 with unknown usage retained at its full upper charge. The disabled candidate profile has only a static review; no configuration is enabled by this document.


## Current method adoption matrix

Each cell uses the original T0.4 ok/fail format. Here, ok means the recorded
small integration fixture or one paired observation supports attempting that
method; it is not a guarantee for complex real application schemas or all
prompts. An unverified token-budget effect is rejected for adoption, while its
raw probe status remains unknown.

| Role | Chat | JSON | Tools | Reasoning toggle | Token budget |
| --- | --- | --- | --- | --- | --- |
| Ultra | ok(method=chat) | ok(method=json_schema) | ok(method=tools) | ok(method=chat_template_kwargs) | fail(error=effect_unverified) |
| Super | ok(method=chat) | ok(method=json_schema) | ok(method=tools) | ok(method=chat_template_kwargs) | fail(error=effect_unverified) |
| Nano | ok(method=chat) | ok(method=json_schema) | fail(error=missing_or_wrong_tool) | ok(method=chat_template_kwargs) | fail(error=effect_unverified) |
| Lightning | ok(method=chat) | ok(method=json_schema) | ok(method=tools) | ok(method=chat_template_kwargs) | fail(error=requested_budget_not_enforced) |

The token-budget verdict covers reasoning_budget=128 and max_thinking_tokens=128.
For Ultra/Super/Nano, effect_unverified is an evidence limitation, not proof that
every possible budget control is unsupported. Lightning's verdict comes from
380/450 reported reasoning tokens exceeding those two requested limits.
The ineffective /no_think prefix is not adopted. Nano's absent reasoning-token
count is not converted to zero. Detailed observations and source hashes remain
in the unchanged capability-review.json and sections below.

## Four-model capability review — 2026-10-25 local / 2026-10-24 UTC

The user authorized remaining original-plan model work within existing gifted
credit, with no recharge or overspend. The four remaining-capability groups
issued 47 single requests with no retries, all with exact response identities,
HTTP 200 and known usage-priced charges. They cost $0.00691720; together with the
five retained checkpoint samples, the 52 capability samples cost $0.00726816.
These amounts are not reconciled invoice totals. Capability failure or unknown
parameter semantics do not mean unknown billing.

| Role | json_object | json_schema | Fenced JSON | Expected tool-call generation |
| --- | --- | --- | --- | --- |
| Ultra | Pass, one fixture | Pass, one fixture | Pass, one fixture | Pass |
| Super | Pass, one fixture | Pass, prior checkpoint | Pass, one fixture | Pass, prior checkpoint |
| Nano | Pass, one fixture | Pass, one fixture | Pass, one fixture | Fail: missing_or_wrong_tool; finish=stop |
| Lightning | Pass, one fixture | Pass, one fixture | Pass, one fixture | Pass |

JSON success means exactly the two-key object with probe=headroom and integer
value=7, not arbitrary Diagnosis/Patch schema reliability. Tool success means
generation of add(a=2,b=3), not execution of an external tool or a Tavily loop.
All four also have one successful nonempty chat sample.

The paired arithmetic prompt was the same within each on/off method. The
template parameter was chat_template_kwargs.enable_thinking=true/false; effort
was reasoning_effort=high/none. Each pair showed a reasoning stream on the first
request and no reasoning stream on the second. The table records reported
reasoning-token counts; Nano did not return that usage breakdown.

| Role | Template on / off | Effort high / none | /no_think observation |
| --- | --- | --- | --- |
| Ultra | 121 / 0 | 91 / 0 | Reasoning remained, 88 tokens |
| Super | 48 / 0 | 48 / 0 | Reasoning remained, 48 tokens |
| Nano | Counts unknown; stream present / absent | Counts unknown; stream present / absent | Reasoning remained; count unknown |
| Lightning | 439 / 0 | 702 / 0 | Reasoning remained, 691 tokens |

These are observable stream differences in one pair per model, not a guarantee
about hidden reasoning, arbitrary future prompts or mathematical answer
correctness. The /think versus /no_think system-prefix pair did **not** disable
reasoning in any of the four tested cases.

| Role | reasoning_budget=128 | max_thinking_tokens=128 |
| --- | --- | --- |
| Ultra | Unverified: 92 reported reasoning tokens | Unverified: 100 reported reasoning tokens |
| Super | Unverified: 48 reported reasoning tokens | Unverified: 48 reported reasoning tokens |
| Nano | Unverified: reasoning count absent; 103 total completion tokens | Unverified: reasoning count absent; 118 total completion tokens |
| Lightning | Failed to enforce requested parameter: 380 reasoning tokens | Failed to enforce requested parameter: 450 reasoning tokens |

A result below 128 on this short task does not exercise or establish a hard
limit. Lightning's counts exceed the requested parameters, but remain inside the
separate max_completion_tokens=1024 output ceiling. No provider completion-bound
violation was reported. Do not use either 128-token parameter as a budget bound.

Disabling the observed reasoning stream did not consistently reduce total
output or cost. Super template on/off returned 92/200 completion tokens and
cost $0.0000936/$0.0001908; effort high/none returned 97/454 and cost
$0.0000981/$0.0004194. These single observations are not a cost or latency
benchmark.

Evidence: reports/live-campaign-20261025/capability-review.json contains every
observation's source path, JSON pointer and source SHA-256, including the four
root-reviewed group receipts and earlier checkpoints. The raw control rows keep
their original unknown classification; the review adds the narrower paired
interpretations without rewriting them. That capability-only review recorded
long-input/concurrency as pending at its observation time; the subsequent results
are recorded below. No production configuration is changed here.

## Completed long-input staircase and Super concurrency — 2026-10-24 UTC

| Requested local approximation | Server prompt tokens | Server completion tokens | Outcome | Known usage-priced / retained USD |
| --- | ---: | ---: | --- | --- |
| 64,000 | 64,031 | 154 | HTTP 200, exact needle, identity matched | $0.064493 known |
| 200,000 | 200,031 | 161 | HTTP 200, exact needle, identity matched | $0.200514 known |
| 500,000 | 500,029 | 161 | HTTP 200, exact needle, identity matched | $0.500512 known |
| 900,000 | Unknown (null) | Unknown (null) | HTTP 429; no response identity or usage | Actual unknown; $1.049344 permanently retained |

The local requested counts are generator approximations, not the server's
tokenizer. The largest successful observed prompt, 500,029 server tokens, is a
tested lower bound. The 900k HTTP 429 is a rate-limit failure and does **not**
establish a context-length ceiling. It was not retried. Reported cached-input
tokens were 56,576 at 200k and 191,488 at 500k; the listed probe costs use ordinary
prompt prices conservatively and are not discounted invoice totals.

After the 900k failure, all subsequent model dispatch stopped. The original
safe_to_continue=false review remains unchanged. An independent review retained
the complete $1.049344 request bound, kept actual_cost_usd=null and prohibited
new POSTs before 2026-10-24T21:17:23.615810Z. Root then refreshed the account and
reviewed continuation for other original-plan calls only. This did not authorize
a 900k retry or release any unknown charge. An unchanged aggregate UI balance
was not treated as evidence of zero cost.

Long-input evidence: reports/live-campaign-20261025/ultra-long-64000/report.json,
ultra-long-200000/report.json, ultra-long-500000/report.json and
ultra-long-900000/report.json under the same campaign directory. The corresponding
claims/*-review.json files contain source hashes. Continuation evidence:
reports/live-campaign-20261025/retained-429-review.json and
reports/live-campaign-20261025/claims/ultra-long-900000-continuation-review.json.

The subsequent four-way Super group completed all four single requests with
HTTP 200, nonempty content, exact model identities and finish=stop:

| Probe | Prompt / completion / reasoning tokens | Content TTFT ms | Request elapsed ms | Known token cost USD |
| --- | --- | ---: | ---: | ---: |
| super-concurrent-0 | 23 / 19 / 14 | 795.762 | 796.834 | 0.000024 |
| super-concurrent-1 | 23 / 36 / 31 | 958.755 | 959.101 | 0.0000393 |
| super-concurrent-2 | 23 / 19 / 14 | 856.383 | 884.664 | 0.000024 |
| super-concurrent-3 | 23 / 19 / 14 | 884.041 | 884.643 | 0.000024 |

The group used 92 prompt / 93 completion tokens and cost $0.0001113, with no
unknown usage or retained reservation. This is one four-request experiment;
per-request elapsed values are not a sustained-throughput or group-wall-time
benchmark. Evidence: reports/live-campaign-20261025/super-concurrency-4/report.json
and reports/live-campaign-20261025/claims/super-concurrency-4-review.json.

Across all 60 original inference probes, known usage-priced amounts total
$0.77289846 and the separate permanently retained unknown charge is $1.049344:
$1.82224246 combined known-or-retained accounting, including the five earlier
calls. Actual invoice cost remains unresolved for the 900k request.
The proposed 150,000 evidence-token budget is below 0.6 × 500,029 = 300,017.4
and the original 150,000 ceiling. The candidate profile remains disabled; its
static review is reports/live-campaign-20261025/runtime-profile-static-review.json.
Root still needs to review the installed configuration and issue the final
T0.4 receipt. Completion of the probe list does not make every capability pass.

## First bounded capability checkpoint — 2026-10-25 local / 2026-10-24 UTC

The owner authorized exactly three single calls, zero retries, a $1.25 token
ceiling and a $2 total envelope using existing gifted credit. All three returned
HTTP200 with the exact requested model identity and known, bounded usage.

| Case | Prompt / completion tokens | Reasoning within completion | Finish / classifier | Token cost USD |
| --- | ---: | ---: | --- | ---: |
| Ultra chat | 23 / 20 | 16 | stop / nonempty_content | 0.000083 |
| Super native JSON schema | 29 / 76 | 61 | stop / exact_json_shape | 0.0000771 |
| Super tool generation | 394 / 40 | 9 | tool_calls / expected_tool_call | 0.0001542 |

Total: **$0.0003143** in usage-priced tokens; **$0.000380303** with a 21%
reference tax calculation. These are not reconciled invoice amounts. The
refreshed UI remained Active with $30.25 including-tax balance and separate
$1 trial credit; its rounded values do not establish the exact charged pool.

Schema classification checks the requested object with probe=headroom and
integer value=7. Tools classification checks the generated add(a=2,b=3)
function call; no external function or Tavily call was executed. Raw response
text and arguments are not saved, so no exact Ultra wording is asserted.
A single success per method does not establish general quality or latency.

Before each POST, the operator manually compared freshly returned catalogue
identity, context, ordinary/cached prices and all zero non-token fees with
pricing-current.json. This matters because the script's catalogue refresh only
enforces model presence; it does not automatically compare prices/context/fees
to that reviewed file. The fixed per-process reservations summed to $1.2093952
and could not reuse the entire allowance independently. Exclusive dispatch
records and sequential reviews preserve the three-call boundary.

All three allowed POSTs are consumed; remaining dollars authorize no extra
request. No long-context, control, concurrency, diagnosis, repair or runtime
profile activation occurred. Full T0.4 is still unaccepted. Detailed reports,
authorization, dispatch and review receipts are in
reports/model-checkpoint-20261025/; the old observations below remain historical.

## First authenticated model observations — 2026-10-24 10:21–10:24 UTC

Both official directories returned HTTP200 (US18 models; default30). Both listed
all four original Nemotron candidates. Super and Nano were then called once each
through the US endpoint, using max_completion_tokens=128, zero retries and exact
response identity checks. Both returned HTTP200, nonempty text and finish_reason=stop.
The model IDs below are exact API identifiers, not normalized UI labels.

| Model | Exact model ID | API context advertised | Input/output per1M USD | Measured chat |
|---|---|---:|---|---|
| Ultra | nvidia/Nemotron-3-Ultra-550b-a55b | 1048576 | 1.00/3.00 | not invoked |
| Super | nvidia/nemotron-3-super-120b-a12b | 262144 | 0.30/0.90 | 23 prompt +19 completion;0.670570s |
| Nano | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 262144 | 0.06/0.24 | 23 prompt +47 completion;1.506663s |
| Lightning | nvidia/Nemotron-3_5-Lightning | 1048576 | 0.06/0.24 | not invoked |

Account Prices UI explicitly uses1M tokens and excludes taxes. Multiplying the
catalogue token prices by1M matched these ordinary input/output prices. Request,
image, video-second and minute surcharges were explicitly zero. Nano cached
input was null in the API catalogue, while Prices UI displayed0.012/1M; this
discrepancy is preserved. All prompt tokens were conservatively charged at the
ordinary price; Super reported cached_tokens=0, Nano did not provide a breakdown.

Usage-priced estimate: Super0.000024USD + Nano0.00001266USD =0.00003666USD.
Including a conservative21% tax reserve gives0.0000443586USD. These are usage
calculations, not a reconciled invoice. The authorized gross ceiling was0.10USD;
a shared token cap0.0826USD left room for the tax reserve. Full advertised context
was used as each input reservation ceiling; no short-prompt tokenizer guess was
used. Successful settlement released unused reservations before the next request.
No uncertainty, identity mismatch or provider ceiling violation was observed.

The API documents max_completion_tokens as including visible and reasoning
output. Super reported14 reasoning tokens within its19 completion tokens; Nano
streamed reasoning but did not provide that breakdown. This tests basic chat,
not a reasoning on/off control or the separate reasoning_budget candidates.

The original historical default probe IDs remain below for reproducibility;
use the explicit exact Nano override shown above when probing. No long-input
limit is inferred from advertised context. At that earlier checkpoint, Ultra could not be reserved under the
then-current0.10USD authorization using its entire advertised context as input bound.

Sources: [Chat API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion),
[Prices](https://tokenfactory.nebius.com/organization/prices),
[Cached tokens](https://docs.tokenfactory.nebius.com/cached-tokens.md).

## Historical candidate models and endpoints

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

Inference probes use the selected official --base-url (default us-central1). Redirects and non-allowlisted endpoints are refused. Catalogue absence prevents dispatch to that model. No other LLM provider is used.

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

Any execution plan containing inference requests still requires all of:
1. --execute;
2. --allow-paid-requests and --credit-confirmed, backed by real operator authorization;
3. positive --budget-usd and --available-credit-usd sufficient to cover that cap;
4. --pricing-file containing verified current prices and provider-enforced token ceilings/cap behavior for every selected model;
5. NEBIUS_API_KEY already present in the caller environment; the tool never reads .env automatically or takes a key as an argument.

These CLI confirmations are preconditions, not a mechanism to grant oneself spending permission. A current active account or trial balance is not evidence that the server key, exact model access, pricing and billable limits are verified. No live command was executed by this implementation change.

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

## Read-only authenticated catalogue and minimal chat planning

With a privately configured server key, an explicitly requested directory-only command is:

~~~sh
uv run --env-file .env python scripts/probe_models.py --suite catalogue --execute
~~~

This pure plan performs exactly two allowlisted `GET /v1/models?verbose=true` calls. It does not read a pricing file, require paid-inference/credit flags, construct an inference budget or send a chat/POST request. No key value is accepted as an argument or included in reports. Without `--execute`, the script still prints a zero-network plan without reading credentials. Mixed/full plans retain every original paid gate.

The report preserves each actual HTTP status and sanitized advertised metadata, including context length, pricing (and its request/cache components), per-request limits and supported sampling parameters. Both directories must return a nonempty valid model list for exit0; any401/5xx, empty/malformed response or transport failure remains failed/nonzero. `accepted` stays false, and `inference_requests=0` does not assert any billing balance or prove that a listed model can perform inference.

The smallest planned three-role chat check is:

~~~sh
.venv/bin/python scripts/probe_models.py --suite capabilities \
  --roles ultra super nano --capability-method chat \
  --model-id nano=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B \
  --max-retries 0 --max-completion-tokens 16
~~~

This is also a dry-run: two catalogue entries plus one chat per selected role, with no request sent. `--capability-method` is repeatable for distinct known methods and only filters capability rows. Default behavior remains thirteen methods and62 total entries. Selecting `--suite all` still includes long-context/concurrency probes even when capabilities are filtered; use the explicit capabilities-only example for a minimal plan. Unrecognized/duplicate methods, or using the option for a suite without capabilities, are rejected before credential lookup.

No claim is made that all three models can be verified within $0.10 or that $1 trial credit completes the original capability/context evaluation. Any future POST requires separately authorized spend and independently verified model prices, a genuine server-billable prompt ceiling, output caps that include reasoning and no unsupported fee components. Do not set verified flags merely to make the probe run. The current token-only price formula does not account for a separate request surcharge; a nonzero/unknown such charge requires review before inference. A catalogue-only check can precede those monetary/capability verifications without inventing them.

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
| 64k | unknown | not run | unknown | unknown | pending full-suite authorization |
| 200k | unknown | not run | unknown | unknown | pending full-suite authorization |
| 500k | unknown | not run | unknown | unknown | pending full-suite authorization |
| 900k | unknown | not run | unknown | unknown | pending full-suite authorization |

The report's accepted flag always remains false, including after every request succeeds. config_proposal.applied remains false. Root must review the evidence and capability semantics, reconcile the real maximum/lower bound, update the application configuration, and review at least five genuine FEEDBACK entries before independently marking T0.4 accepted.

## Remaining live acceptance steps

- The original-plan continuation is authorized within existing gifted credit only; retain the fixed funding allocation, strict provider bounds, unknown-charge stops and current price/cap review.
- Inspect both live verbose catalogues; reconcile exact model IDs, deployment context limits and pricing.
- The four-model capability matrix is recorded and reviewed above. Retain the Nano tool failure, ineffective prefix-off observations and unverified/failed token-budget semantics; do not replace them with HTTP 200 success.
- The full long staircase and one four-way Super experiment are recorded above. Preserve the 900k rate-limit failure, permanent unknown-charge reservation and all per-request measurements.
- Populate at least three actual NVIDIA model prices and honest live capability tables here from the report.
- Genuine observations TF-001 through TF-014 are recorded in docs/FEEDBACK.md; root still reviews their use in final T0.4 acceptance.
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

## Final installed-configuration review

T0.4 accepted on2026-10-25 local; see reports/t0.4-acceptance-20261025.json. This supersedes the pending final-review status recorded above. All prescribed samples were executed, including explicit failures. Installed ULTRA_MAX_INPUT_TOKENS=500029 is a tested lower bound, EVIDENCE_TOKEN_BUDGET=150000, JSON_METHOD=json_schema and REASONING_METHOD=chat_template_kwargs. Real client/diagnosis/repair acceptance is separate.
