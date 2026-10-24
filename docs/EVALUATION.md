# Evaluation harness

This module implements repeatable evaluation bookkeeping and explicit execution gates. It does not create benchmark results from fixtures, historical estimates, or missing provider access. The original plan and its acceptance thresholds remain unchanged.

## Manifest

`eval/scenario_set.yaml` contains 12 entries: the original eight synthetic scenarios, pinned nanoGPT, the random-initialized Hugging Face Trainer example, and two additional real-library candidates:

- `eval/candidates/vit_random/train.py`: Transformers ViTForImageClassification, random weights and synthetic image batches.
- `eval/candidates/t5_random/train.py`: Transformers T5ForConditionalGeneration, random weights and synthetic token batches.

Both new candidates use the existing Transformers 4.46.3 dependency. They never call `from_pretrained`, download datasets, or fetch weights. Their `--profile cpu-smoke --device cpu` paths use different small models and are only plumbing checks. Full default CUDA behavior is a separate measured gate.

Every script is pinned by SHA-256. Paths must remain within the project and cannot be symbolic links. Manifest loading does not import target scripts. nanoGPT is prepared from the locally cached, exact reviewed three-file source profile and deterministic synthetic tokens; the harness never fetches a missing repository or executes setup commands. A missing cache or mismatched source blocks that case.

The manifest records **authored fixture intent** separately from **unverified scientific truth**. Synthetic s5's reserved-memory gap does not prove fragmentation; it remains unscored for cause agreement until truth is independently established. The real repository/library examples also remain unscored for cause agreement until reviewed. s2 uses the meaningful `reclaim` target because its existing baseline is already below 22 GB. This does not satisfy or replace T2.1's unresolved requirement of at least two rounds to fit 22 GB.

## Four separate modes

`validate_manifest(path, project_root=...)` reads configuration, checks source presence/hash and installed dependency metadata, and returns `mode=validate_only, executed=false`. A `valid` result is **not** the plan's baseline execution acceptance.

`campaign_plan(path, policy_names=("default",), ...)` powers `headroom eval --plan-only`. It reports selected workloads, conditions, full effective policies, pipeline-count multipliers, the sum of configured per-run caps, and the unchanged campaign/daily limits. It does not load a live profile, read credentials, import workload scripts, or call a provider. Planning is not a baseline or repair result.

`execute_baselines(path, execute=True, ...)` is the backend for the original `headroom eval --dry-run` meaning. It actually runs the selected baselines through the isolated Lab, sequentially, with a new GPU busy/lock check for each run. It makes no model or research API call. Default limits are 20 optimizer steps and 120 seconds per case. Completed cases must reach the selected step count; OOM must be a Lab-classified CUDA OOM. Capture completion and cleanup are required. An unexpected baseline outcome stays a failure; the harness does not edit scenarios or expected outcomes.

A complete `accepted=true` baseline report requires the full manifest, at least 20 requested steps, actual CUDA execution, expected behavior, complete capture, verified cleanup, and no observed shared GPU. A selected subset can set `selected_baselines_passed=true` without accepting the whole manifest. CPU captures and injected offline runners can never set GPU acceptance.

`run_campaign(path, execute=True, live_authorized=True, runtime_profile=..., ...)` runs actual repair campaigns. It refuses to dispatch unless both explicit gates and a verified runtime profile are supplied. The caller must obtain the existing human authorization and credit/price/cap evidence before supplying these flags. The default per-run cap is USD 0.60; the campaign cap defaults to USD 0.60, so one run does not implicitly authorize a full campaign. Original daily/provider budget enforcement remains in the shared runtime ledger.

The campaign reserves the next whole per-run limit against its remaining cap before dispatch. An unresolved charge stops subsequent dispatch. Failed and partial attempts retain all durable Store usage, including unknown costs. The known subtotal is never presented as the final total when charges are unresolved. A process interrupted after dispatch retains its prewritten run ID and reservation in campaign.json, while the runtime preserves pending billing records. Automatic resume/retry of a campaign is intentionally unsupported; each new invocation creates a new historical directory.

## Python / CLI integration

The CLI owner can call these functions without changing their meanings:

