# Headroom v4.2 technical plan review

Date: 2026-10-23 (Asia/Shanghai). Scope: read-only review of the complete 402-line supplied plan, plus official documentation/source checks. This document records findings and proposed resolutions; it does not amend PLAN.md, approve a deviation, certify implementation, or report completed acceptance tests.

All proposed resolutions below are explicitly **PROPOSED / NOT APPROVED**. “Implementation detail” means a correctness-preserving way to meet the existing requirement. “Acceptance change” means changing an explicit algorithm, scope, numerical criterion, policy, or promised behavior; Frank must decide before applying it. Installed PyTorch behavior must be tested on azuki; official pages currently redirect to PyTorch 2.14, whereas source citations pinned to 2.5 illustrate APIs already present at the plan's minimum version.

## 1. Technical findings and proposed resolutions

| ID | Finding | PROPOSED resolution | Classification |
|---|---|---|---|
| R01 | Patching only base Optimizer.step misses subclasses such as AdamW; the base method raises NotImplementedError. PyTorch has a global optimizer post-hook and wraps subclass step implementations [S1]. | Use a version-verified global optimizer post-hook, or equivalent verified subclass/instance interception; test AdamW, SGD, custom subclass, closure, multiple optimizers and GradScaler skipped updates. Define successful optimizer update separately from backward calls. | Implementation detail preserving intended step tracking; record the departure from literal monkeypatch wording. |
| R02 | A post-step or StepLimitReached snapshot is the end state, not the composition of an earlier activation/temporary peak. History may be truncated by max_entries; non-PyTorch CUDA allocations are not visible [S2]. | Reconstruct live allocations at the observed peak from alloc/free/segment history; distinguish free_requested from free_completed, address reuse and pools/streams. Add an allocate-large-then-free fixture and compare the reconstructed peak with allocator counters. Mark incomplete history instead of fabricating peak composition. | Implementation detail required for the promised peak evidence. |
| R03 | An OOM baseline measures successful allocations before failure, not the full-run peak. A 24 GiB device cannot directly measure a 31.4 GB successfully allocated peak. | Store observed peak, failed allocation request and any inferred requirement separately. Do not call allocated+failed_request a measured complete-run peak or claim a reliable percentage reduction from it. | Implementation detail for truthful reporting; any criterion requiring unavailable full-run peak needs an acceptance change. |
| R04 | Same seed plus a smaller batch does not make two loss series comparable. Effective batch, data grouping, update count, loss normalization, RNG use and BatchNorm behavior can change. | Compare original and patched implementations with identical initial parameters, ordered samples, effective batch and optimizer updates; use paired feasible reference inputs. Aggregate microbatch losses by samples, and where useful compare gradients/parameters or fixed validation outputs. Label unsupported comparison n/a. | Acceptance change: C.5 and T1.6 literally require small-batch reference comparisons and sometimes specific equivalence outcomes. |
| R05 | Tensor.backward scalars may be scaled loss, loss/accumulation_steps or closure intermediates; autograd.backward bypasses this method, and inference/evaluation may have no backward calls. s3's definition does not inherently yield T1.1's 20 backward losses. | Record capture provenance and scale/aggregation semantics; explicitly test both backward entry points, AMP and accumulation. Use n/a when unavailable. Resolve whether s3 contains training plus evaluation or needs a separate acceptance fixture. | Instrumentation is an implementation detail; altering the s3 ≥20 loss acceptance is an acceptance change. |
| R06 | reserved−allocated includes normal reusable cache and does not prove fragmentation. max_split_size_mb only applies to native allocator; expandable_segments is experimental and workload-dependent [S3]. | Report the gap neutrally; diagnose fragmentation using inactive split blocks, pool/stream, free-block sizes, failed request and driver free bytes. Verify allocator backend/flag support on the pinned runtime. | Metric naming/validation are implementation details; T1.2's automatic high label based solely on ≥1GB requires acceptance change. |
| R07 | Per-process allocation counters exclude other processes, but contention changes available memory, OOM location and allocator retries/cache release. Therefore shared GPU can affect completion and comparability, not only timing. | Capture external-process/free-memory state before and after runs; flag shared_gpu, allocation retries and potential contention-induced OOM. Compare paired runs under comparable availability, and avoid ranking invalid timings. Never kill unrelated processes. | Implementation detail correcting an unsupported general claim; record in PLAN_CHANGES before replacing published wording. |
| R08 | s2: bf16 autocast does not itself halve fp32 parameters or Adam moments; fused does not remove persistent moments. foreach can increase temporary peak [S4,S5]. | Measure state and temporary bytes separately. Test foreach=False/fused and checkpointing as candidates without promising impossible state savings; precision/8-bit changes obey policy and observed equivalence. | Implementation detail; changing the required ≥40% optimizer-state ground truth or two-round acceptance needs approval. |
| R09 | s4: ordinary backward releases saved tensors; total_loss += loss alone may retain graph nodes without the claimed large saved-tensor leak. Live allocation stacks usually point to forward allocation sites, not the retaining addition. | First prove the actual retaining mechanism on azuki. Separate allocation-site evidence from source-level retention evidence; do not hardcode a total_loss allocation stack. | Implementation detail for diagnosis; changing the exact s4 fixture or required stack-line match is an acceptance change. |
| R10 | s7: merely including frozen parameters with grad=None in AdamW does not allocate state. AdamW initializes state lazily only for parameters with gradients [S5]. | Construct and document a real scenario: stale existing state, unintended gradients, or incorrectly frozen parameters. Verify intended trainable set and reference semantics. | Scenario calibration is implementation detail within stated alternatives; changing task meaning/ground truth requires approval. |
| R11 | Environment whitelisting and cwd isolation do not prevent a same-UID subprocess reading other files, accessing .env or opening sockets. Static import socket rejection is not a security boundary. | Keep trusted-fixture execution distinct from public upload execution. Require actual network/filesystem/process/resource isolation for untrusted scripts; verify read-only source/HF mounts, writable run_dir only, no host secrets, process-group timeout cleanup. | Implementation detail for promised safety. If Docker/isolation is unavailable, enabling public arbitrary-script execution would require an acceptance/scope change. |
| R12 | Loading a snapshot.pickle written by an untrusted script in the secret-bearing orchestrator can execute code through pickle deserialization. | Convert snapshots to schema-checked, bounded JSON inside the sandbox; retain pickle as opaque evidence. Never deserialize untrusted pickle on the host controller. Validate paths/symlinks and report artifact size. | Implementation detail required to preserve the isolation objective. |
| R13 | Official Ultra page says 1M while the official catalogue still says 256K [S8,S9]. HTTP 200 does not show that a parameter took effect or that the full prompt was processed. | Test live catalogue and exact IDs, needle answer, server usage, finish_reason, schema/tool-call shape, latency and errors. Test reasoning knobs behaviorally; record ignored/unsupported separately. Use the actual model tokenizer or clearly label cl100k estimates. Largest successful staircase input is a verified lower bound, not an exact maximum. | Implementation detail; if lower limit prevents the 200k/500k gates, follow §F and obtain any necessary acceptance-change decision. |
| R14 | A 150k-token, Top-N-trimmed evidence pack is not necessarily the full raw CUDA snapshot. | Report evidence bytes/events/stacks/source coverage and truncation. Say “the entire generated evidence pack” when true, and distinguish advertised context capacity from actually exercised inputs. | Implementation detail for truthful claims. |
| R15 | Seed control alone is insufficient for deterministic CUDA behavior; checkpointing also has RNG-preservation constraints [S6,S7]. | Pin versions, data order and deterministic settings where supported; log nondeterministic-operation failures. Verify repeated baseline before assigning identical. | Implementation detail; any relaxation of exact-equality acceptance needs approval. |
| R16 | Same parameter count does not prove identical training. A patch can keep unused parameters while skipping layers/data/updates or changing the objective. | Combine structural/static checks with update counts, effective batch, data/sample counts, trainable-parameter fingerprints, model shape invariants and paired numerical evidence. Parameter totals remain required but are not sufficient. | Implementation detail for Honesty. |
| R17 | CUDA work is asynchronous; float(loss) synchronizes, and pre/post optimizer timing alone excludes forward/backward. Allocator traces may have event indices rather than timestamps. | Define full-step timing, warmup and synchronization; record instrumentation effects consistently. Use event index or step on plots unless actual timestamps exist. | Implementation detail for meaningful throughput and plots. |
| R18 | Eight synthetic ablation cases do not automatically establish a statistically significant context benefit; tuning prompts on the same cases leaks evaluation information. | Freeze prompts/settings, pair seeds and budgets, retain every failure, distinguish descriptive counts from significance, and report real-repository cases separately. Do not force the expected direction. | Implementation detail; expanded sample counts are optional and must remain within authorized time/cost. |
| R19 | “First”, “nobody” and “no existing tool” are unproven universal novelty claims in A.1/A.4. | Verify current related work and use a scoped statement supported by sources, retaining concrete distinctions about snapshots, patches and hardware verification. | Truthful documentation detail; explicitly record any replacement of requested literal README wording. |
| R20 | GB/GiB and allocator versus total-device usage are mixed; 24GB product branding does not define a byte parser. | Persist bytes, define GB=10^9 and GiB=2^30 in CLI/schema, and render both when helpful. Do not compare differently defined values. | Implementation detail; changing a literal fit threshold's intended unit needs clarification. |

