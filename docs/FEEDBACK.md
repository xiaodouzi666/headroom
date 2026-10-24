# Tool feedback

Token Factory observations remain pending credentials and credit confirmation.
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


## Token Factory — live experience pending

Endpoint scoping, explicit authorization, retry accounting and partial-report
behavior have offline tests. No authenticated Token Factory experience has been
measured. Feedback about actual latency, reliability or billing is pending T0.4.

## Nemotron Ultra — long-input evidence pending

The evidence builder emits bounded source and allocator context; actual Ultra
long-input acceptance, 1M-context behavior and end-to-end diagnosis remain
unmeasured. No “million-token success” claim is justified.

## Nemotron Super — patch behavior pending

Diff, compilation, honesty and retry controls run against offline structured
responses. Actual Super patch quality and model costs remain unmeasured.

## Nemotron Nano — label behavior pending

Top-stack labels and a two-cent run sub-budget are implemented and tested offline.
Eight-scenario live category agreement and actual Nano costs remain unmeasured.

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
4. Token Factory/model APIs: document whether max output tokens includes billed
   reasoning and provide consistent usage/model identity on interrupted/error paths.
5. Model documentation: publish tested structured-output and long-input capability
   tables per exact model identifier so client profiles can be evidence-backed.
