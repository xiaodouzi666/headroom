# Runtime and spending gates

## Fresh-checkout configuration

After the README dependency and lab-image steps, copy .env.example to a private
.env with mode 0600 and add your own provider keys. The example keeps browser run
submissions, saved-snapshot uploads and the historical gallery disabled; these
UI settings do not grant model spending permission.

Provider credentials are read from the private .env. The runtime-profile path,
budget caps and public-interface switches are read from the process environment;
copying .env.example does not export them. Supply reviewed settings through the
launcher or the documented user-service environment configuration. The dedicated
public launcher still enforces its disabled submission switches.

The API can select a reviewed private profile with HEADROOM_RUNTIME_PROFILE.
CLI repair and watch commands accept --runtime-profile explicitly. The profile
must describe verified model capabilities, billing and an authorized total;
do not enable it by copying a sample fragment or assuming a key implies credit.
HEADROOM_RUN_BUDGET_USD and HEADROOM_DAILY_BUDGET_USD are optional API/service
downward caps, not new funding. CLI repair/watch/evaluation use their explicit
--budget and --daily-budget options. HEADROOM_BUDGET_DB_PATH selects the accounting database; changing
its path must never silently erase the accounting of an existing allocation.

For a public deployment, use the reviewed launcher and instructions in
[FUNNEL.md](FUNNEL.md). Set the bare public hostname only there, and enable trust
for forwarded headers only with the corresponding loopback proxy configuration.
Leaving both forwarding-trust flags false is the normal local setting.

Rebuild the Lab image whenever uv.lock changes. The runner compares the image's
dependency-lock label against the checkout and refuses an older image. Use
bash scripts/build_lab_image.sh; never bypass this identity check just because
an older image with the same tag exists.


### Build your own disabled profile

The complete [disabled strict-mode template](examples/runtime-profile.disabled.json)
uses the actual `LiveProfile` / `ProfileModel` / `BillingBound` structure in
[headroom/runtime.py](../headroom/runtime.py). Start with this mode; it needs no
local tokenizer and does not require the project's private acceptance receipts,
allocation registry, historical runs or budget database.

Copy it into **your own checkout**, without replacing an existing profile:

```bash
mkdir -p .cache
(umask 077; set -C; cat docs/examples/runtime-profile.disabled.json > .cache/tokenfactory-runtime.json)
```

Keep `live_enabled=false` and `credit_confirmed=false` while filling it in.
`REVIEW_*` strings are deliberately invalid monetary/date placeholders, not
prices or credit. The three numeric billing fields set to `1` are schema-only
placeholders, **not proven bounds**; replace them before marking billing verified.
The model IDs are the public candidates in `headroom/config.py`, not proof of
availability in your account. No credentials belong in this JSON.

