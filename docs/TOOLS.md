# Tavily tool contract and T0.5 probe

Status: **T0.5 accepted on 2026-10-24** after four authorized live operations,
exit code 0, independent report review, two factual FEEDBACK entries and this
schema update. See `reports/t0.5-acceptance.json`. This establishes the four probe
operations, not the later T2.2 research agent or any Nebius model acceptance.

## Installed SDK inspected

The remote environment contains `tavily-python 0.8.5`. The following signatures
come directly from `inspect.signature` on that installed distribution, inspected
2026-10-23; they are not inferred from an API response. The full strings are also
saved in every probe report. `search()` and `extract()` return untyped Python
dictionaries. The SDK inserts an empty `results` list when absent; `extract()`
also inserts an empty `failed_results` list. Therefore dictionary presence or an
HTTP 200 alone does not establish successful content retrieval.

```python
TavilyClient.search(self, query: str, search_depth: Literal['basic', 'advanced', 'fast', 'ultra-fast'] = None, topic: Literal['general', 'news', 'finance'] = None, time_range: Literal['day', 'week', 'month', 'year'] = None, start_date: str = None, end_date: str = None, days: int = None, max_age_hours: int = None, max_results: int = None, include_domains: Sequence[str] = None, exclude_domains: Sequence[str] = None, include_domains_mode: Literal['restrict', 'prefer'] = None, include_answer: Union[bool, Literal['basic', 'advanced']] = None, include_raw_content: Union[bool, Literal['markdown', 'text']] = None, include_images: bool = None, timeout: float = 60, country: str = None, auto_parameters: bool = None, include_favicon: bool = None, include_usage: bool = None, exact_match: bool = None, fetch_timeout: float = None, cache_fallback: bool = None, language: str = None, filter_by_language: bool = None, **kwargs) -> dict
TavilyClient.extract(self, urls: Union[List[str], str], include_images: bool = None, extract_depth: Literal['basic', 'advanced'] = None, format: Literal['markdown', 'text'] = None, timeout: float = 30, include_favicon: bool = None, include_usage: bool = None, query: str = None, chunks_per_source: int = None, **kwargs) -> dict
```

## Fixed probe operations

| ID | Method | Fixed request |
|---|---|---|
| search_basic | search | `search_depth="basic"`, maximum 2 results |
| search_advanced | search | `search_depth="advanced"`, maximum 2 results |
| extract_checkpoint | extract | PyTorch 2.5 checkpoint documentation, basic extraction |
| extract_issue | extract | pytorch/pytorch issue 102223, basic extraction |

Search query: `PyTorch 2.5 torch.utils.checkpoint use_reentrant False`. Search
uses the official-documentation/GitHub domain restriction, `auto_parameters=False`,
no generated answer, and no raw content. All four requests set `include_usage=True`
and timeout 30 seconds. Each operation is attempted once with no automatic retry,
fallback query, account request, or model call. The endpoint is fixed to
`https://api.tavily.com`; the client ignores ambient proxy configuration.

