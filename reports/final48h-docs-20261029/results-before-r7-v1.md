# Results

## Summary

These results cover the recorded nine-scenario evaluations completed on 2026-10-25 and 2026-10-27.

The latest evaluation met **2/9 memory targets** and produced **3/9 valid correct first-cause diagnoses**, with **5 unknown first causes**. Across the separate evaluations, **5 distinct scenarios have a recorded automatic memory-target success**: s1, s2, s3, s4, and s8. The best single evaluation reached **3/9**.

### Historical results

Each successful row selects the lowest recorded peak after repair, using the latest evaluation to break ties. Unsolved rows use the latest baseline. The s2 row uses the larger AdamW workload. Memory values are **decimal GB = bytes / 1,000,000,000**.

| Scenario | Expected cause | Selected diagnosis / memory target | Observed peak before → after (GB) | Numerical evidence | Date / source commit |
| --- | --- | --- | --- | --- | --- |
| s1: oversized batch | Activations | Correct / target met | 24.750 (OOM) → 14.297 (−42.23%) | Identical first 5 scalars vs. baseline-derived checkpoint reference; pairing matched. | [2026-10-25 / 3e8281e](../reports/acceptance-v2-r2-20261025/README.md) |
| s2: AdamW capacity | Optimizer state | Correct / target met | 22.919 → 18.639 (−18.67%) | 20 scalars within tolerance, not identical; input/batch/objective pairing unknown. | [2026-10-27 / a42fb7c](../reports/acceptance-v2-r5-20261027/README.md) |
| s3: evaluation autograd | Activations | Correct / target met | 2.436 → 0.648 (−73.38%) | 20 identical scalars; input/batch/objective/seed pairing matched. | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |
| s4: retained graphs | Retained graph | Correct / target met | 24.769 (OOM) → 2.534 (−89.77%) | Identical first 5 scalars vs. original-workload offload reference; pairing matched. | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |
| s5: variable lengths | Fragmentation candidate; unverified | Stopped before diagnosis / no selected repair | 5.022 → — | Not established | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |
| s6: full-vocabulary logits | Temporaries | Stopped before diagnosis / no selected repair | 21.588 (OOM) → — | Not established | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |
| s7: frozen optimizer parameters | Optimizer state | Stopped before diagnosis / no selected repair | 17.820 → — | Not established | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |
| s8: unused teacher model | Parameters | Correct / target met | 3.100 → 0.122 (−96.07%) | 20 identical recorded scalars; input/batch/objective pairing unknown. | [2026-10-27 / cfeb67f](../reports/acceptance-v2-r4-20261027/README.md) |
| pinned nanoGPT | Unverified | Stopped before diagnosis / no selected repair | 24.705 (OOM) → — | Not established | [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) |

Selected successful runs:

| Scenario | Run ID | Baseline → candidate optimizer updates | Compared loss scalars | Parameter count before = after |
| --- | --- | ---: | ---: | ---: |
| s1: oversized batch | adc7e667237f46a5a9f71a619fab5c31 | 0 → 20 | 5 | 101,007,360 |
| s2: AdamW capacity | 2942b1e3d8e34ead80baef0cdc468753 | 20 → 20 | 20 | 1,141,338,112 |
| s3: evaluation autograd | 84f929ba8ace49b3829df6455419641d | 20 → 20 | 20 | 37,791,744 |
| s4: retained graphs | b7f348d0dc8d423f8076b81fd2c15375 | 12 → 20 | 5 | 50,374,656 |
| s8: unused teacher model | d10adf0ffac74dcf8d874a460a2a3628 | 20 → 20 | 20 | 747,474,432 |

### Latest evaluation — 2026-10-27

Source commit: 4f4e67dca3d031dcf64983fe0e5f467a765c5c80. All nine scenarios remain in the denominator.

| Scenario | Valid correct first cause | Result | Run ID |
| --- | --- | --- | --- |
| s1: oversized batch | Yes | Needs more information; no selected repair | 810e0803757740dfaaa65fd4ecd2adf9 |
| s2: AdamW capacity | No | Needs more information; no selected repair | 05ab015193c1458392b4082629dd5050 |
| s3: evaluation autograd | Yes | Memory target met | 84f929ba8ace49b3829df6455419641d |
| s4: retained graphs | Yes | Memory target met | b7f348d0dc8d423f8076b81fd2c15375 |
| s5: variable lengths | Unknown | Stopped before diagnosis/patch | 450d5f43de35422a8c5323c6b0b0b61b |
| s6: full-vocabulary logits | Unknown | Stopped before diagnosis/patch | 986a46de5be54e279a64afc42a59dbf5 |
| s7: frozen optimizer parameters | Unknown | Stopped before diagnosis/patch | c3fded26d11846038f9134855c8983eb |
| s8: unused teacher model | Unknown | Stopped before diagnosis/patch | a7e2bff86ce849eea3c0798d2097c642 |
| pinned nanoGPT | Unknown | Stopped before diagnosis/patch | 9445bf3c9fa040738f23a78ee582b724 |

### Does the snapshot matter?

Same nine saved workloads, diagnosis only, one request per condition:

