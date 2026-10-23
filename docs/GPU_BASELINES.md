# Phase 0 GPU baseline evidence

`check_gpu_baselines.py` collects the original T0.6 full-size baseline evidence.
It is a Phase 0 validation utility, not the Phase 1 Lab implementation. The
original plan and its acceptance requirements are unchanged.

```sh
source scripts/env.sh
uv run python scripts/check_gpu_baselines.py --check-only
uv run python scripts/check_gpu_baselines.py
```

The default run covers eight synthetic scripts plus the pinned nanoGPT
configuration. `--case s1_batch_too_big` restricts collection to that case. No
`--tiny`, alternate provider or reduced batch is used. The current s1 fixture
version is described below; it must not be compared with its old version as a
memory repair.

Before launch it checks a clean pinned nanoGPT checkout, input files, the Lab
image and GPU availability. The resource guard expects a near-empty 24 GiB card
for this baseline calibration and refuses to launch while another compute
process is present. This operational check previously prevented measuring
roughly 3.4 GiB of available capacity as a full-card baseline. The competing
service was subsequently stopped by Frank, and the full default run completed. It does not redefine
any plan acceptance threshold or assert that future workloads always require
exclusive GPU access.

Each target runs in an unprivileged Docker container: no network, read-only
source and dependency mounts, no .env mount or API credentials, bounded host
RAM/CPU/PIDs, and only temporary writable directories. GPU process observations
are recorded during the run. A foreign process or failed inspection invalidates
the observation; only the runner's UUID-named container is stopped or removed.

OOM candidates have a 60-second limit; reclaim cases have a separate 300-second
operational timeout while still requiring exactly 20 completed steps. nanoGPT
has a 180-second operational timeout. A timeout is never a CUDA OOM success.
The runner distinguishes typed CUDA OOM, host/cgroup memory OOM, ordinary errors,
partial evidence, and 20-step completion. Runtime timing is recorded separately
from container cleanup. Cleanup is checked against Docker and GPU process state.

Raw stdout, stderr and per-case JSON remain under runs/phase0-baselines/. A
unique aggregate JSON is saved under reports/. Existing runs are not replaced.
A nanoGPT traceback is created only after a real verified CUDA OOM; an existing
different traceback is preserved and the new one remains in its run directory.

The tool does not edit README measurements, INDEX statuses, or mark T0.6 accepted.
Review the observed default configuration, timings, full traces, step counts,
allocated/reserved peaks and cleanup first. Record measured reclaim peaks in the
corresponding READMEs, then apply every original T0.6 requirement. Later T1.2
snapshot criteria remain separate and unverified.

## Validation evidence

- Before the service was stopped, the occupied GPU caused --check-only to exit
  78 and launch zero workloads.
- CPU-only Docker canaries exercise rejection of CPU OutOfMemoryError and cleanup
  of a timed-out owned container. Their GPU telemetry is synthetic; they do not
  run training or validate GPU baselines.
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

Runtime includes startup and monitoring but excludes cleanup; it is not training
throughput. All three synthetic OOM cases failed within 60 s, all five reclaim
cases completed 20 steps, and all containers were cleaned up. The full nanoGPT
configuration reproduced CUDA OOM with its original traceback. No exact nanoGPT
peak is available from upstream output.

The source reports A/B and raw run directories above are recorded per case in
`reports/t0.6-acceptance.json`. Terminal historical counters measure successful
allocations, not the total demand of an OOM workload. The first preliminary s1
run had startup-only peak values; `reports/gpu-baseline-013012-peak-correction.json`
invalidates those fields while preserving the raw report.

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

This baseline evidence completes only T0.6. T1.1 is accepted separately in
`reports/t1.1-acceptance.json`. No model repair or later T1.2/T2.1 acceptance is
established. In particular, s2 is already below 22 GB and its measured moment/peak
ratio is about 39.963%; s5's large cache gap does not prove harmful fragmentation.
See `docs/RESULTS.md` for the unchanged, unresolved later requirements.
