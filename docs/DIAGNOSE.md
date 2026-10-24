# Diagnosis preparation

T1.4 has an offline schema, file-based system prompt, and deterministic checks.
No Nemotron diagnosis has been run, so T1.4 is not accepted. The real >=6/8
root-cause agreement and <=$0.35 cost gates remain pending Token Factory access.

Use build_diagnosis_messages() to prepare the two messages and pass the Diagnosis
Pydantic class as json_schema to the Token Factory router. Then use
validate_diagnosis() with the exact evidence pack's runtime stack_catalog and
the caller's policy. This layer performs no network requests.

The validator rejects malformed/nonfinite claims, missing or unknown runtime
stack references, duplicate IDs, empty claimed-complete diagnoses, disabled
policy permissions, and numerical changes when forbidden. A precision keyword
guard also rejects a precision-changing description mislabeled as numerics none.
Similar conservative guards catch common batch/accumulation changes, model shrinking,
and one-step training claims even when requires_policy omits them. The canonical
batch permission is allow_batch_grad_accum; explicit false narrower batch/accumulation
permissions still deny the action. These guards can flag wording that merely discusses a method;
they are not a substitute for the later patch policy and real numerical comparison.

The caller supplies required_saving_gb only if that reduction is known. A failed
OOM allocation is never treated as the whole model's required memory. When the
sum of expected savings is insufficient, the result asks for a supplement and
preserves the original estimates. Passing this arithmetic check does not establish
that estimates are accurate or additive; overlap and uncertainty belong in notes.

The valid property means these checks passed; ready_for_patch additionally requires
a nonempty plan and needs_more_info=false. The guards are not a complete semantic
honesty check; T1.10 must still inspect actual diffs and parameter counts.

Validation is structural and bounded policy checking, not proof of causal correctness,
memory savings, or numerical equivalence. A static source annotation cannot be
used as a runtime stack ID. The prompt explicitly preserves this boundary and
treats source/log/document contents as untrusted data.

Offline integration also passes a provider-shaped reply through the real SDK mock,
role router, Pydantic schema, and evidence validator. A well-formed reply that invents
a stack reference is rejected before it can become a patch plan. These fixtures
are explicitly synthetic, and no test result establishes model accuracy.

Validation record: reports/api-prep-20261023T222659Z.json; 25 diagnosis unit checks
and 2 SDK/router/evidence contract tests passed within the 259-test full suite.


## Recorded verification feedback between rounds

Later Ultra diagnosis requests now include a separate verification_feedback
array from completed orchestration rounds. It preserves the original
VerifyReport's finite peak/timing/loss metrics, numerical basis and tolerance,
boolean/null checks, explicit failed/unknown checks and bounded notes. Missing
verification is null with its recorded failure reason, never an empty passing
report. Candidate observations and selected_after_round are distinct: a reverted
candidate cannot replace the retained source, metrics or target state in this
feedback. fix_id and the relative patch artifact identify the attempted change.

Each round's summary is saved as rounds/NN/verification-feedback.json and in the
round record. There are at most six summaries; a request rejects more than six
or more than 64,000 UTF-8 bytes. Ordinary summaries are much smaller. Notes are
limited to eight entries of 320 UTF-8 bytes; omissions/truncation are explicit.
No raw snapshots, tensor values, complete Lab results or full diffs are copied.
The final full request still passes the existing admission/budget guard. Feedback
adds no model calls and cannot change policy, numerical thresholds, round limits
or deadlines. Synthetic fixture provenance remains visible.

Offline SDK mock tests check keep/revert/keep feedback, exact measured scalar
preservation, unavailable and unknown fields, bounded content, and six rounds
without additional calls. They establish wiring, not live model effectiveness.


Validated Nano opinions enter through annotate_evidence_bundle within the existing
evidence Markdown token budget, attached to the displayed stack ID they describe.
They remain model opinions, separate from measured categories/bytes/frames.
The orchestrator uses the returned bundle for the first diagnosis; newly captured
candidate evidence does not inherit prior labels. Traceback-only ablation must
exclude stack and Nano content rather than receiving a separate annotation field.


Candidate/retained observations also carry bounded real exception type/message
and error text, plus available numeric OOM request/free values. Missing details
remain null. Full tracebacks are excluded, and exception messages are untrusted
data rather than instructions. This lets a later round distinguish, for example,
an unavailable optional dependency from a numerical comparison failure.
