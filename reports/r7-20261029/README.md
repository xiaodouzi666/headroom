# R7: latest recorded repair campaign

The existing F3 campaign finished all 12/12 executions and its service is inactive. This means execution finished, not that all repairs succeeded. The fixed nine reached **1/9 memory targets**, below the unchanged 6/9 requirement. Earlier successes are not added. The two new s2 tiers and HF are separate.

The successful s4 candidate reduced observed allocated peak from **24.768717824 GB to 2.533996544 GB** (89.76936730433156231833859823%). Its baseline ran out of memory after 12 updates; the candidate completed 20. The accepted numerical comparison covers **only the first 5 backward-loss scalars against an original-workload offload reference**, maximum delta 0.0. It does not establish 20-loss, parameter-bitwise or optimizer-state-bitwise equivalence.

The first-round category matched the authored category in **7/9** cases. Requiring a valid saved diagnosis gives **5/9**: s3 and s7 had matching category names but invalid diagnoses. These are diagnosis measurements, not successful repairs.

## Fixed nine

GB uses 10^9 bytes; exact bytes and GiB are in [r7-summary.json](r7-summary.json). An unavailable after peak means no selected successful candidate, not zero.

| Scenario | Result | Before GB | Selected after GB | Initial category / valid | Run |
|---|---|---:|---:|---|---|
| s1_batch_too_big | needs_human | 24.750424064 | unavailable | activations / True | e82cd9646adc44fabb86270591701803 |
| s2_capacity_v2 | needs_human | 22.919430656 | unavailable | optimizer_state / True | 6330dcf4e44b4accb09b73110dda0183 |
| s3_eval_no_grad_missing | needs_human | 2.435717632 | unavailable | activations / False | ce2e4bf037a84b349d178c5bd661230b |
| s4_loss_accumulation_graph | completed · target met | 24.768717824 | 2.533996544 | retained_graph / True | e8213706570e478f9845e49e24c2b54b |
| s5_fragmentation_varlen | needs_human | 5.021758464 | unavailable | activations / True | 0d433ae4d2cd401abd66d6dc6230226f |
| s6_full_vocab_logits_fp32 | needs_human | 21.588379648 | unavailable | temporaries / True | 5a8094e6cadc4013a5fda5e9e5f1bb70 |
| s7_frozen_params_optimizer_state | needs_human | 17.819808768 | unavailable | optimizer_state / False | 966c277a39cf456f92a58b388a501dbb |
| s8_two_models_resident | needs_human | 3.100141568 | unavailable | params / True | f7b8b420a8754127a8e929fe64d81c45 |
| nanogpt | failed | 24.705183744 | unavailable | unavailable / unavailable | b0a316117611448a8688ceb8fea7781a |

## Additional cases

| Additional case | Status | Requirement met | Run |
|---|---|---|---|
| s2-strict | failed | False | e978fa9fb8e3458c9283a05516045f15 |
| s2-allow-precision | needs_human | False | d41abe2170e14888bbe3a5113d24c431 |
| hf-trainer | failed | False | c9bc35c378884595bb06fe8fad85e148 |

These three do not alter the denominator. The new strict s2 tier requires 20 recorded scalar losses to match bitwise, unchanged precision and independent workload pairing; it makes no parameter/optimizer-state bitwise claim. The bf16 tier requires observed bf16 and the existing numerical/safety checks. HF requires its configuration check and actual repair outcome. Failed or unobserved candidates satisfy none of these requirements.

## First-cause counting

Only rounds/01/diagnosis.json is read; its diagnosis.root_causes[0].category is compared by exact string equality with frozen truth when truth_status=authored. The existing campaign raw count does not require valid=true; the qualified count does. needs_more_info and patch readiness are separate. 2/9 were valid, category-correct and ready for patching.

s5 and nanoGPT truth remains unverified; neither is counted correct or incorrect, and the denominator remains nine. The saved round-one result may follow same-round validation repair/supplement requests. It is not necessarily the first raw HTTP response, and later/final diagnoses are never substituted. Summary rows contain the exact diagnosis SHA, field pointers, truth status and validity issue codes.

## Reported API usage and timing

Fixed nine: known actual subtotal **USD 0.65966386**; full actual total **unavailable**; separately recorded resolved billing bound **USD 0.68780824**.

All twelve: known actual subtotal **USD 0.97655704**; full actual total **unavailable**; separate resolved billing bound **USD 1.01159284**. Upper bounds are not actual charges. The records contain 42 Token Factory calls, including 11 unknown-actual calls, 11 bounded calls and 0 unresolved-cost calls.

Sum of recorded per-cell wall times: 1175.055 seconds. Exact whole-service wall time is unavailable after transient-unit collection. These end-to-end cell times include Lab execution, models, checks and cleanup; they are not model latency or TTFT. Exact amounts and token counters remain in the JSON.

## Protocol and evidence

Release: 6c7cde25b7b17ef2aaf236aa2c6543abb57f8499. Prepared pack: runs/final48-repair-preparation-20261029-v4/preparation.json; semantic SHA 808158410158d15f979b1ef21f62f15430f9c122066f3b965180ad6c63ee235f.

Preserved full twelve-cell source: runs/final48-f3/execution-20261029-v1/campaign.json; SHA 09d197bc4be5c4c6c7656ba282b65bd4ce757da90ceb3a99a8ba77482acaec82. All original artifacts remain unchanged; producing this report made no provider/GPU calls.

Fixed-nine controls retain the scenario targets, 20 required updates, seed 1337, at most six rounds and 480 seconds per child. Its policy name strict means the legacy policy, not the new exact-loss20-v1 tier. FINAL48 explicitly caps diagnosis completion at 2000 tokens and requests reasoning off; it differs from older default request settings.

[failure-analysis-first3.md](failure-analysis-first3.md) records the observed early s1/s2/s3 failure paths without changing scores.

## Prepared Results projection — not published

[staging/public-evaluations.json](staging/public-evaluations.json) and its R7 campaign file contain only the fixed nine and pass the current API reader/product projection. The one-entry staging registry must be merged with, not replace, the existing R5/R6 catalog.

Known actual subtotals come from stored usage.known_cost_usd; original driver null fields remain untouched. Actual totals remain null and billing bounds separate. Public first-cause fields preserve raw category matching; the title states 7/9 versus 5/9 valid. No independent full-suite acceptance banner is asserted.

The validation receipt records source/output hashes and projection adjustments; selected captures, patch provenance and compared-loss scope were checked. This is artifact-summary validation, not a rerun or a full HTTP/ledger audit. No online files, services, historical records or gallery cards changed.
