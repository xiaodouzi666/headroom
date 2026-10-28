# Snapshot diagnosis — engineering verification

Date: 2026-10-29 (Asia/Shanghai). Scope: FINAL_48H F3b-1, bring your own
snapshot. **Live acceptance A is pending; public snapshot uploads remain
disabled.** This report records implementation and offline checks, not a
successful model diagnosis or GPU repair.

## Implemented behavior

The CLI exposes `headroom diagnose --snapshot PATH` with optional
`--traceback`, `--source`, `--budget`, `--runtime-profile`, and `--run-root`.
The [CLI guide](../../docs/CLI.md#diagnose-a-saved-cuda-snapshot) documents the
actual options and capture example. The workflow reads a saved capture, prepares
bounded evidence, validates an Ultra diagnosis against visible allocation-stack
IDs, and can ask Super for one static patch draft when source and a suitable plan
are available. It never runs the uploaded training script or a GPU verification
job. A patch is always labelled **unverified: not run on hardware**.

The native pickle/JSON reader accepts only bounded primitive snapshot data.
Opcode checks and a restricted unpickler reject object construction, including
malicious `__reduce__` payloads; the isolated parsing process has memory, CPU, and
wall-time limits. Inputs reject symlinks, excess sizes, cycles, deep graphs, and
trailing pickle payloads. Limits are 50 MiB for the snapshot, 256 KiB for traceback
text, and 1 MiB for source text. Stack-frame paths never cause host-source reads.

Evidence records `input_kind=uploaded_snapshot` and
`hardware_verification=not_run`; it does not invent a Lab run, parameter count,
seed, step count, loss result, or exact peak. Source is supplied as data and is
not imported or executed. The policy does not authorize model, numerical,
batch-size, or accumulation changes. Public stack references are bound to the
same snapshot/evidence/diagnosis using hashes. Private full evidence remains
separate from the bounded display projection.

Model dispatch still requires an existing reviewed runtime and authorized budget.
This workflow forces strict per-attempt reservation and accepts a request allowance
of at most $0.30; it does not establish credit or increase shared limits. Unknown
charges are not converted to zero. Offline tests use injected fixtures, with their
provenance recorded as `offline_fixture`.

The Web implementation adds a paused upload entry and owner-session result and
download routes. Both submission flags must permit dispatch; a judge credential
does not override the paused state or grant another session's result access.
When enabled, the snapshot queue admits one active job and two waiting/receiving
jobs, applies two uploads per IP per hour unless the judge quota exception
applies, and bounds the whole request lifecycle to at most 480 seconds.
The service stores inputs/results in `runs/uploads` with a 24-hour expiry and
periodic cleanup. The CLI does not start that cleanup worker; custom CLI output
roots require caller-managed retention.

## Verification receipts

These rows describe separate observed runs. **Do not add their counts:** test
scopes and implementation revisions overlap. No full-repository regression was
run for this report, and no tests were rerun while writing this documentation.

| Observed check | Result | Evidence and scope |
| --- | --- | --- |
| Restricted snapshot reader | 70 passed in 1.70 s; Ruff check/format passed | Earlier reader-agent receipt for `tests/test_snapshot_input.py`; malicious reduce, resource/input bounds, primitive compatibility. |
| Snapshot evidence preparation | 39 passed in 1.42 s; Ruff check/format passed | [evidence-check.json](evidence-check.json), including exact source/test hashes and compatibility measurements. |
| Core/API/CLI/launcher integration, earlier implementation | 82 passed in 18.54 s | [integration-tests.log](integration-tests.log); command below. This is historical evidence preceding the final review fixes described below. |
| Core path-redaction follow-up | 32 passed in 3.01 s; Ruff passed | [path-safety-tests.log](path-safety-tests.log), root receipt for `tests/test_snapshot_diagnosis.py`; includes three new core → public projection → Markdown cases preserving constraints between two private paths. |
| Snapshot UI and Home | 46 focused tests passed in 2.12 s | Frontend-agent receipt: SnapshotDiagnosisPanel 20 + App 26; all inputs are synthetic offline fixtures. |
| Frontend type checking and isolated build | Passed | Frontend-agent receipt; Vite output went to `.cache/snapshot-ui-dist`, not the serving `web/dist`. |

The 82-test command was:

```sh
.venv/bin/pytest -q \
  tests/test_snapshot_diagnosis.py \
  tests/test_snapshot_integration.py \
  tests/test_api.py \
  tests/test_public_launcher.py
```

An earlier 17-test core milestone was superseded by this broader run and is not
an additional acceptance count. The 82-test command does not include the reader,
evidence, or snapshot-routes test modules; their own receipts must be consulted
for those scopes. No count is inferred for a module merely because it exists.

Independent review identified two follow-up changes: preserving surrounding
prose when redacting private paths and reporting snapshot-manager lock ownership
correctly in availability. The root fixed path redaction and recorded the
32-test focused result above; the earlier path-related failure log was retained.
At draft time, the manager-ownership change still awaits its final focused
receipt. The historical 82-test result does not verify either later change;
this draft does not claim a full regression after them.

A desktop private-preview screenshot is retained as
[preview-desktop.png](preview-desktop.png). It shows the expanded paused entry
and the nonexecution, unverified-draft, and retention text. A requested 390-pixel
viewport had no effect on the inspected page (`window.innerWidth` remained
1920), so this is **not** a verified mobile rendering result. The temporary private preview and its SSH forward were stopped after inspection.
A temporary build and desktop preview are not proof that public upload is enabled or that a real
upload completed. An earlier four-file secret scan predates subsequent UI edits
and is not a final-source scan receipt.

## Saved real-capture compatibility

The saved s2 and nanoGPT captures were read without running training or models.
Optional saved source and traceback were included as context. All three original
input files in each case retained their hashes. Temporary compatibility output
directories were removed after checking; the original captures were unchanged.

| Observed property | nanoGPT | s2 |
| --- | ---: | ---: |
| Native pickle size | 611,186 bytes | 9,853,783 bytes |
| Segments / allocator events read | 95 / 2,575 | 297 / 60,549 |
| Evidence tokens, cl100k approximation | 17,508 / 24,000 | 16,981 / 24,000 |
| Visible / full-catalog stacks | 9 / 49 | 11 / 31 |
| Private evidence JSON | 1,550,927 bytes | 843,469 bytes |
| Evidence Markdown | 57,332 bytes | 56,153 bytes |
| Public projection JSON | 90,462 bytes | 89,181 bytes |
| Diagnosis schema constructed / evidence ready | Yes / yes | Yes / yes |
| Exact peak established | No | No |
| Hardware verification | not_run | not_run |
| Model diagnosis or patch result in this check | None | None |

Token counts use `cl100k_base`, not a verified provider tokenizer. Both inputs
produce analyzable stack evidence, but that does not establish diagnosis accuracy.
The safe reader discards unrelated payload fields and cannot supply a true-peak
counter absent from its accepted snapshot data. The complete evidence receipt is
[evidence-check.json](evidence-check.json).

## Acceptance A still pending

The unchanged [F3b-1 acceptance](../../docs/FINAL_48H.md)
requires actual model diagnosis of the saved s2 and nanoGPT captures, with the
first cause matching the recorded truth in at least one of the two cases; one
real Web snapshot upload must reach and display a diagnosis; malicious reduce
must be rejected; and each real diagnosis must have confirmed cost at most
$0.30. The adversarial rejection has offline test evidence. The model, real Web
upload, accuracy denominator, and actual-cost requirements remain unverified.

The original F3b total allowance of at most $1 is unchanged. This report creates
no allocation and authorizes no dispatch. There is no new hardware repair,
numerical equivalence, throughput result, or live acceptance success to add to
the project's existing results.

## Final manager-availability correction

The queue exposes a read-only readiness property covering ownership, dispatch
mode, stop state, and the live worker thread. Configuration reports the snapshot
entry as unavailable if a second instance owns the manager or the dispatcher has
stopped; disabled submission flags still report paused. This retains one manager
per project and does not expand public permissions.

The final API-agent run of
`tests/test_snapshot_integration.py` passed **8 tests in 2.60 seconds**,
including real lock contention with both a retention-only owner and an active
owner, startup/shutdown visibility, both submission flags and the read-only
public launcher. Ruff check and format check passed for the three changed files.
These overlap the prior integration receipt and must not be added to it.

The F3 conditional memory-strategy prompt changes separately passed 39 focused
prompt/contract tests in 1.14 seconds. Snapshot routing/queue tests separately
passed 34 tests in 5.80 seconds. Both are offline agent receipts. The new
source, docs, tests and private-preview build are prepared for review; the
serving `web/dist` and public process were not switched to this feature in
this follow-up. The public site remains the previously verified read-only site.
