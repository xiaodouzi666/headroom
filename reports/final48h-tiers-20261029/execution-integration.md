# F3 execution integration — proposed next-turn work

Status: read-only design, not execution-ready. No source changes, tests, model/GPU calls, profile reads, allocation creation or ledger writes were performed for this report. The root agent independently reviewed the final numerical-tier OOM reference chain and unchanged legacy defaults and reported that they satisfy the current requirements. That review covers the tier rules, not the still-missing execution/budget/CLI integration.

## Exact execution count

F3 requires **12 separate full-pipeline executions**, not 11:

| Group | Executions | Numerical policy | Score treatment |
|---|---:|---|---|
| Fixed nine, same R5 scenario protocol | 9 | Existing evaluation strict alias, which remains legacy numerical acceptance | Fixed denominator stays 9 |
| s2 new strict tier | 1 | exact-loss20-v1 | Separate tier result |
| s2 new allow_precision tier | 1 | observed-bf16-v1 | Separate tier result |
| HF Trainer | 1 | Explicit proposed permission policy; target fix-oom | Separate repository result |

s2 therefore occurs three times: once in the fixed-nine campaign under the old policy, and once under each new tier. The old name strict is not the new exact-loss20-v1 requirement. Replacing the fixed-nine s2 run with the new strict tier would change the original campaign's contract and is not proposed. New tiers/HF must not increase the fixed-nine numerator or denominator.

Source: FINAL_48H.md lines 72–78. The fixed-nine base is eval/mvp_phase1_v2.yaml; take only hf_trainer from eval/scenario_set_v2.yaml and repos/hf_trainer.yaml. Do not substitute the entire latter manifest: its reclaim defaults differ from the fixed-nine manifest and it also contains library scenarios. Existing R5 controls include full_ultra, old strict, until_target, six rounds, 20 updates, 480 seconds per supervised run and 0.6 USD per run. R7 explicitly changes the overall scope ceiling to 4 USD and the reviewed FINAL48 Ultra request policy/admission; do not claim wire/model settings identical to R5.

## Confirmed integration gaps

1. headroom/cli.py fix has no numerical_requirement option. cli_execution.cli_arguments also emits no such argument. CLIExecution.before_run compares the entire parsed request to the queued request, so a new tier currently cannot round-trip through the actual installed CLI; it should fail, not silently become legacy.
2. evaluation.run_campaign/_campaign has no allocation receipt argument or scope claim. The existing driver tracks only its own campaign costs and cannot bind the new F3 receipt or aggregate the additional tier/HF jobs into that same task ceiling.
3. run_fix currently obtains its budget database through select_budget_database(PROJECT_ROOT). Without the bound child environment, it falls back to the historical .cache/budget.db. Merely supplying the new runtime-profile path does not select the new allocation database.
4. allocation.verify_and_claim_allocation verifies a task cap for an individual claim. F1 alone has a pinned input binding and a forced once execution key. F3 is currently neither a once-only aggregate pack nor an aggregate 4 USD task counter. Twelve independent claims, or three separately capped campaigns, would not enforce F3's total ceiling.
5. The generic evaluation matrix uses resolve_policies, which intentionally knows only the old names. Do not redefine that mapping to implement the new tiers.
6. HF's source manifest requests configuration-only edits of at most 15 changed lines, but no implementation of this acceptance checker was found in headroom source. The existing protocol plan lists hf_configuration_diff as pending; a target_met result alone would not certify the full HF requirement.

## Smallest proposed implementation set

| File | Proposed change |
|---|---|
| headroom/cli.py | Add a typed numerical-requirement option with legacy default; explicit CLI value flows into Policy. Do not change normal CLI defaults. |
| headroom/cli_execution.py | Emit the option only for explicit nonlegacy tiers. Add a bounded optional allocation-task binding to the private Invocation; verify it before dispatch and require its receipt/profile/database identities and cell request to match. Preserve installed-CLI receipts. |
| headroom/evaluation_worker.py | Carry that binding through the existing supervised child and its private CLI context; select the verified allocation database only in the owned child environment, reject conflicting overrides, and retain the current 480-second deadline/cleanup behavior. |
| headroom/acceptance/allocation.py | Add explicit F3 preparation binding and a single once-only F3 campaign claim, capped by min(approved F3 task cap, 4 USD). Do not change F1 bindings or existing allocation receipts silently. |
| New headroom/acceptance/final48_repair.py | Pure prepare/verify pack plus a gated sequential 12-cell driver; reuse manifest loading, row/result summaries, the supervisor and prepare_s2_tiers/summarize_s2_tier. Own durable task-cost/cell state and the separate tier/HF summaries. Add the small HF configuration-diff checker here or in a narrowly scoped companion. |
| New scripts/prepare_final48_repair.py | Default preparation only. Future execute path requires reviewed preparation SHA, active allocation receipt and explicit execution authorization. No implicit allocation activation. |

