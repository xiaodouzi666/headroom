# Public API SQLite incident — 29 October 2026

The F2 run failed and its supervisor completed cleanup. An independent database-lock defect left the final cleanup update in a WAL file that had been unlinked while the API still held it open. The running API could return the newer state while a fresh database reader saw older state. A report download returned HTTP 500 at 23:03:13 UTC on 28 October.

## Preserved evidence

The private incident directory named in receipt.json contains ten descriptor/path copies, file metadata and the service journal. The directory is mode 0700 and original evidence files are mode 0400. Raw database copies and request content remain private.

The base database and its reconstruction with the deleted WAL both pass integrity checks and have identical schema hashes. Both contain the failed run, 14 events, one model-call record and one round. Events, model calls, research and rounds have identical content hashes. Only the run table differs: the base records api_worker_finished=false and no cleanup flag at 23:03:11.000056 UTC; the recovered committed update records both flags as true at 23:03:11.601629 UTC.

The deleted WAL has 25 frames in its current generation and a stale recycled tail. SQLite accepted the committed current-generation records. The original database inode did not change; the API process had not restarted. Its original WAL and shared-memory descriptors had link count zero while a new empty WAL existed at the pathname. The local ext4 filesystem had 54% disk use and 1% inode use.

## Cause and fix

The run-detail GET invokes the initial-diagnosis loader. Previously that loader opened and closed the active database with the ordinary artifact-file helper before opening a SQLite connection. POSIX closes release the process's advisory locks for that inode, including SQLite locks. The worker's subsequent Store close could then remove the WAL while the parent continued using its open descriptor. The exact failure was reproduced with the original loader in an isolated two-process API fixture. SQLite documents this mechanism in [How To Corrupt An SQLite Database File, section 2.1](https://www.sqlite.org/howtocorrupt.html).

The diagnosis loader now uses metadata checks without a raw database descriptor and explicitly closes its SQLite reader through SQLite. The snapshot registry had the same unsafe validation pattern: it now uses no-follow metadata checks, and startup raw-opens only a newly created exclusive inode. Regular-file and symlink checks remain; the diagnosis database retains its 1 GiB size limit.

Seven new regression cases cover API/worker WAL lifetime, report downloads, independent and post-close reads of final metadata, snapshot read-lock preservation and unsafe paths. Both lock regressions fail with the original corresponding implementation. The combined focused checks passed 77 tests in 9.56 seconds; Ruff check and formatting passed. No provider or GPU work was performed.

## Recovery recommendation

The standalone reconstruction is analysis/recovered-complete.db inside the private incident directory, SHA-256 e5d1129aa52fb8564357c3911f39748da2c815f9b411adbde12f54cd1ebd22d0. It contains the completed cleanup metadata and retains the failed outcome. It has not been installed by the investigating agent.

1. Finish recording, stop accepting new jobs, and preserve a final capture of the open descriptors before stopping only the dedicated public API service.
2. Compare final file hashes with this capture. If later committed writes exist, rebuild and review a fresh candidate instead of using this earlier reconstruction.
3. With the dedicated service and its workers stopped, archive the database and sidecars together. Install the validated standalone reconstruction as a new file. Never replace or delete sidecars of a running database.
4. Start the API with the source fix and live submissions disabled until their separate funding review completes. Verify failed status, both cleanup flags and report downloads through the authenticated API and an independent SQLite reader.
5. Keep the funding state and any retry decision separate: database recovery does not reconcile the unknown exact model charge or turn the failed outcome into a success.

Production recovery is owned by the parent task. This handoff changes source and isolated test fixtures only; the original service, database and budget were not modified by this agent.


## Independent post-recovery verification

The parent task subsequently restored the standalone database and restarted only the dedicated public API. Independent checks recorded in recovery-validation.json then returned HTTP 200 for the public homepage, health and configuration endpoints, and for the original owner's run detail and both report downloads. The run remains failed; both cleanup fields are true in the API and an independent SQLite reader. Integrity checks pass, and no API database descriptor points to a deleted WAL or shared-memory file. The baseline container is absent. New live runs, snapshots and judge-script submissions remain disabled; the previously authorized read-only verified gallery remains enabled.

This validation reused the private recording session for GET requests only. The private execution-review file binds the original failed-run artifacts and this validation by hash. It supports a separate funding-state review and does not authorize or perform another execution.
