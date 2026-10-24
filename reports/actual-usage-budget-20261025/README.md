# Actual-usage run budget correction (offline verification)

The original PLAN and all numeric acceptance thresholds are unchanged. A reviewed
profile can explicitly select run_budget_mode: actual_usage; omitted/default
profiles and migrated rows use strict_reservation. The existing CLI
--runtime-profile path selects the mode; --budget 0.6 remains unchanged.

The new mode keeps full provider-bound admission in shared global/day pools and
uses run actual usage as its stopping condition. Equality stops further calls but
still meets cost <= limit; a strict overrun stops with a partial report and no
top-level target-success claim. Retained patch/verification facts are preserved.
No estimate admission may enter the same shared ledger after actual mode has
been enabled. Historical known costs remain recorded; unknown billing still
globally blocks calls.

Validation: 293 focused tests passed in 47.06s, independent DNS/INET/real .env
guards reported zero external access attempts. Ruff and diff whitespace checks
passed. The first broad run's four legacy wording assertion failures are retained
in focused.log; the compatibility repair and final run are separately retained.
The new full pipeline fixture verifies first-round keep followed by actual
$0.60008 cost: three client records, retained patch, failed run cost criterion and
false top-level target success, with original candidate verification still true.

This is implementation evidence only. No live API, GPU, profile activation,
original capture rewrite, PLAN change, commit, or push was performed.

## Boundary revision after the first complete backend suite

The initial full suite passed 1674 tests in 475.95 seconds. Its broad 220-file
inventory changed only root PROGRESS.md documentation; all other 219 files were
unchanged. Original receipt/log/hashes remain intact, with a separate source-review
note explaining that documentation-only difference.

Independent review then identified two untested boundaries, now fixed:
unknown/pending/invalid billing after a successful keep must revoke overall run
success; a run/ledger from yesterday must not dispatch against yesterday's daily
pool. The trusted UTC clock is checked at both reserve and mark-dispatched.
Already dispatched charges still settle normally across midnight.

The revision passes 218 focused boundary/ledger/runtime/report tests plus 65
acceptance-driver compatibility tests. It includes real client/router mock chains
for missing usage, HTTP 429, transport failure, pending settlement interruption
and output-bound violation after a retained successful patch. No extra request
escapes the accounting guards. Scoped lint and formatting pass.

Latest source hashes are in receipt-boundary-revision.json; implementation diff
is implementation-boundary-revision.diff. The full suite has not been rerun after
these two narrow fixes; parent integration will verify the combined current tree.

## Interrupted integrated suite and API fixture isolation

The next integrated full suite was intentionally stopped after a confirmed
live diagnosis issue required a separate router/diagnosis fix. Its status is
interrupted_for_confirmed_live_failure_fix; raw receipt, annotated receipt,
interruption process ownership and log are retained under the
full-regression-20261024T212521Z-e116b982 prefix. All 208 non-Markdown source/config
hashes, PLAN and the independent guard were unchanged during that partial run.
Only the owned pytest process received SIGINT; its resource tracker, Docker
attach child and test container were confirmed gone.

Partial result: 1 failed, 719 passed. The sole failure was an API fixture that
assumed the actual project runtime profile was absent. Production health was
correct to show the newly enabled profile. The test fixture now uses a temporary
project root and copies only the public example index/training scripts; it never
copies profiles, keys, run state or budgets. Production health is unchanged.
Guarded API/deadline/availability verification: 88 passed in 34.93s, with the
actual runtime profile left enabled and untouched. See api-isolation-receipt.json.
The complete integrated suite must run again after the separate diagnosis fix
is frozen; this partial run is not represented as a pass.
