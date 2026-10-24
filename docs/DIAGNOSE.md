# Diagnosis preparation

T1.4 has a schema, file-based system prompt, deterministic checks and a separate
live acceptance driver. Saved real attempts and their failures are retained under
`runs/acceptance/`; neither an individual response nor offline tests establish
the full >=6/8 agreement and <=$0.35-per-call acceptance.

Use `build_diagnosis_messages()` to prepare the two messages and
`build_diagnosis_schema(evidence=evidence, policy=policy)` to construct a
fresh, constrained copy of `Diagnosis.model_json_schema()`. The pure builders
and `validate_diagnosis()` perform no network requests.
`diagnose_with_router()` builds this schema before its first call and
reuses it for any permitted supplement, then runs the original postvalidator
against the same evidence and policy.

The schema's root-cause `evidence_refs` items enumerate only actual runtime
catalog IDs. `requires_policy` items may reference only keys whose value is
exactly true; no enabled keys means `maxItems=0` instead of an empty enum.
Unless `allow_numerics_change` is exactly true, `numerics_impact` permits
only `none`. Missing/invalid catalogs fail before dispatch. Both the full
evidence document and direct analysis input remain supported. The original
schema and supplied evidence/policy are never modified, and source frames or
scenario truth labels are not copied into the enum.

The reviewed live profile uses native `json_schema` for this request.
Traceback-only evaluation derives its schema from the restricted visible
catalog (`traceback` / `memory_summary`), never the hidden full snapshot;
the Super diagnosis adapter preserves the same schema, cap and reasoning flag.
Provider compliance and valid references alone do not establish a correct
diagnosis, so every existing post-response check below remains required.

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
role router, dynamic request schema, Pydantic model, and evidence validator. A well-formed reply that invents
a stack reference is rejected before it can become a patch plan. These fixtures
are explicitly synthetic, and no test result establishes model accuracy.

Historical validation record: reports/api-prep-20261023T222659Z.json; 25 diagnosis unit checks
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


## Diagnosis output and rejected-response evidence

`diagnose_with_router` requests a diagnosis-specific 8192-token completion cap.
Diagnosis explicitly requests `reasoning=False` through the existing router.
The profile must contain independently verified support for its reasoning toggle;
missing support is refused before dispatch. The verified output-cap semantics
continue to include reasoning where configured. Other role/router defaults remain
4000. Profiles and the shared ledger still determine whether a request is allowed;
the new default grants no additional account budget and makes no implicit retry.

The router continues to reject truncated/filtered output, empty or invalid JSON
and schema mismatch. `ResponseValidationError.response` exposes the received
`ClientResponse` for an explicit private audit sink, while its string contains
only the fixed reason. It does not persist or log assistant content by itself.
The T1.4 driver saves bounded private response evidence before recording the case
failure; see `docs/DIAGNOSIS_ACCEPTANCE.md` for the continuation and accounting gates.


The prompt defines a stable generic cause vocabulary without changing the
historical schema or exact acceptance scoring. Physical allocation-origin
categories and causal mechanisms such as retained_graph remain distinct;
unknown remains available, and a cache gap is not proof of fragmentation.
Post-step optimizer markers are explicitly described as completion observations,
so allocations within an update can precede its marker. The default proposed
verification is 20 optimizer updates with loss comparison and FP32 tolerance
0.001; executable thresholds continue to be chosen by the host, including
permitted precision-specific checks. Model wording cannot relax them.

This change addresses observed response truncation and terminology ambiguity.
It does not establish that a new diagnosis is correct. Earlier 4000/8192-token
failures, exact-category mismatches and the original captures remain unchanged.


## Current evidence and preserved failed attempts

v4 made eight real diagnosis calls with `reasoning=False` and an 8192-token
cap. All returned `stop` and observed zero reasoning tokens. Its **7/8**
first-category matches passed that numerical sub-gate, while full T1.4
acceptance remained **false**: disabled permissions, numerical-change
violations and invented stack references failed the existing checks. Review
also identified s3's recorded workspace-allocation wording rejection as a
matcher false positive; the historical failed artifact is retained rather than
rescored. Known usage-priced cost was $0.327699 across eight calls.

The later dynamic schema moves expressible reference/permission/numerics
restrictions into the request without removing postvalidation or changing the
scenario truth, score or thresholds. Its production/prepared-driver integration
passed 322 focused checks, four parameterized CPU wrapper cases and 109
schema/evaluation checks (overlapping suites, not a unique total); evidence is
`reports/diagnosis-schema-20261025/integration-receipt.json`. These are
software checks, not a live acceptance claim. The full v2/v3/v4 history is
documented in `docs/DIAGNOSIS_ACCEPTANCE.md`. v5 is currently a separate live
attempt; this update does not assign it a final result.
