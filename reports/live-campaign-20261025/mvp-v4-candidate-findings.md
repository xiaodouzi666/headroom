# MVP v4 — actual patch, candidate, and reusable subgate evidence

As of 2026-10-24T23:35:05.935995+00:00. Read-only review of frozen source `78a83df86b181674c37509b192517a9d4101ad92` and campaign `runs/evaluation/live/20261024T231940915002Z-2098d11d/campaign.json`.

**The final nine-case MVP did not pass: 0/9 targets, 7/9 first causes matched and 2/9 first causes remain unknown. One partial-improvement configuration is retained (s8 round 2), but it does not meet its 20% reclaim target.** All nine cases are real live evaluation attempts; no generic patch component, offline fixture, or manual baseline is counted as a successful scene.

This report is independent of the fixed-nine/CLI/financial audits. It made no model, Tavily or GPU invocation, did not curate a replay, and changed no production source, existing run, profile or ledger.

## Nine-scene facts

| Scene | Patch attempts | Invalid diff / apply failure / response reject / applied | Real git apply + compile | Verified candidate | Final selected configuration | Target |
|---|---:|---|---|---|---|---|
| s1_batch_too_big | 21 | 20/0/0/1 | Yes | r3: oom, completed=false | None | false |
| s2_fp32_adamw_1b | 4 | 0/4/0/0 | No | None observed | None | false |
| s3_eval_no_grad_missing | 24 | 21/3/0/0 | No | None observed | None | false |
| s4_loss_accumulation_graph | 24 | 19/5/0/0 | No | None observed | None | false |
| s5_fragmentation_varlen | 12 | 9/3/0/0 | No | None observed | None | false |
| s6_full_vocab_logits_fp32 | 0 | 0/0/0/0 | No | None observed | None | false |
| s7_frozen_params_optimizer_state | 16 | 15/0/1/0 | No | None observed | None | false |
| s8_two_models_resident | 9 | 4/4/0/1 | Yes | r2: completed, completed=true | r2; applied=true; completed=true | false |
| nanogpt | 0 | 0/0/0/0 | No | None observed | None | false |

The totals are **110 attempts = 88 invalid-patch rejections + 19 application failures + 1 rejected model response + 2 applied patches**. There are 109 observed nonempty normalized diffs: 107 rejected and 2 applied. The remaining rejected response has no available normalized diff; it is not counted as empty or nonempty. There are zero CLI-only applications. This distinction avoids confusing total rejections with nonempty rejected diffs.

Every recorded patch round had one initial attempt plus at most three fixers. Every observed Super call had completion usage at or below 4,000 tokens. Both successful application records used `git apply --3way` with **direct fallback**, followed by `py_compile` exit 0; neither is described as a successful three-way merge.

## The two actual GPU candidates

- **s1, round 3, reverted:** peak remained 24.750424064 GB, reduction 0%, candidate OOM at zero optimizer updates, `loss_equivalence=n/a`, `target_met=false`. Parameter count, observed FP32 policy and hardware checks passed, but numerical acceptance did not. The applied file still invokes the full-batch forward at line 99. Inserted microbatch code begins at line 124, after `main()` and the OOM re-raise; it did not replace the failing training path.
- **s8, round 2, kept:** 20 optimizer updates completed; peak 3.100141568 → 2.989897728 GB (3.55609050689649% reduction), throughput regression 0.9417549149311144%, scalar loss delta 0, parameter count unchanged at 747474432, observed FP32 unchanged. `memory_target=false` because the required reduction is 20%. The retained change creates the teacher on the GPU and only then calls `.to('cpu')`; subsequent offload cannot erase the earlier historical allocation peak. Rounds 3 and 4 were reverted while round 2 remained selected.

s8 `loss_equivalence=identical` is the original-plan full-backward scalar-series comparison. `same_inputs`, `same_effective_batch` and `same_objective` remain unknown, and `loss_comparable=false`; the report does not claim proven paired workload equivalence. The completed candidate contains `StepLimitReached` at the intended 20 updates, which is recorded successful step completion rather than an unexpected crash.

Correction to an intermediate monitoring message: s8 round 2 was **keep**, not revert. The primary machine-readable review already preserved the correct selected-round/applied/completed fields; this final text is authoritative.

## Reusable original Phase 1 gates

