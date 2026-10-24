# T1.4 diagnosis-only acceptance

This driver prepares and later evaluates the original eight synthetic diagnoses.
It does not run Lab, repair a workload, call Tavily or Nano, change the model
profile, or satisfy a live gate with fixture responses.

The implementation is `headroom/acceptance/diagnosis.py`; the CLI is
`scripts/check_diagnosis_acceptance.py`. The shared runtime lifecycle is
`headroom/acceptance/common.py`. All files and captures stay on azuki.

## Prepare first, without credentials or network

Use an explicit JSON mapping of the eight scenario IDs to existing capture
directories, or select those same IDs from a saved baseline report:

~~~sh
source scripts/env.sh
uv run --offline python scripts/check_diagnosis_acceptance.py \
  --from-baselines reports/evaluation-baselines-20261024.json \
  --output runs/acceptance/diagnosis-prepared-NEW
~~~

Alternatively `--captures captures.json` takes a JSON object such as
`{"s1_batch_too_big": "/absolute/existing/capture", ...}`. Neither route searches
for a convenient passing run. Duplicate selected baseline rows and unknown
mapping IDs are rejected. The output directory must be new and outside every selected capture and canonical scenario source; old captures,
prepared packages, and failures are preserved.

Preparation validates each capture's existing CUDA protocol, successful cleanup,
original default source hash/entrypoint/arguments, twenty-step configuration,
and the expected OOM/completed status. A completed capture must contain twenty
completed updates; an OOM capture is not required to have completed twenty.
Snapshot history must exist. Selected capture metrics and original raw result
must agree. No pickle is executed. Source, result, manifest, selected snapshot
and environment artifacts are hashed, with the source checked against both
the original scenario INDEX and the MVP manifest's source identity.

These checks bind cooperative Lab evidence. They do not authenticate an
adversarial workload that falsifies its capture. Evidence-quality fields retain
history/peak uncertainty independently of capture protocol completeness.

The driver regenerates bounded Markdown/JSON evidence only into the **new**
package, pins those bytes, and copies each original README verbatim for human
review. It also pins the scenario manifest, INDEX, canonical source files, and
diagnosis prompt. Source/capture hashes are rechecked after preparation and
before execution. Each later case reads and verifies its evidence bytes again
immediately before using those same bytes; modifying a future case during a
batch prevents its dispatch.

Missing or invalid captures remain explicit rows in `preparation.json`.
Preparation can finish with fewer than eight ready rows, but execution requires
all eight. Every preparation has `accepted=false`; readiness is not a model
result, paid authorization, or a live-profile verification.

## Ground truth and scoring

The denominator is always **eight**, and the required first-cause matches are
always **six**. The driver never shrinks the denominator to the scoreable cases.

| Scenario | Maintained category | Scoring treatment |
| --- | --- | --- |
| s1 batch | activations | Exact first-category comparison |
| s2 AdamW | optimizer_state | Exact first-category comparison |
| s3 evaluation | activations | Exact first-category comparison |
| s4 accumulated loss | retained_graph | Exact first-category comparison |
| s5 variable length | fragmentation_candidate | Unknown; never automatically counted as a match |
| s6 vocabulary logits | temporaries | Exact first-category comparison |
| s7 nominally frozen backbone | optimizer_state | Exact first-category comparison |
| s8 resident teacher | params | Exact first-category comparison |

These categories are read from the maintained manifest and checked against
`scenarios/INDEX.yaml`; the accompanying README and hashes are retained.
They represent authored fixture intent, not a new scientific truth established
by the model. Truth notes and labels are **not inserted into the model prompt**.

In particular, s5's README says harmful fragmentation is unconfirmed.
Reserved-minus-allocated includes reusable cache. Neither a large gap nor an
Ultra answer claiming fragmentation upgrades s5 to an established truth.
Its match remains `null`, even if its emitted category exactly spells the
candidate label. There is no automatic adjudication or override flag.

When a response passes the router schema checks, its original first root-cause
category is compared literally; rejected structured output remains unscored.
There is no post-hoc synonym mapping, model-based judging, or category rewriting.
Both schema-valid and router-rejected responses now retain bounded visible
assistant text in `model-response.json` before scoring, with observed finish
reason, usage, validation reason and full-content hash. Valid parsed responses
are retained when they fit the artifact limit. The 256 KiB/0600 artifact rules
below apply; reasoning text and request credentials are excluded. Invalid
references and malformed/truncated answers remain inspectable failures. The
earlier attempt1 did not preserve rejected response text or finish reason;
this change does not reconstruct that missing historical evidence.

