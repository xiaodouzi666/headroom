# Headroom Phase 0 interim status — 2026-10-23

Phase 0 is NOT complete. This is a handoff of verified preparation and unresolved prerequisites.

## Verified

- T0.2 environment preflight accepted: Ubuntu 24.04.4, RTX 3090 Ti, Docker GPU support, network access and sufficient disk.
- T0.3 toolchain accepted: torch 2.5.1+cu124 recognizes the GPU; allocator snapshot contains segments and device traces; pre-commit checks pass; .env is ignored and mode 600; initial commit ca6c86ad099c519b92d1ccb88219b08450aa8da6 uses the existing Frank identity and was pushed to https://github.com/xiaodouzi666/headroom .
- T0.6 source preparation: eight standalone scenarios and READMEs; each completed 20 tiny CPU steps in a network-disabled, unprivileged Docker container with source mounted read-only and without API secrets. All stdout/stderr and source hashes are preserved in reports/.
- nanoGPT is pinned at 3adf61e154c3fe3fca428ad6bc3818b27a3b8291; deterministic synthetic inputs prepared; an isolated tiny CPU run exited 0. Its upstream max_iters=20 includes iterations 0 through 20.

## Unresolved

- No Token Factory account/key or credited balance has been provided. No live Token Factory or Tavily calls have run. The account guide is docs/ACCOUNT_SETUP.md. The current official billing page requires a bank card and permits negative balances with automatic charging; promotional credit is not verified as a hard spending cap.
- Frank authorized stopping the existing llama-server. Fresh identity verification found PID 398152 owned by chenchunlai. A normal SIGTERM failed with PermissionError; no permission bypass was attempted. Latest check still shows about 20.6 GiB used and 3.4 GiB free. The owner or an administrator must stop that process before a controlled full GPU baseline can run.
- All full-size GPU peaks/OOM sites/times remain unmeasured. No nanoGPT OOM traceback, repair success, numerical-equivalence result, model capability result or benchmark result is claimed.
- Frank explicitly retains the original plan and defers proposed acceptance changes for later discussion. docs/PLAN.md remains byte-identical to the original (SHA-256 e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56). No proposed acceptance revision was applied.

## Resume steps

1. Frank sets up Token Factory and Tavily, stores keys only in the remote .env, confirms actual available credit and the permitted spending boundary.
2. The llama-server owner or administrator releases the GPU. Recheck live GPU/process status before any full baseline run.
3. Complete the original T0.1/T0.4/T0.5 and T0.6 acceptance checks before advancing to Phase 1. Do not treat CPU smoke as GPU acceptance.

All source, dependencies, model/data caches and test artifacts remain on azuki. Only this text report may be copied to the Mac.

---

# Results

No automated repair or benchmark result has been measured. Phase 0 is incomplete.

## Preparation checks (not benchmark results)

| Check | Observed outcome | Limit |
|---|---|---|
| CUDA toolchain | torch 2.5.1+cu124 recognizes 3090 Ti; snapshot API returns traces | Small allocation only |
| Synthetic scenarios | 8/8 CPU tiny checks completed 20 steps | No full GPU calibration |
| nanoGPT | Pinned upstream source + deterministic random input; tiny CPU run exit 0 | No GPU OOM reproduction |
| Live model/Tavily calls | None | Account, keys, credits and spending boundary pending |

## CPU source smoke evidence

| Scenario | Steps | Process exit | Wall seconds |
|---|---:|---:|---:|
| s1_batch_too_big | 20 | 0 | 4.047 |
| s2_fp32_adamw_1b | 20 | 0 | 4.034 |
| s3_eval_no_grad_missing | 20 | 0 | 4.046 |
| s4_loss_accumulation_graph | 20 | 0 | 3.997 |
| s5_fragmentation_varlen | 20 | 0 | 4.047 |
| s6_full_vocab_logits_fp32 | 20 | 0 | 4.002 |
| s7_frozen_params_optimizer_state | 20 | 0 | 4.047 |
| s8_two_models_resident | 20 | 0 | 4.02 |

These wall times include container startup and are not training throughput measurements. Sources and commands are in reports/scenario-cpu-smoke-summary.json and its referenced logs. CPU tiny changes model dimensions for plumbing checks only; those runs are not submitted as memory optimization results.

The pinned nanoGPT smoke retains vocabulary 50304 but uses tiny depth/width/sequence/batch to check loading and training in isolation. GPU acceptance uses the separate unmodified baseline configuration in repos/nanogpt.yaml.

