# Token Factory client and role router

Status: **offline implementation and mock verification only**. No live request was
made while implementing this layer. T1.3 remains unaccepted until real Super schema
JSON and a real Ultra 200k-token request succeed, with latency/cost evidence in
`docs/FEEDBACK.md`. T0.4 model availability, prices, capability parameters and
maximum input length also remain unverified. This document does not waive those
gates or the original T1.2 requirements.

## Entry points

```python
from headroom.config import RuntimeConfig
from headroom.llm.client import TokenFactoryClient
from headroom.llm.router import LLMRouter

# Construction is safe without credentials and does not send anything.
client = TokenFactoryClient(config=RuntimeConfig())
router = LLMRouter(client)
# router.chat(...) raises LiveRequestsDisabled until explicitly enabled or mocked.
```

`LLMRouter(client).chat(role, messages, json_schema=None, tools=None, *,
reasoning=None, token_budget=None, max_tokens=4000, temperature=None)` accepts a
nonempty message list. `json_schema` is a JSON Schema dictionary or Pydantic
`BaseModel` class. The router adds the schema instruction, parses the reply and
validates locally. Pydantic validation is strict. Parsed output is a dictionary,
list or other JSON value, never a Pydantic instance.

The return `ChatResult` exposes:

- `role`, `model` (requested), `response_model` (provider-reported), `text`, `parsed`.
- `tool_calls` (tuple of dictionaries; the client never executes tools).
- `usage`: `Usage` or `None`; prompt/completion/total counts plus optional cached
  and reasoning token details.
- `cost`: `Cost(usd: Decimal | None, status: known | unknown, reason)` for the
  successful attempt; use `client.ledger` for **all attempts**, including retries.
- `attempts`, `elapsed_seconds`, `finish_reason`.

Role names map as follows; unknown roles fail before network activity:

| Model family | Accepted roles | Default timeout |
|---|---|---:|
| Ultra | ultra, diagnose, diagnostician, planner | 600 seconds |
| Super | super, patch, patcher, verifier | 120 seconds |
| Nano | nano, annotate, annotator, summarize, summarizer | 120 seconds |

The candidate model IDs in `headroom/config.py` preserve C.1 verbatim. They are not
an assertion that these models exist on either endpoint. Lightning is a candidate
constant, not an automatic fallback. `ULTRA_MAX_INPUT_TOKENS`,
`EVIDENCE_TOKEN_BUDGET`, `REASONING_METHOD`, and `JSON_METHOD` remain `None` until
supported by T0.4 evidence. The current offline evidence builder's independent
CLI budget is not a verified provider context limit.

## Explicit runtime configuration

`RuntimeConfig(base_url=..., live_enabled=False, models=...)` only accepts these
HTTPS URLs (an omitted trailing slash is normalized):

- `https://api.tokenfactory.us-central1.nebius.com/v1/`
- `https://api.tokenfactory.nebius.com/v1/`

The `models` mapping contains `ultra`, `super`, `nano`, each a `ModelSpec` with
`model_id`, `timeout_seconds`, `capabilities`, `pricing`, `model_verified` and
`evidence`. It is copied and made read-only. Verified flags and evidence references
must only be populated from actual reviewed probe results; the constructors
validate their shape, not the truth of a referenced document.

`VerifiedCapabilities` accepts these methods:

| Setting | Values |
|---|---|
| json_method | text (default), json_object, json_schema |
| reasoning_method | None, chat_template_kwargs, system_prefix, reasoning_effort |
| token_budget_method | None, reasoning_budget, max_thinking_tokens |
| tools | False (default), True |

Nondefault methods require an `evidence` reference. `reasoning_effort` additionally
requires the observed `reasoning_on` and `reasoning_off` values. No method is
selected merely because it appeared in documentation or received HTTP 200.
Requesting reasoning, a token budget or tools without configured evidence raises
`CapabilityNotVerified` before a request is sent. The text JSON fallback is local
parsing, not a claim of provider structured-output support.

