# Headroom Phase 0 handoff — current snapshot

As of 2026-10-24T22:38:27.854762+00:00 (UTC): **MVP v2 is running; it is not accepted or complete.**
T0.1–T0.6 are accepted under their preserved receipts. T1.3's real client/long-evidence gate and T2.7's independent Docker-contained subprocess comparison are accepted. T1.4 v5 has partial evidence (7/8 first causes and valid references) but full acceptance remains false due to policy/readiness failures. Failed MVP v1 remains failed. The overall original goal is unfinished.

This handoff combines the current Phase 0 summary, Results and Progress snapshots requested by PLAN lines14/102. The embedded files preserve their own historical context: the Phase 0 summary's activation/day-pool/isolation-pending wording and the Results snapshot's “MVP v2 not yet executed” wording predate the now-running v2. They are not the latest run status. Current T2.7 acceptance is reports/t2.7-acceptance-20261025.json; retained billing review is reports/live-campaign-20261025/mvp-v2-cap-budget-review.json. No numerical gate or old failure is changed here.

One historical activation-code value is redacted at both occurrences in the embedded PROGRESS copy, including its promo URL. Original source files are untouched; their hashes below describe the original bytes, not the redacted copy. No credentials, image binaries or snapshots are included. All files remain on azuki; no copy to Mac was made.

Previous handoff preserved byte-for-byte at reports/handoff-phase-0-before-mvp-v2-20261025.md
Previous SHA-256: b8f7789f057ed6a0504827856c44c6204d8f7124b8fbb3218ba723ed8fca15a6

## Included source snapshots

- reports/phase-0-summary.md: 2110 bytes; SHA-256 e52310675ee790ef94ad66ff6e2123a4cb7687c14d31ea1546bda4187d189c44
- docs/RESULTS.md: 24292 bytes; SHA-256 59ad07812b464cde81454e512c07ef0bb1e0dfb238f02f9f9503c2e02014576d
- PROGRESS.md: 42304 bytes; SHA-256 2d719d86096e611c74c979f0540bbf0a349c00d94350239542ff283579e9bc32


---

## BEGIN reports/phase-0-summary.md

# Headroom Phase 0 completion — 2026-10-25

Phase 0 tasks T0.1 through T0.6 are accepted under their saved evidence. All code, tests, captures and credentials remain on azuki. The original plan is unchanged.

T0.4 is now accepted: 60 prescribed model samples were executed, including five historical samples and 55 new ones. Four model IDs and prices were checked against both authenticated official catalogues. Super native JSON and generated tool call passed, as did four concurrent Super chats. Model-control failures remain explicit: Nano tool generation failed, system /no_think did not disable observed reasoning, and thinking-budget parameters are unverified or ineffective.

Ultra exact retrieval succeeded with service-reported inputs of64031,200031 and500029 tokens. The900k sample receivedHTTP429 withRetry-After255, so it is recorded as a rate-limit failure rather than a context-limit finding. No retry occurred.500029 is the largest successful tested input and a lower bound, not the exact maximum. Installed evidence budget is150000; runtime defaults remain disabled until separate activation review.

Known usage-priced cost of all60 samples isUSD0.77289846. One unknown429 charge permanently occupiesUSD1.049344, giving conservative totalUSD1.82224246. These are not invoice totals. The fixed gift-only working pool isUSD16 net, including historical calls; runtime hasUSD9.99964904 all-time and initiallyUSD5.99964904 per UTC day. No recharge occurred.

Key receipts: reports/t0.4-acceptance-20261025.json; reports/live-campaign-20261025/capability-review.json; retained-429-review.json; allocation.json. The current catalogues, dispatch claims, source hashes and per-attempt observations are retained. docs/MODELS.md and docs/FEEDBACK.md contain the factual matrix and limitations.

This completion does not accept Phase1 client/diagnosis/repair or the full project. The existing s2 optimizer fraction39.8715% below40%, original numerical/precision gates, two-round fixture issue, isolated subprocess permissions, owner design/domain/deployment and future-date obligations remain separate.

## END reports/phase-0-summary.md


---

## BEGIN docs/RESULTS.md

# Results

Measured GPU baselines now cover twelve workloads. The complete 2026-10-24
manifest run reproduced five CUDA OOMs and completed twenty steps in seven workloads.
All captures and cleanup checks passed. This is baseline acceptance, not automated
repair or model-quality evidence.

No model-generated repair has yet passed the original acceptance gates, and
there is no accepted main repair benchmark or ablation score. Authenticated
capability probing and the real long-evidence client gate are now complete.
Diagnosis v5 has partial measured success; MVP v1 stopped safely after its first
Nano call. **MVP v2 has not been executed at this documentation snapshot.**
Tavily API/cache component evidence and the independent T2.7 GPU execution-path
comparison have passed. These facts do not substitute for a successful repair.

## 2026-10-25 model and isolation evidence

| Gate | Recorded observation | Acceptance boundary |
|---|---|---|
| T0.4 capability matrix | 60 prescribed samples, including five reused historical samples; Super native schema/tools and four-way concurrency passed; Ultra successful server input up to 500,029 tokens | Matrix execution and recorded results accepted; 500,029 is a tested lower bound, not the exact provider maximum. The 900k probe returned 429 and was not retried; Nano tools and unverified thinking-budget methods remain disabled |
| T1.3 client/router | Super strict schema and Ultra authentic evidence with 268,920 provider input tokens from 53 unique source records; one attempt each | Accepted transport/schema/usage gate; no filler. The free-text Ultra response overclaimed fragmentation, so this is not diagnosis correctness |
| T1.4 diagnosis v5 | 7/8 first-cause matches, 8/8 valid references, eight stop responses with zero reasoning tokens; usage-priced total USD 0.328770 | Full acceptance remains false: s1/s6 contain forbidden proposals, s7 requests more information, and s5 truth remains unverified. The fixed denominator is eight |
| T1.12 MVP v1 | One of nine attempted: real s1 baseline, then one Nano response; no applied repair and eight unexecuted cases | Failed campaign remains preserved. Its unknown actual Nano charge was not treated as zero or retroactively accepted |
| T2.7 isolation parity | Six real CUDA arms: s1, s3 and HF through production Docker and an independent subprocess controller; allocated/reserved peak differences 0% | Accepted original <=1% gate. s3 completed 20 updates in each arm with identical losses; s1 and HF genuinely OOM before the first update, not 20-step successes |

The T0.4 receipt records USD 0.77289846 in known usage-priced charges and
USD 1.049344 permanently retained for the unknown 900k/429 outcome, for a
conservative occupied amount of USD 1.82224246. The T1.3 calls cost
USD 0.0001344 (Super) and USD 0.269367 (Ultra), totaling USD 0.2695014.
These are scoped observations, not an account invoice or additive account-wide
totals; aggregate receipts may already include individual calls.

MVP v1's Nano usage was 3,643 prompt plus 480 completion tokens, with exact
model identity and HTTP 200, but no cache-token count. Its actual charge remains
null. A formal reviewed-retention audit keeps the **original full USD 0.01644864
reservation permanently occupied**. This clears only that reviewed billing
block for future dispatch: the old Store call, report and failed campaign remain
unchanged. At the saved pre-v2 review, runtime known charges were USD 1.37040652
and known-or-retained occupation was USD 1.38685516; the actual total remained
null. These are saved audit values, not a fresh balance reading.

New missing-cache responses can be reported with a verified conservative upper
only after strict identity, tariff, usage, output-cap and ledger settlement checks.
The UI and results keep actual cost unknown, known subtotal separate and the
bound explicit. A verified upper no greater than the original cost threshold
proves that inequality; a larger upper does not prove actual overspending and
cannot certify the threshold. Unreviewed unknown charges still block dispatch.
No original cost, accuracy, numerical or timing gate is lowered.

Sources: [T0.4 receipt](../reports/t0.4-acceptance-20261025.json),
[T1.3 receipt](../reports/t1.3-acceptance-20261025.json),
[diagnosis v5 review](../reports/live-campaign-20261025/diagnosis-attempt4-review.json),
[failed MVP v1 audit](../reports/live-campaign-20261025/mvp-v1-audit.json),
[pre-v2 retained-charge review](../reports/live-campaign-20261025/mvp-v2-cap-budget-review.json),
and [T2.7 independent review](../reports/t2.7-acceptance-20261025.json).
The T2.7 reference runs inside the same Docker isolation envelope, with shared
capture instrumentation/image/source/clock checks; it is not a bare-host backend
or independent allocator instrumentation. It makes no throughput claim.