```python
from headroom.evaluation import (
    CONDITIONS,
    campaign_plan,
    validate_manifest,
    execute_baselines,
    run_campaign,
)

validation = validate_manifest("eval/scenario_set.yaml")
# --validate-only: return validation, never run workloads.

baselines = execute_baselines(
    "eval/scenario_set.yaml",
    execute=True,
    device="cuda",
    max_steps=20,
    max_seconds=120,
    scenario_ids=None,  # all 12; an explicit subset never accepts the full manifest
)
# --dry-run: this is actual baseline GPU execution, with no model calls.

# Only after separate live authorization and verified profile prerequisites:
campaign = run_campaign(
    "eval/scenario_set.yaml",
    execute=True,
    live_authorized=True,
    runtime_profile="path/to/reviewed-profile.json",
    scenario_ids=["s1_batch_too_big"],
    conditions=("full_ultra",),
    policy_names=("default",),  # one policy unless explicitly expanded
    per_run_budget_usd="0.6",
    campaign_budget_usd="0.6",
    daily_budget_usd="12",
)
```

The interface does not modify the public API's FixRequest contract. Baseline/campaign functions return the unique saved report path. Paths default under `runs/evaluation/`; no earlier result is overwritten. The manifest SHA, actual source SHA, Lab result path, source run ID, evidence/report paths, condition, and usage support auditability.


## Explicit policy selection and unchanged T2.8 gate

The CLI defaults to `--policies default`. It accepts a comma-separated, duplicate-free selection of `default`, `strict`, and `allow_precision`; only `--plan-only` and `--live` accept policy or condition selections. The Python equivalent is `policy_names=(...)`. Every queued, failed, partial, and completed row records the policy name and the complete effective `Policy`.

- `default` uses the current existing `Policy()`.
- `strict` explicitly sets `allow_numerics_change=false`.
- `allow_precision` explicitly sets `allow_numerics_change=true`; other policy permissions retain their existing defaults. It permits consideration of precision-changing candidates; it does not guarantee bf16 or a successful repair.

The original T2.8 wording is **default / allow_numerics_change=false**. The current default already forbids numerical changes, so `default` and `strict` are equivalent; plans expose this through `same_effective_policy_as`. This ambiguity is preserved for discussion. The optional `allow_precision` setting does not silently rewrite that requirement or claim its acceptance.

A policy matrix without an explicit scenario selection uses the original ten synthetic/repository workloads, excluding the two additional library candidates. A single-policy, single-condition campaign retains the existing twelve-entry default. Multiple diagnosis conditions retain the eight-synthetic-scenario scope.

```sh
headroom eval --plan-only --policies default,strict
headroom eval --plan-only --policies default,allow_precision
```

Each example plans 10 × 1 × 2 = 20 pipeline runs. With the unchanged USD 0.60 per-run cap, their configured run caps sum to USD 12.00, but the campaign cap remains USD 0.60 unless explicitly changed under existing authorization. All policies and conditions share that one campaign cap: dispatch requires room for the next whole per-run reservation, and any unresolved charge stops subsequent rows. A matrix never multiplies authorized spend automatically. A pipeline run can include annotation, diagnosis supplements, multiple patch attempts, retries, and research; the plan therefore leaves the provider API-attempt count unknown instead of treating 20 pipelines as 20 calls. Every actual model attempt remains governed by the existing runtime ledger.

Target/cause counts, measured means, numerical-equivalence denominators, failure modes, and costs are reported per policy as well as globally. Missing target/cause observations keep the exact overall rate unknown; scored-only accuracy and a lower bound are separately named. Means include measured values only and expose missing counts. Equivalence excludes `n/a` from its comparable denominator. No absent throughput or fee is filled with zero. Ablation pairs require the same policy name and effective policy, with separate per-policy comparisons.

The original real two-policy evaluation, at most three prompt/evidence/policy optimization rounds, target_met at least 75%, first-cause agreement at least 75%, total spend at most USD 12, and reports/phase-2-summary.md remain pending. Offline matrix/CLI tests establish control flow and accounting only.

## Diagnosis ablation

The three controlled conditions are:

