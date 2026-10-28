# FINAL_48H request policy and admission preparation — 2026-10-29

## Current handoff

This is the preserved request-policy-only stage report. Its statements about
unimplemented estimation and proposed receipt binding describe that earlier
stage, not the current code. The later
[input-calibration and implementation report](../final48h-input-calibration-20261029/README.md)
records the opt-in NativeSchemaEstimateAdmission and profile-carried 2000/False
diagnosis policy, including the CLI route. Defaults remain unchanged, and the
local estimate is not a guaranteed provider billing bound.

The [feature integration receipt](../final48h-feature-scope-20261029/integration.md)
records the completed allocation/CLI/Web/Watch bridges at e97bc42. Current
prepared inputs are [F1 v8](../final48-f1-preparation-20261029/final-preparation-check.json)
and [F3 v2](../final48h-feature-scope-20261029/f3-preparation-refresh.json),
both with zero executed requests/cells. A's explicit amount, fresh price checks,
the actual reviewed profile/allocation and real execution remain pending.
No live profile or new pool was activated by these offline implementations.

## Historical request-policy-only state

At this earlier stage, only the opt-in diagnosis request policy and offline tests
were implemented. FINAL_48H §0.4 estimated-cost admission was **not implemented
or enabled by that stage**. Frank's §1-A amount is still absent. No allocation, live profile, production ledger, credential, provider call, GPU run, or public-service setting was created or changed.

The new `FINAL48_DIAGNOSIS_ONLY` constant is frozen, with `id=final48-diagnosis-only-2000-v1`, `max_completion_tokens=2000`, and `reasoning=False`. It selects an actual request cap; it is not merely a 2,000-token cost estimate. This is an explicit new request configuration for the F1 runner, not a reinterpretation of the old pipeline.

`build_diagnosis_messages(..., request_policy=FINAL48_DIAGNOSIS_ONLY)` substitutes 2000 into the existing prompt cap marker. `diagnose_with_router` accepts the same optional policy and preserves False/2000 through any caller-authorized existing supplement. The policy itself grants no supplementary calls or spending. F1 uses one direct budgeted `router.chat` followed by local validation, not this supplement loop. Mixing an old study protocol with the new policy is rejected.

Ordinary diagnosis remains 16384 output tokens with reasoning requested. The earlier `common-diagnosis-4000-v1` study remains 4000 with reasoning requested; it is eight synthetic cases and independent end-to-end repair, not F1's nine-case diagnosis-only experiment. F3's ordinary orchestrator still inherits the ordinary defaults unless explicitly changed later. Snapshot diagnosis separately already requests 2000/reasoning False; that does not configure F1 or F3.

## Historical proposed implementation route

**PROPOSED, not activated:** use a separate new SQLite budget database for the new FINAL_48H allocation, reusing `BudgetLedger` unchanged. Preserve the old database and its unresolved amounts. Do not weaken its global blockers, rewrite old records, or treat a fresh arbitrary database as funding authorization.

An explicit allocation receipt should bind: unique allocation ID, Frank's authorization reference and exact USD amount X, confirmed available-balance reference, allowed scope, canonical database path and file identity, reviewed profile hash, admission-policy version, and creation time. It must have no default amount and no implicit creation in an ordinary run. Select this existing initialized database through the current path/identity checks, or inject the validated immutable selection directly into the F1 runtime. Do not switch the public service or ordinary worker merely by setting an environment variable.

Use `strict_reservation` run mode for locally estimated reservations. This name describes the ledger's pre-dispatch accounting, not a provider cost guarantee. Current `actual_usage` requires verified provider bounds and explicitly rejects local estimates; it is not the desired new mode.

For F1, one uniquely named run owns the whole 27-request sequence, with run limit at most USD 1.50 and the same shared allocation's total/daily limits. The parent pool may also fund later explicitly scoped tasks; opening another database must not replenish it. Each actual request still reserves atomically before transport, settles reported usage afterward, and retains uncertain charges. A new unknown, response model mismatch, or estimate overrun must stop subsequent dispatch in the new pool. Old unknowns in the separate historical database do not consume or block the newly authorized pool.