## Manual GPU verification regression (not model-driven repair)

On 2026-10-24, the new default verifier was exercised on the full-size s3
standalone workload and a **manually authored** one-line `@torch.no_grad()`
evaluation fix. Both ran for 20 optimizer updates in separate network-disabled
Lab containers on the 3090 Ti, seed 1337, with no other GPU process observed.
All captures and cleanup checks passed.

| Measurement | Original | Manual candidate |
|---|---:|---:|
| Peak allocated, decimal GB | 2.435717632 | 0.648419840 |
| Lab optimizer-interval median, ms | 40.896303 | 41.032609 |
| Completed updates | 20 | 20 |
| Parameters | 37,791,744 | 37,791,744 |

Peak reduction was **73.3787%**; the measured optimizer-interval increase was
**0.3333%**. All 20 training losses were identical (`max_loss_delta=0`), and
actual input/target fingerprints, initial parameters and per-update pairing
matched without a caller override. The unchanged reclaim comparison returned
`target_met=true`. These are observed Lab intervals, not an end-to-end training
throughput claim. Initialization hashing is reported separately; it remains
part of total wall time.

Evidence: [manual GPU receipt](../reports/pairing-manual-gpu-20261024T111357Z.json),
with raw source, patch, snapshots and results under
`runs/manual-pairing-gpu-20261024T111357Z/`. The receipt records the exact
reproduction procedure and source hashes. This validates the verifier and new
CUDA instrumentation for one known repair; it contributes **zero model-generated
repair successes** to T1.12/T4.2/T4.3. Automatic pairing remains limited to the
reviewed s3/s4 source contracts; unsupported scripts and old captures remain
unknown. The current verifier evaluates the original C.5 scalar rule without
requiring these optional fingerprints; it reports the comparison basis and
limitations explicitly. Full model-generated T1.6 acceptance remains open.

A later manual command regression exercised `python -O -m train` with a source
outside the pinned pairing contracts. Both 20-update GPU runs had unchanged
parameters and identical observed losses. Allocated peak fell from
2,435,717,632 to 648,419,840 bytes (73.3787%); median optimizer interval moved
from 41.3288 to 40.5021 ms. Pairing remained unknown, and the report used
`original_plan_full_backward_scalar_series` with standard acceptance scope.
See [command-mode GPU receipt](../reports/command-manual-gpu-20261024T113103Z.json).
This also contributes zero model-generated repair successes.

## Preparation checks (not benchmark results)

| Check | Observed outcome | Limit |
|---|---|---|
| CUDA toolchain | torch 2.5.1+cu124 recognizes 3090 Ti; snapshot API returns traces | Small allocation only |
| Synthetic scenarios | 8/8 CPU tiny checks completed 20 steps; full GPU baselines below | CPU smoke itself is not GPU acceptance |
| nanoGPT | Pinned source; tiny CPU run exit 0; full GPU CUDA OOM reproduced below | Exact allocator peak unavailable from upstream output |
| Historical minimal live model calls | Super and Nano each returned HTTP200, matched identity and stop | Two short chats only at that checkpoint; later capability/long-evidence results are recorded above, repair remains unaccepted |
| Tavily | Real search/extract and versioned cache checks passed | Provider-reported credits are separate from account counters |

## T0.6 full default GPU baselines

Current T0.6 evidence is a composition of two measured runs on azuki RTX 3090 Ti,
torch 2.5.1+cu124:

- **A — current s1:** `reports/gpu-baseline-20261023T022519Z-e164c187.json`, measured at 10:25 Beijing time on 2026-10-23.
- **B — unchanged s2–s8 and nanoGPT:** `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`, measured at 09:32–09:34 Beijing time on 2026-10-23.

Each workload used full default CUDA dimensions in its own network-disabled
Docker container. No foreign GPU compute process was observed in the recorded
samples; all nine containers were cleaned up and none was killed by host-memory
OOM. Source hashes in `reports/t0.6-acceptance.json` match all eight current
synthetic scripts. The old s1 entry in source B is historical and excluded from
the current nine-case acceptance.

| Scenario | Source | Observed status | Completed steps | Runtime s | Peak allocated GiB | Peak reserved GiB |
|---|---|---|---:|---:|---:|---:|
| s1_batch_too_big | A | cuda_oom | 0 | 4.187 | 23.027313 | 23.041016 |
| s2_fp32_adamw_1b | B | completed_20_steps | 20 | 14.615 | 20.026398 | 20.673828 |
| s3_eval_no_grad_missing | B | completed_20_steps | 20 | 6.259 | 2.221808 | 2.314453 |
| s4_loss_accumulation_graph | B | cuda_oom | 12 | 6.260 | 23.147012 | 23.152344 |
| s5_fragmentation_varlen | B | completed_20_steps | 20 | 9.387 | 4.630246 | 18.419922 |
| s6_full_vocab_logits_fp32 | B | cuda_oom | 0 | 5.218 | 20.082430 | 20.103516 |
| s7_frozen_params_optimizer_state | B | completed_20_steps | 20 | 7.311 | 16.549359 | 16.570312 |
| s8_two_models_resident | B | completed_20_steps | 20 | 9.388 | 2.840601 | 2.851562 |
| nanogpt | B | cuda_oom | 0 logged updates | 11.489 | unknown | unknown |

Runtime includes container startup and process monitoring, excludes cleanup,
and is not steady-state training throughput. GiB means 2^30 bytes. Synthetic
peaks are terminal PyTorch historical counters for successful allocations; they
do not include a failed allocation or estimate the memory needed to finish an
OOM run. nanoGPT does not emit those counters, so its exact peak is unknown.
Its traceback confirms a 512 MiB request failed during the upstream GELU forward;
no completed training update was logged. Its initial loss evaluation is not a
training update.

The three synthetic OOM cases finished within 60 s; the five reclaim cases
completed exactly 20 updates and have measured peaks in their READMEs. The
pinned nanoGPT source is clean at `3adf61e154c3fe3fca428ad6bc3818b27a3b8291`, and
`repos/nanogpt.oom.txt` is byte-identical to its raw stderr. These baseline measurements satisfy T0.6 only. T1.1 capture evidence is recorded
separately below; no diagnosis, patch, verification or search result is claimed.

Evidence: source reports A/B above, `reports/t0.6-acceptance.json`, and raw
per-case stdout/stderr/result files under their corresponding
`runs/phase0-baselines/<run_id>/` directories. Each synthetic source SHA-256 and
exact peak byte values are recorded in its README and `scenarios/INDEX.yaml`.
Reproduce on an available GPU from the project root:

```sh
source scripts/env.sh
uv run python scripts/check_gpu_baselines.py --check-only
uv run python scripts/check_gpu_baselines.py
```

An earlier s1 run (`20261023T013012Z-466ebd63`) did reproduce OOM, but its original
peak fields contained only startup counters. That raw report is preserved and
invalidated for peak claims by `reports/gpu-baseline-013012-peak-correction.json`.
Both later source runs use terminal OOM counters and supersede those fields.

The adopted s1 fixture now uses width 256 and depth 192 instead of width 1024
and depth 12. Parameters changed from 100,749,312 to 101,007,360 (+0.256129%);
batch 32, sequence length 2048, float32, SGD and the activation root cause remain
unchanged. This fixture calibration increases genuine allocation-history events.
It is a new baseline version, not a model repair, a memory-savings comparison, or
a numerical-equivalence claim. Its source SHA-256 is
`668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28`.
The old source `bd685f1480a2d0d9a5a68af44eaf0f4b325d27f7a1f99ba56d217daae8dd2856`
and source-B s1 result (5.227 s; allocated 24,845,041,664 bytes; reserved
24,857,542,656 bytes) remain historical evidence.


## T1.1 Lab capture acceptance

All original T1.1 clauses are accepted in `reports/t1.1-acceptance.json`, combining
`reports/lab-gpu-acceptance-20261023T022523Z.json` with
`reports/lab-tests-20261023T0212.log` (61 tests passed in 53.15 s).