1. `full_ultra`: the complete bounded evidence prompt and Ultra diagnosis.
2. `traceback_ultra`: only captured traceback and `memory_summary()` text in the diagnosis prompt, with a reference catalog limited to those visible texts. No snapshot, allocation stacks, or selected source excerpts are passed to that diagnosis. The round number, prior decisions, kept-round identifier, and policy flags remain available as explicitly trusted search metadata; snapshot-derived memory measurements are excluded.
3. `full_super`: complete evidence with only the diagnosis call routed to the existing Super/patcher role. The same runtime client, accounting hooks, and budget reservations remain active.

Selecting multiple conditions defaults to the eight synthetic scenarios and rejects an explicitly mixed non-synthetic selection. Other pipeline stages, patching, research policy, and verification are held to the same system rules. This is a **diagnosis input/model ablation**; it does not assert that the patcher is denied its normal source/evidence inputs. The first-round diagnosis is read from `rounds/01/diagnosis.json`, never substituted with the final-round diagnosis.

Each diagnosis writes its visible evidence Markdown and hash, initial diagnosis messages and hash, system-prompt hash, condition, visible reference IDs, and routed role to the campaign's private audit directory. The message hash is before the router adds its schema instruction; it is not a wire-request hash and does not cover subsequent supplement turns. Captured text is labeled untrusted. Raw prompts stay in ignored run history; they are not public-repo fixtures.

Cause agreement is exact category equality against authored truth. Paired comparisons require all three conditions, the same source hash and effective policy, and known first-round scores. Missing/duplicate conditions, unverified truth, and different source hashes are listed as exclusions. The summary reports descriptive differences, without claiming statistical significance or inventing the expected superiority of full evidence. The unchanged T4.3 expectation cannot be accepted until actual model results exist.

## Reports and limits

The generated campaign JSON/Markdown include each scenario's truth state, first-cause agreement, target outcome, before/after peak bytes, reduction, step-time change, separately recorded throughput change, numerical equivalence, rounds, cost, elapsed time, and source run. Missing fields stay null/unknown. Step-time change is not automatically relabeled throughput. Unknown failed outcomes are included as unknown attempts rather than silently removed to inflate success rate. The summary exposes a success lower bound and keeps the exact target rate unknown while outcomes remain unresolved.

`run_fixture_campaign` is an explicitly separate offline-test interface. Its outputs are forced into an `offline-fixtures` namespace and all such rows are excluded from live performance/cost summaries. They verify storage, control flow, and reporting only.

Offline tests exercise execution gates, path/source integrity, sequential baseline classifications, immutable history, budget reservation, partial/unknown charge accounting, model routing, ablation information isolation, paired scoring, and fixture exclusion. The two new scripts passed two CPU tiny training steps each. Full CUDA baseline evidence, when available, is recorded separately and does not certify model repair, T1.2, T2.1, T4.2, or T4.3.

## Recorded CUDA baseline campaign — 2026-10-24

The full 12-entry manifest was executed sequentially through the Lab with 20-step / 120-second limits.
The unique saved aggregate is `runs/evaluation/baselines/20261024T023317672107Z-69b2d798/baseline.json`.
All 12 actual behaviors matched the pinned manifest; every raw result has capture_complete=true, cleanup_verified=true, and shared_gpu=false.
Five cases produced CUDA OOM and seven reached 20 optimizer steps. This accepts only the T4.1 baseline-behavior execution scope.
All source hashes, aggregate counters, and raw Lab result counters were rechecked after completion. GPU memory returned to 58 MiB used.

| Scenario | Actual status | Steps | Observed peak allocated bytes | Capture wall seconds |
|---|---|---:|---:|---:|
| s1_batch_too_big | oom | 0 | 24750424064 | 3.181 |
| s2_fp32_adamw_1b | completed | 20 | 21553250816 | 21.190 |
| s3_eval_no_grad_missing | completed | 20 | 2435717632 | 5.987 |
| s4_loss_accumulation_graph | oom | 12 | 24768717824 | 4.498 |
| s5_fragmentation_varlen | completed | 20 | 5021758464 | 6.885 |
| s6_full_vocab_logits_fp32 | oom | 0 | 21588379648 | 1.437 |
| s7_frozen_params_optimizer_state | completed | 20 | 17819808768 | 6.164 |
| s8_two_models_resident | completed | 20 | 3100141568 | 5.827 |
| nanogpt | oom | 0 | 24705183744 | 8.358 |
| hf_trainer | oom | 0 | 24805119488 | 7.266 |
| vit_random | completed | 20 | 2082592768 | 20.158 |
| t5_random | completed | 20 | 8042536960 | 53.254 |

