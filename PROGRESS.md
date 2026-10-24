# Headroom Progress

Initialized: 2026-10-23T00:44:58.397951+00:00
Canonical plan: docs/PLAN.md (v4.2, preserved verbatim).
All work, caches, runs, and media remain on azuki.

## Tasks

| Task | Description | Status | Evidence |
|---|---|---|---|
| T0.1 | 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min） | 进行中 | GitHub/Tavily and private Nebius key verified; authenticated catalogues200 and Super/Nano chats passed; original >=25USD credit gate pending |
| T0.2 | 服务器环境勘察（P0，~30min） | 已验收 | docs/ENV.md; reports/env-preflight.json; Docker GPU ok, NET ok, 5694.85 GiB free; shared GPU and no sudo recorded |
| T0.3 | 仓库骨架与工具链（P0，~40min） | 已验收 | reports/toolchain-checks.json; reports/pre-commit-t0.3.log; commit ca6c86ad099c519b92d1ccb88219b08450aa8da6, Frank author/committer, pushed origin/main |
| T0.4 | Token Factory 探测（P0，~1h） | 首次目录/chat实测通过；完整验收待办 | reports/tokenfactory-minimal-20261024.json; two catalogues200; exact Super/Nano chats; full JSON/tools/Ultra staircase/concurrency pending;93 guarded probe tests |
| T0.5 | Tavily 探测（P1，~15min） | 已验收 | reports/t0.5-acceptance.json; live exit0, 4/4 operations, 2 factual FEEDBACK entries, observed schema; API total3 credits matches UI3/1000 |
| T0.6 | 场景集 v0（P0，~2h） | 已验收 | reports/t0.6-acceptance.json; 3 synthetic CUDA OOM <7s, 5 reclaim completed20 steps with measured README peaks; pinned nanoGPT CUDA OOM11.489s; all cleanup verified |
| T1.1 | Lab 包装器：运行并抓证据（P0，~3h） | 已验收 | reports/t1.1-acceptance.json; GPU report022523 all checks true; s1 2050 events; s3 completed20 deterministic; final full regression 95 tests passed |
| T1.2 | 证据包生成（P0，~3h） | 实现完成，验收未通过 | reports/t1.2-acceptance.json; s1/s2/s4/s5 artifacts and real peak replay verified; s2 optimizer-state fraction 39.8715% < original 40% |
| T1.3 | LLM 客户端与路由（P0，~1.5h） | 离线实现完成，实测待验收 | reports/runtime-output-cap-20261024T102844Z/verification.json;210 guarded tests; exact Nano ID and explicit output-cap field; real Super JSON/Ultra200k pending |
| T1.4 | Diagnose（Ultra）（P0，~2.5h） | 实现完成，模型验收待办 | docs/DIAGNOSE.md; docs/PROMPT_PREFLIGHT.md; four complete requests audited locally; provider billing domain and real Ultra diagnosis pending |
| T1.5 | Patch（Super）与应用（P0，~2.5h） | 实现及离线验收完成；真实补丁待办 | docs/PATCH.md; git apply, compile, bounded repair and policy tests; real Super/GPU cases pending |
| T1.6 | Verify 与比较（P0，~2h） | 比较器与CPU配对已测；修复验收待办 | docs/VERIFY.md; parameter shrink rejected; original numerical/throughput gates retained |
| T1.7 | 单轮编排 + 存储 + 事件（P0，~2h） | 主流程与存储已实现并离线联调 | docs/SEARCH.md; SQLite ordered events, partial reports, SDK fixture pipeline; live two-call gate pending |
| T1.8 | 报告（P0，~1.5h） | 报告实现与数字追溯通过 | docs/STORAGE_REPORTS.md; JSON/Markdown, source links, Pareto files; real repaired report pending |
| T1.9 | 真实仓库：nanoGPT（P0，~2h） | 固定仓库输入与真实GPU基线通过 | reports/nanogpt-lab-baseline-20261024.json; actual repair/22GB/diff/cost gates pending |
| T1.10 | Honesty 与安全（P0，~1h） | 静态与CPU真实性检查通过；完整修复待办 | docs/PATCH.md; model shrink/truncation/escape checks and observed parameter counts |
| T1.11 | Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h） | Docker隔离与缓存组件通过 | docs/LAB.md; docs/WATCH_HF.md; no-network, read-only source/cache and cleanup tests |
| T1.12 | MVP 整体验收 + 报告（P0，~1.5h，10/24 晚） | 待Nebius真实MVP验收 | Nine real repair runs and success/time/cost thresholds not yet measured |
| T2.1 | 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h） | 六轮搜索与Pareto实现完成；真实验收待办 | docs/SEARCH.md; original baseline fixed, retained cumulative patches; s2 two-round/bf16 policy issue unchanged |
| T2.2 | Tavily Research（P0，~2h） | 真实Research组件通过；修复报告待办 | reports/research-component-20261024T022414Z.json; four live methods, 3 reported credits, repeat cache 0 calls/credits |
| T2.3 | Nano 栈标注（P1，~1h） | Nano标注与子预算已实现；实测待办 | headroom/annotate.py; top40 strict labels, 0.02 USD sub-budget; live eight-case agreement pending |
| T2.4 | 预算守卫与成本面板（P0，~45min） | 持久预算与面板已实现并离线测 | docs/RUNTIME.md; per-attempt reservations, unknown charges, daily/total caps, partial stop reports |
| T2.5 | HF Transformers 场景（P1，~2h） | HF场景CPU/GPU基线通过；修复待办 | reports/hf-trainer-baseline-20261024.json; real Trainer OOM; configuration-only repair gate pending |
| T2.6 | Watch 模式（P2，~1.5h） | 通用argv隔离观察/退出码通过；完整修复验收待办 | docs/WATCH_HF.md; 89 scoped tests passed; modules/inline/flags/shell observed in Docker; unsupported replay OOM needs_human; missing capture unknown; no host fallback |
| T2.7 | Docker/HF 缓存稳健性（P1）：验收：三个场景在 Docker 路径下结果与子进程路径一致（峰值差 ≤ 1%）。 | 安全独立子进程环境阻塞；原门槛未通过 | reports/t2.7-isolation-preflight-20261024.json; unshare uid_map EPERM; bwrap network setup EPERM; no sudo/system change/unsafe host fallback; existing Docker dual-entry CPU checks are component evidence only |
| T2.8 | 小评测 + 自优化（P0，可夜间自治，~4h） | 显式策略矩阵与离线统计完成；原真实验收待办 | docs/EVALUATION.md; default/strict 实际等价，allow_precision 必须显式选择；全矩阵共享预算，逐行完整 Policy；原两档歧义、≤3轮优化、target_met/首因各≥75% 和 $12 实测均未关闭 |
| T3.1 | FastAPI + SSE（P0，~3h） | API队列/SSE/下载已实现并测 | docs/API.md; shared admission/preparation/queue/worker deadline, owned process cleanup, report-ready SSE, session isolation and rate limits |
| T3.2 | 前端素版（P0，~4h） | 四页前端/当前浏览器通过；真实修复流程待办 | reports/continuation-web-20261024.json;33 tests/typecheck/build; current browser and refreshed health verified; earlier Lighthouse Home90/90/90, baseline Run89/98/89 remains dated evidence |
| T3.3 | Replay（P0，~1.5h） | 5条真实基线回放可用；规定修复回放待办 | reports/baseline-replays.json; explicitly baseline-only; s2 two-round/nanoGPT/reclaim repair replay not fabricated |
| T3.4 | Claude Design 对齐（P1，~3h；设计稿 10/25–10/26 由 Frank+Claude 产出到 `design/`） | 待Frank设计稿与认可 | No design package has been supplied; theme implementation exists |
| T3.5 | 公网部署、限流、监控（P0，~2.5h；Frank 提供域名/Cloudflare） | 部署与监控模板完成；公网待办 | docs/DEPLOYMENT.md;600s from admission through execution, cleanup separate; fresh read-only availability/local budget; public domain/tunnel/alerts acceptance pending |
| T3.6 | 预录素材（P0，~1h） | 8张真实基线UI素材完成；完整修复素材待办 | docs/media/ui-20261024T025659Z-baseline-only; baseline-only labels, desktop/mobile Home/Results/About/Run; no repaired before-after/diagnosis/diff fabricated |
| T4.1 | 评测集定稿 | 基线范围已验收 | reports/evaluation-baselines-20261024.json; all12 matches, 5 OOM/7 completed20, full capture/cleanup; source pins |
| T4.2 | 主评测 | 工具与表格已准备；真实主评测待办 | docs/EVALUATION.md; docs/RESULTS.md; Nebius live model run required |
| T4.3 | 消融 | 三条件消融工具完成；实测待办 | full Ultra / traceback+summary Ultra / full Super; no predicted gain presented as measured |
| T4.4 | 冻结 | 待真实评测后冻结 | No v0.9-eval tag created before acceptance |
| T5.1 | README | README初稿完成；干净环境真实repair待办 | README.md; honest role/status table, local quickstart, evidence and limits |
| T5.2 | docs 定稿 | 文档初稿完成；评审与真实模型反馈待办 | docs/ARCHITECTURE.md; RESULTS.md; FEEDBACK.md; no fabricated model experience |
| T5.3 | Devpost 描述 | Devpost本地草稿完成；未保存表单 | docs/DEVPOST.md; owner final review/submission pending |
| T5.4 | 视频 | 视频脚本完成；待真实修复与录制 | docs/VIDEO_SCRIPT.md; <=2:50 storyboard, actual evidence required |
| T5.5 | 首次完整提交 | 未开始 | — |
| T5.6 | 评委视角自检 | 当前就绪审阅完成；发布前复检待办 | reports/submission-readiness-20261024.md; actual repair, public demo/video and submission gate remain pending |
| T5.7 | 最终提交 | 未开始 | — |
| Phase 6 | Weekly health/alerts; balance by Nov 25; manual Dec 1 and Dec 8 access | 未开始 | Future dated acceptance |

