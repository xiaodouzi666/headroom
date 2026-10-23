# Headroom Progress

Initialized: 2026-10-23T00:44:58.397951+00:00
Canonical plan: docs/PLAN.md (v4.2, preserved verbatim).
All work, caches, runs, and media remain on azuki.

## Tasks

| Task | Description | Status | Evidence |
|---|---|---|---|
| T0.1 | 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min） | 进行中 | GitHub public Apache-2.0 verified; keys and balance pending |
| T0.2 | 服务器环境勘察（P0，~30min） | 已验收 | docs/ENV.md; reports/env-preflight.json; Docker GPU ok, NET ok, 5694.85 GiB free; shared GPU and no sudo recorded |
| T0.3 | 仓库骨架与工具链（P0，~40min） | 已验收 | reports/toolchain-checks.json; reports/pre-commit-t0.3.log; commit ca6c86ad099c519b92d1ccb88219b08450aa8da6, Frank author/committer, pushed origin/main |
| T0.4 | Token Factory 探测（P0，~1h） | 离线实现完成，实测待验收 | scripts/probe_models.py; 55 guarded tests; default 62-item dry-run sends zero requests; live verification pending Nebius access |
| T0.5 | Tavily 探测（P1，~15min） | 进行中 | Probe prepared,14 offline tests; no live API calls or acceptance |
| T0.6 | 场景集 v0（P0，~2h） | 已验收 | reports/t0.6-acceptance.json; 3 synthetic CUDA OOM <7s, 5 reclaim completed20 steps with measured README peaks; pinned nanoGPT CUDA OOM11.489s; all cleanup verified |
| T1.1 | Lab 包装器：运行并抓证据（P0，~3h） | 已验收 | reports/t1.1-acceptance.json; GPU report022523 all checks true; s1 2050 events; s3 completed20 deterministic; final full regression 95 tests passed |
| T1.2 | 证据包生成（P0，~3h） | 实现完成，验收未通过 | reports/t1.2-acceptance.json; s1/s2/s4/s5 artifacts and real peak replay verified; s2 optimizer-state fraction 39.8715% < original 40% |
| T1.3 | LLM 客户端与路由（P0，~1.5h） | 离线实现完成，实测待验收 | 82 mock tests; docs/LLM.md; real Super JSON and Ultra200k pending |
| T1.4 | Diagnose（Ultra）（P0，~2.5h） | 离线准备 | Pydantic schema, prompt, runtime reference and bounded policy checks; 27 CPU/schema/SDK-contract tests; no live diagnosis |
| T1.5 | Patch（Super）与应用（P0，~2.5h） | 未开始 | — |
| T1.6 | Verify 与比较（P0，~2h） | 未开始 | — |
| T1.7 | 单轮编排 + 存储 + 事件（P0，~2h） | 未开始 | — |
| T1.8 | 报告（P0，~1.5h） | 未开始 | — |
| T1.9 | 真实仓库：nanoGPT（P0，~2h） | 未开始 | — |
| T1.10 | Honesty 与安全（P0，~1h） | 未开始 | — |
| T1.11 | Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h） | 未开始 | — |
| T1.12 | MVP 整体验收 + 报告（P0，~1.5h，10/24 晚） | 未开始 | — |
| T2.1 | 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h） | 未开始 | — |
| T2.2 | Tavily Research（P0，~2h） | 未开始 | — |
| T2.3 | Nano 栈标注（P1，~1h） | 未开始 | — |
| T2.4 | 预算守卫与成本面板（P0，~45min） | 未开始 | — |
| T2.5 | HF Transformers 场景（P1，~2h） | 未开始 | — |
| T2.6 | Watch 模式（P2，~1.5h） | 未开始 | — |
| T2.7 | Docker/HF 缓存稳健性（P1）：验收：三个场景在 Docker 路径下结果与子进程路径一致（峰值差 ≤ 1%）。 | 未开始 | — |
| T2.8 | 小评测 + 自优化（P0，可夜间自治，~4h） | 未开始 | — |
| T3.1 | FastAPI + SSE（P0，~3h） | 未开始 | — |
| T3.2 | 前端素版（P0，~4h） | 未开始 | — |
| T3.3 | Replay（P0，~1.5h） | 未开始 | — |
| T3.4 | Claude Design 对齐（P1，~3h；设计稿 10/25–10/26 由 Frank+Claude 产出到 `design/`） | 未开始 | — |
| T3.5 | 公网部署、限流、监控（P0，~2.5h；Frank 提供域名/Cloudflare） | 未开始 | — |
| T3.6 | 预录素材（P0，~1h） | 未开始 | — |
| T4.1 | 评测集定稿 | 未开始 | — |
| T4.2 | 主评测 | 未开始 | — |
| T4.3 | 消融 | 未开始 | — |
| T4.4 | 冻结 | 未开始 | — |
| T5.1 | README | 未开始 | — |
| T5.2 | docs 定稿 | 未开始 | — |
| T5.3 | Devpost 描述 | 未开始 | — |
| T5.4 | 视频 | 未开始 | — |
| T5.5 | 首次完整提交 | 未开始 | — |
| T5.6 | 评委视角自检 | 未开始 | — |
| T5.7 | 最终提交 | 未开始 | — |
| Phase 6 | Weekly health/alerts; balance by Nov 25; manual Dec 1 and Dec 8 access | 未开始 | Future dated acceptance |

