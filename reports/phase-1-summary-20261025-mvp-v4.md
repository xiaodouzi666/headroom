# Headroom Phase 1 — 最后一次原计划 MVP 修复验收（v4）

**结论：MVP 未通过，完整 goal 尚未完成。** 九个原定场景均真实执行，目标达成 **0/9**（原门至少6/9），首因命中 **7/9**（另2项unknown，不从分母剔除）。本轮是初次MVP之后的第3次修复迭代；原 PLAN §0.6 的修复轮数已用完，停止进一步修复试错，等待 Frank 决定是否扩展轮数。账号、密钥和赠送额度已就绪，不是本次停止原因。

实现/评测来源：78a83df86b181674c37509b192517a9d4101ad92。全部代码、依赖、GPU数据和媒体在azuki；Mac仅接收本报告。原PLAN、9场景、精度策略、阈值和失败历史均未改动。本轮结束于2026-10-24T23:31:55.358346+00:00，driver退出1，总墙钟735.240秒。

## 九场景结果

下表的“候选”与“最终选中”分开：s1有实际候选但OOM后revert；s8第2轮keep，后续失败不覆盖它，保留一个未达目标的小改善。其余没有验证成功的候选。completed工作流状态仅表示搜索结束。

| 场景 | 原标签 / 诊断首因 | 首因命中 | apply+compile | 候选完成 | 最终选中轮 | target |
|---|---|---|---|---|---|---|
| s1_batch_too_big | activations / activations | 是 | 1 | 否 | 无 | false |
| s2_fp32_adamw_1b | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s3_eval_no_grad_missing | activations / activations | 是 | 0 | 未执行 | 无 | false |
| s4_loss_accumulation_graph | retained_graph / retained_graph | 是 | 0 | 未执行 | 无 | false |
| s5_fragmentation_varlen | fragmentation_candidate / activations | unknown | 0 | 未执行 | 无 | false |
| s6_full_vocab_logits_fp32 | temporaries / temporaries | 是 | 0 | 未执行 | 无 | false |
| s7_frozen_params_optimizer_state | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s8_two_models_resident | params / params | 是 | 1 | 是 | 2 | false |
| nanogpt | unknown / activations | unknown | 0 | 未执行 | 无 | false |

## 峰值、数值、费用与时长

GB使用十进制字节/1e9。after仅列最终选中配置，不用失败候选冒充修复结果。费用“≤”表示已核验保守上界，actual仍为null；无“≤”为完整usage-priced已知费用，不是独立核销发票。

| 场景 | peak before GB | selected after GB | 降幅% | step时间变化% | 数值状态 | 调用数 | 模型费用USD | 秒 |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| s1_batch_too_big | 24.750424064 | — | — | — | unknown | 28 | ≤0.12634370 | 91.948 |
| s2_fp32_adamw_1b | 21.553250816 | — | — | — | unknown | 8 | 0.068768988 | 54.264 |
| s3_eval_no_grad_missing | 2.435717632 | — | — | — | unknown | 34 | 0.192787128 | 139.395 |
| s4_loss_accumulation_graph | 24.768717824 | — | — | — | unknown | 34 | 0.175681208 | 128.276 |
| s5_fragmentation_varlen | 5.021758464 | — | — | — | unknown | 19 | 0.112660608 | 112.125 |
| s6_full_vocab_logits_fp32 | 21.588379648 | — | — | — | unknown | 2 | ≤0.03223954 | 18.110 |
| s7_frozen_params_optimizer_state | 17.819808768 | — | — | — | unknown | 23 | ≤0.11876024 | 88.777 |
| s8_two_models_resident | 3.100141568 | 2.989897728 | 3.556091 | 0.941755 | identical | 14 | ≤0.12185840 | 62.184 |
| nanogpt | 24.705183744 | — | — | — | unknown | 3 | ≤0.09073224 | 39.175 |

s1第3轮实际应用并编译，但仍OOM、0训练步，peak=24.750424064GB，loss=n/a，参数量未变。s8第2轮完成20步，peak从3.100141568降至2.989897728GB，仅3.556090507%（要求20%）；记录的backward标量loss序列identical，原口径numerical_acceptance=true，但same_inputs/effective_batch/objective仍unknown，不能扩写为新的配对数值等价证明。s8实际step时间增加约0.941755%，throughput gate通过。

本轮165次模型调用：已知小计1.037464332USD，加5条Nano可核验上界0.00236772USD，保守合计1.039832052USD；实际总额null。9项均≤0.60USD且≤480秒。campaign.summary.known_cost_usd=0.549897932仅汇总4个总费用完全已知run；另外5个bounded run内的已知调用0.487566400USD也属于已知小计，不能遗漏。

## 原验收门逐项状态

- T1.5：8个合成场景中仅2个有真实git apply命令/direct fallback及compile0，低于6/8；所有patch轮均初稿+最多3次fixer，Super调用均≤4000 completion tokens。direct fallback不冒充三方合并成功。
- T1.6：s1未完成；s3未产生候选，30%降幅门未通过。旧手工/负例GPU与单元测试证据保留，不充当模型修复成绩。
- T1.7：s1有49事件、28模型调用及所需事件顺序；但本次通过eval worker调用核心流程，字面headroom fix命令未观察。九个worker均exit0不等于九个CLI exit0；根据已核对状态推导CLI码为0,78,0,0,78,78,78,78,78。
- T1.8：九份JSON/Markdown报告均存在、均≥7个二级标题；实际scripts/check_report_numbers.py逐份运行9/9通过。唯一最终选中patch的独立apply-check收尾证据见mvp-v4-s8-selected-apply-check.json；没有选中patch的八项为n/a。
- T1.9：nanoGPT无候选、fit22未通过，loss unknown；≤0.8USD费用门单独成立，不能替代MVP≤0.6门或22GB门。
- T1.12：报告/来源/清理/费用/时长门成立；目标0/9和真实CLI入口门未通过，不能进入“已验收”。
- T2.2：真实模型工具循环形成9条research记录、8次API、7个记录credits；s4成功提取匹配PyTorch2.5的checkpoint文档，s5命中s3缓存且API/credits均0。但原要求的s1 checkpoint Sources与s5 CUDA memory Sources均缺，完整门未过。
- T2.3：8场景仅4项完整标注；这4项40个可评分栈中仅3个类别与启发式一致，其他4项失败不能被剔除。每项费用上界≤0.02成立，完整覆盖/≥80%一致率门未过。