| Clause | Measured evidence |
|---|---|
| s1 CUDA OOM and snapshot | `oom`; pickle exists; 2050 device-0 trace events > 1000 |
| s1 allocation and traceback | Requested 268,435,456 bytes (0.268435456 GB); traceback contains OutOfMemoryError |
| s3 small-batch completion | Two batch-1, seed-1337 captures each completed 20 updates with 20 losses |
| Determinism | First five s3 losses exactly equal across the two GPU runs |
| Timeout and cleanup | Real infinite loop plus child process; 30-second limit; observed 30.001734 s, TIMEOUT and verified cleanup |
| Credential boundary | Subprocess NEBIUS_API_KEY is null; source/runtime credential files excluded and source read-only |

The 13 GPU report checks are true, all three captures are complete and cleanup
was verified. GPU sharing flags describe recorded samples, not continuous
exclusivity. These results validate the Lab wrapper, not T1.2 peak reconstruction,
a model diagnosis, a repair, or end-to-end acceptance. See `docs/LAB.md` for run
provenance, the binutils symbolizer fix and preserved failed attempts.

## T1.2 evidence-pack implementation and acceptance

The four real Lab captures produce Markdown, structured JSON and PNG timelines.
Their reconstructed physical-block peaks and terminal allocations match native
counters. All source scripts are included in full, with verified hashes, and
each prompt is below the 150,000-token budget. Final regression is 95 passed in 53.54 s (reports/tests-20261023T025427Z-final.log);
Ruff and the actual evidence CLI smoke pass. The final reviewed report is
`reports/t1.2-acceptance.json`; it retains a failed task status.

| Capture | Peak allocated bytes | Optimizer steps marked | Prompt tokens |
|---|---:|---:|---:|
| s1 | 24,750,424,064 | 0 (OOM before first update) | 20,907 |
| s2 | 21,553,250,816 | 20 | 29,970 |
| s4 | 24,768,717,824 | 12 | 29,396 |
| s5 | 5,021,758,464 | 20 | 24,550 |

The Lab captures use seed 1337 and include the capture instrumentation. Their
measurements are separate from the earlier direct T0.6 baselines; their small
differences are not memory improvements.

- **s2 fails the unchanged gate:** optimizer moments at peak are 8,593,604,608
  bytes / 21,553,250,816 bytes = **39.8715009692%**, below 40%.
  Foreach update intermediates remain temporaries; they are not relabeled as
  optimizer state. Scalar step counters are not counted as GPU moment blocks.
- **s4 passes the source-location clause:** actual Top40 includes
  `/source/train.py:107`, the `total_loss += loss` statement. This stack accounts
  for only 512 bytes and is rank 15 of 15. It proves the runtime location,
  not that this small allocation alone caused the retained graph's large footprint.
- **s5 passes the stated header/indicator clause:** terminal reserved minus
  allocated is 19,124,731,904 bytes, and the indicator is `high`. The run has
  no OOM, so `fragmentation_confirmed=false`; harmful fragmentation is unproven.
- OOM positions and the available timestamp-aligned optimizer boundaries are
  drawn at allocator event indices. Missing timestamps are never fabricated.

## Unresolved later acceptance requirements

- T1.2 remains unaccepted because s2 falls below its original >=40% gate.
  No threshold or category has been changed to force a pass.
- The s2 baseline is already below 22 GB. It does not demonstrate T2.1's
  required two-round fit:22GB improvement.
- No authenticated model-generated GPU repair has been demonstrated.
  CPU numerical-pairing checks and offline Pareto/search/report tests exist,
  but do not establish real repaired-GPU memory savings or end-to-end acceptance.
- Capability and long-evidence client gates are accepted as recorded above.
  The reviewed runtime and gifted-credit authorization are available; actual
  repair, main evaluation and ablation acceptance are still pending. No recharge
  or exceeding the shared global/day pools is authorized. Tavily component
  evidence remains distinct from Sources on a complete model-generated repair.

## Historical CPU source smoke evidence

| Scenario | Steps | Process exit | Wall seconds |
|---|---:|---:|---:|
| s1_batch_too_big | 20 | 0 | 4.047 |
| s2_fp32_adamw_1b | 20 | 0 | 4.034 |
| s3_eval_no_grad_missing | 20 | 0 | 4.046 |
| s4_loss_accumulation_graph | 20 | 0 | 3.997 |
| s5_fragmentation_varlen | 20 | 0 | 4.047 |
| s6_full_vocab_logits_fp32 | 20 | 0 | 4.002 |
| s7_frozen_params_optimizer_state | 20 | 0 | 4.047 |
| s8_two_models_resident | 20 | 0 | 4.02 |

This smoke table predates the s1 default-fixture calibration; its tiny dimensions
are unchanged, but it is not a new current-source run. These wall times include container startup and are not training throughput measurements. Sources and commands are in reports/scenario-cpu-smoke-summary.json and its referenced logs. CPU tiny changes model dimensions for plumbing checks only; those runs are not submitted as memory optimization results.

The pinned nanoGPT smoke retains vocabulary 50304 but uses tiny depth/width/sequence/batch to check loading and training in isolation. GPU acceptance uses the separate unmodified baseline configuration in repos/nanogpt.yaml.


## 2026-10-24 complete evaluation baseline pass

Source: [evaluation-baselines-20261024.json](../reports/evaluation-baselines-20261024.json).
Every row links a preserved raw Lab result and source SHA. The manifest's SHA is
`c494865118285ab75a96bf2eeacbc67b1048d962ba5d9ebecadd0ff0d47a637d`. The new ViT and T5 workloads use actual Transformers
implementations with random initialization and synthetic inputs, not pretrained
task-quality tests. HF Trainer's first-step OOM occurs before optimizer state is
initialized; optimizer-state causation is therefore not established by that run.

| Scenario | Actual baseline | Steps | Peak allocated GB | Wall seconds |
|---|---|---:|---:|---:|
| s1_batch_too_big | oom | 0 | 24.750424 | 3.181 |
| s2_fp32_adamw_1b | completed | 20 | 21.553251 | 21.190 |
| s3_eval_no_grad_missing | completed | 20 | 2.435718 | 5.987 |
| s4_loss_accumulation_graph | oom | 12 | 24.768718 | 4.498 |
| s5_fragmentation_varlen | completed | 20 | 5.021758 | 6.885 |
| s6_full_vocab_logits_fp32 | oom | 0 | 21.588380 | 1.437 |
| s7_frozen_params_optimizer_state | completed | 20 | 17.819809 | 6.164 |
| s8_two_models_resident | completed | 20 | 3.100142 | 5.827 |
| nanogpt | oom | 0 | 24.705184 | 8.358 |
| hf_trainer | oom | 0 | 24.805119 | 7.266 |
| vit_random | completed | 20 | 2.082593 | 20.158 |
| t5_random | completed | 20 | 8.042537 | 53.254 |

GB here is decimal bytes / 1e9. Peaks are successful allocations observed by the
Lab; an OOM peak does not estimate total memory required to finish. Wall time is
not steady-state throughput. All twelve runs have capture_complete=true,
cleanup_verified=true and shared_gpu=false in the recorded samples. A lost SSH
attach connection did not restart the campaign; its supervised server process
completed the remaining rows.

### Component evidence, separate from benchmark results

- Parameter capture regression: `reports/lab-gpu-acceptance-20261024T021625Z.json`.
  Real s1 OOM trace and repeated s3 twenty-step loss agreement passed.
- New pinned nanoGPT preparation/Lab path: `reports/nanogpt-lab-baseline-20261024.json`.
- HF Trainer CPU pairing and full GPU OOM: `docs/WATCH_HF.md` and
  `reports/hf-trainer-baseline-20261024.json`.
- Tavily versioned checkpoint/allocator retrieval: `reports/research-component-20261024T022414Z.json`.
  Four live methods reported three credits total; repeated queries had zero API
  calls and zero credits from the local cache. Store contains eight operation rows.
  This does not yet establish Sources on a complete s1/s5 model-driven repair.
- Five imported real baseline replays: `reports/baseline-replays.json`.
  They contain no model diagnosis, patch, repaired after-run or invented agent trace.
- Offline SDK responses, patching, keep/revert and reporting remain separately
  labeled fixtures. They do not enter the main or ablation score table.

### Main and ablation results

| Evaluation | State | Success / diagnosis / cost claims |
|---|---|---|
| Ten original workloads, original two-policy requirement | Runtime available; original full matrix not yet executed | Not measured; current default/strict are equivalent and original wording remains unresolved |
| Full evidence + Ultra | Diagnosis-only v5 and failed first MVP attempt recorded above; no accepted repair main table | No repair success or ablation advantage claimed |
| Traceback + memory_summary + Ultra diagnosis | Not yet executed under a fixed comparable protocol | Not measured |
| Full evidence + Super diagnosis | Not yet executed under a fixed comparable protocol | Not measured |

