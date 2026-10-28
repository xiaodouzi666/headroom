# F1 diagnosis-only comparison: prepared, not executed

On 2026-10-29, offline preparation produced all **27 requests: nine fixed scenarios × three conditions** from existing real baseline artifacts. There were **zero new model requests, zero GPU executions, and zero searches**. This is an implementation and preparation receipt, not a new diagnosis accuracy or repair result.

Live execution is still pending separate authorization, a correctly bound approved allocation, and approval/enabling of the native-schema admission estimate. The runner being implemented does not establish that the current profile can admit this experiment. Changes to the request implementation or admission/runtime code require rebuilding and reviewing the frozen preparation before execution.

## Fixed comparison

| Condition | Model role | Input |
| --- | --- | --- |
| full_ultra | Ultra, diagnose role | Newly rebuilt snapshot analysis and captured source |
| traceback_ultra | Ultra, diagnose role | Only the captured traceback and memory summary |
| full_super | Super, patcher routing role | The exact same diagnosis messages and schema as full_ultra |

All nine original baseline captures come from R6 (20261027T022818939585Z-151818b1), selected through each job's preserved before-evidence baseline ID. No patched capture is substituted. Captured source hashes, arguments, completion and cleanup metadata, the fixed scenario manifest, and truth-document references are checked and pinned. The historical nanoGPT adapter's recorded /input to headroom_synthetic dataset relocation is verified. No source, dataset, or training workload is executed during preparation.

The fixed scenario order is s1, s2_capacity_v2, s3, s4, s5, s6, s7, s8, nanoGPT. Seven authored categories can be scored against the fixed manifest and README notes where present. **s5 and nanoGPT retain unknown truth and remain in each condition's denominator of nine.**

## Preregistered scoring

The primary outcome is **first-category agreement with authored truth**, separate from reference or complete-Diagnosis validation. It is extracted from the original response only when the response is strict JSON and its first root cause has a category in the shared nine-category enum already defined in the diagnosis prompt. Duplicate JSON keys, nonfinite values, non-JSON prefixes/fences, missing first categories, and categories outside that enum are unknown. There is no JSON repair, substring extraction, supplementary response, or retry.

A response with the right first category and a bad citation still matches the primary category outcome. The runner records references_valid, diagnosis_valid, and valid_correct_first_causes separately, so a failure of those checks cannot silently change the primary numerator. All three conditions share the same JSON fields and category enum. The short condition may cite its real traceback or memory-summary text identities; these are not represented as snapshot stacks. Only each condition's legal evidence-reference enum changes with the supplied material.

The fixed scoring policy and its hash are stored in the preparation and copied into execution output. Future real results must not be used to change this preregistered definition. Missing responses and unknown truths are not zero-filled or removed from the denominator.

## Execution controls

- The shared FINAL48_DIAGNOSIS_ONLY policy fixes at most 2,000 completion tokens and reasoning=False. There is one direct budgeted router.chat per cell, with no diagnosis supplements, schema repair request, patch generation, research, or GPU execution.
- One existing acceptance_run encloses the entire comparison with a requested limit no greater than $1.50. The runner requires strict_reservation before opening the runtime and checks it again before requests; actual_usage stop-line mode is refused. It uses the existing shared spending database, request-wire audit, and cleanup lifecycle rather than creating a new allocation.
- HTTP retries are zero, including the client's built-in retry path. A malformed response is that cell's single failed structured response. An admission refusal is not_dispatched, not a model diagnosis. Uncertain dispatch or unknown charge stops later requests.
- completed_all_requests and within_budget are separate fields. Unknown cost cannot satisfy the combined study_complete_within_budget result. Each condition records provider usage, elapsed time, raw category agreement, validation results, and known/unknown costs. Complete condition means and totals remain null unless all nine observations are available.
- Frozen original inputs, request artifacts, scoring policy, and key implementation files are hash-checked before execution and before each request. An existing execution directory cannot be resumed or overwritten implicitly.
- Full prompts, captured source, responses, and wire evidence stay inside the private ignored runs directory. This public receipt contains summary metadata only.

## Evidence separation and interpretation

