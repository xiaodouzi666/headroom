# Submission readiness audit — 2026-10-24

**Current conclusion: not ready to claim Stage One passage or submit a first-prize-ready project.** The engineering foundation has real GPU baseline and local-interface evidence. Authenticated Nemotron repair runs, the public deployment/video, and the complete evaluation/ablation package remain separate uncompleted gates.

This audit uses the requirements preserved in [PLAN §G](../docs/PLAN.md), and inspects the current source, README, Devpost draft, saved acceptance artifacts, and new non-paid CLI/API smokes. It does not re-register, accept terms, pay for anything, publish, or submit. The official event page is [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/); this is an implementation-readiness audit, not a new verification of changing contest terms.

## Stage One: pass/fail requirements

| Requirement recorded in PLAN §G | Current evidence | Readiness |
|---|---|---|
| Runtime uses Nebius Token Factory inference, or deployment on Nebius AI Cloud | Client/router/budget and partial-report paths are implemented. The actual local health response says Token Factory configured=false/reachable=null. Missing-profile fix exits 78 before baseline/model work. No accepted authenticated model-run evidence was supplied for this audit. | **Not demonstrated.** A provider name, SDK mock, model ID, or account-registration step does not satisfy the runtime requirement. |
| Uses at least one NVIDIA open-source model through the required route | Ultra/Super/Nano roles, capability probes and structured contracts exist. Live model identity/capability, real usage and long-input acceptance remain pending. | **Not demonstrated.** Preserve actual requested/returned model identity and provider usage from an authorized runtime run. |
| Coding and Agentic Engineering: agents that write, run and test code | Local Lab execution, evidence reconstruction, patch application, verification, search decisions, storage and reporting have component/fixture evidence. Actual model-authored repair remains pending. | **Implemented architecture; end-to-end runtime demonstration pending.** Show one actual diagnosis → source patch → test/verification loop. |

A live Tavily component does not substitute for the Nebius/NVIDIA hard gates. The saved Tavily probe and research-component reports establish real search/extract/cache behavior, but not an overall award or a completed model-driven repair.

## Four equal-weight judging dimensions

PLAN §G records four 1–5 dimensions, with ties compared in the listed order. **No numerical judge scores are assigned here.** The “+1 opportunity” column means a small, evidence-producing improvement to prioritize, not a guaranteed point or prediction of winning.

| Dimension | Demonstrated now | Evidence gap | Smallest defensible “+1” opportunity |
|---|---|---|---|
| Technological Implementation | Real allocator capture on 12 pinned scenarios; isolated execution/cleanup; bounded evidence; policy checks; durable unknown-cost accounting; real Tavily research component. | No accepted authenticated Ultra/Super/Nano behavior or complete successful repair. Original s2 evidence threshold remains 39.8715% against 40%; it is not rounded up. | After account/credit/cap authorization, run one already-reproduced s1 case through the actual provider and preserve requested/returned model ID, evidence references, patch, verification, timings and charge. Present the measured result even if it fails; do not invent the target win. |
| Design | Four implemented English pages, real examples, SSE, explicit unknowns, safe diffs, partial reports and five honestly labeled baseline replays; passing frontend contract tests and production build. Actual localhost GET endpoints and replay stream end work. Saved browser evidence covers Home/Run/Results/About and mobile width 390 without horizontal overflow. | Browser evidence is saved in reports/browser-validation-20261024.json; that record does not establish a Lighthouse score. Baseline replays are not successful repairs; T3.3's required two-round s2 replay is missing. | Preserve the completed mobile/example-to-needs-human browser evidence, complete performance and remaining reconnect/error/download checks, then curate one genuine repair replay when available. |
| Potential Impact | The workload problem is concrete; 12 actual baselines span authored fixtures and random-initialized nanoGPT/Trainer/ViT/T5 examples. | No verified memory savings, repair success rate, user time savings, or real downstream quality result. A baseline peak is not a saved-memory result. | Add one measured before/after case with memory, step-time, numerical-policy tradeoff and a clear intended user. Explain the engineering decision the report enables; keep the rest of the benchmark pending until measured. |
| Quality of the Idea | Evidence-referenced diagnosis, bounded keep/revert search, explicit failure/unknown states and auditable tradeoffs form a coherent workflow beyond a static memory plot. | The claimed benefit of large-context evidence over traceback-only input is not yet measured. The techniques themselves are established prior work. | Add a concise comparison with manual allocator inspection and show one real trace-reference → patch → decision chain. Complete the unchanged eight-scenario × three-condition ablation before claiming that full evidence outperforms traceback-only input; an illustrative pair is not the full gate. |