## Acceptance log

- 2026-10-24 11:18UTC: original-goal continuation closed concrete production gaps: explicit diagnosis information requests stop after one call (including empty plan), reclaim planning uses remaining reduction against the fixed original30% target, per-round stored diffs/verification remain visible after revert, curated Results campaigns and measured/unknown summaries/paired-ablation Markdown are implemented. Automatic pairing now derives actual tensor/initial-parameter/per-update evidence for bounded s3/s4 contracts; other sources and historical captures remain unknown. Full guarded backend923tests passed160.25s with unchanged source hashes; frontend38tests/typecheck/build passed. Two full-size manual s3 GPU runs verified20updates, unchanged37,791,744parameters, exact loss equality,73.3787%peak reduction and0.3333%optimizer-interval increase; no model generated this repair and it contributes zero model benchmark successes. No additional model charge, recharge, public port, submission, or original PLAN/gate change. See reports/plan-completion-20261024/verification.json and reports/handoff-plan-completion-20261024.md. Original full goal remains incomplete.

- 2026-10-24T10:54:58.477225+00:00: continuation completed the explicit model output cap/exact Nano ID, CPU-only complete-request audit, shared600s admission deadline, owned preparation cleanup including supervisor death, report-ready SSE, cached read-only availability/local budget, and the host-versus-reviewed HF cache separation. Full guarded backend859tests passed142.74s with source hashes unchanged; frontend33tests/typecheck/build passed on Node24.22.1; four real15s health polls stayed fresh and browser baseline report links worked. Reports: continuation-validation-20261024.json and handoff-continuation-20261024.md. Earlier18 CPU failures, Node startup failure and stale-preview observations remain preserved. Minimal Super/Nano calls are the only new model inference; no further billing, GPU repair, public deployment or submission was performed. Original PLAN/gates remain unchanged.