| Fields | What to supply and verify |
| --- | --- |
| `base_url` | One of `OFFICIAL_BASE_URLS` in `headroom/config.py`, matching the endpoint whose catalogue, identity and prices you reviewed. `.env`'s `NEBIUS_BASE_URL` does not override this profile. |
| `available_credit_usd`, `authorized_total_usd` | Your confirmed usable **net model credit** and the amount you explicitly permit this installation to spend, as decimal strings; `0 < authorized <= available`. Allow separately for taxes, fees and other account spending. Do not copy this project's amounts. |
| `verified_at`, top-level `evidence` | Your review timestamp and reference to the account/credit/spending decision. These strings record the review; the schema does not authenticate it or validate a timestamp format. |
| `live_enabled`, `credit_confirmed` | Keep false until the configuration and external evidence have been reviewed. A schema check or API key is not that review. |
| `evidence_token_budget` | Positive evidence-rendering limit, at most 150000. The template's 24000 is an application setting, not a billable input-token ceiling. |
| `run_budget_mode`, `diagnosis_request_policy` | Keep `strict_reservation` and `null` for the ordinary workflow. The explicit FINAL48 policy below is optional; changing it changes the diagnosis request, not your authorization. |
| `models` | Exactly `ultra`, `super`, `nano`, with distinct exact catalogue/response IDs. All three are required even if an individual invocation only uses some roles. |
| Per-model `timeout_seconds`, `evidence` | A timeout in `(0, 600]` seconds and references supporting the exact model identity and current account prices. `docs/MODELS.md` describes the probe format and its limitations. |
| `input_usd_per_million`, `output_usd_per_million`, `cached_input_usd_per_million` | Current USD prices per million tokens, as nonnegative decimal strings. `null` cached price means unknown, **not free**; do not invent a discount. Replace every `REVIEW_*` price. |
| `capabilities` | Set only methods backed by your saved evidence. `VerifiedCapabilities` in `headroom/config.py` validates the method names. The template's text fallback and null reasoning method are unverified defaults; ordinary diagnosis requests reasoning, so review its supported selector rather than assuming the placeholder enables it. Nondefault methods need `capabilities.evidence`; `reasoning_effort` additionally requires tested `reasoning_on` / `reasoning_off` values. Optional low-effort mode requires its separate matching receipt; leave it absent for initial setup. |
| `billing.mode` | Keep `verified_provider_bound`. This is separate from the run's `strict_reservation` accounting mode. |
| `billing.prompt_token_ceiling`, `billing.max_prompt_utf8_bytes` | A proven server-billable input-token ceiling for **every accepted request** within the chosen byte domain, including schema/tools/template overhead. A single observed usage count or approximate tokenizer count is insufficient. The byte measurement is implemented by `BillingBound.upper_usd`. |
| `billing.max_completion_tokens`, `billing.output_cap_field` | The maximum output count your reviewed policy permits and the verified wire field (`max_tokens` or `max_completion_tokens`). The count must accommodate the selected workflow's actual requests; smaller caps cause pre-dispatch refusal. Both top-level cap fields cannot be sent together. |
| `billing.output_cap_includes_reasoning`, `billing.verified`, `billing.evidence` | Evidence that the selected output cap includes billed reasoning and that the entire billing domain is justified. Leave both flags false until verified. If you cannot establish an input bound, strict mode is not ready; consider the explicitly acknowledged estimate mode below instead of inventing one. |

The following **offline template check** imports schemas only. It does not read
`.env`, create a ledger, load a live runtime, download assets or call a provider.
`LiveProfile.model_validate_json` accepts string-shaped placeholders, so this
also checks capability dictionaries and demonstrates that the prices remain
unusable. Success means **disabled template structure checked**, not live-ready:

```bash
.venv/bin/python - <<'PYCODE'
from decimal import InvalidOperation
from pathlib import Path
from headroom.config import VerifiedCapabilities, normalize_base_url
from headroom.llm.cost import Pricing
from headroom.runtime import BillingBound, LiveProfile
p = LiveProfile.model_validate_json(Path('docs/examples/runtime-profile.disabled.json').read_text())
assert p.live_enabled is False and p.credit_confirmed is False
assert p.run_budget_mode == 'strict_reservation'
assert set(p.models) == {'ultra', 'super', 'nano'}
assert len({m.model_id for m in p.models.values()}) == 3
normalize_base_url(p.base_url)
for m in p.models.values():
    VerifiedCapabilities(**m.capabilities)
    assert isinstance(m.billing, BillingBound)
    assert m.billing.verified is False and m.billing.output_cap_includes_reasoning is False
    try:
        Pricing(m.input_usd_per_million, m.output_usd_per_million,
                m.cached_input_usd_per_million, verified=False)
    except InvalidOperation:
        pass
    else:
        raise AssertionError('Template must retain unreviewed price placeholders')
print('Disabled template structure checked; prices and evidence remain unreviewed.')
PYCODE
```

After filling your private copy, this separate **offline value check** still
requires it to be disabled. It validates decimal values and model/capability
syntax without claiming that external evidence, account access or billing
bounds are true. No secrets or profile contents are printed:

```bash
.venv/bin/python - <<'PYCODE'
from pathlib import Path
from headroom.budget import money
from headroom.config import ModelSpec, VerifiedCapabilities, normalize_base_url
from headroom.llm.cost import Pricing
from headroom.runtime import BillingBound, LiveProfile
try:
    p = LiveProfile.model_validate_json(Path('.cache/tokenfactory-runtime.json').read_text())
    assert p.live_enabled is False and p.credit_confirmed is False
    assert p.run_budget_mode == 'strict_reservation'
    assert set(p.models) == {'ultra', 'super', 'nano'}
    assert len({m.model_id for m in p.models.values()}) == 3
    assert 0 < money(p.authorized_total_usd) <= money(p.available_credit_usd)
    normalize_base_url(p.base_url)
    for m in p.models.values():
        assert isinstance(m.billing, BillingBound)
        price = Pricing(m.input_usd_per_million, m.output_usd_per_million,
                        m.cached_input_usd_per_million, verified=False)
        ModelSpec(m.model_id, m.timeout_seconds,
                  capabilities=VerifiedCapabilities(**m.capabilities), pricing=price,
                  output_cap_field=m.billing.output_cap_field, evidence=m.evidence)
    print('Local values checked; still disabled. External evidence needs operator review.')
except Exception:
    raise SystemExit('Local validation failed; review the configuration privately.') from None
PYCODE
```

The live loader `read_live_profile` intentionally rejects disabled profiles; it
is not the template checker. Do not enable the profile merely to make validation
pass. Only after completing your own evidence review, confirming available credit
and authorizing the amount, manually set `live_enabled=true` and
`credit_confirmed=true` in your private copy. Each strict model's completed
billing review must also justify `billing.verified=true` and
`billing.output_cap_includes_reasoning=true`, with the placeholder bounds replaced
as described in the table. These flags record facts you have verified; changing
them does not verify those facts. Then explicitly select your own profile with
`--runtime-profile .cache/tokenfactory-runtime.json` and your own `--budget` /
`--daily-budget` values when choosing to make model-backed requests. This page's
checks do not perform that activation or launch a trial request.

For an independent installation, leave `HEADROOM_BUDGET_DB_PATH` unset. The
ordinary CLI initializes its own `.cache/budget.db` when it starts a valid live
run; no download or copy of our ledger is needed. It applies the profile's total
limit and the CLI daily/run limits. Preserve that ledger across runs; changing
paths does not restore credit. An explicit external database path is for an
already initialized shared ledger and is validated rather than silently created.
The FINAL48 acceptance/allocation scripts are not prerequisites for normal CLI
use. F5 used a pre-reviewed shared profile and pool; its clean-checkout result
was not a test of creating a new user's account/profile from these instructions.

## Explicit FINAL48 diagnosis mode

A reviewed profile may explicitly select
diagnosis_request_policy = final48-diagnosis-only-2000-v1. This carries a typed
request policy through the repair/CLI diagnosis path: the prompt, saved request
metadata, initial call and any existing supplement all use a 2,000-token output
cap with reasoning disabled. It does not add calls or change Super/Nano. Profiles
without the field retain their prior behavior; conflicting study policies fail
before dispatch.

Ultra native JSON-schema input estimation is a separate opt-in billing mode:
local_estimate with estimate_protocol = ultra_native_schema_v1. It counts the
pinned NVIDIA chat template plus the entire serialized response_format, then
applies the explicitly configured multiplier and token allowance. Only the
verified model/request shape and configured token/byte domain are accepted.
This remains an estimate, not a provider billing bound. Usage is settled after
each request, and newly unknown charges or an exceeded estimate stop further
calls.

Neither option creates an allocation or rewrites historical charges. A new
FINAL48 pool still requires the owner's amount authorization and a separately
bound profile/database. The calibration and guarded offline CLI request checks
are recorded in [the input-estimation report](../reports/final48h-input-calibration-20261029/README.md).
No actual account profile was enabled by this implementation.

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

The SQLite budget ledger reserves each open run's limit as a floor against the daily and authorized-total budgets. The default run_budget_mode=strict_reservation also requires every request reservation to fit inside that run's remaining limit. Each actual network attempt reserves an explicitly labeled provider bound or local estimate before dispatch. Successful known usage settles that reservation. Missing usage, network errors and interrupted attempts retain unknown actual charges and block every later dispatch through the same ledger, including other open runs and after restart. Unknown is never displayed as zero or as a proven finite maximum debt.