These allocator maxima describe the captured execution. In an OOM case they are not the total memory required by a hypothetical completed workload. The aggregate does not invent a peak_is_exact flag absent from the Lab result.
The SSH output channel closed after ten completed rows, while the detached supervisor continued running. No duplicate campaign was started. The final aggregate and all 12 raw Lab results were then read and verified through a fresh connection.
No model or Tavily requests were made by this campaign; T4.2 repair results and T4.3 ablation outcomes remain pending.

Final scoped implementation verification: 33 offline evaluation tests passed; scoped Ruff and git diff whitespace checks passed. ViT and T5 also passed source-policy scanning and separate two-step CPU tiny smoke checks.

## Policy-matrix verification — 2026-10-24

Focused evaluation/CLI verification passed 75 tests in 1.35 seconds, including
whole-matrix reservations, unknown-cost stop, explicit precision permissions,
complete policy provenance, comparable-policy ablations, missing-score
denominators, and Watch adapter reporting. Scoped Ruff and whitespace checks
passed. The actual non-executing CLI planning smokes are preserved in
`reports/policy-matrix-smoke-20261024T025631Z-d034c92f/verification.json`: default 12 pipeline runs,
original two-label matrix 20, explicit precision matrix 20, and synthetic
three-condition/two-policy matrix 48. Every invocation kept executed=false,
authorization_expanded=false, and the unchanged USD 0.60 campaign cap.
No model request, environment-key read, Docker workload, or GPU execution was
part of this verification. These checks do not replace the original live gates.


## Explicit reclaim targets and repository command provenance

Each scenario may declare reclaim_reduction_pct (finite, greater than 0 and at most 100); omission
keeps the original verifier default of 30. The field is passed through FixRequest
to verification and is recorded in campaign plans and result rows. It is an
explicit requested memory goal, not an inferred metric or a changed loss bound.

eval/mvp_phase1.yaml selects exactly the original eight synthetic scenarios and
nanoGPT for T1.12. Only its reclaim cases explicitly request 20%, matching that
task's aggregate pass line. eval/scenario_set.yaml remains the unchanged
12-case general evaluation set with the default 30%. The T1.6 s3-specific 30%
requirement and the unresolved s2 requirements remain independent gates.
Selecting the MVP manifest does not imply that its live runs or acceptance passed.

Repository-group cases execute the command recorded in repository_manifest,
after checking that its entrypoint and arguments match the scenario. Interpreter
flags and module form are retained. nanoGPT's existing /input dataset rewrite is
applied with replay_argv, and the resulting command is checked against the
prepared source. Requested argv, actual execution argv, the command source and
repository-manifest hash are saved beside the input and in result evidence.
For a repository-group case without a repository manifest, the command is
explicitly constructed from the scenario's entrypoint and script_args and labeled
as such; it is not presented as a historical upstream command. Synthetic/library
cases retain their existing direct-script mode.

Baseline runs and repair campaigns use the same prepared repository command.
Repair requests set repository_mode so the original T1.9 no-reference rule can
be applied by the verifier without asserting numerical equivalence. Command or
source mismatches fail before Lab/model execution. Preparation remains local:
no Git fetch, setup command, model request, GPU workload, or credential access is
performed by loading/planning the manifest or by these offline regression tests.


Campaign rows also retain the verifier's numerical_basis and acceptance_scope.
The curated public API accepts their defined values only and preserves the n/a
loss state. The Results table displays the observed-comparison basis beside its
numerical state; a repository no-reference exception stays explicitly unverified.
Older records without these fields show that the basis was not recorded.

## Explicit search mode selection

A version-1 evaluation manifest may set top-level `search_mode: until_target`
(default) or `search_mode: bounded_pareto`. This one mode applies to every
selected scenario/condition/policy in that campaign; it is not another implicit
matrix multiplier. Existing manifests remain target-stop campaigns.

```sh
headroom eval --plan-only --manifest eval/scenario_set.yaml --search-mode bounded_pareto
```

