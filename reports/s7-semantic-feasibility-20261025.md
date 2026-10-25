# s7 full-training semantic feasibility, 2026-10-25

This is a human-authored research control. It is not a model repair, does not add an MVP success, and does not rewrite the v7 record or the 6/9 aggregate requirement. It establishes that preserving s7's existing full-parameter training can meet its original T1.12 MVP 20% memory reduction and 25% slowdown limits on this host.

## Why the previous candidate was not equivalent

The original program calls backbone.eval(), but leaves every backbone parameter trainable and passes model.parameters() to AdamW. Evaluation mode does not freeze those parameters. The v7 candidate switched the optimizer to head-only training, changing the optimization problem. Its loss difference must not be attributed to a generic cross-batch issue. The existing full-training requirement already rules out this change.

The original 1,075,970,304 FP32 parameters occupy 4.303881216 GB; the two FP32 Adam states occupy another 8.607762432 GB. Keeping all states on CUDA while releasing each gradient after its update has a 12.911643648 GB parameter/state floor, plus working tensors. This can plausibly meet the MVP 20% limit (14.2558470144 GB from the fresh baseline); it does not imply the generic 30% limit (12.4738661376 GB) can be met.

## Public method and compatibility

[PyTorch's optimizer-in-backward tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html) describes releasing gradients as they become available, requires the post-accumulate hook available since PyTorch 2.1, and excludes gradient accumulation. The original s7 uses one backward per update, no clipping, scaling, distributed reduction, shared parameters, or checkpointing.

The implementation uses the [PyTorch 2.5.1 post-accumulate hook](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/_tensor.py) and its existing [AdamW single-tensor functional implementation](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/optim/adamw.py). Every parameter retains the original AdamW settings and FP32 optimizer states. No backbone freezing, lower precision, reduced batch, data change, state compression, or CPU offloading was introduced. foreach=False was already present in the original, so disabling foreach is not the new improvement.

The exact functional update is invoked per parameter. One public outer step closes one logical update. This is necessary because the Lab observes optimizer steps globally: blindly copying the tutorial's per-parameter optimizer.step calls would count parameter callbacks as separate updates. The research helper's restricted contract excludes accumulation, clipping, GradScaler, closures, distributed reduction, compiled and higher-order execution. It is not advertised as a general replacement.

## Preregistered GPU evidence

Plan: runs/research/s7-semantic-control-20261025/plan.json. It records original and prepared source hashes, helper/measurement source hashes, 20 logical updates, 20% and 30% memory gates separately, 25% slowdown, FP32 tolerance 1e-3, and exactly four CUDA attempts with 180 seconds each. Original source SHA: 35004f013ac7bb561ebe7b1aae92ab50809b46a01488c6188ff16929de9a1191.

NVIDIA RTX 3090 Ti was idle before and after these four runs. All containers completed 20 logical updates and verified cleanup.

| Run | Peak allocated GB | Median step ms | Wall seconds |
|---|---:|---:|---:|
| Tiny original, 9de9536fa1a54d5aba23cc1e88092fb8 | 0.068193280 | 3.353413 | 4.072 |
| Tiny control, 2efd01a1865845009fd1b7676c0bba1a | 0.068193280 | 3.677775 | 3.975 |
| Full original, bf1a3f5b88eb4813903d3b0b19b8297d | 17.819808768 | 110.995955 | 50.395 |
| Full control, 49e59ba857ad48fda49e99c8718800f8 | 13.792195072 | 111.530489 | 51.060 |

Full memory reduction: **22.6018907%**. Median step slowdown: **0.4815794%**. All 20 loss values are exactly equal (maximum absolute difference 0.0). The full baseline peak reproduces the old v7 baseline; its step time is also close to the historical 111.031449 ms.

Both tiny and full pairs have exactly matching initial and final input fingerprints, all parameter fingerprints, every AdamW state fingerprint, and algorithm parameter groups. The full snapshot covers the complete 1.076 billion parameters and both state tensors rather than sampling them. Initial and final fingerprints happen outside the training loop; the initial snapshot affects only the first interval, and the final snapshot runs after the twentieth step in a finally block. Median timing remains based on actual Lab step intervals. Snapshot wall time remains inside the 180-second limit.

Summary: runs/research/s7-semantic-control-20261025/cuda-full-summary.json. Its scalar 20% result is true, while the generic 30% result is false. The production pairing adapter remains unsupported for arbitrary s7 model patches; the extra research fingerprints prove only this controlled pair. Historical acceptance is unchanged.

## CPU verification and implementation boundary

headroom/optim/in_backward_adamw.py supplies the restricted optimizer. Existing real CPU Docker tests compare loss, every parameter, and every optimizer state at each of 20 steps, including default AdamW, AMSGrad, maximize, multiple parameter groups, unused parameters, and checkpoint restoration. These are exact rtol=0/atol=0 comparisons. A separate test confirms 80 callbacks are recorded as 20 logical steps. Invalid modes fail closed.

headroom/optim/control_capture.py supplies bounded, read-only chunked fingerprints. scripts/research_in_backward_adamw.py prepares observer-only baseline and helper-based control sources and reserves each condition once. Both are explicit research tools, never model input or score overrides.

The Lab mounts headroom at /runtime/headroom, so importing this helper inside the research sandbox is supported. That mount is not evidence that an arbitrary external project has the new helper installed. A genuine model patch must be self-contained or declare and validate its actual installed dependency. The model must independently produce the repair; this control's source must not be inserted as a hidden solution.

## s1 reference follow-up

The new bounded pairing contract supports the exact s1 program and only an explicitly imported non-reentrant checkpoint(block, hidden, use_reentrant=False) form, optionally preserving RNG state explicitly. It preserves the full normalized program, actual input tensors, initialized parameters, and one ordinary forward/backward per optimizer update. CPU paired tests establish exact loss equality for the small workload; changed batch with the same seed fails actual-input/effective-batch pairing. Clipping, accumulation, changed data/objective/optimizer and other transformations are not inferred equivalent.

The [PyTorch 2.5.1 checkpoint implementation](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py) supplies the reviewed non-reentrant API. Checkpoint recomputation roots during the observed backward are tracked separately from training forwards, only under this pinned contract.

A CPU one-block saved-tensor observation, saved in runs/research/s7-semantic-control-20261025/s1-size-observation.json, gives an engineering estimate of 129,352,761,344 bytes of saved tensors per full batch32/depth192 step. The existing reference spool duplicates each saved tensor, so the s4 64 GiB disk cap is insufficient for s1. Twenty steps imply roughly 5.17 TB of write/read traffic before serialization overhead. Capacity and the unchanged 480-second limit need independent validation; no full s1 reference GPU run was performed in this study. A separately declared checkpoint-based original-workload reference could avoid that I/O, but would need explicit original-source binding and transformation proof. It is not silently enabled by adding the pairing contract.
