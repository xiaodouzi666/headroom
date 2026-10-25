# 新版九场景独立验收摘要（2026-10-25）

本次独立结论是 **目标 1/9、有效且正确首因 6/9**。原要求仍为固定九个场景、至少六个目标达标；目标门未通过，不进入 Phase 2。此次是新运行的独立成绩，不与历史 v7 的 1/9 合并，也不重算旧记录。

## 来源与完整性

- 正式 campaign：`runs/evaluation/live/20261025T083415856928Z-b5f2e084/campaign.json`，九行均有独立真实 run ID；状态 finished，整个调度用时 436.8342552690301 秒，CLI 总退出码 1。
- 执行提交：`ce38d3c67d8990f25c810fb85f7bab448cfdda10`。
- 冻结审计程序：`audit_mvp_v2.py`，SHA256 `09fa339c212966c8a0dca7a619689f6b51e1adedbd063dba73f05aa9a8323129`。
- 独立机器收据：[公开机器收据](independent-audit-public.json)，SHA256 `9c66be84c80c78227eeb8be2e19488675759ba35d26fe9b76df492d55c97f724`。
- 完整测试前、测试后、运行审阅与审计时的 **288 项源码库存逐项相同**。测试 HEAD 与执行 HEAD 的差异已明确记录为源码相同的测试后提交，未以部分关键文件代替完整库存。
- 原始机器收据字节与上述 SHA 保留在服务器。公开副本仅把 source_hashes 映射改为 path/sha256 数组，以免源码校验和被扫描器误认作 API key；已验证可无损还原全部数据，未修改审计结论或放宽扫描规则。
- 九条真实 installed CLI 的 argv、Store request、源与应用结果链全部可核；退出码为 **一个 0、八个 78**，因此“九条 CLI 均退出 0”的原单项仍未通过。其余每行的来源、费用、清理和 480 秒时限证据完整。
- 审计前后账本与 Store 稳定；`errors=[]`、`changed_artifacts=[]`。未额外运行模型、GPU、补丁或历史重放。

## 固定分母结果

| 场景 | 目标 | 有效且正确首因 | 真实 CLI 退出码 |
|---|---|---|---:|
| s1_batch_too_big | 未达标 | 通过 | 78 |
| s2_capacity_v2 | 未达标 | 通过 | 78 |
| s3_eval_no_grad_missing | 达标 | 通过 | 0 |
| s4_loss_accumulation_graph | 未达标 | 通过 | 78 |
| s5_fragmentation_varlen | 未达标 | unknown | 78 |
| s6_full_vocab_logits_fp32 | 未达标 | 未通过有效性门 | 78 |
| s7_frozen_params_optimizer_state | 未达标 | 通过 | 78 |
| s8_two_models_resident | 未达标 | 通过 | 78 |
| nanogpt | 未达标 | unknown | 78 |

原始 campaign 汇总中的“首因匹配 7”只反映分类标签匹配，不能直接作为有效诊断成绩。s6 的首份诊断虽然分类匹配，但包含被 strict policy 拒绝的精度方案，原始 `rounds/01/diagnosis.json` 的 `valid=false`、错误为 `NUMERICS_CHANGE_FORBIDDEN`。独立审计因此只计六个有效正确首因。s5 与 nanoGPT 的 ground truth 未经验证，继续保留 unknown，未从九个分母中移除。

## 费用与赠送池

本轮共 **27 个模型 attempt**：

| 项目 | USD |
|---|---:|
| 有已知实际 token 用量的费用小计 | 0.62027986 |
| 9 个未知实际费用 attempt 的保留上界 | 0.00440220 |
| 本轮保守记账总额 | 0.62468206 |
| 同一账本历史至今已知实际费用小计 | 5.765111776 |
| 历史至今未知实际费用保留额 | 0.03605460 |
| 同一账本历史至今保守记账总额 | 5.801166376 |
| 原累计授权池上限 | 9.99964904 |
| 当前池剩余可分配额 | **4.198482664** |

本轮及全账本均无 pending/unresolved attempt。实际总费用仍是 unknown；不能把上述已知小计写成实际总额，也不能将未知部分记为零。全体旧账本行、既有外部探测保守总额 1.82224246（其中未知保留 1.049344）完整保留，没有释放额度、建立新池或充值。这些是 token 预算记账与保留证据，不是银行卡扣款凭证。

## 已定位的失败边界

八个未通过场景最终均停在 `diagnosis_needs_more_info`，不等于八个场景都缺少同一种证据。

- s1 首轮候选真实完成了 20 次 optimizer update，峰值降到约 17.112 GB，但每个 microbatch mean loss 未按累积次数缩放，20 次更新对应 160 条 backward scalar，未通过数值契约。之后模型关于“start 未定义、optimizer.step 在内层”的解释与实际候选不符，不能照收为事实。
- s2 请求中的源码、seed argv 和 source SHA 都完整。模型声称第 116–121 行被遮挡，但真实 HTTP 请求的存储副本中可以读到完整尺寸赋值、AdamW foreach=True 与 inputs/targets。另一方面，受信的 named-tensor runtime observation 对 s2 确实是 unsupported；不能将源程序 stdout 自报的尺寸冒充独立运行观测。模型把梯度累积所需的前提用于阻塞当前仅切换 foreach 的计划，属于需要进一步修复和验证的计划依赖解释问题。

本收据只认证这一轮已观察到的结果；其他原单项、Phase 2、library、HF、BF16/Pareto 和比赛提交要求仍须独立验收。没有因已有离线测试或资源校准通过而把这些项目写成完成。
