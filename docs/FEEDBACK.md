# Tool feedback

All 60 original Token Factory inference probes have been executed, including preserved failures and unverified controls. The four-model matrix, Ultra long staircase and Super four-way experiment are recorded below. Full T0.4 awaits root's installed-configuration review and final receipt; complex client/schema and model-driven repair acceptance remain separate.
Tavily observations below come from the authorized live run on 2026-10-24.


## TAVILY-001 — Search depth does not pin the PyTorch version

Observed 2026-10-24 00:57 UTC using tavily-python 0.8.5. For the same query
`PyTorch 2.5 torch.utils.checkpoint use_reentrant False`, with max_results=2 and
the same official/GitHub domain restriction, both basic and advanced returned
the same two URLs: PyTorch main checkpoint documentation and the main-branch
checkpoint.py source. Basic took 2.932 seconds and reported 1 credit; advanced
took 4.297 seconds and reported 2 credits. Advanced snippets contained 1,461/2,300
characters versus basic's 1,357/1,445. These are single observations, not a latency
benchmark or proof that one depth is generally more accurate.

Implication for Headroom: a version number in the search query does not establish
that the result applies to that installed version. A version-sensitive repair
must inspect a pinned documentation/source URL. More text or a higher score alone
does not establish better evidence. This observation does not change the plan's
research strategy or acceptance criteria.

Evidence: `reports/probe-tavily-20261024T005720856027Z-332161bd.json`, operations
`search_basic` and `search_advanced`. Only metadata, shapes and content lengths
were retained; no raw page content or credentials were saved.

## TAVILY-002 — Pinned extraction works; zero reported credits is not a free tier claim

In the same live run, basic extraction returned the exact requested PyTorch 2.5
checkpoint URL and pytorch/pytorch issue 102223 URL. Their nonempty raw_content
lengths were 17,645 and 14,925 characters, with empty failed_results arrays.
Observed client elapsed times were 1.335 and 0.148 seconds respectively. Both
responses supplied title, URL, raw_content, images, response_time, usage and
request_id fields; images was empty. Each response reported usage.credits=0.

Implication for Headroom: validate the requested URL, nonempty raw_content, and
failed_results instead of relying on an HTTP success alone. Keep API-reported
usage separate from account billing: this run reported 3 credits in total, and
the refreshed free-plan account counter independently moved from 0 to 3/1,000.
The zero extract values do not prove that later extraction is free; the account
page prices basic extraction in groups of five URLs. The historical issue is an
extraction fixture and does not establish its applicability to installed PyTorch.

Evidence: `reports/probe-tavily-20261024T005720856027Z-332161bd.json`, operations
`extract_checkpoint` and `extract_issue`, plus
`reports/tavily-account-after-20261024T005808Z.json` for the account observation.


## Token Factory — minimal live integration verified

Two authenticated directories and one Super/Nano chat each succeeded on2026-10-24.
The observations below do not establish full T0.4 or end-to-end repair acceptance.

## Nemotron Ultra — long-input evidence pending

The evidence builder emits bounded source and allocator context; actual Ultra
long-input acceptance, 1M-context behavior and end-to-end diagnosis remain
unmeasured. No “million-token success” claim is justified.

## Nemotron Super — patch behavior pending

Diff, compilation, honesty and retry controls run against offline structured
responses. Actual Super patch quality remains unmeasured. One minimal chat cost estimate is recorded below.

## Nemotron Nano — label behavior pending

Top-stack labels and a two-cent run sub-budget are implemented and tested offline.
Eight-scenario live category agreement remains unmeasured. One minimal chat cost estimate is recorded below.

## TAVILY-003 — Versioned runtime research and cache reuse

On 2026-10-24 the production ResearchSession retrieved PyTorch 2.5 checkpoint
and CUDA allocator references through search plus extract. Four real methods
reported 3 credits total. Repeating both requests used cached content, issued
zero methods and reported zero credits; eight research-operation rows were saved.
Evidence: reports/research-component-20261024T022414Z.json. This is component
validation, not an s1/s5 completed repair report. Retrieved issue applicability
remains explicitly unverified.

## Actionable suggestions

These are integration requirements inferred from observed behavior, not claims
about untested provider failures:

1. Tavily: support explicit documentation-version constraints and return whether
   a result actually matches that version, rather than relying on query words.
