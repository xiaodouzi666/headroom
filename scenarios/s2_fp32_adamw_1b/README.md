# s2 — Full float32 model and AdamW state

**Status: source prepared; GPU baseline, runtime and peak are unmeasured.**
This is a reclaim candidate under T0.6, not a claim that a 1B model must OOM.
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

Expected peak is roughly 18–22 GiB and intended default mode is **reclaim**, but
this range is not a measured peak or a guaranteed bound. The 20-step completion,
actual optimizer-state fraction and run duration still require GPU calibration.
At a peak greater than 20.0085 GiB, the two moments alone are below 40% of peak;
therefore the later T1.2 ≥40% requirement is explicitly **not certified** here.
Likewise this configuration does not certify T2.1's two-round fit:22GB requirement.
Those original acceptance requirements remain unchanged pending discussion.

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
peak bytes. Errors and OOMs remain uncaught for the Lab's original traceback.
