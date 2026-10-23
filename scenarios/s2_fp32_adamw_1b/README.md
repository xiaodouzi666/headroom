# s2 — Full float32 model and AdamW state

**Status: full default GPU baseline measured on 2026-10-23; see the measurement below.**
This default workload completed its T0.6 reclaim baseline; a 1B model does not
necessarily OOM on this device.
Run it only inside the isolated, network-disabled Lab.

## Workload and ground truth

A randomly initialized residual MLP has 32 blocks of width 2,048, each with two
4× expansion projections and a LayerNorm: **1,074,200,576 trainable parameters**.
All parameters, gradients and AdamW moments are float32. Default input is two
samples × 128 tokens, 20 optimizer steps, seed 7. AdamW explicitly uses
`foreach=True`; no external optimizer package or pretrained weights are needed.

The intended primary cause is **optimizer_state**, with a secondary contribution
from real foreach optimizer temporaries. AdamW lazily creates two moment tensors
on the first update. The script reports actual optimizer tensor bytes each step.
For the default parameter count, the following are **arithmetic estimates**:

- Parameters: 4.0017 GiB; full gradients: another 4.0017 GiB.
- Two moments: 8.0034 GiB, excluding small per-parameter step tensors.
- Parameters + gradients + moments: 16.0068 GiB.
- One additional parameter-sized foreach intermediate would give about
  20.0085 GiB before inputs, activations, other temporaries and allocator effects.

The earlier planning estimate was roughly 18–22 GiB for **reclaim** mode; this
range was not a measurement or guarantee. The default run completed 20 steps
in 14.615 s with an allocated peak of 21,503,181,312 bytes (20.026398 GiB).
The runtime logs 8,593,605,376 optimizer-state bytes, including small scalar
step counters. The two fp32 moments account for 8,593,604,608 bytes from the
parameter count; divided by measured allocated peak, this is approximately
**39.963%**.
Thus the later T1.2 ≥40% peak-composition requirement is **not certified** by
these counters; it still requires its specified snapshot evidence. The baseline
is already below both 22 GB and 22 GiB, so it also cannot demonstrate T2.1's
required two-round fit:22GB improvement. These original requirements remain
unchanged and unresolved pending discussion; no baseline was inflated to meet them.

## Expected repair classes and constraints

Candidate repairs include reducing foreach temporaries (`foreach=False` or an
appropriate fused implementation), optimizer state offload, and, if the selected
numerical policy permits it, 8-bit optimizer state or different parameter dtypes.
The plan also names bf16 autocast: it can reduce forward activation cost, but
**autocast alone does not halve float32 AdamW moments**. Fused AdamW likewise does
not remove the two persistent moment tensors. All savings and numerical changes
must be measured, including the optimizer update, not inferred from option names.
Keep parameter count, trainability, objective and step count fixed. A precision-
changing patch needs the applicable policy permission. No repaired outcome is
claimed by this fixture.

## Invocation and output

Inside the sandbox:

```sh
python train.py --device cuda --steps 20
python train.py --device cpu --tiny --steps 20
```

`--batch`, `--steps`, `--device`, `--seed` and `--tiny` are supported. Tiny mode
uses width 32, two blocks, eight tokens and the same fp32 foreach AdamW mechanism;
it cannot establish any GPU memory result. JSON lines include parameter count,
measured optimizer state bytes, losses, step times and CUDA allocated/reserved/
peak bytes. OOMs emit terminal counters and are re-raised with their original
traceback; other errors propagate to the Lab.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `completed_20_steps`;
completed training steps: 20; runtime including container startup
but excluding cleanup: 14.615 s.

- Peak allocated: **20.026398 GiB** (21503181312 bytes).
- Peak reserved: **20.673828 GiB** (22198353920 bytes).
- Source SHA-256: `bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s2_fp32_adamw_1b/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