- 2026-10-24 10:24UTC: user confirmed private key setup and explicitly authorized only up to0.10USD trial credit for minimal connectivity. Both official catalogue GETs succeeded; one Super and one Nano chat each returned200/stop with exact identity, valid usage, zero retries and no cap violation. Usage-priced total0.00003666USD, with21% tax reserve0.0000443586USD; not an invoice reconciliation. Evidence reports/tokenfactory-minimal-20261024.json. No Ultra/full evaluation or recharge authorized; live runtime remains disabled. User also requests continued original-goal development and later use of promotional credits when they arrive. Original PLAN and failed gates remain unchanged.

- 2026-10-24 full-development checkpoint: final backend718tests passed107.57s; frontend27tests/typecheck/build passed; Home Lighthouse90/90/90 and real baseline Run89/98/89. Twelve actual GPU baselines matched5OOM/7completed20 with capture and cleanup verified. Full source-hash receipt: reports/final-validation-20261024.json; handoff: reports/handoff-development-20261024.md. Real Research added3credits; refreshed Tavily total6/1000,994remain, pay-as-you-go off. Nebius key/profile absent; no authenticated Nebius inference or recharge performed. All original failed gates retained.

- 2026-10-24: Frank explicitly requests full original-plan development, continuing every implementable part while only genuinely Nebius-dependent work waits. Implement later components with honest offline/real-evidence verification; retain original acceptance gates and existing failures. Self-funded Token Factory availability is being researched; no payment or paid inference has been authorized by that question.

