# F2 public API allocation bridge

Status: offline engineering checks passed; real public s3 acceptance has not run. This change creates no production pool, token or live deployment.

The server can inject `DemoAllocation(receipt_path, project_root=...)` into `create_app(..., demo_allocation=...)`. It validates the canonical FINAL48 receipt, profile and existing budget database, then gives each public run a registered F2_demo claim. The durable aggregate allowance is at most $0.30 and survives service restarts. Each dispatch uses only the remaining aggregate allowance. The daily and global limits come from the approved receipt; $0.30 is not used as a global daily limit.

The queue retains its normal spawned worker and `run_fix` lifecycle. Only `Services.budget_factory` is supplied: ordinary runtime construction, opening and closing the run, SDK usage and settlement remain intact. The original uploaded/preselected source hash, prepared request, receipt/profile/database and active claim are checked before execution and before each model reservation. Unknown charges or uncertain cleanup stop subsequent work. The original historical budget database is unchanged.

Anonymous callers still select catalog examples; arbitrary scripts require the existing judge Bearer token. Public repository execution remains forbidden. Existing per-IP hourly admission, at most two waiting jobs, 480-second deadline and owner-only result/SSE access remain in place. s3 now recommends Reclaim because its baseline already runs; an explicit user target is still respected.

## Operator activation

Default launcher behavior remains read-only. After the root task activates the reviewed pool, the operator may configure both `HEADROOM_RUN_SUBMISSIONS_ENABLED=true` and `HEADROOM_PUBLIC_ALLOCATION_RECEIPT=/home/xiaodouzi/workspace/headroom/.cache/final48-allocation/receipt.json`. Missing or invalid authorization refuses startup. The launcher selects that receipt's existing ledger in its own process. It does not edit .env or create credentials. Gallery configuration remains independent; snapshot uploads remain disabled.

A judge credential, if separately configured, only authorizes the script input path; it cannot bypass the same F2 aggregate allowance, IP limit, queue or ownership rules. While an active run or unsettled pool prevents admission, the current readiness response pauses new submissions. The two-waiter queue bound is unchanged.

## Verification

- 104 focused tests passed in 39.74 seconds; see [focused-tests.txt](focused-tests.txt).
- Both anonymous s3 and judge script requests traversed the real API, spawn, normal runtime, SDK MockTransport, new temporary ledger settlement, owner detail and SSE completion. Source/Lab work and cleanup were synthetic fixtures; no training script, GPU, Tavily or real model request ran.
- Dedicated helper tests cover aggregate spending across restarts, $6.43 daily-limit inheritance, source changes before a later reservation, unknown fees, cleanup uncertainty, concurrent claims and preservation of historical unknown charges.
- Ruff check/format and the scoped secret scan passed. Exact files and hashes: [receipt.json](receipt.json); scan: [gitleaks.json](gitleaks.json).

F1's enumerated implementation files are unchanged. F3 pins all Python source and scripts, so its preparation must be refreshed once after this bridge is frozen. No submission, production run or empirical repair result is claimed here.
