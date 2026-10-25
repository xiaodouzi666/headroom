# Reasoning enablement review — protocol v2 repair iteration 1

2026-10-25. This review covers an implementation change and offline validation. It is not a new capability probe, GPU run, numerical acceptance, or model success. Historical v7 and protocol-v2 baseline results remain unchanged; the primary gate remains 6 of 9.

## Observed requests and prior capability evidence

The completed protocol-v2 baseline campaign is `runs/evaluation/live/20261025T083415856928Z-b5f2e084/campaign.json`. A read-only inspection of its 27 captured HTTP request records (14 Ultra diagnosis, 4 Super patch, 9 Nano annotation) found `chat_template_kwargs.enable_thinking=false` in every request. Ultra used an 8192 completion cap and Super 4000. All 18 Ultra/Super usages reported zero reasoning tokens. Nano omitted that usage detail; absence is not proof of zero reasoning. Only the s3 row met its target in that campaign. These observations establish a disabled reasoning path, not proof that it caused every failed repair.

Existing, retained `reports/live-campaign-20261025/capability-review.json` already selects `chat_template_kwargs` and `json_schema` for Ultra and Super:

| Existing probe | Completion tokens (including reasoning) | Reasoning tokens | What it establishes |
| --- | ---: | ---: | --- |
| Ultra template on, remaining-capabilities probes/4/attempts/0 | 126 | 121 | HTTP 200, matching model identity, stop; on flag worked on this fixture |
| Ultra template off, probes/5/attempts/0 | 4 | 0 | Off flag suppressed reasoning on this fixture |
| Ultra schema, probes/1/attempts/0 | 105 | 93 | Final two-key JSON matched the schema with reasoning present |
| Super template on, remaining-capabilities probes/2/attempts/0 | 92 | 48 | HTTP 200, matching model identity, stop; on flag worked on this fixture |
| Super template off, probes/3/attempts/0 | 200 | 0 | Off flag suppressed reasoning on this fixture |
| Super schema, `reports/model-checkpoint-20261025/super-schema/report.json`, probes/0/attempts/0 | 76 | 61 | Final two-key JSON matched the schema with reasoning present |

Remaining-capabilities reports are under `reports/live-campaign-20261025/{ultra,super}-remaining-capabilities/report.json`. The listed remaining-capabilities requests used a 1024-token output cap. The older Super schema report did not retain a request-cap field; this review does not infer one. Short probes do not establish adequacy of 4000 tokens for a long source-edit task. The prior prefix off probes still emitted reasoning; unsupported token-budget experiments did not establish enforceable reasoning budgets. No new paid probe was needed or run for this change.

## Primary sources and their limits

