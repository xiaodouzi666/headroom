# s4 — Tensor-valued epoch loss retains training graphs

**Status: source prepared; GPU baseline, runtime and peak are unmeasured.**
Run this intentionally defective training loop only in the isolated,
network-disabled Lab. No OOM, ≤60-second runtime or allocation-stack acceptance
has been measured.

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
plausible on 24 GiB. This is an estimate, not a measured rate or peak.

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
not certified** by this source preparation. Correlate measured saved tensors,
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
uncaught so the Lab receives its original traceback. The measured peak remains
pending an available GPU.
