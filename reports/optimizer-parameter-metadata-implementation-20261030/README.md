# Native parameter metadata — CPU/offline implementation verification

The new optional observer reads prebound native Tensor/Parameter metadata descriptors for dtype, CPU/CUDA device/index, strided layout and is_leaf. It uses only already-known weak parameter identities and captures no shape, optimizer state, tensor value, alias or native optimizer authentication. Constructor, step-pre and successful-step-post counts remain distinct; constructor-only failure cannot invent updates, and failed native steps have no post observation.

Changed or mixed metadata cannot become a stable all-FP32 assertion. Subclasses, unsupported layouts/devices and unknown identities leave the optional component unknown. Legacy group metadata wins within one shared64KiB raw envelope; the existing3KiB optimizer summary likewise keeps old facts and omits the new component if it cannot fit. Optional errors never replace native returns, errors or existing update/loss capture.

89 guarded CPU/offline tests passed in5.22s, including real installed hooks, the final native post before StepLimitReached, live weak-reference cleanup, no-value/copy/sync/state canaries, changed/unknown metadata, shared capacity limits and actual MockTransport model-request visibility. A subsequent one-hunk exact-class identity hardening received its own1-test metaclass negative in2.05s; the original89-test receipt is preserved. Ruff, format and diff checks passed. verification-v2.json contains final source hashes, and independent-response-budget-review.json records the independent PASS.

No real provider request or GPU workload was performed. New metadata requires a fresh capture and does not backfill historical dtype facts or add a repair success.