2. Tavily: document credits/rounding at per-operation and account-counter levels;
   an extraction response with zero credits can otherwise be misread as free.
3. Token Factory: expose an account hard spending cap separately from automatic
   payment thresholds, with a clear API status when the cap is reached.
4. Token Factory/model APIs: surface the documented max_completion_tokens reasoning
   semantics beside each model and keep usage/model identity consistent on error paths.
5. Model documentation: publish tested structured-output and long-input capability
   tables per exact model identifier so client profiles can be evidence-backed.


## TF-001 — Authenticated directories differ, core candidate access overlaps

At10:21UTC both official verbose directories returned200; the US directory listed18
models and the default directory30. Both included Ultra, Super, Nano and Lightning.
UI processing-region labels did not prevent the two later US-endpoint chats. This
supports reading each actual directory before dispatch, not assuming that region
labels require different client URLs. Other models/endpoints were not invoked.

## TF-002 — Nano spelling is an exact API identity

The live catalogue and every identity-bearing SSE event used
nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B. The plan's lowercase historical candidate is
not the observed identifier. Explicit selection and exact response verification
worked; no alias or silent lowercase transformation was required.

## TF-003 — Super reports reasoning inside the completion count

One US-endpoint chat with max_completion_tokens=128 returned23 prompt,19 completion
and14 reasoning tokens, stop, with first content at670.258ms and total670.570ms.
Its exact response identity matched. The usage-priced estimate was0.000024USD.
This is one small request, not a latency benchmark, JSON/tools validation or patch
quality result. The documented output cap includes reasoning; no reasoning toggle
was tested by this request.

## TF-004 — Nano streams reasoning without a reasoning-token breakdown

One Nano chat with the same128 completion ceiling returned23 prompt and47 completion
tokens, stop, first content at1474.222ms and total1506.663ms. Reasoning appeared in
the stream, but usage omitted the reasoning/cache details present for Super. The
ordinary-input usage estimate was0.00001266USD. Missing fields remain unknown;
they are not zero reasoning or zero cache claims. Stack-label agreement is pending.

## TF-005 — Cached pricing differs between directory and Prices UI

Nano's authenticated catalogue returned input_cache_read=null while the account
Prices UI showed0.012USD per1M cached input tokens. Ordinary input/output values
matched after the API-to-1M conversion. Headroom retained the discrepancy and used
ordinary input pricing conservatively; the shared net cap also reserved21% for
possible tax because UI prices exclude tax. The two-chat total0.00003666USD is a
usage estimate, not a reconciled invoice or a guarantee of future pricing.

Evidence for TF-001 through TF-005: reports/tokenfactory-minimal-20261024.json;
raw source paths and SHA256 values are retained there. Public sources:
https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion,
https://docs.tokenfactory.nebius.com/cached-tokens.md,
https://tokenfactory.nebius.com/organization/prices.

## TF-006 — Ultra first chat succeeded with bounded reported reasoning

The 2026-10-25 local checkpoint sent one Ultra chat with max_completion_tokens=1024.
The exact Ultra identity matched in every identity-bearing event; HTTP200 ended
with stop and nonempty_content. Usage was 23 prompt and 20 completion tokens,
including 16 reasoning tokens; the usage-priced cost was $0.000083. The retained
classification does not preserve the exact answer text. This establishes a
single small Ultra inference, not long-input capability or diagnosis accuracy.

## TF-007 — Super native schema passed one exact object check

One Super json_schema request with max_completion_tokens=256 returned HTTP200,
stop and exact_json_shape: the validator checked probe=headroom and integer
value=7 with the required key set. Usage was 29 prompt / 76 completion, with 61
reasoning tokens inside completion; cost $0.0000771. This supports the native
schema method for this fixture. Complex Diagnosis/Patch schema reliability and
the dedicated real client acceptance remain untested.

## TF-008 — Super generated the expected function call

One Super tools request returned expected_tool_call and finish_reason=tool_calls.
The classifier verified add with arguments matching a=2 and b=3. Usage was
394 prompt / 40 completion, including 9 reasoning tokens; cost $0.0001542.
Content TTFT was null because this was a tool-call response; event TTFT was
793.903ms and elapsed 916.082ms. No external function or Tavily was executed,
so this does not close T2.2's multi-turn research acceptance.