This does not make a local estimate a hard provider bill cap: an already-dispatched request could exceed its reservation. Preserve its full actual charge and stop; never clip accounting to the estimate or manufacture a successful USD 1.50 result. F1 succeeds only if all 27 real records exist and their measured costs satisfy the original limit.

## Input-token and native-schema boundary

The existing `LocalEstimateAdmission` already audits the final SDK request, uses pinned local tokenizer/template assets, reserves per attempt, and settles actual usage. It currently:

- supports only the exact pinned Ultra model;
- requires a multiplier greater than one plus positive additive tokens;
- rejects unmodeled provider-only fields, including native `response_format.json_schema`;
- explicitly does not prove a match to the provider's tokenizer/template or establish a provider input-token bound.

Therefore simply setting output to 2000, changing the profile to `actual_usage`, removing its risk margin, ignoring `response_format`, or switching to a new database does not implement §0.4.

**PROPOSED:** add a separately named estimation policy rather than loosening the old policy in place. Its decision should expose separately: model ID, final request hash, pinned local template tokens, schema/domain estimate and method, any explicit overhead allowance, input-price source, requested output cap, and the resulting admission estimate. Use the model's reviewed input price and no assumed cache discount. Report local input tokens as an estimate; actual provider prompt tokens are available only from the response.

For native JSON Schema, the router already prepends the schema into a system message and the client also sends `response_format`. The former is counted by the local template; provider handling of the latter remains unverified. `preflight.py` records serialized schema statistics but specifically warns that separate domain counts are not an additive provider billing bound. Counting the extra domain as zero, or asserting that UTF-8 bytes prove its provider tokenization, is unjustified.

The smallest defensible native-schema extension is a reviewed, bounded request domain: exact model/template revision, supported fields, schema-size limit, evidence/source-size limit, and an explicit estimation formula supported by saved paired wire-request/provider-usage receipts for that same domain. Store the predicted-versus-observed discrepancy. Refuse unsupported fields or inputs outside the reviewed envelope. Such calibration supports an estimate, not a mathematical maximum. This report selects no numeric overhead formula: no verified formula is currently established.

An explicitly named text-JSON F1 variant could instead place the schema only in messages and validate returned JSON locally, which the existing estimate domain supports. That would change native structured-output behavior and the experimental request protocol; it must be a deliberate documented selection across all three arms, never an automatic fallback to make admission pass. No such variant is selected here. Super can retain its existing verified-provider-bound policy with the actual 2000 output request if it fits the shared allowance; do not reuse Ultra's tokenizer for Super.

Before paid execution, freeze all 27 full outgoing requests and their estimates, compare the aggregate forecast with USD 1.50, then also enforce the ledger on each dispatch. Forecast fit is not measured acceptance. If the native-schema estimation contract is not ready, F1 execute remains blocked; the offline runner and request policy can still be complete.

## Official output-cap facts

Checked the [Token Factory Chat Completions reference](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion) on 2026-10-29: `max_completion_tokens` covers visible output and reasoning tokens; omitted/null `max_tokens` defaults to 8192. Keep the reviewed model's existing `output_cap_field`; the runtime must receive only that one field and validate it against the reviewed cap semantics. The new request policy does not override the field selected by the model profile.

`reasoning=False` records the requested model switch. It does not prove that the provider returned zero reasoning tokens. Preserve actual completion/reasoning usage as reported.

The root's review of the [official documentation index](https://docs.tokenfactory.nebius.com/llms.txt) found no tokenizer/count-token endpoint. That is a search result, not proof that no such endpoint exists. No token-count endpoint was invented or called.

## Historical source paths and proposed ownership

