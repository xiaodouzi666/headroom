# Optimizer group options: review-only proposal

Status: **not applied**. Only this report directory has been written. The frozen
production hooks and optimizer observation sources retain their original bytes.

The current selected s1 capture completed zero optimizer calls and zero logical
updates. Its initial Parameter catalog is available, but scalar group options were
never recorded; no source default can be promoted into an observed value.

The proposed patch samples actual `optimizer.param_groups` after successful base
`Optimizer.__init__` return and immediately before an optimizer call. It records
only the allowlisted built-in numeric/boolean/None values and exact two-element
`betas`/`etas`/`step_sizes` containers. A tensor, custom object, string, mapping,
non-finite float, oversized integer, or unknown group option remains unsupported.
No `.item`, tensor conversion, value copy, arbitrary repr, secret-key/name copy,
optimizer state mutation, or GPU operation is introduced.

Constructor and step-pre records have distinct stages and monotonically numbered
weak optimizer identities. Repeated unchanged observations deduplicate; a changed
LR/configuration is a new observed configuration. Metadata capacity failure only
marks this optional metadata incomplete and stops it; native optimizer exceptions
and deadline BaseExceptions retain their original behavior. No additional logical
update, successful optimizer call or mathematical equivalence is inferred.

`runtime_optimizer_observations` continues to require the selected Lab run ID and
exact retained entrypoint digest before exposing any options. Legacy captures stay
`not_captured` without backfill. New metadata is summarized within a 1024-byte
component and the existing **3072-byte** total cap. If it does not fit, it is
explicitly omitted/unknown. The parent optimizer/coverage status is unchanged.
The same existing execution context is delivered to Ultra and Super; their JSON
output schema, call count, token caps, prices, policy and verification rules stay
unchanged. The existing generic parent evidence reference is still sufficient;
no new availability claim or validator relaxation is proposed.

`proposed.patch` changes only `headroom/lab/hooks.py` and
`headroom/optimizer_observations.py`. Full review copies live under `draft/`.
`test_draft.py` performs 19 standard-library-only contract checks against those
copies; it does not install the hook or exercise a real target. The old zero-step
result is replayed read-only for exact parity. A **synthetic** option extension
checks byte bounds without modifying that historical result. The 34-child/680-call
shape is also synthetic metadata, not newly executed optimizer updates.

Before production use: independently review the patch, add and run installed-hook
CPU integration tests plus existing optimizer observation/catalog regressions,
then refresh preparation implementation pins. No model/GPU outcome is claimed.
See `verification.json` for immutable hashes, exact bounds and unrun checks.
