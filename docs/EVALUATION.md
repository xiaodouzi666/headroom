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
