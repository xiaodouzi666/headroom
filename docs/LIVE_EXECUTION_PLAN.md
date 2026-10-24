# Live-model acceptance: first checkpoint complete, remaining package proposed

Status on 2026-10-25 local: **the explicitly authorized first three-call checkpoint passed; the remaining package is unapproved and unexecuted**. Initial proposal was prepared 2026-10-24 against HEAD `96aca1d`; executable-driver instructions were updated from `20e9956`. Actual checkpoint receipts are in reports/model-checkpoint-20261025/. This document does not enable a live profile, change the original PLAN, create credentials, or authorize additional spending.

## Current evidence and what it does not establish

Promotional credit was redeemed in the existing Token Factory organization on 2026-10-24. At 14:50 UTC, the refreshed transaction was **Adjustment: AI Builder Program Credits +$30.25 (Incl. tax)** and account balance was **$30.25**; trial credit remained separately **$1 / 29 days**. The received promotion had a $25 face value. The original at-least-$25 credit-availability condition is now evidenced, but this is promotional account credit, not cash or a card recharge. Evidence: `reports/promo-redemption-20261024.json`. The earlier private `.cache/account-check-20261024T132819Z.json` remains an unchanged historical snapshot; do not publish its tenant information.

The specific promotion email states a 2026-12-31 redemption deadline and no expiry after redemption. The $25 × 1.21 = $30.25 adjustment is consistent with the official Netherlands 21% VAT rate and the UI's inclusive-tax label; it is not a new provider spending guarantee. See [billing and consumption](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new). Refresh available credit immediately before any later authorized dispatch. The existing headroom-azuki key remains listed under the same account's default project; no new key or inference call was made during redemption.

The default `.cache/tokenfactory-runtime.json` remains closed/absent. The earlier $0.10 trial authorization covered two Super/Nano chats costing $0.00003666 by usage. The owner then authorized exactly one Ultra chat, one Super json_schema and one Super tools request, with zero retries, a $1.25 token cap and $2 total envelope. All passed and all three allowed requests are consumed: current checkpoint token cost $0.0003143, 21% reference amount $0.000380303. These are not invoice totals and neither authorization covers the remaining package. T0.4 remains unaccepted.

The historical price file `.cache/setup/probe-prices-minimal-20261024.json` covers Super/Nano only. The later preparation directory reports/promo-checkpoint-preparation-20261024/ remains an unchanged pre-approval receipt. The executed checkpoint used reports/model-checkpoint-20261025/pricing-current.json, manually matched against fresh catalogues before each dispatch. Its scope is exact Ultra/Super only; it is not a full live runtime profile or permission for more calls.

Historical catalogue arithmetic below is a planning input, not renewed provider verification:

| Role | Exact model ID | Historical context ceiling | Input / output USD per million |
| --- | --- | ---: | --- |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1048576 | 1 / 3 |
| Super | `nvidia/nemotron-3-super-120b-a12b` | 262144 | 0.30 / 0.90 |
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262144 | 0.06 / 0.24 |
| Lightning | `nvidia/Nemotron-3_5-Lightning` | 1048576 | 0.06 / 0.24 |

Refresh both authenticated official catalogues, verify exact response IDs, current ordinary/cached prices and any request surcharges, and review `max_completion_tokens` as including billed reasoning. Current code's price model must cover every nonzero surcharge before dispatch. Historical Ultra/Super metadata also reported 200000 tokens/minute; a large advertised context does not prove a 500k/900k request is allowed for this account.

## The budget mismatch is real

Strict admission reserves the full reviewed provider input ceiling, not the short local prompt count. Historical strict reservation for Ultra is:

- 256 output tokens: $1.049344.
- 1024 output tokens: $1.051648.
- 4000 output tokens, used by diagnosis: $1.060576.

The previous trial-only $1 balance could not admit even the first strictly bounded Ultra probe. The newly credited promotional balance removes that particular balance obstacle. A funded account alone still does not make the default `--budget 0.6` pipeline executable: the first Ultra diagnosis requires more than the whole run allowance. PLAN T1.4's $0.35 is an **actual per-call acceptance threshold**; no separate $0.35 runtime cap was found. PLAN T1.12 additionally explicitly requires the $0.60 run argument.

