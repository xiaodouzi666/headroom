# 提交后的剩余要求盘点 — 2026-10-30

本次只读核对原 `docs/PLAN.md`、后续替代范围 `docs/FINAL_48H.md`、当前台账及实际保存产物。没有新的 provider/GPU 调用、评分、资金或部署操作。Snapshot 与 R8 正在独立推进，本文不预填其结果。历史审核文件不覆盖。

## 已完成的外部交付

F7 已有 Devpost **Submitted 5/5** 的真实界面证据：[正式项目](https://devpost.com/software/headroom-8vfuwj)、[Public 视频](https://www.youtube.com/watch?v=aaXF60LryWI)。来源为 `reports/submission-final-review-20261030/`。Frank 已确认手机移动网络首页三秒内打开；这是用户观察，不是所有网络的性能保证。视频与正式提交不再列为外部阻塞。

## 除 Snapshot / R8 之外的具体剩余项

| 项目 | 当前证据与未完成边界 | 最少下一步 / 类型 |
|---|---|---|
| T2.2 Tavily Sources | 工具、真实模型 tool call、Search/Extract、版本化来源、24小时缓存已实现。s1 **已有可复用合格历史**：`runs/evaluation/live/20261025T121115251021Z-2fe7da84/jobs/d52ca1fc2f394a92b6c82918b25d8a43/report.json` 的 Sources 含 PyTorch 2.5 checkpoint（version_match=true）；run.research 为 completed/model_tool_calls，实际 search 1 call/1 credit，extract cache_hit=true、api_calls=0、credits_used=0。R5 亦有 2.5 checkpoint。s5 仍未找到规定的 CUDA memory 文档来源；历史 s5 仅一轮含两个 issue，其余所核报告及 R7 Sources 为空。 | **集成实测待补，不是缺整个模块。** 复用 s1 与缓存收据；只有实际 s5 修复所采用 API/flag 触发研究、来源注入 Patch 并进入报告，才关闭剩余项。不能手工补 URL 假装被调用。 |
| T2.3 Nano ≥80% | R7 的八个 `annotations.json` 实际为 **5/8 完整**，不是旧盘点的4/8；s2/s5/s6 为 missing_duplicate_or_unrecognized_stack。完成的 s1/s3/s4/s7/s8 与已知启发式类别一致率分别 37.5%、15.3846%、20%、0%、27.2727%，均未达80%。这些是启发式一致率，不是独立真值准确率。 | **实现已有、质量验收失败。** 可先无费用审查实际响应的ID集合错误/现有schema约束，再做小范围离线改进；新的质量结论仍需独立真实八场景覆盖，费用≤0.02/run，不泄露启发式答案给模型来凑指标。 |
| T2.8 20-cell / 75% | 当前 `eval/protocol_v2.json#/scopes/phase2_policy_matrix` 固定10例×strict/allow_precision=20；没有已完成矩阵及两项75%目标的真实收据。F1 27次仅诊断、R7 12项和R8 fixed-nine都不能替代。当前 manifest 的s5、nanoGPT、HF真值unverified，因此即使20项执行完，已知正确首因最多14/20=70%；完整准确率仍unknown。 | **真实评测与真值证据缺口。** 先独立裁定是否存在可证实真值，保留旧unknown与历史，不以模型答案标真值、不更改分母。完整矩阵只在修复能力稳定且实际授权余量允许时执行；计划≤12是阶段上限，不是新增资金。 |
| T2.1 / F3 s2双档 | 两个独立新数值档已有实现与实际失败记录；原“≥2轮才达到fit22”还涉及基线已低于22的历史条件冲突。没有两条合格新Pareto补丁可展示。 | **实测未过。** 不能用默认/strict别名或同一FP32候选充当两档，不能把允许bf16当实际观察bf16。R8固定九项不替代独立两档。 |
| T2.5 / F3 HF | 隔离准备及真实基线已有；完整修复失败。F3要求无论成败报告已完成，但HF target_met/config-only≤15行的原验收未过。 | **能力实测失败。** 保留失败，只有新的真实合格修复才能加成功卡；无须另建框架。 |
| F5 | 环境恢复后的独立clean checkout确实走自身installed CLI、GPU及模型并产report；结果needs_human/no patch。后来公开disabled profile与自建配置说明已补。 | “干净CLI能运行并产report”有证据；“最新Quickstart、自有新配置成功修复”没有新增实测。不要以文档校验升级成此结论，也不因此重置旧once。 |
| F8 | 预定2026-10-30 **16:00北京**。本次核查时为12:52北京，尚未发生。已有一次失败全量及原203个失败/错误节点后续通过覆盖；不是最新版本重新全量通过。 | **计划内实际检查待发生。** 到时按原授权核服务/Funnel/公开链接、保留额、最终保存及有界smoke；不再重跑全量，不用排程记录当执行。 |
| 告警与未来保活 | 当前生产Funnel health timer每5分钟GET-only采样，明确不通知人；HTTPS通知器与30秒旧本地模板已有，但无真实收件渠道/投递收据。5分钟采样不能证明“停服2分钟收到告警”。 | **配置/外部渠道与实际送达验收缺失。** 先确定已授权收件端、正确生产origin与采样频率，再在受控故障条件验证投递及收件。HTTP2xx不等于Frank已收到。不得擅自联系别人或停正式服务演示。 |

## 可立即推进的无费用事项

1. 修正下一版台账的两处旧结论：s1 Tavily来源已在历史中满足；R7 Nano完整覆盖是5/8。原JSON不修改。
2. 将Tavily剩余集成验收收窄到s5，不重复已经成立的s1/缓存调用。
3. 20-cell运行前先说明三个unknown真值使固定分母75%无法被现有评分证明；不先花钱跑满再换分母。
4. 新授权的部署 admission drain 属于真实工程缺口：当前shutdown会取消已接收队列/运行任务。主线程已批准单服务主PID信号暂停新准入、保留已接收任务排空；实现和针对测试正在独立进行，本文不提前记完成。首次部署旧版不具备drain，必须另有受控安全窗口，不能给旧进程盲发SIGUSR1。
5. F8按预定时间执行；告警先明确收件渠道与生产接线。所有源修改期间仍须保持当前实际运行/source pins一致，不借此启动新模型或GPU工作。

## 本轮动态结果（由主线程终态后补）

- Snapshot 新协议及一次反馈纠正后的真实结果：**待本轮终态与独立验收；旧失败不回填。**
- R8 fixed-nine：**待本轮终态；九分母与原阈值保持。**
- admission drain：**待源码冻结、离线race/排空测试和首次部署收据。**

## 边界与来源

- `docs/FINAL_48H.md` 替代原Phase3–6交付安排；动画Replay、等待外部设计稿、被取消的显存回归功能不再作为新编码任务。主动搜索修复边界、多GPU等仍非原本轮必需范围。
- Watch真实OOM触发已完成，后续F3b-2明确允许修复失败，不把它重新列为“必须修复成功”。
- 提交后的评审期持续在线/余额与Tavily credits检查是未来运维，不能现在标完成。
- 原计划精确要求：T2.2行299–301、T2.3行303–304、T2.8行318–320；F8与告警分别见FINAL48行118–119及PLAN行338–339。
- Tavily组件及缓存：`reports/research-component-20261024T022414Z.json`（4实际method、8 research rows；不冒充全部s1/s5修复验收）。
- R7原12项：`reports/r7-20261029/r7-summary.json`，原campaign为`runs/final48-f3/execution-20261029-v1/campaign.json`；Nano逐run附件见下。
- Nano历史R1（119/119完整但7/79=8.86%）：`reports/acceptance-v2-r1-20261025/annotation-readonly-review.md`，不与R7混成新样本。
- 矩阵实现/评分边界：`docs/EVALUATION.md`、`eval/protocol_v2.json`、`eval/scenario_set_v2.yaml`。
- 生产监控/通知边界：`docs/FUNNEL.md:208–222`、`docs/DEPLOYMENT.md`。

### R7 Nano 逐项来源

| 场景 | 状态 | 一致率 | 原产物 |
|---|---|---:|---|
| s1_batch_too_big | completed | 0.375 | `runs/final48-f3/execution-20261029-v1/jobs/e82cd9646adc44fabb86270591701803/annotations.json` |
| s2_capacity_v2 | failed | unknown | `runs/final48-f3/execution-20261029-v1/jobs/6330dcf4e44b4accb09b73110dda0183/annotations.json` |
| s3_eval_no_grad_missing | completed | 0.15384615384615385 | `runs/final48-f3/execution-20261029-v1/jobs/ce2e4bf037a84b349d178c5bd661230b/annotations.json` |
| s4_loss_accumulation_graph | completed | 0.2 | `runs/final48-f3/execution-20261029-v1/jobs/e8213706570e478f9845e49e24c2b54b/annotations.json` |
| s5_fragmentation_varlen | failed | unknown | `runs/final48-f3/execution-20261029-v1/jobs/0d433ae4d2cd401abd66d6dc6230226f/annotations.json` |
| s6_full_vocab_logits_fp32 | failed | unknown | `runs/final48-f3/execution-20261029-v1/jobs/5a8094e6cadc4013a5fda5e9e5f1bb70/annotations.json` |
| s7_frozen_params_optimizer_state | completed | 0.0 | `runs/final48-f3/execution-20261029-v1/jobs/966c277a39cf456f92a58b388a501dbb/annotations.json` |
| s8_two_models_resident | completed | 0.2727272727272727 | `runs/final48-f3/execution-20261029-v1/jobs/f7b8b420a8754127a8e929fe64d81c45/annotations.json` |