The evaluator records first-round diagnosis, all failure/unknown charges, source
pins and per-condition evidence provenance. Unverified root-cause labels remain
unscored. No expected ablation advantage is reported as an observed finding.
Original s2 40% and two-round fit acceptance remain unresolved; no gate was lowered.

### Policy-campaign implementation update

The evaluator now records full effective policies per row and supports explicit
`default`, `strict`, and `allow_precision` selections; the default remains a single
policy. `--plan-only` exposes the matrix multiplier and unchanged spend cap without
running workloads or using a provider. The current default and strict policies
both prohibit numerical changes. The optional precision-permitting selection
does not resolve or replace the original T2.8 wording. Aggregate and per-policy
metrics preserve unknown values and scored/comparable denominators. Real
two-policy results, the at-most-three-round optimization study, and the original
target_met >=75%, first-cause agreement >=75%, and USD 12 gates remain unmeasured. See [EVALUATION.md](EVALUATION.md).


## Evaluation application and completion evidence

The campaign table now preserves successful patch/configuration application
separately from the final retained configuration. It reports the selected round,
its verified completion, and per-round candidate outcomes, including reverted
attempts. Missing historical facts stay unknown. Empty source diffs do not
invalidate an applied argv/environment change.

This is reporting functionality, not a new model benchmark. Offline fixtures and
the manually authored GPU regressions above do not add live repair successes.
MVP v1 failed before repair; MVP v2 is not yet executed. Accepted main evaluation
and ablation results remain pending.

## First Token Factory connectivity measurements — not repair results

Evidence: reports/tokenfactory-minimal-20261024.json, source commit269efd0.
Both official authenticated catalogues returned200. One chat each ran on US:

| Role | Prompt tokens | Completion tokens | Total seconds | Usage-priced estimate USD |
|---|---:|---:|---:|---:|
| Super | 23 | 19 | 0.670570 | 0.000024 |
| Nano | 23 | 47 | 1.506663 | 0.00001266 |

Both finish_reason=stop, identity matched, no retry, max_completion_tokens=128.
Total0.00003666USD; with21% tax reserve0.0000443586USD. Pricing uses ordinary
input conservatively and is not an independently reconciled invoice. These are
single observations, not model speed benchmarks or completed repair scores.
At that historical checkpoint all later gates remained open. T0.4 and T1.3 are
now accepted with the limitations recorded above; original repair gates remain
open. This historical two-chat record is not rewritten as later acceptance.

## END docs/RESULTS.md


---

## BEGIN PROGRESS.md

# Headroom Progress

Initialized: 2026-10-23T00:44:58.397951+00:00
Canonical plan: docs/PLAN.md (v4.2, preserved verbatim).
All work, caches, runs, and media remain on azuki.

## Tasks

