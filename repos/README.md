# Pinned real-repository scenario

`nanogpt.yaml` is JSON-compatible YAML. It pins karpathy/nanoGPT at
`3adf61e154c3fe3fca428ad6bc3818b27a3b8291`; upstream source is cached under
`.cache/upstream/nanoGPT`, outside tracked project source.

Run `source scripts/env.sh` and `uv run python scripts/prepare_nanogpt.py` to
fetch the pin and generate deterministic synthetic tokens (no weights needed).
The helper refuses to replace dirty sources or different existing input data.

The default command preserves a 24-layer, 1024-wide model, sequence length 1024,
vocabulary 50304, and batch 32. Its expected activation/gradient/optimizer demand
is intended to exceed a 24 GiB device. This remains an estimate until the exact
baseline is run on an available GPU; the fit:22GB repair goal is not a result.

Run target code only inside Lab/Docker with the repository mounted read-only,
synthetic data mounted read-only at `/input` (passed as the dataset path), no network,
no API secrets, and writable `/tmp` for output. Do not run train.py on the host.
`repos/nanogpt.oom.txt` will be created only from a real failed GPU run. T0.6 is
not accepted without that traceback and the eight synthetic GPU checks.