Evidence for TF-006 through TF-008: reports/model-checkpoint-20261025/verification.json
and its hashed per-call reports. Exactly three POSTs, no retries, no unknown
billing or token-bound violation. Total usage-priced cost was $0.0003143;
21% reference amount $0.000380303 is not a reconciled invoice. Every dispatch
had a manual current catalogue price/context/fee review. At that checkpoint,
the script version did not enforce equality between new catalogue metadata and
the reviewed file. The later capability groups below record catalogue guards
and catalogue_consistency_passed=true; the earlier limitation remains historical.


## TF-009 — All four models passed the small JSON fixture

Ultra, Super, Nano and Lightning each returned the exact two-key object in
json_object, json_schema and fenced-prompt modes. The twelve samples checked
probe=headroom, integer value=7 and no extra keys; Super json_schema came from
the earlier checkpoint. This gives an observable integration baseline for all
three JSON paths. It does not show that the larger Diagnosis/Patch schema is
reliable, and does not establish a production fallback ordering.

## TF-010 — HTTP 200 did not guarantee Nano's requested tool call

Nano's forced add(a=2,b=3) fixture returned HTTP 200 and finish=stop, but the
validator recorded missing_or_wrong_tool. Its 312 prompt / 31 completion tokens
cost $0.00002616, so a failed capability still had a known charge. The retained
classification does not distinguish a missing call from a different call;
neither should be invented from the report. Ultra, Super and Lightning passed
the expected-call classifier. None of these fixtures executed an external tool.
A surfaced model-specific tool-support declaration would help avoid treating an
accepted HTTP request as demonstrated tool capability.

## TF-011 — Template and effort controls changed the observed reasoning stream

For the same short arithmetic prompt, enable_thinking true/false and
reasoning_effort high/none each switched from a visible reasoning stream to none.
Reported reasoning-token pairs were Ultra 121/0 and 91/0, Super 48/0 and 48/0,
and Lightning 439/0 and 702/0. Nano showed the same stream-present/absent pairs,
but omitted reasoning-token usage: that missing count remains unknown, not zero.
This supports an observable toggle in these specific pairs. It does not prove
hidden reasoning was absent, answer correctness, or reliability on other tasks.
Consistent reasoning usage fields across models would make the control easier
to audit.

## TF-012 — The /no_think system prefix was ineffective in these four tests

The /think versus /no_think system-prefix requests both produced reasoning in
every model. The /no_think cases reported 88 reasoning tokens for Ultra, 48 for
Super and 691 for Lightning. Nano also streamed reasoning but supplied no count.
The prefix therefore did not provide an observed off switch in these samples.
The request was accepted, but acceptance must not be documented as enforcement.

## TF-013 — Lightning exceeded both requested 128-token reasoning parameters

With reasoning_budget=128, Lightning reported 380 reasoning tokens; with
max_thinking_tokens=128 it reported 450. Both requests returned HTTP 200 and
finish=stop. These are direct counterexamples to treating either parameter as
an enforced 128-token ceiling for this tested endpoint/model.

Ultra reported 92/100 and Super 48/48 for the two parameters. Those values are
below 128, but a short task ending naturally cannot prove enforcement. Nano
omitted reasoning-token counts and returned 103/118 total completion tokens;
that also does not demonstrate a binding limit. A rejected unsupported parameter
or explicit effective-limit metadata would be clearer than accepting an
ineffective parameter. The separate max_completion_tokens=1024 ceiling was not
violated, so this is not a billing-bound failure.

## TF-014 — Reasoning off was not uniformly cheaper in the observed samples

Super template on/off used 92/200 completion tokens and cost
$0.0000936/$0.0001908. Effort high/none used 97/454 and cost
$0.0000981/$0.0004194. Both off cases reported zero reasoning tokens, but longer
visible output made their total usage charges higher in these individual tests.
A generic lower-cost claim would therefore be unsupported; applications should
record total completion usage and exact response behavior. These are single
samples, not a repeated latency, quality or cost benchmark.

Evidence for TF-009 through TF-014:
reports/live-campaign-20261025/capability-review.json links all source reports,
root group reviews, JSON observation pointers and SHA-256 hashes. The review
combines 47 new single calls with five preserved checkpoint calls; it performs
no new request, changes no raw result and enables no model configuration.
The 47 new calls cost $0.00691720; all 52 capability samples total $0.00726816
before any tax reconciliation. That capability-only review did not measure
long-input or four-way concurrency; their later evidence follows below.