## 2. Conflicts requiring explicit accounting

Every resolution in this section is **PROPOSED / NOT APPROVED**, except the already explicit v4.2 precedence noted in C03.

| ID | Conflict | Proposed handling |
|---|---|---|
| C01 | C.5 says ≤4 rounds; T2.1 says ≤6. | Choose one documented configuration and acceptance expectation with Frank. Do not silently choose whichever makes a test pass. |
| C02 | Default policy forbids numerical change, but T2.1 requires default output including bf16; stop-on-target may produce only one Pareto point. | Keep policy hard constraints. If authorized, run a separately labeled permissive strategy and specify an exploration stopping rule; otherwise ask to amend the two-tier criterion. |
| C03 | T1.12 and Phase 2 heading say wait for Frank, but §0.6 explicitly updates continuation in v4.2. | Existing v4.2 instruction controls: after passing MVP continue Phase 2 P0; after at most three repair rounds still failing, stop for Frank. This is interpretation of explicit revision, not a new approval. |
| C04 | T1.12 says clear runs; discipline forbids deletion without approval. | Preserve evidence and use a fresh evaluation campaign namespace. If literal deletion is required, obtain approval for the concrete paths first. |
| C05 | §F allows cutting T2.5 HF, but P0 T2.8 and T4.1 require HF in their evaluation denominators. | Record the dependency. Do not silently reduce 10-case/20-run evaluations; seek a coordinated acceptance change if cutting HF. |
| C06 | T1.9 allows ≤$0.8; T1.12 requires each run ≤$0.6. | The stricter integrated $0.6 gate must independently pass even if the individual nanoGPT gate passed. |
| C07 | Phase 2 ≥75% metrics are explicitly labeled targets with truthful recording. | Preserve actual denominators/failures and report whether targets were attained; do not mark all evaluation work absent solely because a target misses, or mislabel the target as met. |
| C08 | Main instructions require every Phase summary/handoff/push, even where individual tasks omit filenames. | Include phase-0/3/5/6 summaries and handoffs in addition to numbered task artifacts. |
| C09 | Phase 6 has future human-visit requirements. | Shipping software or scheduling reminders does not finish the overall goal; retain future checks until current evidence proves them complete. |

