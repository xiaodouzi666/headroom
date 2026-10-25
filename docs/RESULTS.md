# Results

Measured GPU baselines now cover twelve workloads. The complete 2026-10-24
manifest run reproduced five CUDA OOMs and completed twenty steps in seven workloads.
All captures and cleanup checks passed. This is baseline acceptance, not automated
repair or model-quality evidence.

The latest completed authorized extension, MVP v6, passed one target out of nine.
Its s3 model-generated repair completed 20 updates, reduced peak memory by
73.378694%, and preserved all recorded losses and parameter count. The original
overall MVP gate remains failed (minimum six targets); raw first-cause matches
are 7/9, or six correct, one invalid and two unknown with the validity gate.
All nine literal CLI execution chains were verified: one exit 0, eight exit 78.
V1–v5 failures remain preserved. The owner authorized three additional iterations
v5/v6/v7; final v7 is integrated and undergoing full regression before live testing.
Main evaluation, ablations and complete project acceptance remain pending.
Capability/client, Tavily component and T2.7 isolation evidence do not substitute
for these remaining gates. See the versioned v6 summary and latest phase summary.

## 2026-10-25 model and isolation evidence

| Gate | Recorded observation | Acceptance boundary |
|---|---|---|
| T0.4 capability matrix | 60 prescribed samples, including five reused historical samples; Super native schema/tools and four-way concurrency passed; Ultra successful server input up to 500,029 tokens | Matrix execution and recorded results accepted; 500,029 is a tested lower bound, not the exact provider maximum or proof of a request at the advertised 1M context. The 900k probe returned 429 and was not retried; its unknown charge remains retained. Nano tools and unverified thinking-budget methods remain disabled |
| T1.3 client/router | Super strict schema and Ultra authentic evidence with 268,920 provider input tokens from 53 unique source records; one attempt each | Accepted transport/schema/usage gate; no filler. The free-text Ultra response overclaimed fragmentation, so this is not diagnosis correctness |
| T1.4 diagnosis v5 | 7/8 first-cause matches, 8/8 valid references, eight stop responses with zero reasoning tokens; usage-priced total USD 0.328770 | Full acceptance remains false: s1/s6 contain forbidden proposals, s7 requests more information, and s5 truth remains unverified. The fixed denominator is eight |
| T1.12 MVP v1 | One of nine attempted: real s1 baseline, then one Nano response; no applied repair and eight unexecuted cases | Failed campaign remains preserved. Its unknown actual Nano charge was not treated as zero or retroactively accepted |
| T1.12 MVP v2 | s1: 22 model calls, 16 Super attempts (10 file-count rejections, six truncation/filtered responses), zero apply/compile/candidate runs; eight later cases stopped at runtime readiness | Not accepted: target success 0/9, first-cause match one with eight unobserved. The eight admission skips are not model quality failures |
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

## MVP v2: real protocol failure before candidate execution

The campaign completed with exit 1. All nine harness workers exited 0 and wrote
reports; that process evidence does not mean successful repair. Only s1 ran the
model/GPU pipeline: one genuine CUDA OOM baseline (24.750424064 allocated GB),
22 model calls (Nano 1, Ultra 5, Super 16), and 283.708064 seconds including
campaign cleanup. Its first cause was activations, matching the authored label,
but target_met=false and there is no selected patch or after-run.

Four patch rounds produced 16 attempts: ten rejected with “diff must touch
between one and twenty files”, and six rejected as truncated/filtered responses.
No attempt reached git apply or py_compile, and no candidate GPU/verification
run occurred. The fifth diagnosis requested more information. Candidate loss
equivalence, parameter equality and memory savings are unmeasured, not failures
of an executed candidate. The original any-applied aggregate remains unknown
where evidence is missing; no nonexistent final patch is manufactured.