## TF-015 — Ultra reached 500,029 prompt tokens; the 900k failure was rate limiting

The requested local approximations 64k/200k/500k produced server prompt counts
64,031/200,031/500,029 and exact-needle responses with matched Ultra identity.
The generator count and provider count are different measurements. This
establishes a successful tested input lower bound, not the model's exact maximum
context or general long-document reasoning quality. The proposed 150k evidence
budget is within 60% of the largest successful observed sample.

The 900k request returned HTTP 429 with Retry-After=255, no usage and no response
model identity. It was not retried and must not be interpreted as context
overflow. The full $1.049344 reservation remains permanently allocated to this
campaign with actual cost unknown. After the stop and separate independent
review, root waited past 21:17:23.615810 UTC, refreshed the account and allowed
other original-plan calls. No zero-charge inference was drawn from unchanged
UI balance. Structured error metadata that distinguishes context rejection from
rate limiting and provides request-linked billing disposition would improve
large-input planning.

Evidence: reports/live-campaign-20261025/ultra-long-64000/report.json,
ultra-long-200000/report.json, ultra-long-500000/report.json and
ultra-long-900000/report.json under that campaign directory; their root reviews;
reports/live-campaign-20261025/retained-429-review.json and
reports/live-campaign-20261025/claims/ultra-long-900000-continuation-review.json.
The original failed report and safe_to_continue=false review are preserved.

## TF-016 — One four-way Super group completed without a rate-limit error

The four concurrent Super requests each returned HTTP 200, exact model identity,
nonempty content and finish=stop. They used 23 prompt tokens each and
19/36/19/19 completion tokens; reasoning breakdowns were 14/31/14/14.
Per-request elapsed times were 796.834/959.101/884.664/884.643 ms. The total
usage-priced charge was $0.0001113, with no unknown usage or retained upper
charge in this group. This supplies one observed four-way concurrency result,
not a sustained throughput guarantee or a claim that the earlier Ultra
rate-limit condition cannot recur.

Evidence: reports/live-campaign-20261025/super-concurrency-4/report.json and
reports/live-campaign-20261025/claims/super-concurrency-4-review.json.
The per-request measurements do not report total group wall time or an
end-to-end application latency benchmark.

Final root review: T0.4 accepted by reports/t0.4-acceptance-20261025.json after installing the measured constants; subsequent real diagnosis/repair remains separately assessed.

## TF-017 — Real client transport passed; free-text diagnosis overclaimed fragmentation

The actual router accepted Super native JSON (181input/89output,0.0001344USD) and a source-pinned53-record Ultra evidence package (268920provider input/149completion,0.269367USD,10.914s). Both were single attempts with exact identity and complete usage. The Ultra free-text response called the cache gap and allocator indicator severe fragmentation, which the measurements do not prove. This is a model-interpretation failure to track, not a verified root cause. T1.3 accepts transport/long-input delivery; T1.4 separately scores diagnosis against authored truth and actual stack references. Evidence: reports/t1.3-acceptance-20261025.json and the immutable execution result paths within.

## TF-018 — Native schema improved reference validity but did not enforce semantic policy

The v4 and v5 diagnosis batches used the same eight original captured workloads
and unchanged truth, policy and acceptance thresholds. Both matched seven of
eight first categories; s5 remains unverified truth and never supplies a match.
In v4, some response references did not exist in the actual stack catalog.
The v5 request bound each reference to that catalog with a dynamic native schema:
all eight reference sets were valid, and all eight calls ended with stop and
zero reported reasoning tokens. This is an observed batch result, not a general
guarantee of model correctness.

The complete v5 gate still failed. s1 and s6 included changes forbidden by the
current policy; s7 requested more information. A schema that limits permission
keys and numerical-impact values cannot itself prove that the free-text
proposal obeys those meanings. Headroom retained its semantic and actual patch
checks. The v5 known usage-derived cost was $0.328770. Earlier failures were not
rescored after implementation changes.

Evidence: reports/live-campaign-20261025/diagnosis-attempt3-review.json and
diagnosis-attempt4-review.json, with original bounded responses and hashes.

## TF-019 — Nano omitted cache usage in the first real repair pipeline

