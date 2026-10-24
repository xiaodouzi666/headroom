# CLI 退出码与评测 worker 的验收边界

原 `docs/PLAN.md:285–287` 要求 8 个合成场景和 nanoGPT 各跑 `headroom fix`，9 个 run 都退出 0 并生成报告。T1.7 还要求真实 CLI 时间线和命令退出证据。

当前 `headroom/cli.py:243–248` 的规则：`completed` → 0；`needs_human` / `budget_exceeded` → 78；`timeout` → 124；其他状态 → 1。`target_met` 是独立门，工作流 `completed` 且目标未达标仍映射为 CLI 0，不能当作修复成功。

`evaluation_worker.py:67–84` 直接调用 `run_fix` 并保存结果，没有经过 CLI 的 Typer 返回分支；捕获异常并写入失败状态后也可能正常返回。因此 `evaluation_timing.worker_exit_code=0` 仅证明 worker 正常退出，不证明真实 `headroom fix` 命令退出 0。`headroom eval` 自身退出码、报告/回放命令退出码同样不能替代。

只读辅助脚本 `.cache/setup/audit_cli_exit_semantics_v1.py` 固定经过审阅的 CLI 文件 SHA，并核对映射 AST。它核对 campaign、report 顶层与 run、原 worker-result、Store 列与 data 的身份/状态一致性，再推导 `expected_fix_exit_code`。缺失、冲突或源代码改变时不生成可用的 0。它始终输出 `literal_fix_exit_code=null` 和 `invocation_observed=false`；即使推导全为 0，也不会把正式 CLI 门设置为通过。

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  .cache/setup/audit_cli_exit_semantics_v1.py \
  --campaign runs/evaluation/live/20261024T225604279740Z-1a7d57a8/campaign.json
```

脚本只向 stdout 输出 JSON，不写旧 run；拒绝 `.env`、GPU 设备、网络/DNS、外部进程及文件写入，只接受 `mode=ro` SQLite。它不能运行模型、执行补丁或补造命令历史。脚本退出 0 仅代表只读证据完整且预计映射全为 0，仍不代表实际 CLI 验收；其他情况退出 2。实际 CLI 入口、参数/YAML/仓库准备、终端事件及 shell 退出码仍需独立证据。

v3 真实结果六处状态来源一致。9 个 worker 均退出 0，但预计 `fix` 退出码为 `[78,78,78,0,78,78,78,78,78]`；只有 s4 的工作流状态为 `completed`，而其 `target_met=false`。补充审计退出 2，预计 CLI 条件失败；实际 CLI 调用未观察。旧 auditor 和原失败记录未改。

证据：
- [v3 补充审计](mvp-v3-cli-exit-semantics.json)
- [脚本验证收据](cli-exit-semantics-driver-receipt.json)：11 项离线测试通过。
- [原 v3 审计](mvp-v3-audit-v2.json)：固定 9 分母，仍未通过。

v4 沿用原 9 场景执行。结束后可对同一批结果复用补充审计，无须为推导退出码增加模型调用。如果目标/首因等门达到但 literal CLI 仍未观察，正式原计划验收继续标为待补证；不能把 worker 退出 0 改名为 CLI 退出 0。
