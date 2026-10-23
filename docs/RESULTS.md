# Results

T0.6 full-size GPU baseline checks and T1.1 Lab capture acceptance are complete.
No automated repair, model diagnosis, or optimization benchmark result has been
measured. Phase 0 remains
incomplete while account-dependent T0.1/T0.4/T0.5 checks await credentials and
credit/spending confirmation.

## Preparation checks (not benchmark results)

| Check | Observed outcome | Limit |
|---|---|---|
| CUDA toolchain | torch 2.5.1+cu124 recognizes 3090 Ti; snapshot API returns traces | Small allocation only |
| Synthetic scenarios | 8/8 CPU tiny checks completed 20 steps; full GPU baselines below | CPU smoke itself is not GPU acceptance |
| nanoGPT | Pinned source; tiny CPU run exit 0; full GPU CUDA OOM reproduced below | Exact allocator peak unavailable from upstream output |
| Live model/Tavily calls | None | Account, keys, credits and spending boundary pending |

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
- No model-generated repair has been applied, and no numerical-equivalence,
  memory-savings, Pareto, or end-to-end acceptance has been run.
- Account-dependent probes still await credentials, available promotional
  credits and a confirmed spending boundary. Offline probe tests and dry runs
  are not live service feedback.

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