Two different future choices exist; neither is implicit approval:

1. Keep strict provider-bound admission and explicitly approve a larger run/diagnosis admission cap. This can preserve the actual $0.35/$0.60 pass/fail measurements, but changes the original MVP's `--budget 0.6` procedure and therefore needs a narrow user decision.
2. Explicitly accept the implemented Ultra `local_estimate` admission mode while preserving `--budget 0.6`. Its local tokenizer and margins are not provider guarantees; a single actual charge may exceed its reservation or nominal total cap. Full actual usage is recorded and subsequent calls halt. Do not describe this as a guaranteed hard spending ceiling.

Super/Nano retain strict admission. The current Ultra estimator supports reviewed text-schema fallback, not native `response_format`, arbitrary provider reasoning controls, or ignored historical tool IDs. Its pinned local template has a 262144-token limit although the provider catalogue advertised 1048576; a nominal 200k evidence pack is not automatically eligible for this estimator.

## Completed first authorization — exactly three calls

**Authorized and completed: one staged strict probe tranche with token-charge cap $1.25 and a $2 overall envelope.** Refreshed promotional balance was $30.25 including tax before each call and after completion. The $0.75 difference was reserved for tax/fees, not extra calls. The tranche was separate from the old $0.10 authorization and used strict provider bounds, without local-estimation risk acceptance.

The completed tranche comprised exactly:

1. one Ultra chat request, output cap 1024;
2. one Super `json_schema` request, output cap 256;
3. one Super `tools` request, output cap 256.

Freshly reviewed bounds gave fixed reservations summing to $1.2093952. Reports were reviewed sequentially, with one POST per process and no retries. All three capabilities passed with exact identity, complete usage and no truncation/unknown charge/bound violation. The tools fixture only generated the expected add call; it executed no external tool. No long-input request, live runtime profile or repair was included. Per-call results and independent review are retained in reports/model-checkpoint-20261025/verification.json.

This passed access/capability checkpoint is **not T0.4/T1.3/MVP acceptance**. Its three-call authorization is fully consumed even though the usage-priced cost was only $0.0003143. Any further inference requires a separate scope; do not repeat these calls under this receipt.

## Exact probe commands and review protocol

The following are future operator templates, not instructions to execute now. `CREDIT`, `REMAINING`, `PRICE_FILE`, and each unique output directory must be filled only after the corresponding authorization and review. `source scripts/env.sh` selects the project tools but does not load secrets. `uv run --env-file .env` is the intentionally explicit future credential-loading boundary.

First refresh catalogue evidence; this route makes only the two official GET requests and requires no price/budget flags:

~~~sh
cd /home/xiaodouzi/workspace/headroom
source scripts/env.sh
uv run --env-file .env python scripts/probe_models.py \
  --suite catalogue --execute \
  --output-dir reports/tokenfactory-catalogue-UNIQUE
~~~

After reviewing a new price file and account credit, run one capability request at a time:

~~~sh
uv run --env-file .env python scripts/probe_models.py \
  --suite capabilities --roles ultra --capability-method chat \
  --model-id ultra=nvidia/Nemotron-3-Ultra-550b-a55b \
  --max-completion-tokens 1024 --max-retries 0 \
  --execute --allow-paid-requests --credit-confirmed \
  --available-credit-usd "$CREDIT" --budget-usd "$REMAINING" \
  --pricing-file "$PRICE_FILE" \
  --output-dir reports/tokenfactory-ultra-chat-UNIQUE
~~~

For the two Super requests, use the same command structure with `--roles super`, exact ID `nvidia/nemotron-3-super-120b-a12b`, output cap 256, and respectively `--capability-method json_schema` and `--capability-method tools`. Recompute `REMAINING` after **each reviewed report**, from the single authorized tranche total minus all known charges and unresolved reservations. Do not provide the original full amount independently to every invocation.

The probe refresh checks exact model presence, but does not compare refreshed catalogue price/context/fee values against the reviewed pricing file. Before every POST, the operator must perform that comparison and refuse unknown/nonzero unsupported fees or mismatches; refreshed catalogue retrieval alone is insufficient. The completed checkpoint retained these manual comparisons in its review receipts.

