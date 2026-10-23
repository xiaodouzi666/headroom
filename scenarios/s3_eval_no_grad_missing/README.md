# s3 — Evaluation builds an unnecessary autograd graph

**Status: full default GPU baseline measured on 2026-10-23; see the measurement below.**
This **reclaim** workload completed 20 steps in the isolated, network-disabled
Lab. No repaired outcome or ≥30% memory saving has been measured.

## Workload and ground truth

A residual MLP with width 768, eight blocks and **37,791,744 parameters** performs
one SGD training update and then a validation pass each step. Training batch is
one; default validation batch is 16; both use 512 tokens. There are 20 optimizer
steps, random initialization and fixed synthetic data with seed 7.

The evaluation helper calls `model.eval()` but omits `torch.no_grad()`. Because
parameters require gradients, evaluation constructs and retains saved activation
tensors until that helper returns its scalar metric. `eval()` by itself does not
disable autograd. The training backward releases its own saved activations.
No prediction list or cross-step graph cache is used, so this fixture isolates
unnecessary evaluation **peak** memory rather than a deliberate epoch-long leak.

Each expanded evaluation activation is 16 × 512 × 3,072 × 4 = **96 MiB**.
Multiple tensors per block can remain live over eight blocks. Expected baseline
peak is on the order of **2–4 GiB**, versus a smaller inference-only validation
peak. That was a planning estimate. The measured allocated peak is
2,385,648,128 bytes (2.221808 GiB), and all 20 steps completed in 6.259 s;
the exact reserved peak and evidence paths are below.

## Expected repair classes and constraints

Wrap the evaluation helper's forward and metric calculation in
`torch.no_grad()` or, after compatibility verification, `torch.inference_mode()`.
Keep the training backward enabled, and preserve model, data, validation batch,
objective, optimizer updates and metrics. The desired repair should preserve
training/validation losses and remove saved evaluation activations. The later
T1.6 ≥30% reduction remains an unchanged, unverified acceptance criterion.

## Invocation and output

Inside the sandbox:

```sh
python train.py --device cuda --steps 20
python train.py --device cuda --batch 1 --steps 20
python train.py --device cpu --tiny --steps 20
```

`--batch` controls evaluation batch only; training batch stays one. Tiny mode
uses width 32, two blocks, eight tokens and evaluation batch two while retaining
the missing-no-grad defect. `--seed` defaults to 7. JSON lines contain configuration,
parameter count, **training** loss, validation loss, timing and CUDA peak bytes.
There is one real backward and optimizer step per iteration, so the later Lab
hooks can collect the requested training loss sequence. Lab hooks at the exact
optimizer step occur before that iteration's evaluation; full-run peak must still
include the last validation pass. No result has been fabricated for those hooks.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `completed_20_steps`;
completed training steps: 20; runtime including container startup
but excluding cleanup: 6.259 s.

- Peak allocated: **2.221808 GiB** (2385648128 bytes).
- Peak reserved: **2.314453 GiB** (2485125120 bytes).
- Source SHA-256: `7fedcae13989b309cc5a034e62284094829057654aebb2e716c3413dfb0fea67`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s3_eval_no_grad_missing/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