Every cause must have at least one valid ID in the selected evidence's actual
runtime stack catalog, with no nonexistent references. The current request uses
a fresh copy of the historical Diagnosis schema, constrained before dispatch:

- root-cause reference items are enumerated from that case's actual stack catalog;
- `requires_policy` items may name only keys whose policy value is exactly true;
  with no enabled permissions the array has `maxItems=0`, not an invalid empty enum;
- `numerics_impact` is restricted to `none` unless
  `allow_numerics_change` is exactly true.

The reviewed live profile sends these constraints through native `json_schema`.
Missing or invalid catalogs fail before any model request; neither source text,
scenario answers nor hidden ablation evidence supplies substitute IDs. The
historical Pydantic schema and the evidence/policy inputs remain unchanged.
All original post-response reference, policy, savings, identity and cost checks
remain active: a constrained request is not proof that the provider obeyed it
or that the diagnosis is correct. Parsed responses retain original references
and validation details; router-rejected responses retain bounded raw visible
text and the rejection reason, with unavailable parsed fields left unknown.

The requested reduction uses the existing orchestration calculation. Completed
reclaim captures use the original default **30%** reduction target; the MVP
manifest's explicit 20% aggregate threshold does not leak into this separate
diagnosis check. OOM runs retain an unknown required reduction: successful
allocation peaks and a failed request do not measure total memory needed to
finish. This value and its basis are frozen in the prepared request.

Execution calls `diagnose_with_router(..., max_supplements=0)` once per case.
Insufficient proposed savings remains `requires_supplement=true` and is not a
complete passing diagnosis; the driver does not issue that supplement.
A local wrapper independently builds the expected dynamic schema from the
same revalidated prepared evidence and policy, then checks the request's
messages, canonical JSON schema, one-call limit, 8192-token cap and
`reasoning=False` before delegating to the ordinary router. A changed schema
or request is refused before dispatch. `messages.json` is **before** the
router adds its schema and is not mislabeled as a wire hash.
The normal runtime still checks the complete SDK payload before dispatch.

## Explicit execution and budgets

Execution requires all of:

- a reviewed preparation with eight ready captures;
- an explicitly selected, already enabled and verified runtime profile;
- current human authorization covering this live stage (the recorded gifted-credit
  authorization covers original-plan work; it is not requested again per case);
- explicit per-case, campaign and daily **admission** caps;
- the existing private project credential file, accessed only on the execute path.

Example template, **not an authorization or a command to run now**:

~~~sh
uv run --offline python scripts/check_diagnosis_acceptance.py \
  --execute --live-authorized \
  --prepared runs/acceptance/diagnosis-prepared-NEW/preparation.json \
  --runtime-profile .cache/tokenfactory-runtime.json \
  --admission-cap-usd "$AUTHORIZED_CASE_ADMISSION" \
  --campaign-cap-usd "$AUTHORIZED_CAMPAIGN_ADMISSION" \
  --daily-cap-usd "$AUTHORIZED_DAILY_ADMISSION"
~~~

There are deliberately no execute defaults for these three admission values.
The original **actual cost per Ultra call <= $0.35** acceptance threshold is
fixed and separate. A larger admission reservation does not raise it or grant
spending authority. With `run_budget_mode=strict_reservation`, an Ultra 8192-output request
reserves $1.073152 at the reviewed full-context prices, so a $0.35 run cap
refuses before dispatch. The currently reviewed live profile instead explicitly
uses `actual_usage`: the unchanged $0.35 run threshold applies to settled actual
usage, while the shared global/day pools must reserve the full verified provider
bound before each request. A single settled request can cross the actual run
threshold; it is then a failed acceptance and stops later dispatch. This does
not promise a $0.35 worst-case per-request charge. Existing gifted-credit-only
authorization and reviewed pool limits are recorded in
`reports/live-campaign-20261025/authorization.json`, `allocation.json`, and
`daily-reallocation-review.json`. No recharge or overspend is authorized.
A local-estimate profile remains a separate mode and does not supply a provider
hard bound; it is not the mode used for the v3 execution below.

All actual calls use `build_live_runtime`, its normal router/accounting hooks,
the authorized profile total, and the existing shared `.cache/budget.db`.
The acceptance Store is `runs/acceptance/headroom.db`, so acceptance-only rows
do not masquerade as ordinary repair runs. Environment run/daily caps can only
lower the explicit request. Existing unknown charges block later dispatch
across packages, runs and restarts.

