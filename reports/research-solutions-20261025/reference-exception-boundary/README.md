# Explicit reference failure boundary

Read-only review found a reachable verifier path: the selected original_saved_tensor_offload strategy can decline unsupported/unbound sources without executing a reference. It then supplies reference=None to compare_runs. The repository exception previously excluded only the checkpoint strategy, allowing this offload path to borrow the legacy no-reference exception and report target_met=true.

The added negative tests reproduced the actual issue before the fix: 2 failed and 26 passed. The two failures were direct comparison and verify_script with the repository scope; the latter executed only its mocked candidate and zero reference/fallback calls. This uses offline measured fixtures and no model/GPU requests.

The production fix changes one predicate: repository_no_reference_exception now requires reference_strategy == LEGACY_STRATEGY. Legacy repository acceptance with no reference remains available under its original rules. Missing or failed references under either explicit strategy cannot use that exception. Provided failed legacy references remain ineligible as before. Scalar tolerances, candidate precision policy, memory/performance thresholds and historical evidence are unchanged.

The bounded matrix covers legacy/offload/checkpoint, standard/repository, and None/error/timeout/oom references. The actual runner negative covers both explicit strategies in both scopes. Focused comparison, offload, checkpoint, runner and reference-option tests passed: 173 in 29.16 seconds. Ruff passed. The search keep/revert consumer relies on the generated numerical basis and exception check; it does not independently recreate this exception.

Files before-fix.txt, after-fix.txt and receipt.json retain the evidence. This comparison change does not alter the s1 v3 resource experiment or any source hash pinned by that experiment. The earlier full-suite receipt belongs to the earlier source version; a new full regression is required for this fix. No historical score is rewritten.
