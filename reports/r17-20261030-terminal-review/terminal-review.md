# R17 terminal review

Targets: **3/9**, unchanged gate **6/9**. Terminal cases: 9/9. Full nine-case execution: True.

Unrun/pending cases remain unknown within denominator nine. Prepared request bodies are pre-transport evidence; unknown fees are not zero.

Final valid diagnoses: 5/9; final ready: 3/9.

| Case | Status | Campaign target | Final diagnosis |
|---|---|---|---|
| s1_batch_too_big | needs_human | False | valid=False, ready=False |
| s2_capacity_v2 | needs_human | False | valid=True, ready=False |
| s3_eval_no_grad_missing | completed | True | valid=True, ready=True |
| s4_loss_accumulation_graph | completed | True | valid=True, ready=True |
| s5_fragmentation_varlen | needs_human | False | valid=True, ready=False |
| s6_full_vocab_logits_fp32 | needs_human | False | valid=False, ready=False |
| s7_frozen_params_optimizer_state | needs_human | False | valid=False, ready=False |
| s8_two_models_resident | completed | True | valid=True, ready=True |
| nanogpt | needs_human | False | valid=False, ready=False |

Direct ledger charged total: 0.86369752 USD. Known actual call subtotal: 0.83529898 USD; actual total: None; unknown actual calls: 9.

Preserved Lab captures: 16; all recorded cleanup verified: True; recorded GPU-after inventories clear: True; all observed worker PIDs absent: True.

Exact raw rows, all saved round/diagnosis/patch/verification data, request metadata, source pins, billing and cleanup observations are in the adjacent JSON. This reviewer dispatches no model/GPU work and changes no historical result.
