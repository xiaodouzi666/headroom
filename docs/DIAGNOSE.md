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