For six Super responses completion reached 4000: five also reported 4000
reasoning tokens, and one reported 3962. The ten old raw diff payloads were not
saved, so their error cannot uniquely identify missing headers, escaped newlines
or explanation-only output. An independent standard-diff check accepted both
ordinary unified diff and a matching optional git header; separate malformed
inputs reproduced the same file-count error. There is no evidence of an
inherent prompt/parser format contradiction.

The parent disabled future admission after seeing the common protocol failure.
s2–s8 and nanoGPT therefore produced runtime_not_ready/needs_human reports with
zero model calls and zero GPU runs. They remain in the unchanged nine-case
acceptance denominator, but must not be called eight model quality failures.
The reviewed profile was restored after the campaign ended; this operation did
not change the ledger or regrade any result.

s1 actual cost is still null: known subtotal USD 0.14104766 plus formally
verified Nano upper USD 0.00025122 gives conservative upper **USD 0.14129888**.
The upper certifies the original <=0.6 cost gate; it does not establish exact
actual spend or compensate for target failure. The saved post-v2 ledger review
records known USD 1.51145418, conservative occupation USD 1.52815404 and
remaining runtime pool USD 8.47149500. These are historical local-ledger values,
not a refreshed account balance or invoice.

At the pre-v3 checkpoint, the common patch/fixer fix had been applied:
explicit reasoning=False with the original 4000 cap, clearer existing diff
instructions, and bounded private visible-response evidence. That production-tree
targeted integration passed 294 guarded tests. **At that checkpoint the next
live run had not yet been tested; it subsequently failed as recorded in MVP v3
below.** The earlier 1977 backend/68 frontend results validated the committed
5d3093c baseline, not the then-new protocol revision.

The later line-array protocol revision passed [2026 production regression
tests](../reports/patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json),
with 236 source/config/test/production-prompt hashes unchanged during execution.
This is a separate regression checkpoint, not retroactive evidence for an older
run or a real repair acceptance.

Evidence: [v2 audit](../reports/live-campaign-20261025/mvp-v2-audit.json),
[operational classification](../reports/live-campaign-20261025/mvp-v2-operational-audit-note.json),
[repair findings](../reports/live-campaign-20261025/mvp-v2-repair-findings.md),
[restored-profile ledger snapshot](../reports/live-campaign-20261025/mvp-v2-profile-restored.json),
[standard diff contract](../reports/unified-diff-contract-20261025.json),
[non-unique error controls](../reports/unified-diff-contract-20261025-supplement.json),
and [applied revision](../reports/super-patch-fix-20261025/application.json).
The original failed v1/v2 artifacts remain unchanged.

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
- MVP v6 demonstrates one authenticated model-generated GPU repair (s3),
  with the original gates preserved. That single success does not establish
  overall MVP, main benchmark or ablation acceptance.
- Capability and long-evidence client gates are accepted as recorded above.
  The reviewed runtime and gifted-credit authorization are available; actual
  overall repair, main evaluation and ablation acceptance are still pending. No recharge
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
| Full evidence + Ultra | Latest completed MVP v6: 1/9 targets; 7 raw / 6 valid first causes. Versioned MVP trials are not a fixed-protocol main benchmark | One s3 repair verified; no main benchmark or ablation advantage claimed |
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
MVP v1, v2 and v3 failed before an accepted repair; the eight later v2 cases
were operational skips. Accepted main evaluation and ablation results remain
pending. Historical v4 failed with target0/9; v6 later passed s3 only (1/9 overall). Both records are preserved below.

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

## MVP v3 — second repair iteration, failed (2026-10-25)

Source commit: 1a935c8716cee05edf2b1ad1d3e37d35f52a5ef3. Original nine-case manifest and thresholds were unchanged. All nine harness child workers recorded worker_exit_code=0 and cleanup_verified=true in matching campaign/report timing records; this is not a CLI fix invocation. The campaign exited1 because the original success gate failed. Five cases ran with models; four later cases were operational admission stops with zero GPU/model work, not four observed model-quality failures. Fixed denominator: target0/9; first cause3/9 true,1/9 false,5/9 unknown.

