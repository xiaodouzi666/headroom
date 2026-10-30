# R13 first-two dependency audit — read only

Both terminal jobs failed the existing dependency contract after their one prerequisite-review supplement. This is not a new campaign score or a basis to change acceptance.

- s1 final plan contains `p1` (checkpointing), but request0 declares `current_plan` with `blocked_plan_ids=[]`. Its text still asks about gradient accumulation if pursued. The missing nonempty current ID triggers `INVALID_EVIDENCE_DEPENDENCY` at `/evidence_requests/0`.
- s2 final plan is empty, yet both requests declare `current_plan` with empty IDs. No existing current ID exists, so both requests violate the same rule.

The final diagnosis artifacts contain precise validator feedback: s1 allowed IDs[p1], s2 allowed IDs[], with the scope contract. That feedback was produced **after** the second model response. The shared supplement was already consumed by prerequisite review, so this final feedback was not sent as a third call.

The actual second request did already contain the general scope rule, but its `current_plan_ids` metadata described the **prior** diagnosis: s1[grad_accum], s2[cfg1]. Full first-pass valid-needs output is not retained in the inspected job artifacts or call rows; only its declared requests/IDs survive inside the review metadata. The audit does not reconstruct unsaved full first-plan text.

All four Ultra request bodies include the new `owned_source_verified` operator catalog and policy.allow_batch_grad_accum=true. s2's first question incorrectly says that policy permission is undeclared, while binding its question to unrelated runtime evidence. Catalog/source metadata did not weaken or bypass the validator.

Minimal generic next-change suggestion: clarify the existing review's prior-ID scope and add a compact output self-check. Dependencies must be rebuilt from the replacement response's own plan; an empty plan cannot use current_plan; questions concerning a discarded alternative are not automatically current-plan blockers. The model must still identify any genuine current/overall unknown and preserve needs accordingly. Do not auto-clear needs, rewrite dependencies, relax validation, or add a third call. Source changes and further live work remain the root agent's later decision after R13 terminates.

See audit.json for exact retained first-pass review metadata, final dependencies, issues and artifact hashes. No code, profile, credential, ledger, GPU or model execution was changed by this audit.