The campaign passes at most its unspent nominal allowance into each case's
reservation. Actual known costs are summed with 256-digit Decimal precision.
Unknown billing, identity failure, transport failure, a violated cost/budget
bound, unconfirmed cleanup or preflight refusal stops later cases. A structured
output validation failure (including truncation) fails that row but permits the
next independent case only after the finalized receipt proves exactly one
settled, exact-model response, known actual cost <= $0.35 and a closed ledger
with no pending/unknown charge, halt or unresolved bound. It is not retried or
counted as a passing diagnosis. Already attempted cases retain their evidence;
unattempted rows remain `not_executed`.
An incomplete final accounting receipt is unknown, never silently $0.
The per-package `execution/` directory is exclusive: rerunning the same
prepared package cannot silently spend again.

The driver does not retry a failed case or regenerate evidence automatically.
The client's existing retry implementation remains behind the shared ledger's
unknown-charge stop. Runtime profile/capability failure does not activate a
profile, select a substitute model or weaken the output contract.

## Outputs and acceptance states

Each case retains its selected capture/hash record, original README, bounded
evidence, prepared messages, diagnosis, bounded response evidence, exact response
identity, attempts, server usage, actual cost, elapsed time and shared-budget
receipt. Execution packages must be inside the project's ignored `runs/` tree.
Both successful and rejected structured responses save their visible assistant
content and observed finish reason to mode-0600 `model-response.json`, capped at
256 KiB including JSON encoding. Full UTF-8 content length/SHA-256 and explicit
text truncation or parsed-value omission preserve the audit boundary. No raw
reasoning text, request headers, credentials or environment values are saved.
No source or model-generated code is executed by this driver.

The diagnosis-specific completion cap is 8192 (including provider-billed
reasoning when the verified cap declares that semantic). Diagnosis now explicitly
requests `reasoning=False` through the independently verified reasoning toggle;
missing toggle support refuses before dispatch. This is not a reasoning-token
budget control. Earlier v2/v3 calls used the then-current default reasoning
behavior; their observed output and failures are preserved. Other roles retain
their existing output defaults. The runtime must already
allow this output cap; no profile, account authorization, acceptance threshold
or retry allowance is expanded by this driver. A cap can still be exhausted,
and malformed/truncated output remains a failed case.

The earlier 4000-token s2 attempt did not persist its finish reason. Its known
usage showed all 4000 completion tokens as reasoning, but the missing finish
reason is not reconstructed or claimed to have been observed.

A live accepted result requires eight completed diagnostic attempts, all
schema/policy/reference/identity/cost gates, and >=6 matching first categories.
The s5 unknown truth can remain unknown while six other cases provide the
required minimum; it never contributes a positive match.

Offline MockTransport runs have `provenance=offline_fixture` and
`accepted=false` unconditionally. `fixture_gates_passed` only records that
the software's gates behaved as expected under synthetic responses.

CLI exit status is 0 for an execution accepted on live evidence, 1 for
incomplete/failed acceptance, and 2 for input/preflight CLI refusal. Preparation
returns 0 when all eight captures are ready, 1 otherwise; its JSON always
identifies `mode=prepare` and `accepted=false`.

## Development evidence, 2026-10-24

The first real-capture preparation used the eight synthetic entries in
`reports/evaluation-baselines-20261024.json`; all eight existing captures were
readable under denied DNS/INET and denied `.env` access. That first package is
preserved at `runs/acceptance/diagnosis-prepared-20261024/`. It predates the
required-reduction correction, is superseded, and is not an execution target.
The corrected offline 8/8 ready preparation was
`runs/acceptance/diagnosis-prepared-20261024-v2/preparation.json`. Its attempted
live execution and failures remain preserved. The later v3 preparation and
execution are recorded below; v2 is not the only or current execution package.
Its focused test receipts are recorded in `reports/diagnosis-acceptance-20261024/`.

No live model request, new GPU workload, credential read, profile activation,
budget change, or T1.4 live acceptance was performed during that initial offline
development. Subsequent authorized live execution is separate evidence below.


Optional `--min-case-interval-seconds N` (API:
`min_case_interval_seconds=N`) spaces the starts of independent cases by a
finite interval from 0 through 60 seconds. The default 0 preserves immediate
sequential execution. For example, an explicit 20 gives the provider more time
between requests without sending a retry. Each row records its start offset
and actual interval wait separately; wait is excluded from the case's
`elapsed_seconds`. This is proactive pacing, not a promise to avoid token-rate
limits. A 429 still retains its unknown-billing stop; neither the output cap,
cost threshold nor authorization is expanded by waiting.


## Second live attempt — v3, 2026-10-25 local date

`runs/acceptance/diagnosis-prepared-20261025-v3/preparation.json` is byte-for-byte
identical to the corrected v2 preparation: the same eight raw
captures, source/evidence hashes, original README truth, policy, targets and
thresholds. The independent review rehashed 159 referenced artifacts without
changing any historical capture or result.

