# Compact bounded diagnosis output — 2026-10-30

## Confirmed failure

Recorded run.failed response-validation histories for R10 s8, R10 nanoGPT and the F8 public s3 smoke contain six Ultra requests. Every one ended finish_reason=length/error_reason=truncated at exactly2,000 completion tokens with zero reasoning tokens. Each case spent the existing single supplement at the identical cap and truncated again. This is a response-length failure, not evidence that six complete answers failed semantic validation. The original raw response text was not retained; the audit uses exact recorded provider validation/usage metadata and saved pre-transport request metadata. No raw body inspection is claimed.

## Change

For the existing explicit FINAL48 2,000-token request policy only, narrow the generated wire schema to at most two supported root causes, one complete independent candidate, three short notes, four stack references per cause, and two evidence-request entries with room to group real prerequisites. IDs/titles/description/risk have bounded lengths. A short output contract is prepended to that policy's system prompt. All necessary setup belongs inside the same candidate; unrelated fallback strategies do not need separate plans.

This never edits or clips a model response. It never changes the host Diagnosis model or validator. Genuine missing prerequisites must retain needs_more_info; if dependencies cannot be fully expressed, the model is told to state incompleteness and remain blocked. Schema errors still use only the original finite supplement and undergo the full policy/evidence validator. Other ordinary/study prompts and schemas remain unchanged. The cap remains2,000, reasoning remainsFalse, and pricing, profiles, funding and call allowances are untouched. diagnose.py integration is owned by the prerequisite-loop agent.

## Verification

Final44 guarded offline cases passed in5.79s: six new schema/SDK/containment cases plus existing FINAL48/profile-policy checks. The real SDK MockTransport checks the wire schema, constant token/reasoning fields, original one-supplement limit and unchanged full policy rejection. It also verifies an empty-plan answer with genuine blockers remains valid but unready. Ruff, formatting and focused diff checks passed.

Initial six-test run retained5 pass/1 fixture failure because the new test file's literal defs key was stripped during creation; restoring the literal corrected the fixture only. Initial policy compatibility run retained34 pass/4 failures: two expectation sites needed the newly selected compact prompt, and the mode dictionaries needed the new additive purpose metadata from the parallel loop change. Updated assertions preserve old cap/reasoning/policy checks and verify ordinary/study schema shape is unchanged while selected2k schema is narrowed.

No provider/GPU invocation, deployment or model-quality result was generated here. Structured size constraints make concise output possible; actual model obedience and successful hardware repair still require a later authorized live check. The old truncated runs and costs remain preserved.