`--search-mode` is accepted by `--plan-only` and the separately authorized
`--live` path. `--validate-only` validates the manifest but does not search, and
`--dry-run` captures baselines; both reject a CLI search override instead of
silently ignoring it. Python `campaign_plan`/`run_campaign` accept
`search_mode=None` to inherit the manifest, or an explicit supported string to
override it. Precedence is explicit CLI/function argument > evaluation YAML >
`until_target`. Invalid values fail before live profile access or workload
dispatch. This does not consume the separate project `headroom.yaml`.

`bounded_pareto` permits continued exploration after first target achievement
within the existing maximum of six rounds, per-run/campaign/daily budget checks,
timeouts and policy permissions. It cannot enable bf16, expand a spend cap, or
guarantee multiple retained/non-dominated points. The original acceptance gates
and unresolved s2 baseline/precision-policy conflicts remain unchanged.

New plans, campaign documents and every pending/running/failed/completed row
record the actual requested `search_mode`. Executed rows preserve the report's
search stop reason, first-target round, baseline-target observation and executed
round count. Terminal status and reason remain independent of target achievement,
including a budget failure after an earlier successful configuration. Markdown
tables and the curated public projection retain mode and stop reason. Historical
artifacts with no recorded search evidence remain null/unknown; they are never
backfilled from today's default. Offline fixtures remain excluded from live scores.

Ablation pairing also requires consistent recorded search modes because the mode
is part of the diagnostic context. Different known modes, or a mix of known and
unknown modes, are excluded as `search_mode_not_comparable`. All-unknown legacy
pairs keep their pre-existing comparability rules, with `search_mode: null` in
the pair; no historical default is invented.

## Recorded patch and completion outcomes (T1.12)

The original MVP table requires patch application and completion facts. A workflow
state such as `completed`, a `target_met` flag, a retained round, or an empty diff
does not establish either fact. New campaign rows carry the following separate
fields, projected unchanged in meaning through the curated API and Markdown:

| Field | Meaning |
|---|---|
| `patch_applied` | True when any recorded round has a successful patch/config application, including a candidate later reverted. False only when all recorded rounds have explicit failed/rejected patch results. Otherwise null. |
| `patch_applied_rounds` | Round numbers with observed application success; an empty array alone does not prove no application happened. |
| `selected_round` | The explicit retained round identity, never the last attempted candidate. Null when selection is absent, invalid or contradictory. |
| `selected_patch_applied` | Application fact for that selected round. A modern explicit `kept: null` means false; historical missing selection remains null. |
| `selected_completed` | The selected round's actual verifier `completed` Boolean. It does not mean target success. Missing, conflicting or rejected evidence remains null. |
| `round_outcomes` | At most six records containing only `round`, `decision`, `patch_applied` and `candidate_completed`. These are attempted-candidate facts, separate from the selected before/after metrics. |
| `outcome_basis` | `recorded_round_artifacts_v1` for this extraction contract; null for historical rows with no recorded outcome basis. |

Application comes from `rounds/NN/patch-result.json` and the producer's
`status=applied` contract (accepted application plus static checks). It covers
valid CLI/environment-only changes with an empty code diff. Search keep/revert
does not alter that historical application fact.

Candidate completion comes from `rounds/NN/verification.json`. A genuinely
missing file may use the actual saved inline round verification; a malformed,
oversized, symlinked or otherwise rejected artifact cannot fall back to an inline
success. A conflicting inline/file Boolean remains unknown. Selected completion
requires an explicit consistent selected identity and corresponding round
verification; a selected round explicitly marked reverted, a failed selected
patch, a conflicting final verification Boolean, or a different final after-run
ID cannot become selected completion success.

A run that keeps round 1, then reverts round 2, reports both applications and both
candidate outcomes while retaining round 1's completion and original selected
after metrics. A later budget stop or error preserves those same selected facts.
An all-reverted run can have `patch_applied=true` with no selected completed result.
No artifact is rewritten to add these facts.

`summary.outcomes` contains `patch_applied`, `selected_patch_applied`, and
`selected_completed` counters, each with `true_count`, `false_count`,
`unknown_count`, and `known_count`. Only attempted live rows enter these counts;
fixtures are excluded. No new acceptance rate or relaxed original threshold is
introduced. Historical absent fields remain unknown even if workflow status or
target success was recorded.


## Live evaluation wall-clock supervision

