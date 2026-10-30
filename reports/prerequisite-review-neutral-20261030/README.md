# Neutral prerequisite review eligibility — 2026-10-30

A structurally valid diagnosis with `needs_more_info=true` and a nonempty plan may now use the existing shared, unused prerequisite-review allowance even when its requests are empty or no scoped reference can be located. Only a fixed neutral instruction and counts are added; unlocatable question text and old free-form notes are not copied. No source, runtime value, reference or answer is fabricated.

The existing path for scoped references still uses credential-aware validation metadata. If scoped requests exist but all such metadata is withheld/unavailable, the helper still returns no review. A ready diagnosis or absent plan remains ineligible.

The neutral instruction asks the model to independently recheck its original context and either declare a real dependency or derive a different complete supported plan. It conditionally clarifies that `goal=fix-oom` with `required_saving_gb=null` is an unset numerical savings threshold, not itself missing measurement or proof of success. The host never changes needs flags, binds a null reference, removes requests or bypasses original schema, policy, saving or numerical checks.

The router is unchanged. This uses its existing shared supplement counter and one-review flag; default allowance1 still allows at most2 provider requests including the initial request. A used validation/response repair leaves no additional default allowance. With an explicitly larger allowance, one existing validation repair may be followed by exactly one neutral review; repeated needs then stops, and no fourth call is added by the review loop. The old compatibility test for that deliberate case was updated only after root approval.

101 focused guarded offline cases passed (prerequisite review, bounded diagnosis repair, evidence blockers, validation feedback). Dedicated tests cover empty requests, R9-style null savings references, unsafe-text omission, strict byte bounds, limit0/1/3, repeated true needs, independently model-proposed readiness and an already-spent supplement. The first run's single legacy call-count expectation failure is retained in focused.log/focused.xml; focused-final.log/focused-final.xml contain the passing result. Ruff, formatting and git diff check passed.

No live provider, GPU workload, production database change, deployment or spend was performed. Source is frozen for the next run's preparation pins; this report is offline behavior evidence, not a new acceptance score.