The default CLI run limit is 0.6 USD and daily limit is 12 USD. Its admission meaning is controlled by the reviewed profile as described below. Environment caps `HEADROOM_RUN_BUDGET_USD` and `HEADROOM_DAILY_BUDGET_USD` can only lower a request's caps. The confirmed authorized total is a separate all-time admission limit, including across day boundaries. An estimated admission can overshoot its reservation and therefore cannot guarantee actual provider charges remain below that limit. Nano annotations share a 0.02 USD per-run sub-budget across retries. A response identity mismatch or violated billing bound halts further billable work.

These local controls govern this application only. They are not a guarantee about Nebius account charges made elsewhere. A card top-up is not an account-level spending cap.

## Explicit actual-usage run stop mode

A reviewed runtime profile may explicitly set "run_budget_mode": "actual_usage".
Omitting it preserves "strict_reservation" for old profiles and migrated ledger
rows. This is a run accounting choice, not the local_estimate admission policy:
all three model roles must have verified BillingBound records, and every
attempt must use verified_provider_bound. Mixing local estimates is refused.
Finite positive authorized-total and daily pools are required. Once the shared
ledger contains an actual_usage run, all later attempts through that ledger
must use provider bounds, including older strict_reservation runs and after
close/restart. This prevents another profile's local estimate from invalidating
the shared pool protection. Previously settled known estimate costs remain
recorded; no historical charges or reservations are reset.

The CLI keeps --budget 0.6; no project YAML can select this financial mode.
--runtime-profile selects the reviewed profile for fix/watch/evaluation, and
the acceptance drivers use the same ledger lifecycle. Before every POST, one
SQLite transaction accounts for other open-run floors, all outstanding/actual
charges and the next request's **full** provider upper bound in both shared
pools. Thus a $1.060576 Ultra reservation can fit a sufficient shared pool while
the run still has a $0.6 actual-cost stop line. Unused reservation is released
only after known usage is settled. This changes neither provider prices nor
the original actual-cost acceptance threshold.

Once known run usage reaches its limit, settlement commits the actual charge,
updates the call record and raises RunBudgetReached. No subsequent request in
that run may dispatch, including after restart. Exact equality is a stop and
still satisfies the cost <= limit check; strictly greater usage fails that
cost check and the run's top-level target-success claim is false. Retained
patches, candidate verification and measurements remain available in its
partial report. A run stop does not globally halt unrelated runs; unknown
billing, response identity mismatch, provider-bound violations and incomplete
local accounting still do. A run with pending/unknown billing or an invalid
provider bound cannot claim overall target success even if an earlier retained
configuration verified successfully; its original verification remains visible.

**The run stop line is not a hard maximum charge for one request.** A request
admitted while actual usage is below $0.6 may settle above $0.6, in which case
the run fails the unchanged cost requirement. Hard admission protects the
shared pool of model charges. The operator must set that pool below available
promotional credit after separately allowing for taxes/fees and prior spending
outside this ledger; this mode does not perform that conversion. The application
cannot protect against independent account spending by other clients.

HEADROOM_RUN_BUDGET_USD still only lowers the run stop line, and reaching a
0.05 line produces budget.exceeded plus a partial report. Daily pool 0.1
still rejects opening the default 0.6 run immediately; lowering the run line
does not let a full Ultra reservation bypass that daily pool. Reports/CLI
results record run_budget_mode, run_limit_basis, settled actual usage,
and separate run_budget_reached/run_budget_exceeded flags. Historical
reports without these fields remain unknown, not inferred.

## UTC day boundary

Before reservation and again before marking a request dispatched, the ledger
checks the run's accounting day and the ledger instance's day against a fresh,
trusted UTC date. An old run or long-lived ledger crossing midnight cannot send
new requests against yesterday's day pool. Start a new run with a fresh ledger
instance instead. A caller-supplied day label cannot override this dispatch
clock. Already-dispatched requests may settle after midnight, preserving their
original run/day and full known or unresolved charge. Confirmed unsent
reservations may still be cancelled; no dispatched reservation is erased.

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