The probe budget is per-process memory, not the runtime's durable SQLite ledger. Every invocation also performs two GETs. A report with HTTP 400/429 and missing usage can retain a conservative reservation without globally halting the script; exit code zero does not mean all capabilities passed. Consequently:

- Do not execute a shell loop, `--suite all`, or automatic retry chain under the immediate-stop-on-unknown policy.
- Run one role/method or one long-input size per invocation, retries zero.
- Inspect HTTP status, exact model identity, finish reason, usage completeness, reserved/actual cost, billing-bound flags and capability outcome before authorizing the next command.
- Unknown charges remain charged/reserved for the envelope. Reconcile them with provider/account evidence before any further dispatch; never reset the total by starting a new CLI process.
- Four-way Super concurrency is a later, separately approved stage. Once four requests are sent, an error in one cannot unsend the others; report that concurrency explicitly.

## Full acceptance stages and proposed capped envelopes

A larger, **conditional** proposal is $12.30 of nominal token-charge allowance, with a $15 account envelope only if separately reviewed fees fit the remaining $2.70. A 21% calculation yields $14.883, consistent with the rate underlying the displayed promotional adjustment. The actual future usage invoice and fee coverage still need reconciliation; this arithmetic is not a guaranteed all-in cap. The completed first tranche belongs to stage A: subtract its actual $0.0003143 token cost if a later stage-A total is authorized, without counting its released reservation twice.

| Stage | Proposed nominal token cap | Required scope and stop point |
| --- | ---: | --- |
| A: T0.4 | $2.90 | Finish reviewed four-model matrix, four Ultra long sizes, and four-way Super concurrency; stop before any reservation that cannot fit, or immediately after unknown billing/identity/bound failure |
| B: T1.3 | $1.20 | One real Super schema call through the client/router, and one real Ultra 200k evidence-pack call through that client; review both before advancing |
| C: T1.4 diagnosis | $2.80 | Eight synthetic first diagnoses; actual cost must be <= $0.35 each, with real stack-reference and authored-truth review |
| D: T1.12 MVP | $5.40 | Nine original default-policy runs, each nominal cap $0.60; retain all failed runs and original acceptance thresholds |
| Total | $12.30 | Any unspent allowance remains unused unless expressly included in a later approved stage |

This envelope is a **capped attempt**, not a promise to complete all acceptance. Stages C/D are currently blocked on the explicit strict-versus-estimate choice above. With local estimates the nominal cap is not a provider-hard ceiling. If a genuinely hard total is required, use strict bounds and resolve the original $0.60 procedure conflict first.

For perspective, reserving every default probe at its full historical input ceiling gives $20.20365824 for the 60 POST requests in the 62-item plan, before tax/fees. This is a conservative arithmetic ceiling, not predicted actual cost. It alone exceeds stage A's capped attempt and would be about $24.4464 with a 21% tax allowance. Do not promise the full plan fits a $25 promotion on worst-case reservations plus downstream work.

### A: T0.4 detail

The thirteen implemented methods are `chat`, `json_object`, `json_schema`, `fenced`, `tools`, `template_on`, `template_off`, `prefix_on`, `prefix_off`, `effort_high`, `effort_none`, `reasoning_budget`, and `max_thinking_tokens`. Dispatch each role/method separately under the protocol above. Override Nano's historical default with exact `--model-id nano=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`.

Long-input template, separately for 64000, 200000, 500000, and 900000:

~~~sh
uv run --env-file .env python scripts/probe_models.py \
  --suite long --long-input-tokens 64000 \
  --model-id ultra=nvidia/Nemotron-3-Ultra-550b-a55b \
  --max-completion-tokens 256 --max-retries 0 \
  --execute --allow-paid-requests --credit-confirmed \
  --available-credit-usd "$CREDIT" --budget-usd "$REMAINING" \
  --pricing-file "$PRICE_FILE" \
  --output-dir reports/tokenfactory-long-64000-UNIQUE
~~~

Concurrency uses the same paid flags and `--suite concurrency`; it schedules four Super requests concurrently and needs enough remaining allowance for all four reservations. Historical cap256 reservation is $0.3154944 for the group.

