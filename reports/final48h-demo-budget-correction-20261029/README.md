# Demo per-run budget correction — 2026-10-29

Status: implementation and focused offline validation complete. This report does not deploy the change, restart production, create an allocation, change a receipt/ledger/claim, enable an entry, or make a model/GPU call. The primary agent owns the separate deployment receipt.

## Authorization and corrected interpretation

FINAL_48H F2 requires one real browser acceptance run costing no more than USD 0.30. It also specifies a shared running pool, one run per IP per hour and at most eight minutes per run. The separately confirmed FINAL_48H authorization caps total model spending at USD 6.43 net, within USD 7.79 gross, using gift credit with no recharge.

The primary agent reviewed all visible user authorization and found no instruction limiting all public/judge demos together to USD 0.30. The old implementation had reused receipt field `task_run_caps_usd.F2_demo` as an aggregate scope cap. This correction separates those meanings; the original receipt and the user's explicit limits remain unchanged. It does not promise unrestricted judging-period access or remove the hourly rule.

## Implementation and compatibility

Only `headroom/acceptance/demo_binding.py` changes production code. Default construction now creates version-2 run bindings with a per-run cap no greater than USD 0.30 and the original receipt's F2 task-run cap. Each new run is also limited by the shared pool's remaining charge allowance. Total and daily limits come from the same original receipt.

The existing `f2_demo_runs` and `claims` tables receive ordinary new-run entries. No historical payload, settlement, scope row, receipt or attempt is migrated or rewritten. An explicit `scope_limit_usd` argument preserves version-1 aggregate behavior; the existing launcher does not pass it and therefore selects version 2 after restart. Old active version-1 bindings remain verifiable and can finish through the ordinary terminal/cleanup/settlement path. Default version-2 admission waits for prior runs to settle.

Each bound open_run and reserve revalidates the run identity, request, source, receipt/profile, persisted binding and limit fields. A persisted budget-run limit must equal its binding, and its budget mode must remain strict_reservation. The original BudgetLedger transaction then enforces the run, day and entire shared-pool limits across all task charges. Resolved conservative charges continue counting toward caps while their actual costs remain null. Unknown/unsettled costs, active other tasks and uncertain cleanup continue to block admission.

No changes were made to budget.py, runtime.py, allocation.py, feature scopes, queue timing/rate limits, HTTP routes, public flags, tokens or the production service.

## Focused evidence

- Initial focused run: **27 passed in 7.06s**, before adding the final compatibility cases. Retained in [focused-initial.log](focused-initial.log).
- Final focused command: `.venv/bin/pytest -q tests/test_demo_allocation.py tests/test_demo_api.py tests/test_resolved_allocation.py`.
- Pre-review result: **47 passed in 7.95s**, [focused-tests.log](focused-tests.log), preserved unchanged.
- Final revised result: **48 passed in 8.00s**, [final-revised.log](final-revised.log), after adding persisted-budget-mode tamper protection. These groups overlap; do not add their counts.
- Ruff check/format and scoped git diff --check passed.
- Three final changed source/test files were scanned in an isolated copy: **no Gitleaks findings**, [revised scan log](gitleaks-revised.log), [JSON](gitleaks-revised.json). The earlier scan files remain preserved.

Fixtures use temporary project roots and temporary allocation/accounting files. Existing socket/DNS and credential-read guards apply; the spawned API worker uses a synthetic Lab, guarded network and httpx.MockTransport with the ordinary runtime/accounting path. The API tests retain one-request-per-IP/hour and launcher checks. No real provider request, GPU job, production database access or secret read was performed by this validation.

The tests demonstrate:

- Legacy payload/settlement strings, scope rows, claims, old budget rows/attempts, original receipt bytes and historical accounting remain unchanged when later v2 runs settle.
- Two newer runs can take cumulative demo charges above USD 0.30 while each remains within its own limit.
- Other tasks' charges reduce the same USD 6.43 pool; exhaustion blocks the next run.
- The inherited daily limit still refuses a run before any attempt.
- A lower receipt task-run cap cannot be widened by a v2 binding.
- Forged schema/cap/day/total fields are rejected even when the fixture's registry payload is changed to match.
- Source, receipt/profile, persisted run-limit or persisted budget-mode changes are detected before a second reserve.
- Wrong run identity, oversized open_run/reserve, unknown charges and unverified cleanup remain rejected.
- Historical v1 bounded-cost and recovery fixtures retain their old semantics; v2 keeps actual=null for resolved conservative charges without shrinking every subsequent run to an aggregate USD 0.30 remainder.

Independent review identified the missing persisted-budget-mode check: changing an opened run to actual_usage could otherwise change per-run reservation semantics. The revised check and negative fixture reject that change before another attempt. This was a read-only code finding and an offline fixture; no production row was altered.

## Primary-agent deployment procedure — not executed by this report

1. Confirm the public queue is idle, prior workers have cleaned up, and the shared accounting has no unresolved/active work. Preserve the existing private logical snapshots and old source backup.
2. Review and publish these source changes with their focused evidence. Keep the existing receipt path, profile, allocation database, daily limit, environment, tokens and public flags.
3. Restart the existing `headroom-public.service` only. Do not start the inactive `headroom-api.service` or create a second server.
4. Check health/config/queue with read-only requests. Confirm the hourly limit and snapshot/public settings are unchanged. Compare the protected old rows and receipt/profile against the private pre-deployment snapshots.
5. There is no global active-binding file to migrate: the normal queue calls DemoAllocation.begin for a future real run and persists its new v2 payload. No smoke POST or paid request is authorized by this implementation report.

Rollback: wait for any active v2 worker to finish and cleanup/settlement to be verified, restore the reviewed old source backup and restart the same service. Do not restore an old database over newer rows, delete v2 claims, reset spending or alter the receipt. The old implementation may pause demo admission if cumulative demo charges now exceed its old USD 0.30 aggregate cap; that fail-closed behavior is expected, and must not be bypassed by deleting history.

[receipt.json](receipt.json) pins the source/test hashes and validation logs. Production before/after checks belong to the primary agent's deployment.json.

## Production deployment

The primary agent deployed the reviewed revision after confirming the queue was idle. The existing headroom-public.service recovered in 1.771 seconds; public health and configuration returned HTTP 200. Configuration, receipt/profile/environment bytes, and every old/new accounting and registry table remained identical by logical hash. No new allocation, claim, model attempt or GPU job occurred. The default v2 path is loaded for future submissions; no new run was submitted by this verification. See [deployment.json](deployment.json).

Independent review checked the queue/runtime/transaction chain and requested a strict-budget-mode recheck alongside the run-limit recheck; that change is included in the final 48-pass revision. No blocking finding remained after the final frozen hashes were reviewed.
