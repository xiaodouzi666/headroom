# Proposal: next live-model acceptance execution package

Status: **proposal only; not authorized and not executed**. Prepared 2026-10-24 against Headroom HEAD `96aca1d`. This document does not enable a live profile, change the original PLAN, create credentials, or authorize spending. No key, API call, or GPU job was used to prepare it.

## Current evidence and what it does not establish

The account UI was refreshed on 2026-10-24; the original confirmed-credit gate of at least $25 remains unmet. Private account evidence remains in `.cache/account-check-20261024T132819Z.json`; do not publish its tenant information. Credit must be refreshed immediately before any later authorized dispatch.

The default `.cache/tokenfactory-runtime.json` is absent. Previous explicit authorization covered only $0.10 of trial connectivity checks. It does **not** authorize this package. Existing Super/Nano chat evidence is in `reports/tokenfactory-minimal-20261024.json`; Ultra has not been invoked. The two known calls had usage-derived token cost $0.00003666, not an invoice total. T0.4 remains unaccepted.

The existing reviewed probe price file `.cache/setup/probe-prices-minimal-20261024.json` contains only Super and Nano. It cannot authorize Ultra or Lightning requests. A future reviewed file must be prepared from refreshed official model metadata and output-cap evidence; do not add `verified=true` merely to bypass a guard.

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

An account with only $1 of usable credit cannot admit even the first strictly bounded Ultra probe. A funded account alone also does not make the default `--budget 0.6` pipeline executable: the first Ultra diagnosis requires more than the whole run allowance. PLAN T1.4's $0.35 is an **actual per-call acceptance threshold**; no separate $0.35 runtime cap was found. PLAN T1.12 additionally explicitly requires the $0.60 run argument.

Two different future choices exist; neither is implicit approval:

1. Keep strict provider-bound admission and explicitly approve a larger run/diagnosis admission cap. This can preserve the actual $0.35/$0.60 pass/fail measurements, but changes the original MVP's `--budget 0.6` procedure and therefore needs a narrow user decision.
2. Explicitly accept the implemented Ultra `local_estimate` admission mode while preserving `--budget 0.6`. Its local tokenizer and margins are not provider guarantees; a single actual charge may exceed its reservation or nominal total cap. Full actual usage is recorded and subsequent calls halt. Do not describe this as a guaranteed hard spending ceiling.

Super/Nano retain strict admission. The current Ultra estimator supports reviewed text-schema fallback, not native `response_format`, arbitrary provider reasoning controls, or ignored historical tool IDs. Its pinned local template has a 262144-token limit although the provider catalogue advertised 1048576; a nominal 200k evidence pack is not automatically eligible for this estimator.

## Smallest recommended next authorization

**Only after usable credit is at least $2: authorize one staged strict probe tranche with token-charge cap $1.25 and a $2 overall envelope.** The $0.75 difference is unspent headroom for tax/fees and account uncertainty, not permission for extra calls. Confirm applicable fees before treating that envelope as sufficient. This tranche is separate from the old $0.10 authorization and requires no local-estimation risk acceptance.

The tranche comprises, at most:

1. one Ultra chat request, output cap 1024;
2. one Super `json_schema` request, output cap 256;
3. one Super `tools` request, output cap 256.

Using the historical bounds, all three reservations sum to $1.2093952. No retries, no alternative-method retries, no long-input requests, no live runtime profile, and no repairs are included. Review each report before the next request. If Ultra truncates, JSON parsing fails, tools do not execute as expected, the model identity differs, billing is unknown, or an account/rate limit is returned, stop and retain that evidence. A failed capability result is useful evidence, not permission to repeat it.

This is an access/capability checkpoint, **not T0.4/T1.3/MVP acceptance**. If promotional credit remains absent and no payment is desired, keep this tranche pending and continue offline work.

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

The probe budget is per-process memory, not the runtime's durable SQLite ledger. Every invocation also performs two GETs. A report with HTTP 400/429 and missing usage can retain a conservative reservation without globally halting the script; exit code zero does not mean all capabilities passed. Consequently:

- Do not execute a shell loop, `--suite all`, or automatic retry chain under the immediate-stop-on-unknown policy.
- Run one role/method or one long-input size per invocation, retries zero.
- Inspect HTTP status, exact model identity, finish reason, usage completeness, reserved/actual cost, billing-bound flags and capability outcome before authorizing the next command.
- Unknown charges remain charged/reserved for the envelope. Reconcile them with provider/account evidence before any further dispatch; never reset the total by starting a new CLI process.
- Four-way Super concurrency is a later, separately approved stage. Once four requests are sent, an error in one cannot unsend the others; report that concurrency explicitly.

## Full acceptance stages and proposed capped envelopes

A larger, **conditional** proposal is $12.30 of nominal token-charge allowance, with a $15 account envelope only if separately reviewed fees fit the remaining $2.70. For reference only, a 21% buffer would yield $14.883. This is not a claim about this account's tax treatment. The first $1.25 tranche above would be included in stage A, not added twice.