| Scenario | First cause | Target | Model calls | Cost upper USD | Wall seconds | Outcome |
|---|---:|---:|---:|---:|---:|---|
| s1_batch_too_big | yes | false | 27 | 0.12610878 | 83.213 | diagnosis_needs_more_info |
| s2_fp32_adamw_1b | yes | false | 7 | 0.07339602 | 57.965 | diagnosis_needs_more_info |
| s3_eval_no_grad_missing | no | false | 8 | 0.08762380 | 44.520 | diagnosis_supplement_exhausted |
| s4_loss_accumulation_graph | yes | false | 31 | 0.16205718 | 96.722 | max_rounds_reached |
| s5_fragmentation_varlen | unknown | false | 5 | 0.05945934 | 34.306 | diagnosis_needs_more_info |
| s6_full_vocab_logits_fp32 | unknown | false | 0 | n/a (no calls) | 0.954 | runtime_not_ready |
| s7_frozen_params_optimizer_state | unknown | false | 0 | n/a (no calls) | 0.930 | runtime_not_ready |
| s8_two_models_resident | unknown | false | 0 | n/a (no calls) | 0.922 | runtime_not_ready |
| nanogpt | unknown | false | 0 | n/a (no calls) | 1.061 | runtime_not_ready |

Across54 Super responses, all finish=stop and reported reasoning_tokens=0. Fifty-two nonempty diff strings had no physical linefeeds and were rejected before application; a separate empty diff was rejected as NO_CHANGE. The other empty-diff CLI-only proposal was statically accepted but the actual s5 candidate rejected its unsupported --grad_accum_steps=4 argument (SystemExit2). Thus git-apply-plus-compile success=0 and verified repair success=0. Workflow status completed on s4 means loop completion only.

Exactly78 model calls were joined to their authoritative budget attempts: known0.50587762USD plus5 settled Nano missing-cache bounds0.00276750USD yields conservative0.50864512USD; actual total remains null. As of the saved post-v3 ledger snapshot at 2026-10-24T23:01:44.356938Z, runtime cumulative conservative2.03679916USD left7.96284988USD under the unchanged9.99964904USD allocation. This is a historical local-ledger reading, not the current balance or an invoice. Historical unknown reservations remain occupied.

Evidence: reports/live-campaign-20261025/mvp-v3-audit-v2.json; mvp-v3-repair-review.json; mvp-v3-repair-findings.md; mvp-v3-protocol-stop.json; mvp-v3-profile-restored.json. At this v3 checkpoint, final original repair iteration3 was being prepared. That v4 iteration subsequently failed; its final evidence is appended below.


## MVP v4 — final third repair iteration, failed

**结论：MVP 未通过，完整 goal 尚未完成。** 九个原定场景均真实执行，目标达成 **0/9**（原门至少6/9），首因命中 **7/9**（另2项unknown，不从分母剔除）。本轮是初次MVP之后的第3次修复迭代；原 PLAN §0.6 的修复轮数已用完，停止进一步修复试错，等待 Frank 决定是否扩展轮数。账号、密钥和赠送额度已就绪，不是本次停止原因。

实现/评测来源：78a83df86b181674c37509b192517a9d4101ad92。全部代码、依赖、GPU数据和媒体在azuki；Mac仅接收本报告。原PLAN、9场景、精度策略、阈值和失败历史均未改动。本轮结束于2026-10-24T23:31:55.358346+00:00，driver退出1，总墙钟735.240秒。

## 九场景结果

下表的“候选”与“最终选中”分开：s1有实际候选但OOM后revert；s8第2轮keep，后续失败不覆盖它，保留一个未达目标的小改善。其余没有验证成功的候选。completed工作流状态仅表示搜索结束。