| Task | Description | Status | Evidence |
|---|---|---|---|
| T0.1 | 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min） | 已验收 | reports/t0.1-acceptance-promo-20261024.json; official promo face25USD redeemed, UI30.25USD incl.tax; current matching key/0600/env and both authenticated catalogues200 with4/5Nemotron models; public Apache2 and retained live Tavily proof verified; further inference authorization remains separate |
| T0.2 | 服务器环境勘察（P0，~30min） | 已验收 | docs/ENV.md; reports/env-preflight.json; Docker GPU ok, NET ok, 5694.85 GiB free; shared GPU and no sudo recorded |
| T0.3 | 仓库骨架与工具链（P0，~40min） | 已验收 | reports/toolchain-checks.json; reports/pre-commit-t0.3.log; commit ca6c86ad099c519b92d1ccb88219b08450aa8da6, Frank author/committer, pushed origin/main |
| T0.4 | Token Factory 探测（P0，~1h） | 已验收（失败/未支持项保留） | reports/t0.4-acceptance-20261025.json; all60 prescribed samples executed; Ultra500029 provider tokens verified,900k429 retained; Super JSON/tools/concurrency pass; config500029/150000/json_schema/chat_template_kwargs,8 new feedback entries; Nano tools and thinking-budget failures disabled |
| T0.5 | Tavily 探测（P1，~15min） | 已验收 | reports/t0.5-acceptance.json; live exit0, 4/4 operations, 2 factual FEEDBACK entries, observed schema; API total3 credits matches UI3/1000 |
| T0.6 | 场景集 v0（P0，~2h） | 已验收 | reports/t0.6-acceptance.json; 3 synthetic CUDA OOM <7s, 5 reclaim completed20 steps with measured README peaks; pinned nanoGPT CUDA OOM11.489s; all cleanup verified |
| T1.1 | Lab 包装器：运行并抓证据（P0，~3h） | 原验收保留；绝对截止及部分证据GPU增强通过 | reports/t1.1-acceptance.json retains original checks; reports/deadline-manual-gpu-20261024T131612Z.json verifies shared hard deadline, natural/small-timeout full captures, stress timeout explicit partial, canonical s3 twice20updates; no invented inference training steps |
| T1.2 | 证据包生成（P0，~3h） | 实现完成，验收未通过 | reports/t1.2-acceptance.json; s1/s2/s4/s5 artifacts and real peak replay verified; s2 optimizer-state fraction 39.8715% < original 40% |
| T1.3 | LLM 客户端与路由（P0，~1.5h） | 已验收 | reports/t1.3-acceptance-20261025.json; actual client/router Super schema passed; authentic53-record Ultra evidence returned268920 server input tokens; both1attempt/exact ID/known cost total0.2695014USD; free-text fragmentation overclaim recorded, not diagnosis acceptance |
| T1.4 | Diagnose（Ultra）（P0，~2.5h） | 首因7/8及全部引用有效；完整验收未通过 | reports/live-campaign-20261025/diagnosis-attempt4-review.json; v5八次真实响应stop/0 reasoning，cost0.328770USD；s1/s6禁止改动及s7需补充信息保留；原6/8与政策门未改 |
| T1.5 | Patch（Super）与应用（P0，~2.5h） | 实现及离线验收完成；真实补丁待办 | docs/PATCH.md; git apply, compile, bounded repair and policy tests; real Super/GPU cases pending |
| T1.6 | Verify 与比较（P0，~2h） | 运行时精度识别、原计划数值比较及GPU回归通过；模型修复验收待办 | docs/VERIFY.md; FP32/BF16 observation selects original 1e-3/2e-2 tolerance, unknown retains stricter bound; actual dtype change requires policy; 20-update GPU proof retained |
| T1.7 | 单轮编排 + 存储 + 事件（P0，~2h） | 主流程与存储已实现并离线联调 | docs/SEARCH.md; SQLite ordered events, partial reports, SDK fixture pipeline; live two-call gate pending |
| T1.8 | 报告（P0，~1.5h） | 报告、选中配置及数字追溯通过 | docs/STORAGE_REPORTS.md; selected round argv/environment/manifest and patch downloads, explicit CLI-only/empty diff; real repaired report pending |
| T1.9 | 真实仓库：nanoGPT（P0，~2h） | 仓库命令重跑与无参考n/a接线完成；真实修复待办 | reports/nanogpt-lab-baseline-20261024.json; actual repair/22GB/diff/cost gates pending |
| T1.10 | Honesty 与安全（P0，~1h） | 静态与CPU真实性检查通过；完整修复待办 | docs/PATCH.md; model shrink/truncation/escape checks and observed parameter counts |
| T1.11 | Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h） | 自有Python镜像、干净目录CPU及隔离组件通过 | docs/LAB_RUNTIME.md; hash-locked image-owned Python3.12, verified immutable image ID, no host venv mount; clean candidate tree script/module each3updates with capture/cleanup verified |
| T1.12 | MVP 整体验收 + 报告（P0，~1.5h，10/24 晚） | 首轮MVP安全停止，真实修复未验收 | reports/live-campaign-20261025/mvp-v1-audit.json; s1真实GPU基线后Nano缺缓存计数，账本保留0.01644864USD上界并阻断后续；1/9尝试、8未执行，无修复成功 |
| T2.1 | 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h） | 有界搜索与逐轮验证反馈完成；真实验收待办 | docs/SEARCH.md; selected state survives revert; per-round verification-feedback.json exposes actual loss/check/error facts to later rounds; original s2/bf16 policy gates unchanged |
| T2.2 | Tavily Research（P0，~2h） | 原生Super工具循环已接入并离线验证；模型实测待办 | reports/research-tool-loop-20261024/receipt.json; model chooses search/extract with preserved IDs and actual Sources; run-wide5 model turns/4 tool slots; original Tavily component live proof retained, one Super native tool-generation fixture passed in model-checkpoint-20261025; full multi-turn research acceptance pending |
| T2.3 | Nano 栈标注（P1，~1h） | 来源绑定及预算内证据/报告/UI接线完成；实测待办 | docs/NANO_ANNOTATIONS.md; model opinions separate from measurements; optional failure retains original evidence; historical real capture plus14 synthetic offline labels passed without changing source; eight-case accuracy/cost gate pending |
| T2.4 | 预算守卫与成本面板（P0，~45min） | 保守上界费用处理与定向验证通过；真实多轮验收待办 | reports/bounded-billing-20261025/receipt.json and bounded-billing-reporting-20261025/receipt.json; oldNano actual=null/full0.01644864 retained after explicit reviewed-retention audit; runtime conservative1.38685516USD/known1.37040652USD, remaining8.61279388USD; unknown unreviewed still stops dispatch; .05/.1/live<=1.2 gates pending |
| T2.5 | HF Transformers 场景（P1，~2h） | HF场景CPU/GPU基线通过；修复待办 | reports/hf-trainer-baseline-20261024.json; real Trainer OOM; configuration-only repair gate pending |
| T2.6 | Watch 模式（P2，~1.5h） | shell/Python启动器可定位唯一CUDA OOM子进程并重跑；真实模型修复验收待办 | docs/WATCH_HF.md; preserved multi-process inventory and selected capture binding; exact target replay; manual real GPU helper+s1 OOM selected correctly; candidate/reference each20updates passed; duplicate/OOM ambiguity and root failures rejected; no host fallback |
| T2.7 | Docker/HF 缓存稳健性（P1）：验收：三个场景在 Docker 路径下结果与子进程路径一致（峰值差 ≤ 1%）。 | 已验收 | reports/t2.7-acceptance-20261025.json; six actual GPU arms independently audited; s1/s3/HF allocated/reserved peak differences 0% <=1%; s3 both20updates/identical losses, s1/HF genuineOOM; Docker-contained independent subprocess controller, source/image/seed/capture/cleanup verified; original hostEPERM retained |
| T2.8 | 小评测 + 自优化（P0，可夜间自治，~4h） | 显式策略矩阵与离线统计完成；原真实验收待办 | docs/EVALUATION.md; default/strict 实际等价，allow_precision 必须显式选择；全矩阵共享预算，逐行完整 Policy；原两档歧义、≤3轮优化、target_met/首因各≥75% 和 $12 实测均未关闭 |
| T3.1 | FastAPI + SSE（P0，~3h） | API队列/SSE/选中轮次下载已实现并测 | docs/API.md; selected round after PNG/JSON and configuration manifest; missing selected evidence never falls back to stale files; existing ownership/nofollow/deadline rules retained |
| T3.2 | 前端素版（P0，~4h） | 费用上界显示及前端回归通过；真实修复流程待办 | 68 frontend tests/typecheck/build passed; actual unknown stays unknown with separate conservative upper; desktop/mobile and Lighthouse must be refreshed against current build and genuine repair evidence |
| T3.3 | Replay（P0，~1.5h） | 5条真实基线回放可用；规定修复回放待办 | reports/baseline-replays.json; explicitly baseline-only; s2 two-round/nanoGPT/reclaim repair replay not fabricated |
| T3.4 | Claude Design 对齐（P1，~3h；设计稿 10/25–10/26 由 Frank+Claude 产出到 `design/`） | 待Frank设计稿与认可 | No design package has been supplied; theme implementation exists |
| T3.5 | 公网部署、限流、监控（P0，~2.5h；Frank 提供域名/Cloudflare） | 默认关闭的告警投递已实现；公网/真实收件待办 | docs/DEPLOYMENT.md; explicit HTTPS webhook, durable incident/attempt state, bounded retry, identical idempotent payload and unknown delivery; 57 guarded tests and systemd template verification; no channel configured or service/timer installed |
| T3.6 | 预录素材（P0，~1h） | 8张真实基线UI素材完成；完整修复素材待办 | docs/media/ui-20261024T025659Z-baseline-only; baseline-only labels, desktop/mobile Home/Results/About/Run; no repaired before-after/diagnosis/diff fabricated |
| T4.1 | 评测集定稿 | 基线范围已验收 | reports/evaluation-baselines-20261024.json; all12 matches, 5 OOM/7 completed20, full capture/cleanup; source pins |
| T4.2 | 主评测 | 工具与表格已准备；真实主评测待办 | docs/EVALUATION.md; docs/RESULTS.md; Nebius live model run required |
| T4.3 | 消融 | 三条件消融工具完成；实测待办 | full Ultra / traceback+summary Ultra / full Super; no predicted gain presented as measured |
| T4.4 | 冻结 | 待真实评测后冻结 | No v0.9-eval tag created before acceptance |
| T5.1 | README | 五命令Quickstart与干净目录CPU通过；真实repair待办 | README.md; locked Python3.12 and self-contained Lab image; reports/portable-lab-20261024 proves script/module capture without local .venv/.env; clean-clone live fix remains pending |
| T5.2 | docs 定稿 | 文档初稿完成；评审与真实模型反馈待办 | docs/ARCHITECTURE.md; RESULTS.md; FEEDBACK.md; no fabricated model experience |
| T5.3 | Devpost 描述 | Devpost本地草稿完成；未保存表单 | docs/DEVPOST.md; owner final review/submission pending |
| T5.4 | 视频 | 视频脚本完成；待真实修复与录制 | docs/VIDEO_SCRIPT.md; <=2:50 storyboard, actual evidence required |
| T5.5 | 首次完整提交 | 未开始 | — |
| T5.6 | 评委视角自检 | 当前就绪审阅完成；发布前复检待办 | reports/submission-readiness-20261024.md; actual repair, public demo/video and submission gate remain pending |
| T5.7 | 最终提交 | 未开始 | — |
| Phase 6 | Weekly health/alerts; balance by Nov 25; manual Dec 1 and Dec 8 access | 未开始 | Future dated acceptance |

## Next acceptance and remaining deliverables

- The dedicated T1.3/T1.4 drivers and PLAN A5 / T2.2 native model tool loop are implemented. Real historical inputs have been prepared and independently hash-checked; this does not accept model capability, token usage, diagnosis accuracy or repair success.
- The owner authorizes remaining original-plan model work using existing gifted credit only, with no recharge/overrun. reports/live-campaign-20261025 records authorization, allocation and the enabled actual_usage profile with verified provider global/day reservations. All60 original T0.4 samples are finalized with failures retained; Ultra900k429 permanently occupies1.049344USD under the completed conservative continuation review. Runtime all-time/current UTC2026-10-24 daily ceiling is9.99964904USD, including spent usage; combined external probe plus maximum runtime day total11.82189150USD remains below12. No unknown charge is treated as zero. T1.3 is accepted; latest T1.4 v5 is7/8 exact first causes with8/8 valid references but incomplete policy/readiness. Its0.328770USD calls are known; subsequent MVP Nano missing-cache usage retained0.01644864USD and halted the runtime. Earlier v2/v3/v4 failures remain preserved.
- Keep original failed gates and procedure conflicts visible: s2's 39.8715% optimizer fraction versus40%, default precision policy/bf16 tier. T2.7 isolation comparison is now accepted with its Docker-contained reference boundary.
- T1.12 reporting is now implemented and verified with retained offline pipeline artifacts. The nine real model-generated repairs, accuracy, budget and timing requirements still need actual execution.
- T3.5 / Phase6 webhook delivery is implemented but disabled. The owner must select/authorize a real destination and supply public domain/Cloudflare access before deployment and delivery acceptance; no recipient message or unit installation has occurred.
- Current requirement-by-requirement source audit found no additional independently implementable feature gap at1452d27; see reports/readiness-after-outcomes-20261024.md. This does not establish full acceptance or release readiness. Owner design, genuine repair replay/media, final review/video/submission and future dated uptime checks remain separately open.
- No original threshold is lowered, no old run is replaced, and no evaluation/release tag is created before acceptance.

## Acceptance log

