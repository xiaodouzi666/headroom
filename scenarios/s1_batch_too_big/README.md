# s1 — Batch activations exceed the device budget

**Status: full default GPU baseline measured on 2026-10-23; see the measurement below.**
This intentionally defective training workload passed its T0.6 baseline check.
It is not a repaired result. Execute it only through the isolated, network-disabled Lab.

## Workload and ground truth

A residual token-wise MLP trains on a fixed synthetic regression batch. Default:
32 samples × 2,048 tokens, width 1,024, 12 blocks, float32, SGD without momentum,
20 optimizer steps, seed 7. It has **100,749,312 parameters** by construction.
Every forward block saves expanded GELU/linear activations for backward.
The entire batch is processed at once with no activation checkpointing.
There are no unused filler tensors, duplicated models or downloaded weights.

The intended primary cause is **activations**, rather than optimizer state. Each
expanded activation is 32 × 2,048 × 4,096 × 4 = **1 GiB**; several such tensors can
remain live per block. Twelve blocks are expected to demand more than the 24 GiB
card can hold. This is shape arithmetic, **not an observed allocator peak**.
The measured default run reached CUDA OOM in 5.227 s, satisfying the ≤60-second
baseline requirement. The failed request was 256 MiB; exact historical allocated
and reserved peak counters are recorded below.

## Expected repair classes and constraints

- Checkpoint residual blocks while keeping model shape and the full objective.
- Split the full batch into microbatches and accumulate gradients to preserve its
  effective batch, sample order and optimizer update count.

Shrinking model width/depth, sequence length, the effective batch, or step count
is not an accepted memory repair. A smaller `--batch` is a reference/calibration
input only; equal seed does not make losses from different batch sizes equivalent.
No numerical-equivalence or speed claim has been measured.

## Invocation and output

Inside the Lab sandbox, with no credentials and no network:

```sh
python train.py --device cuda --steps 20
python train.py --device cuda --batch 1 --steps 20
python train.py --device cpu --tiny --steps 20
```

`--tiny` keeps the activation-retaining computation but uses width 32, two blocks,
eight tokens and a default batch of two. It tests plumbing only and is never a
24 GiB acceptance run. All scripts also expose `--seed` (default 7). JSON lines
contain configuration/parameter count, per-step loss and wall time, and CUDA
allocated/reserved/peak bytes when applicable. An OOM emits terminal historical peak counters and propagates with its original
traceback for the Lab to capture. The observed default OOM and peaks are recorded below.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `cuda_oom`;
completed training steps: 0; runtime including container startup
but excluding cleanup: 5.227 s.

- Peak allocated: **23.138748 GiB** (24845041664 bytes).
- Peak reserved: **23.150391 GiB** (24857542656 bytes).
- Source SHA-256: `bd685f1480a2d0d9a5a68af44eaf0f4b325d27f7a1f99ba56d217daae8dd2856`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s1_batch_too_big/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
