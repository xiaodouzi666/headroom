# Acceptance feasibility research — 2026-10-25

This research resolves the mechanism and makes the fixed-fixture constraint auditable.
It does not certify T1.2/T2.1/T2.8, revise their thresholds, or rerun model repair.

## Findings confirmed from primary sources and this checkout

1. The canonical s2 workload explicitly uses float32 AdamW with `foreach=True`.
   PyTorch v2.5.1 initializes two moment tensors with `zeros_like(p)` only for
   parameters whose gradients are present; its non-capturable, non-fused step
   scalar is on CPU. An optimizer name alone therefore cannot establish that
   every model parameter has GPU state. The preserved s2 evidence attributes
   8,593,604,608 bytes to those moments; its source-derived parameter count is
   1,074,200,576, consistent with 8 bytes per parameter for this workload.
   This consistency check is not a new independent tensor-semantics proof.
   [Pinned AdamW source](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/adamw.py).

2. The extra foreach memory is real optimizer working memory. The same-version
   optimizer documentation states that foreach uses approximately one parameter
   set more peak memory than the loop implementation, and offers
   `foreach=False` or smaller optimizer parameter groups when memory is tight.
   It does not promise an invariant state/peak ratio.
   [Pinned optimizer documentation](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/optimizer.py).

3. PyTorch's official optimizer-in-backward tutorial shows a peak containing
   parameters, gradients, two moment sets, and an additional parameter-sized
   temporary. It also explains that the global peak can move after a repair.
   The tutorial requires PyTorch >=2.1 and explicitly excludes ordinary gradient
   accumulation from its basic recipe. This supports the mechanism on 2.5.1,
   but does not justify automatically applying optimizer-in-backward to arbitrary
   Headroom inputs. The tutorial page currently has a newer documentation shell.
   [Official tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html).