- 2026-10-24T21:22:45.657445+00:00: T0.4 accepted from all60 actual prescribed samples (55 new,5 historical); Ultra64k/200k/500k exact retrieval succeeded,900k hit429 and was not retried. Super4 concurrency passed. Installed tested input lower bound500029 and evidence budget150000; no exact-maximum claim. Known usage-priced total0.77289846USD, plus permanent unknown upper1.049344USD gives conservative occupied1.82224246USD. Native schema and template reasoning chosen; Nano tools and unproven thinking-budget methods disabled. Original PLAN unchanged; T1.3/T1.4/repair gates remain separate.

- 2026-10-24T20:43:13.008906+00:00: completed the authorized first model capability checkpoint: exactly1 Ultra chat,1 Super native json_schema,1 Super generated add tool call; HTTP200/exact identity/complete usage, no retries or unresolved charges. Token cost0.0003143USD;21% reference0.000380303USD, not reconciled invoice. Account remained Active with rounded30.25USD incl.tax balance and separate1USD trial. Catalogue prices/context/fees were manually compared before each dispatch; current probe code does not enforce that comparison itself. No Tavily/GPU/repair/runtime activation or recharge. Three-call authorization fully consumed; full T0.4/T1.3/MVP and original failed gates remain open. Evidence: reports/model-checkpoint-20261025/verification.json.

- 2026-10-24T14:54:54.961187+00:00: completed T0.1 account/credit gate: official received25USD promo redeemed in the existing Token Factory organization, refreshed transaction shows AI Builder Program Credits +30.25USD including tax, trial separately1USD. Existing console/server key mask matches, both fresh official GET catalogues200 with4/5Nemotron models, private0600 ignored env and public Apache2 repository verified; prior accepted live Tavily evidence retained. No card top-up, new key/terms or new model/Tavily/GPU work. First1.25USD token/2USD total checkpoint requested, not yet authorized; live profile remains absent. Promo-arrival heartbeat paused after fulfillment. Reports: reports/promo-redemption-20261024.json and reports/t0.1-acceptance-promo-20261024.json. Full goal remains active.

- 2026-10-24T14:43:16.949374+00:00: completed original T1.12 actual patch/config application, selected configuration completion and per-round facts through JSON/Markdown/curated API/UI; reverts retain application facts and ambiguous evidence remains unknown. Default-disabled T3.5/Phase6 HTTPS notification delivery now has durable incident state, bounded retry and safe unknown-delivery handling. Full guarded backend1583passed473.96s; all148 source hashes unchanged and current; frontend66passed/typecheck/build. Four retained offline pipeline outcomes and actual desktop/390px browser layout verified; live score count remains0. Health unit templates validate but are not installed or enabled. New model/Tavily calls/GPU workloads/notifications/cost0; live runtime profile absent; original PLAN/gates unchanged. Reports: reports/outcomes-monitoring-20261024/verification.json and reports/handoff-outcomes-monitoring-20261024.md. Full goal remains active; current requirement audit and external acceptance are separate.

- 2026-10-24T14:23:27.338609+00:00: implemented dedicated T1.3/T1.4 prepare/execute acceptance drivers over the actual client/router and shared durable ledger, plus native Super/Tavily tool calling in production search. Independent audit rebuilt authentic s2 evidence byte-for-byte from53 original records (222428 local content tokens), verified all8 diagnosis packages and unchanged source captures; local counts/fixtures do not accept live model gates. Full guarded backend1485passed472.39s; source hashes unchanged and rechecked. Localhost preview health and baseline downloads200; no frontend changes or new frontend suite claimed. New model/Tavily calls/GPU runs/cost0; live profile absent, original PLAN/gates unchanged. Reports: reports/acceptance-integration-20261024/verification.json and reports/handoff-acceptance-integration-20261024.md. Remaining independent gaps: original MVP patch-application/completed columns and default-disabled health notifier delivery. Full goal remains active.

- 2026-10-24T13:56:31.488370+00:00: connected actual bounded round verification feedback, source-bound budgeted Nano opinions in evidence/report/UI, coherent optional-publication recovery and download locators, and pinned bitsandbytes research routing. Final guarded backend1387passed456.37s with unchanged sources; frontend51passed/typecheck/build. Historical real baseline plus14 synthetic offline labels retained all measurements and original hashes; this is not live model accuracy. Initial missing-env failures and interrupted review-fix run preserved. New model-inference/Tavily calls/GPU workloads/cost0; no live profile, PLAN or original gate changes. Reports: reports/diagnostic-context-20261024/verification.json and reports/handoff-diagnostic-context-20261024.md. Genuine client/diagnosis acceptance drivers and model Tavily tool loop remain independently implementable. Full goal remains active.

- 2026-10-24T13:25:14.043559+00:00: portable image now owns Python3.12/hash-locked CUDA dependencies and runs by verified immutable image ID; clean candidate tree with no .venv/.env passed script/module CPU capture. Shared absolute hard deadline and durable partial-first finalization retain timeout facts without inventing success; actual GPU natural/small-timeout complete, continuous stress explicitly partial, and two canonical s3 runs completed20 with deterministic first5 losses. Selected-round after evidence/configuration downloads and report/UI execution metadata fixed; CLI-only empty patch distinguished. Full guarded backend1344passed450.83s with unchanged sources; frontend50passed/typecheck/build and historical browser compatibility verified. Initial GPU serialization failure preserved. New model calls/cost0; no live profile/PLAN/gate changes. Reports: reports/portable-delivery-20261024/verification.json and reports/handoff-portable-lab-20261024.md. Full goal remains active.

- 2026-10-24 bounded Pareto continuation: explicit until_target/bounded_pareto across CLI/YAML/API/Watch/evaluation/UI; default stops at first verified target, bounded stays within <=6 rounds and unchanged policy/budget/deadline. Later revert/budget/error retains selected patch/metrics/verification together; fresh-evidence loss clears stale after image. Search metadata distinguishes baseline goal, first verified target and exploration termination. Cross-mode ablation pairs are excluded; missing historical mode remains unknown. Full guarded backend1266passed322.07s with unchanged sources; frontend47passed/typecheck/build and browser baseline-only display verified. Ruff/precommit/gitleaks passed. Reports: reports/bounded-pareto-20261024/verification.json and reports/handoff-bounded-pareto-20261024.md. New model calls/cost0; no new GPU workload, no live runtime profile. All original failed/external gates remain open.

- 2026-10-24T12:33:06.435709+00:00: multi-process wrappers now select a unique CUDA OOM target and replay the same entrypoint for candidate/reference while preserving all raw captures and wrapper exit semantics. Explicit Ultra local-estimate admission is separate from verified bounds/actual usage; unknown billing persists and blocks further dispatch; default strict/live-disabled retained. Full guarded backend1186tests passed315.96s with source unchanged; frontend42tests/build passed. Real GPU helper+s1 baseline OOM, candidate/reference20updates,101007360parameters, exact compared losses and selected child snapshot peak passed; manual change earns zero model benchmark credit. The first full run found a real concurrent WAL initialization race (1failed1166passed), now fixed with bounded pre-transaction retry and preserved logs. Local preview refreshed; no new model calls/cost or original PLAN change. See reports/multicapture-admission-20261024/verification.json. Full goal remains active; bounded Pareto exploration remains independently implementable.

- 2026-10-24T12:04:28.000883+00:00: runtime precision observation now selects original FP32/BF16 tolerance and records actual precision changes; shell launchers with one mapped Python target preserve wrapper/cwd/module while replaying patched target arguments. Guarded full backend1100tests passed257.33s with source hashes unchanged; frontend39tests/build passed. Actual CUDA FP32/BF16 runs each completed20updates/20losses, observed change and2% tolerance verified (max delta0.0001003146). Stable s2 diagnostic copy explains foreach temporary peak but does not replace canonical acceptance. No new model calls/cost, profile enablement or PLAN changes. Evidence reports/precision-wrapper-20261024/verification.json.

- 2026-10-24T11:37:25.038903+00:00: restored the retained original scalar-loss contract instead of unapproved global pairing gates; optional pairing remains evidence. Added scoped repository no-reference n/a acceptance, CLI/YAML policy controls, exact Python flags/module replay through baseline/candidate/reference/Watch/API/evaluation, and separate nine-case MVP20% reclaim targets (general default30% unchanged). Guarded full backend1035tests passed with unchanged source hashes; frontend39tests/typecheck/build passed. Manual non-pinned Python module GPU regression completed20updates twice,73.3787%peak saving, identical observed losses and unknown pairing; zero model benchmark credit. Local preview refreshed; six-hour read-only promo follow-up installed. New model cost0, no recharge/public submission, PLAN bytes unchanged. Full goal remains active; see reports/original-plan-contract-20261024/verification.json.

