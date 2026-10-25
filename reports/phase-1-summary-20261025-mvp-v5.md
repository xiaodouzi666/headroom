# Phase 1 — MVP v5（额外修复第 1/3 轮）

原 MVP 未通过。九场景已完整执行，目标 0/9；首因类别匹配 7/9（2 未知），保留旧审计器 diagnosis.valid 条件后为 6 真、1 假、2 未知。未将部分显存改善、组件验证或 worker 退出 0 算作整体通过。

执行源码 d6f29945eaffe2c56a2969d85f23fdfe06f03aa7；campaign 为 runs/evaluation/live/20261025T022454741538Z-8e6e085d/campaign.json。2026-10-25 02:24:53–02:36:26 UTC，共692.93秒。原 PLAN 与九场景 manifest 未修改；额外三轮已使用一轮。

| 场景 | 首因（含有效性门） | 有静态应用候选 | 最终保留轮 | 目标 | 保守费用 USD | 秒 |
|---|---|---|---|---|---|---|
| s1_batch_too_big | 正确 | 是 | 无 | 未达标 | 0.12525164 | 114.69 |
| s2_fp32_adamw_1b | 正确 | 否 | 无 | 未达标 | 0.04753906 | 44.24 |
| s3_eval_no_grad_missing | 正确 | 是 | 无 | 未达标 | 0.09023786 | 56.42 |
| s4_loss_accumulation_graph | 正确 | 是 | 无 | 未达标 | 0.15481084 | 145.27 |
| s5_fragmentation_varlen | 未知 | 否 | 无 | 未达标 | 0.09600868 | 64.39 |
| s6_full_vocab_logits_fp32 | 未通过有效性门 | 否 | 无 | 未达标 | 0.0336181 | 19.17 |
| s7_frozen_params_optimizer_state | 正确 | 是 | 无 | 未达标 | 0.11522816 | 93.94 |
| s8_two_models_resident | 正确 | 是 | 无 | 未达标 | 0.10851474 | 80.74 |
| nanogpt | 未知 | 是 | 无 | 未达标 | 0.12575908 | 72.97 |

52次补丁尝试中，17次真实应用并编译成功、31次精确源码片段匹配拒绝、4次模型响应拒绝。17条应用链的原始响应、源哈希、生成diff、实际位置和候选字节均独立核验；4条缺失有效响应链保留unknown。5/8合成场景出现过合格静态应用，仍低于T1.5的6/8。每次Super输出均不超过4,000 tokens。

## 失败证据与下一轮调整

1. 模型抄写old_lines时改变引号、遗漏调用参数，host正确拒绝。下一轮用明确源码行ID选择范围，由host获取原字节，保留source SHA、严格位置及候选字节检查。
2. 编译成功不代表运行正确。s1两个候选仍OOM；s3把评估batch当训练batch，产生空微批与NaN；s8有被后续赋值覆盖的无效修改，以及被参数量门拒绝的对象删除。下一轮要求诊断/补丁先核对真实producer、consumer、训练/评估路径和有效batch，优先处理实际异常。
3. s4六轮同一补丁去掉retain_graph，均完成20步，峰值24.768717824→2.533996544 GB（下降89.769367%）。但参考batch1、候选batch8，same_inputs/effective_batch=false，原scalar-loss门仍拒绝。差异不能证明补丁改变同工作负载的数学行为，也不能据此改记通过。原阈值不变，重复同一候选没有形成新的探索。

## CLI与验收边界

这轮调用评测worker；9个worker退出0不等于实际headroom fix CLI退出0，原CLI项仍未观测。下一轮已在服务器隔离树实现真实安装console script的同PID exec，待整合与全套回归；保留同一UUID/Store/预算/480秒截止时间，且只执行一次run_fix。非零CLI状态不得改为0。

原T1.6、nanoGPT T1.9、最终选中补丁重应用及后续Phase 2/4接受门均未因本轮静态改善被判通过。2,134项guarded回归通过，Ruff/格式/diff检查及历史/暂存gitleaks零发现，固定源码收据保留在reports/anchored-patch-integration-20261025/。

## 费用与模型体验

98次真实调用的全调用已知费用小计$0.89236424，另有$0.00460392经验证的严格上界，保守总额$0.89696816；actual总额仍为null。campaign.summary.known_cost_usd=0只表示没有费用完全已知的整run，并不表示免费调用。9个run均低于$0.6与480秒，无pending、unresolved或halt。

本轮后共享runtime账本397次尝试均settled、56个run均closed；累计已知$3.948962832、保守$3.975401832，原$9.99964904池剩余$6.024247208。不充值、不增加分配。v5前通用组件单次调用$0.00054已包含账本，不能计入九场景成功率。

Ultra实际已获得相关源码，失败不能笼统归因于缺少源码；后续强调源码前提和失败优先级。Super新协议减少了旧diff传输问题，但逐字抄写与语义理解仍有失败。Nano费用中无法确定实际缓存用量的部分继续记严格上界；所有未知保留。先前长输入探测及失败证据见phase-1-summary-20261025-mvp-v4.md，本轮未重跑或改写。

## 继续执行

按用户已授权的额外最多三轮，继续整合第二轮v6：源码范围ID、诊断/补丁前提核对和真实CLI接线。保持原九场景、目标、数值/参数量门和费用边界；不删除旧runs，不把补充证据替代原验收。最终视频、Devpost提交及需要用户资源的部署事项仍按原计划处理。

审计依据：reports/live-campaign-20261025/mvp-v5-audit-v2.json、mvp-v5-anchored-review.json、mvp-v5-cli-exit-semantics.json、mvp-v5-audit-notes.json。
