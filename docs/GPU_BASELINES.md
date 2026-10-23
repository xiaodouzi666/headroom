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
process is present. This operational check prevents measuring the current
3.4 GiB of available capacity as a full-card baseline. It does not redefine
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

## Validation so far

- The real occupied GPU causes --check-only to exit 78 and launch zero workloads.
- CPU-only Docker canaries exercise rejection of CPU OutOfMemoryError and cleanup
  of a timed-out owned container. Their GPU telemetry is synthetic; they do not
  run training or validate GPU baselines.
- The full GPU path remains unexecuted until the competing process is released.
