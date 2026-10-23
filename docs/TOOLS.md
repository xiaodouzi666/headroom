# Tavily tool contract and T0.5 probe

Status: the probe is prepared and tested with offline fixtures only. No Tavily API
call, live success, account balance, or actual credit charge has been observed by
this preparation work. T0.5 remains pending real probe acceptance and two factual
`docs/FEEDBACK.md` entries. Offline fixture reports are not live evidence.

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

## Documented API response shapes — live observation pending

The following field shapes are supported by the official
[Search reference](https://docs.tavily.com/documentation/api-reference/endpoint/search)
and [Extract reference](https://docs.tavily.com/documentation/api-reference/endpoint/extract),
read on 2026-10-23. Optional fields depend on request options and API behavior.
These are documentation-based contracts; the probe records the actual sanitized
field/type structure when an authorized live request eventually runs.

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

Only after Frank confirms available credits and the allowed spending boundary:

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