| Diagnosis input / model | First-cause matches | Valid and correct | Mean input tokens | Model cost (USD) | Mean elapsed |
|---|---:|---:|---:|---:|---:|
| Full evidence + Ultra | 6/9 | 4/9 | 46,496 | $0.464260 | 8.498 s | <!-- numbers: ablation.full_ultra -->
| Traceback + memory summary + Ultra | 2/9 | 2/9 | 11,009 | $0.09866092 | 4.691 s | <!-- numbers: ablation.traceback_ultra -->
| Full evidence + Super | 6/9 | 4/9 | 46,496 | $0.1308225 | 5.681 s | <!-- numbers: ablation.full_super -->

First-cause matches compare the first category in strict JSON with the reference cause. Valid and correct also requires the full diagnosis, evidence references and policy checks to pass. Full evidence produced more category matches in this pass; these are diagnosis results and do not add automatic repair successes.

This was one fixed-order pass without repeated trials. The two workloads with unconfirmed reference causes remain in the denominator. Elapsed time includes the router call and local validation; it is not time to first token. Costs use observed usage and include cache discounts, before tax.

All 27 requests completed. Total model cost was $0.69374342 before tax. [Experiment details and measured data](../reports/ablation-20261028/README.md).

### Cost and time

The following table lists the API usage supported by complete records and the sum of recorded end-to-end run times.

| Date / source commit | Memory targets met | Valid correct first causes | API usage with complete records (USD) | Sum of run wall time (s) |
| --- | ---: | ---: | ---: | ---: |
| [2026-10-25 / ce38d3c](../reports/acceptance-v2-20261025/README.md) | 1/9 | 6/9 | 0.62027986 | 435.79 |
| [2026-10-25 / aa42ef5](../reports/acceptance-v2-r1-20261025/README.md) | 3/9 | 5/9 | 0.79450272 | 902.17 |
| [2026-10-25 / 3e8281e](../reports/acceptance-v2-r2-20261025/README.md) | 3/9 | 4/9 | 1.26789928 | 1592.62 |
| [2026-10-25 / 344cbae](../reports/acceptance-v2-r3-20261025/README.md) | 3/9 | 4/9 | 1.20596190 | 1185.04 |
| [2026-10-27 / cfeb67f](../reports/acceptance-v2-r4-20261027/README.md) | 3/9 | 6/9 | 1.30208280 | 1089.22 |
| [2026-10-27 / a42fb7c](../reports/acceptance-v2-r5-20261027/README.md) | 3/9 | 6/9 | 2.02308846 | 1721.65 |
| [2026-10-27 / 4f4e67d](../reports/acceptance-v2-r6-20261027/README.md) | 2/9 | 3/9 | 0.47373284 | 863.73 |

The recorded API usage in this table totals **$7.68754786**.

### Limitations

Historical coverage combines successful examples from different evaluations; it is not a single-run success rate. The four successful gallery examples come from the evaluations on 2026-10-27 and exclude the earlier s1 success. A new evaluation has not yet run.

Only the selected s3 result has 20 identical compared loss scalars with every recorded input, effective-batch, objective and seed check matched. These are empirical comparisons. The s2 result is fp32 and tolerance-based, with a maximum recorded loss difference of 4.76837158203125e-7; its input, effective-batch and objective pairing is unknown. The same pairing information is incomplete for s8 despite its identical recorded scalars.

The s1 and s4 repairs each completed 20 optimizer updates, but their numerical comparisons cover only the first 5 backward-loss scalars. Their reference methods are identified in the table. The s1 repaired peak is reconstructed and is not marked exact. OOM baseline peaks are the largest observed allocations before failure; the memory needed to finish and completed-run throughput remain unknown.

In the latest evaluation, s5, s6, s7, s8 and nanoGPT stopped before an Ultra or Super request because the remaining spending allowance could not cover the next call. Their unknown diagnoses remain in the nine-scenario denominator. The s1 lower-memory candidate was reverted because the required numerical reference was unavailable. The s2 diagnosis identified temporary allocations instead of the authored optimizer-state cause and ended without a selected repair.

The variable-length workload's fragmentation cause remains unverified: a large gap between reserved and allocated memory is insufficient evidence. The full-vocabulary-logit and frozen-parameter workloads still lack a verified repair. nanoGPT also remains unsolved; its earlier configuration change still ran out of memory.

Some model calls have incomplete usage information, so each evaluation's full API cost remains unknown. The subtotal above also excludes earlier prototype evaluations, capability probes and other project work. Recorded wall time includes model calls and orchestration and is not GPU compute time.

The matched three-condition diagnosis comparison is reported above. HF Trainer automatic repair and the s2 strict-versus-bf16 comparison have not run. Existing HF baseline captures do not demonstrate a repair. The measured s2 fp32 result supplies only one configuration; a memory-versus-speed comparison between the two precision settings remains pending.

### Run details

The [measurement notes](../reports/final48h-docs-20261029/README.md) explain selection and calculation. [Detailed measurements and sources](../reports/final48h-docs-20261029/numbers.json) include exact bytes, GiB conversions and run IDs. The earlier dated sections below are retained verbatim.

