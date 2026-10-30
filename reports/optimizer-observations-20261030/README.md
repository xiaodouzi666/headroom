# Selected optimizer observations: independent bounded evidence

This fixes a real prompt-evidence omission. The existing Lab capture already contains optimizer parameter/update observations, but the old named-input adapter returns early for unsupported AST families. The new runtime_optimizer_observations context is independent of that adapter and reaches both existing Ultra diagnosis and Super patch request paths.

## Boundaries

- A selected host Lab result must have a valid run identity. Its captured source digest must match exactly one retained entrypoint source item; an unrelated candidate/source cannot fill the current context.
- Only bounded counts, requires-grad totals, reported optimizer class tags from a fixed whitelist, and actual recorded update-set coverage are summarized. No weights, raw tensors, source text, free-form capture prose, errors, model-layer names, environment or files are read.
- Original capture/observation completeness flags remain explicit. Partial records and zero-step OOM never become twenty completed updates. Per-record catalog coverage does not identify named layers or prove workload/objective/numerical equivalence.
- Optimizer classes remain reported tags, not authenticated implementations; group hyperparameters, precision, clipping and other helper preconditions are not inferred.
- The named-input status stays unsupported where unsupported. Existing 3 KiB summary, 16 KiB execution, 8 KiB evidence-availability and 64 KiB shared context bounds remain.
- The evidence-availability catalogue adds exactly three text entries (summary, parameters, updates); runtime_values_verified remains false. No policy, validator, patch schema, observer, optimizer, target source, tool/model-call cap or acceptance gate changed.

## Verification

121 guarded focused tests passed in 4.94 seconds across the new optimizer tests, runtime-input observations, solver context, owned operator metadata and evidence blockers. Ruff, formatting and diff checks passed. The guard denies real credentials/profile/databases, network, GPU jobs and service commands.

The initial log is retained: 78 passed and one integration-fixture failure, because the synthetic baseline fixture omitted a source digest. Only that fixture was completed before the final passing run.

retained-r13-wire.json is an offline construction from the unchanged R13 s7 report, not a new model/GPU execution. Its source-bound summary exposes 34 catalogued parameters with requires_grad=true, 1,075,970,304 elements and twenty complete update sets covering all 34. Named-input observations remain unsupported. Generic MockTransport integration tests independently show that both fresh real SDK request paths receive the identical selected optimizer summary without extra calls.

No provider call, GPU execution, deployment or new target success is claimed. R13 historical results remain unchanged.