Record actual server input tokens separately from the generator's approximate count, latency, usage and exact failure text. A largest successful sample is a **tested lower bound**, not proof of the provider's exact maximum. Rate-limit failure is not evidence of a context limit. Merely accepting a reasoning parameter is not proof that it changed reasoning behavior. The script deliberately leaves `accepted=false` and does not apply its configuration proposal; reviewed model/config updates, meaningful capability interpretation and >=5 genuine feedback entries remain required by PLAN T0.4.

### B: T1.3 client acceptance driver

The dedicated driver is implemented in scripts/check_client_acceptance.py and
headroom/acceptance/client.py; see docs/CLIENT_ACCEPTANCE.md. Preparation uses one
preserved CUDA capture, its unchanged C4 summary and unique original allocator
records with JSON pointers and hashes. It does not load credentials or a runtime
profile. Local counts are estimates; only a successful real Ultra response with
provider prompt_tokens >= 200000 can accept the long-input gate. A needle/filler
probe still does not satisfy this evidence-pack requirement.

Prepare a new package without inference:

~~~sh
python scripts/check_client_acceptance.py \
  --capture "$CAPTURE" --output runs/acceptance/client/UNIQUE
~~~

After separate authorization and capability/credit review, execute one selected
case at a time; review its result before selecting the other case:

~~~sh
python scripts/check_client_acceptance.py \
  --prepared runs/acceptance/client/UNIQUE/prepared.json \
  --case super_schema --execute --live-authorized \
  --profile "$PROFILE" --run-limit-usd "$CASE_ADMISSION" \
  --daily-limit-usd "$DAILY_ADMISSION"
~~~

The second case is ultra_200k. Both use an output cap of 512, the actual
build_live_runtime/router chain and the shared .cache/budget.db. Dedicated
acceptance records live in runs/acceptance/headroom.db and do not become repair
results. Each package permits only one execution attempt per case; failed
artifacts are retained. Unknown charges block later cases and invocations.
Deployment budget environment variables can lower admission limits.

Use reviewed strict admission for this proposal. A 220k local preparation does
not prove the local-estimator template or a provider bound will accept it.
Inspect the returned identity, schema/text, usage, latency, actual cost and
runtime receipt; append factual live findings to docs/FEEDBACK.md only after
real execution. Offline MockTransport results never close T1.3.

### C: T1.4 diagnosis-only acceptance driver

scripts/check_diagnosis_acceptance.py prepares eight specified original captures
without rerunning GPU workloads. It freezes README/manifest truth, source and
evidence hashes, actual stack IDs and required savings. s5 uncertainty remains
explicit with denominator eight; a cache gap is not relabeled as proven harmful
fragmentation. See docs/DIAGNOSIS_ACCEPTANCE.md.

~~~sh
python scripts/check_diagnosis_acceptance.py \
  --from-baselines reports/evaluation-baselines-20261024.json \
  --output runs/acceptance/diagnosis/UNIQUE
~~~

The future separately authorized execution template is:

~~~sh
python scripts/check_diagnosis_acceptance.py \
  --prepared runs/acceptance/diagnosis/UNIQUE/preparation.json \
  --execute --live-authorized --runtime-profile "$PROFILE" \
  --admission-cap-usd "$CASE_ADMISSION" \
  --campaign-cap-usd "$CAMPAIGN_ADMISSION" --daily-cap-usd "$DAILY_ADMISSION"
~~~

One diagnosis per case uses max_supplements=0 through the shared runtime and
ledger. It does not run patches, Lab, research or Nano. It retains raw responses,
validation issues, stack references, first-category comparisons, actual usage,
cost and timing. Missing/changed inputs, unknown charges and failed capability
or budget admission remain visible; they do not become zero-cost successes.

The original first-cause threshold remains >=6/8 and actual per-call cost remains
<=$0.35. Explicit admission values are separate from that actual-cost gate.
Historical strict Ultra reservation with 4000 output tokens is $1.060576, so a
$0.35 admission cap can refuse a call even if its eventual actual cost might be
lower. A local estimate remains non-guaranteed and requires the earlier explicit
decision; neither this driver nor these templates supply that authorization.

### D: T1.12 existing executable path

Offline prerequisites, without reading credentials or running workloads:

~~~sh
uv run --offline headroom eval eval/mvp_phase1.yaml --validate-only
uv run --offline headroom eval eval/mvp_phase1.yaml --plan-only \
  --conditions full_ultra --policies default --search-mode until_target \
  --budget 0.6 --campaign-budget 5.4 --daily-budget 12
~~~

Do **not** use `--dry-run` as a read-only substitute: it runs real Lab baselines.

Once the live profile, authorization, original-plan decision and earlier gates are complete, the existing full path is:

~~~sh
uv run --offline headroom eval eval/mvp_phase1.yaml --live \
  --conditions full_ultra --policies default --search-mode until_target \
  --budget 0.6 --campaign-budget 5.4 --daily-budget 12 \
  --runtime-profile .cache/tokenfactory-runtime.json
~~~

The nine IDs are `s1_batch_too_big`, `s2_fp32_adamw_1b`, `s3_eval_no_grad_missing`, `s4_loss_accumulation_graph`, `s5_fragmentation_varlen`, `s6_full_vocab_logits_fp32`, `s7_frozen_params_optimizer_state`, `s8_two_models_resident`, and `nanogpt`. To require a human/operator checkpoint after each, add one `--scenario ID`, use a $0.60 campaign cap, and reconcile all nine campaigns against the shared $5.40 tranche. Do not rerun the first case without charging the extra attempt to a newly approved allowance.

The live campaign uses the existing full pipeline, isolated GPU execution and default policy; it is not included in the current no-GPU preparation. Preserve actual costs, selected configuration, numerical basis/limitations, wall time, patches and all failures. MVP reclaim uses its explicit 20% target; it does not replace T1.6's 30% s3 check or resolve s2's separate T1.2/T2.1 gates.

## Global stop conditions and ledger reconciliation

Stop before sending if account credit, authorization, exact catalogue identity, reviewed input/output bound, price coverage, or necessary source/evidence is missing; if the next reservation exceeds the stage or total remainder; or if the live profile is not deliberately enabled for that stage.

After any dispatch, stop on unknown usage/charge, identity mismatch, violated bounds, account suspension/credit/rate-limit response, invalid/truncated structured output, or a failed stage acceptance requiring investigation. Retain the original result and report. No automatic retry, fallback model, recharge, wider budget, pricing verification flag, or change to PLAN follows from a failure.

Runtime calls share `.cache/budget.db`; it preserves pending/unknown charges across runs/restarts. Probe invocations do not share that ledger, so an operator receipt must subtract probe expenses/reservations before setting the remaining runtime authorization. Runtime `authorized_total_usd` is an all-time ledger limit, not a fresh per-stage balance; reconcile any existing rows before choosing it. The $12 daily default is separate from the all-time total and the proposed $12.30 combined package; do not silently increase the daily cap to squeeze stages into one day.

A closed/absent live profile remains the required state until preparation and the explicit authorization choice are complete. The narrow checkpoint has its separate receipt; no broader stage acceptance is inferred.

## Narrow decisions still outstanding

The <=$2 checkpoint was authorized and completed. No repeated approval is needed for those already completed calls. Further T0.4 capabilities, long input and concurrency require a new concrete spending scope; the larger stage table above is still only a proposal.

Before diagnosis/MVP, ask one separate concrete decision: retain a genuinely hard provider-bound budget and approve the specified larger admission cap/procedure, or accept the explicitly described local-estimation overshoot risk while keeping the original nominal $0.60 cap. Neither choice lowers actual-cost or scientific acceptance thresholds.

Original C.5 four-round/stop-at-target versus T2.1 six-round/Pareto language, default precision permission versus requested bf16 tier, and s2's two-round fixture issue remain separately documented pending decisions. This package keeps default `until_target` and default precision policy; it does not use this authorization to resolve those disagreements or alter historical evidence.

Sources: `docs/PLAN.md` (T0.4/T1.3/T1.4/T1.12/T2.1), `docs/RUNTIME.md`, `docs/PROMPT_PREFLIGHT.md`, `docs/MODELS.md`, `docs/EVALUATION.md`, `scripts/probe_models.py`, `headroom/runtime.py`, `headroom/llm/admission.py`, `headroom/orchestrator.py`, `headroom/evaluation.py`, and `eval/mvp_phase1.yaml`.
