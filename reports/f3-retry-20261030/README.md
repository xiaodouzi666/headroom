# F3 fixed-nine retry binding — 2026-10-30

Implementation only. No production prepare, claim, model request or GPU execution was performed by this agent. R7 remains 1/9 against the unchanged 6/9 threshold. Current main at the final check is e3b887e9b8f95ea9cfcd52ec80dde0d2652672d9 plus this reviewed candidate and other separately owned work.

## Scope

- New headroom/acceptance/f3_retry.py reuses the existing F48 receipt/profile/database identity, allocation cost helpers, shared registry transaction and pending-claim checks. It creates independent F3-retry:<revision>:<fixed-cell> feature parents/children only when explicitly claimed.
- The old F3 once claim, original twelve children, receipt, profile and historical reports are never reset. All original twelve charges plus every F3 retry revision count against the original USD 4 F3 cap; every request also remains within the original shared F48 ceiling.
- The old preparation is authenticated by its original once-claim SHA. Current controls, cells, input pins, source files, calibration and repository identities must match it. Only implementation pins may change. The selected ordered set is exactly the original fixed nine; no s2 tiers/HF, denominator stays nine even when a run is not dispatched.
- Each candidate retains the original USD .60 request allowance. A whole .60 must fit before admission. It is possible to stop with not_run cells: the preserved R7 conservative bound was USD 1.01159284, leaving USD 2.98840716 of the F3 cap before new retries, less than nine worst-case .60 allowances. The current shared-pool balance must be rechecked after other work settles.
- CLI adds only an explicit retry-schema verifier and budget-factory branch. Normal supervisor, installed CLI, runtime, model router, source preparation, GPU Lab and verified cleanup remain the production route. No mock/fake production entrypoint was added.
- reserve and mark_dispatched recheck source/input pins, exact request/profile, receipt/database, ledger day and raw mode/limit. The dispatch check permits only the exact own undispatched reservation; other unresolved costs or cleanup uncertainty block continuation. Both demo→retry and retry→demo claim/open gaps are covered.

## Offline evidence

focused-initial.log/json: 51 passed, 6 failed. The six were new-test fixture/expectation errors: repeated run ID was rejected before the duplicate-cell branch, invalid demo run ID, a wrong temporary-table PK name in three parameter cases, and database conflict correctly refused earlier than the expected layer. No business guard was weakened; the original failure is retained.

focused-review.log/json: **60 passed / 24.10 seconds**, exit 0. Includes new F3 retry tests plus existing final48 CLI binding and original F3 allocation tests. Parent and spawn v4 negative probes passed. Tests used temporary fixtures/ledgers with real network, credentials, production database and GPU access denied.

Coverage includes original twelve costs and immutable rows; cumulative cap across revisions; competing F48 cost; whole-run floor; same-cell race; old preparation and fresh-but-altered workload rejection; source mutation after reserve; profile and raw ledger day/mode/limit changes; shared pending-claim exclusion; unknown cost and cleanup fail-closed; unchanged legacy CLI binding. A normal build_live_runtime→SDK MockTransport path observes the original temporary ledger marked dispatched before transport, then settles a synthetic actual USD .0004. This is not a real provider run.

Two existing F5 compatibility nodes (parameterized to 5 cases) also passed in 3.45s under the same guard; this is a separate focused result, not a new all-suite run.

ruff check/format passed for all three owned source/test files. Source hashes and final checks are in final-checks.json.

## Prepared handoff scripts, not executed

prepare-fixed9-retry.py.txt only writes a new pinned preparation and private proposal. It reads original registry metadata, does not claim or create a budget run. Run after all implementation source has frozen; current snapshot edits will otherwise invalidate the preparation.

```sh
.venv/bin/python reports/f3-retry-20261030/prepare-fixed9-retry.py.txt \
  --revision r8 \
  --original-preparation runs/final48-repair-preparation-20261029-v4/preparation.json
```

The preparation and proposal are exclusive new files; do not overwrite a previous reviewed revision. It prints the proposal hash and fresh scope/pool accounting. A preparation is not approval or execution.

execute-fixed9-retry.py.txt is a reviewable controller draft. It requires --execute-reviewed, the exact proposal SHA, and a new output directory. It sets umask 0077 before file creation, labels threshold_scope=memory_targets_only (not valid first-cause or overall acceptance), traverses the original nine, keeps not_run rows, uses 480s supervisor deadlines, and accepts execution only with normal CLI proof, terminal result, verified cleanup and settled resolved costs. It stops if the next complete .60 allowance cannot fit. Raw execution failures/cost uncertainty are retained. On an interrupt, a still-active binding remains blocked rather than being automatically settled.

The controller was syntax-checked only; it is not part of the 60 core binding tests. Root must review it and retain its exact SHA before any actual execution. Do not describe it as tested GPU execution. Neither script has run in production.

## Independent review

headroom_plan_audit completed a separate read-only review of the full module, CLI diff, both script templates, existing registry/quiet/cost paths and targeted tests. No specific blocking issue found; exact reviewed source hashes match final-checks.json. The reviewer did not rerun tests or access production configuration/ledgers.

## Expected next actions

Review complete; freeze all current repair source; prepare a fresh R8 proposal; inspect accounting and exact hashes; root alone dispatches a reviewed controller if the same existing gift allowance can support it. Do not increase output tokens/call count, alter the nine controls, reclassify old outcomes or transfer spending to the judge pool.
