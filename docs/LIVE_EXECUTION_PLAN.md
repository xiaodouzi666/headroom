# Live-model acceptance: authorized gift-credit continuation

Status on 2026-10-25 local: the owner authorized all remaining original-plan model calls using existing gifted credit only, with no recharge and no exceeding that credit. Exact authorization, balance/pricing review, allocations, dispatch claims and receipts are in `reports/live-campaign-20261025/`. This supersedes the earlier narrow three-call permission; it does not change `docs/PLAN.md` or turn failed gates into passes.

## Funding and admission

The fresh account observation is $30.25 including tax; the separate $1 trial is excluded. The working model-token ceiling is $16 including historical calls. A 21% reference tax calculation gives $19.36, leaving $0.89 contingency and at least $10 for judging. This is a conservative allocation, not invoice reconciliation.

- Historical token usage before this campaign: $0.00035096.
- New probes: shared pool $6, never reset per invocation.
- Runtime: all-time pool $9.99964904, including every runtime case and stage.
- Combined UTC-day ceiling: $12. Initial runtime daily limit is $5.99964904 after reserving the full $6 probe pool and historical same-day usage.
- Unknown charges and outstanding claims retain their full bounds. Missing reports or uncertain dispatch stop progression until reviewed. A complete HTTP429 refusal may resume other work after Retry-After and explicit review only while permanently retaining its full verified per-request upper bound; actual cost remains unknown. Transport/identity/bound incidents without that evidence remain stopped.
- No recharge, extra key, or paid service upgrade is authorized.

Exact decimals and evidence are authoritative in `allocation.json` and `funding-review.json`. Refresh balance and official catalogues at stage boundaries; refuse unreviewed price increases, nonzero unsupported fees, identity changes or bounds.

## Original thresholds and the shared hard pool

The original plan defines cost as actual usage times price and requires MVP CLI `--budget 0.6`. Full-context reservation against each individual run was an implementation choice, not an original-plan requirement. The reviewed `actual_usage` mode preserves the CLI and threshold while reserving the complete provider upper bound atomically against shared global/day pools before every dispatch. All roles require verified provider bounds; no local-estimate admission is enabled.

One request can cross the run's actual-cost threshold; the charge is persisted and later calls stop. Above-threshold runs fail cost acceptance and cannot report target success. Reaching the threshold exactly stops calls without inventing an overspend. Unknown billing, identity mismatches or provider-bound violations halt the shared pool across runs/restarts. The default remains strict reservation; runtime activation requires the reviewed profile and regression evidence. Original $0.35 diagnosis/$0.60 MVP/time/accuracy gates remain unchanged.

## Model evidence and probe protocol

The prior checkpoint is retained at `reports/model-checkpoint-20261025/verification.json`: Ultra chat, Super schema and Super tool generation, exactly three requests costing $0.0003143. Earlier Super/Nano chats cost $0.00003666. These receipts are not replayed.

The new four-role capability matrix is complete. JSON and supported switches are adopted only from actual response evidence. Nano tool failure, ineffective `/no_think`, and unproven or ineffective thinking budgets remain visible. Ultra64k/200k/500k succeeded;900k was rate-limited and retains an explicit failed sample. Four-way Super concurrency passed. Installed constants are500029 as the tested server-token lower bound and150000 as evidence budget; final T0.4 receipt is maintained separately.

| Role | Exact model ID | Provider input ceiling | Input/output USD per million |
| --- | --- | ---: | --- |
| Ultra | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1048576 | 1 / 3 |
| Super | `nvidia/nemotron-3-super-120b-a12b` | 262144 | .30 / .90 |
| Nano | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262144 | .06 / .24 |
| Lightning | `nvidia/Nemotron-3_5-Lightning` | 1048576 | .06 / .24 |

Official account prices establish cached input .12/.06/.012/.03. Missing Nano/Lightning catalogue cache prices remain missing; only explicit recorded external-price fallback accepts them. `max_completion_tokens` includes visible and reasoning output.

The probe now compares authenticated catalogues against reviewed price/context/fee bounds before POST. Every process has an exclusive dispatch claim and zero retries. Capability failure and known billing remain separate. Ultra long requests run individually with review between; final Super concurrency intentionally contains four requests. `remaining-plan.json` records exact groups and caps. Sequence: T0.4 staircase/concurrency; T1.3 actual client with real >=200k evidence; T1.4 eight diagnoses; T1.12 nine original-policy repair runs; then remaining original development and acceptance under the same global/day limits.

A successful staircase size is a tested lower bound, not an exact context maximum. Rate-limit errors are not context-limit evidence. HTTP acceptance of a parameter is not proof it works. Failed gates are not hidden by changed fixtures or thresholds.

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

Under the current gift-credit authorization, after capability/credit review, execute one selected
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

Use reviewed full provider bounds against the shared global/day pool. Run thresholds use the reviewed actual_usage mode; no local estimate is authorized. A 220k local preparation does
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

The current authorized execution template, after profile review, is:

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
