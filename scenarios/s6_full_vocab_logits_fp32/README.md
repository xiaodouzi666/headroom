# Full-vocabulary fp32 logits

Status: source preparation only, **not calibrated on the 24 GiB GPU**. No measured peak or within-60-second OOM is claimed.

Ground truth: a small token model projects every token to a 131072-entry vocabulary, retains the bf16 logits, materializes a full fp32 copy with `.float()`, and passes the entire matrix to cross entropy. Loss intermediates and backward can overlap these tensors. All logits are used by the objective; there are no unrelated filler allocations.

Default: batch 8, sequence length 2048, hidden width 128, vocabulary 131072, bf16 model on CUDA, SGD, 20 requested steps. Intended mode is `fix-oom`. Tensor-size arithmetic: the full bf16 logits occupy **4 GiB**, and their fp32 copy **8 GiB**. Full fp32 log-softmax and backward buffers can bring required live memory above **24 GiB** (planning estimate **28–36 GiB**, unmeasured). On a 24 GiB card the successful-allocation peak before failure is not the full required peak. The actual OOM site, elapsed time and peak await calibration.

Expected repair classes: chunk the projection and CE across token rows with correctly weighted loss and backpropagation, or avoid unnecessary `.float()` if the selected numerical policy permits that change. Chunking CE after retaining the entire fp32 logits still retains that matrix and may not suffice. Preserve vocabulary, sequence length, batch/effective-batch and all target tokens. Lower-precision CE is not automatically numerically equivalent to fp32 CE.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Available flags: `--batch`, `--steps` (20), `--device` (cuda), `--tiny`, `--seed` (17). CPU uses fp32 for portability; its tiny smoke tests the full logits/CE path but cannot reproduce the extra bf16-to-fp32 copy. CUDA tiny retains that copy. JSON Lines report dimensions, losses and memory bytes (null for CPU GPU-memory fields). OOM is re-raised, preserving traceback for the future Lab wrapper.