The first-prize path therefore starts with Stage One runtime evidence and a compelling verified end-to-end demonstration. Additional interface polish cannot compensate for absent required-provider evidence.

## Submission artifacts

| Artifact | Observed state | Required before submission |
|---|---|---|
| Runnable project | Source and local CLI/API work. The missing-profile path produces a reviewable partial result. | Demonstrate the actual intended repair runtime, with the original acceptance failures visible. |
| Public repository and license | README names a GitHub repository; the local root LICENSE is Apache-2.0. Current working tree contains substantial uncommitted implementation. | Independently verify the intended final code is pushed and publicly readable, license visibility, and a clean-clone quickstart. A local working tree or existing repository URL does not prove published delivery. |
| Public demo URL | README explicitly says pending approved hostname/deployment. Local service at 127.0.0.1:8765 responds. | Public HTTPS/mobile-network verification and required availability during the judging window. Loopback responses do not satisfy this. |
| Public YouTube video ≤3 minutes | README/Devpost draft explicitly mark pending. | Record actual operation, name Nebius Token Factory/NVIDIA Nemotron clearly, keep within the limit, and verify public playback. No fake repair sequence or placeholder result numbers. |
| English project description | README and `docs/DEVPOST.md` are drafts and contain explicit limitations. | Fill the actual submission fields, including accomplishments/learning, using only measured claims; owner review and save/submit verification are still separate. |
| Mandatory feedback | Saved Tavily probe/research observations are factual. | Token Factory and NVIDIA-model feedback must follow actual use; do not turn planned experience or fixture behavior into feedback. |
| Replay package | Actual endpoint lists five recorded-baseline replays and an inspected replay ends cleanly. | Complete required successful/iterative repair cases, including the original s2 condition if achievable without changing its gate. Merely having five rows is insufficient. |
| Main evaluation and ablation | Twelve CUDA baselines accepted for their baseline-behavior scope. Explicit policy matrices and offline tests exist. | Actual model repair outcomes/costs and the three-condition comparison, preserving unknowns, failures, source identity and complete effective Policy. Original default/strict policy ambiguity remains unresolved. |
| Final checks and submission | Full regression passed 671 tests in 98.92 seconds at 20261024T024820Z. The earlier temporary-directory failure remains preserved. Subsequent policy-matrix changes require final integrated regression; scoped checks are recorded separately. No submission was performed by this audit. | Complete final integrated checks after the current changes, obtain final owner approval where required, then verify the actual saved/submitted state. |

## New non-paid smoke evidence

Canonical directory: `runs/cli-smoke/20261024T023931Z-9a32e921/`.

| Check | Observed result | Scope |
|---|---|---|
| `headroom eval --validate-only` | Exit 0; 12 ready manifest entries; executed=false and baseline_acceptance=pending | Configuration/source/dependency validation only |
| `headroom watch ... --device cpu -- python train.py --tiny --device cpu --steps 2` | Exit 0; two tiny CPU steps; triggered=false; cleanup verified | Non-OOM passthrough; no repair |
| `headroom watch ... --device cpu -- python exit7-fixed.py` | Exit 7, matching original non-OOM SystemExit(7); triggered=false; cleanup verified | Original failure propagation |
| `headroom fix ... --runtime-profile <absent path> --device cpu --no-research` | Exit 78; needs_human; 11 report chapters; baseline=null; usage.calls=0 | Correct partial outcome before GPU/provider work |
| Existing local serve endpoints | health/examples/runs/replays/usage/Home/Results/About: HTTP 200; 8 examples; 5 baseline replays | GET-only loopback inspection; no jobs submitted |
| One saved replay | Detail HTTP 200; recorded_baseline provenance; SSE report.written then stream.end | Historical baseline presentation only |
| CLI and eval contract tests | 58 offline tests across two files | Routing, exit status, parameter preservation, budgets and evidence boundaries; not repair accuracy |