---

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
| T0.4 | Token Factory 探测（P0，~1h） | 未开始 | — |
| T0.5 | Tavily 探测（P1，~15min） | 未开始 | — |
| T0.6 | 场景集 v0（P0，~2h） | 进行中 | 8 sources and READMEs ready; 8/8 Docker CPU tiny tests completed 20 steps; nanoGPT pinned and CPU smoke passed; full GPU calibration awaits free GPU |
| T1.1 | Lab 包装器：运行并抓证据（P0，~3h） | 未开始 | — |
| T1.2 | 证据包生成（P0，~3h） | 未开始 | — |
| T1.3 | LLM 客户端与路由（P0，~1.5h） | 未开始 | — |
| T1.4 | Diagnose（Ultra）（P0，~2.5h） | 未开始 | — |
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

- T0.6 partial only: eight source fixtures + README + INDEX prepared. `uv run python scripts/check_scenario_smoke.py` (two four-case batches) completed 20 CPU tiny steps in all 8 cases; evidence reports/scenario-cpu-smoke-summary.json and per-batch logs. This is not GPU baseline acceptance. nanoGPT pinned at 3adf61e154c3fe3fca428ad6bc3818b27a3b8291, deterministic synthetic inputs prepared, original upstream CPU tiny run exit 0 (upstream max_iters=20 emits iterations 0 through 20). No full-size GPU OOM traceback, peak measurement, live model call or repair result is claimed.

- T0.3: `uv run python scripts/verify_toolchain.py` exit 0: torch 2.5.1+cu124, CUDA True, NVIDIA GeForce RTX 3090 Ti; snapshot True True; .env ignored and mode 600. `uv run pre-commit run --all-files`: all three hooks Passed. `gitleaks detect` and staged scan: 0 findings. Commit ca6c86ad099c519b92d1ccb88219b08450aa8da6 author and committer both match existing Frank identity; push origin/main succeeded.

- T0.2: `python3 scripts/inspect_env.py` exit 0. All checks retain original stdout/stderr/exit code. DOCKER_GPU=ok; NET=ok; disk=5694.85 GiB. Existing other compute process is noted. sudo requires password; uv/gitleaks not initially installed.
- T0.1: public https://github.com/xiaodouzi666/headroom created with Apache-2.0; server .env initialized with empty keys, permissions 600, gitignored. PLAN SHA-256 matches attachment e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.

- Bootstrap: SSH verified; project did not exist; git identity is already configured; gh authenticated as xiaodouzi666; repository did not exist.

## 待 Frank 决策

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. GPU remains occupied (20618 MiB process, 3429 MiB free). Owner/admin action is required; no permission bypass attempted. Evidence: reports/gpu-release.json.

- No paid API calls will run before available promotional credits and spending boundary are confirmed. Current official Token Factory billing documentation requires a bank card and allows negative balances/automatic charges; no account-level hard spending cap was verified. See docs/ACCOUNT_SETUP.md. Frank does not currently have a Token Factory account/key.

## Frank 待办

- Devpost: register/sign in and Join Hackathon: https://nebiusglobalaihackathon.devpost.com/
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 ; activation code NEBIUS-DEVPOST-GLOBAL26 ($25); Builders Program https://dev.nebius.com/builders (additional $25). Provide NEBIUS_API_KEY in server .env and confirm available credits >= $25.
- Tavily: https://tavily.com ; provide TAVILY_API_KEY in server .env.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.

---

# Account setup and outstanding access

Checked 2026-10-23. This documents account requirements; no account or billing setup was performed.

Headroom requires real NVIDIA-model runtime calls through Nebius Token Factory. Its remaining code can run on azuki; an AI Cloud GPU rental is not required. Source: https://nebiusglobalaihackathon.devpost.com/details/faqs

1. Sign in to https://tokenfactory.nebius.com using Google or GitHub.
2. The current billing documentation requires a billing account and bank card during onboarding. It supports negative balances and automatic card charging. We have not confirmed an account-level hard spending cap. Do not assume promotional credits enforce a zero-overspend limit. Source: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new
3. Apply for the hackathon promotional credits via https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 . NEBIUS-DEVPOST-GLOBAL26 is the application activation code; it is not confirmed as a directly redeemable billing code. Check actual received credits in the console.
4. Optional additional Token Factory credit: https://dev.nebius.com/builders . Its terms specify a 90-day validity from issuance: https://nebius.com/builders-terms-and-conditions . The separate hackathon credit expiration has not been verified.
5. Create an API key in the Token Factory console. Store only in server .env (mode 600), not chat, source or reports. Source: https://docs.tokenfactory.nebius.com/api-reference/introduction
6. Obtain a Tavily key at https://tavily.com and store in the same .env file. No secret values belong in this document.

T0.1 remains incomplete until the credentials are verified and Frank confirms at least $25 credit. Live probes remain paused pending a confirmed spending boundary. No API usage or account setup has been performed here. If billing/country/credits block signup, the official FAQ directs participants to Nebius support: https://discord.com/invite/eXYTGhgnhK .