| File or call path | Present support / remaining change |
| --- | --- |
| `headroom/diagnosis_protocol.py` | Added immutable explicit request policy; old caps/study metadata unchanged. |
| `headroom/diagnose.py` | Added optional policy to message construction and diagnosis invocation; old defaults unchanged. |
| `headroom/llm/router.py::LLMRouter.chat` | Prepends schema to messages, then calls client and validates locally; no paid repair loop. |
| `headroom/llm/client.py::TokenFactoryClient.complete` | Builds full request; SDK retries disabled; wrapper retries independently admitted. F1 must pass `max_http_retries=0` through runtime. |
| `headroom/runtime.py::build_live_runtime` | Existing pre-attempt reserve/pending-store/dispatch and post-response settlement. Proposed: validate explicit allocation and separately versioned admission policy; do not infer authorization. |
| `headroom/llm/admission.py`, `preflight.py` | Proposed: new domain-specific estimator and records; preserve old fail-closed policy. |
| `headroom/ledger_path.py` | Existing initialized-path and identity checks reusable; not itself an allocation authorization mechanism. |
| New `headroom/final48_allocation.py` plus focused tests | Proposed minimal receipt validation/opening helper, without a general ledger rewrite or auto-initialization. |
| `headroom/budget.py` | Reuse existing reserve/settle/restart behavior; no proposed accounting-schema rewrite. |
| F1 runner agent's new files | Separate nine-case by three-condition diagnosis-only runner, dry-run default, explicit execute gating, no patch/Nano/research/GPU. This report is not its completion receipt. |

Concrete F1 call path: authorized allocation selection → `BudgetLedger(new_db, total_limit=X, daily_limit=approved_daily)` → one `open_run` capped at 1.50 → `build_live_runtime(..., max_http_retries=0)` → policy-bound frozen messages/schema → direct budgeted `router.chat("diagnose" or "patcher", ..., max_tokens=2000, reasoning=False)` → local `validate_diagnosis` and actual per-request records → close run. The existing pre-dispatch model/capability/pricing guards remain in force.

## Historical enablement checklist (superseded by current handoff)

1. Receive Frank's explicit X and balance confirmation under §1-A; no recharge and no inferred amount.
2. Resolve and review the native-schema input estimate or explicitly select a documented alternative protocol. Preserve old estimator behavior.
3. Implement/test the small receipt binding and create the new database only under that authorization. Keep old records unchanged; stop or leave disabled any older paid dispatcher.
4. Bind the new reviewed profile and allocation, with live disabled until checks are complete. Match model IDs, current verified prices, output fields, prompt-size domain, and policy hashes.
5. Run offline positive/negative tests: unauthorized creation, wrong receipt/path/identity/profile, restart, concurrent reservations, old unknown retained, new unknown/overrun blocks, unsupported schema domain, missing pricing, request cap mismatch, one request per F1 cell, and the 27-request shared USD 1.50 limit.
6. Only then explicitly execute within A's scope. Any needed provider calibration is paid work and must be counted inside the authorized pool; it cannot be silently added to F1's 27 experimental calls. Save any incomplete result as incomplete and do not relax denominators.

## Verification of the historical request-policy stage

Focused tests: **87 passed in 2.52s**, including 21 new policy tests and 66 existing compatibility/recovery tests. Counts are disjoint within this single run, not added to previous executions. An outer process-level DNS/socket blocker recorded **0 attempts**; provider-shaped calls used MockTransport only. The new module also has its own autouse DNS/socket guard.

Coverage includes unchanged ordinary/study prompt and wire modes, opt-in 2000/False, native schema preserved, chosen output field preserved, wrong policy/mixed study rejection, immutable policy, format-repair mode preservation, and zero-supplement validation failure without a second request. Existing truncation recovery and common-study contracts remained passing.

Log: `request-policy-tests.log`. Ruff, formatting, and scoped secret-scan results are recorded alongside it. These are software checks, not live model capability, budget authorization, or F1 acceptance.
