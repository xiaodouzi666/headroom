# Related work review — 2026-10-24

Original PLAN A.4 / T5.1 requires truthful related-work comparisons. README now covers each named family with primary-source links, without claiming first-ever/only-tool novelty or completed Headroom live repair validation.

Verified corrections to the planning shorthand:

- GPU-Boost currently documents approved deterministic edits, validation and rollback, in addition to analysis and benchmark advice. It must not be characterized as unable to execute or validate.
- loadtune includes runtime tuning and automatic batch/OOM handling; its scope is broader than static DataLoader advice.
- Checkmate is the MLSys 2020 tensor-rematerialization work (1910.02653), not the unrelated NSDI 2026 model-recovery checkpoint system with the same name.
- ZeRO-Offload also works on one GPU and can be configured in DeepSpeed without rewriting a model. The named research systems do not all require a model rewrite or distributed-only deployment.
- AutoKernel here is RightNow-AI/autokernel, not the separate Halide/Tengine OAID project of the same name.
- The original PLAN is preserved; current README uses evidence-bounded project positioning.

Primary sources inspected:

1. https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html
2. https://pytorch.org/blog/understanding-gpu-memory-1/
3. https://github.com/its-arnavtech/GPU-Boost/blob/main/README.md
4. https://docs.nvidia.com/nemo/megatron-bridge/nightly/skills/nemo-mbridge-memory-snapshot-analysis/SKILL.html
5. https://pypi.org/project/loadtune/
6. https://github.com/RightNow-AI/autokernel/blob/main/README.md
7. https://github.com/karpathy/autoresearch/blob/master/README.md
8. https://arxiv.org/abs/1910.02653
9. https://www.deepspeed.ai/tutorials/zero-offload/
10. https://github.com/CentML/Mist/blob/main/README.md
11. https://github.com/PKU-DAIR/Hetu-Galvatron

This was a documentation scope check, not a benchmark of these tools or an exhaustive novelty survey. No upstream source code was executed. Headroom's own remaining live acceptance gates are unchanged.
