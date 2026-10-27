# s1/s2 failure-stage investigation and generic repair guidance — 2026-10-27

Scope: offline inspection and generic solver-context improvements. No model requests, GPU runs, campaign changes, ledger/profile mutations, gate changes, commits, or modifications to historical evidence. The original 6/9 target remains unchanged.

## Verified artifact findings

- R3 campaign: runs/evaluation/live/20261025T121115251021Z-2fe7da84/campaign.json.
- R3 s1 job d52ca1fc2f394a92b6c82918b25d8a43, round 1: a whole-stack checkpoint candidate OOMed during backward recomputation. The candidate peak was 24.784536576 GB and completed zero updates. The original first-forward activation footprint was incorrectly called retained_graph. This alone is not evidence of cross-update graph retention.
- R3 s1 rounds 2 and 3: patch generation was rejected by TRAINING_TRUNCATED before candidate execution. Inspection of the round 2 final diff confirms that it removed the completion emission and corrupted a step emission. This is a legitimate static rejection; no policy relaxation was made. Later diagnosis text confused the retained baseline OOM with new candidate execution and described unavailable numerical comparison as a numerical failure.
- R2 s1 job adc7e667237f46a5a9f71a619fab5c31, round 2: the historical successful candidate checkpointed each block, completed, measured 14.297204736 GB, and obtained identical loss comparison with max_loss_delta 0 against the host baseline-derived reference. This is historical evidence only and was not injected into solver prompts or counted toward a future campaign.
- R3 s2_capacity_v2 job de1e5c248c51415abd63c47cc6554600, round 1: changing AdamW foreach to false improved peak from 22.919430656 to 22.564054528 GB, below the required saving and still above the 22 GB target.
- R3 s2 round 2: the microbatch candidate completed, but produced 40 backward scalars for 20 updates. Its comparison was n/a with max_loss_delta null and loss_series_aligned_to_updates false, not a measured tolerance violation. Its memory target also remained false. This does not establish an accepted repair.

## Implemented generic changes

- headroom/solver_context.py: bounded outcome_stage metadata labels patch rejection before execution, absent execution evidence, failed/incomplete/completed candidate execution, and numerical-comparison availability. Missing or contradictory evidence remains unknown; retained baseline state is never consulted when deriving candidate outcome.
- headroom/diagnose.py: includes the same candidate-only stage interpretation in verification feedback.
- headroom/prompts/diagnose.md: clarifies stage attribution, ordinary activation lifetime versus unintended graph retention, bounded checkpoint segments and recomputation peaks, optimizer-state versus transient-workspace lifetime, and conditional per-parameter update/gradient release prerequisites. The guidance preserves actual parameter updates, data, precision, accumulation, scheduler/state semantics and unchanged verification gates.
- tests/test_solver_failure_stages.py: regressions cover delivery through both mock solver boundaries, retained OOM attribution, missing/contradictory artifacts, unavailable versus real numerical comparisons, malformed fields and completion states.

No scenario ID, historical answer, exact successful patch, human-control result or numeric target was added to the generic guidance. Unknown literal batch size is not treated as a universal blocker for optimizer changes whose relevant source/update prerequisites are independently established.

## Validation

Guarded focused command:

    .venv/bin/python -B reports/mvp-v7-integration-20261025/full_guarded.py tests/test_solver_failure_stages.py tests/test_solver_context.py tests/test_verification_feedback.py

Result: 41 passed in 5.28s. The guard independently confirmed blocked credentials/profile/database access and DNS in parent and spawned process; CUDA visibility was disabled. This checks offline behavior and request delivery, not real model repair quality or GPU acceptance.

## Public-source basis

- [PyTorch checkpoint documentation](https://docs.pytorch.org/docs/2.14/checkpoint.html): checkpoint execution may recompute saved intermediates; explicit non-reentrant mode and preserved RNG behavior matter. Sequential checkpointing exposes segment boundaries. The inference that a very large region can retain a high recomputation peak is consistent with the observed R3 failure and must still be measured for each candidate.
- [PyTorch AdamW documentation](https://docs.pytorch.org/docs/2.14/generated/torch.optim.AdamW.html): foreach optimizer arithmetic can require extra tensor-list intermediates; disabling foreach can reduce workspace but does not remove persistent parameter/state storage.
- [PyTorch optimizer-in-backward tutorial](https://docs.pytorch.org/tutorials/intermediate/optimizer_step_in_backward_tutorial.html): earlier per-parameter updates and gradient release can reduce simultaneous gradient memory, under compatible accumulation/update semantics. This is a conditional generic hypothesis, not a verified repair for either retained scenario.

## Remaining work for the coordinating agent

Resolve billing authorization/accounting before any live call. Review these changes with other generic patch-feedback improvements, run integrated checks once, and then use a new bounded real campaign under unchanged manifests/gates and gift-only bounds. A future 6/9 claim must come from that campaign, not pooled historical successes.

## Follow-up: strict precision prose false positive

The plan validator previously rejected any BF16/FP16/autocast token, including existing-dtype facts. The precision intent predicate now evaluates each local clause and mention, exempting only explicit preservation, bounded source-fact/lifetime descriptions and single negated actions. Unexplained affirmative low-precision proposals and mixed sentences with a positive change remain rejected; same-clause conversion/use actions cannot hide behind an existing/current qualifier. numerics_impact other than none remains blocked under strict policy. No applied-source, observed-precision or numerical gate changed. This does not validate incorrect lifetime semantics such as deleting a value before its consumer.

Added tests/test_diagnosis_precision_intent.py, including positive/negative/mixed/double-negation examples and real validate_diagnosis calls. Final guarded focused run across precision intent, diagnose schema/contract, bounded repair and failure-stage tests: 150 passed in 1.78s. No network or GPU calls were made.
