# F3b real feature checks

The two planned CLI snapshot attempts completed and were settled, but neither delivered a usable diagnosis. The required **at least 1 of 2** truth-matching diagnoses is therefore **not met**. The Web upload also completed but returned no usable diagnosis. Watch evidence is still pending.

| Feature | Run | Observed result | Usable diagnosis | Unverified patch | Actual model usage, USD net |
| --- | --- | --- | --- | --- | ---: |
| s2 snapshot CLI | 81149070970843cf912a127b671e00e9 | needs_human / diagnosis_unavailable | No | No | 0.040679 |
| nanoGPT snapshot CLI | 5177f870aa7240b48ec2ea4e94789086 | failed / diagnosis_unavailable | No | No | 0.039002 |
| nanoGPT snapshot Web | 8fcd4570a96145ceb0244c0190d95635 | needs_human / diagnosis_unavailable | No | No | 0.01439744 |
| Watch | Pending | No acceptance asserted | — | — | — |

The two CLI calls cost **$0.079681 net**. Including the independent Web transport attempt, the three actual Ultra calls returned HTTP 200 and cost **$0.09407844 net** in total. Each remained within its $0.25 child allowance and the plan's $0.30 per-attempt limit. All three cleanup receipts and financial settlements are complete. CLI exit status, file creation, HTTP 200 and settlement do not establish feature acceptance.

## What failed

**s2:** the provider returned structured diagnosis content that passed JSON/schema parsing. Its first category was optimizer_state, matching the scenario's stated primary cause. The complete diagnosis was rejected because /evidence_requests/0 used blocking_scope=overall_feasibility while also naming current plan IDs p1, p2, and p3. The existing validator correctly reports INVALID_EVIDENCE_DEPENDENCY. Missing target/step/device information was mentioned by the model, but missing information alone was not the rejection condition.

A separate manual content check found a memory-quantity error: the response called the LayerNorm stack's **16.62 GB cumulative allocations** a temporary peak. The same input evidence records **557,056 bytes** live at the reconstructed peak and **16,620,584,960 bytes** allocated over the capture for that stack. A matching first label does not make the full response accurate or valid.

**nanoGPT:** one billed response was recorded (33,002 input tokens, 2,000 completion tokens), but the router/LLM path failed before any diagnosis-validation artifact was written. The handler retained only diagnosis_unavailable. Neither the raw response, finish reason nor exception reason was saved. Reaching the 2,000-token cap is consistent with truncation, but does **not** prove it; malformed JSON/schema, filtering or another LLM error cannot be distinguished. There is no delivered diagnosis and no patch: the non-null patch object is only {status: unavailable, diff: null}.

**Web:** the browser submitted the same nanoGPT input bytes exactly once and received HTTP 202. The worker returned a parsed diagnosis, but rejected it for EVIDENCE_AVAILABILITY_CONTRADICTED, NUMERICS_CHANGE_FORBIDDEN and BATCH_CHANGE_FORBIDDEN. It used 33,002 input tokens (26,112 cached) and 1,458 completion tokens. Upload transport succeeded; the requirement to display a valid diagnosis card did not. This reuses the nanoGPT scenario and does not add a third truth case. The final recorder receipt and restored-service receipt establish the terminal UI observation and cleanup. An earlier local multipart-guard rejection forwarded zero submissions and is not a model attempt.

## Confirmed engineering issues

All three retained requests tell the model that the completion cap is **16,384 tokens**, while the actual request sets **2,000** and disables requested thinking. The snapshot worker builds its messages without the explicit request policy and then sets the smaller limit on router.chat. This is a confirmed mismatch, not a demonstrated causal explanation for the nanoGPT failure.

The minimal proposed fix is to resolve the typed profile request policy once, pass it to message construction, and use its same cap/reasoning for dispatch. A focused real-runtime MockTransport test should assert the prompt and body both state 2,000, only one cap field is sent, and conflicting policies fail before dispatch. Existing legacy defaults must remain unchanged.

The snapshot worker also discards the specific LLM/response-validation failure reason and attached response. Proposed follow-up: retain bounded private reason/finish_reason/response hash/usage, with a separate private response where permitted; public errors stay sanitized. Test truncation, malformed JSON, schema mismatch and filtering separately without introducing retries or accepting invalid output.

The main agent has chosen to keep the frozen F3b/F5 attempts on the same source revision. Future fixes and offline tests will be separate evidence, not retroactive success for this run. This audit makes no code changes and no retry.

## Evidence boundaries

- The s2 input is a previously completed 20-update capture, **not an OOM capture**. It can test optimizer-state diagnosis, not an OOM recovery claim.
- The nanoGPT input contains an OOM before a completed update, but its root-cause ground truth is unknown. Do not score an unverified category as correct.
- The analyzer reconstructs peaks of 22,919,430,656 bytes (s2) and 24,705,183,744 bytes (nanoGPT), with peak_is_exact=false for both. Uploaded snapshots do not supply authenticated hardware provenance or independent peak counters.
- Uploaded source was context data. This feature did not run the user's script or perform hardware repair/loss verification.
- The earlier [snapshot engineering report](../snapshot-diagnosis-20261029/README.md) documents offline malicious-pickle and bounds tests. Those checks were not rerun here and are not live model acceptance.
- [receipt.json](receipt.json) contains exact source/artifact hashes, call metadata, source-pointer rules and acceptance state. It intentionally excludes prompts, raw responses, credentials, owner sessions and the budget database.

The Watch row will be updated only from its own terminal artifacts and actual trigger/publication evidence. The fixed two-snapshot denominator and unknown-truth boundary remain unchanged.


## Watch terminal update

This update supersedes the earlier pending Watch statement; the original receipt.json and its three-snapshot figures remain unchanged.

The actual command **python train.py** for s1 encountered a confirmed CUDA OOM and automatically created repair run **a5c98d7d4be845288b4b4d40cd1e6435**. The capture finished with zero completed updates and verified cleanup. This establishes the OOM-to-diagnosis trigger.

The repair did not succeed. Round 1 produced a candidate with a measured peak reduction from **24.750424064 GB to 17.112406528 GB (30.860148%)**, but its loss changed (maximum delta **2.5490983724594116**) and verification rejected it. Its comparison basis was the original plan's first five backward scalars, not all 20 losses. Round 2 ended in **ResponseValidationError**, with no patch recorded. No candidate was retained, and target_met remained false. The original controller exited 1, confirmed terminal execution/cleanup, and settled the child.

There were **7 model calls**. Watch's exact total cost is **unknown**: the known subtotal is **$0.12101216 net**, while **$0.12329942** was conservatively charged against its cap. The entire four-slot F3b group is financially settled: known actual subtotal **$0.21509060**, exact total **unknown**, charged total **$0.21737786**, within the **$1.00** group cap. Settlement does not change the snapshot diagnosis failures.

Watch trigger acceptance is met. The full Watch requirement also calls for its real run to appear in Verified runs or Results; that publication has not yet been independently verified here. Repair failure is permitted by the Watch criterion and is retained honestly.

[watch-receipt.json](watch-receipt.json) contains the terminal, round, usage and financial evidence with artifact hashes. This audit made no retry, source change or model/GPU dispatch.