- 2026-10-24 11:18UTC: original-goal continuation closed concrete production gaps: explicit diagnosis information requests stop after one call (including empty plan), reclaim planning uses remaining reduction against the fixed original30% target, per-round stored diffs/verification remain visible after revert, curated Results campaigns and measured/unknown summaries/paired-ablation Markdown are implemented. Automatic pairing now derives actual tensor/initial-parameter/per-update evidence for bounded s3/s4 contracts; other sources and historical captures remain unknown. Full guarded backend923tests passed160.25s with unchanged source hashes; frontend38tests/typecheck/build passed. Two full-size manual s3 GPU runs verified20updates, unchanged37,791,744parameters, exact loss equality,73.3787%peak reduction and0.3333%optimizer-interval increase; no model generated this repair and it contributes zero model benchmark successes. No additional model charge, recharge, public port, submission, or original PLAN/gate change. See reports/plan-completion-20261024/verification.json and reports/handoff-plan-completion-20261024.md. Original full goal remains incomplete.

- 2026-10-24T10:54:58.477225+00:00: continuation completed the explicit model output cap/exact Nano ID, CPU-only complete-request audit, shared600s admission deadline, owned preparation cleanup including supervisor death, report-ready SSE, cached read-only availability/local budget, and the host-versus-reviewed HF cache separation. Full guarded backend859tests passed142.74s with source hashes unchanged; frontend33tests/typecheck/build passed on Node24.22.1; four real15s health polls stayed fresh and browser baseline report links worked. Reports: continuation-validation-20261024.json and handoff-continuation-20261024.md. Earlier18 CPU failures, Node startup failure and stale-preview observations remain preserved. Minimal Super/Nano calls are the only new model inference; no further billing, GPU repair, public deployment or submission was performed. Original PLAN/gates remain unchanged.

- 2026-10-24 10:24UTC: user confirmed private key setup and explicitly authorized only up to0.10USD trial credit for minimal connectivity. Both official catalogue GETs succeeded; one Super and one Nano chat each returned200/stop with exact identity, valid usage, zero retries and no cap violation. Usage-priced total0.00003666USD, with21% tax reserve0.0000443586USD; not an invoice reconciliation. Evidence reports/tokenfactory-minimal-20261024.json. No Ultra/full evaluation or recharge authorized; live runtime remains disabled. User also requests continued original-goal development and later use of promotional credits when they arrive. Original PLAN and failed gates remain unchanged.

- 2026-10-24 full-development checkpoint: final backend718tests passed107.57s; frontend27tests/typecheck/build passed; Home Lighthouse90/90/90 and real baseline Run89/98/89. Twelve actual GPU baselines matched5OOM/7completed20 with capture and cleanup verified. Full source-hash receipt: reports/final-validation-20261024.json; handoff: reports/handoff-development-20261024.md. Real Research added3credits; refreshed Tavily total6/1000,994remain, pay-as-you-go off. Nebius key/profile absent; no authenticated Nebius inference or recharge performed. All original failed gates retained.

- 2026-10-24: Frank explicitly requests full original-plan development, continuing every implementable part while only genuinely Nebius-dependent work waits. Implement later components with honest offline/real-evidence verification; retain original acceptance gates and existing failures. Self-funded Token Factory availability is being researched; no payment or paid inference has been authorized by that question.

- 2026-10-24 00:57 UTC: Frank completed hidden-input Tavily import; private .env preflight passed. The authorized four-operation live probe exited0; basic/advanced searches and both exact-URL extracts succeeded. Report: reports/probe-tavily-20261024T005720856027Z-332161bd.json. Two factual feedback entries (TAVILY-001/002) and observed TOOLS schemas are now recorded; independent read-only review confirmed API checks. Full T0.5 acceptance: reports/t0.5-acceptance.json.
- Account usage was independently refreshed before and after this run: free-plan used credits moved0 to3/1000, matching API total3;997 remain, pay-as-you-go and auto-upgrade are off, and the UI says requests stop at plan limit. Evidence: reports/tavily-account-after-20261024T005808Z.json. The two extract responses reporting0 do not prove future extraction is free. Nebius remains deferred/unverified; no model calls or other task acceptance is implied.

- 2026-10-24 offline continuation completed: reports/api-prep-20261023T222659Z.json records 259 passed in53.97s, Ruff and formatting passed, and the default model-probe dry-run planned62 operations with network_requests=0 and accepted=false. New coverage includes55 guarded probe tests,82 LLM client/router/cost tests,25 diagnosis checks and2 SDK/schema/evidence integration tests. Full prior tests remain green; historical runs are preserved. Original PLAN SHA remains e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.
- Independent review fixed native-versus-fenced JSON classification, retry dispatch after a shared budget violation, absolute streaming deadlines, nonfinite JSON, malformed SDK responses missing accounting, and response model identity. Missing or mismatched identity cannot become accepted capability/diagnosis; uncertain billing stays unknown and model probes halt further paid dispatch. T0.4/T1.3/T1.4 remain unaccepted pending real model calls.
- Test-isolation incident retained: an earlier AsyncClient refactor round attempted three official-endpoint transports using only a fixed dummy credential; exact network outcomes are unknown. No real key or .env was used by those tests. Corrected mocks and independent DNS/socket-denial guards passed, including separate reviewer checks. See docs/MODELS.md; do not describe the whole development turn as zero network.
- Historical pre-import credential check (superseded by the verified Tavily import above): server .env was0600; Tavily and Nebius values were empty. Hidden-input Tavily importer syntax validated. No authenticated model/search probe was run; the Tavily four-operation live check remains pending import, and Nebius registration/credit troubleshooting remains deferred at Frank's request.

- 2026-10-24: Frank asked to defer the Nebius registration/credit issue and start previously account-dependent work. Proceed with T0.4/T1.3 offline preparation and T1.4 schema/prompt checks while keeping their live acceptance pending. This sequencing instruction does not waive T1.2, numerical, loop, or cost gates.
- Tavily live UI preflight: Researcher Free, 0/1000 credits used, pay-as-you-go and auto-upgrade off; requests stop at plan limit. Evidence: reports/account-status-20261023T221833Z.json. Existing default key remains in the browser; server import is pending because computer-use access to Terminal was denied. User was given a hidden-input SSH importer; no key was printed, no new key was created, and no paid setting was changed.

- T1.2 final review: reports/t1.2-acceptance.json retains accepted=false. All four real evidence bundles are present, their true peak/terminal replay matches native counters, full source hashes match, budgets pass, and OOM PNGs are visually checked. Nine of ten scenario checks pass; s2 optimizer moments are 8,593,604,608 / 21,553,250,816 bytes =39.8715009692%, below the unchanged40% gate. s4 actual Top40 train.py:107 stack is512 bytes; s5 high denotes a19.125GB cache-gap proxy, not confirmed harmful fragmentation.
- Final regression: reports/tests-20261023T025427Z-final.log, 95 passed in53.54s; exact invocation in reports/tests-latest-final.json. Ruff check and format passed; real evidence CLI smoke passed. No live API calls were made.

- T1.1: all original GPU checks passed in reports/lab-gpu-acceptance-20261023T022523Z.json; s1 CUDA OOM with2050 device0 trace events, valid pickle/native JSON, positive request and traceback; s3 twice completed20 with20 losses and exact first5 equality. 61 tests passed in53.15s including real30s timeout and child cleanup, secret isolation, AdamW step hooks, command capture and symbolizer dependency. CLI CPU smoke reached5 controlled steps.

- T0.6 s1 calibration: original width1024/depth12 baseline produced268 trace events underLab, below unchanged T1.1>1000. Width256/depth192 uses101007360 real parameters(+0.256%); batch32/seq2048/SGD and activation root cause unchanged, no filler. New source separately verified in reports/gpu-baseline-20261023T022519Z-e164c187.json; new model version is never compared to old as a repair. Old evidence retained.

- Lab corrections retained with failing evidence: Docker29 lowercase absence text initially caused false cleanup-unverified; fixed case-insensitive exact-owned-container checks. Old image lackedaddr2line; fullC++symbolization failed stoi, fixedbybinutils in image54accb9f... with fullstack capture unchanged. Initial reports/lab-gpu-acceptance-20261023T020307Z-failed.json and020718.json retained.

