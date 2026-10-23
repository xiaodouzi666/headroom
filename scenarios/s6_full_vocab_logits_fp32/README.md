# Full-vocabulary fp32 logits

Status: full default GPU baseline measured on 2026-10-23; see the measurement below.

Ground truth: a small token model projects every token to a 131072-entry vocabulary, retains the bf16 logits, materializes a full fp32 copy with `.float()`, and passes the entire matrix to cross entropy. Loss intermediates and backward can overlap these tensors. All logits are used by the objective; there are no unrelated filler allocations.

Default: batch 8, sequence length 2048, hidden width 128, vocabulary 131072, bf16 model on CUDA, SGD, 20 requested steps. Intended mode is `fix-oom`. Tensor-size arithmetic: the full bf16 logits occupy **4 GiB**, and their fp32 copy **8 GiB**. Full fp32 log-softmax and backward buffers can bring required live memory above **24 GiB** (historical planning estimate **28–36 GiB**, not a measured requirement). On a 24 GiB card the successful-allocation peak before failure is not the full required peak. The default run produced a real CUDA OOM in 5.218 s with an 8 GiB failed request; the measured historical allocated peak is 20.082430 GiB. The failed request is not included in that counter. See the exact bytes and original traceback below.

Expected repair classes: chunk the projection and CE across token rows with correctly weighted loss and backpropagation, or avoid unnecessary `.float()` if the selected numerical policy permits that change. Chunking CE after retaining the entire fp32 logits still retains that matrix and may not suffice. Preserve vocabulary, sequence length, batch/effective-batch and all target tokens. Lower-precision CE is not automatically numerically equivalent to fp32 CE.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

Available flags: `--batch`, `--steps` (20), `--device` (cuda), `--tiny`, `--seed` (17). CPU uses fp32 for portability; its tiny smoke tests the full logits/CE path but cannot reproduce the extra bf16-to-fp32 copy. CUDA tiny retains that copy. JSON Lines report dimensions, losses and memory bytes (null for CPU GPU-memory fields). OOM is re-raised, preserving traceback for the future Lab wrapper.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `cuda_oom`;
completed training steps: 0; runtime including container startup
but excluding cleanup: 5.218 s.

- Peak allocated: **20.082430 GiB** (21563344896 bytes).
- Peak reserved: **20.103516 GiB** (21585985536 bytes).
- Source SHA-256: `4f5d7e0f4331a4efcda2039c8ac8a421b2a1923778379896e2658553619b1bba`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s6_full_vocab_logits_fp32/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
