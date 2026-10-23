# Results

The T0.6 full-size GPU baseline checks are complete. No automated repair, model
diagnosis, or optimization benchmark result has been measured. Phase 0 remains
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

Canonical run: `20261023T013238Z-a16fc6fb`, 2026-10-23 09:32–09:34 Beijing time,
azuki RTX 3090 Ti, torch 2.5.1+cu124. Each workload ran in its own network-disabled
Docker container at the default CUDA dimensions without tiny mode or a reduced
batch. No competing GPU compute process was observed, and cleanup was verified
for all nine containers. Container host-memory OOM was false in all nine cases.

| Scenario | Observed status | Completed steps | Runtime s | Peak allocated GiB | Peak reserved GiB |
|---|---|---:|---:|---:|---:|
| s1_batch_too_big | cuda_oom | 0 | 5.227 | 23.138748 | 23.150391 |
| s2_fp32_adamw_1b | completed_20_steps | 20 | 14.615 | 20.026398 | 20.673828 |
| s3_eval_no_grad_missing | completed_20_steps | 20 | 6.259 | 2.221808 | 2.314453 |
| s4_loss_accumulation_graph | cuda_oom | 12 | 6.260 | 23.147012 | 23.152344 |
| s5_fragmentation_varlen | completed_20_steps | 20 | 9.387 | 4.630246 | 18.419922 |
| s6_full_vocab_logits_fp32 | cuda_oom | 0 | 5.218 | 20.082430 | 20.103516 |
| s7_frozen_params_optimizer_state | completed_20_steps | 20 | 7.311 | 16.549359 | 16.570312 |
| s8_two_models_resident | completed_20_steps | 20 | 9.388 | 2.840601 | 2.851562 |
| nanogpt | cuda_oom | 0 logged training updates | 11.489 | unknown | unknown |

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
`repos/nanogpt.oom.txt` is byte-identical to its raw stderr. These satisfy T0.6
only. No Phase 1 snapshot, diagnosis, patch, verification or search result is
claimed.

Evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`,
`reports/t0.6-acceptance.json`, and raw per-case stdout/stderr/result files under
`runs/phase0-baselines/20261023T013238Z-a16fc6fb/`. Each synthetic source SHA-256 and
exact peak byte values are also recorded in its README and `scenarios/INDEX.yaml`.
Reproduce on an available GPU from the project root:

```sh
source scripts/env.sh
uv run python scripts/check_gpu_baselines.py --check-only
uv run python scripts/check_gpu_baselines.py
```

An earlier s1 run (`20261023T013012Z-466ebd63`) did reproduce OOM, but its original
peak fields contained only startup counters. That raw report is preserved and
invalidated for peak claims by `reports/gpu-baseline-013012-peak-correction.json`.
The canonical run above uses terminal OOM counters and supersedes those fields.

## Unresolved later acceptance requirements

- s2: runtime logs 8,593,605,376 optimizer-state bytes including scalar step
  counters. Two fp32 moments account for 8,593,604,608 bytes from the parameter
  count, approximately 39.963% of the measured allocated peak. T1.2's >=40% snapshot peak-composition requirement is
  not certified. This baseline is already below both 22 GB and 22 GiB, so it
  also does not demonstrate T2.1's required two-round fit:22GB improvement.
- s5: final current reserved minus allocated is 19,358,302,208 bytes; inactive
  split bytes are 760,758,272 and allocation retries are zero. Ordinary cache
  contributes to the gap, so harmful fragmentation remains unproven. This does
  not certify T1.2's snapshot header/fragmentation acceptance.
- No model-generated repair has been applied, and no numerical-equivalence,
  memory-savings, Pareto, or end-to-end acceptance has been run. Original plan
  thresholds remain unchanged; the above conflicts are recorded, not waived.

## CPU source smoke evidence

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

These wall times include container startup and are not training throughput measurements. Sources and commands are in reports/scenario-cpu-smoke-summary.json and its referenced logs. CPU tiny changes model dimensions for plumbing checks only; those runs are not submitted as memory optimization results.

The pinned nanoGPT smoke retains vocabulary 50304 but uses tiny depth/width/sequence/batch to check loading and training in isolation. GPU acceptance uses the separate unmodified baseline configuration in repos/nanogpt.yaml.