| 场景 | 原标签 / 诊断首因 | 首因命中 | apply+compile | 候选完成 | 最终选中轮 | target |
|---|---|---|---|---|---|---|
| s1_batch_too_big | activations / activations | 是 | 1 | 否 | 无 | false |
| s2_fp32_adamw_1b | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s3_eval_no_grad_missing | activations / activations | 是 | 0 | 未执行 | 无 | false |
| s4_loss_accumulation_graph | retained_graph / retained_graph | 是 | 0 | 未执行 | 无 | false |
| s5_fragmentation_varlen | fragmentation_candidate / activations | unknown | 0 | 未执行 | 无 | false |
| s6_full_vocab_logits_fp32 | temporaries / temporaries | 是 | 0 | 未执行 | 无 | false |
| s7_frozen_params_optimizer_state | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s8_two_models_resident | params / params | 是 | 1 | 是 | 2 | false |
| nanogpt | unknown / activations | unknown | 0 | 未执行 | 无 | false |

## 峰值、数值、费用与时长

GB使用十进制字节/1e9。after仅列最终选中配置，不用失败候选冒充修复结果。费用“≤”表示已核验保守上界，actual仍为null；无“≤”为完整usage-priced已知费用，不是独立核销发票。

| 场景 | peak before GB | selected after GB | 降幅% | step时间变化% | 数值状态 | 调用数 | 模型费用USD | 秒 |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| s1_batch_too_big | 24.750424064 | — | — | — | unknown | 28 | ≤0.12634370 | 91.948 |
| s2_fp32_adamw_1b | 21.553250816 | — | — | — | unknown | 8 | 0.068768988 | 54.264 |
| s3_eval_no_grad_missing | 2.435717632 | — | — | — | unknown | 34 | 0.192787128 | 139.395 |
| s4_loss_accumulation_graph | 24.768717824 | — | — | — | unknown | 34 | 0.175681208 | 128.276 |
| s5_fragmentation_varlen | 5.021758464 | — | — | — | unknown | 19 | 0.112660608 | 112.125 |
| s6_full_vocab_logits_fp32 | 21.588379648 | — | — | — | unknown | 2 | ≤0.03223954 | 18.110 |
| s7_frozen_params_optimizer_state | 17.819808768 | — | — | — | unknown | 23 | ≤0.11876024 | 88.777 |
| s8_two_models_resident | 3.100141568 | 2.989897728 | 3.556091 | 0.941755 | identical | 14 | ≤0.12185840 | 62.184 |
| nanogpt | 24.705183744 | — | — | — | unknown | 3 | ≤0.09073224 | 39.175 |

s1第3轮实际应用并编译，但仍OOM、0训练步，peak=24.750424064GB，loss=n/a，参数量未变。s8第2轮完成20步，peak从3.100141568降至2.989897728GB，仅3.556090507%（要求20%）；记录的backward标量loss序列identical，原口径numerical_acceptance=true，但same_inputs/effective_batch/objective仍unknown，不能扩写为新的配对数值等价证明。s8实际step时间增加约0.941755%，throughput gate通过。

本轮165次模型调用：已知小计1.037464332USD，加5条Nano可核验上界0.00236772USD，保守合计1.039832052USD；实际总额null。9项均≤0.60USD且≤480秒。campaign.summary.known_cost_usd=0.549897932仅汇总4个总费用完全已知run；另外5个bounded run内的已知调用0.487566400USD也属于已知小计，不能遗漏。

## 原验收门逐项状态

