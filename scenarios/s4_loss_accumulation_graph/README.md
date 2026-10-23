# s4 — Tensor-valued epoch loss retains training graphs

**Status: full default GPU baseline measured on 2026-10-23; see the measurement below.**
Run this intentionally defective training loop only in the isolated,
network-disabled Lab. CUDA OOM was reproduced in 6.260 s after 12 completed
steps. The later allocation-stack acceptance has not been demonstrated.

## Workload and ground truth

A width-1,024, six-block residual MLP with **50,374,656 parameters** trains using
SGD on eight samples × 1,024 tokens by default. It requests 20 optimizer steps,
uses random initialization and fixed synthetic data, and seeds PyTorch with 7.
The intended primary cause is **retained computation graphs / activations**.
There are two interacting mistakes, both visible in the script:

1. `loss.backward(retain_graph=True)` unnecessarily keeps saved forward tensors.
   This loop traverses each loss graph only once, so graph retention is unneeded.
2. `total_loss += loss` adds the differentiable tensor to an epoch metric and
   keeps previous loss graphs reachable. The metric is never backpropagated.

Every optimizer update is real; no dummy tensors are allocated to force OOM.
Graphs from earlier updates are not backpropagated again, avoiding an unrelated
in-place parameter-version error. Reading a metric with `.item()` does not detach
or release the original `total_loss` tensor that remains live in the loop.

This fixture deliberately documents the necessary retention mechanism:
**ordinary backward normally releases saved tensors, so `total_loss += loss`
alone is not proof of a large activation leak**. The two mistakes together keep
real forward saved tensors alive. Each expanded activation is 8 × 1,024 × 4,096
× 4 = **128 MiB**; several are retained per block and per step. Expected live
memory growth is on the order of **1–3 GiB per step**, making OOM within 20 steps
plausible on 24 GiB. This was a shape-based estimate, not a measured growth
rate. The default run actually OOMed during the next iteration after 12 completed
updates; its historical peak counters and original traceback are recorded below.

## Expected repair classes and evidence caveat

Use a detached numeric accumulator (`total_loss += loss.item()`, adapting its
logging as needed) and remove the unnecessary `retain_graph=True`. Preserve all
SGD updates, model dimensions, data and step count. A repaired metric should
retain its meaning as the sum of per-step loss values.

CUDA allocation stacks generally identify where forward tensors were allocated;
they do not automatically identify the later Python expression retaining them.
The `total_loss += loss` source location is essential causal evidence, but its
scalar allocation need not appear among the largest allocation stacks. The
original T1.2 requirement that Top stacks locate this line is **not changed and
not certified** by this T0.6 baseline. Correlate measured saved tensors,
source code and allocator evidence honestly; do not insert fake allocations or
rewrite stack frames to manufacture a match.

## Invocation and output

Inside the sandbox:

```sh
python train.py --device cuda --steps 20
python train.py --device cpu --tiny --steps 20
```

The common `--batch`, `--steps`, `--device`, `--tiny`, `--seed` arguments are
supported. Tiny mode keeps both defects but uses width 32, two blocks, eight
tokens and batch two, allowing a small CPU plumbing check without establishing
GPU acceptance. JSON lines expose each actual step loss, accumulated loss,
parameter count, wall time and CUDA allocated/reserved/peak bytes. An OOM is
re-raised after terminal counters are emitted so the Lab receives its original
traceback. The full default GPU peak is recorded below.

## Measured default GPU baseline — 2026-10-23

Run: `20261023T013238Z-a16fc6fb` on azuki RTX 3090 Ti, torch 2.5.1+cu124.
Full default dimensions, CUDA, no tiny mode. Observed outcome: `cuda_oom`;
completed training steps: 12; runtime including container startup
but excluding cleanup: 6.260 s.

- Peak allocated: **23.147012 GiB** (24853914624 bytes).
- Peak reserved: **23.152344 GiB** (24859639808 bytes).
- Source SHA-256: `b29322f3c89204318d45c5350e7998e0f2ed900673b596a9490efc19188a447b`.
- No competing GPU process observed; container cleanup verified.
- Aggregate evidence: `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`; raw stdout/stderr: `runs/phase0-baselines/20261023T013238Z-a16fc6fb/s4_loss_accumulation_graph/`.

These counters measure the historical maximum of successful allocations. For an
OOM run, they do not include the failed allocation or estimate the total memory
needed to finish. Earlier planning ranges in this document are estimates; use
the measured values above for this source version. No repair or later-phase
acceptance is certified by this baseline.
