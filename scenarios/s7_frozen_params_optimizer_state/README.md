# An intended frozen backbone still accumulates gradients and AdamW state

Status: full default GPU baseline measured on 2026-10-23; see the measurement below.

Ground truth: the intended task is head-only fine-tuning. The program calls `backbone.eval()` but fails to set `requires_grad_(False)` and supplies every parameter to AdamW. eval mode does not freeze gradients. Backpropagation therefore creates backbone gradients, and AdamW lazily creates two moment tensors for those parameters. This explicitly uses the original plan's `requires_grad`-not-disabled alternative. Simply putting correctly frozen parameters with grad=None in a fresh AdamW optimizer would not demonstrate this defect.

Default: batch 8, width 8192, 16 fp32 linear/GELU backbone blocks and a 256-class head, AdamW with foreach=False, 20 updates. Intended mode is `reclaim`. Approximately 1.074 billion backbone parameters account for **4 GiB weights + 4 GiB gradients + 8 GiB AdamW moments**, before head parameters, activations and step temporaries. Historical planning peak estimate: **16–18 GiB allocated**, distinct from the measured result below. No filler allocations are used. The default run completed all 20 updates in 7.311 s with a measured allocated peak of 16.549359 GiB; exact counters and evidence are below.

Expected repairs: explicitly freeze the backbone before constructing the optimizer, optimize only the head, and run the frozen backbone without autograd when valid. A frozen backbone must still be evaluated to produce head inputs. The script logs actual backbone state bytes after each optimizer step so state allocation can be verified.

Numerical caveat: fixing the declared head-only intent changes the buggy baseline's trainable set and updates. It is **not** a loss-identical repair of its current all-parameter training. Report the observed numerical/policy outcome honestly; strict equivalence may reject this repair. This fixture does not change plan acceptance or authorize relaxing numerical policy. A separate correctly frozen reference is needed to validate intended behavior.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Flags: `--batch`, `--steps` (20), `--device`, `--tiny`, `--seed`. Tiny mode preserves the missing-freeze defect. JSON Lines report intended versus actual trainable parameters, backbone optimizer-state bytes, losses and GPU memory bytes (null on CPU). CUDA OOM is summarized then re-raised with its traceback.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `completed_20_steps`;
completed training steps: 20; runtime including container startup
but excluding cleanup: 7.311 s.

- Peak allocated: **16.549359 GiB** (17769739264 bytes).
- Peak reserved: **16.570312 GiB** (17792237568 bytes).
- Source SHA-256: `35004f013ac7bb561ebe7b1aae92ab50809b46a01488c6188ff16929de9a1191`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s7_frozen_params_optimizer_state/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
