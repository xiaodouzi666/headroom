# An intended frozen backbone still accumulates gradients and AdamW state

Status: source preparation only, **not calibrated on the 24 GiB GPU**. No measured peak or acceptance pass is claimed.

Ground truth: the intended task is head-only fine-tuning. The program calls `backbone.eval()` but fails to set `requires_grad_(False)` and supplies every parameter to AdamW. eval mode does not freeze gradients. Backpropagation therefore creates backbone gradients, and AdamW lazily creates two moment tensors for those parameters. This explicitly uses the original plan's `requires_grad`-not-disabled alternative. Simply putting correctly frozen parameters with grad=None in a fresh AdamW optimizer would not demonstrate this defect.

Default: batch 8, width 8192, 16 fp32 linear/GELU backbone blocks and a 256-class head, AdamW with foreach=False, 20 updates. Intended mode is `reclaim`. Approximately 1.074 billion backbone parameters account for **4 GiB weights + 4 GiB gradients + 8 GiB AdamW moments**, before head parameters, activations and step temporaries. Planning peak estimate: **16–18 GiB allocated**, unmeasured. No filler allocations are used. Actual runtime and the 20-step peak await calibration.

Expected repairs: explicitly freeze the backbone before constructing the optimizer, optimize only the head, and run the frozen backbone without autograd when valid. A frozen backbone must still be evaluated to produce head inputs. The script logs actual backbone state bytes after each optimizer step so state allocation can be verified.

Numerical caveat: fixing the declared head-only intent changes the buggy baseline's trainable set and updates. It is **not** a loss-identical repair of its current all-parameter training. Report the observed numerical/policy outcome honestly; strict equivalence may reject this repair. This fixture does not change plan acceptance or authorize relaxing numerical policy. A separate correctly frozen reference is needed to validate intended behavior.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Flags: `--batch`, `--steps` (20), `--device`, `--tiny`, `--seed`. Tiny mode preserves the missing-freeze defect. JSON Lines report intended versus actual trainable parameters, backbone optimizer-state bytes, losses and GPU memory bytes (null on CPU). CUDA OOM is summarized then re-raised with its traceback.
