# Offline Ultra input-token comparison

This is an offline comparison of saved Token Factory responses with the existing pinned NVIDIA tokenizer and chat template. No new provider request, GPU workload, credential read, runtime profile, allocation, or ledger change was made. Raw prompts remain private.

## Historical sample

From 242 saved Ultra call rows, 124 had a captured unredacted native JSON Schema request, an HTTP 200 response with the exact requested model identity, settled usage, and matching prompt-token fields. Within each requested-thinking group, select six evenly spaced order statistics of provider input length; selection did not depend on the observed discrepancy. The eligible set contained 19 requests with thinking requested off and 105 with it requested on.

The 12 selected requests span **31,877–73,183 provider prompt tokens**. The pinned local template count matches the saved provider prompt count exactly in **12/12 cases**: residual 0, provider/local ratio 1.0. Six requests had thinking requested off and six on. Ten are retained live pipeline calls; two are prior completed diagnostic probes. A diagnosis need not be valid for its input-token usage to be useful here.

The native schema subtree's serialized size spans **3,997–5,849 UTF-8 bytes** and its separate local count **1,295–2,205 tokens**, with 11 distinct schema hashes. Requests contain three or five messages, no tools, and only `response_format` among the locally unmodeled provider-only fields. Historical output caps were 8,192 or 16,384. These are observed input-count matches, not evidence of correctness of the model's diagnosis, zero hidden reasoning, or a provider billing maximum.

`statistics.json` includes each sample's counts, complete response-format-domain estimates, stored-payload/wire/template/schema/source-row hashes, and pinned assets. The exact private database row mapping is retained below ignored `.cache/final48h-input-calibration-20261029/`; no raw request or source text was copied into this public directory.

The capture point is local pre-transport. HTTP 200, response identity, and usage are paired in the same stored call; the capture's `delivery_confirmed=False` field is not rewritten into a standalone delivery guarantee. Captured payload hashes were recomputed before analysis. The database was opened with SQLite `mode=ro` and `query_only=ON`; no Store or BudgetLedger was constructed.

## What the comparison supports

For these historical native-schema requests, separately adding the native response-format schema was unnecessary to reproduce the observed provider input count: the local chat template already matched it. The router also places the requested schema in a system message, which is included in the template count.

This finite observation does **not** prove that all schemas, shorter inputs, future provider preprocessing, other models, tools, or other reasoning controls behave identically. The public field `provider_tokenizer_match_verified` remains false and no provider bound is established.

A separately versioned estimate may conservatively count both the template and the whole native response-format JSON domain:

`estimated_input = ceil((template_tokens + serialized_response_format_tokens) × multiplier) + additive_tokens`

`estimated_USD = (estimated_input × reviewed_input_price + requested_output_cap × reviewed_output_price) / 1,000,000`

The response-format count includes its type/name/schema wrapper; it is explicit additional allowance, even though it may duplicate text already counted in the system prompt. Preserve the existing positive multiplier margin and additive allowance; report this as an estimate. Exact model identity, known template switches, no tools, bounded request/schema size, explicit output cap, and rejection of unsupported fields remain necessary. This report does not select margin values, write a live profile, or enable such a policy.

## F1 request comparison

`f1-offline-counts.json` records a **v4 draft** preparation. It uses the actual LLMRouter and TokenFactoryClient with a synthetic capability fixture and MockTransport to construct the final body, including the router's schema system message and native response format. The dummy response is discarded; it is not provider usage.

The 18 Ultra requests in that draft span 10,564–65,184 pinned-template tokens: 418,093 full-evidence tokens and 98,714 traceback-arm tokens in total. All nine traceback requests are below the historical sample's empirical lower length bound. Their schema subtrees, 4,457–5,188 bytes, are within the sampled size range. Similar schema size does not remove the short-input extrapolation.

The F1 owner subsequently added the already-defined nine-category enum to the request schema. This changes both the schema and the router prefix, so v4 counts must not be treated as final. The frozen v5 counts are saved separately in `f1-v5-offline-counts.json`; original draft records are retained. In v5 the 18 Ultra requests span **10,605–65,225** pinned-template tokens: **418,462** full-evidence tokens plus **99,083** traceback tokens. All nine traceback requests remain below the empirical sample length floor. Native schema subtrees span **4,590–5,321 bytes**, within the historical size range. `f1-v5-domain-27.json` covers all 27 cells and explicitly leaves Super model-token counts unknown.

Super's nine full-evidence messages/schema match the full Ultra arm, but there is no pinned Super tokenizer in this review. Ultra counts must not be presented as Super model-token counts. A prepared-token approximation is not measured provider usage, and no projected dollar total is reported as F1 acceptance.

