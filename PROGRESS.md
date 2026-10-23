# Headroom Progress

Initialized: 2026-10-23T00:44:58.397951+00:00
Canonical plan: docs/PLAN.md (v4.2, preserved verbatim).
All work, caches, runs, and media remain on azuki.

## Tasks

| Task | Description | Status | Evidence |
|---|---|---|---|
| T0.1 | 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min） | 进行中 | GitHub public Apache-2.0 verified; keys and balance pending |
| T0.2 | 服务器环境勘察（P0，~30min） | 已验收 | docs/ENV.md; reports/env-preflight.json; Docker GPU ok, NET ok, 5694.85 GiB free; shared GPU and no sudo recorded |
| T0.3 | 仓库骨架与工具链（P0，~40min） | 进行中 | Server-local uv and verified gitleaks binary; torch 2.5.1+cu124 installed; final CUDA/snapshot/lint checks running |
| T0.4 | Token Factory 探测（P0，~1h） | 未开始 | — |
| T0.5 | Tavily 探测（P1，~15min） | 未开始 | — |
| T0.6 | 场景集 v0（P0，~2h） | 未开始 | — |
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

- T0.2: `python3 scripts/inspect_env.py` exit 0. All checks retain original stdout/stderr/exit code. DOCKER_GPU=ok; NET=ok; disk=5694.85 GiB. Existing other compute process is noted. sudo requires password; uv/gitleaks not initially installed.
- T0.1: public https://github.com/xiaodouzi666/headroom created with Apache-2.0; server .env initialized with empty keys, permissions 600, gitignored. PLAN SHA-256 matches attachment e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.

- Bootstrap: SSH verified; project did not exist; git identity is already configured; gh authenticated as xiaodouzi666; repository did not exist.

## 待 Frank 决策

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. GPU remains occupied (20618 MiB process, 3429 MiB free). Owner/admin action is required; no permission bypass attempted. Evidence: reports/gpu-release.json.

- No paid API calls will run before available promotional credits and spending boundary are confirmed.

## Frank 待办

- Devpost: register/sign in and Join Hackathon: https://nebiusglobalaihackathon.devpost.com/
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 ; activation code NEBIUS-DEVPOST-GLOBAL26 ($25); Builders Program https://dev.nebius.com/builders (additional $25). Provide NEBIUS_API_KEY in server .env and confirm available credits >= $25.
- Tavily: https://tavily.com ; provide TAVILY_API_KEY in server .env.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.