- T1.5：8个合成场景中仅2个有真实git apply命令/direct fallback及compile0，低于6/8；所有patch轮均初稿+最多3次fixer，Super调用均≤4000 completion tokens。direct fallback不冒充三方合并成功。
- T1.6：s1未完成；s3未产生候选，30%降幅门未通过。旧手工/负例GPU与单元测试证据保留，不充当模型修复成绩。
- T1.7：s1有49事件、28模型调用及所需事件顺序；但本次通过eval worker调用核心流程，字面headroom fix命令未观察。九个worker均exit0不等于九个CLI exit0；根据已核对状态推导CLI码为0,78,0,0,78,78,78,78,78。
- T1.8：九份JSON/Markdown报告均存在、均≥7个二级标题；实际scripts/check_report_numbers.py逐份运行9/9通过。唯一最终选中patch的独立apply-check收尾证据见mvp-v4-s8-selected-apply-check.json；没有选中patch的八项为n/a。
- T1.9：nanoGPT无候选、fit22未通过，loss unknown；≤0.8USD费用门单独成立，不能替代MVP≤0.6门或22GB门。
- T1.12：报告/来源/清理/费用/时长门成立；目标0/9和真实CLI入口门未通过，不能进入“已验收”。
- T2.2：真实模型工具循环形成9条research记录、8次API、7个记录credits；s4成功提取匹配PyTorch2.5的checkpoint文档，s5命中s3缓存且API/credits均0。但原要求的s1 checkpoint Sources与s5 CUDA memory Sources均缺，完整门未过。
- T2.3：8场景仅4项完整标注；这4项40个可评分栈中仅3个类别与启发式一致，其他4项失败不能被剔除。每项费用上界≤0.02成立，完整覆盖/≥80%一致率门未过。

## Top 3失败模式与已经做过的调整

1. **补丁结构仍不可靠。** v2的reasoning耗尽已通过显式reasoning=False处理；v3的无换行字符串已改成diff_lines并保留原响应与规范diff。v4共110次patch尝试：88格式/安全拒绝、19应用失败、1响应拒绝、2应用编译成功。109个非空diff中107个被拒，另1个响应形态unknown。实证包括缺前缀、hunk计数不符、复制展示行号及缺少上下文；JSON合法不代表可应用。
2. **静态成功不保证有效修改执行路径。** s1零context hunks把代码追加到main调用/异常分支之后，原forward仍OOM。s8先在GPU创建teacher再搬到CPU，保留小幅改善但未消除先前峰值。真实Lab与keep/revert正确保留失败或不足目标的事实；没有手工替模型写场景答案。
3. **诊断/证据附属门仍有缺口。** 多项搜索以needs_more_info结束；Nano出现标签覆盖/类别不一致；Tavily虽有真实调用和缓存，指定Sources未齐。s2原39.8715%<40%、已fit22却要求两轮才fit22、默认禁精度变化却要求bf16档等原计划冲突仍需逐项讨论。

## 模型、服务与验证体验

T0.4全部60项探测已执行并保留失败；Ultra实测500029输入token成功，900k返回429，其未知1.049344USD上界继续占用，不宣称完整1M请求成功或精确最大上下文。T1.3真实53记录/268920输入token通过。独立诊断v5首因7/8且引用8/8有效，但完整政策/计划门未过。Super通用docstring组件最终经正常fixer应用/编译通过，只证明组件，不计MVP成功。Nano缺cache split时actual保持null，独立核验上界；Tavily工具与费用记录见上。

当前源码完整回归2026 passed（551.34秒），运行期间236项源/配置/测试/生产prompt哈希不变；后续仅泄密扫描器精确非秘密哈希例外发生配置变化，生产代码/测试/prompt未变。前端68测试、typecheck、build既有结果保留，未伪称本次重跑。当前Home单次Lighthouse99，390px无横向溢出；这不是浏览器实时修复验收。T2.7三场景六GPU臂峰值差0%，独立Popen控制器在Docker内、共享采集协议，宿主EPERM历史保留。

## 赠送额度与后续预算

截至最终财务复核，总账298次attempt全部结算、46个run全部关闭，无pending/unresolved/halt。runtime已知3.056058592USD，保守3.077893672USD；既定9.99964904USD runtime池剩6.921755368USD。加外部探测保守占用1.82224246USD，总净保守占用4.900136132USD；21%税预留后5.92916471972USD。这是内部保守核算，非账户实扣/发票，也不使用旧UI余额当现时余额。原16USD净总包络、税/备用与10USD评审储备未调整；未充值、未转移未用探测池，历史未知费用未释放。