- 2026-10-24 00:57 UTC: Frank completed hidden-input Tavily import; private .env preflight passed. The authorized four-operation live probe exited0; basic/advanced searches and both exact-URL extracts succeeded. Report: reports/probe-tavily-20261024T005720856027Z-332161bd.json. Two factual feedback entries (TAVILY-001/002) and observed TOOLS schemas are now recorded; independent read-only review confirmed API checks. Full T0.5 acceptance: reports/t0.5-acceptance.json.
- Account usage was independently refreshed before and after this run: free-plan used credits moved0 to3/1000, matching API total3;997 remain, pay-as-you-go and auto-upgrade are off, and the UI says requests stop at plan limit. Evidence: reports/tavily-account-after-20261024T005808Z.json. The two extract responses reporting0 do not prove future extraction is free. Nebius remains deferred/unverified; no model calls or other task acceptance is implied.

- 2026-10-24 offline continuation completed: reports/api-prep-20261023T222659Z.json records 259 passed in53.97s, Ruff and formatting passed, and the default model-probe dry-run planned62 operations with network_requests=0 and accepted=false. New coverage includes55 guarded probe tests,82 LLM client/router/cost tests,25 diagnosis checks and2 SDK/schema/evidence integration tests. Full prior tests remain green; historical runs are preserved. Original PLAN SHA remains e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.
- Independent review fixed native-versus-fenced JSON classification, retry dispatch after a shared budget violation, absolute streaming deadlines, nonfinite JSON, malformed SDK responses missing accounting, and response model identity. Missing or mismatched identity cannot become accepted capability/diagnosis; uncertain billing stays unknown and model probes halt further paid dispatch. T0.4/T1.3/T1.4 remain unaccepted pending real model calls.
- Test-isolation incident retained: an earlier AsyncClient refactor round attempted three official-endpoint transports using only a fixed dummy credential; exact network outcomes are unknown. No real key or .env was used by those tests. Corrected mocks and independent DNS/socket-denial guards passed, including separate reviewer checks. See docs/MODELS.md; do not describe the whole development turn as zero network.
- Historical pre-import credential check (superseded by the verified Tavily import above): server .env was0600; Tavily and Nebius values were empty. Hidden-input Tavily importer syntax validated. No authenticated model/search probe was run; the Tavily four-operation live check remains pending import, and Nebius registration/credit troubleshooting remains deferred at Frank's request.