- [Nebius create-chat-completion API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion.md) defines `max_completion_tokens` to include visible output and reasoning tokens, and exposes reasoning usage details. Its published schema supports `json_schema`. The fetched API schema does **not** document `chat_template_kwargs`; the provider-specific evidence for that extension comes from the retained actual Nebius probes above.
- [Nebius structured-output guide](https://docs.tokenfactory.nebius.com/ai-models-inference/json.md) distinguishes schema-following output from an arbitrary JSON object and recommends also supplying the schema in the prompt. It does not require reasoning to be disabled.
- [NVIDIA Super model documentation](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-super-120b-a12b) describes configurable reasoning through the chat-template `enable_thinking` flag. [NVIDIA Ultra documentation](https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b) also describes this flag.
- The NVIDIA NIM inference endpoints are a different provider interface. Their effort levels, `reasoning_budget`, Ultra `medium_effort`, or backend-specific flags must not be assumed to work identically on Nebius. This change adds none of them.
- [Anthropic's agent design guidance](https://www.anthropic.com/research/building-effective-agents) and [Google's ReAct research description](https://research.google/blog/react-synergizing-reasoning-and-acting-in-language-models/) support an action–observation–evaluation loop: a proposed repair is a hypothesis until execution supplies evidence. They do not establish that any Headroom candidate satisfies memory, numerical, or timing gates.

The Nebius Markdown pages were freshly fetched from their public official URLs during this review after browser extraction failed; no authenticated inference endpoint was used for documentation retrieval.

## Implemented scope and retained constraints

`headroom/patch.py` now requests Super reasoning and passes the bounded `numerical_reference_context` host metadata through the existing solver-context builder. The diagnosis owner similarly enabled Ultra reasoning. That capability metadata describes available validation mechanisms and their limits, not a prepared benchmark answer or an assertion that a candidate passed.

The canonical PLAN T1.5 (line 259 at review) requires each Super completion to be at most 4000 tokens. Therefore both the PatchEngine default and hard maximum remain **4000**, despite the reviewed provider profile permitting requests up to 8192. Ultra remains **8192**. The patch prompt's 4000-token cap must be understood as reasoning **plus** visible JSON. Enabling reasoning may leave fewer visible tokens or increase `finish_reason=length`; the router continues to reject length-truncated structured responses. The private patch response artifact separately persists the available `finish_reason` and usage through `headroom/patch_evidence.py:save_patch_response` (line 178 at this review). CallRecord/Store do not persist that field, and it is not a generic durable diagnosis field. Therefore a Store-only retrospective audit must report finish/length as unknown unless separate persisted evidence is explicitly linked; reaching the completion cap alone does not establish a length finish or explain a parse failure. Hidden reasoning text is not copied into response artifacts.

PLAN T1.4's required total projected savings also remains unchanged. This review does not authorize accepting a partial-saving plan that fails that gate. Evidence requests should concern dependencies of the current executable plan; irrelevant future fallback ideas should not be promoted into blockers. Genuine unknowns needed by a selected change remain unknown. A source coverage record may disprove a claim that a line was omitted, but does not prove the model understood it or that a repair will work.

## Billing bound proof

The runtime continues to reserve the full verified provider prompt domain, rather than an estimated size of the visible request:

`upper = (prompt_token_ceiling × max(input_price, cached_input_price) + completion_cap × output_price) / 1,000,000`.

| Request role | Prompt ceiling | Completion cap, including reasoning | Unchanged full reservation |
| --- | ---: | ---: | ---: |
| Ultra diagnosis | 1,048,576 | 8192 | $1.073152 |
| Super patch | 262,144 | 4000 | $0.0822432 |

The existing shared all-time/daily pool remains $9.99964904; the per-run settled-cost stop remains $0.60. A full reservation may exceed that per-run stop only under the already-reviewed actual-usage mode, and must still fit the shared remaining pool. No pool, cap, price, profile, retry count, or reasoning-budget parameter was changed. `completion_tokens` is billed in full; `reasoning_tokens` is a subset, not an additional or free allowance.

New temporary-DB/MockTransport tests verify both roles: the full reservation exists before transport; a 500-token completion including 490 reasoning tokens bills all 500 tokens; final JSON validates; hidden reasoning text is absent from persisted call records; an underfunded shared pool causes zero transport calls and no pending record. Existing patch response tests retain length-truncation and usage evidence.

## Offline validation and retained failures

- Initial combined focused run: **397 passed, 12 failed**. Five failures were in new test fixtures (an intentionally non-official URL was correctly rejected by the endpoint allowlist; the context assertion used the wrong existing envelope key). These fixtures were corrected without production relaxation.
- Seven existing `test_actual_usage_budget.py` cases failed with `checked` unexpectedly a string. Running the two affected small-run cases alone passed; the complete file alone passed **39 tests**.
- Investigation identified test import-order contamination: `test_llm_request_audit.py` patched `diagnose_with_router` before `condition_services` first imported `orchestrator`, so the Services dataclass captured the mock as its default. Matching patterns existed in `test_evaluation.py` and `test_evidence.py`. The tests now load the canonical orchestrator before patching. No production exception swallowing or budget assertion change was made.
- After fixture correction, the patch/runtime/client/cost/request-audit/billing group excluding the separately investigated actual-usage file passed **370 tests**. Log: `.cache/reasoning-focused.log`. Standalone actual-usage log: `.cache/reasoning-actual-usage-alone.log`.
- The targeted ordered regression and final lint status are recorded below after completion. A fresh full suite and new formal nine-case campaign remain the parent's next gates; these focused results are not a model score.

### Final focused receipt

After the import-order correction, the exact original 14-file focused order passed **409 tests in 5.68 seconds**. Log: `.cache/reasoning-focused-final.log`. The narrower ordered pair `test_llm_request_audit.py` then `test_actual_usage_budget.py` passed **48 tests in 2.71 seconds**; log: `.cache/reasoning-ordered-regression.log`. The first lint run on the isolation change found two unnecessary F401 suppressions; removing those comment suppressions resolved lint without changing execution. Final Ruff check and format-check passed for all eight touched implementation/test files. The initial 397/12 result above remains part of this record.

Production/test writes by this reviewer are now frozen. The unchanged original profile SHA is `a15ee9a357b4e0c41aeb46219081066c4d5a2299a777f8f87127dde60118026c`. No live inference, GPU job, profile edit, live budget DB edit, or model-cap increase was performed by this change or its tests.