## Phase 2建议与必须由Frank决定的下一步

先解决MVP补丁可靠性，再做完整Phase2与主表/消融。只读提案mvp-v4-next-repair-options.md给出三项具体方案：有界结构化格式错误反馈；将原文与展示行号分离并验证基线hash/精确旧块锚点；验证实际应用位置与锚点一致。全部保留原数值、参数量、吞吐、4000token和每patch三次修复门，不预写场景答案。方案尚未实施。

原docs/PLAN.md第41行：若未达标，“最多再修3轮，仍不达标则停下等Frank”。v1初次失败、v2/v3/v4三次修复均已保留。当前需要的是是否允许追加有界MVP修复轮数，不是重新索要已授权的赠送额度调用许可；本次不自行开始第4轮或更改阈值。

真实五条规定修复回放、浏览器完整运行、HF修复、Watch真实修复、10×2/12主评测与消融仍未通过。设计稿/还原认可、域名/Cloudflare和告警收件渠道、视频/Devpost最终提交及未来日期在线检查仍各有独立门。没有发布evaluation/release标签、公开服务或提交比赛。

## 证据与交付

- 原campaign：runs/evaluation/live/20261024T231940915002Z-2098d11d/campaign.json（私有原始运行）。
- 固定九项：reports/live-campaign-20261025/mvp-v4-audit-v2.json。
- 费用/CLI：同目录mvp-v4-finance-review.json、mvp-v4-cli-exit-semantics.json。
- 候选与子门：同目录mvp-v4-candidate-verification-review.json、mvp-v4-candidate-verification-supplement.json。
- 报告数字：同目录mvp-v4-report-number-checks.json；选中patch：mvp-v4-s8-selected-apply-check.json。
- 后续提案：同目录mvp-v4-next-repair-options.md；完整未完成门：reports/final-decision-20261025.md。
- 当前完整回归：reports/patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json。
- 本任务既有localhost preview已重启加载78a83df，health/Home200，无UI提交；mvp-v4-final-source-check.json与final-preview-restart.json保留收尾证据。
- 最终handoff合并本页、RESULTS和PROGRESS，纯文本小于1MiB。提交前扫描/交付状态单独记录；原失败和旧summary保留。

## MVP v5 — 2026-10-25

Original target gate:0/9. First-category match:7/9 (2 unknown); unchanged auditor also requires valid diagnosis, giving6 true/1 false/2 unknown.17/52 patch attempts applied/compiled with independently verified source-byte chains;5/8 synthetic scenes had an applied candidate. s4 completed20 steps and reduced measured peak89.769367%, but the original scalar-loss check compared batch1 reference with batch8 candidate and rejected it. No final configuration selected. All nine scenes executed; PLAN and manifest unchanged. Details: reports/phase-1-summary-20261025-mvp-v5.md.

98 calls: all-call known$0.89236424, verified bounded remainder$0.00460392, conservative$0.89696816, actual-total null. Campaign known0 is its fully-known-run-only subtotal, not all-call known cost. Real CLI invocation still not observed in v5.

## MVP v6 — fixed-nine live evaluation, 2026-10-25

Source765b64d; original9 executed,1target(s3),6valid firstcauses/1invalid/2unknown. s3:20updates,2.435717632→0.64841984GB (73.378694%),identicalloss,maxdelta0,params37791744unchanged,CLI0,finalpatchclean-reapplybytesmatch. OthersCLI78;all9literalexecutionchainsverified. 32calls knownsubtotal0.531157108USD,verifiedboundedremainder0.00419238,conservative0.535349488;actualtotalunknown. No changedthresholds, no recharge. Full details: reports/phase-1-summary-20261025-mvp-v6.md.

V7 quality checkpoint: full guarded backend 2,218 passed in 560.90s; 247 source entries and original PLAN/guard unchanged, no skips. This is software regression evidence; the final nine-case live result is pending.
