# s1 — Batch activations exceed the device budget

**Status: current full default GPU baseline measured; T0.6 accepted.**
This intentionally defective workload is not repaired. Run it through the
isolated, network-disabled Lab.

## Workload and ground truth

A residual token-wise MLP trains on a fixed synthetic regression batch. Current
defaults are 32 samples × 2048 tokens, width 256, 192 blocks, float32, SGD without
momentum, 20 optimizer steps, and seed 7. It has **101,007,360 parameters**.
Every block retains expanded GELU/linear activations for backward. The full batch
runs at once with no activation checkpointing. There are no filler tensors,
duplicated models, or downloaded weights.

The intended primary cause is **activations**. One expanded activation is
32 × 2048 × 1024 × 4 = **268,435,456 bytes (256 MiB)**; several tensors remain
live per block. This shape arithmetic predicts capacity pressure; it is not a
measured peak or the memory needed to finish the OOM workload.

## Expected repair classes and constraints

- Checkpoint residual blocks while preserving the model and training objective.
- Use microbatches with gradient accumulation, preserving effective batch,
  sample order and optimizer update count.

Shrinking width/depth, sequence length, effective batch or training step count is
not an accepted memory repair. A smaller `--batch` is a reference/calibration input
only; equal seeds do not establish equal objectives across different batch sizes.
No repair, numerical-equivalence or speed improvement has been measured.

## Invocation and output

Inside the Lab, with no credentials and no network:

```sh
python train.py --device cuda --steps 20
python train.py --device cuda --batch 1 --steps 20
python train.py --device cpu --tiny --steps 20
```

`--tiny` uses width 32, two blocks, eight tokens and a default batch of two for
plumbing checks only. JSON lines report configuration, parameter count, per-step
loss/time, and CUDA allocated/reserved/historical peak bytes. CUDA OOM emits
terminal peak counters and preserves the original traceback.

## Current measured default GPU baseline — 2026-10-23

Run `20261023T022519Z-e164c187`, RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, no tiny mode. **cuda_oom**, 0 completed updates,
**4.187 s** including startup/monitoring but excluding cleanup.

- Peak allocated: **23.027313 GiB** (24725389312 bytes).
- Peak reserved: **23.041016 GiB** (24740102144 bytes).
- Source SHA-256: `668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28`.
- No foreign GPU process observed in samples; container cleanup verified.
- Report: `reports/gpu-baseline-20261023T022519Z-e164c187.json`.
- Raw logs: `runs/phase0-baselines/20261023T022519Z-e164c187/s1_batch_too_big/`.

These historical counters cover successful allocations; they exclude the failed
allocation and do not estimate total memory required to finish.

## Fixture version history and separate Lab evidence

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

The formal T1.1 capture in `reports/lab-gpu-acceptance-20261023T022523Z.json`
uses this current source with seed 1337: status `oom`, 2050 device-0 trace events,
`snapshot.pickle` present, positive requested allocation 268,435,456 bytes, and an
`OutOfMemoryError` traceback. This validates Lab capture only; its timing and
instrumented peak are separate from the T0.6 baseline. T1.2 evidence composition,
diagnosis and model repair remain outside this acceptance.
