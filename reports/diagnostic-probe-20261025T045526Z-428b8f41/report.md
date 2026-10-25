# Two bounded diagnosis probes — 2026-10-25

These probes tested the updated diagnosis context and literal-argument validation
against two preserved v7 evidence packs. They generated no patch, executed no
GPU workload, and do not change the nine-scenario score or certify acceptance.

## Execution and accounting

| Case | Original source run | Calls | Exact cost USD | Final diagnosis |
|---|---|---:|---:|---|
| s3 | 52bb8129723241889337486bcb187f63 | 1 | 0.05222 | valid; ready_for_patch=true; needs_more_info=false |
| nanoGPT | ff1aaf6695b74045bfee4e0789133427 | 2 | 0.08931888 | invalid; ready_for_patch=false; needs_more_info=true |

Total exact cost: **$0.14153888**. Conservative cost for these calls is identical
because all three charges are exact and settled. There were three dispatches
under the four-dispatch limit; the nanoGPT second call was the existing single
diagnostic supplement, not an SDK retry.

The unchanged shared total/daily limit is $9.99964904. Conservative total usage
increased from $4.968399436 to $5.109938316, leaving **$4.889710724**. Both probe
runs retain the original actual-usage stop line of $0.60. All 78 budget runs are
closed; all 460 attempts are settled; no halt or unresolved charge remains.

The reviewed profile SHA-256 remains
`a15ee9a357b4e0c41aeb46219081066c4d5a2299a777f8f87127dde60118026c`.
Before dispatch, four full provider bounds ($4.292608) fit the remaining
$5.031249604 pool. Output cap was max_completion_tokens=8192, reasoning=false.
There was no recharge, pool expansion, or provider retry.

A remote-control SSH connection closed while the worker was running. The same
remote process continued, saved all artifacts, and settled both runs. Read-only
process and ledger checks confirmed completion. The driver was not restarted
and no request was repeated because of the SSH interruption.

## What changed in s3's response

The v7 diagnosis treated the training batch as 16 and proposed reducing it to 4
with four accumulation steps. The new response explicitly distinguishes
training batch 1 from evaluation batch 16, both with sequence length 512 and
width 768. It proposes only disabling autograd for evaluation, with estimated
saving sufficient for the unchanged 0.4871435264 GB reclaim requirement.
It no longer requests additional evidence before proposing that candidate.

This is a correction in the model's written diagnosis. It supplied no literal
invocation_claims, so its invocation provenance correctly remains unverified.
The captured runtime-input helper supplied observed input information; no
source-default claim was promoted to verified runtime configuration by the host.

No memory saving or numerical-equivalence result was measured. The model's note
that gradient accumulation could reduce training batch further is not usable
as stated when the training batch is already 1. A candidate implementation and
normal verification would still be needed before accepting a repair.

## What did not improve in nanoGPT

Both new responses still use source defaults batch_size=12 and
gradient_accumulation_steps=40 without resolving the retained CLI values
--batch_size=32 and --gradient_accumulation_steps=1. Retained argv is evidence of
the invocation, not independent proof of the final runtime configuration; a
correct diagnosis must account for the precedence instead of silently choosing
the defaults. Runtime input observations remain unsupported for this old OOM
capture, and the required saving remains unknown rather than inferred from an
OOM peak.

The model also explicitly claims execution_argv[0] is train.py. The captured
literal token at index 0 is /opt/venv/bin/python. The new validator detects that
contradiction, sends one bounded supplement identifying the actual visible
token, and keeps the response invalid when the contradiction remains.

The two parsed nanoGPT responses are identical. The SDK request records show
that the second request had five messages instead of three and contained the
literal-contradiction feedback. Both captured request bodies contain the
retained batch and accumulation arguments. This rules out local omission of
those inputs as the explanation for this result; it does not reveal why the
model ignored them.

The useful result here is that the unsupported response is rejected and retained
as a failure. The probe does not establish that nanoGPT diagnosis reliability has
been repaired. No additional call was made after its single supplement failed.

## Audit records

The original evidence JSON/Markdown, baseline result, manifest, captured source
files and actual CLI were checked and pinned during preparation. No saved
diagnosis, ground-truth answer, candidate patch or expected remedy was added to
the probe inputs. The original canonical fixtures and historical failures remain.

| Request | SDK body SHA-256 | UTF-8 bytes |
|---|---|---:|
| s3 initial | 8eae0b98819c2d4e39df89b91399613108bce8b74794cd29317c4fc99a03753a | 145122 |
| nanoGPT initial | 8e92dbb59eab52e730032fe013903e4afb5b214e26faca37c905c95489d2234e | 180639 |
| nanoGPT supplement | 494a7a63679233877d0944b69d38d7c9c5eee724f32b8903eff05ad3195e024c | 187906 |

Public receipts: summary.json, probe-a.json and probe-b.json in this directory.
Raw response text, complete prepared request copies and source pins remain in
the private setup directory. This report contains only bounded interpretation
and accounting summaries; no credentials or runtime-profile contents.
