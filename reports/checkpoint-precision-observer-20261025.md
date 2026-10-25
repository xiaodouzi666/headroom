# Checkpoint precision observer repair, 2026-10-25

The precision observer now supports the reviewed PyTorch 2.5.1 non-reentrant checkpoint path with the default context. Two real CUDA regressions passed: an FP32 functional-only checkpoint and a checkpoint that performs BF16 operations internally and returns FP32. Both ran 20 complete logical updates on a different CUDA autograd worker thread with an actual TorchFunctionMode active before the recomputation function body began. This is observer validation, not a model repair or MVP success.

## The retained failure

Full s1 resource run c079b92990a74fe1833b68fce0abe021 completed 20 updates in 84.157571 seconds with peak allocation 14,297,204,736 bytes. It correctly remained ineligible: precision was unknown (3,840 unsupported-structure and 46,080 cross-thread observations), historical original-baseline fingerprints were absent, and later stat inspection found a 1,284,045,979-byte snapshot exceeding the unchanged 512 MiB analysis gate.

The v2 receipt, raw snapshot, and failed result are preserved. Neither all-visible-FP32 metadata nor a matching seed upgrades that historical proof.

## Reviewed implementation

[PyTorch 2.5.1 checkpoint source](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py) uses a non-reentrant generator whose recomputation closure calls its fn argument. The adapter wraps that argument only; imported aliases of the public checkpoint function still resolve the same module helper. The original public forward still invokes the original function.

The adapter requires the exact reviewed runtime and helper signature. Missing or incompatible private APIs disable this optional evidence rather than breaking ordinary training. The original functions are restored at capture teardown.

An original checkpoint forward must already be enclosed in a real root observer and operation mode. Recompute-only evidence cannot certify an unseen functional forward. Before the actual recomputation function executes, the adapter enters an explicitly provisioned thread-local observer and TorchFunctionMode. It observes function arguments, all exposed Python-dispatched operations in the executed body, and normal returns. Thus functional operations outside module calls are covered. Module hooks route only to the currently active child observer; an unregistered thread still fails closed.

The official early-stop exception records coverage of the prefix that actually executed and exits the mode in finally. A genuine function exception records failure and also exits. Metadata-only access through the precise Tensor.grad_fn descriptor may return a valid autograd Node; this is recorded as recognized graph metadata. An arbitrary module return containing such an object remains unsupported.

Non-default user context_fn values execute with the original function and original context ordering, and are explicitly unknown. This avoids claiming coverage inside arbitrary user dispatch modes. Reentrant checkpoints, unobserved initial forwards, unregistered worker forwards, missing scopes, unknown outputs, and unsupported compiled paths remain unknown. The observer does not claim every C++ or custom operator dtype is proven.

The hooks change is limited to adapter installation/restoration, the verified recompute callback, and active-observer routing. AST comparison confirms all 11 logical-update functions, including recorded_backward, are unchanged. Audit: reports/research-solutions-20261025/checkpoint-precision-logical-update-audit.json.

## Verification

The final private implementation received independent review and an independent 62-test CPU run. After production integration, 95 focused tests passed in 17.02 seconds, including the real CPU reference pipeline now explicitly requiring complete FP32 precision. Tests exercise functional-only bodies, genuine BF16 followed by a float32 return, user contexts, the dispatch-mode hidden-precision counterexample, official early-stop, real exceptions, TLS cleanup, function restoration, missing/incompatible private APIs, and fail-closed cases.

GPU preregistration: runs/research/checkpoint-precision-gpu-20261025/plan.json. Maximum two runs, each at most 60 seconds and 20 updates; no model APIs or payments.

| Condition | Run | Result |
|---|---|---|
| FP32 functional checkpoint | bd0b3ec1b5b34879957ab304246b187b | Complete FP32, actual worker operation mode, balanced cleanup |
| BF16 operations with FP32 return | b620bf0e944448e4ba701a022aab5c10 | Complete BF16; default policy correctly rejects the precision change |

Both runs observed 20 initial forwards and 20 recomputation entries. Both proved the recomputation ran on another thread and that its function body already had the operation mode installed. The combined summary is passed=true at runs/research/checkpoint-precision-gpu-20261025/summary.json. GPU cleanup and absence of compute processes were confirmed.

The subsequent full-size s1 v3 resource qualification also passed: run b6ea4ee5fd3144a3adae57ffb05f9d8f completed 20 updates in 115.271469 seconds, with complete FP32 precision, 3,840 actual worker recomputation entries/exits, 3,860 balanced operation-mode entries/exits, and no observer errors. The lossless encoded snapshot was 27,640,271 bytes and passed the unchanged 512 MiB reader and original analysis entry. The full record is in reports/s1-checkpoint-reference-20261025.md. This does not establish the missing historical baseline fingerprints or count as a model success; those require the fresh formal baseline and candidate.