- **T1.5:** only **2/8** synthetic scenes have recorded application plus compile, below the original ≥6/8 requirement. The ≤3-fixer and 4,000-output constraints are observed, but the s2 false-precision-policy negative case is not newly executed by this campaign.
- **T1.6:** s1 still OOM and s3 has no applied candidate; both specified positive gates remain failed/unproven. The halved-model negative GPU demonstration was not executed in this review.
- **T1.7:** s1 persisted 49 events and 28 model calls, including the required ordered baseline/evidence/diagnosis/apply/verify/done sequence. This is evaluation-harness evidence, not an observed literal `headroom fix` CLI invocation or a new browser-started SSE run. The separate CLI audit preserves that distinction.
- **T1.8:** all nine reports have 14 level-two headings. The original `scripts/check_report_numbers.py` was invoked in-process against each existing report pair under network/credential/GPU denial: all nine returned 0. In a fresh temporary work copy, s8's selected cumulative patch also passed an actual `git apply --check --verbose` with exit 0 and `Checking patch train.py...`; the source and copied files stayed byte-identical. The other eight have no selected retained patch, so their selected-patch check is n/a. These checks do not turn s8 into a target success.
- **T1.9:** nanoGPT ended `needs_human` without a patch or candidate. Its selected peak, selected completion, diff≤60/train-config-only, and loss gates remain unknown; no literal repository CLI invocation is claimed. Its cost ceiling alone cannot satisfy this task.
- **T1.10:** both actual candidates preserve parameter count; this is reusable positive evidence. The already recorded full-suite honesty negatives are separate evidence and were not rerun or upgraded into a live cheating-patch experiment here.

The initial JSON records that report-number and standalone selected-patch checks had not yet been invoked. The two later supplementary receipts record those subsequently completed checks without rewriting the earlier snapshot.

## Actual Tavily research — T2.2

SQLite was opened with `mode=ro` and `query_only=ON`. Its nine `research` records match the reports' saved operations: eight search operations (including one cache hit) and one extraction; eight actual API requests; seven recorded credits. Every run stayed at or below four actual API requests.

- s4 performed an actual model-directed search and successful extraction of `https://docs.pytorch.org/docs/2.5/checkpoint.html`, with `torch_version=2.5.1+cu124`, `version_match=true`, 21,242 extracted characters. The response explicitly recorded zero extraction credits; this is not an assumption that all extraction is free.
- s5 reused s3's matching cache key and original request ID, with `cache_hit=true`, `api_calls=0`, `credits_used=0`. This proves the repeated-query cache subgate within this real campaign.
- The required complete gate is still **not passed**: s1 Sources has no checkpoint documentation URL, and s5 Sources has no PyTorch CUDA-memory-management URL. Research results in another scene do not substitute for those scene-specific requirements.

## Nano annotations — T2.3

| Synthetic scene | Complete labels / requested | Scored known-heuristic stacks | Matching stacks | Recorded agreement |
|---|---:|---:|---:|---|
| s1_batch_too_big | 10/10 (completed) | 8 | 0 | 0.000000% |
| s2_fp32_adamw_1b | 14/14 (completed) | 11 | 0 | 0.000000% |
| s3_eval_no_grad_missing | 0/18 (failed) | unknown | unknown | unknown |
| s4_loss_accumulation_graph | 15/15 (completed) | 10 | 0 | 0.000000% |
| s5_fragmentation_varlen | 0/17 (failed) | unknown | unknown | unknown |
| s6_full_vocab_logits_fp32 | 0/15 (failed) | unknown | unknown | unknown |
| s7_frozen_params_optimizer_state | 0/16 (failed) | unknown | unknown | unknown |
| s8_two_models_resident | 14/14 (completed) | 11 | 3 | 27.272727% |

Four of eight synthetic scenes have complete validated labels; the other four failed with missing, duplicate or unrecognized stack IDs and remain in the fixed eight-scene denominator. On the completed subset only, 3/40 scored stacks agree (7.5%); this conditional statistic is not an eight-scene accuracy claim. No synthetic scene reaches 80%. Unknown heuristic categories are excluded only from each scene's already-defined scored-stack set, not from the scene denominator.

All eight synthetic Nano calls have certified exact-cost or verified-upper-bound cost ≤$0.02. Where exact actual cost is unknown it remains null; cost certification does not turn failed labels into valid annotations or satisfy accuracy. nanoGPT has 19/19 validated labels and 2/18 agreement, but it is outside the original eight-synthetic denominator.

## Cross-checks, limits and artifacts

The separate fixed-nine/financial audit reports 165 model calls, known-cost subtotal $1.037464332 plus five Nano upper bounds totaling $0.00236772, for a conservative campaign total $1.039832052. Exact campaign actual cost remains unknown. No budget reconciliation or charge state was modified by this review.

No replay curation was performed. There is one real retained partial improvement suitable for transparent inspection, but no target-passing repair; any later publication must preserve the selected configuration, failed target, numerical limitations, provenance and access controls.

Authoritative detailed evidence:

- `mvp-v4-candidate-verification-review.json`: nine scene rows, all 110 classified attempts, actual verification facts, research and Nano records, and input artifact hashes.
- `mvp-v4-candidate-verification-supplement.json`: nine successful original report-number checks and hashes/line markers of the actual s1/s8 candidate sources.
- `mvp-v4-s8-selected-apply-check.json`: pinned original source, selected patch, temporary work copy, no enclosing Git repository, actual check command/exit, and unchanged source/copy hashes.
- `mvp-v4-audit-v2.json`, the CLI-exit supplement and `mvp-v4-finance-review.json`: separate original fixed-nine, literal-CLI distinction, and financial reviews; those remain the authority for their respective scopes.

Original thresholds and PLAN were not changed. This is the final original repair iteration's evidence, not a claim that the overall goal or submission is complete.
