# F1 diagnosis-only ablation

In this single 27-request pass, the two full-evidence conditions each matched the authored first-cause category on 6 of the fixed nine workloads; traceback and memory-summary evidence matched 2 of nine.
Requiring the complete diagnosis to pass reference and policy validation reduces the correct counts to 4, 2 and 4, respectively; all 27 requests cost USD 0.69374342 before tax.
These are descriptive results for this protocol, with two unknown truths and no repeated trials; they do not establish model superiority or successful repairs.

| Condition | Calls | Primary category matches | Valid correct diagnoses | Mean provider input tokens | Mean elapsed (s) | Net model cost (USD) |
|---|---:|---:|---:|---:|---:|---:|
| Full evidence + Ultra | 9/9 | 6/9 | 4/9 | 46,495.78 | 8.498 | 0.464260 |
| Traceback + memory summary + Ultra | 9/9 | 2/9 | 2/9 | 11,009.22 | 4.691 | 0.09866092 |
| Full evidence + Super | 9/9 | 6/9 | 4/9 | 46,495.78 | 5.681 | 0.1308225 |

The denominator stays nine in every column. s5 and nanoGPT have unverified truth, remain null in the data and do not contribute a correct match. All nine calls in each condition have observed usage and elapsed time, so the complete-condition means above are available.

## Protocol and scoring

One request per scenario/condition; 27 real requests in fixed scenario order, with Full Ultra, restricted Ultra, then Full Super for each scenario. The evidence was rebuilt from the preserved R6 baseline captures; no workload, patch or research tool ran for this study.
The shared output cap was 2,000 tokens, reasoning was requested off, and retries/supplements were disabled. The same first-category enum and scoring rule applied to all three conditions.
Primary category matches use strict JSON and the first root-cause category only. A matching category can coexist with an invalid plan or evidence request; the secondary column requires full diagnosis, reference and policy validation.

Scoring policy: first-category-agreement-v1. SHA256: fca45c3be1332b0da3aa23d7bacea438a1cf34942d5853cda1b01da18df0cf7e.
Preparation semantic SHA256: ae7ae3e60f0deb7bb1ee13a5d1db45c6529ecb561946962912ab8f93355d26c1.

## Per-scenario observed scores

Each cell is primary / valid-correct. Yes means an observed match, no means an observed mismatch or failed full validation, and unknown remains unscored. Missing denotes no valid first category could be extracted.

| Scenario | Authored truth | Full Ultra | Restricted Ultra | Full Super |
|---|---|---|---|---|
| s1_batch_too_big | activations | yes / yes | yes / yes | yes / no |
| s2_capacity_v2 | optimizer_state | missing / no | no / no | yes / yes |
| s3_eval_no_grad_missing | activations | yes / yes | yes / yes | yes / no |
| s4_loss_accumulation_graph | retained_graph | yes / yes | no / no | yes / yes |
| s5_fragmentation_varlen | unknown | unknown / unknown | unknown / unknown | unknown / unknown |
| s6_full_vocab_logits_fp32 | temporaries | yes / no | no / no | no / no |
| s7_frozen_params_optimizer_state | optimizer_state | yes / no | no / no | yes / yes |
| s8_two_models_resident | params | yes / yes | no / no | yes / yes |
| nanogpt | unknown | unknown / unknown | unknown / unknown | unknown / unknown |

Full Ultra had two truncated responses (s2 and nanoGPT). Its category-matching s6 and s7 answers failed evidence-dependency/range validation. Full Super matched s1 and s3 categories but proposed disallowed model/input reductions. Those answers remain primary matches and are excluded from valid-correct counts.

## Measurement limits

Input counts are provider-reported prompt tokens, not local estimates. Elapsed time covers each router call plus local validation; it is not TTFT or a pure server inference measurement. Costs use observed token usage at net model rates, exclude tax, and include the recorded cache discount; 34,816 cached tokens occurred in restricted Ultra.
All calls have settled known cost; runtime cleanup reported no errors. Total observed usage was 936,007 input tokens and 31,209 completion tokens. The earlier archived preflight attempt made zero calls and is excluded from the 27-request study.
This is one fixed-order, non-blinded pass over seven authored truths and two unknown truths. It provides no statistical significance, general model ranking or new hardware repair result.

## Evidence

Run: bc8659e89a214473b2f9fc24a86eccda. Service headroom-final48-f1-20261029-r1 reached inactive/dead with Result=success and exit status 0. The source artifacts were read after completion and rehashed before writing this report.
The public [ablation.json](ablation.json) contains protocol, observed metrics, score codes and source hashes only. Complete prompts, provider response text, request evidence and credentials are not copied here.

| Source artifact | SHA256 |
|---|---|
| runs/final48-f1/prepared-20261029-v8/execution/ablation.json | 72af6e63444d721156adfc33ce64dd74ec45c75ddbabd633744170e0c65bfc8f |
| runs/final48-f1/prepared-20261029-v8/execution/runtime/runtime.json | 449d5434190958d25eabeb6c7f7f6fd23a2c446b4d1665d3450b5a34b00b8709 |
| runs/final48-f1/prepared-20261029-v8/preparation.json | 0fd07f892f83bd38a4cc59a28934f4a645264d18d99bfb2eb03505a692af74fa |
| headroom/acceptance/final48_ablation.py | c66ccec9325542a6d104286ea8c20c98f8ac11283068cb541d76c9c336bd81ed |
| eval/mvp_phase1_v2.yaml | 2b5d669700c68737abaa258a7e8eb26a683baaa4e39d378a9d98a88bda2f1c20 |
| headroom/evaluation.py | 4a5ddd06ec86012d7769cfda9da6e76aff98090f27b8f6bdba04fbf3a6bca6ed |

The original response artifacts remain private under runs/; their SHA256 hashes and row pointers are listed in the public JSON for traceability. The failed zero-call preflight artifact is also identified separately.