Full evidence is freshly rebuilt from captured snapshot and source, rather than reused from historical model annotations or diagnoses. Ground-truth labels and README contents are kept in preparation metadata, outside messages and the schema. Offline canary tests check for both previous-model-answer and README-answer leakage. Only stack identities actually presented in the rebuilt full evidence are offered as legal snapshot references.

The full condition intentionally includes authored synthetic code. Source comments and captured paths can suggest mechanisms, so this is not a blinded benchmark or evidence about unseen repositories. Paths are kept consistent rather than renamed in a way that breaks source references. There is one observation per scenario and condition; the comparison is descriptive, with no replication, significance, or repair-success claim. It does not rescore or replace historical repair campaigns.

Local cl100k input estimates are planning approximations, not provider billable usage or guaranteed cost bounds. In particular, the short inputs are smaller than the available historical Ultra calibration range; that is an extrapolation, not same-range provider verification. Ultra tokenizer observations cannot establish Super's token count. Execution outputs use audited provider usage when available.

## Reproduction and checks

The CLI defaults to preparation:

~~~sh
.venv/bin/python scripts/prepare_final48_ablation.py \
  --output runs/final48-f1/a-new-private-preparation
~~~

Live mode additionally requires --execute, --live-authorized, a frozen --prepared file, an approved --profile, an explicit --daily-limit-usd, and the matching --allocation-receipt. These flags are operator confirmations; existing admission rules still apply. No live command was run for this receipt.

The preserved pre-allocation package is runs/final48-f1/prepared-20261029-v5/preparation.json. Its implementation pins predate the allocation and native-policy integrations, so it must be rebuilt before execution. Its semantic hash, scoring hash, and source-verification summary are recorded in [preparation-check.json](preparation-check.json). Earlier incomplete or superseded packages remain private and are not execution inputs. If shared implementation files subsequently change, this package must be rebuilt before use.

Focused validation: pytest -q tests/test_final48_ablation.py — **17 passed in 36.06s**. Tests use explicitly labeled offline captures and httpx.MockTransport, block DNS/INET and .env access, and exercise the real runtime/router/store/spending chain in temporary directories. They cover 27-request wire behavior, zero retries, strict budget-mode rejection, pre-dispatch admission refusal, unknown cost, tampered files, missing inputs, independent category/reference scoring, duplicate/non-JSON responses, and prepare-only CLI default. No full regression suite was run.

## Final rebuilt package after integration

The executable preparation candidate is now runs/final48-f1/prepared-20261029-v6/preparation.json, with semantic SHA-256 **5e868343794e6e32d4d7fdbc682d1c15ae79b986b791714878e4dc4c3eaad965**. The [final check](final-preparation-check.json) verifies all 27 requests, 102 original input pins and [28 implementation pins](final-implementation-pins.json), including the allocation binding, native admission, request audit, Store and numerical-policy dependencies. The scoring hash remains **fca45c3be1332b0da3aa23d7bacea438a1cf34942d5853cda1b01da18df0cf7e**.

All 27 request files, ordered message serializations and schema serializations are unchanged from v5; v5 remains preserved. The real input review also confirms that README truth documents and historical annotations do not enter the nine full requests. The narrower capture source selector still includes original Python comments and paths, whose interpretation limits are described above.

The [final offline cost preview](cost-preview-final.json) recomputes the same hypothetical net total, **$1.4487068**, from the current calibrated count artifact and the previously recorded candidate tariffs. It repairs the source binding in a new receipt because the older cost-preview document referenced a stale count-file digest. This is an estimate with a retained Super bound, not actual usage or a guaranteed Ultra billing ceiling; Super price evidence must still be refreshed before profile activation.

The allocation revalidation now also requires the run's claim to remain active. A concurrent-once check confirms only one of two simultaneous F1 claims succeeds. A separate fixture changes the approved profile after the first response and confirms the second request is stopped. The allocation focused suite passed 12 tests in 9.44s, followed by that additional per-request test passing in 2.30s. These overlap earlier validation and are not added to produce a cumulative test total.

No amount authorization, actual allocation, production profile, new ledger or live model execution was created by this rebuild. Other CLI/R7 and public-service allocation integrations remain separate work.
