# V5 generic solver feedback review for the frozen V6 implementation

Read-only review of recorded V5 failures and the current V6 call chain. No model/GPU run, source edit, gate change, or fixture edit was performed. V6 has not yet produced a nine-case result. These are candidates for a final permitted repair only if V6 still fails, not evidence of future success.

## Confirmed missing context

1. **Ultra lacks structured effective invocation/configuration.** headroom/orchestrator.py:533-545 adds search state to retained evidence; headroom/diagnose.py:251-266 supplies goal, policy, required saving, evidence Markdown and bounded verification feedback. Neither carries current_args/effective command. NanoGPT's saved evidence includes all 336 lines of train.py and 330 of model.py, but displays source defaults batch_size=12, gradient_accumulation_steps=5*8, 12 layers and compile=True. Actual V5 execution used batch 32, accumulation 1, 24 layers and compile=False. Round 1 planned 12→8/40→60; round 3 again called 12/40 current configuration and proposed disabling compile. Super already receives base_cli (headroom/patch.py:618-627), so this omission is specific to diagnosis. A source comment showing an example command is not actual invocation evidence.

2. **Neither model receives actual rejected candidate diff/source on the next outer round.** round_verification_feedback (headroom/diagnose.py:210-235) carries a path string in change.patch_artifact plus measured summaries and exception fields. After REVERT, current_result/current_source remain the selected baseline. The diagnosis call (diagnose.py:440-446) supplies no tools; the router forwards default tools=None (headroom/llm/router.py:95-138). Patcher calls likewise supply no file-reader tools (patch.py:636-642). The separate research loop is for Tavily and does not give these calls an implicit local artifact reader. The artifact path is an identity reference, not delivered candidate bytes.

3. **Super also lacks detailed verification feedback already given to Ultra.** orchestrator.py:379-390 reduces history to six fields: number, fix_id, decision, reason, memory_improvement_pct and current_throughput_regression_pct. Only this history, new diagnosis, goal/search state and research summaries reach Super (orchestrator.py:731-742). verification_feedback goes to Ultra at line 580, but not Super. Thus an outer-round retry loses candidate finite-loss failure, exception, parameter delta, individual failed checks and numerical comparison details. Within one PatchEngine repair sequence, structural details and the previous proposal ARE retained (patch.py:834-847); this working inner loop is distinct from missing outer-loop feedback.

4. **Outer-round structural rejection loses its specific detail.** Saved PatchAttempt has bounded detail and policy issues, but diagnostic feedback after SOURCE_EDIT_REJECTED generally has only reason, no verification/patch artifact and failure=null. Carrying the final structural rejection would distinguish copying/coordinate errors from an unsuitable plan. V6 IDs address old-text copying but do not deliver this missing outer-round detail.

## Recorded V5 examples

| Case | Actual result | Implication |
|---|---|---|
| s1 | Two applied microbatch candidates still OOM at zero updates, peaks 24.8507/24.8517 GB. Round 3 changes optimizer cadence to every fourth outer iteration; round 4 accumulates unweighted mean losses. | Actual failure was OOM. Candidate diff/update semantics would help next planning; no measured numerical divergence exists because neither completed. |
| s3 | All 137 source lines were supplied, including training leading dimension 1. Round 2 sliced using unrelated batch=16, making empty slices/NaN; one update then failure. Round 3 received exception but emphasized secondary 6791% timing regression. | V6 train/eval/runtime-failure prompt changes are appropriate; original source was not absent. Deliver rejected candidate and failed checks to both models. |
| s4 | Six identical backward(retain_graph=True)→backward() patches. Twenty updates at 2.5340 GB, 89.77% lower peak, but original scalar delta 0.052162>0.001 with reference batch 1 vs candidate batch 8. | Repeated identical candidates waste search. Original gate remains failed; scalar mismatch does not establish changed training mathematics. V6 already asks not to repeat unchanged failures. |
| s7 | Head-only optimizer reduced peak 49.67% but scalar delta was 3.3520. Subsequent requires_grad filters left all parameters eligible and peak unchanged. Final diagnosis conflated those edits. | Candidate identity/diff must accompany results. eval() is not freezing; comments about intended workload do not authorize changing the actual trained parameter set. |
| s8 | Round 1 comment-only. Round 2 CPU teacher assignment was overwritten by original later GPU assignment. Round 3 deleted teacher and correctly failed parameter count. Final diagnosis guessed why CPU move failed. | Actual diff would expose overwrite. Preserve correct parameter-count gate; no device-filter accounting defect was found. |
| nanoGPT | Checkpointed model.py observed 21.506 GB but still OOM on 6.14 GiB request, zero updates; later planning retained source-default config. | A lower peak without completion is not target success. Planner needs effective invocation and failed candidate details. |

Source coverage: s1 123/123 lines, s3 137/137, s7 156/156, s8 151/151, nanoGPT train/model 336/336 and 330/330. This does not establish that arbitrary larger programs fit the source budget.

## Narrow generic options if another repair is justified