## Top 3失败模式与已经做过的调整

1. **补丁结构仍不可靠。** v2的reasoning耗尽已通过显式reasoning=False处理；v3的无换行字符串已改成diff_lines并保留原响应与规范diff。v4共110次patch尝试：88格式/安全拒绝、19应用失败、1响应拒绝、2应用编译成功。109个非空diff中107个被拒，另1个响应形态unknown。实证包括缺前缀、hunk计数不符、复制展示行号及缺少上下文；JSON合法不代表可应用。
2. **静态成功不保证有效修改执行路径。** s1零context hunks把代码追加到main调用/异常分支之后，原forward仍OOM。s8先在GPU创建teacher再搬到CPU，保留小幅改善但未消除先前峰值。真实Lab与keep/revert正确保留失败或不足目标的事实；没有手工替模型写场景答案。
3. **诊断/证据附属门仍有缺口。** 多项搜索以needs_more_info结束；Nano出现标签覆盖/类别不一致；Tavily虽有真实调用和缓存，指定Sources未齐。s2原39.8715%<40%、已fit22却要求两轮才fit22、默认禁精度变化却要求bf16档等原计划冲突仍需逐项讨论。

## 模型、服务与验证体验

T0.4全部60项探测已执行并保留失败；Ultra实测500029输入token成功，900k返回429，其未知1.049344USD上界继续占用，不宣称完整1M请求成功或精确最大上下文。T1.3真实53记录/268920输入token通过。独立诊断v5首因7/8且引用8/8有效，但完整政策/计划门未过。Super通用docstring组件最终经正常fixer应用/编译通过，只证明组件，不计MVP成功。Nano缺cache split时actual保持null，独立核验上界；Tavily工具与费用记录见上。

当前源码完整回归2026 passed（551.34秒），运行期间236项源/配置/测试/生产prompt哈希不变；后续仅泄密扫描器精确非秘密哈希例外发生配置变化，生产代码/测试/prompt未变。前端68测试、typecheck、build既有结果保留，未伪称本次重跑。当前Home单次Lighthouse99，390px无横向溢出；这不是浏览器实时修复验收。T2.7三场景六GPU臂峰值差0%，独立Popen控制器在Docker内、共享采集协议，宿主EPERM历史保留。

## 赠送额度与后续预算

截至最终财务复核，总账298次attempt全部结算、46个run全部关闭，无pending/unresolved/halt。runtime已知3.056058592USD，保守3.077893672USD；既定9.99964904USD runtime池剩6.921755368USD。加外部探测保守占用1.82224246USD，总净保守占用4.900136132USD；21%税预留后5.92916471972USD。这是内部保守核算，非账户实扣/发票，也不使用旧UI余额当现时余额。原16USD净总包络、税/备用与10USD评审储备未调整；未充值、未转移未用探测池，历史未知费用未释放。

## Phase 2建议与必须由Frank决定的下一步

先解决MVP补丁可靠性，再做完整Phase2与主表/消融。只读提案mvp-v4-next-repair-options.md给出三项具体方案：有界结构化格式错误反馈；将原文与展示行号分离并验证基线hash/精确旧块锚点；验证实际应用位置与锚点一致。全部保留原数值、参数量、吞吐、4000token和每patch三次修复门，不预写场景答案。方案尚未实施。

原docs/PLAN.md第41行：若未达标，“最多再修3轮，仍不达标则停下等Frank”。v1初次失败、v2/v3/v4三次修复均已保留。当前需要的是是否允许追加有界MVP修复轮数，不是重新索要已授权的赠送额度调用许可；本次不自行开始第4轮或更改阈值。

真实五条规定修复回放、浏览器完整运行、HF修复、Watch真实修复、10×2/12主评测与消融仍未通过。设计稿/还原认可、域名/Cloudflare和告警收件渠道、视频/Devpost最终提交及未来日期在线检查仍各有独立门。没有发布evaluation/release标签、公开服务或提交比赛。

## 证据与交付

- 原campaign：runs/evaluation/live/20261024T231940915002Z-2098d11d/campaign.json（私有原始运行）。
- 固定九项：reports/live-campaign-20261025/mvp-v4-audit-v2.json。
- 费用/CLI：同目录mvp-v4-finance-review.json、mvp-v4-cli-exit-semantics.json。
- 候选与子门：同目录mvp-v4-candidate-verification-review.json、mvp-v4-candidate-verification-supplement.json。
- 报告数字：同目录mvp-v4-report-number-checks.json；选中patch：mvp-v4-s8-selected-apply-check.json。
- 后续提案：同目录mvp-v4-next-repair-options.md；完整未完成门：reports/final-decision-20261025.md。
- 当前完整回归：reports/patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json。
- 本任务既有localhost preview已重启加载78a83df，health/Home200，无UI提交；mvp-v4-final-source-check.json与final-preview-restart.json保留收尾证据。
- 最终handoff合并本页、RESULTS和PROGRESS，纯文本小于1MiB。提交前扫描/交付状态单独记录；原失败和旧summary保留。
