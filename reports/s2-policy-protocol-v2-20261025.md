# Versioned s2 and precision-policy protocol — 2026-10-25

Status: the independent classification and all four preregistered capacity checks **passed**. The aggregate artifact audit returned accepted=true with no errors; model acceptance remains separate. This work makes no model calls and awards no model repair scores. Historical v7 remains **1/9**, with the primary gate **6/9**.

## Approved scope

The user approved separate classification/capacity fixtures and explicit strict/allow_precision policies. The original PLAN, s2 source, MVP manifest and scores remain historical. New manifest filenames version the benchmark while retaining parser schema version 1.

- Classification v2: 32 blocks, width 2048, sequence 128, batch 2, fp32 AdamW foreach=False, seed 1337, 20 optimizer updates. The existing state-category threshold stays **40%**. This independent preflight is outside the nine repair cases.
- Capacity v2: 34 blocks, width 2048, sequence 128, batch 24, fp32 AdamW foreach=True, seed 1337, 20 updates. It occupies one s2 position in the **nine** repair cases, targeting **22,000,000,000 bytes**.
- Measured inventories check actual initialized states and moment dtype/shape/device/bytes. Optimizer class name alone does not establish initialized state.
- Optimizer-only, checkpoint-only and combined controls are private research copies, excluded from Git and model source roots. Their successes never count as model repairs.

The requirement that the capacity baseline completes 20 updates is an additional preregistered **calibration design condition**. The original capacity objective itself also permits recovery from OOM. This condition isolates the two memory pressures; it cannot be dropped after a failed calibration.

## Fixed calibration gates

Every run must complete 20 actual updates within 180 seconds, with complete capture, verified cleanup, no observed sharing, and agreement between native and replayed peaks. Baseline and each isolated control must exceed 22 GB; the combined control must fit at or below 22 GB. A baseline already fitting the target fails calibration.

The foreach=False control reduces optimizer update temporaries, not persistent Adam moment-state bytes. It does not establish T2.1's specifically worded state-first repair requirement; that remains a separate model-evidence gate.

These controls establish only fixture potential. The model must still produce and validate its own repairs, with at least two successful rounds and at most six search rounds. Numerical equivalence and throughput remain separate model-candidate gates.

Theoretical estimates are not measurements. Capacity has 1,141,338,112 parameters. Parameters, gradients, moments and a parameter-sized foreach temporary suggest about 22.827 GB; activation retention should create another peak. Actual results decide whether this expectation is valid.

## Retained measurements

| Attempt | Status | Exact peak bytes | State-category bytes | Decision |
|---|---|---:|---:|---|
| v2-a classification | Completed 20 updates | 17,390,699,008 | 8,593,604,608 | Ratio exceeds 40%, but inventory emitted after Lab's stop was absent; full preflight failed |
| CPU observation repair | Completed 2 updates | n/a | n/a | Inventory after update 1 survives stop at update 2; no GPU acceptance |
| v2-b classification | Completed 20 updates | 17,390,699,008 | 8,593,604,608 | All gates passed, approximately 49.415% |
| v2-b capacity baseline | OOM before completing update 1 | 22,449,488,384 | 9,130,704,896 | Failed; controls not run |

The v2-b classification inventory is explicitly from **update 19**, not 20: 192/192 states, fp32 moments matching parameter shapes/devices, and 8,593,604,608 CUDA moment bytes matching the existing category at peak. Lab independently recorded 20 updates and exact allocator history. Moving inventory into step output did not alter training dimensions, loss, dtype, optimizer, target, or threshold.

Capacity v2-b reserved 24,807,211,008 bytes. The recorded OOM satisfies the existing fragmentation condition: request 67,108,864 bytes, insufficient driver free memory, and enough inactive split memory. This is more specific than a reserved-minus-allocated gap, but does not prove fragmentation is the sole cause. The failed receipt and original Lab artifacts are retained.

## v2-c preregistration

v2-c fixes expandable_segments:True uniformly for baseline and all three capacity controls. It changes no dimensions, batch, dtype, seed, steps, timeout or threshold. It references the already-passed independent v2-b classification receipt, allows at most four capacity runs and stops after the first failure.

This is a common environment setting, not model repair credit. The new manifests and all future candidates must inherit the same initial allocator setting. Source hashes, classification receipt hash and gates are fixed in reports/s2-calibration-v2-20261025-c/preregistration.json. At preparation of this section, those four runs have not executed.

## Explicit policy scopes

The protocol JSON and pure protocol_v2 planner define:

- Primary: nine cases under strict/full_ultra, minimum **6/9**. Successes are never pooled across policies.
- MVP comparison: nine cases × strict/allow_precision = **18** pipeline runs, reported separately.
- Phase 2: eight synthetic cases + nanoGPT + HF × two policies = **20** pipeline runs, retaining the original separate 75% target/first-cause descriptive goals.
- HF's configuration-only patch gate and two library cases remain separate acceptance work.
- Default remains strict. allow_precision explicitly permits numerical change; it does not prove BF16 use, lower peak or an additional Pareto candidate. Each requires measured candidate evidence and its own patch.

The planner does not access credentials, GPU, provider or billing. Planned run-cap sums are not extra credits. Future execution uses the existing authoritative promotional pool only.

## Standard human-control verification

The two saved original Lab result files were passed directly to compare_runs with target fit:22GB, default Policy and required_steps=20. The standard comparator returned target_met=true, loss_equivalence=within_tol, maximum loss difference 4.76837158203125e-7, and throughput regression 18.53381692101326%. This is stored as human_control_only and repair_score_eligible=false in human-control-standard-verification.json.

No pairing claims were supplied or fabricated: same_inputs, same_effective_batch and same_objective remain null, with loss_comparable=false. The standard verdict follows the original scalar-series gate; it is not a claim of strong workload pairing or bitwise identity. Formal model-generated repairs, T2.1's state-first method/two-round sequence, and the BF16 Pareto candidate remain separate acceptance work.

## Version-pinned primary sources

- [PyTorch 2.5.1 optimizer documentation/source](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/optimizer.py): foreach can require parameter-sized additional peak memory.
- [PyTorch 2.5.1 AdamW](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/adamw.py): moment initialization depends on parameter gradients.
- [PyTorch 2.5.1 checkpoint](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/utils/checkpoint.py): explicit use_reentrant=False is supported; recomputation trades compute for retained activation storage.
- [PyTorch 2.5.1 CUDA notes](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/docs/source/notes/cuda.rst) and [allocator implementation](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/c10/cuda/CUDACachingAllocator.cpp): expandable segments are experimental, off by default, and grow per-stream segments to reduce unusable tails. This motivates a test, not a guarantee.
- [Official optimizer-step-in-backward tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html): after an optimization, another training phase can become the peak. Its current site version is newer than installed 2.5.1; pinned sources govern compatibility here.
- [PyTorch 2.5.1 autocast](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/amp/autocast_mode.py): autocast operation selection is not blanket conversion of fp32 parameters or Adam moments.

The 40%, 22 GB, 6/9 and two-round criteria are **project criteria**, not industry standards.

## Verification

56 new offline protocol/calibration tests pass, covering exact integer boundaries, already-fit rejection, incomplete evidence/state, policy separation and nine-case preservation. A real isolated CPU tiny Lab test checked controlled-stop observation. Recorded GPU runs establish only the scope above. Full regression and model acceptance are parent-coordinated and remain separate.
