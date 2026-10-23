# Pinned real-repository scenario

`nanogpt.yaml` is JSON-compatible YAML. It pins karpathy/nanoGPT at
`3adf61e154c3fe3fca428ad6bc3818b27a3b8291`; upstream source is cached under
`.cache/upstream/nanoGPT`, outside tracked project source.

Run `source scripts/env.sh` and `uv run python scripts/prepare_nanogpt.py` to
fetch the pin and generate deterministic synthetic tokens (no weights needed).
The helper refuses to replace dirty sources or different existing input data.

The default command preserves a 24-layer, 1024-wide model, sequence length 1024,
vocabulary 50304, and batch 32. Its expected activation/gradient/optimizer demand
was expected to exceed a 24 GiB device. The full default configuration now has
a measured CUDA OOM, recorded below; the fit:22GB repair goal is still not a
repaired result.

Run target code only inside Lab/Docker with the repository mounted read-only,
synthetic data mounted read-only at `/input` (passed as the dataset path), no network,
no API secrets, and writable `/tmp` for output. Do not run train.py on the host.
`repos/nanogpt.oom.txt` contains the real default-run CUDA OOM traceback.
Together with the eight full synthetic GPU checks, it supports the separate
T0.6 acceptance record in `reports/t0.6-acceptance.json`.

## Measured GPU baseline

On 2026-10-23, run `20261023T013238Z-a16fc6fb` reproduced a genuine CUDA OOM
in the upstream GELU forward path in 11.489 s.
The attempted allocation was 512 MiB. The full pinned configuration was used;
`repos/nanogpt.oom.txt` is byte-identical to that run's stderr. Docker did not
report host-memory OOM, no foreign GPU process was observed, and cleanup was
verified. Upstream did not emit historical allocator peak counters, so no exact
peak value is inferred from sampled GPU usage or rounded exception text.
No completed training update was logged before failure; the printed initial
train/validation loss evaluation is not a training update.

| Observed status | Completed training updates | Runtime including startup s | Exact peak allocated/reserved |
|---|---:|---:|---|
| cuda_oom | 0 logged | 11.489 | unknown / unknown |

Evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json` and raw files under
`runs/phase0-baselines/20261023T013238Z-a16fc6fb/nanogpt/`. Reproduce with
`uv run python scripts/check_gpu_baselines.py --case nanogpt` after sourcing
`scripts/env.sh`. The full nine-case table is in `docs/RESULTS.md`.
This is T0.6 baseline evidence only: no model repair, loss-equivalence check,
T1.2 snapshot acceptance, or T2.1 search acceptance is certified.