## 3. Complete 43-task acceptance mapping

This is an index to PLAN.md, not a replacement for its exact acceptance wording. Each task needs actual command/output/artifact evidence and status in PROGRESS.md. P1/P2 cuts must be explicit; no denominator may silently shrink.

| Task | Priority | Required acceptance evidence |
|---|---|---|
| T0.1 | P0 | Required .env keys and mode 600; ≥3 Nemotron API catalogue entries; successful Tavily result; authorized headroom public repo with Apache license; existing Frank Git identity; Frank confirms ≥$25 balance. |
| T0.2 | P0 | Raw outputs for nvidia-smi, OS, disk, RAM, Python, uv/docker/git, GPU Docker test, sudo and HF network; ENV.md conclusions DOCKER_GPU/NET/DISK_FREE_GB; record non-ok states. |
| T0.3 | P0 | C.7 scaffold/dependencies/tools; CUDA True and 3090 Ti; snapshot True True; all pre-commit checks pass; first commit with Frank identity; gitleaks zero. |
| T0.4 | P0 | Both endpoint catalogues and ≥3 model prices; capability matrix; Super JSON/tools successes; 64k/200k/500k/900k Ultra probes including latency/cost; four-way Super probe; measured config; ≥5 FEEDBACK items. |
| T0.5 | P1 | Tavily basic/advanced plus checkpoint-document and GitHub-issue extraction; script exit zero; two FEEDBACK items; TOOLS.md schema. |
| T0.6 | P0 | All eight scripts/READMEs/truth/expected fixes/peaks and INDEX.yaml; ≤60s OOM or 20-step reclaim measurements; pinned nanoGPT ref/config and genuine OOM traceback. |
| T1.1 | P0 | s1 oom result/snapshot/>1000 events/positive request/OOM traceback; runnable s3 completed/20 steps/≥20 loss values; 30s timeout/no descendants; no API key in child; repeated first-five-loss exactness. |
| T1.2 | P0 | s1/s2/s4/s5 MD+JSON; ≤105% token budget; s2 state≥40%; s4 source evidence; s5 ≥1GB gap and requested fragmentation criterion; aggregation/trimming tests; PNG with OOM. See R02/R06/R09. |
| T1.3 | P0 | Routing/retry/cost mock tests; real Super schema JSON; actual 200k-token Ultra evidence call with latency/cost in FEEDBACK. |
| T1.4 | P0 | ≥6/8 correct first root causes; each cause valid stack references; ≤$0.35 Ultra call; diagnose schema tests. |
| T1.5 | P0 | ≥6/8 patches apply with 3way and compile within ≤3 repairs; no forbidden autocast under strict policy; Super completion_tokens≤4000. |
| T1.6 | P0 | s1 completed/<24GB/identical-or-within_tol; s3 reduction≥30%; half-model cheat changed and target false; all four equivalence states tested. See R04. |
| T1.7 | P0 | End-to-end fix exits zero; expected baseline→evidence→diagnose→patch→verify→done sequence; events≥15; llm_calls≥2; usage equals DB cost sum. |
| T1.8 | P0 | report MD/JSON, before/after PNG, composition/diff/verification/usage; report and replay commands; ≥7 level-two sections; every GB/% backed by JSON; patch applies to original. |
| T1.9 | P0 | Pinned repo/ref/cmd/sitecustomize flow; nanoGPT completed≤22GB; ≤60 changed lines only train/config; equivalence not changed (n/a allowed if no reference); ≤$0.8. |
| T1.10 | P0 | Shrunk-layer/vocab/training-truncation cheats refused with required reason codes; normal patches accepted; parameter-count consistency; effective network/path controls. |
| T1.11 | P1 | Only if Docker GPU ok: network absent; default Docker s1 succeeds; timeout container cleanup; HF cache read-only and usable. |
| T1.12 | P0 | Nine complete reports/zero exits; ≥6 targets and ≥6 correct first causes; each≤$0.6 and 8min; pytest≥25/ruff0/gitleaks0; RESULTS full table; summary with failures/adjustments/model experience/Phase2 advice. |
| T2.1 | P0 | Actual keep/revert search; strict s2 ≥2 rounds fit22; required ≥2 Pareto tiers with independent patches; injected loss regression reverted; ≤6 rounds; per-round decision/reason. See C01/C02. |
| T2.2 | P0 | Actual current-torch Tavily search/extract injected into patch context; s5 CUDA and s1 checkpoint URLs; repeated-query credit0 cache; research records; ≤4 calls/run. |
| T2.3 | P1 | Every Top40 stack gets Nano annotation; ≤$0.02/run; ≥80% agreement with heuristics across eight cases. |
| T2.4 | P0 | $0.05 run budget yields partial report and budget.exceeded; $0.1 daily budget immediately refuses new runs; full multi-round run≤$1.2. |
| T2.5 | P1 | HF Trainer target met; only≤15 configuration lines changed; state+activation diagnosis. |
| T2.6 | P2 | watch arbitrary command triggers complete OOM repair flow; non-OOM preserves actual exit code. |
| T2.7 | P1 | Three scenarios agree Docker vs subprocess peak within 1%; HF cache robustness. |
| T2.8 | P0 | Ten scenarios×two policies; complete metrics/failure table; target and first-cause rates against 75% goals; ≤3 tuning rounds; total≤$12; phase-2 summary. |
| T3.1 | P0 | All specified run/report/patch/evidence/example/usage/health endpoints; historical+live SSE; second concurrent request queued; health200; socket-upload400 with reason; worker/limits. |
| T3.2 | P0 | Home/Run/Results/About and all specified evidence/download/source/cost/brand views; real browser run streams through final report; Lighthouse≥70; no mobile horizontal overflow. |
| T3.3 | P0 | ≥5 replays including two-round s2/nanoGPT/reclaim; playback starts≤2s; budget/GPU-busy guidance. |
| T3.4 | P1 | Supplied design fidelity accepted by Frank for Home/Run; tokens in web/src/theme.ts. |
| T3.5 | P0 | Approved public HTTPS works on phone network; third same-IP hourly run429; queue≤3; run≤10min; restart recovery≤10s; stopped-service alert actually received within requirement. |
| T3.6 | P0 | ≥8 server-only screenshots covering timelines/composition/diagnosis/diff/verification. |
| T4.1 | P0 | scenario_set with ten core plus two–four new real scripts; eval dry-run executable; observed baseline behavior matches expectation. |
| T4.2 | P0 | Complete per-scenario main RESULTS table and aggregate, including failures, costs, timings, numerical status and reproduction commands. |
| T4.3 | P0 | Eight cases×full+Ultra/summary-only+Ultra/full+Super; ablation table and three–five evidence-supported sentences; retain unfavorable results. |
| T4.4 | P0 | v0.9-eval tag; phase-4 summary; thereafter bug fixes only. |
| T5.1 | P0 | All README sections/first-20-line requirements; ≤5-command quickstart; clean-clone s1 verification; GitHub Apache detection; gitleaks0. |
| T5.2 | P0 | ARCHITECTURE/RESULTS/FEEDBACK final; five tool/model sections and three–five actionable suggestions; Claude review acceptance; no secrets. |
| T5.3 | P0 | English DEVPOST draft; actual Devpost draft pasted and saved, with confirmation evidence. |
| T5.4 | P0 | Frank-recorded public YouTube video≤2:55/1080p; permitted assets; UI and named Nebius/NVIDIA narration in first60s; demo/ablation numbers match evidence. |
| T5.5 | P0 | By Oct28 evening: actual Devpost Submitted, Coding and Agentic Engineering, three working links, feedback completed. |
| T5.6 | P0 | Four 1–5 self-scores and cheapest +1-point improvement each; Stage One audit; reports/final-summary.md. |
| T5.7 | P0 | v1.0 tag; clean-environment rerun; public smoke test; Devpost final save by Oct30 15:00 CET. |

