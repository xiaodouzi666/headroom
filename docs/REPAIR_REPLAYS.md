# Curating existing repair replays

The CLI `headroom replay RUN_ID` already reads the saved event sequence without
calling a model or running Lab. It does not curate a run for the web replay list.
`curate_baseline_replays.py` imports explicitly labeled baseline captures; those
rows are not repair evidence and cannot satisfy the repair replay requirements.

The new entry point validates explicit existing repair IDs. It never searches
for five convenient examples, imports baseline records, executes a target, or
regrades a result. All commands below are templates; no real run has been
curated by the implementation tests.

From the azuki project directory:

```sh
source scripts/env.sh
uv run --offline python scripts/curate_repair_replays.py --run-id RUN_ID
```

The default is read-only SQLite inspection. It does not construct Store, create
a database, copy assets, add events, or set flags. Repeat `--run-id` to inspect
an explicitly chosen batch, with at most 16 unique IDs.

After reviewing the dry-run result, an explicit mutation is:

```sh
uv run --offline python scripts/curate_repair_replays.py --run-id RUN_ID --execute
```

Every selected row must be eligible; one failure rejects the whole batch. The
script requires terminal live provenance, one or more saved CUDA repair attempts,
corresponding diagnosis/patch response records, complete ordered events, and
matching run/report/round verification/patch/candidate capture artifacts. It
checks the report's aggregate usage against the stored calls. A successful
target must retain its selected configuration. Failed attempts may be curated,
with their original failed status, target result, unknowns and verification.

For campaign runs, the API's existing artifact routes read from
`runs/jobs/RUN_ID`, while the original files may live below a campaign directory.
Explicit execution mirrors only allowlisted display files, preserving their
bytes and hashes, and records `repair-replay-curation.json`. No source tree,
raw allocator snapshot, credential file, or arbitrary directory is copied.
Existing API jobs are inspected in place. Conflicting existing files are never
overwritten. Before commit, a confirmed rollback removes only newly created
files/directories owned by this invocation. If commit succeeded before an
interruption, or rollback cannot be confirmed, the complete display assets and
audit manifest are retained so published links cannot be broken by cleanup.
The original exception still propagates; inspect the same explicit IDs before
retrying. A failed exclusive manifest write removes only the file created by
that write, leaving all pre-existing files untouched.

Only `public_replay` and its curation audit metadata are added to the existing
run data. Status, target, provenance, measurements, events, rounds and model
usage are not changed. No import/replay events are invented. Repeating the same
curation is idempotent when the recorded assets and metadata still match.

The original report remains byte-for-byte unchanged. Its absolute paths remain
historical source metadata; API downloads resolve approved names under the
canonical job directory, never those absolute paths. The curation manifest
lists the API download URLs and asset hashes. Existing UI event replay and
report/configuration download routes work for the curated run. Downloaded raw
Markdown retains its original relative asset references; no public filesystem
route or arbitrary file browser is introduced.

Execution changes visibility in the currently configured application's replay
list. It does not start a server, expose a port, deploy a site, or contact an
external service. Curation checks the preserved application's records; it is
not a new GPU measurement or proof that a failed run has become successful.
