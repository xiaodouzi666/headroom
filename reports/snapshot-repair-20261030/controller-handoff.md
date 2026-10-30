# 一次性 s2 Snapshot retry 控制脚本交接

脚本：execute-s2-retry.py.txt。只用于已准备并审核的 s2 proposal，不更改业务源码、原 receipt/profile/额度或 F3b 历史。没有自动重试。

已按根代理提供的信息执行一次**只读文件验证**：
- run_id：afa13b5096eb4194a805df299d7d7f93
- proposal digest：6677f49cb791e9a2c4b6920edf97ebb918118bda7767bed1d9fad94691fcf534
- 结果：file-validation-only；claim_created=false；registry_or_runtime_checked=false；model_calls=0；gpu_jobs=0。
- 此验证不证明 proposal 当前账务/源码状态仍新鲜；真正 claim 时 snapshot_retry 会事务重算并拒绝陈旧 proposal。

## 执行前审阅

默认不带 --execute 时只读取指定的私密 JSON、检查 mode 0600/owner/大小/路径、验证 proposal digest 与请求 schema；不 claim、不读取账本、不调用模型。只有根代理独立审阅脚本后，可显式执行：

    .venv/bin/python reports/snapshot-repair-20261030/execute-s2-retry.py.txt \
      --proposal .cache/snapshot-repair-20261030/afa13b5096eb4194a805df299d7d7f93-proposal.json \
      --expected-sha256 6677f49cb791e9a2c4b6920edf97ebb918118bda7767bed1d9fad94691fcf534 \
      --execute

本交接未运行上面的执行命令。使用现有真实凭据环境；若当前 HEADROOM_BUDGET_DB_PATH 指向不同池会先拒绝，不偷偷切换。根代理应保持本次审核源码冻结并避免同池并发任务；claim 自身会检查完整原 scope、剩余额度、原输入、源码、UTC 日期及共享账本状态。

## 真实执行与安全边界

1. 固定新 run_id 独占创建 once 目录。已有目录或结果时拒绝，不覆盖、不删除、不重启同次尝试。
2. 调用 claim_snapshot_retry，随后将完整 binding 与 request 以 mode 0600、exclusive create、fsync 保存到 .cache/snapshot-repair-20261030/<run_id>/，成功落盘后才 spawn。
3. 子进程只调用正常 run_snapshot_diagnosis，并传 SnapshotServices(budget_factory=snapshot_retry_budget_factory(binding))。没有 runtime_factory、patch_factory 或模型响应注入；不执行上传源码，不发起 GPU Lab。
4. 子进程独立 session，父进程死亡信号终止其整个 group；公开接口同款 no_new_privs、128 MiB FSIZE、2 GiB 地址空间、60 CPU 秒边界。总运行截止 480 秒。512 MiB/4096 项输出监督不是硬目录 quota；进程输出只保存在 0600 worker.log，异常只公开类型，不打印原始消息/密钥。
5. 工作流返回后子进程刻意等待 supervisor 清理。父进程杀本次拥有的 group 并等待退出/检查 /proc。因此成功返回也可能记录 process_exit_code=-9；必须与 worker_returned、status、execution_terminal 和 cleanup 联合阅读，不能据 -9 单独认定模型失败，也不能忽略无返回的 -9。
6. 分别记录进程组清理与 snapshot_cleanup_verified，再将真实事实传给 finish_snapshot_retry。超时、异常、输出异常、清理不明或未知费用保留 blocked/未结清，不重试。finisher 自身失败时不手改 registry，保留现有 claim，summary 明确 settlement_recorded=false、费用 unknown。
7. 功能结果与财务结算分开：诊断可能 failed/needs_human，但已知费用与清理均真实结清时，finisher 可返回 settled；这不是成功修复。已知实际费用不会被伪造为 unknown，未知也不会写成 0。
8. 完整真实 tokenizer/runtime 在 2 GiB 限制下是否足够仍需本次执行观察，summary 记录 peak_rss_kib；本次准备不声称已验证。

## 产物

- 私密：.cache/snapshot-repair-20261030/<run_id>/{once,binding,request,dispatch-once,outcome,settlement,controller-summary}.json 与 worker.log。
- 实际诊断产物：runs/uploads/<run_id>/，保留 public-report、diagnosis、private validation/error/usage/cleanup。
- 可公开的最小 controller summary：reports/snapshot-repair-20261030/<run_id>-controller-summary.json。只有运行结果状态、run ID、proposal digest、资源与结算事实，不复制完整 binding 或原始日志。
- 父进程自身 SIGKILL/主机失效无法保证 finally 执行；子进程 parent-death 保护仍终止执行，原 claim/once marker 保留，后续应人工核对现有尝试，不能删 marker 后重跑。

准备阶段仅完成 compile、Ruff check/format、只读文件验证，未执行子进程/claim/模型/GPU。脚本将交由根代理独立代码审阅与实际执行。
