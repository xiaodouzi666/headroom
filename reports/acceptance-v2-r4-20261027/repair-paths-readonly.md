# Read-only repair-path investigation
These are human feasibility findings, not model inputs or additional benchmark successes. No historical result is rescored.

## s2
The calibrated combined control preserves batch, loss and logical updates: foreach=False plus per-block non-reentrant checkpoint. Re-reading hash-bound historical controls with the current comparator gives baseline 22.919430656 GB, foreach-only 22.564054528 GB, checkpoint-only 22.919430656 GB and combined 18.639258624 GB. The combined control has 20/20 loss scalars, max loss difference 4.76837158203125e-7 within 0.001, and 18.5338% measured throughput regression within 25%.

Current keep rules preserve the foreach-only improvement, then preserve the combined improvement. Checkpoint first alone has zero measured peak improvement and is reverted. This motivates generic multi-component peak reasoning; it does not authorize injecting this patch or control result into the solver. Same-input/effective-batch/objective strong pairing remains unknown; the original scalar acceptance contract does not prove those stronger claims. T2.1 persistent-optimizer-state reduction and bf16 Pareto obligations remain separate.

## s7
The existing AdamW-in-backward human control remains separate. The completed-baseline comparison path uses finite, complete loss series, equal seed and original tolerances; optional pairing/update-set completeness is not in REQUIRED_CHECKS. Missing stronger evidence therefore does not automatically make the original numerical gate fail, and no new gate was introduced.

A possible later product change is a neutral, version/hash-bound restricted optimizer API catalog. It must contain no scenario IDs, historical control patch or measured savings; the model would still independently select and generate a patch, followed by unchanged static and actual GPU validation. The existing research class is not promoted automatically.

An isolated prototype under .cache/optimizer-api-prototype-20261027 uses an explicit backward(loss) then step() boundary, fixed dense FP32 parameter groups and unsupported-use failures. Its initial 31 single-thread CPU tests passed, including 20-step parameter/state comparisons, but this is not GPU acceptance or proof of universal safety. Independent review is pending. No prototype source or catalog is part of R4 inputs.

Public basis: https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html