## 4. Unnumbered Phase 6

- Oct31–Dec15: weekly /api/health and alert checks with timestamps/outcomes and necessary bug-fix evidence.
- By Nov25: Token Factory balance≥$10 and available Tavily credits confirmed.
- Keep azuki online through judging; judging-period changes only bug fixes.
- Required human visits on Dec1 and Dec8 with records. These cannot be pre-certified.
- The continuing goal remains incomplete until these future requirements and all human deliverables have authoritative evidence.

## 5. Cross-phase deliverables and human gates

Required throughout:
- PLAN.md preserved byte-for-byte; amendments/proposals only in PLAN_CHANGES.md.
- PROGRESS.md contains every task, status, actual acceptance commands/output summaries, “待 Frank 决策” and “Frank 待办”; next session reruns the prior task's acceptance.
- All code, tools, environments, dependency caches, models, raw evidence, node_modules, screenshots and video assets remain on azuki.
- Every Phase produces reports/phase-N-summary.md, updated docs/RESULTS.md and PROGRESS.md, combined reports/handoff-phase-N.md under 1MB, terminal summary, and the exact authorized pull-command pattern:
  scp -P 40022 xiaodouzi@azuki.ubj.ink:~/workspace/headroom/reports/handoff-phase-N.md ~/Downloads/