## Acceptance log

- 2026-10-24 offline continuation completed: reports/api-prep-20261023T222659Z.json records 259 passed in53.97s, Ruff and formatting passed, and the default model-probe dry-run planned62 operations with network_requests=0 and accepted=false. New coverage includes55 guarded probe tests,82 LLM client/router/cost tests,25 diagnosis checks and2 SDK/schema/evidence integration tests. Full prior tests remain green; historical runs are preserved. Original PLAN SHA remains e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.
- Independent review fixed native-versus-fenced JSON classification, retry dispatch after a shared budget violation, absolute streaming deadlines, nonfinite JSON, malformed SDK responses missing accounting, and response model identity. Missing or mismatched identity cannot become accepted capability/diagnosis; uncertain billing stays unknown and model probes halt further paid dispatch. T0.4/T1.3/T1.4 remain unaccepted pending real model calls.
- Test-isolation incident retained: an earlier AsyncClient refactor round attempted three official-endpoint transports using only a fixed dummy credential; exact network outcomes are unknown. No real key or .env was used by those tests. Corrected mocks and independent DNS/socket-denial guards passed, including separate reviewer checks. See docs/MODELS.md; do not describe the whole development turn as zero network.
- Latest credential presence check: server .env is0600; Tavily and Nebius values remain empty. Hidden-input Tavily importer syntax validated. No authenticated model/search probe was run; the Tavily four-operation live check remains pending import, and Nebius registration/credit troubleshooting remains deferred at Frank's request.

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

- T1.2: s2 optimizer-state peak fraction is39.8715%, below original40%; task remains unaccepted. Its baseline also already fits22GB, so later T2.1 two-round acceptance remains unresolved. Preserve these results for the requested later discussion; no threshold or fixture changes made to force a pass.

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. The initial permission denial was not bypassed. Frank subsequently stopped it; GPU availability and all T0.6 baselines were verified on 2026-10-23 at09:29–09:34 Beijing time. Evidence: reports/gpu-release.json.

- No paid API calls will run before available promotional credits and spending boundary are confirmed. Current official Token Factory billing documentation requires a bank card and allows negative balances/automatic charges; no account-level hard spending cap was verified. See docs/ACCOUNT_SETUP.md. Frank reports registration complete; Tavily free-plan limits were verified, while the Nebius key and promotional credits remain unverified and its issue is deferred at his request.

## Frank 待办

- Devpost: registration and an existing project draft were observed in the logged-in browser on 2026-10-24; final project submission remains pending.
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 ; activation code NEBIUS-DEVPOST-GLOBAL26 ($25); Builders Program https://dev.nebius.com/builders (additional $25). Provide NEBIUS_API_KEY in server .env and confirm available credits >= $25.
- Tavily: account and free plan verified on 2026-10-24; import the existing default key into server .env using the hidden-input importer. No new account is needed.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.
