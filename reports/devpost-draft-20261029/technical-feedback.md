# Saved Devpost technical feedback draft — 2026-10-29

These fields were saved through the user's authenticated Chrome session. This is a draft, not a submitted entry. The qualitative ratings of 6/10 (output quality), 7/10 (recommendation) and 7/10 (development experience) are suggested project assessments based on the recorded evidence, not measured benchmark scores. Personal and eligibility answers remain blank pending Frank.

## Which track are you submitting your project into?

Coding and agentic engineering

## Is your project new or existing prior to August 26, 2026?

New

## Provide a URL to your public code repository for judging and testing on either GitHub, GitLab or Bitbucket.

https://github.com/xiaodouzi666/headroom

## Provide a URL to a working demo, hosted application, or test build of your Project.

https://headroom.tail45186b.ts.net/

## Which model(s) did you use, and why did you choose that size/variant?

We used NVIDIA Nemotron 3 Ultra for diagnosis and repair planning, Super for structured source edits and the Tavily tool loop, and Nano for optional allocation-stack labelling, all through Nebius Token Factory's OpenAI-compatible API. Ultra handled 268,920 server-counted tokens in one authentic CUDA-memory evidence request and 500,029 in a separate retrieval probe. Its role requires reading a snapshot-derived evidence pack plus source and citing recorded stack IDs. Super handles the narrower exact-line-edit task; Nano offers inexpensive advisory labels whose coverage we validate. These are measured examples, not a claim that every context size or requested API control works equally well.

## How would you rate Nemotron's output quality for your use case? (1 = Poor, 10 = Excellent)

6/10 for this end-to-end repair use case. The strengths were long-input evidence handling and useful diagnosis hypotheses with allocation-stack citations. In the latest fixed nine-workload repair campaign, first saved categories matched 7/9 authored causes, 5/9 diagnoses also passed validation, and only 1/9 repairs met its memory target. Super's patch application improved with exact source-span edits, but malformed responses, unsupported evidence requests and ineffective changes remained. Nano's historical complete-label coverage was 4/8, with limited agreement with stack heuristics; we keep its labels advisory. The successful separate s3 browser demonstration reduced peak memory by 73.3787% with 20 exactly matching loss samples. We did not evaluate multilingual performance.

## Did you fine-tune, prompt-engineer, or use Nemotron out of the box? What was your approach?

We prompt-engineered the hosted models; we did not fine-tune them. The pipeline prepares a token-budgeted evidence pack from CUDA allocator history, includes source and policy constraints, and asks Ultra for structured diagnoses with valid stack references. Super emits exact line edits bound to the original source hash. Validation errors and hardware measurements are fed back to later keep-or-revert rounds. We tested native JSON schema, function calling and chat_template_kwargs, and explicitly disabled reasoning for the final constrained campaign. We did not establish a controlled quality improvement from that setting. Tavily provides version-specific documentation during the runtime research loop, with per-query caching.

## How did Nemotron's performance compare to other models you've used for similar tasks?

We did not run a controlled end-to-end benchmark against another provider's models on these workloads, so we cannot make a fair cross-provider ranking. Our measured within-Nemotron diagnosis comparison used the same nine saved workloads: full evidence with Ultra gave 6/9 first-category matches, traceback plus memory_summary with Ultra 2/9, and full evidence with Super 6/9. Fully valid diagnoses were 4/9, 2/9 and 4/9 respectively. This was a single fixed-order pass without repeats; two unconfirmed reference causes remain in the denominator. Development assistants helped build the software, but their outputs are not comparison results for the repair engine.

## Which Nebius platform capabilities were most valuable to your project and how?

The most valuable capability was hosted access to large NVIDIA open models through a familiar OpenAI-compatible API. It let a local RTX 3090 Ti focus on reproducing PyTorch workloads and verifying repairs while Token Factory served Ultra, Super and Nano. We did not provision a Nebius GPU VM, dedicated endpoint or autoscaling deployment; the public FastAPI/React application and hardware verifier run on our own server with Tailscale Funnel. Native JSON schemas and function calls simplified integration. The observed 268,920-token real-evidence request completed in 10.91 seconds and the separate 500,029-token retrieval probe in 17.98 seconds. Promotional access helped us test long requests within a small allowance, while per-call usage recording and conservative handling of missing cached-token usage were necessary.

## How likely are you to recommend running Nemotron on Nebius to other developers? (1 = Unlikely, 10 = Highly Likely)

7/10. We would recommend Token Factory to developers who need hosted access to NVIDIA open models, particularly large evidence inputs, and can validate structured outputs before acting on them. Its API integration was straightforward enough for our multi-model routing and Tavily tools. We would advise checking the exact model identifier, endpoint, supported controls and usage fields first. Some accepted controls did not yield the requested behavior, and missing cache-token usage complicated precise cost accounting. We would not recommend treating a valid JSON response or a plausible diagnosis as proof of a correct repair.

## How would you rate your experience running Nemotron inference on Nebius compared to previous cloud or local development environments? (1 = Poor, 10 = Excellent)

7/10 for our project's development experience. Hosted inference removed the need to deploy Ultra or Super on our local 24 GB GPU, leaving that GPU for workload reproduction and verification. The OpenAI-compatible client made it practical to route between three model sizes. Setup, promotional access and API-key configuration were separate steps; we did not measure total onboarding time or compare deployment time under controlled conditions. Long-input responses were useful, but unclear limits, occasional unsupported controls and missing usage details added integration work. This rating is a qualitative project assessment, not a controlled comparison with previous cloud or local environments.

## What additional features or improvements would have made the Nemotron on Nebius experience more effective for your project?

1. Publish capabilities and context/token-rate limits for each exact model and endpoint, with working JSON/tool examples. 2. Return cached-input and reasoning-token usage consistently, including partial responses, and explain unavailable values. 3. Provide a tested Super patch-output recipe using exact line arrays or source spans, with newline and truncation handling. 4. Document which reasoning controls each model honors and how reasoning consumes the completion allowance. 5. Distinguish input-length limits from token-rate limits with precise errors and retry guidance. Our nominal 900k probe returned HTTP 429 with Retry-After 255 and no server-counted input usage, so that result did not identify a context-limit rejection. Full measured feedback: https://github.com/xiaodouzi666/headroom/blob/main/docs/FEEDBACK.md

## What do you most hope to see from the Nemotron team next?

More reliable evidence-grounded coding workflows: schema-valid diagnoses that reference only supplied stack IDs, well-formed source edits at exact anchors, calibrated requests for additional evidence, and tool use that respects explicitly supplied invocation details. We would value small published evals spanning diagnosis, patch application and actual hardware outcomes, rather than JSON validity alone. For Nano, complete identifier coverage and clearer uncertainty would make stack labels more useful. For Super, robust editable-span output and explicit truncation handling would directly address our recorded failures.

## Did you use Tavily in your project?

Yes

## Which AI tools have you leveraged while working on this project?

OpenAI Codex assisted with engineering, research, testing, documentation, browser checks and recording raw feature footage. Claude contributed planning advice; final video editing is assigned to the user's local Opus workflow and is still pending. The application itself uses NVIDIA Nemotron 3 Ultra, Super and Nano through Nebius Token Factory, plus Tavily search/extract at runtime. Claims about repairs come from saved GPU runs and validation reports, not from the development assistants' assertions.