The first MVP attempt reached a genuine s1 GPU baseline and one Nano annotation
response. HTTP200 and the exact requested Nano identity were recorded. Parsed
usage contained 3643 prompt tokens, 480 completion tokens and total4123, but
cached_tokens and reasoning_tokens were null. Because the account has a distinct
cached-input price, the original exact-cost calculation refused to treat the
missing cache count as zero. Its missing_cached_token_usage result caused the
shared budget guard to stop the run and the remaining eight scenarios.

The original complete provider reservation $0.01644864 remains occupied, and
actual cost remains unknown. The priced token counts permit a conservative
upper-bound calculation; they do not determine the exact cached split or
invoice. This run did not separately persist the raw SDK usage object, so the
parsed missing field must not be described as a raw provider declaration of
cached=0. Consistent usage details would avoid this accounting ambiguity.
The failed campaign is preserved and is not a successful repair.

Evidence: runs/evaluation/live/20261024T221011565478Z-4deef5b7/campaign.json,
reports/live-campaign-20261025/mvp-v1-audit.json, and the source-pinned call record
for run1ae2055418724d708a7b2fb1a9e76fc6 / attempt4b98ca96f08441c38f5fdca0537eaf4f.

## TF-020 — Super exhausted patch output in reasoning; old diff failures remain ambiguous

MVP v2's s1 generated 16 Super patch/fixer attempts across four rounds. Six
responses reached the original 4000 total-completion cap: five reported 4000
reasoning tokens and the sixth reported 3962. They corresponded to rejected
truncated/filtered responses. The production patcher had not explicitly selected
reasoning=False; accepting a total output cap did not guarantee useful visible
JSON within it. The 4000 limit remains unchanged.

Ten other attempts failed before git apply with “diff must touch between one
and twenty files”. Their raw parsed.diff values were not persisted, so this
message cannot establish whether the model omitted headers, double-escaped
newlines, returned prose, or produced another malformed form. The independent
standard-diff receipt successfully parsed/applied/compiled both standard unified
diff and the same diff with a matching optional git header. Negative controls
for literal backslash-n and plain explanation reproduced the old file-count
error. This rules out claiming a demonstrated prompt/parser contradiction; it
does not reconstruct the ten missing responses.

All 16 attempts stopped before apply/compile; no candidate GPU result or
numerical-equivalence result exists. s1's final diagnosis requested more
information; the eight later cases were operationally skipped, not eight
independent model quality failures. Failed model requests remained in the
financial records.

The applied common revision now requests reasoning=False for patch and fixer,
keeps max_completion_tokens<=4000 and existing policy/parser checks, clarifies
the existing standard-diff instructions, and saves private bounded visible
response evidence. Current production-tree targeted integration passed 294 guarded tests. At that v2 checkpoint there had been no next live validation. Later v3/v4 failures are recorded below; this change is not reported as a successful model repair. Clear effective reasoning-control metadata and
complete usage on truncated responses would help clients diagnose this failure
without assuming that a short or schema-constrained response is reliable.

Evidence: [v2 repair findings](../reports/live-campaign-20261025/mvp-v2-repair-findings.md),
[v2 audit](../reports/live-campaign-20261025/mvp-v2-audit.json),
[standard diff receipt](../reports/unified-diff-contract-20261025.json),
[ambiguous-error controls](../reports/unified-diff-contract-20261025-supplement.json),
and [applied revision](../reports/super-patch-fix-20261025/application.json).

## TF-021 — A second Nano response omitted the cache split; its cost remains bounded

The fresh v2 s1 annotation response used 3643 prompt tokens and 136 completion
tokens (3779 total) with the exact Nano identity. Parsed cached-token usage was
again missing. This is a new response, separate from v1's 480-completion
observation. Missing cache usage is not cached=0 and is not an exact invoice.

Using the reviewed maximum input tariff of $0.06 per million and output tariff
$0.24 per million gives the conservative upper
3643*0.06/1,000,000 + 136*0.24/1,000,000 = **$0.00025122**.
The runtime verified provider-bound admission, identity, valid usage, output cap,
tariffs and successful ledger settlement before marking this charge bounded.
Actual cost remains null; exact-cost complete remains false. The known s1
subtotal $0.14104766 plus this bound yields $0.14129888 conservative total,
not known actual spend. This newly bounded charge is distinct from v1's
separately reviewed, permanently retained full reservation of $0.01644864.

