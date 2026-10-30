# Snapshot diagnosis repair and bounded F3b retry

Date: 2026-10-30 (Asia/Shanghai). Candidate source and offline checks only.
No provider call, GPU job, production retry claim, changed original funding,
public flag or service restart was performed by this work.

## Diagnosis change

The saved-capture workflow now uses a concise snapshot-specific system prompt.
It keeps the ordinary request context and evidence-availability catalogue,
the same dynamically constrained Diagnosis schema and the same semantic
validator. The prompt includes no scenario answer or ground-truth category.

The shared 400-line automatic-repair prompt included multi-round execution and
strategy material unrelated to uploaded data. The replacement focuses on the
snapshot's actual evidence, missing facts and strict policy while retaining the
2000 completion-token cap, disabled requested reasoning, zero HTTP retries and
zero patch repair retries. It separates cumulative allocation traffic from live
peak contribution, explains decimal GB, and preserves unknown peaks/provenance.

The evidence Markdown now states these measurement semantics before the long
data section. The public numeric observations are unchanged. A repeated
512-byte allocation fixture demonstrates a 512-byte live peak versus 2048
cumulative bytes without changing either quantity.

A valid diagnosis may honestly require more information and have no patch.
Bad dependency scopes, forbidden batch/numerical changes and false missing-source
claims remain rejected. No validator, acceptance threshold or original result
was relaxed.

Files:
- headroom/prompts/snapshot_diagnose.md
- headroom/snapshot_diagnosis.py
- headroom/snapshot_evidence.py
- tests/test_snapshot_diagnosis.py
- tests/test_snapshot_evidence.py

The separate parent change to evidence_blockers is not attributed to this diff.
The independent plan reviewer found no specific blocker in these five files.
That review did not run tests or establish live model quality.

## Offline checks

- Core/evidence: **87 passed in 5.73 s**, exit 0; core-focused.log/json.
- F3b retry allocation: **23 passed in 5.62 s**, exit 0; retry-final-focused.log/json.
- Both used the unchanged closing_guarded_v4.py with passing parent and spawned
  negative probes. Network/provider, GPU subprocess, real credential/profile,
  production ledger, public DB and service operations are denied inside tests.
- Ruff check and format check passed for the six Python files owned here.
- The retry integration test traverses normal build_live_runtime and the real SDK
  with MockTransport, verifies a private cleanup receipt and settles temporary
  synthetic usage. Its live_model label means the ordinary code branch; it is
  not real provider evidence.
- The first core failure was a new test's fixed message-index assumption; the
  router adds a schema system message. It was corrected to select by role.
- The first retry failure reused an attempt ID across two temporary ledger runs;
  the fixture now uses unique IDs. A later profile mutation test parsed its
  deliberately malformed file before reaching the intended guard; it now passes
  the prior in-memory profile and verifies the actual receipt guard.
- All original failed logs remain. The 14-case intermediate pass is a subset of
  the final 23; counts are not summed into a new full-suite result. No full
  repository regression was run.

## Original funding, unchanged

Read-only registry/ledger metadata at 03:58 UTC confirmed:

| Item | USD net |
| --- | ---: |
| Original F3b cap | 1.00 |
| Original F3b conservative charged amount | 0.21737786 |
| F3b remaining after that charge | 0.78262214 |
| Original F48 approved pool | 6.43 |
| Original F48 charged | 2.067736672 |
| Original F48 remaining after charge | 4.362263328 |

The original F3b exact actual remains **unknown** because the historical Watch
attempt included an unknown charge. Existing reviewed conservative accounting is
retained; it is not relabelled exact or zero. The original parent is completed;
all four original children are settled. At that read there were zero unsettled
attempts, open runs or halted runs. See f3b-slot-state.json and
f3b-financial-state.json. These are point-in-time observations, rechecked by every
new proposal/claim.

## Retry implementation

headroom/acceptance/snapshot_retry.py adds a separately reviewed revision in the
existing feature parent/child tables. It never overwrites the original parent,
children, receipt, profile or ledger. It does not spend the judge pool.

Preparation pins the original settled history, content-identical snapshot intent,
original request cap/profile, shared pool state, UTC ledger day, source hashes
and this user authorization. Claiming requires the exact reviewed proposal SHA
and a fresh transaction check. The code hashes cover the snapshot prompt/core,
shared diagnosis/availability/schema, runtime/router/client and budget code.

The existing registry BEGIN IMMEDIATE transaction and recognized feature_children
state make ordinary demo/feature admission observe the retry before ledger open.
The reverse path explicitly checks an outstanding demo claim. A concurrent
demo/retry fixture confirms exactly one winner. A blocked cleanup/charge keeps
the child non-settled, preventing later shared-pool work from bypassing it.

