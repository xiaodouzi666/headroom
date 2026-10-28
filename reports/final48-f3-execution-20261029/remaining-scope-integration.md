# Remaining F3b and clean-checkout integration

Read-only audit after the R7 integration, 2026-10-29. No source edits, new
allocation, model call or GPU execution were part of this audit.

## Already available

Selecting the new runtime profile together with HEADROOM_BUDGET_DB_PATH routes
snapshot diagnosis, Watch and fix to the same new database through
select_budget_database. Normal run opening/closing, actual fee settlement,
whole-pool total and daily constraints already exist. A second accounting core
or another database is unnecessary.

## Work still needed before claiming complete task-specific accounting

- F3b needs one fixed combined ceiling of at most USD 1 across its two CLI
  snapshot diagnoses, real Web diagnosis and Watch demonstration. Snapshot
  invocations each retain their USD 0.30 maximum. Using the shared database alone
  does not express that combined task ceiling.
- Snapshot's normal live path is snapshot_diagnosis._live_runtime. A trusted
  budget factory must preserve its ordinary open/close behavior. The test-only
  SnapshotServices.runtime_factory changes provenance to offline_fixture and
  must not be used to label a real acceptance result.
- SnapshotQueue._execute currently forwards upload paths, profile and per-run
  budget. The server should own any acceptance binding and bind the upload
  hashes/run identity before the worker starts; HTTP callers must not choose
  receipts or money fields. The actual dispatcher also checks both running
  switches and singleton ownership.
- Watch already accepts a trusted fix_runner in watch_command. Its triggered
  repair can use the normal run_fix budget factory while retaining the captured
  command/source identity and the real OOM-trigger record.
- F5 must retain one actual clean-checkout s3 invocation at at most USD 0.30.
  Absolute shared DB/profile locations are supported, but its installed package
  must still import the clean checkout. The original checkout's PYTHONPATH must
  not be used to make an apparent clean reproduction.

The existing common.acceptance_run cannot simply wrap a CLI that creates its
own budget run: that would open a second run without binding the real child.
Its generic non-F1 execution_key is also caller-selected, so it does not itself
prove a fixed number of attempts. Reuse the existing bound-ceiling/factory
mechanism where needed rather than adding a competing accounting system.

This audit identifies remaining engineering; it does not change any public flag,
request a larger pool, broaden authorization, or complete F3b/F5. The current R7
prepared pack remains valid because no implementation file changed.
