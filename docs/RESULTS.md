# Results

Measured GPU baselines now cover twelve workloads. The complete 2026-10-24
manifest run reproduced five CUDA OOMs and completed twenty steps in seven workloads.
All captures and cleanup checks passed. This is baseline acceptance, not automated
repair or model-quality evidence.

No authenticated Nemotron repair, main repair benchmark or ablation score has
been measured. Nebius account/key and two minimal chats are now verified; full
capabilities, long-input testing and a larger authorized evaluation budget remain
required. Tavily real API and cache checks have passed.

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
| Minimal live model calls | Super and Nano each returned HTTP200, matched identity and stop | Two short chats only; Ultra/structured output/repair/long-context acceptance pending |
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
- Nebius model probes still await a reviewed live runtime, available credits
  and a confirmed spending boundary. Tavily's separate live probe and research
  component are recorded below; offline model tests and dry runs remain distinct.

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
| Ten original workloads, original two-policy requirement | Explicit matrix support; actual campaign awaits reviewed Nebius runtime | Not measured; current default/strict are equivalent and original wording remains unresolved |
| Full evidence + Ultra | Awaiting reviewed Nebius runtime | Not measured |
| Traceback + memory_summary + Ultra diagnosis | Awaiting reviewed Nebius runtime | Not measured |
| Full evidence + Super diagnosis | Awaiting reviewed Nebius runtime | Not measured |

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
Full T0.4, original long-context/JSON/tools gates and all repair gates remain open.
