# CPU prompt preflight

This is an offline diagnostic tool for complete Ultra chat requests. It provides an exact count
for a specific local NVIDIA tokenizer/template rendering and separate estimates for raw JSON
domains. It **does not provide a Nebius billable-token ceiling, authorize spending, enable a live
profile, or satisfy the current runtime budget gate**. PLAN, its thresholds, and verified/live
capability gates are unchanged.

Run from the azuki repository with the existing environment:

```sh
.venv/bin/python scripts/audit_prompt_tokens.py /absolute/path/request.json --output /absolute/path/new-audit.json
```

The input is a full request, including the exact Ultra model ID, messages, one explicit positive
`max_tokens` or `max_completion_tokens` cap, tools/schema/reasoning fields when present.
It accepts the supported SDK kwargs form (`extra_body`, optional `timeout`) and flattened wire
JSON. Duplicate SDK/wire fields and dual output caps are refused. The output path must be new.
No API keys, dotenv files, network request, model weights, CUDA inference, or model client are
needed by the tool. No dependency was added; it reuses tokenizers, transformers and Jinja2 already
in the environment.

## Pinned local assets

Repository: [NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4/tree/02462641f13d3af838b904f48195b9bb8a1e4ebc)

Revision: `02462641f13d3af838b904f48195b9bb8a1e4ebc`

| File | SHA-256 |
| --- | --- |
| tokenizer.json | 623c34567aebb18582765289fbe23d901c62704d6518d71866e0e58db892b5b7 |
| tokenizer_config.json | 10f93eabcb9b1602fbb991d6308e787ce1df28ee9cd7a1c6d1e8c3f338b957bc |
| chat_template.jinja | 82753bef5cedc4932c1ed509b5c9a12be680fd86d1adb65bc3f7398d11c8eebc |

Default directory:
`.cache/tokenizers/nemotron-3-ultra/02462641f13d3af838b904f48195b9bb8a1e4ebc/`.
These three files total about 17.3 MB. Every run checks their hardcoded hashes before loading.
It reads exactly those files; it does not use AutoTokenizer or remote code. The tokenizer is
constructed directly from verified JSON bytes, and the verified Jinja template is explicitly
supplied. This is necessary because installed transformers 4.46.3 does not automatically load
this separate template file. The official-config compatibility test compares token counts against
`PreTrainedTokenizerFast.from_pretrained(..., local_files_only=True)` with the same template.

Assets have already been downloaded on azuki. If the cache needs rebuilding, the following is an
**explicit setup step with public network access**; auditing never downloads automatically:

```python
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen
from headroom.llm.preflight import ASSET_HASHES, TOKENIZER_REPO, TOKENIZER_REVISION

directory = Path(".cache/tokenizers/nemotron-3-ultra") / TOKENIZER_REVISION
directory.mkdir(parents=True, exist_ok=True)
for name, expected in ASSET_HASHES.items():
    url = f"https://huggingface.co/{TOKENIZER_REPO}/resolve/{TOKENIZER_REVISION}/{name}"
    with urlopen(url, timeout=60) as response:
        data = response.read()
    if sha256(data).hexdigest() != expected:
        raise RuntimeError("Tokenizer asset integrity mismatch")
    (directory / name).write_bytes(data)
```

## What is counted

The report includes SHA-256 and compact UTF-8 JSON bytes for the normalized request and **every
supported top-level field**. It contains no raw messages, schema text, tool names, or prompt text.
JSON serialization preserves key order because tool-schema property order can affect the template.
Report source URLs, asset hashes and library versions make the rendering reproducible.

| Report field | Meaning |
| --- | --- |
| `local_template.tokens` | Exact token count of the pinned local rendered messages/tools, with explicit template switches, `add_generation_prompt=True`, `add_special_tokens=False`. |
| `request_fields.*.serialized_json_local_tokens_estimate` | Local encoding of each raw compact JSON domain; **not** provider prompt tokens. |
| `extra_schema` | Separate local estimate/bytes/hash of response-format JSON schema; it is not injected into the local chat template. |
| `provider_only_unmodeled_fields` | Supplied fields whose server-side prompt or generation handling has not been modeled. |
| `provider_billable_token_ceiling`, `provider_cost_upper_usd` | Always null. |
| `provider_tokenizer_match_verified`, `live_authorized` | Always false. |

The domain estimates are not additive. Adding raw JSON estimates to template counts would
double-count some content and still miss unknown provider preprocessing. A schema already in a
system message is part of the local exact rendering; a separately supplied `response_format`
schema is reported only as an additional raw-domain estimate.

Supported domains:

- Text-only system/user/assistant/tool messages, assistant `reasoning_content`, and function-call
  history with **object** arguments. The local template can truncate prior reasoning. Historical
  tool IDs are counted in raw domains and explicitly flagged as ignored by this local template.
- Function tools with name, description, parameter-schema object and optional strict flag, rendered
  by the pinned NVIDIA template. Nested schema data is preserved as JSON; this tool is not a
  JSON Schema validity checker and never resolves schema references.
- `chat_template_kwargs.enable_thinking`, `medium_effort`, `truncate_history_thinking` as booleans.
  Their local defaults are true, false, true. These are NVIDIA-template assumptions; provider
  support/default equivalence has not been verified.
