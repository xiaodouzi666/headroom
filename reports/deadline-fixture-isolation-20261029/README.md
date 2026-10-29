# Pending expiry fixture isolation — 2026-10-29

The three authorized focused checks passed: **3 passed in 13.60 seconds**, exit 0. No full regression, provider request, GPU job, production database change, or production-code change occurred.

## Why the previous test failed

The previous saved run gave the second request only 1.2 seconds for a fresh preparation spawn/import/handshake and queue waiting combined. Its first successful preparation alone took about 1.216 seconds. The second request therefore ended as preparation_deadline_exceeded before entering the pending queue. The old failure remains unchanged in ../final48h-closing-regression-20261029/.

Those observations did not identify the individual cost of harness checks, imports, scheduling or cleanup. The production code intentionally shares one admission deadline across preparation, waiting and execution; this change does not alter that contract.

## Minimal change

Only test_waiting_job_expires_without_starting_and_slow_report_does_not_delay_watchdog in tests/test_api_deadline.py changed.

- The first task still uses real preparation spawn, the real owned worker process, scheduler, expiry thread, timers and cleanup.
- After the first worker starts, the second preparation uses the existing trusted fake_prepare callback locally. It receives the original deadline, with before/after expiry assertions. No new or extended deadline is created.
- The existing 4-second, 1.2-second and 5.2-second thresholds, cleanup grace, and pending/report/watchdog assertions remain unchanged.
- New assertions require a real run.queued event and verify the recorded 1.2-second admission deadline.
- The slow report blocks only queue_deadline_exceeded; the second submission now belongs to the release try/finally.

The separate real-spawn preparation timeout/owned-descendant cleanup check and worker-inherits-remaining-time check were also run unchanged.

## Validation and saved state

The exact three node IDs and command are in [receipt.json](receipt.json). Existing v4 parent and spawn negative probes passed before the run. All recorded source entries were identical before/after execution. Test-file Ruff, format check, and git diff --check passed.

[queue-timeline.json](queue-timeline.json) is a read-only extraction from this run's temporary fixture database:

- Both requests have run.queued events.
- The second task reached queue_deadline_exceeded at 05:09:19.897994 UTC; its 1.2-second deadline was 05:09:19.894802 UTC.
- The first task completed deadline cleanup at 05:09:20.395890 UTC, approximately 4.113 seconds after admission, preserving its 4-second budget plus 0.1-second cleanup grace while the second report was blocked.
- Only the first task has a started marker. Both final rows have api_worker_finished=true and api_cleanup_verified=true.
- The saved rows are post-release final state; the assertions about a pending/unfinished report ran while it was blocked.

[change.patch](change.patch), [original test file](test-before.txt), [guard probes](guard-probe.log), [focused log](focused.log), [source inventories](sources-before.json) and the exact runner text are preserved. The runner is stored as run-focused.py.txt with its hash in the receipt, so formatting tools do not rewrite execution evidence.

This is focused evidence for the repaired test boundary. It does not replace the previously failed full-suite result or certify untested production behavior.