Every revision's charges count with the original F3b charges against the same
<=1 USD cap. The per-run allowance must match the original pinned input intent
and original receipt task cap, never exceed 0.30, and fit the remaining original
pool. The current live s2 template retains its original allowance rather than
raising it. Reserve and dispatch revalidate input/profile/code/history and caps;
dispatch permits only that exact current undispatched reservation. Unknown
charges and cleanup uncertainty block continuation.

This is the existing reviewed estimate-plus-margin admission policy; it does
not turn an estimate into a mathematical guarantee of the provider's final bill.

## First s2 preparation command

Run from the remote repository only after reviewing the final candidate:

```sh
.venv/bin/python reports/snapshot-repair-20261030/prepare-s2-retry.py.txt
```

The command reads the original s2 binding and the recorded input paths, verifies
identical bytes, and saves a new proposal plus request under
.cache/snapshot-repair-20261030/ with mode 0600. It prints the proposal SHA,
run ID and limits, but no credential. It **does not claim, dispatch or mutate
the original registry/ledger**. The current task has prepared this script but
has not run it against production.

Authorization reference: the user's instruction to submit first and then
continue snapshot and all unfinished development, within existing gifts only,
without recharge/overspend and preserving at least $8. This retry does not add
money or reset the F3b cap.

After the parent reviews the prepared SHA, the live controller should:
1. Load that exact proposal/request and call claim_snapshot_retry with its SHA.
2. Persist the returned binding privately before execution.
3. Call run_snapshot_diagnosis with SnapshotServices containing only
   snapshot_retry_budget_factory(binding). Do not inject runtime_factory or a
   custom patcher; the actual reviewed profile and normal SDK path are required.
4. Bound the execution to the normal 480-second deadline. On normal terminal
   return, check snapshot_cleanup_verified(run_root, run_id); separately verify
   process exit/group cleanup. Pass both actual terminal/cleanup facts to
   finish_snapshot_retry. Missing evidence or timeout must remain blocked.
5. Preserve public/diagnosis/private-validation/error and usage/cleanup artifacts
   before any second attempt; no automatic repeat.

The original s2 diagnosis cost $0.040679 net. This is a historical planning
reference, not a forecast guarantee; a valid source-supported diagnosis may
also request one Super static patch draft. The proposal's original run allowance
covers the whole attempt, with no HTTP retry or patch-repair loop. Any SDK
failure/unknown cost follows the existing conservative/blocking rules.

Acceptance for the first new s2 attempt: a schema- and semantic-valid diagnosis,
actual visible stack references, primary cause evaluated against the separately
held s2 truth after generation, no cumulative/peak substitution, accurate
unknown/verification labels, total known or resolved charge within the pinned
run limit and <=0.30, and terminal cleanup. The s2 capture completed 20 updates;
it is not an OOM-recovery demonstration. No uploaded source/GPU execution occurs.

This does not replace the original CLI 0/2, Web invalid diagnosis, R7 1/9 or
6/9 acceptance threshold. The new attempt is a separate retry result. A successful
s2 check alone does not establish the complete two-snapshot plus Web acceptance.


## Final patch-source pin follow-up

The retry's CODE_FILES also pins headroom/patch.py, headroom/patch_structure.py
and headroom/prompts/patch.md. A changed patch generator, structure helper or
prompt between reservation and dispatch is rejected before the SDK call.
The focused follow-up passed **6 tests in 3.06 s**, exit 0
(patch-pins-focused.log/json); this is a targeted subset/extension, not another
full 23-test run or a full repository regression.

Independent read-only review of the parent's new step_call_enclosures helper
found a traversal RecursionError gap. The parent fixed it by dropping the current
file's partial anchors if traversal overflows. The reviewer then confirmed the
per-file rollback, deep-AST test, 12-anchor bound, lexical scope handling and
explicit syntactic-only prompt labels. No remaining concrete blocker was found
in that narrow review. The parent's 52 patch tests are separate evidence; this
agent did not run or reattribute them.

The preparation command is directly executable and intentionally creates no
claim or SDK call. The live steps above require a supervised controller: the
worker must use the normal runtime and budget_factory; only the controller may
call finish_snapshot_retry after checking normal process termination, owned
process-group cleanup and the private snapshot_cleanup_verified receipt. A
timeout, exception, missing receipt or surviving child must keep cleanup false
and leave the claim blocked/unsettled. Do not substitute result.status or
process exit alone for cleanup verification, and do not run an unbound legacy
headroom diagnose CLI against the retry proposal.
