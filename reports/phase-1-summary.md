# Headroom Phase 1 — MVP v3 checkpoint

All code, artifacts and runs remain on azuki. This is an unaccepted checkpoint; the complete original goal remains unfinished.

## MVP v3 — second repair iteration, failed (2026-10-25)

Source commit: 1a935c8716cee05edf2b1ad1d3e37d35f52a5ef3. Original nine-case manifest and thresholds were unchanged. All nine harness child workers recorded worker_exit_code=0 and cleanup_verified=true in matching campaign/report timing records; this is not a CLI fix invocation. The campaign exited1 because the original success gate failed. Five cases ran with models; four later cases were operational admission stops with zero GPU/model work, not four observed model-quality failures. Fixed denominator: target0/9; first cause3/9 true,1/9 false,5/9 unknown.

| Scenario | First cause | Target | Model calls | Cost upper USD | Wall seconds | Outcome |
|---|---:|---:|---:|---:|---:|---|
| s1_batch_too_big | yes | false | 27 | 0.12610878 | 83.213 | diagnosis_needs_more_info |
| s2_fp32_adamw_1b | yes | false | 7 | 0.07339602 | 57.965 | diagnosis_needs_more_info |
| s3_eval_no_grad_missing | no | false | 8 | 0.08762380 | 44.520 | diagnosis_supplement_exhausted |
| s4_loss_accumulation_graph | yes | false | 31 | 0.16205718 | 96.722 | max_rounds_reached |
| s5_fragmentation_varlen | unknown | false | 5 | 0.05945934 | 34.306 | diagnosis_needs_more_info |
| s6_full_vocab_logits_fp32 | unknown | false | 0 | n/a (no calls) | 0.954 | runtime_not_ready |
| s7_frozen_params_optimizer_state | unknown | false | 0 | n/a (no calls) | 0.930 | runtime_not_ready |
| s8_two_models_resident | unknown | false | 0 | n/a (no calls) | 0.922 | runtime_not_ready |
| nanogpt | unknown | false | 0 | n/a (no calls) | 1.061 | runtime_not_ready |

Across54 Super responses, all finish=stop and reported reasoning_tokens=0. Fifty-two nonempty diff strings had no physical linefeeds and were rejected before application; a separate empty diff was rejected as NO_CHANGE. The other empty-diff CLI-only proposal was statically accepted but the actual s5 candidate rejected its unsupported --grad_accum_steps=4 argument (SystemExit2). Thus git-apply-plus-compile success=0 and verified repair success=0. Workflow status completed on s4 means loop completion only.

Exactly78 model calls were joined to their authoritative budget attempts: known0.50587762USD plus5 settled Nano missing-cache bounds0.00276750USD yields conservative0.50864512USD; actual total remains null. Current runtime cumulative conservative2.03679916USD leaves7.96284988USD under the unchanged9.99964904USD allocation. Historical unknown reservations remain occupied.

Evidence: reports/live-campaign-20261025/mvp-v3-audit-v2.json; mvp-v3-repair-review.json; mvp-v3-repair-findings.md; mvp-v3-protocol-stop.json; mvp-v3-profile-restored.json. Final original repair iteration3 is being prepared; it is not an accepted result.

## Top three remaining failure modes

1. The 52 nonempty Super diff strings lacked physical line boundaries; explicit array transport is under development. A separate empty diff was rejected as NO_CHANGE. Prior reasoning exhaustion was removed, with all54 current responses reporting zero reasoning tokens.
2. Diagnosis can request more information or propose an unsupported CLI; original policy and runtime checks reject or stop rather than inventing success.
3. Independent original gates remain open: s2 optimizer fraction39.8715%<40%, s2 fit22 already met atbaseline and default-precision/bf16 requirements conflict. The owner has retained the original plan for later discussion.

## Model and service evidence

Original T0.4 all60 samples are retained. Ultra accepted500029 server input tokens; the900k request returned429 and its unknown1.049344USD reservation remains occupied. T1.3 authentic268920-token evidence passed. T1.4 latest diagnosis-only batch has7/8 first causes and8/8 valid references, but complete readiness/policy acceptance remains false. Super JSON/tool capability is proven separately from patch validity. Nano actual cost may be unknown when cached-token usage is missing; only independently verified upper bounds certify expense limits. Tavily component/live cache proof remains accepted; genuine repair-linked research acceptance is still open.

## Next original-plan step

Finish and test the explicit line-array protocol, perform one generic Super transport/application component check, then run the third and final allowed MVP repair iteration. Keep all prior failures,9-case denominator,.6USD/480s per-run limits and original target/first-cause gates. Under PLAN§0.6, if that final iteration still misses MVP, stop for Frank's decision; do not silently start unrestricted extra repair rounds. No recharge or allocation increase has occurred.