The extract inputs were checked with ordinary public-page reads, not through
Tavily: [PyTorch 2.5 checkpoint](https://docs.pytorch.org/docs/2.5/checkpoint.html)
and [pytorch/pytorch issue 102223](https://github.com/pytorch/pytorch/issues/102223).
The issue is an extraction fixture, not evidence that its historical behavior
applies to our installed PyTorch release. Versioned documentation avoids the
moving `stable` redirect.

## API response shapes — documentation and live observations

The following field shapes are supported by the official
[Search reference](https://docs.tavily.com/documentation/api-reference/endpoint/search)
and [Extract reference](https://docs.tavily.com/documentation/api-reference/endpoint/extract),
read on 2026-10-23. Optional fields depend on request options and API behavior.
These general contracts are documentation-based. The report below records the
actual sanitized field/type structures observed in the authorized live run.

```text
SearchResponse = {
  query?: string,
  results: [{url: string, title?: string, content: string, score?: number,
             raw_content?: string | null, ...}],
  answer?: string | null, images?: array,
  response_time?: number | string,
  usage?: {credits?: number, ...}, request_id?: string, ...
}
ExtractResponse = {
  results: [{url: string, raw_content: string, images?: array, ...}],
  failed_results?: [{url: string, error?: string, ...}],
  response_time?: number | string,
  usage?: {credits?: number, ...}, request_id?: string, ...
}
```

An extract response may contain failures even with HTTP 200; each requested URL
must have nonempty `raw_content`. Search needs at least one nonempty content result
with an HTTP(S) URL. Malformed results, missing URLs, empty lists, and any extract
failure cause a failed operation. Returned credit usage is recorded verbatim as
numeric `usage.credits`; absent/invalid usage stays `null`, never assumed zero.
Extract's reported credits may be zero before its accumulated billing threshold;
zero is not proof of a permanently free request.

## Live results, 2026-10-24

Command: `.venv/bin/python scripts/probe_tavily.py --execute`, exit 0. Report:
`reports/probe-tavily-20261024T005720856027Z-332161bd.json`. Exactly four SDK method
attempts were made, with no automatic retries or fallback queries.

| Operation | Content result | Client elapsed seconds | API-reported credits |
|---|---|---:|---:|
| search_basic | 2 nonempty results | 2.932 | 1 |
| search_advanced | 2 nonempty results | 4.297 | 2 |
| extract_checkpoint | Exact versioned URL; 17,645 raw-content characters | 1.335 | 0 |
| extract_issue | Exact issue URL; 14,925 raw-content characters | 0.148 | 0 |

Both extracts returned an empty failed_results array. All four responses had a
unique request_id. Search returned main-branch URLs despite the version keyword;
see TAVILY-001 in FEEDBACK. These observations are not statistical performance
claims or a content-accuracy evaluation.

The actual successful response shapes were:

```text
Search = {
  query: string, follow_up_questions: null, answer: null, images: [],
  results: [{url: string, title: string, content: string, score: number,
             raw_content: null, id: string}],
  response_time: number, usage: {credits: integer}, request_id: string
}
Extract = {
  results: [{url: string, title: string, raw_content: string, images: []}],
  failed_results: [], response_time: number,
  usage: {credits: integer}, request_id: string
}
```

The report preserves item counts separately (2 for each search, 1 for each
extract). Empty arrays and nulls describe this run, not all possible responses.
API-reported total was 3 credits. The refreshed Billing page independently showed
3/1,000 free-plan credits used, 997 remaining, pay-as-you-go off, auto-upgrade off,
requests stopping at the limit and no upcoming invoice. Evidence:
`reports/tavily-account-after-20261024T005808Z.json`. Per-extract zeros remain
observed values, not a claim of free future extraction.

## Probe report schema

Every invocation writes a new `reports/probe-tavily-<UTC timestamp>-<suffix>.json`;
existing reports are never overwritten. Primary fields:

```text
ProbeReport = {
  task: "T0.5", schema_version: 1, created_at: ISO UTC string,
  mode: "dry_run" | "execute", status: "not_executed" | "succeeded" | "failed",
  preflight: {credential_present: boolean, env_mode_600: boolean, ...},
  sdk: {distribution: string, version: string, search_signature: string,
        extract_signature: string, source: string},
  attempted_requests: integer, api_checks_passed: boolean, task_accepted: false,
  operations: [{id: string, method: "search" | "extract", arguments: object,
    status: "not_executed" | "succeeded" | "failed", reason: string | null,
    elapsed_seconds: number | null, credits: number | null,
    response_schema?: sanitized recursive field/type shape,
    results?: [{url?: string, title?: string, score?: number,
                content_characters?: integer, raw_content_characters?: integer}],
    failed_results?: sanitized array | null, usage?: sanitized object | null,
    credits_source?: "api_usage.credits" | "not_reported",
    api_response_time?: number | string | null, request_id?: string | null,
    error_type?: string, error?: redacted string}],
  credits_total_reported: number | null, exit_code: integer, ...
}
```

Elapsed time is measured around the SDK method. `attempted_requests` counts
method attempts, not independently observed HTTP packets. The report preserves
sanitized API metadata and field/type shapes; raw retrieved page text and request
headers are not saved. Keys are read only from the designated `.env` without
interpolation or changing environment variables. Reports contain only whether
a credential exists. Known credential values, bearer tokens, token-like strings,
and sensitive dictionary fields are redacted before persistence.

## Execution and acceptance boundary

Default preflight/dry-run, which sends no requests and exits 78:

```sh
source scripts/env.sh
uv run python scripts/probe_tavily.py
```

The completed run used the user-authorized free plan after verifying 0/1,000 used,
pay-as-you-go off, auto-upgrade off and a hard stop at the plan limit. Any later
run must stay within its separately authorized scope and current account limits:

```sh
uv run python scripts/probe_tavily.py --execute
```

`--execute` is required even if a key exists. A missing key or `.env` permissions
other than 600 blocks execution with exit 78. All four API operations must succeed
for exit 0; any actual probe failure exits 1. An exit 0 establishes only those
four probe checks. `task_accepted` stays false because the full T0.5 gate also
requires reviewing real results and adding two genuine feedback observations.
No probe run automatically writes FEEDBACK or promotes a plan task.

Offline checks, using synthetic credentials and an HTTP/socket blocker:

```sh
uv run pytest -q tests/test_tavily_probe.py
```

The tests cover the default execution guard, missing credentials, private-file
permissions, four-request parameters, partial/malformed failures, redaction,
unknown credits, and unique report files. Their mocks do not demonstrate service
availability, key validity, content quality, latency, or actual credit usage.


## Topic-specific research documentation

The bitsandbytes topic searches official Hugging Face documentation as well as
the existing allowed PyTorch/issue hosts, then extracts the pinned
[bitsandbytes 0.50.2 optimizer guide](https://huggingface.co/docs/bitsandbytes/v0.50.2/optimizers).
That public documentation page was checked on 2026-10-24. The topic previously
constructed PyTorch's generic optim.html, which could not document bitsandbytes.
Other topics still extract the observed PyTorch minor version's exact page.

The context and notes explicitly say that the installed bitsandbytes version,
dependency availability and numerical compatibility remain unverified. The
existing source version_match field is specifically an exact PyTorch URL
match; false for this separate library is not a measured incompatibility.
A documentation result never installs a package or grants a precision-policy
exception. Explicit caller-supplied search domains still take precedence.

The ordinary per-run four-call limit and 24-hour cache remain in force.
The standalone explore method remains for component callers/probes. Production
repair research now uses the native model tool loop below; a host topic hint
does not execute search or extraction on the model's behalf.


## Native Super tool loop (offline implementation verified)

A repair run constructs one ResearchToolLoop using its existing budgeted router
and ResearchSession. For each new API topic from an accepted diagnosis plan,
Super receives two function schemas with json_schema=None: tavily_search and
tavily_extract. The model chooses the query, allowed domains and extraction URLs.
The host adds the observed PyTorch version, fixes basic depth and the existing
SDK request settings, and executes only these two read-only methods.

The loop preserves assistant tool_calls and each corresponding tool_call_id
message. Entire batches are validated before any member executes: function
names, exact fields, JSON duplicate/nonfinite rejection, types, domains, public
official URLs, exact PyTorch documentation minor version and unique bounded IDs.
If a batch exceeds the remaining dispatch slots or contains an invalid member,
all members are explicitly not_executed and no follow-up model request is made.
A provider/tool failure stops research; any unexecuted members of that same
batch receive explicit not_executed responses. Cancellation retains the partial
transcript and never invents an interrupted tool's output.

Limits apply across all repair rounds, not separately per topic:

- At most 5 logical router calls and 4 tool dispatch slots, including cache hits.
- The shared ResearchSession independently persists at most 4 actual Tavily
  method attempts per run; cached results retain credits_used=0 without a call.
- The original model-client retry policy is unchanged. Actual HTTP attempts are
  separately recorded. The production budget callbacks halt on unknown charges;
  a 429/503 cannot dispatch a second request after the unknown charge is recorded.
- All model requests use the same run/daily ledger, existing profile capability
  checks and global deadline. This adds no live authorization or budget.

Tools require successful saved capability evidence in the reviewed Super
profile. Without it, research records tools_capability_unverified and sends no
model/tool request; there is no host exploration fallback. Optional missing
Tavily credentials/session or absent API topic remain explicit. Unknown model
billing or a model/budget failure propagates to the existing partial-run stop.
Unknown Tavily credits stop further research with the real null credit value.

Each tool message is at most 16,000 UTF-8 bytes and contains an explicitly
untrusted evidence object. Text excerpts start at an 8,000-byte limit and may
shrink to keep the serialized message within its cap. Source omissions and
truncation are marked. Retrieved text cannot add tools, change policy, run code,
read credentials or increase quotas. Final assistant prose is preserved as
model output but never creates Sources: citations come only from successful or
cached ResearchSession results. Search-only or issue-only extraction stays partial. Completion requires a
successful/cached search and extraction of the topic's official documentation
hint URL; a fluent final answer cannot establish that. Actual retrieval can
complete at the turn cap without an extra model summary.

rounds/NN/research-TOPIC.json preserves transcripts, validated dispatch records,
actual operation metadata, logical-turn/attempt counts and stop reason. Store
research rows remain the actual Tavily operations. Existing research.done events
also include newly recorded model identity/usage/time/cost from the LLM ledger,
separately from Tavily credits. Patch context and report Sources use this same
research evidence. Repeated topics reuse the saved result; research_enabled=False
and existing evaluation evidence restrictions are not overridden.

Guarded reproduction:
    .venv/bin/python reports/research-tool-loop-20261024/offline_tests.py -q tests/test_research_tool_loop.py tests/test_orchestrator.py tests/test_research.py

The runner installs independent DNS/INET and real-project-.env read guards
before importing tests. Tests use the real OpenAI SDK/router/budget callbacks
with MockTransport and fake Tavily method responses. They demonstrate protocol,
dispatch, cache, limits, failure and production wiring. They do not establish
live Super tool capability, a new Tavily extraction, GPU repair effectiveness,
or completed s1/s5 competition acceptance.
