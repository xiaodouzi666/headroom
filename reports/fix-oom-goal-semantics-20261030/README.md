# Clarify goals when a numeric saving is unknown

This is a **report-only candidate**, prepared while R9 runs on frozen commit 5817a72. It has not been applied, tested against a live model, or deployed. No historic diagnosis is changed.

## Observed cause

R9 s1 run `a04d28ed80f640df9a3da447c3d367b9`, `rounds/01/diagnosis.json`, is valid but not ready because `needs_more_info=true`. Its only evidence request asks for a numeric `required_saving_gb` (overall feasibility), although it proposes per-block checkpointing with a positive estimated saving. The host correctly respects that flag and does not create a candidate.

`orchestrator._required_reduction` intentionally returns None when an OOM baseline has no completed measured demand, and for fix-oom generally. `build_diagnosis_messages` supplies the goal string and the null value. The current prompt explains that null means unknown, but does not define fix-oom's completion criterion; its unconditional instructions to cover requested total savings invite treating the deliberately unknown amount as a missing mandatory target. The existing validator only checks coverage when the required saving is known. This is a prompt-contract gap, not a reason to override the model's existing answer or lower the host's acceptance rules.

## Candidate scope

The proposed prompt distinguishes completion (`fix-oom`), an absolute measured peak ceiling (`fit`), and reduction against a completed baseline (`reclaim`). It never fills null with zero or an invented number. For fix-oom only, null by itself is not a prerequisite for proposing a source-supported positive-saving candidate; execution must still prove completion and every original numerical/policy/performance check. Genuine unresolved semantic, update, loss-weighting, reference and policy conditions remain blockers. No model answer, needs_more_info flag, schema, budget, number of rounds or verifier is changed.

This does not cure other s1 model errors, such as conflating checkpointing with batch permission or misstating model dimensions. It does not assert that the unexecuted R9 plan is valid at runtime.

## Focused offline verification plan (not yet executed)

1. Use the real SDK MockTransport and a temporary ledger, with network/GPU/private-state guards. Inspect the actual initial wire prompt for all three target modes, including the 2000-token/False request policy. Assert no new request path or increase in existing supplement count.
2. fix-oom + null: a schema-valid, source-supported positive-saving synthetic plan with no genuine evidence request may remain ready; the same answer with a real unresolved loss/reference prerequisite must remain needs_more_info and must not call PatchEngine. Replay the unedited R9 response and require it to stay valid but not ready (the host must not clear its flag).
3. fit:22GB and fit:22GiB + null: preserve the actual absolute target/unit and no fabricated numeric saving. Separately exercise a known required saving where an insufficient estimate retains the original rejection/needs-more-info behavior. This change cannot replace measured peak checks.
4. reclaim + completed baseline/known required reduction: retain the exact host-calculated reduction requirement. Missing/incomplete baseline plus null must not become a zero-reduction target or a passed reclaim check.
5. Exercise forbidden precision/batch/model changes and malformed evidence references through the original validator; they must remain rejected. A schema-contract error may use only the existing bounded supplement; genuine null-only questions are not automatically rewritten by host code.
6. Run only the affected diagnosis/prompt/orchestrator-focused nodes plus ruff/diff checks after R9 has ended and root applies the reviewed patch. Preserve R9's original prompt hash and results. A later authorized real run is required to judge whether the clarified instructions improve model behavior.

## Applied verification

Applied after R9 finished. The prompt also restricts chunked cross-entropy suggestions to source that already computes cross-entropy; it cannot replace another objective. Independent review passed. Final guarded focused checks: 114 passed in 30.93s. Initial 107 pass/7 failure results remain: these seven stale tests looked for the preceding strategy heading and prior activation-priority wording, already absent from HEAD before this change. The fixture now checks the current source-driven strategy wording; original permission, objective, precision, reference and real-verification checks remain. No diagnosis flag, validator, run result or budget was rewritten. No live improvement is claimed by these checks.