- 2026-10-24: Frank asked to defer the Nebius registration/credit issue and start previously account-dependent work. Proceed with T0.4/T1.3 offline preparation and T1.4 schema/prompt checks while keeping their live acceptance pending. This sequencing instruction does not waive T1.2, numerical, loop, or cost gates.
- Tavily live UI preflight: Researcher Free, 0/1000 credits used, pay-as-you-go and auto-upgrade off; requests stop at plan limit. Evidence: reports/account-status-20261023T221833Z.json. Existing default key remains in the browser; server import is pending because computer-use access to Terminal was denied. User was given a hidden-input SSH importer; no key was printed, no new key was created, and no paid setting was changed.

- T1.2 final review: reports/t1.2-acceptance.json retains accepted=false. All four real evidence bundles are present, their true peak/terminal replay matches native counters, full source hashes match, budgets pass, and OOM PNGs are visually checked. Nine of ten scenario checks pass; s2 optimizer moments are 8,593,604,608 / 21,553,250,816 bytes =39.8715009692%, below the unchanged40% gate. s4 actual Top40 train.py:107 stack is512 bytes; s5 high denotes a19.125GB cache-gap proxy, not confirmed harmful fragmentation.
- Final regression: reports/tests-20261023T025427Z-final.log, 95 passed in53.54s; exact invocation in reports/tests-latest-final.json. Ruff check and format passed; real evidence CLI smoke passed. No live API calls were made.

- T1.1: all original GPU checks passed in reports/lab-gpu-acceptance-20261023T022523Z.json; s1 CUDA OOM with2050 device0 trace events, valid pickle/native JSON, positive request and traceback; s3 twice completed20 with20 losses and exact first5 equality. 61 tests passed in53.15s including real30s timeout and child cleanup, secret isolation, AdamW step hooks, command capture and symbolizer dependency. CLI CPU smoke reached5 controlled steps.

- T0.6 s1 calibration: original width1024/depth12 baseline produced268 trace events underLab, below unchanged T1.1>1000. Width256/depth192 uses101007360 real parameters(+0.256%); batch32/seq2048/SGD and activation root cause unchanged, no filler. New source separately verified in reports/gpu-baseline-20261023T022519Z-e164c187.json; new model version is never compared to old as a repair. Old evidence retained.

- Lab corrections retained with failing evidence: Docker29 lowercase absence text initially caused false cleanup-unverified; fixed case-insensitive exact-owned-container checks. Old image lackedaddr2line; fullC++symbolization failed stoi, fixedbybinutils in image54accb9f... with fullstack capture unchanged. Initial reports/lab-gpu-acceptance-20261023T020307Z-failed.json and020718.json retained.

- 2026-10-23: Frank reports the GPU service stopped and asks to continue other work while he registers accounts. Proceed with API-independent Lab implementation; T0.1/T0.4/T0.5 remain pending, and all original acceptance criteria remain unchanged. No paid call has been authorized by this sequencing instruction.

- T0.6 accepted: `uv run python scripts/check_gpu_baselines.py` exit0, canonical run20261023T013238Z-a16fc6fb launched9 full GPU workloads. All source hashes and raw results independently checked. README allocated/reserved peaks recorded for all8; INDEX provenance updated; nanoGPT.oom.txt matches raw traceback. See reports/t0.6-acceptance.json. No later snapshot/repair criteria certified.

- 2026-10-23T01:29Z: Frank stopped the competing service. Live check: no compute processes, 24055 MiB free, baseline guard ready=true. Full GPU T0.6 calibration resumed. First s1 run reproduced typed CUDA OOM in 5.235s with verified cleanup; its startup-only peak fields are invalidated by reports/gpu-baseline-013012-peak-correction.json. OOM terminal counter instrumentation added before the canonical rerun.