## Verification boundary

Both local analyses installed DNS/socket refusal before importing request/tokenizer tooling, set offline Hugging Face modes and disabled visible CUDA devices. Each recorded zero attempted DNS/socket connections. All 18 request-construction calls used MockTransport; actual new provider calls were zero.

Only the finite selected historical sample was tokenized for calibration; the full 124-call candidate pool was not asserted to match. No production code was changed for this analysis. Source scripts, private mapping, and logs remain on azuki. Public artifacts contain non-sensitive statistics and hashes only.

## Opt-in estimator implementation (offline preparation)

After the finite-sample review, an explicitly versioned `NativeSchemaEstimateAdmission` was added in `headroom/llm/admission.py` and included in the runtime profile type union. It requires `estimate_protocol="ultra_native_schema_v1"` plus the existing explicit `mode="local_estimate"`, risk acknowledgement, multiplier greater than one, positive additive allowance, reviewed cap fields, and new explicit minimum/maximum local token and maximum native-format byte limits. No actual profile was written or enabled.

The implemented formula above counts the **whole serialized response_format**, not just its schema subtree. Accepted requests are limited to the exact pinned Ultra model, plain system/user/assistant text messages, the currently generated native wrapper (`type=json_schema`, `name=headroom_response`, `schema`; no extra strict/description wrapper fields), explicit thinking False, and a reviewed output field capped at 2000. Tools, historical reasoning/tool fields, additional provider controls, unsupported fields, out-of-domain sizes, wrong models and missing verified prices are refused. The old LocalEstimateAdmission continues to reject native schema.

The minimum-token bound is explicit configuration, so admitting F1's short arm must be a deliberate reviewed extension below the sampled input floor, not an assertion that those shorter requests were measured. No numeric margin or live domain configuration is selected by this report. Model accounting still uses `local_estimate`; no BudgetLedger schema or global blocker was changed. Unknown actual costs and estimate overruns retain the existing stop behavior.

Focused verification: **90 passed in 30.84s** on the final files, comprising 34 new native-estimate tests and 56 existing admission/runtime compatibility tests in that run. SHA-256 checks before and after the tests confirmed all three implementation/test files were unchanged. The earlier 90-pass run in 30.78s is retained separately and is not added to this count. Outer DNS/socket guard attempts: **0**. These counts do not add to earlier request-policy tests. The tests use temporary fixture databases and MockTransport, not the production account or ledger. Ruff/format and the final scoped secret-scan receipts are retained with this report.

## Profile-carried policy through F3 and the CLI

The optional `LiveProfile.diagnosis_request_policy` field now accepts only `final48-diagnosis-only-2000-v1` or None; its default is None. A reviewed profile selecting the identifier produces a typed policy on the runtime's LLMRouter. The router does not rewrite ordinary `chat` calls.

The ordinary `diagnose_with_router` path resolves that carried policy before constructing its prompt or sending a request. An explicit caller policy cannot conflict with it, and an explicit old study protocol cannot be combined with it. Every existing permitted supplement retains the same selected 2000/False settings. The old profile default remains 16384/True, and the old 4000-token study remains unchanged. No real profile was created or modified.

The evaluation/CLI condition wrapper uses the same resolver when saving its initial messages and cap metadata, so those artifacts match the eventual wire request. An old full-Super study arm is explicitly refused when a carried Ultra policy is present; direct patcher/Nano calls are not changed. Dynamic mock/proxy attributes are not treated as selected policy: only an explicit instance attribute holding the validated type or None is read.

The final focused run passed **194 tests in 33.22s**, with all nine source/test SHA-256 values unchanged before and after the run and zero outer DNS/socket attempts. This supersedes the earlier stage-only regression for the final files; the 90-test stage receipt is retained as historical evidence and must not be added to 194.

The new 17 policy-routing tests include a real installed console invocation through the CLI bridge, run_fix, build_live_runtime, SDK MockTransport and fixture Store/ledger. That request used the synthetic profile's selected output field at 2000 with `enable_thinking=False`, and its saved prompt/cap records matched the serialized body. The child additionally blocks production paths, network, Docker and GPU commands. This is an offline CLI integration check, not live model or repair acceptance.

Current modified implementation scope: diagnosis_protocol.py, diagnose.py, llm/router.py, runtime.py, evaluation.py and llm/admission.py, plus the three focused request-policy/admission test modules. BudgetLedger and settlement behavior remain unchanged. Actual pool creation, authorization, live profile selection and execution remain outside this preparation.