- Every commit follows a zero-findings gitleaks detect; author/committer are Frank's existing server identity, no AI attribution. Push only headroom, at least once per Phase.
- Secrets remain in chmod600 gitignored .env, absent from child environments/logs/reports. Do not echo credentials or pass them in exposed command arguments.

Human gates:
1. Accounts/credentials and missing GitHub authentication or existing Git identity; Frank's Token Factory balance confirmation. Continue T0.2/T0.3/T0.6 while waiting, as explicitly authorized.
2. Monetary consumption beyond confirmed authorization: the four Ultra long-input prompts alone total approximately 1.664M input tokens, about $1.664 at the plan's $1/M rate before outputs, retries or other probes. Prepare a concrete bounded probe budget first; verify live pricing.
3. Opening ports/public exposure, deletion, and genuine changes to plan/acceptance criteria: record concrete action and recommendation and wait for Frank.
4. Phase1 failing after at most three repair rounds: stop for Frank; passing follows the explicit v4.2 continuation rule.
5. Domain/Cloudflare access and an authorized monitoring/alert recipient at T3.5; do not send third-party messages without authorization.
6. Frank design acceptance; Claude review of final docs; Frank video recording and Devpost submission; required December human visits.
7. P1/P2 cuts under §F need a recorded scope decision and dependency accounting, especially HF requirements embedded in P0 evaluations.