No change to BudgetLedger or the shared native-admission/runtime core is required by this proposal. Generic evaluation.py may remain unchanged if the new driver reuses its existing manifest/preparation/result utilities and the existing supervisor directly. If a public evaluate entry is later requested, expose the new driver explicitly; do not overload old policy_names or pretend run_campaign already has receipt binding.

Focused next-turn tests should cover CLI round-trip for all three requirement modes; missing/tampered/conflicting receipt/profile/database; replayed F3 claim; changed preparation pins; all 12 rows and unchanged fixed-nine thresholds; interrupted/unknown-cost child blocking further cells; OOM reference propagation; and HF configuration-diff checks. No new tests were run for this design report.

## Proposed durable execution flow

1. Prepare a pack offline, pinning the fixed-nine manifest/source files, s2 calibration receipt, nanoGPT repository identity, HF source/command/dependency manifest, implementation files and numerical/reference policies. Record exactly 12 unique cell IDs and one group tag per row. Pin reviewed controls and ordering before execution; leave allocation/profile references unresolved until actual authorization exists.
2. Before any GPU, research or model work, verify the pack and active allocation receipt. Claim F3 once using that pack identity and confirm its task ceiling is no greater than 4 USD. Retain the old ledger as historical evidence; never edit or re-charge its unknown calls into the new pool.
3. Execute cells sequentially through supervise_evaluation_run -> installed CLI -> run_fix -> existing build_live_runtime. Each child retains its own run ID, artifacts, deadline and normal pending/settled accounting in the receipt-bound shared database. Revalidate receipt/profile/database identity before each child. The child environment must not fall back to the old database.
4. Preserve the R5 0.6 USD per-run allowance unless a separately reviewed pack explicitly tightens it. Before each cell, require settled/retained prior F3 charges plus that allowance to fit the same <=4 USD task ceiling. Existing unknown/pending or exceeded-cost behavior stops the pack; never use zero or release unknown usage. A consumed once-only claim cannot be retried as a fresh campaign to reset the ceiling. A future resume must bind the same pack and reconstruct all child costs from the existing ledger.
5. This is a task-level admission ceiling, not a provider-guaranteed upper bound: native-schema input counting remains an explicitly acknowledged estimate. Any new estimate overrun, unknown bill or unresolved child prevents further dispatch and prevents certification of the scope cost. No claim is made that 12 full repairs are guaranteed to finish for 4 USD; if funds run short, persist the remaining rows as unrun and the pack as partial.
6. Write one aggregate F3 report with separate fixed-nine, new s2 tiers and HF sections. For a failed strict s2 run, retain unknown pairing and its failure reason; do not fabricate a Pareto point, independent patch or successful gallery card. For HF, report baseline OOM/parameter/source facts, actual repair outcome and the configuration-diff check separately; a no-reference exception does not turn loss n/a into equivalence.

## Scope boundaries

The fixed-nine s2 still uses its established legacy acceptance; the new strict tier still requires independently proven pairing and cannot pass the currently unsupported s2 contract. No pairing contract/fingerprint expansion is part of this integration. HF can receive explicit numerical-change permission only as recorded in its approved request; permission does not prove BF16 or paired numerical equivalence. Source/GPU preparation and any research stay inside the existing runtime-ready and execution-authorization boundary.

This report adds no new approved spending scope. The proposed F3 pack is not ready until receipt/CLI integration is implemented and reviewed. Current frozen numerical-tier implementation receipt remains the authority for its 415 offline focused tests; this report adds zero test results.
