# s1 — Batch activations exceed the device budget

**Status: source prepared; GPU baseline, runtime and peak are unmeasured.**
This is an intentionally defective training workload, not a measured result or a
passed T0.6 acceptance. Execute it only through the isolated, network-disabled Lab.

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
Expected peak: reaches device capacity and OOM; exact requested/allocated/reserved
bytes and the ≤60-second requirement remain uncalibrated on an available GPU.

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
allocated/reserved/peak bytes when applicable. An OOM propagates with its original
traceback for the Lab to capture. No baseline OOM or peak has been recorded yet.