### Optional tokenizer preparation and offline hash check

Only local-estimate admission needs these assets. Their source is NVIDIA's
[official tokenizer repository at the pinned revision](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4/tree/02462641f13d3af838b904f48195b9bb8a1e4ebc).
The exact repository, revision and three SHA-256 values come from
`TOKENIZER_REPO`, `TOKENIZER_REVISION` and `ASSET_HASHES` in
[headroom/llm/preflight.py](../headroom/llm/preflight.py); do not use `main` or
substitute hashes when a download fails. The revision is
`02462641f13d3af838b904f48195b9bb8a1e4ebc`.

This optional preparation command makes public HTTPS downloads, not model API
calls. It sends no API key, downloads no weights, does not execute remote code,
verifies bytes before writing, and refuses an existing mismatched file. Run it
only when choosing to prepare estimate-mode assets. It was not executed as part
of the documentation check:

```bash
.venv/bin/python - <<'PYCODE'
import hashlib
from pathlib import Path
from urllib.request import urlopen
from headroom.llm.preflight import ASSET_HASHES, TOKENIZER_REPO, TOKENIZER_REVISION
root = Path('.cache/tokenizers/nemotron-3-ultra') / TOKENIZER_REVISION
root.mkdir(parents=True, exist_ok=True)
assert not root.is_symlink()
for name, expected in ASSET_HASHES.items():
    path = root / name
    assert not path.is_symlink()
    if path.exists():
        assert path.is_file() and path.stat().st_size <= 64 * 1024 * 1024
        raw = path.read_bytes()
    else:
        url = f'https://huggingface.co/{TOKENIZER_REPO}/resolve/{TOKENIZER_REVISION}/{name}'
        with urlopen(url, timeout=60) as response:
            raw = response.read(64 * 1024 * 1024 + 1)
    assert 0 < len(raw) <= 64 * 1024 * 1024
    assert hashlib.sha256(raw).hexdigest() == expected, f'Hash mismatch: {name}'
    if not path.exists():
        with path.open('xb') as output:
            output.write(raw)
print(root.resolve())
PYCODE
```

The independent hash check below is **offline**. Use the printed absolute path
as `billing.tokenizer_assets_dir` only after separately reviewing the estimate
policy, domain, margins and risk acknowledgement. Matching these assets does
not prove provider token counts, establish a billing bound or enable live use.
For native JSON-schema responses, select the separately documented
`ultra_native_schema_v1` protocol; the original local-estimate mode rejects that
request shape.

```bash
.venv/bin/python - <<'PYCODE'
import hashlib
from pathlib import Path
from headroom.llm.preflight import ASSET_HASHES, TOKENIZER_REVISION
root = Path('.cache/tokenizers/nemotron-3-ultra') / TOKENIZER_REVISION
assert root.is_dir() and not root.is_symlink()
for name, expected in ASSET_HASHES.items():
    path = root / name
    assert path.is_file() and not path.is_symlink()
    assert 0 < path.stat().st_size <= 64 * 1024 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, f'Hash mismatch: {name}'
print('Three pinned tokenizer hashes match; no provider verification performed.')
PYCODE
```

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

## Explicit shared ledger across checkouts

HEADROOM_BUDGET_DB_PATH may select an existing initialized budget SQLite database
by absolute path. The default remains the current project's .cache/budget.db.
The explicit target, its parents and SQLite sidecars must not be symlinks;
missing, empty, unrelated or replaced targets fail instead of creating a fresh
budget pool. Offline acceptance fixtures reject paths outside their private root
before opening SQLite.

This setting does not reset history, clear unknown charges, select a runtime
profile or change spending limits. Each CLI/API/acceptance entrypoint must still
use the same reviewed absolute profile and explicit authorized daily/run limits.
A copied checkout must not silently acquire a new allowance. Path selection
assumes a trusted operator filesystem; validation and SQLite open are not an
atomic no-follow operation.

The development ledger remains halted after the R3 HTTP 529 request with unknown
actual usage. Configuring this path is not authorization to clear that halt or
perform another paid evaluation.