- `response_format`, `reasoning_effort`, `reasoning_budget`, `max_thinking_tokens`,
  `tool_choice`, and `parallel_tool_calls` are recorded but **not injected** into the template;
  their provider-side consequences remain unknown.
- Explicit output cap, n=1, sampling controls, stop strings, stream/usage controls, seed and
  SDK timeout are recorded as request domains. Timeout is an SDK control, not a wire prompt field.

Unknown top-level/message/tool/template fields, multimodal content, developer role, JSON-string
historical tool arguments, duplicate JSON keys, combined reasoning selectors, ambiguous cap
fields, nonfinite values, and requests over the local 16 MiB audit input limit are refused.
The audit input limit is a tool memory safeguard, not a provider bound or a PLAN acceptance limit.

## Limits and live-budget readiness

The pinned NVIDIA tokenizer config declares 262144 tokens, while the observed Nebius catalogue
advertises 1048576 for Ultra. The NVFP4 model artifact is a public candidate tokenizer source; no
evidence establishes that Nebius uses this exact revision, template, serializer or defaults.
The audit flags exceeding the local config length but does not claim provider acceptance.

A small local count can help prepare a future provider-validation experiment. It cannot by itself
replace `BillingBound.prompt_token_ceiling` or verify a `max_prompt_utf8_bytes` billing domain.
A provider contract, verified provider-side hard input limit, or an explicitly reviewed future
change to the budget policy is still needed before replacing the conservative catalogue-context
reservation. Increasing account balance alone does not resolve the original $0.35 diagnosis /
$0.60 run guard mismatch. This tool makes no changes to those guards.

## Saved CPU verification

Evidence: `reports/prompt-preflight-20261024T103732Z/`.

Four existing evidence files were hash-checked against `reports/t1.2-acceptance.json`. The current
diagnosis builder and real router/client prepared their complete request payload; a before-attempt
capture stopped execution **before SDK invocation**, backed by an offline MockTransport tripwire
and independent process-wide DNS/socket refusal. No model request or new GPU run occurred.
The original cl100k counts were recomputed from the existing local cache.

| Scenario | Original evidence-only cl100k estimate | Complete pinned local template | Complete JSON local estimate |
| --- | ---: | ---: | ---: |
| s1 | 20907 | 29221 | 30424 |
| s2 | 29970 | 40430 | 41903 |
| s4 | 29396 | 39411 | 40883 |
| s5 | 24550 | 33831 | 35386 |

The current request uses text fallback and already includes the response schema in a system
message. Separate **hypothetical** response-format schema audits each record a 639-token raw
schema estimate; these do not establish provider JSON-schema support and are not added to the
table's template counts.

Tests cover exact local rendering, independent official-config equivalence, full request/schema
accounting, reasoning history, SDK/wire equivalence, unmodeled provider controls, unknown/malformed
inputs, asset tampering before tokenizer loading, credential/network refusal, redacted reports,
and non-overwriting CLI output. Asset integration tests explicitly skip when pinned assets are
absent; all ran on azuki. See the receipt for exact test totals and source hashes.

The retained setup/audit logs include the initial separate-template compatibility finding, an
audit-driver assertion corrected from `CostLedger.records` to `entries`, and a blocked cl100k
cache miss. The latter was resolved by pointing at the already existing `.cache/tiktoken`;
the network guard stayed enabled. None changed project behavior or acceptance claims.

## Read-only admission audit (2026-10-24)

The 1.060576 USD value is a conservative implementation reservation for 1,048,576
input tokens plus 4,000 output tokens at the observed 1/3 USD-per-million prices.
It is **not** a minimum fee charged by Nebius and the original PLAN does not require
short requests to reserve the entire model context. PLAN acceptance remains based
on actual usage-priced cost, including the original diagnosis/run thresholds.

The public OpenAPI reviewed at version `20261022-1d60f32ca` had no documented
free tokenize/count endpoint or numeric Chat input cap. Responses truncation is
`auto` or `disabled`; it does not establish a smaller numeric billing ceiling.
Completions accepts token-ID arrays in the public schema, but Ultra compatibility
and additional billable special tokens are not verified, so it cannot yet replace
the Chat adapter or establish a hard upper bound.

Local template counts, provider-contract bounds, and actual usage costs must stay
separate. An explicitly configured estimate-based admission policy can use the
complete final request, pinned tokenizer/template, a margin and output cap; it
can stop subsequent calls on unknown or excessive charges. Such a prediction
cannot guarantee that an individual call will never exceed its estimate. No
policy/profile has been enabled by this audit, and current authorization remains
limited to the previously approved 0.10 USD trial connectivity scope.

Primary sources: [Ultra cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md),
[OpenAPI](https://api.tokenfactory.nebius.com/openapi.json),
[Chat](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion),
[Responses](https://docs.tokenfactory.nebius.com/api-reference/inference/create-a-response),
[Completions](https://docs.tokenfactory.nebius.com/api-reference/inference/create-completion),
[billing](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new).
Account balance is not treated as a provider hard stop; the billing documentation
describes negative balances and automatic payment. No API inference, credential
read, payment or account mutation was performed for this audit.