The first exit-7 fixture was written with a shell-quoting mistake and instead produced a SyntaxError/exit 1. Its source and logs remain preserved. A separate corrected fixture produced exit 7; this was a test-fixture correction, not a hidden implementation failure.

This smoke made no model/Tavily request, read no private environment file, and ran no GPU workload. The prior authorized GPU baseline campaign is separate evidence.

## Relevant measured sources and unchanged limitations

- Full 12-case GPU baseline: `runs/evaluation/baselines/20261024T023317672107Z-69b2d798/baseline.json`. Five CUDA OOM outcomes and seven completed 20-step captures; all capture/cleanup checks true and shared_gpu=false.
- Original T1.2 failure: `reports/t1.2-acceptance.json`. The s2 optimizer-state threshold remains below 40%; s5's cache gap is not fragmentation proof.
- Tavily probe: `reports/t0.5-acceptance.json`.
- Real research component: `reports/research-component-20261024T022414Z.json`: four actual method calls, followed by cache reuse; full s1/s5 repair acceptance remains false.
- Local API and CLI source evidence: `runs/cli-smoke/20261024T023931Z-9a32e921/local-api.json`, `commands.json`, `contract-tests.json`, and preserved stdout/stderr.
- Full regression history: `reports/full-tests-20261024T024006Z.json` preserves the temporary-directory setup failure; `reports/full-tests-20261024T024114Z.json` passed 669 tests; `reports/full-tests-20261024T024820Z.json` passed 671 tests in 98.92 seconds before the subsequent policy-matrix implementation.
- Actual browser interactions/mobile-width evidence: `reports/browser-validation-20261024.json`. This is distinct from the earlier GET-only CLI/API smoke and does not invent a Lighthouse score.
- Base revision for this implementation: `27ac46887e0200257564a8a1d646a3a79ccb5aa7`.

No numeric success rate, jury score, first-prize probability, ablation advantage, or completed submission is inferred from the evidence above.


## Final regression update

The first broad invocation (024006) failed during temporary-directory setup; its logs are retained. After creating the missing parent and using a file-backed runner compatible with multiprocessing spawn, the full suite passed 669 tests in 99.37 seconds (reports/full-tests-20261024T024114Z.json and .log). The next recorded full suite passed 671 tests in 98.92 seconds (reports/full-tests-20261024T024820Z.json and .log). This resolves the earlier fixture-setup blocker, not any live-model acceptance gate. Frontend contract tests, typecheck and build pass; subsequent chart-legend regression additions are being checked in the final frontend run. The later policy-matrix implementation has separate focused verification and remains subject to the final integrated regression.

## Subsequent policy-matrix and Watch adapter checks

The focused evaluation/CLI suite passed 75 tests in 1.35 seconds after adding
explicit policy selection and Watch capture/repair-mapping output fields.
`reports/policy-matrix-smoke-20261024T025631Z-d034c92f/verification.json` preserves four real
CLI planning invocations with exit 0 and executed=false. The default remains one
policy; all expanded matrices retain the same campaign spending limit. The
original default/strict ambiguity and all real repair/evaluation gates remain
open. Full integrated regression after these changes is a separate record.

## Final integrated checkpoint

After the Watch/explicit-policy/high-precision budget fixes, the complete backend suite passed718tests in107.57seconds. Frontend27tests, strict typecheck and production build passed. Final mobile Lighthouse scores are Home90/90/90 and real baseline Run89/98/89; eight actual UI screenshots are retained with hashes. See reports/final-validation-20261024.json and reports/lighthouse-20261024.json. These later records supersede pending check descriptions above while preserving prior outcomes. They do not close Stage One, authenticated model repair, original failed gates, public demo/video or submission requirements.
