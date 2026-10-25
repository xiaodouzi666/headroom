# Independent checkpoint precision review

Reviewed the private, version-pinned draft only. Verdict: **no blocking design finding remains for the proposed bounded GPU validation**. This is not a claim that GPU worker coverage, numerical equivalence, or overall MVP acceptance has passed.

## Exact review and independent CPU result

- Private precision.py: 5ad05a55a880134d88afd2c58e40fc8eb550a23434ae298973aca1a1fd612e1d
- Private hooks.py: 1195c22c8fdf6d06ec350702dbe71009eb014776b14d6b2ff9a316bec5e34701
- Private test file: 7fb1e4febb722953407892bb4373658acdcc40aba370ea90d97abdb516892b93
- Installed torch: 2.5.1+cu124; helper signature: (fn, preserve_rng_state=True, context_fn: Callable[[], Tuple[ContextManager, ContextManager]] = <function noop_context_fn at 0x76c17ccaaa20>, determinism_check: str = 'default', debug: bool = False, *args, **kwargs).
- Independent command: .venv/bin/python .cache/checkpoint-precision-review/run_cpu.py; **62 passed in 1.48s**. It loads private modules into a separate CPU-only process, then runs the private checkpoint tests and existing precision/Lab hook tests. Production source was not edited by this reviewer.
- Full pins, official installed helper source hash, and production/original equality snapshot are in the adjacent JSON receipt.

## Verified design boundaries

1. The graph-metadata exemption is limited to the exact Tensor.grad_fn descriptor's __get__ returning an official autograd Node. A Node returned as arbitrary module output remains unsupported; it does not stand in for tensor dtype evidence.
2. The adapter validates torch 2.5.1, official module/name metadata and the helper signature before installation. Missing or incompatible helpers mark observation unknown without altering ordinary training. Imported aliases of the public checkpoint function still reach the module helper.
3. The official non-reentrant generator closes over its fn for recomputation; the public function executes the original function for the initial forward. The wrapper changes only that recompute boundary. It does not replace user computations, alter input tensors, or supply numerical answers.
4. Registration requires an already-observed initial root and operation mode. A bare functional checkpoint whose first forward was never observed cannot become certified merely because recomputation was observed.
5. The default-context recompute function has a real thread-local TorchFunctionMode and a synthetic root when needed. This covers functional-only operations, including internal BF16 operations followed by an FP32 return. Registered-worker routing is active only inside the actual recompute scope; unregistered workers remain unknown.
6. The Lab callback additionally requires its active owner Tensor.backward group, one backward group, and an active graph-task id. Unsupported entry points do not receive implicit authorization or synthetic proof.
7. Normal return, official early-stop, and exceptions leave through finally; mode entry/exit and recompute entry/exit must balance. Real failures remain unknown. The CPU tests check mode cleanup and restoration of original global helper identities.
8. Non-noop context_fn executes unchanged through the official helper without the recompute-function wrapper and records checkpoint_context_unverified. This intentionally leaves custom contexts unknown. The previously identified counterexample uses a custom TorchFunctionMode with FP32 initial computation and hidden BF16 recomputation, both returning FP32 metadata; the actual CPU regression now preserves execution while refusing FP32 certification.
9. Reentrant checkpoint, known compiled wrappers/subtrees and unknown output structures remain unknown. Custom contexts and unsupported variants are not claimed as newly supported.

## Scope that still needs evidence

- The 62 CPU checks include a manually registered worker scope but do not substitute for actual CUDA autograd-worker recomputation. The proposed tiny GPU checks must verify both FP32 and BF16-with-FP32-return behavior and balanced worker-mode cleanup.
- A completed historical 20-update checkpoint reference with unknown precision is not retrospectively converted to a pass. A new validated reference needs its own source/receipt/reader checks.
- TorchFunctionMode observes Python-dispatched torch functions and metadata; opaque C++/compiled/custom operator internals and deliberate hook tampering are outside this protocol's proof. The existing evidence explicitly reports that not every operator dtype is proven.
- Numerical comparison, 512 MiB snapshot readability, full regressions, model-generated repair scores, and the unchanged 6/9 acceptance gate remain separate checks.

## Primary implementation source

The exact supported semantics were checked against the installed torch 2.5.1 implementation and its version-pinned upstream source: [PyTorch v2.5.1 checkpoint.py](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py). The review does not infer current private API compatibility from newer documentation.
