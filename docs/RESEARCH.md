# Runtime Tavily research

T2.2 runtime support is implemented and tested offline. T0.5's accepted probe
establishes the SDK/API shapes, but is not evidence that this runtime module has
completed a model repair or its s1/s5 integration acceptance. Only an explicitly
authorized caller may enable live requests; this module never reads `.env` or
obtains credentials itself.

## API

```python
from headroom.research.tavily_tool import ResearchSession

research = ResearchSession.for_run(
    run_id,
    torch_version="2.5.1+cu124",
    store=store,
    cache_dir=".cache/tavily",
    api_key=injected_key,
    live=False,
)
result = research.explore("checkpoint")
# result: status, topic, sources, context, operations, api_calls, credits_used, notes
research.close()
```

Live defaults to false even with an injected key. No SDK client is constructed
unless live is true, a nonempty key is present, a valid cache entry is unavailable,
and the run still has a call slot. An offline/cache-only result is explicitly
labelled; it never counts as a successful newly executed API call.

`explore(topic, search_depth="basic", max_results=3, include_domains=None)` supports
checkpoint, allocator, adamw, compile, fsdp, and bitsandbytes, plus the API/flag
aliases in `TOPICS`/`ALIASES`. Each exploration performs at most one search and
one extract. Search names the complete installed torch version. Extraction
requests the fixed major.minor PyTorch documentation URL for the topic plus one
PyTorch GitHub issue returned by search, if available. No issue URL is invented.
For bitsandbytes the fixed PyTorch optimizer documentation supplies the host
framework context; it is not a claim that PyTorch documents the third-party
optimizer's current API. Package-specific documentation may be obtained with
`search(..., include_domains=["huggingface.co", ...])` and `extract(...)` below.

Search can return stable/main documentation despite the version keyword. Each
source includes `version_match`; issue relevance to the current version always
remains unverified, and an explicit note accompanies historical issue reports.
`status="succeeded"` means nonempty accepted search and complete requested-URL
extraction, not correct applicability, complete research, or verified advice.

Lower-level `search(query, search_depth="basic", max_results=3,
include_domains=None)` and `extract(urls, extract_depth="basic")` share the same
run allowance. Search allows one through five results and basic/advanced depth;
extract accepts one or two allowed URLs per method call. Domains and all request
parameters participate in the cache key. No retry or fallback query is performed
implicitly. An exception, malformed response or failed/partial extract consumes
its dispatched method slot and is recorded as failed; failure results are not
cached. Missing credit usage stays null.

## Limits and cache

Each run has at most four dispatched SDK method attempts, including failures.
`max_calls` can lower this limit but cannot increase it. A private on-disk counter
is reserved before dispatch, under a thread lock plus Linux file lock. Separate
sessions and processes for the same run share that quota. With a Store, quota
files are anchored beside that database, independently of the configurable
content-cache directory; without a Store callers must reuse the same cache
root. Store research metadata also establishes a lower bound after restart.
An interrupted dispatch keeps its reserved slot because it may already have
been charged. `session.api_calls` reports consumed slots, which can conservatively
include such an unresolved attempt; per-operation `api_calls` records zero or
one SDK method attempt. These are not packet-level network measurements.

Successful responses are cached for 24 hours. Cache keys include schema version,
complete torch version, method, query/URLs, depths, domain restrictions, result
limit and all other explicit request options. Future timestamps, corrupt data,
unsafe URL data and expired records are not reused. Corrupt quota data fails
closed. Cache hits have `api_calls=0`, `credits_used=0`,
`credits_source="cache_no_call"`, and `api_usage=null`; the original request id is
separately identified as `origin_request_id`. This is zero incremental use and
does not fabricate a new provider usage response.

Body cache defaults to the repository's already gitignored `.cache/tavily/` on
the server. Files are private mode 0600 and written atomically. Never commit
cache bodies or place them in a public report. Temporary test caches remain
under pytest temporary directories. A custom runtime cache location must also
remain server-local and excluded from public source control.

## Evidence, persistence and safety

`context` contains JSON-quoted retrieved text with an explicit UNTRUSTED RESEARCH
DATA instruction boundary. The caller must inject it as third-party evidence,
not system/developer instructions. It may be useful context for Diagnose/Patch;
it does not authorize actions described by a web page.

`sources` and `operations` contain URL/title/length, source kind and version-match
metadata, plus operation state, measured duration, reported credits and request
identity. `store.research` receives only these stable records, never page bodies,
request headers, query text or raw exception messages. `research.called` denotes
dispatch and `research.done` denotes the recorded result; cache/offline outcomes
have no called event. Known key text and common token forms are redacted before
persistence, including cached body text. Metadata is suitable for report Sources;
its titles remain untrusted text and the report renderer escapes them.

The installed tavily-python 0.8.5 SDK is used with fixed
`https://api.tavily.com/search` and `/extract`, `trust_env=False`, no redirects,
no automatic retry and no ambient project/org routing. SDK requests use timeout
30 seconds; Requests timeouts cover connect/read operations and are not a total
wall-clock deadline. There is no public endpoint override. HTTP 200 alone does
not establish success: nonempty permitted result text and all extract URLs are
required. Absent or invalid usage is unknown, never zero.

Only HTTPS on explicit official documentation hosts and exact
`github.com/pytorch/pytorch/issues/<number>` paths is accepted. Private/LAN/IP
origins, alternate ports, userinfo, query credentials, encoded traversal and
arbitrary redirector paths are rejected before SDK dispatch. Versioned PyTorch
URLs are mandatory for extraction. The local client does not resolve or fetch
source URLs; Tavily performs extraction. Source redirects performed inside
Tavily are not independently observed by this module.

## Offline verification

```bash
uv run --offline pytest -q tests/test_research.py
uv run --offline ruff check headroom/research/tavily_tool.py tests/test_research.py
```

Tests install request, DNS and socket guards before all fake-client cases. They
cover explicit live authorization, zero ambient-key fallback, exact versioned
URLs, untrusted-content framing, persistent/concurrent method limits, shared
Store quotas across different cache directories, parameter-sensitive TTL caches,
unknown usage, partial extraction failure, private/credential URL rejection,
private body caches, metadata-only database records, and the official transport
configuration. They send no Tavily or model requests and perform no GPU work.