- 2026-10-23: Frank reports the GPU service stopped and asks to continue other work while he registers accounts. Proceed with API-independent Lab implementation; T0.1/T0.4/T0.5 remain pending, and all original acceptance criteria remain unchanged. No paid call has been authorized by this sequencing instruction.

- T0.6 accepted: `uv run python scripts/check_gpu_baselines.py` exit0, canonical run20261023T013238Z-a16fc6fb launched9 full GPU workloads. All source hashes and raw results independently checked. README allocated/reserved peaks recorded for all8; INDEX provenance updated; nanoGPT.oom.txt matches raw traceback. See reports/t0.6-acceptance.json. No later snapshot/repair criteria certified.

- 2026-10-23T01:29Z: Frank stopped the competing service. Live check: no compute processes, 24055 MiB free, baseline guard ready=true. Full GPU T0.6 calibration resumed. First s1 run reproduced typed CUDA OOM in 5.235s with verified cleanup; its startup-only peak fields are invalidated by reports/gpu-baseline-013012-peak-correction.json. OOM terminal counter instrumentation added before the canonical rerun.

- T0.6 runner preparation: scripts/check_gpu_baselines.py and docs/GPU_BASELINES.md collect full-size default GPU baselines in Docker, distinguish CUDA OOM/host OOM/error/timeout, and retain raw evidence. Actual `--check-only` returned 78 with workloads_launched=0 while the known competing process was still present (historical check). CPU-only Docker canaries: `uv run pytest -q tests/test_phase0_baseline_failures.py` passed 2/2 in 6.19s (reports/phase0-baseline-canaries.log): CPU OOM is rejected; timeout cleans up the owned container. At that preparation checkpoint the full GPU path was unexecuted; it was subsequently verified by the canonical run above.

- T0.6 historical CPU preparation checkpoint: eight source fixtures + README + INDEX prepared. `uv run python scripts/check_scenario_smoke.py` (two four-case batches) completed 20 CPU tiny steps in all 8 cases; evidence reports/scenario-cpu-smoke-summary.json and per-batch logs. This is not GPU baseline acceptance. nanoGPT pinned at 3adf61e154c3fe3fca428ad6bc3818b27a3b8291, deterministic synthetic inputs prepared, original upstream CPU tiny run exit 0 (upstream max_iters=20 emits iterations 0 through 20). At that checkpoint no full-size GPU OOM trace or peak measurement existed; the later canonical run supplies both. Live model calls and repairs remain unverified.

- T0.3: `uv run python scripts/verify_toolchain.py` exit 0: torch 2.5.1+cu124, CUDA True, NVIDIA GeForce RTX 3090 Ti; snapshot True True; .env ignored and mode 600. `uv run pre-commit run --all-files`: all three hooks Passed. `gitleaks detect` and staged scan: 0 findings. Commit ca6c86ad099c519b92d1ccb88219b08450aa8da6 author and committer both match existing Frank identity; push origin/main succeeded.

- T0.2: `python3 scripts/inspect_env.py` exit 0. All checks retain original stdout/stderr/exit code. DOCKER_GPU=ok; NET=ok; disk=5694.85 GiB. Existing other compute process is noted. sudo requires password; uv/gitleaks not initially installed.
- T0.1: public https://github.com/xiaodouzi666/headroom created with Apache-2.0; server .env initialized with empty keys, permissions 600, gitignored. PLAN SHA-256 matches attachment e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.

- Bootstrap: SSH verified; project did not exist; git identity is already configured; gh authenticated as xiaodouzi666; repository did not exist.

## 待 Frank 决策

- Ultra admission: the reviewed profile is now enabled in explicit actual_usage mode; an8192-output diagnosis still reserves the full1.073152USD verified provider bound in global/day pools, while the original0.35/0.60USD actual-cost acceptance thresholds remain unchanged. A settled call can cross its actual run threshold and must then fail/stop; the provider bound is not a minimum charge or a promise of per-call0.35USD worst-case cost. Current runtime all-time/day allocations and prior charges are recorded in reports/live-campaign-20261025. The optional local_estimate mode remains distinct and is not used for the active strict shared pool. No further authorization is pending for already authorized original-plan work within gifted credit; recharge/overrun and threshold changes remain unauthorized.

- T1.2: s2 optimizer-state peak fraction is39.8715%, below original40%; task remains unaccepted. Its baseline also already fits22GB, so later T2.1 two-round acceptance remains unresolved. Preserve these results for the requested later discussion; no threshold or fixture changes made to force a pass. A separate foreach=False diagnostic copy now has stable runtime hashes,49.4149464840% optimizer fraction and20 matched losses (max delta2.384185791e-7); reports/s2-optimizer-diagnostic-20261024 records it. Canonical/history unchanged; this is not acceptance or a model-generated repair.

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. The initial permission denial was not bypassed. Frank subsequently stopped it; GPU availability and all T0.6 baselines were verified on 2026-10-23 at09:29–09:34 Beijing time. Evidence: reports/gpu-release.json.

- Historical limited checkpoints remain preserved: two trial-connectivity chats and the later three-call Ultra/Super checkpoint (0.0003143USD) consumed their original scopes. Subsequent explicit authorization now covers remaining original-plan calls using existing gifted credit only, with no recharge/overrun; see reports/live-campaign-20261025/authorization.json. The >=25USD credit gate is accepted from the redeemed25USD face promo/30.25USD gross adjustment. Current spending is bounded by the shared allocation, not inferred from an account balance or card availability.

## Frank 待办

- Devpost: registration and an existing project draft were observed in the logged-in browser on 2026-10-24; final project submission remains pending.
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=[redacted] ; activation code [redacted] ($25); Builders Program https://dev.nebius.com/builders (additional $25). NEBIUS_API_KEY is now privately configured and authenticated. Promo credit >=$25 is now verified in reports/promo-redemption-20261024.json; remaining original-plan spending is authorized within existing gifted credit and the reviewed allocation; no recharge/overrun.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.

- 2026-10-24T22:00:00+00:00: frozen regression1726passed501.32s with208 tracked/nonignored non-Markdown source hashes unchanged (production prompt Markdown was excluded from this historical inventory; next final inventory will include it). v4 diagnosis then returned8 complete JSON responses withstop/0 reported reasoning and7/8 first-cause agreement at0.327699USD; full acceptance remainsfalse because policy/reference validation rejected plans and a genuine workspace/model-shrink text false positive was found. Preservedv2/v3/v4 packages; matcher and request-schema repairs are being integrated without changing original thresholds. Local preview restarted with explicit reviewed profile;health200/configuredtrue/GPUavailable, no UI run submitted.

- 2026-10-24T22:12:48.407604+00:00: T1.4 v5 completed8 single calls,7/8 first causes,8/8 valid refs,0.328770USD known; full gate stillfalse. First actualMVP campaign stopped after s1 GPU baseline and one Nano response: exactidentity200/3643input/480output but cachecountmissing means actualcostunknown. Full0.01644864USD provider bound retained; no retry/remaining8cases dispatched. Runtime known1.37040652USD, external unknown900k1.049344USD unchanged. Read-only audit retained at reports/live-campaign-20261025/mvp-v1-audit.json. Fee-bound continuation is being implemented with independent review, not bypassed.

- 2026-10-24T22:26:44.941692+00:00: reviewed historical Nano retention completed with no new requests; actual remains unknown and original0.01644864 bound remains charged. Old MVP campaign bytes unchanged. T2.7 six-arm raw GPU audit accepted, all peak differences0%, independent receipt2044c67c26f9782e16c1d360802191e742ae8d245194005c4645d464a38574e3. Final guarded full regression running on233 frozen source files including production prompts; no full-suite success claimed yet.

- 2026-10-24T22:33:53.118136+00:00: full guarded regression1977passed549.80s (driver551.38s),233 production/config/test source files unchanged during execution, including production prompt Markdown; PLAN and network/env guard unchanged. Frontend68 tests/typecheck/build passed. Reports-only style fixes preserve original runner bytes in .py.original.txt with SHA mapping; Ruff check/format and git diff check pass. Local preview restarted with current runtime profile, health200/configuredtrue/GPUavailable and billing complete conservative1.38685516USD/remaining8.61279388USD. Historical private MVP ID is not in default preview Store and returned Run not found; no run UI acceptance is claimed from that lookup.

## END PROGRESS.md