- Add bounded typed execution context to diagnosis and patch context: current effective arguments, repository identity/command, retained source identity and already-recorded workload observations. Distinguish actual parsed/observed values from source defaults. Serialize allowlisted fields only; no arbitrary environment or credentials.
- Reuse existing bounded verification summaries for Super. Add separately labelled rejected-candidate evidence: effective CLI/env changes, diff hash, bounded public diff or changed-source excerpts, specific structural failure and candidate exception. Preserve candidate_selected and selected_after_round; rejected candidate bytes never replace retained-source context.
- Read only supervisor-owned paths under the assigned run root with existing regular-file/no-symlink/containment primitives. Cap file count, UTF-8 bytes and field lengths. Missing/truncated evidence must have explicit availability and omitted-byte metadata; include identity hash where available, never imply snippets are complete. Diff/source/exception/model notes remain untrusted data; policy and instructions stay separate.
- A deterministic duplicate-candidate check could key actual resulting source bytes plus effective CLI/env and relevant execution/verification identity, rather than fix_id/title. It may skip an already-observed identical rejected GPU candidate or request a different plan; never promote failure to success or conflate changed policy/input/seed/hardware. This is a candidate improvement, not implemented V6 behavior.
- Separately inspect unconditional first-plan-step selection at orchestrator.py:636: later items are not attempted as a fixed ordered list; every outer round re-diagnoses and selects the new first item. This can work with richer feedback but currently permits first-item repetition. Do not silently combine unverified plans or expand round/budget limits.

Meaningful tests should capture actual fake-router requests: rejected empty-slice candidate reaches both models with finite-loss/exception failures; CPU-assignment overwrite is distinguishable from deletion; effective CLI overrides are delivered without changing source; duplicate detection distinguishes changed CLI/env/policy/seed; unavailable/truncated artifacts remain explicit unknowns. These are delivery/control-flow tests, not GPU success claims.

Original PLAN, fixed nine cases, numerical tolerance, parameter preservation, required completed updates, budgets and failed history remain authoritative.

## Evidence pins

```json
{
  "campaign": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/campaign.json",
  "campaign_sha256": "90c49ba7f937ce3c9057a767f82243ba94299d412ba6d21037f3a0a0389c7ff7",
  "reviewed_utc": "2026-10-25T03:08:32.685357+00:00",
  "source_pins": {
    "headroom/orchestrator.py": "7d96fb02b7abdcc4a93b5d6c504579fe4d129d8394f8994a6fe7c0e202d5a718",
    "headroom/diagnose.py": "06d0ffa6043247a6edc3120a5d86b76617aa2ab4285d0f6397c7ddd403cbb33b",
    "headroom/patch.py": "7a829eeb4f4684aeba6fc00dfd82a7c9445dc7732c4fb6ac9dc33537fa694f70",
    "headroom/prompts/diagnose.md": "ac99b11525468cfd5cd463bcbdaf203d96c113e5d2d8e95abb3968d45542a18d",
    "headroom/prompts/patch.md": "00b2301734a21a4056ebe671dc2c8473cad2fe5df18d2ff4f5e3c61d9bc70e82",
    "headroom/prompts/patch_fix.md": "fb293c4f69897e54c8354a8f0711e11aad9a0c29b7490310a44924e9d5d04ba3",
    "headroom/llm/router.py": "eb8f8bc0528c2cc94eb0ab2a87b9d27ba4a17d1ceefb8d75882aabf070c99292"
  },
  "case_report_pins": {
    "s1_batch_too_big": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/84fb5dc741fa4931a4eddf961819da7b/report.json",
      "sha256": "408072dfae13129e85e9535ed4cb7ea0c779ca43828485577f02ede454172d56"
    },
    "s3_eval_no_grad_missing": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/46383653e0034d39a815f4d30c590247/report.json",
      "sha256": "ee433b8c6337dc2606a7dcaa01b2f0ecdbebff9169a911e5ef0ac207cd16eac5"
    },
    "s4_loss_accumulation_graph": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/dab41b8349cc4ee48780d6e911f9883b/report.json",
      "sha256": "d449e7b7fd42f033dd418d65aca066a0fe8de22cedad37a1deec1c4209f1e987"
    },
    "s7_frozen_params_optimizer_state": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/80fc991e01b9464880778c5d058d2dbc/report.json",
      "sha256": "b3d346ccbd56058cc93b3173c9b65d0cb392da2fae65f83e1a4815d4eb1fce2e"
    },
    "s8_two_models_resident": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/890bd925382746d78ab16cffd36fc815/report.json",
      "sha256": "fa2bb5a5034b93d713b902cf9c815771f706a2e7a7061202f8d15a93470e2382"
    },
    "nanogpt": {
      "path": "runs/evaluation/live/20261025T022454741538Z-8e6e085d/jobs/dfd0e468099042c8916253616d8a07e3/report.json",
      "sha256": "f41e8da405f2e73696152328c6ebba9c8de2fed4104a584b03837b876bb7ddd9"
    }
  }
}
```
