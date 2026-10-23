# Variable-length token batches and allocator reuse

Status: full default GPU baseline measured on 2026-10-23; see the measurement below. Harmful fragmentation remains unconfirmed.

Ground truth: a six-block residual token MLP receives repeatedly changing padded sequence lengths. Its real activation and temporary tensors change size each step. The native caching allocator can leave incompatible cached blocks or inactive split blocks; whether this fixture actually creates harmful fragmentation is **pending allocator-history evidence**. No unrelated filler tensors are allocated.

Default: batch 8, width 1024, expansion 4, six blocks, sequence lengths 2048–2336, SGD, fp32, 20 updates. Intended mode is `reclaim`. Planning estimate: approximately **3–8 GiB peak allocated**, with a potentially larger reserved peak. These are historical planning estimates. The measured allocated peak is 4.630246 GiB and reserved peak is 18.419922 GiB. At the final observation, current reserved minus allocated is 19,358,302,208 bytes (18.028824 GiB), but this includes ordinary cache. It does not establish T1.2's snapshot-based fragmentation conclusion.

Expected repair classes: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` (set before Python starts) and length bucketing for allocation reuse. Preserve samples, objective, and update accounting when changing grouping. Allocator settings may reduce reserved memory without reducing live allocated peak; do not report such a change as allocated-memory savings. The default fixture neither sets allocator flags nor calls empty_cache each step.

The final observation also reports 760,758,272 inactive-split bytes and zero allocation retries. A reserved-minus-allocated gap alone includes ordinary reusable cache and is not proof of harmful fragmentation. Compare inactive split bytes, allocation history, free-block sizes and failed-request sizes, allocator backend, and comparable device availability. The original T1.2 requirement remains pending; this README does not amend it or pre-label a run high.

Run only inside the project's network-disabled Docker sandbox:

```text
python /src/train.py --steps 20 --device cuda
python /src/train.py --tiny --steps 2 --device cpu
```

`--batch`, `--steps`, `--device`, `--tiny`, and `--seed` are available. Tiny mode retains varying sequence lengths but cannot validate CUDA allocation behavior. JSON Lines report resolved dimensions, loss, per-step timing and bytes; CPU GPU-memory fields are null. CUDA OOM is re-raised with its traceback after an OOM summary.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `completed_20_steps`;
completed training steps: 20; runtime including container startup
but excluding cleanup: 9.387 s.

- Peak allocated: **4.630246 GiB** (4971688960 bytes).
- Peak reserved: **18.419922 GiB** (19778240512 bytes).
- Source SHA-256: `627d24ee9e62601455e37f29166df8abe73a43b9e82382a293feec3a6b558169`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s5_fragmentation_varlen/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