This proves only that this annotation charge is no greater than the original
$0.02/run limit. It does not pass eight-case Top40 annotation coverage,
delivery to Ultra or the >=80% heuristic-agreement gate. Returning a consistent
cached-token count on every response would make exact usage-priced accounting
possible without this uncertainty. The old parsed record does not substitute
for a separately saved raw SDK usage declaration.

Evidence: [v2 call/ledger audit](../reports/live-campaign-20261025/mvp-v2-audit.json),
[operational audit note](../reports/live-campaign-20261025/mvp-v2-operational-audit-note.json),
and [post-v2 saved ledger review](../reports/live-campaign-20261025/mvp-v2-profile-restored.json).

### TF022 — native JSON string flattened patch line boundaries

In MVPv3, Super returned54 complete structured responses with stop/zero reported reasoning. Raw visible JSON and parsed objects agree:52 nonempty unified diff strings have zero LF and zero literal backslash-n separators across multiple scenes. Local parser/control experiments accept standard paired headers with or without diff --git; no local newline stripping was found. Consequently the strict file/hunk parser rejected these52 nonempty responses. A separate empty diff was rejected as NO_CHANGE, making53 total rejections; the other empty-diff CLI-only response reached the real Lab but failed its unsupported argument. This isolates an observed wire-output problem; it does not prove an internal provider cause or a valid repair.

Action: request explicit diff_lines arrays, one physical line per element; reject embedded CR/LF and deterministically join the supplied boundaries while retaining original wire and normalized artifacts. Keep git apply/compile/honesty/4000-token limits intact. At that checkpoint a generic one-call transport check was planned. The first component failed its hunk format; a second unchanged-source component passed through the normal bounded fixer. Final MVPv4 results below do not establish patch correctness merely from transport. Evidence: reports/live-campaign-20261025/mvp-v3-repair-review.json.


## TF-023 — Explicit line transport fixes boundaries, not patch structure or placement

Final MVPv4 preserved explicit diff_lines boundaries, but110 patch attempts yielded88 format/safety rejections,19 application failures,1 response rejection and2 apply/compile successes. Missing prefixes, incorrect hunk counts and copied source display labels are directly retained in response evidence. The current fixer receives a generic invalid-diff message, losing more specific parser detail. One compiled s1 patch landed after the live main path and stillOOM; s8 retained a3.556% peak reduction but missed20%. Proposed bounded structural diagnostics, separate raw-source/line metadata and exact source anchors require the owner's next-round decision. No scenario-specific correct patch was supplied to the model.

MVPv4 used165 calls; all-call known subtotal1.037464332USD, plus verified missing-cache Nano bounds yields1.039832052USD conservative total, actual totalnull. The aggregate known_cost field0.549897932 sums only fully known runs and must not be called the all-call known subtotal. Returning consistent cache usage and exact editable-source/schema behavior would make integrations easier to verify. Evidence: reports/live-campaign-20261025/mvp-v4-finance-review.json; mvp-v4-candidate-verification-review.json; mvp-v4-next-repair-options.md.

## TAVILY-003 — Real model-directed research and cross-run cache, incomplete required Sources

Final MVPv4 recorded9 research rows with8 actualAPI calls and7 reportedcredits. s4's native model tool loop searched then extracted https://docs.pytorch.org/docs/2.5/checkpoint.html with version_match=true. s5 reused s3's exact cached query with api_calls=0 and credits_used=0, preserving the origin request. Nevertheless s1 lacks the required checkpoint Source and s5 lacks the required CUDA-memory Source, so the original T2.2 gate fails. Tool execution and organic use are observed; citation completeness is separate. More consistent version-specific ranking would reduce irrelevant-result handling. Evidence: mvp-v4-candidate-verification-review.json.

## Source-span component observation — 2026-10-25

Super returned source-span IDs and full SHA correctly. The first response included an unchanged second edit and was rejected; its repair added an unreachable duplicate return alongside the requested docstring. The exact source-to-candidate chain and compile passed, while the independent docstring-only AST invariant failed. Two calls cost $0.0013896 in total. Range IDs solve placement and copying ambiguity; they do not establish semantic correctness. Failed artifacts remain in runs/acceptance/source-span-patch-component-20261025-v1 and the public component report remains accepted=false.

Source-span component follow-up: clarifying docstring-only/no duplicated statements yielded an accepted single response. New call $0.0006405; family total $0.0020301 across three calls. Prior failure retained; no benchmark success inferred.
