# R14 terminal review — fresh live campaign

R14 executed all nine fixed cases and achieved **0/9 targets**, below the unchanged **6/9** gate. Five final diagnoses were valid; none of the final diagnoses remained patch-ready. Four cases had a valid ready diagnosis in an earlier round. These are distinct measures.

The unit ended inactive/dead, Result=success, ExitMainStatus=0. This means the controller completed, not that the repair acceptance passed.

| Case | Final valid | Final ready | Final blocker | Recorded rounds | Charged USD |
|---|---:|---:|---|---|---:|
| s1_batch_too_big | True | False | needs_more_info | 1:diagnosis_needs_more_info | 0.06400392 |
| s2_capacity_v2 | False | False | ALTERNATIVE_EVIDENCE_BLOCKS_CURRENT_PLAN | 1:diagnosis_validation_failed | 0.07772412 |
| s3_eval_no_grad_missing | True | False | needs_more_info | 1:diagnosis_needs_more_info | 0.08277670 |
| s4_loss_accumulation_graph | True | False | needs_more_info | 1:verification_hard_constraints_unmet; 2:diagnosis_needs_more_info | 0.13952308 |
| s5_fragmentation_varlen | True | False | needs_more_info | 1:diagnosis_needs_more_info | 0.06810962 |
| s6_full_vocab_logits_fp32 | False | False | EVIDENCE_AVAILABILITY_CONTRADICTED | 1:verification_hard_constraints_unmet; 2:diagnosis_validation_failed | 0.12102900 |
| s7_frozen_params_optimizer_state | True | False | needs_more_info | 1:verification_hard_constraints_unmet; 2:diagnosis_needs_more_info | 0.12690840 |
| s8_two_models_resident | False | False | EVIDENCE_AVAILABILITY_CONTRADICTED | 1:SOURCE_SYNTAX_INVALID; 2:diagnosis_validation_failed | 0.15951168 |
| nanogpt | False | False | INVALID_EVIDENCE_RANGE, INVALID_EVIDENCE_RANGE | 1:diagnosis_validation_failed | 0.09892186 |

## Material observed failures

- **s4:** the model-generated remove-retain-graph patch applied after one syntax repair and executed twenty GPU updates. Peak allocation fell from 24.768717824 to 2.533996544 GB (89.769%); observed candidate slowdown was 0.380%. It was correctly not accepted: the original saved-tensor offload reference failed before initialization with “Insufficient free disk for the bounded reference plus 1 GiB reserve”. Its numerical comparison was unavailable. This is an infrastructure blocker, not a certified numerical success.
- **s7:** the real first Ultra request and Super patch request contained the new source-bound optimizer observations (34 catalogued parameters requiring gradients, 1,075,970,304 elements, twenty complete all-catalog update sets). The model still proposed freezing the backbone/head-only optimization. Its actual GPU candidate completed with peak 4.413207552 GB but loss max delta 3.3520333766937256; the existing numerical gate rejected and reverted it. The second diagnosis still proposed the same training-contract change and asked for objective equivalence. Evidence delivery therefore succeeded; model reasoning/semantic enforcement remains unresolved.
- **s8:** four real patcher responses ended with SOURCE_SYNTAX_INVALID and no candidate execution. The later diagnosis requested missing candidate updates while referencing the already-visible retained-runtime updates object, causing EVIDENCE_AVAILABILITY_CONTRADICTED.
- **s6:** the candidate failed at zero completed updates with a CUDA device-side assertion. The baseline was genuinely OOM at zero updates. The later evidence request contradicted a supplied field.
- **nanoGPT:** Nano returned normally; final diagnosis failed INVALID_EVIDENCE_RANGE twice. No candidate ran.

## Evidence delivery, pins, cleanup and spending

All 33 saved diagnosis/patcher prepared request bodies contain runtime_optimizer_observations. The captured metadata remains pre-transport evidence with delivery_confirmed=false; successful provider responses do not turn it into independent provider-side attestation. Four auxiliary Super research calls are separate from the diagnosis/patch request paths.

There were 46 real provider responses: 9 annotation, 24 diagnosis, 9 patcher and 4 auxiliary Super. No saved call ended timeout; no diagnostic truncation failure was found. The reviewer dispatched no call or GPU job.

All 177 implementation pins and 30 input pins matched at terminal review. All thirteen saved Lab execution captures report cleanup_verified=true, and all nine worker PIDs are absent.

R14 conservative charged total is **USD 0.93850838**. Its known actual subtotal is **USD 0.91055144**, with nine Nano actual amounts unknown. Costs are conservatively resolved; unknown actual amounts are not zero. Including prior R12/R13 charges, the pool charged amount is **USD 1.60437118**, leaving **USD 3.286133220** within the unchanged USD 4.890504400 pool.

The immutable source campaign/preparation identities, per-case diagnoses and patch verification, request summaries, attempt accounting and cleanup facts are in terminal-review.json. No old result, denominator, target threshold, source, budget or controller was modified by this review.
