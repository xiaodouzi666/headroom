# Main diagnosis validation feedback — 2026-10-30

Implemented and independently reviewed at source commit 5817a723df82bf9596397f9ae95598925088f1e0.
No live inference or GPU work was initiated by this change's offline verification.

## Observed R8 failures

The preserved R8 campaign finished all nine rows with 0/9 memory targets.
Contract errors occurred in s1 round 02 (overall-feasibility request incorrectly
named current plan IDs), s2 (supplied source lines 140–170 marked missing),
s3/s5 (runtime references incorrectly carried source-line bounds), and nanoGPT
(dependency plus availability errors). s4/s6/s7 instead had valid diagnoses with
genuine requests for more information; no format repair should force them ready.

The old supplement provided code/path and generic repair wording. For example,
INVALID_EVIDENCE_RANGE told the model to reference a source, although the actual
request concerned a runtime observation and needed null line bounds.

## Minimal implementation

The pure validation_feedback helper adds the exact bounded host issue message,
the offending evidence request, current plan IDs, and metadata from the catalogue
already supplied to the model: reference kind, availability, visible ranges and
the runtime-unverified flag. Scope/range instructions describe the existing
contract. The helper does not change the diagnosis, infer source semantics,
supply expected answers, read source files, perform I/O or call a model.

No source snippet was added: the existing validation entry receives metadata, and
expanding that API solely to recopy source was unnecessary for these contract errors.
No Snapshot memory-prose logic was imported into main diagnosis.

Existing supplement count, 2,000-token FINAL48 policy, budget/client path,
needs_more_info behavior, permissions and acceptance thresholds are unchanged.
The helper fits within 8,192 bytes per context and the caller retains its existing
14,000-byte overall feedback bound. Literal strings are inspected before JSON
escaping. Known credential patterns and conservative sensitive assignments,
including quoted keys, cause the whole request context to be withheld. Missing
catalogue data never produces a fabricated visibility observation.

The helper was also added to snapshot_retry.CODE_FILES (19 to 20), because the
shared main validator's feedback changes must invalidate an old prepared snapshot
retry. No old proposal, claim, receipt, history or ledger was rewritten.

## Verification and retained failure

Final guarded focused suite: **149 passed in 7.36s**, exit 0.
It covers four actual retained R8 failures, unchanged genuine-unknown behavior,
SDK MockTransport supplement/token limits, quoted/unquoted/escaped credential
cases, context bounds, existing evidence/policy tests, and all 20 source pins plus
profile/SDK retry tests. Ruff, format and diff checks passed. Independent read-only
review passed after the raw-string and quoted-key redaction fixes.

The first run is preserved: **145 passed, 2 failed**. The two failures were in the
new reduced fixtures: before-evidence JSON lacked the execution_context that the
real orchestrator adds at request time. s2 therefore had missing literal invocation
references and s3 lacked the observed logical_updates child. The fixture was
completed using the existing pure host execution_context function with the saved
report's baseline/request metadata. The production validator was not loosened.
Fixing only the contradictory declaration leaves all four replayed diagnoses
valid but still needs_more_info, rather than falsely ready for patching.

Receipts: focused-initial.log/json and focused-final.log/json.
Source hashes are in focused-final.json. The test fixture records source artifact
hashes and contains no copied source body. These tests demonstrate feedback
construction and containment, not successful repair or new model quality.
