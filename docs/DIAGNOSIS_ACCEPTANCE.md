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

For each response, the original first root-cause category is compared literally;
there is no post-hoc synonym mapping, model-based judging, or category rewriting.
The complete schema-valid raw text and parsed response are saved in
`model-response.json` before diagnosis validation/scoring. Invalid references
therefore remain inspectable. A response rejected by the existing router before
it returns (for example malformed/truncated JSON) retains the sanitized error,
identity/usage/accounting record where available, and a failed case; the driver
does not claim to possess raw text discarded by that existing contract.

Every cause must have at least one valid ID in the selected evidence's actual
runtime stack catalog, with no nonexistent references. The report retains all
original references, their valid/invalid subsets, schema/policy issues,
`needs_more_info`, and whether more evidence/savings are required.

The requested reduction uses the existing orchestration calculation. Completed
reclaim captures use the original default **30%** reduction target; the MVP
manifest's explicit 20% aggregate threshold does not leak into this separate
diagnosis check. OOM runs retain an unknown required reduction: successful
allocation peaks and a failed request do not measure total memory needed to
finish. This value and its basis are frozen in the prepared request.

Execution calls `diagnose_with_router(..., max_supplements=0)` once per case.
Insufficient proposed savings remains `requires_supplement=true` and is not a
complete passing diagnosis; the driver does not issue that supplement.
A local wrapper verifies that the one diagnosis request exactly matches the
prepared messages, then delegates to the ordinary router. `messages.json`
is **before** the router adds its schema and is not mislabeled as a wire hash.
The normal runtime still checks the complete SDK payload before dispatch.

## Explicit execution and budgets

Execution requires all of:

- a reviewed preparation with eight ready captures;
- an explicitly selected, already enabled and verified runtime profile;
- separate current human authorization for this live stage;
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
spending authority. Under historical full-context strict pricing an Ultra
4000-output request reserves about $1.060576, so an explicit $0.35 admission
cap refuses before the request. Account funding alone does not remove this
mismatch. See `docs/LIVE_EXECUTION_PLAN.md` and `docs/RUNTIME.md` for the
pending authorization/mode choices. A local-estimate profile may overshoot its
reservation; this driver does not turn it into a provider-hard spending cap.

All actual calls use `build_live_runtime`, its normal router/accounting hooks,
the authorized profile total, and the existing shared `.cache/budget.db`.
The acceptance Store is `runs/acceptance/headroom.db`, so acceptance-only rows
do not masquerade as ordinary repair runs. Environment run/daily caps can only
lower the explicit request. Existing unknown charges block later dispatch
across packages, runs and restarts.

The campaign passes at most its unspent nominal allowance into each case's
reservation. Actual known costs are summed with 256-digit Decimal precision.
Unknown billing, identity failure, output/schema transport failure, a violated
cost/budget bound or preflight refusal stops later cases. Already attempted
cases retain their evidence; unattempted rows remain `not_executed`.
An incomplete final accounting receipt is unknown, never silently $0.
The per-package `execution/` directory is exclusive: rerunning the same
prepared package cannot silently spend again.

The driver does not retry a failed case or regenerate evidence automatically.
The client's existing retry implementation remains behind the shared ledger's
unknown-charge stop. Runtime profile/capability failure does not activate a
profile, select a substitute model or weaken the output contract.

## Outputs and acceptance states

Each case retains its selected capture/hash record, original README, bounded
evidence, prepared messages, diagnosis/raw valid response, exact response
identity, attempts, server usage, actual cost, elapsed time and shared-budget
receipt. No source or model-generated code is executed by this driver.

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
The final 8/8 ready preparation is `runs/acceptance/diagnosis-prepared-20261024-v2/preparation.json`.
Its focused test receipts are recorded in `reports/diagnosis-acceptance-20261024/`.

No live model request, new GPU workload, credential read, profile activation,
budget change, or T1.4 live acceptance was performed during this development.
