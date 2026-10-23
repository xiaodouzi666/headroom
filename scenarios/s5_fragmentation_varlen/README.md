# Variable-length token batches and allocator reuse

Status: source preparation only, **not calibrated on the 24 GiB GPU**. No measured peak, fragmentation diagnosis, or acceptance pass is claimed.

Ground truth: a six-block residual token MLP receives repeatedly changing padded sequence lengths. Its real activation and temporary tensors change size each step. The native caching allocator can leave incompatible cached blocks or inactive split blocks; whether this fixture actually creates harmful fragmentation is **pending allocator-history evidence**. No unrelated filler tensors are allocated.

Default: batch 8, width 1024, expansion 4, six blocks, sequence lengths 2048–2336, SGD, fp32, 20 updates. Intended mode is `reclaim`. Planning estimate: approximately **3–8 GiB peak allocated**, with a potentially larger reserved peak. These are unmeasured estimates, not acceptance results; the required reserved-minus-allocated gap of at least 1 GB is also unverified.

Expected repair classes: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (set before Python starts) and length bucketing for allocation reuse. Preserve samples, objective, and update accounting when changing grouping. Allocator settings may reduce reserved memory without reducing live allocated peak; do not report such a change as allocated-memory savings. The default fixture neither sets allocator flags nor calls empty_cache each step.

A reserved-minus-allocated gap alone includes ordinary reusable cache and is not proof of fragmentation. Compare inactive split bytes, allocation history, free-block sizes and failed-request sizes, allocator backend, and comparable device availability. The original T1.2 requirement remains pending; this README does not amend it or pre-label a run high.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

`--batch`, `--steps`, `--device`, `--tiny`, and `--seed` are available. Tiny mode retains varying sequence lengths but cannot validate CUDA allocation behavior. JSON Lines report resolved dimensions, loss, per-step timing and bytes; CPU GPU-memory fields are null. CUDA OOM is re-raised with its traceback after an OOM summary.