Every live campaign case now runs in its own spawned Headroom process under a
480-second monotonic deadline, matching the T1.12 eight-minute acceptance line.
The deadline starts before local source/data preparation. Preparation, condition
setup, baseline, model calls, verification, and the worker's report generation
share this one deadline. The original Lab still owns each no-network Docker
target; spawning Headroom does not introduce host execution of user programs.

On expiry the parent sends SIGTERM so the orchestrator can save its partial
report, permits at most five seconds for that cleanup, then sends SIGKILL if
necessary. It reuses the existing owned-container cleanup check for this case's
generated run ID and stops the campaign if cleanup cannot be verified. Cleanup
time is recorded separately and does not extend the execution deadline or make
an over-eight-minute run pass. Every row retains measured wall_seconds; the new
evaluation_timing records the limit, worker exit, deadline, and cleanup outcome.

A timed-out or failed worker cannot retain an overall target-success claim.
Saved candidate verification, diffs, snapshots and existing run history remain
available. The parent reads persisted Store/worker artifacts to produce the
partial report; it never infers zero billing from a killed process, cancels a
provider reservation, or releases an unknown/pending charge. These charges keep
the ordinary shared ledger blocked. A normal worker returns its complete result
through a bounded atomic local JSON file, avoiding a large result blocking an
unread multiprocessing pipe.

This supervision applies to the live headroom eval path. Pure planning,
baseline-only runs, and run_fixture_campaign do not silently acquire a worker.
The separate headroom fix CLI is unchanged by this integration. A completed
case still needs all original target, cost, numerical and wall-clock checks;
this implementation is not live MVP acceptance.

## Conservative billing coverage and unchanged cost thresholds

A campaign row keeps `cost_usd=null` when actual billing is unknown. A newly
runtime-certified bound adds `billing_complete=true`, `cost_upper_usd`, and
`cost_basis=verified_upper_bound`. The ordinary cost mean and exact total never
substitute this bound for a measured actual amount.

The campaign charges its remaining envelope conservatively using exact cost or
that certified bound, and proceeds only while the next whole run reservation
fits. Unresolved charges still stop dispatch. A bound above the per-run limit
sets `cost_limit_certified=false` and stops the campaign with
`cost_upper_bound_does_not_certify_run_limit`; it is not labeled actual overspend.
Original run/campaign/daily/global limits remain unchanged.

Summaries retain exact `total_cost_usd`, known subtotal and `unknown_cost_runs`,
and separately expose `billing_complete`, `bounded_cost_runs`,
`unresolved_cost_runs` and `conservative_total_usd`. Bounds are displayed in their
own JSON/Markdown/public Results column, not in the actual-cost column. Existing
unknown rows without explicit certification remain unknown. A later review that
retains an old full reservation in the shared ledger does not retroactively turn
the original failed campaign into a pass.

## CLI exit acceptance is separate from worker exit

The original T1.12 procedure invokes `headroom fix` for each of nine cases. A recorded `evaluation_timing.worker_exit_code=0` is the multiprocessing worker's exit status, not an observed `headroom fix` shell exit. The worker calls `run_fix` directly and can return normally with `needs_human` or another non-success status.

The current CLI maps `completed` to 0, `needs_human` and `budget_exceeded` to 78, `timeout` to 124, and other statuses to 1. Target success remains separate: workflow `completed` does not imply `target_met=true`.

The read-only private helper `.cache/setup/audit_cli_exit_semantics_v1.py` derives `expected_fix_exit_code` only when saved campaign, report, worker-result and Store statuses agree, using a pinned CLI source contract. It always keeps `literal_fix_exit_code=null` and `invocation_observed=false`. Predicted zero is not observed CLI evidence, and the helper never makes the literal CLI acceptance gate pass.

See the [boundary report](../reports/live-campaign-20261025/cli-exit-acceptance-boundary.md) and [v3 supplement](../reports/live-campaign-20261025/mvp-v3-cli-exit-semantics.json). v3 had nine normal worker exits but eight predicted CLI exits of 78 and only one predicted 0. No existing result is regraded and no additional provider or GPU call is required for this status audit. Literal CLI invocation, argument/configuration handling, terminal events and shell exit still need their own execution evidence before claiming the original CLI gate passed.