| Stage | Proposed nominal token cap | Required scope and stop point |
| --- | ---: | --- |
| A: T0.4 | $2.90 | Finish reviewed four-model matrix, four Ultra long sizes, and four-way Super concurrency; stop before any reservation that cannot fit, or immediately after unknown billing/identity/bound failure |
| B: T1.3 | $1.20 | One real Super schema call through the client/router, and one real Ultra 200k evidence-pack call through that client; review both before advancing |
| C: T1.4 diagnosis | $2.80 | Eight synthetic first diagnoses; actual cost must be <= $0.35 each, with real stack-reference and authored-truth review |
| D: T1.12 MVP | $5.40 | Nine original default-policy runs, each nominal cap $0.60; retain all failed runs and original acceptance thresholds |
| Total | $12.30 | Any unspent allowance remains unused unless expressly included in a later approved stage |

This envelope is a **capped attempt**, not a promise to complete all acceptance. Stages C/D are currently blocked on the explicit strict-versus-estimate choice above. With local estimates the nominal cap is not a provider-hard ceiling. If a genuinely hard total is required, use strict bounds and resolve the original $0.60 procedure conflict first.

For perspective, reserving every default probe at its full historical input ceiling gives $20.20365824 for the 60 POST requests in the 62-item plan, before tax/fees. This is a conservative arithmetic ceiling, not predicted actual cost. It alone exceeds stage A's capped attempt and would be about $24.4464 under the illustrative 21% buffer. Do not promise the full plan fits a $25 promotion on worst-case reservations plus downstream work.

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

### B: T1.3 detail and missing executable driver

A needle probe alone does not fulfill the original client/router/evidence-pack contract. There is no existing dedicated T1.3 acceptance command in `scripts/`; do not invent one. Before enabling execution, prepare and review a small acceptance driver using existing `build_live_runtime`, `BudgetLedger`, and `router.chat`, with:

- a single Super schema-validated request and one Ultra request containing an auditable 200k evidence pack;
- explicit selected model identity, complete final request hash/token domains, response validation, server usage, latency, and retained raw evidence;
- the shared `.cache/budget.db`, unique run IDs, no supplements/retries after unknown cost, and an explicitly bounded output;
- a **strict** reviewed profile for the long Ultra request, rather than assuming the 262144 local template can accommodate that evidence pack.

At output cap4000 for both calls, historical combined strict reservation is $1.1428192, fitting the proposed $1.20 tranche. The account, reviewed bounds and all earlier expenditure must still permit it. The driver is a remaining preparation deliverable, not an API acceptance result.

### C: T1.4 detail and missing executable driver

There is no diagnosis-only acceptance CLI. Prepare a reviewed driver that reuses valid original scenario evidence, calls `diagnose_with_router(..., max_supplements=0)` once per case, and saves schema validation, real stack IDs, expected/observed first cause and per-call usage. If evidence needs regeneration, schedule the existing isolated Lab separately; it is GPU work and is not included in the present read-only preparation.

Do not count a local estimator or seed/source hash as real model validation. The current s5 authored-truth uncertainty must remain visible; do not relabel measured fragmentation or force a positive score. Each $0.35 threshold is an acceptance result. Under a strict profile its $1.060576 admission reservation cannot fit an independently enforced $0.35 call cap; under local estimates actual overshoot remains possible and must fail the result.

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

A closed/absent live profile remains the required state until preparation and the explicit authorization choice are complete. No outcome in this document counts as acceptance.

## Narrow decisions still outstanding

The immediate decision, when requested later, can be only: **authorize the <=$2 strict checkpoint after confirmed credit, or defer it**. It does not require approving local estimates or changing the original plan.

Before diagnosis/MVP, ask one separate concrete decision: retain a genuinely hard provider-bound budget and approve the specified larger admission cap/procedure, or accept the explicitly described local-estimation overshoot risk while keeping the original nominal $0.60 cap. Neither choice lowers actual-cost or scientific acceptance thresholds.

Original C.5 four-round/stop-at-target versus T2.1 six-round/Pareto language, default precision permission versus requested bf16 tier, and s2's two-round fixture issue remain separately documented pending decisions. This package keeps default `until_target` and default precision policy; it does not use this authorization to resolve those disagreements or alter historical evidence.

Sources: `docs/PLAN.md` (T0.4/T1.3/T1.4/T1.12/T2.1), `docs/RUNTIME.md`, `docs/PROMPT_PREFLIGHT.md`, `docs/MODELS.md`, `docs/EVALUATION.md`, `scripts/probe_models.py`, `headroom/runtime.py`, `headroom/llm/admission.py`, `headroom/orchestrator.py`, `headroom/evaluation.py`, and `eval/mvp_phase1.yaml`.
