# Snapshot 只读定位与下一步

2026-10-30。本轮仅阅读代码及已有报告，没有模型/GPU调用、测试重跑或源码修改。按用户最新安排，先完成比赛提交，再实施和验证修复；公网 Snapshot 维持暂停。

## 确定的失败

原真实执行证据：`reports/final48h-feature-live-20261029/README.md` 与 `receipt.json`。

- s2 CLI `81149070970843cf912a127b671e00e9`：JSON/schema 通过，首因 optimizer_state 符合该合成场景，但 overall_feasibility 同时引用具体 plan IDs，触发 INVALID_EVIDENCE_DEPENDENCY。人工还发现将累计分配 16,620,584,960 bytes 当峰值；该栈实际重建峰值活跃量 557,056 bytes。不能把首因标签匹配算为完整有效诊断。
- nanoGPT CLI `5177f870aa7240b48ec2ea4e94789086`：真实响应用了 2000 completion tokens，但旧处理器未保存 finish_reason、异常细因或响应，故无法确定截断、JSON/schema 或其他 LLM 错误是哪一种；不能声称已证明截断。nanoGPT 原输入的真因未独立确定。
- Web `8fcd4570a96145ceb0244c0190d95635`：上传 202、真实模型响应已返回，但 EVIDENCE_AVAILABILITY_CONTRADICTED、NUMERICS_CHANGE_FORBIDDEN、BATCH_CHANGE_FORBIDDEN 使诊断无效，没有有效诊断卡。Web 与 nanoGPT CLI 用同一输入，不增加真值分母。
- 原 CLI 0/2；三次真实调用合计 $0.09407844 net，均已结算；没有硬件修复验证。金额是历史收据，不是本轮花费。

## 已修到哪一步

`abd5e5a4e02eb73e8e367f22d43c03f8a3586999`（已包含在当前部署）修改 snapshot_diagnosis、orchestrator 及相应测试。

- 当前 `snapshot_diagnosis.py:371–385` 将同一个 FINAL48_DIAGNOSIS_ONLY 用于消息说明和 router dispatch，消除原提示 16384 / 实发 2000 的矛盾；没有增加输出 cap 或重试。
- 当前 `snapshot_diagnosis.py:139–164,442–448` 对 LLM/响应验证异常保存私有结构化 reason、finish metadata、响应 SHA 与最多 64 KiB 摘录；公开错误仍净化。语义验证仍严格拒绝错误结果。
- `tests/test_snapshot_diagnosis.py` 已覆盖 length、malformed/schema/filter 等私有证据以及不可公开泄露；这类离线 MockTransport 是工程接线检查，不是真实模型结果。
- `reports/final-summary.md` 记载历史 140 snapshot/orchestrator focused checks 通过。本轮已核对修复 commit、当前源码及对应测试；在此次有界查找中未定位这 140 项的原始 pytest 收据，因此不把它作为本轮重新验证的数量，也不另行伪造日志。旧 75 项 feature-binding 收据等是不同且重叠的历史范围。
- 没有找到修复后的真实 CLI/Web 成功收据。请求长度和错误留存修复不等同于上述语义错误已解决。

## 最小后续方案

1. 先在独立离线 snapshot 模块改进**有证据支持的输出合同**：明确峰值活跃量和累计分配不能互换；只输出实际提供且可引用的证据；overall_feasibility 不带当前 plan IDs；保留禁止精度/batch 改动规则。在现有 2000-token 预算内使用简短原因和最小计划，不放宽 validator、不丢掉失败输出、不扩大数值结论。
2. 为上述三种已知语义错误加入针对性离线回归；使用现有安全 guard 与临时 fixture，验证 prompt/wire 同一 policy、无额外 retries、私有错误信息可定位且公开投影不泄露。已有 reader 安全合同不变，不跑第二次全量。
3. 正式调用前由可信控制器确认新的一次性 snapshot 预算绑定与可用赠款；旧三个 feature slots 已结算，不能复用为新授权。先用原 s2 输入做一次私有 CLI 复验，保留输入哈希、模型调用/费用、验证问题和 cleanup 收据；若语义无效则据新私有错误定位，不自动循环。之后再核对 nanoGPT；未确立真因时只评估有效性，不报正确率提升。
4. **公网恢复还有独立接线工作**：当前 `serve_public.py:75` 硬置 snapshot_submissions_enabled=False，且未传 snapshot_allocation_parent。现有 snapshot_routes/queue 使用独立管理器与上传目录，未接入新 public storage_admission 总存储门禁。需要先使服务端可信预算绑定、暂停/鉴权策略、上传总存储准入和清理归属于审查过的公共范围；不能仅把布尔开关改为 true，也不能让客户端选择资金池或重新使用过期/已结算 child。
5. 私有 CLI 取得有效诊断后，再用同一已知输入做一笔受控 Web 上传，核对 owner 会话、进度、有效诊断卡、未验证 patch 标记与下载、费用/cleanup；保持原“至少 1/2 真值匹配 + Web 有效卡”的验收，不将 transport 202 或账本结算算成功。Snapshot 只分析已存数据，本身不执行上传训练脚本或 GPU 复验。

此为待执行计划，不是已完成修复、资金批准或恢复公网入口的记录。