- T0.6 runner preparation: scripts/check_gpu_baselines.py and docs/GPU_BASELINES.md collect full-size default GPU baselines in Docker, distinguish CUDA OOM/host OOM/error/timeout, and retain raw evidence. Actual `--check-only` returned 78 with workloads_launched=0 while the known competing process was still present (historical check). CPU-only Docker canaries: `uv run pytest -q tests/test_phase0_baseline_failures.py` passed 2/2 in 6.19s (reports/phase0-baseline-canaries.log): CPU OOM is rejected; timeout cleans up the owned container. At that preparation checkpoint the full GPU path was unexecuted; it was subsequently verified by the canonical run above.

- T0.6 historical CPU preparation checkpoint: eight source fixtures + README + INDEX prepared. `uv run python scripts/check_scenario_smoke.py` (two four-case batches) completed 20 CPU tiny steps in all 8 cases; evidence reports/scenario-cpu-smoke-summary.json and per-batch logs. This is not GPU baseline acceptance. nanoGPT pinned at 3adf61e154c3fe3fca428ad6bc3818b27a3b8291, deterministic synthetic inputs prepared, original upstream CPU tiny run exit 0 (upstream max_iters=20 emits iterations 0 through 20). At that checkpoint no full-size GPU OOM trace or peak measurement existed; the later canonical run supplies both. Live model calls and repairs remain unverified.

- T0.3: `uv run python scripts/verify_toolchain.py` exit 0: torch 2.5.1+cu124, CUDA True, NVIDIA GeForce RTX 3090 Ti; snapshot True True; .env ignored and mode 600. `uv run pre-commit run --all-files`: all three hooks Passed. `gitleaks detect` and staged scan: 0 findings. Commit ca6c86ad099c519b92d1ccb88219b08450aa8da6 author and committer both match existing Frank identity; push origin/main succeeded.

- T0.2: `python3 scripts/inspect_env.py` exit 0. All checks retain original stdout/stderr/exit code. DOCKER_GPU=ok; NET=ok; disk=5694.85 GiB. Existing other compute process is noted. sudo requires password; uv/gitleaks not initially installed.
- T0.1: public https://github.com/xiaodouzi666/headroom created with Apache-2.0; server .env initialized with empty keys, permissions 600, gitignored. PLAN SHA-256 matches attachment e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.

- Bootstrap: SSH verified; project did not exist; git identity is already configured; gh authenticated as xiaodouzi666; repository did not exist.

## 待 Frank 决策

- Ultra readiness: a catalogue-wide 1,048,576-token reservation plus4,000 output tokens costs1.060576USD before tax at observed prices, exceeding the unchanged0.60USD run guard. Four real request payloads now have pinned local template counts29,221–40,430, but this is not a provider billing ceiling. docs/PROMPT_PREFLIGHT.md records the distinction. Promotional balance alone does not settle this guard: establish the provider input domain or explicitly review a bounded calibration/policy alternative before live repair; no verified flag or threshold was changed.

- T1.2: s2 optimizer-state peak fraction is39.8715%, below original40%; task remains unaccepted. Its baseline also already fits22GB, so later T2.1 two-round acceptance remains unresolved. Preserve these results for the requested later discussion; no threshold or fixture changes made to force a pass.

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. The initial permission denial was not bypassed. Frank subsequently stopped it; GPU availability and all T0.6 baselines were verified on 2026-10-23 at09:29–09:34 Beijing time. Evidence: reports/gpu-release.json.

- Current authorization covers only0.10USD from trial credit for minimal connectivity; two successful chats are recorded above. Full repair/evaluation spending and the original >=25USD gate remain pending. Promotional credits will be reconciled when available; their arrival does not erase the spending boundary. Bank-card top-up remains separate from an account-level hard cap. See docs/ACCOUNT_SETUP.md.

## Frank 待办

- Devpost: registration and an existing project draft were observed in the logged-in browser on 2026-10-24; final project submission remains pending.
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 ; activation code NEBIUS-DEVPOST-GLOBAL26 ($25); Builders Program https://dev.nebius.com/builders (additional $25). NEBIUS_API_KEY is now privately configured and authenticated. Confirm available credits >= $25 and full-campaign spending authorization before the original live evaluation.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.
