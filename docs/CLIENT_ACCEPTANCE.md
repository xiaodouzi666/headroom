# T1.3 client acceptance

This driver covers the original PLAN T1.3 client gates separately: a real Super
response accepted by a strict schema, and one successful Ultra request carrying
a genuine long capture evidence package. It does not run training, repair,
research, Nano annotation, T1.4 diagnosis scoring, or an automatic retry campaign.

## Prepare without credentials

From the repository after `source scripts/env.sh`:

```sh
python scripts/check_client_acceptance.py --output runs/acceptance/client/prepared --capture runs/path/to/preserved-lab-capture
```

Omit `--capture` to prepare only the Super case; Ultra is explicitly pending.
Preparation reads no runtime profile or credential, constructs no Store or budget
ledger, and sends no API request. Use a fresh output directory outside the source
capture. Original captures and historical runs are never overwritten.

The selected capture is resolved through the existing
`selected_capture_directory` contract, including nested wrapper captures.
Preparation requires a completed/oom CUDA capture, complete capture metadata,
verified cleanup, and matching preserved source hashes. The snapshot has a
512 MiB read cap; final evidence and prepared message files are capped at 16 MiB.
These checks establish file consistency, not authenticity against a malicious
target that fabricated its own capture.

The C4 summary retains its existing 150,000-token budget. For this dedicated
long-input gate only, the driver adds original allocator records from that
**same snapshot**, in order, with JSON pointers and canonical content hashes.
It deduplicates equal records and never repeats whole snapshots or combines
unrelated runs. The source snapshot hash and selected record positions are
retained alongside the exact router input. No synthetic padding is added.
The default local preparation target is 220,000 cl100k tokens; a package with
fewer than 200,000 tokens of C4 plus record content remains pending. Locator
and hash headers are excluded from that content count.

Local counts are estimates. They do not establish the provider tokenizer,
billable input, a provider token bound, or a successful 200k request.
The global runtime evidence budget and live profile are unchanged.

## Execute only after separate task-specific authorization

Current authorization for at most $0.10 of minimal connectivity does **not**
authorize these acceptance calls. No execution was performed by implementing
or testing this driver. The flags below record an already granted authorization;
they do not create permission, credits, a profile, or a higher budget.

A future authorized operator explicitly supplies one case, an existing reviewed
profile, and admission limits:

```sh
python scripts/check_client_acceptance.py --execute --live-authorized \
  --prepared runs/acceptance/client/prepared/prepared.json \
  --case super_schema --profile /path/to/already-reviewed-profile.json \
  --run-limit-usd APPROVED_RUN_LIMIT --daily-limit-usd APPROVED_DAILY_LIMIT
```

Use `--case ultra_200k` for the separate long-input case. There is no implicit
“execute all” or automatic driver retry. Each case creates an exclusive execution
directory; reusing the same prepared case is refused, including after an interrupted
or blocked attempt. A reviewed new package is needed before any deliberate rerun.

Before runtime construction, the driver checks the prepared manifest seal, exact
messages, all source/capture hashes, and capture selection again. A changed
payload or source, or insufficient long evidence, prevents dispatch.

Both T1.3 and T1.4 use `headroom.acceptance.common.acceptance_run`:
- Existing `read_live_profile`, `build_live_runtime`, `LLMRouter`, verified
  capability/price/cap checks, and the original SDK retry policy.
- The authoritative global `.cache/budget.db`. It is never reset or replaced.
  Total authorization is the existing profile's `authorized_total_usd`; run
  and daily admission limits are explicit. Existing HEADROOM_RUN_BUDGET_USD and
  HEADROOM_DAILY_BUDGET_USD deployment limits can only lower these values; the
  receipt records both requested and effective limits. An admission limit is different from
  an actual acceptance cost threshold, and local-estimate mode is never a hard
  billing guarantee.
- A separate `runs/acceptance/headroom.db` Store, so acceptance calls are not
  presented as repaired runs. Full per-attempt provider identity, usage, exact
  Decimal cost, and the global-ledger snapshot are retained in each runtime receipt.
- Closing a run preserves unresolved reservations and billing halts. Unknown
  charges, model-identity failures and cap violations block later calls through
  the ordinary shared ledger, including across cases and process restarts.

No enabled profile is generated, and `live_enabled`/`credit_confirmed` and
original pricing/billing requirements are not bypassed. If the currently reviewed
request domain or authorized amount cannot admit 200k, execution is blocked:
a larger balance or the local token count is not a replacement for those gates.

## Results and interpretation

`prepared.json` contains case readiness, input hashes, local counts and source
provenance. `prepared.seal.json` detects accidental manifest changes; it is not
a cryptographic identity or protection against an owner rewriting both files.
Each `execution-CASE/result.json` includes the response, actual returned model,
provider usage, actual cost, latency and gate results.
`execution-CASE/runtime/runtime.json` retains every attempted call and billing
state, even after validation errors or interruption. Unknown cost remains null. Confirmed not-dispatched records are reported separately;
pending dispatch is unresolved and is not claimed as a completed live request.
The original role model is checked before sending, and response scoring uses
the probe ID frozen at package verification rather than rereading it after a call.

Super uses the real router's strict schema validation (extra fields forbidden,
strict types) and verifies the prepared probe ID and requested values. The
receipt records the profile's JSON method, distinguishing text plus local
validation from verified provider-native JSON support.

Ultra requires the expected response model, known valid usage and cost, nonempty
untruncated response, and **actual provider prompt_tokens >= 200,000**. Provider
usage counts the full request, including its short instructions; the provider
does not separately report evidence-only tokens. The evidence-content local
count is retained separately. No result claims all allocator records were
semantically processed or that a larger context window was established.

`checks_passed` reports mechanical gate checks. `accepted` additionally requires
live provenance. MockTransport always forces `offline_fixture` and can never
satisfy real T1.3. Receipt status “completed” means runtime lifecycle completion,
not acceptance; the case result is authoritative. A genuine later live result
must be reviewed before recording latency/cost and acceptance in FEEDBACK.

## Offline verification

`tests/test_client_acceptance.py` invokes the actual SDK/router/runtime hooks
against MockTransport using only a temporary profile and fixture credential.
Independent DNS, socket-connect and real-project-`.env` guards are installed.
The tests cover strict schema failure with retained cost, actual provider token
gates, unchanged admission/authorization rules, unknown billing across restart,
changed payload/source, insufficient evidence, interruption and non-repetition.
They perform no GPU or paid API work.