4. DeepSpeed's memory discussion separately budgets Adam moments (8 bytes per
   parameter in its stated FP32-state assumption), parameters, gradients,
   activations and temporary memory. Its ZeRO formulas include sharding and
   precision assumptions; the 18-byte formula is not a generic single-GPU
   FP32 AdamW estimate.
   [DeepSpeed memory requirements](https://deepspeed.readthedocs.io/en/stable/memory.html).

Consequently, no source supports treating an arbitrary 40% ratio as a universal
industry validation rule. In this project it remains the original explicit
acceptance threshold. The saved 39.8715009692% result remains a failed threshold,
while its classified state bytes are consistent with the fixture's moments.
Relabeling temporary allocations as persistent optimizer state would be wrong.

## Exact conflict for the current fixture

Let S be the fixed optimizer-state bytes, P the allocated peak, f the required
state fraction, and L the capacity target. The original share condition implies:

```text
S / P >= f   =>   P <= S / f
S = 8,593,604,608 bytes
f = 0.4
P <= 21,484,011,520 bytes < L = 22,000,000,000 bytes
```

Every integer-byte peak satisfying the original 40% condition already fits
22 GB. The original solver also says to stop once the budget is reached.
Therefore this fixed fixture cannot simultaneously meet the share condition
and begin above the target to demonstrate a two-round capacity repair. This
conclusion is conditional on the fixed state-byte count and common allocated
peak accounting domain. It does not prove that a redesigned fixture is
impossible. It also does not certify any number of useful repair rounds.

The old diagnostic run with only `foreach=False` confirms the expected direction:
its state bytes are unchanged, peak falls to 17,390,699,008 bytes, and the share
rises to 49.4149464840%. That was a manual diagnostic candidate. Its historical
comparison has different Lab versions and is not an accepted model repair or
throughput result. No new GPU result was produced here.

The new pure offline function `audit_fixed_state_capacity` in
`headroom/acceptance/feasibility.py` checks this algebra with exact rational and
integer arithmetic. It accepts explicit state bytes rather than deriving state
from the word AdamW. Missing quantities remain unknown; physically inconsistent
state/peak inputs are rejected. Compatible inequalities are reported only as
`not_ruled_out`, never as acceptance. The CLI needs no profile, credentials,
Torch import, GPU, or database. The receipt is
`reports/acceptance-feasibility-20261025.json`.

Reproduction:

```sh
.venv/bin/python -m headroom.acceptance.feasibility \
  --optimizer-state-bytes 8593604608 \
  --minimum-state-fraction 0.4 \
  --fit-limit-bytes 22000000000 \
  --observed-peak-bytes 21553250816
```

## Precision-policy conflict and the existing implementation

The original T2.1 asks for a default-policy Pareto frontier containing both a
numerics-identical point and a more memory-efficient BF16 point. T2.8 describes
two arms as default versus `allow_numerics_change=false`. Current default
already sets that permission to false.

This was already made explicit in `headroom/evaluation.py:resolve_policies`
and `docs/EVALUATION.md`: default and strict have identical effective policies;
`same_effective_policy_as` exposes the aliases; selecting `allow_precision`
explicitly enables numerical changes. Repeating equivalent arms does not test a
precision policy contrast. No additional preset or implicit permission was added.

PyTorch v2.5.1's autocast source says to use operation-specific dtypes for the
forward and loss region, keep backward outside autocast, and avoid directly
calling model `half()` or `bfloat16()` when using autocast. CUDA BF16 support is
checked explicitly. Autocast does not automatically halve FP32 moment storage.
[Version-pinned autocast source](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/amp/autocast_mode.py).

NVIDIA describes mixed precision as a combination of formats, with FP32 retained
for sensitive operations. Its FP16 guide describes loss scaling and, when
needed, FP32 master weights. This supports explicit precision choices and
validation; it does not establish bitwise equivalence or this project's BF16
tolerance. The FP16 loss-scaling recipe should not be silently generalized to
every BF16 workload.
[NVIDIA mixed precision guide](https://docs.nvidia.com/deeplearning/performance/mixed-precision-training/index.html).

No newer mixed-dtype optimizer-state API was assumed available in torch 2.5.1.
A future versioned precision contrast can select existing strict and
allow_precision arms with distinct effective policies and the existing numerical
checks. Selecting that contrast cannot retroactively satisfy the original
default-policy wording.

## What can and cannot be closed automatically

Closed here: primary-source mechanism verification, exact feasibility audit,
offline regression coverage, and explicit evidence boundaries.

Still requires a project-target decision:
- Whether to preserve current s2 as the historical fixture and add a separately
  versioned capacity-repair fixture calibrated above 22 GB, or revise the target
  of a new benchmark version. Neither option changes old failures.
- What a new version should require of useful multi-round progress. Public
  documentation cannot decide that product criterion.
- Whether the intended policy experiment is strict versus allow_precision, and
  whether BF16 should be permitted under the product's default policy. Current
  default remains unchanged.

## Validation and provenance

- `pytest -q tests/test_acceptance_feasibility.py`: 22 passed.
- Targeted Ruff checks passed; formatter applied only to the new module.
- Tests cover the historical failure, an equal boundary, fractional-byte
  infeasibility, a feasible integer interval without certification, missing
  inputs, invalid data, rational arithmetic, unchanged input, and the standalone
  CLI.
- No provider call, new GPU execution, credential read, production database
  write, historical artifact rewrite, or canonical fixture edit occurred.

Inputs verified on 2026-10-25:

| Artifact | SHA-256 |
|---|---|
| docs/PLAN.md | e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56 |
| eval/mvp_phase1.yaml | 3bb919336829754a52ec8c90ccc4a5181f33986f9e300e99211bec6678849e88 |
| scenarios/s2_fp32_adamw_1b/train.py | bb1d12c69ce5525e6eab67e709740cb2d578c070afa8b094b5f4b6906648bc5b |
| reports/evidence-acceptance-20261023T025427Z.json | 6cfe527147977a601dd38dc8b96c5e0d3ce37262557ebbcda80c9de72e7a7405 |
| reports/s2-optimizer-diagnostic-20261024/report.md | fb6227a8d4706706648be2374aca81b0c3a4a28a3fde15f6b5727bf6ce09d10c |