Live use requires both an explicitly supplied API key and
`RuntimeConfig(live_enabled=True)`. The caller must separately satisfy the user's
credit/spending authorization and live-probe gates. This layer does not read
`.env` or infer permission from a key's presence. It does not implement a dollar
budget guard; orchestration must apply that guard before live use. No API call is
performed on module import, construction or close.

## Requests, retries and credential handling

The installed OpenAI 3.37 SDK is used with its `max_retries=0`. The Headroom loop
retries only HTTP 429 and 5xx, at 1, 2, 4, 8, 16 seconds: at most five retries,
six total attempts. Other HTTP statuses, connection errors and timeouts do not
retry. An uncertain timed-out request is not assumed unbilled. SDK response-decoding
failures also record an unknown charge and a safe error, without automatic retry.

The owned HTTP client has `trust_env=False`, `follow_redirects=False`, an exact
POST `/v1/chat/completions` destination guard, and a request-header whitelist.
Ambient proxy settings, SDK custom headers, cookies and unrelated credentials
are not forwarded. Only the configured key becomes Authorization. Cross-origin
redirects are errors. Host and Content-Length are regenerated for normal HTTP
framing. HTTPS verification stays enabled. The only injectable transport is an
`httpx.MockTransport` for offline tests. This is a trusted testing hook, not an
alternate production endpoint.

Errors expose safe status/category summaries without SDK response bodies or
chained credential-bearing errors. No prompts, responses, headers or keys are
logged by this layer. Usage serialization suppresses warnings that could expose
malformed provider fields. Do not log the SDK's internal object state. Always
close the client, preferably through its context manager.

## Accounting and response validation

`Pricing` uses decimal strings/Decimal, never binary float prices. Verified prices
require a `source` reference. No rates from the plan are installed as actual
prices. Cost is input tokens × input rate plus completion tokens × output rate,
divided by one million. Reasoning counts are already included in completion
counts and are not added again. Cached-input discounts require both their rate
and token count. Missing/invalid usage, unverified/missing rates, unknown cache
pricing, or a response model different from the priced model yields `unknown`.
A missing or mismatched response model is also rejected after the ledger entry is
recorded; its text never enters downstream diagnosis or patching. No model alias
is assumed verified. A zero price is only meaningful when explicitly verified.

`client.ledger.entries` has one `CallRecord` per attempted request, with status,
latency, usage and cost. `known_subtotal_usd` sums known charges only;
`unknown_attempts` counts unresolved entries; `total_usd` is `None` if any attempt
is unknown. A successful retry does not erase the unknown billing of a failed
attempt. The ledger is in-memory and must be persisted by orchestration; it is
not a provider billing reconciliation or a spending cap.

The JSON parser supports a plain response, a JSON fence, or one unambiguous
embedded JSON value. It rejects duplicate keys, NaN/Infinity (including exponent overflow such as
`1e309` at any nesting depth), multiple objects,
malformed JSON and schema violations. It never uses eval, invents keys, executes
tools or makes automatic paid repair calls. Truncated/filtered structured replies
are rejected even if the partial text parses. Validation occurs after recording
response usage, so invalid output still has an accounting entry. Schemas can
reference only their local document; external reference fetching is prohibited.

## Offline verification

```sh
uv run pytest -q tests/test_llm_client.py tests/test_llm_cost.py tests/test_llm_router.py
uv run ruff check headroom/config.py headroom/llm tests/test_llm_client.py tests/test_llm_cost.py tests/test_llm_router.py
```

Tests use HTTP MockTransport through the real SDK and no GPU/network requests.
They cover routing/timeouts, retry exhaustion, success after retries, unknown
costs, Decimal arithmetic/cache/reasoning accounting, rejected endpoints,
redirect/header/proxy isolation, debug-log secrecy, capability injection, tools,
JSON fences, schema validation and local references. Mock evidence proves the
client's behavior; it does not prove any model capability or T1.3 live acceptance.