The v3 execution made eight single Ultra calls with the then-current default
reasoning enabled, an 8192 completion cap and a 20-second minimum case-start interval. It is **not accepted**: only **3/8**
first categories match the unchanged minimum **6/8**, and two responses are
truncated. `stop_reason=null` means all independent cases were attempted with
clear accounting; it does not mean the diagnosis gate passed.

| Case | Recorded outcome | Exact first-category result | Known usage cost (USD) |
| --- | --- | --- | ---: |
| s1_batch_too_big | responded | activations = activations | 0.0215522 |
| s2_fp32_adamw_1b | failed | Unknown; observed length at 8192 | 0.03458592 |
| s3_eval_no_grad_missing | failed | Unknown; observed length at 8192 | 0.068064 |
| s4_loss_accumulation_graph | responded | graph_retention != retained_graph | 0.046266 |
| s5_fragmentation_varlen | responded | Unknown truth; needs_more_info remains incomplete | 0.040135 |
| s6_full_vocab_logits_fp32 | responded | activations != temporaries | 0.036683 |
| s7_frozen_params_optimizer_state | responded | optimizer_state = optimizer_state | 0.05361 |
| s8_two_models_resident | responded | params = params | 0.055423 |

The eight calls total **$0.35631912** known usage-priced cost; each individual
call remains below $0.35. At the independent review, the shared runtime ledger
had 12 closed runs totaling **$0.71393752** (prior $0.3576184 plus this attempt),
with zero pending/unknown attempts or halted runs. These are usage-derived
charges, not a reconciled provider invoice. The external 900k probe's permanently
retained $1.049344 remains separate and is not released.

The enabled profile uses `actual_usage` with verified provider bounds; its hash
matches all eight finalized runtime receipts. The original attempt1, the new
truncated text/finish reasons, exact-category mismatches, s5 uncertainty and all
failed scores remain unchanged. See
`reports/live-campaign-20261025/diagnosis-attempt2-review.json` for hashes and
`runs/acceptance/diagnosis-prepared-20261025-v3/execution/result.json` for the
original verdict. That attempt remains unaccepted.


## Third live attempt — v4, 2026-10-25 local date

The v4 execution used `reasoning=False`, the same 8192 completion cap,
20-second pacing and unchanged eight-case scoring denominator. All eight calls
returned `finish_reason=stop` with observed reasoning tokens equal to zero;
none was truncated. The first categories matched **7/8**, exceeding the
unchanged numerical minimum **6/8**, but **overall acceptance remained false**.
A category match does not override a failed plan/reference/policy check.

| Case | First-category match | Original complete-diagnosis outcome |
| --- | --- | --- |
| s1 | true | Passed recorded checks |
| s2 | true | Disabled permission and numerical-change guards rejected the plan |
| s3 | true | Recorded model-change rejection; review identified a matcher false positive about workspace allocations |
| s4 | true | Passed recorded checks |
| s5 | unknown | Truth remains unverified; disabled permission and numerical-change guards also failed |
| s6 | true | Numerical-change guard rejected the plan |
| s7 | true | Unknown stack reference and disabled permission |
| s8 | true | Unknown stack references |

All eight calls had known usage-priced costs below $0.35, totaling
**$0.327699**. The reviewed result was complete as a batch but failed its
structural gates; `stop_reason=null` does not mean accepted. The s3 false
positive and every other original failure remain in the saved result, with no
retroactive rescore. See
`runs/acceptance/diagnosis-prepared-20261025-v4/execution/result.json` and
`reports/live-campaign-20261025/diagnosis-attempt3-review.json`.

The dynamic request schema described above was added after v4. Offline
integration verifies actual Router/SDK payloads, unchanged postvalidation,
prepared-request binding and ablation visibility; its receipt is
`reports/diagnosis-schema-20261025/integration-receipt.json`. These tests do
not turn v4 into a pass or establish model accuracy. v5 is a separate live
execution in progress at this documentation update; no final v5 verdict is
recorded here.

## Latest live attempt — v5, 2026-10-25 local date

The same eight original captures, evidence, truth, policy and thresholds were retained. Dynamic request constraints and the generic prompt changed; previous results were not rescored. Eight single Ultra responses all finished with stop and zero reported reasoning tokens. First-category accuracy is **7/8**, and all eight reference sets are valid. Known usage-derived cost is **$0.328770**. The full result remains **not accepted**: s1 and s6 contain forbidden changes, and s7 is incomplete/requests more information. See reports/live-campaign-20261025/diagnosis-attempt4-review.json and the preserved v5 execution result. No further diagnosis-only repeat was used to replace these failures before the actual MVP attempt.