## 6. Official references

[S1] PyTorch 2.5 optimizer source: base step, global optimizer hooks, subclass wrapping.
https://docs.pytorch.org/docs/2.5/_modules/torch/optim/optimizer.html

[S2] PyTorch CUDA memory snapshots: visibility limits, ring buffer, trace actions, block states.
https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html

[S3] PyTorch CUDA semantics: allocator controls, inactive split blocks, expandable_segments.
https://docs.pytorch.org/docs/2.14/notes/cuda.html

[S4] PyTorch AdamW API: foreach temporary-memory cost and fused behavior.
https://docs.pytorch.org/docs/2.14/generated/torch.optim.AdamW.html

[S5] PyTorch 2.5 AdamW source: grad=None skip, lazy state initialization and moments.
https://docs.pytorch.org/docs/2.5/_modules/torch/optim/adamw.html

[S6] PyTorch reproducibility guidance.
https://docs.pytorch.org/docs/2.14/notes/randomness.html

[S7] PyTorch gradient accumulation and checkpoint RNG documentation.
https://docs.pytorch.org/docs/2.14/notes/amp_examples.html
https://docs.pytorch.org/docs/main/utils/checkpoint.html

[S8] Nebius official Ultra model cookbook: endpoint, model ID, 1M context and listed pricing.
https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md

[S9] Nebius official Nemotron directory: contains a conflicting 256K Ultra entry; runtime probes remain authoritative.
https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/README.md

No source above substitutes for installed-version tests, authenticated capability probes, actual GPU runs, human approval, or completion evidence.

