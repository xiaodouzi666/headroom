# October 30 R18 partial evaluation

R18 stopped after seven cases because the remaining development pool was below the unchanged $0.60 allowance required to admit another case. Two observed targets were met: s1 and s4. The fixed denominator remains nine and the required six targets were not reached. s8 and nanoGPT were never dispatched; their results remain unknown. R17 remains the latest complete nine-case execution.

| Case | Final status | Memory target |
|---|---|---|
| s1_batch_too_big | completed | met |
| s2_capacity_v2 | needs_human | not met |
| s3_eval_no_grad_missing | needs_human | not met |
| s4_loss_accumulation_graph | completed | met |
| s5_fragmentation_varlen | needs_human | not met |
| s6_full_vocab_logits_fp32 | needs_human | not met |
| s7_frozen_params_optimizer_state | needs_human | not met |
| s8_two_models_resident | not_run | unknown (not run) |
| nanogpt | not_run | unknown (not run) |

The two accepted candidates completed 20 updates. s1 reduced the observed CUDA peak from 24.750424064 GB (original OOM at zero updates) to 14.297204736 GB. Its numerical comparison uses a baseline-derived checkpoint reference and the first five backward scalar losses, with zero recorded difference. The transformed reference preserves original argv and workload; it is not byte-identical original source execution.

s4 reduced the observed CUDA peak from 24.768717824 GB (original OOM at 12 updates) to 2.533996544 GB. Its original-source/argv offload reference completed all 20 updates and cleaned its disk spill. The formal numerical acceptance still compares the first five backward scalar losses, with zero recorded difference. Both targets passed the recorded seed, input and effective-batch pairing checks. Full training coverage and comparable completed-baseline throughput remain unknown for these OOM baselines.

S2 and s7 failed evidence availability validation. S6 failed the existing numerical-change policy. S3 retained a request for more information. S5 exhausted its four permitted patch attempts with an undefined-name rejection, then retained a request for more information. These outcomes were not converted into ready diagnoses or successful repairs.

There were 32 real settled provider responses: 7 annotations, 14 diagnostics, 8 patcher responses and 3 Super responses. All diagnostic requests retained the existing Ultra model, 2,000-token output cap and disabled thinking. This reviewer created no provider calls or GPU jobs.

The R18 conservative charge is $0.57382620. The known actual subtotal is $0.55277484; seven calls retain unknown actual cost covered by their full bounds, so an exact total is unavailable. Previous spending remains $3.72274640, cumulative pool charges are $4.29657260, and $0.593931800 remains. This remainder is not authority to bypass the $0.60 admission rule or increase the pool.

All 11 saved Lab captures report verified cleanup and clear recorded GPU-after inventories. All seven observed worker PIDs were absent at review; the service exited successfully and is inactive. All 185 implementation and 30 input pins match their immutable preparation bytes.

Raw rows, round artifacts, request metadata, cost boundaries and cleanup evidence remain in [terminal-review.json](terminal-review.json). The concise machine-readable qualifications are in [final-qualification-summary.json](final-qualification-summary.json). Original R17 and other historical results are unchanged.

Source revision: 5a013bf32c3e79e3d37e2cc908ea374f72c7c7c3.
