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
`--tiny`, model reduction, alternate provider, or reduced batch is used.

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
- The full GPU path executed in canonical run `20261023T013238Z-a16fc6fb` on
  2026-10-23 09:32–09:34 Beijing time, with all nine baseline checks passing.
  Review and README/index recording are captured in `reports/t0.6-acceptance.json`.

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

Runtime includes startup and monitoring but excludes cleanup; it is not training
throughput. All three synthetic OOM cases failed within 60 s, all five reclaim
cases completed 20 steps, and all containers were cleaned up. The full nanoGPT
configuration reproduced CUDA OOM with its original traceback. No exact nanoGPT
peak is available from upstream output.

The canonical source report is `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`;
raw evidence lives under `runs/phase0-baselines/20261023T013238Z-a16fc6fb/`. Terminal
historical counters measure successful allocations, not the total demand of an
OOM workload. The first preliminary s1 run had startup-only peak values; see
`reports/gpu-baseline-013012-peak-correction.json` for their explicit invalidation.
The original file remains preserved.

This completes only T0.6. No model repair or later T1.2/T2.1 acceptance is
established. In particular, s2 is already below 22 GB and its measured moment/peak
ratio is about 39.963%; s5's large cache gap does not prove harmful fragmentation.
See `docs/RESULTS.md` for the unchanged, unresolved later requirements.
