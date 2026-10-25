# Lab logical update observation — 2026-10-25

## Problem and public basis

The official [PyTorch optimizer-in-backward tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html) attaches a post-accumulate-gradient hook to each parameter and calls its optimizer there. Counting every optimizer callback as a training update can stop a run after only part of a full backward. The public recipe justifies supporting this execution pattern; it does not establish numerical correctness for arbitrary training code.

[PyTorch autograd documentation](https://docs.pytorch.org/docs/2.14/notes/autograd.html#evaluation-mode-nn-module-eval) also distinguishes evaluation mode from gradient control. No requirement to preserve the existing trained parameter set or training objective was relaxed by this instrumentation change.

## Implemented observation contract

- Ordinary optimizer calls outside autograd retain their existing logical step boundary. Multiple backwards followed by one outer optimizer step remain one update.
- Optimizer calls within one outermost observed Tensor.backward are collected. They count as one logical update only after backward returns successfully and every observable participating leaf Parameter was updated exactly once. All callback work, including cleanup after optimizer.step, finishes before the limit can stop the target.
- A bounded traversal of grad_fn.next_functions identifies participating leaf Parameters without reading saved tensors. Parameter weak references, process-local IDs, and before/after version counters identify observed updates. This observes mutation; it does not prove algebraic equivalence.
- Actual optimizer pre/post call counts, optimizer classes, updated parameter identities, logical update basis, and coverage status are retained. No synthetic aggregate optimizer or pairing proof is created. Grouped execution supplies unknown pairing where the existing adapter cannot establish its contract.
- Partial or repeated coverage, an exception after a partial update, missing version evidence, restricted inputs, higher-order/nested/concurrent ambiguity, and unknown graph-task boundaries cannot count as a completed grouped update. Direct autograd.backward/autograd.grad callbacks without the observed Tensor.backward boundary fail closed.
- Ordinary closure-based updates and calls with no observed gradients keep legacy counting but report parameter coverage as unknown. They cannot claim a complete empty update set.
- Observation bounds are 65,536 graph nodes, 4,096 participating/observed parameters, 8,192 process-local identities/calls per grouped update, and 65,536 recorded update-set members. Exceeding supported evidence bounds does not manufacture completeness.
- Only snapshot.json serialization switches to compact JSON; values, arrays, final newline, and the existing 512 MiB downstream parse gate remain unchanged. Other metadata stays formatted.

Coverage is scoped to participating graph leaves. Unused module Parameters are not invented as expected participants; intentionally optimizing only a subset of participating leaves remains unsupported. Tensor version counters and hooks are cooperative runtime evidence, not authenticated protection against adversarial code. No acceptance threshold, numerical gate, old score, model plan, provider, or scenario-specific repair was changed.

## Validation and freeze

Production hooks were kept unchanged throughout the memory calibration. After explicit GPU/Lab release, the candidate was installed atomically after checking the original hash.

- Original hooks SHA-256: 9be7e0adb7ef30a3cb6ad888098f50954944af8db3d09c7a198208ce5556bcc7
- Final hooks SHA-256: 1a717ff197bc33f5b2c6462b9a9f9fcd1db6de583845a095b9f5b9be584cb7d0
- Host runtime: real PyTorch 2.5.1+cu124, tests restricted to CPU.
- Production import focused suite: tests/test_lab_logical_updates.py, tests/test_lab_hooks.py, tests/test_precision.py, tests/test_verify_parameters.py — **73 passed in 2.80 seconds**.
- Ruff and git diff --check passed.

The new suite includes a two-parameter Adam control: 20 complete backward updates, 40 successful parameter optimizer calls, both state counters at 20, exactly 20 loss samples, and exact parameter/loss equality with 20 ordinary full-model Adam updates. A callback failure during the twentieth backward retains only 19 completed logical updates even though one parameter has already advanced. Other cases cover partial/duplicate updates, optimizer/callback exceptions, direct autograd, missing graph-task evidence, ordinary gradient accumulation, callbacks finishing before the limit, unused Parameters, closures, and exact snapshot JSON values.

An independent review identified the ordinary empty-gradient/closure receipt issue; it was fixed and covered by three additional real CPU cases before production freeze. The existing pairing timing unit test uses an old private post-hook seam; its owner is adapting it to the internal recording seam without changing its timing assertions or production behavior.

These are CPU instrumentation and compatibility results. They do not claim a successful GPU repair, changed nine-scenario accuracy, numerical equivalence for arbitrary optimizer-in-backward code, or completed competition acceptance. The parent coordinates remaining GPU/resource and full-suite evidence separately.
