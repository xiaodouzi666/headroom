# Phase 1 真实失败阶段总结 — MVP v2（2026-10-25）

记录时点：2026-10-24T22:46:26.017307+00:00（UTC）。**MVP/Phase 1 尚未通过，整个目标未完成。失败后修复轮 1 已完成；修复轮 2 的通用补丁协议修复准备中，尚无新协议通过声明。**

依据冻结 v1/v2 审计和原始产物。本次只写报告，未启动模型/Tavily/GPU/测试，未改 source/profile/账本/PROGRESS/RESULTS。旧失败和费用保留，不删除 runs、不修改原门槛。v2 campaign 退出1；审计正常退出2表示未通过，errors=[]。

已提交基线：5d3093c94d7b8f8b3ab3626acf0919e3138e8b4d。原 PLAN SHA-256：e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56。旧总结原字节存 phase-1-summary-before-live-20261025.md，SHA-256 d9fea9c70df4b8c526a128afed19632b3cc547647a78a35f52fcb7f6e155942f。

## 1. 原门槛与本轮结论

T1.12（PLAN:285–291）保持原九分母（八合成+nanoGPT）、默认策略、每run预算0.6 USD、九报告和退出证据；target_met≥6/9、首因一致≥6/9；MVP reclaim≥20%；每run≤480秒；原质量检查及阶段总结。

- v1只有s1真实基线和一次Nano请求，缺cache计数触发当时费用未知保护；其余八项未执行，没有成功修复。后续retention不改判v1。
- v2九个harness worker退出0、有报告/清理记录，全部wall≤480秒；这是harness child证据，不冒称真正CLI/browser入口验收。
- v2只有s1实际执行模型/GPU链，target=false、首因activations正确。为避免重复付费协议失败，主代理临时关闭后续admission；另外八项runtime_not_ready，0模型/0GPU，属于运营跳过，不是八个模型质量失败。
- 固定九分母：target_true=0，first_cause_true=1、unknown=8；未到≥6/9。不能删除未执行项凑分，也不能说“九个模型修复都失败”。
- **没有可接受的模型生成修复成功；主评测/消融亦未通过。** 手工GPU修复和离线fixtures均不计分。

## 2. 九场景表

GB为decimal bytes/1e9。before来自本轮真实基线；after/completed/数值只取最终选中配置。费用列为actual与verified upper，不能相加；wall含campaign清理时间。

| 场景 | 真值依据 | 首因 / 一致 | any applied | selected completed | peak before / after GB | 降幅% / step变化% | 数值等价 | target | 轮次 | 模型记录 | GPU | actual / upper USD | wall秒 | 状态 |
|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---:|---|
| s1_batch_too_big | activations（场景作者标签） | activations / 是 | unknown；R1–4=false | unknown | 24.750424064 / unknown | unknown / unknown | unknown | false | 5 | 22 | 基线执行；无选中候选 | null / ≤0.14129888 | 283.708064 | needs_human |
| s2_fp32_adamw_1b | optimizer_state（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.927860 | 运营跳过 |
| s3_eval_no_grad_missing | activations（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.925519 | 运营跳过 |
| s4_loss_accumulation_graph | retained_graph（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.934264 | 运营跳过 |
| s5_fragmentation_varlen | fragmentation_candidate（未独立确认） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.916868 | 运营跳过 |
| s6_full_vocab_logits_fp32 | temporaries（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.930882 | 运营跳过 |
| s7_frozen_params_optimizer_state | optimizer_state（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.946584 | 运营跳过 |
| s8_two_models_resident | params（场景作者标签） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 0.917765 | 运营跳过 |
| nanogpt | unknown（未独立确认） | 未观察 / unknown | unknown | unknown | unknown / unknown | unknown / unknown | unknown | false（运营拒绝） | 0 | 0 | 0 | 0 / — | 1.051360 | 运营跳过 |

s1的patch_applied_any原审计为null，保留unknown。round1–4实际patch-result均rejected、应用事实false；第5轮请求补充信息，没有选中patch/after；不能把缺值补false。本轮无成功应用证据。八项跳过的0费用来自无请求记录，不是把未知账单填0。s5及nanoGPT的未确认真值保持unknown。

## 3. 模型调用、账务与运行事实

s1保存22条调用：Nano1、Ultra5、Super16。前四轮每轮一次patch加至多三次fixer，共16条Super；第5轮diagnosis_needs_more_info停止。38条事件保留；没有成功应用/编译验证后的候选。

| 来源 | actual USD | certified upper / 保守占用 USD |
|---|---:|---:|
| v2 s1 Ultra，5次 | 0.08067176 | 同actual |
| v2 s1 Super，16次 | 0.0603759 | 同actual |
| v2 s1 Nano，1次 | null | 0.00025122 |
| v2 s1总额 | null；known subtotal=0.14104766 | 0.14129888 |
| 其余八项 | 0 | 0 |
| 历史v1 Nano（另列，不是v2费用） | null | 0.01644864 |

v2 Nano未返回cache split，正式strict runtime/ledger在身份、tariff、usage/cap和结算全部验证后给出上界。actual仍null、complete=false；billing_complete=true、bounded1、unresolved0。审计逐call核对budget_attempt_id与账本；旧cost_complete_and_consistent字段在v2采用费用证明语义，不代表精确actual完整。upper0.14129888≤0.6证明原费用门，不是已确认实际花费；全局/日池仍在请求前保留完整provider上界。

v1经review永久保留原full reservation0.01644864，旧Store/report/campaign未改判。不同汇总不能重复相加，不在此推断账户余额或发票。s1 wall283.70806439290754秒，低于480，但费用/时长通过不能覆盖target失败。

## 4. Top3失败模式、已做与待验证调整

| 失败模式 | 真实证据 | 已做 | 待验证 |
|---|---|---|---|
| Nano缺cache usage导致可保守覆盖请求被当作未决 | v1 prompt3643/completion480/cache=null，第一模型请求后安全停止 | **失败后修复轮1完成**：新增正式bound与reviewed-retention，actual不变null，旧full上界永久占用；v2 Nano用upper0.00025122继续进入诊断 | 未审未知/无效bound仍阻止；不称发票核销，不重评v1 |
| Super reasoning消耗4000 completion预算，补丁响应截断 | 4轮中6个attempt为LLM_RESPONSE_REJECTED；现场记录重复4000completion/4000reasoning | 拒绝截断响应、不应用残缺diff；保持每次≤4000；停止后八项以免重复付费 | **修复轮2准备中**：通用patch/fixer显式采用已证实控制，核查可用输出；先离线与单场景真实复验，不声称新patch已测 |
| 输出不满足unified-diff文件结构 | 10个attempt为UNSAFE_OR_INVALID_PATCH，detail为“diff must touch between one and twenty files”；四轮patch-result均rejected | 安全/文件策略未放宽，任意文本/空diff不算补丁；原失败保留 | 修复轮2核验真实schema/prompt/提取→通用parser合同；不得特判场景、手写替代模型或绕过policy |

这些是实际故障类型，不是九场景能力总体统计。T1.4v5的禁止改动建议与补充信息仍为独立限制；协议修好后必须继续真实policy/数值/目标门，首因命中不保证合法修复。

## 5. Ultra长输入实际体验

T0.4的60个规定样本（55新、5历史）中，64k/200k/500k exact-retrieval服务端prompt为64,031 /200,031 /500,029 tokens；总耗时约5.613 /7.412 /17.980秒。900k返回429和Retry-After255、未重试，actual未知、完整保留1.049344 USD。500,029只是成功实测下界，**未验证1M实际成功或精确最大上下文**。

T1.3从同一真实capture取53条唯一原始记录，非filler，真实客户端/路由Ultra返回provider input268,920、completion149、10.913586秒、usage-priced0.269367 USD；Super schema0.0001344，总0.2695014。客户端门接受，但Ultra自由文本曾把cache gap夸为fragmentation，传输能力不等于科学正确。

T1.4v5：7/8首因、8/8引用、八次stop/reasoning0、已知0.328770 USD；s1/s6政策违反、s7补充信息、s5真值未知保留，完整未过。v2首轮s1原因正确却无可用补丁；不另开八次diagnosis-only来重复证明已有事实。

## 6. Token Factory / Super / Nano / Tavily体验

**Token Factory：** 认证、官方目录/价格和能力有实测；usage-priced actual与发票分开。429或缺cache分项不能当0，也不自动重试。正式upper只在可证明条件下继续，全局/日池保护及原0.6门不变。T0.4作用域已知0.77289846+429保留1.049344=保守占用1.82224246 USD，不与包含同批调用的汇总再次相加。

**Super：** native schema、生成add工具、四并发探测通过；add生成不是Tavily执行，也不证明Patch可靠。v2的16次patch/fixer无可应用结果；下一轮检查完整请求和parser，保持completion≤4000及≤3fixer，不以增cap掩盖问题。

**Nano：** 精确model ID已实测。v2 prompt3643/completion136，上界0.00025122≤原0.02/run；这不接受八场景Top40完整标注、交付Ultra或≥80%一致率，仍须实际annotations/delivery统计。native tools失败，继续禁用。

**Tavily：** 真实search/extract与版本缓存组件已验收，重复query已证0API/0credits；不自动接受完整s1/s5报告的Sources/research工具循环。只补缺失证据，不重复买组件事实。

## 7. 原未过门与Phase2建议

- T1.2 s2 optimizer-state39.8715009692%<40%，保留失败。基线已fit22，多跑两轮不能冒充两轮才达标；固定state字节的40%条件推出peak≤21.48401152GB，本就低于22。版本化校准需明确决定，原源/旧runs保留。
- 默认numerics=false与默认bf16档、T2.8 default/strict有效相同的矛盾未解决。不能暗换allow_precision，也不能保留被支配/数值未过配置凑Pareto。
- T1.5≥6/8应用，T1.6 s1数值/peak及s3≥30%，T1.7真实CLI，T1.8选中patch报告，T1.9nanoGPT均未关闭。MVP20%不替代s3的30%；仓库n/a只按原无参考例外。
- **先通用协议修复→一条必要单场景真实复验→补未执行八项**。原预算/日池/费用记录/源与数值门不变；不重复支付相同协议失败的完整九项。最终仍按原九分母完整证据判断。
- 复用合格run的Nano/Research/diff/验证/事件/费用；clean-clone s1 CLI可合并T5.1/T1.7，浏览器与Watch各自保留真实入口。先读产物再补缺项。
- Phase2有限搜索、HF≤15行配置修复、10×2矩阵和Phase4主表/8×3消融待真实验收；≤6搜索轮、≤3优化轮、原分母/总预算不变，不提前写预期增益。T2.7六个真实GPU arms已过≤1%，不重复跑。
- 设计、域名/Cloudflare、真实告警、视频/Devpost和未来保活仍独立。赠送额度内原计划已获授权；场景/默认策略实质变更需具体决定。

## 8. 已验证基线、证据与范围

5d3093c对应冻结基线：独立guarded后端 **1977 passed /549.80秒**，233项生产源/测试/生产prompt/场景输入前后不变；前端 **68 passed**、typecheck/build通过。driver总551.384秒含包装开销。之后报告脚本格式及精确非秘密hash allowlist属于报告/扫描配置变化。**这些结果不验证准备中的修复轮2新patch，不把fixtures计入真实成功。**

- 质量：reports/final-verification-20261025/validation-summary.json及full-regression-20261024T222341Z-d83e26d0-receipt.json；前端reports/bounded-billing-reporting-20261025/receipt.json。
- v1：reports/live-campaign-20261025/mvp-v1-audit.json；SHA-256 afd76e0e9259cf4b98500522a672fa0bbeaf9b2049cc867cf6de71fcdc4d85a1。
- v2：reports/live-campaign-20261025/mvp-v2-audit.json；SHA-25632efb71b7be602197456490802a316bbb7c4ac42fd712673408635b34acda69d；同目录mvp-v2-operational-audit-note.json和mvp-v2-protocol-stop.json。
- 原campaign：runs/evaluation/live/20261024T223453139983Z-b34f1afd/campaign.json；raw report/round/event/call未重写。
- T0.4/T1.3：reports/t0.4-acceptance-20261025.json、reports/t1.3-acceptance-20261025.json；v5：reports/live-campaign-20261025/diagnosis-attempt4-review.json。
- T2.7：reports/t2.7-acceptance-20261025.json，Docker隔离内独立subprocess reference，非裸宿主/独立allocator，不声称吞吐收益。
- 后续：reports/remaining-acceptance-20261025.md；其v2前状态不能覆盖本次失败事实。

本总结与canonical phase-1-summary.md字节一致，<1MB纯文本。只存azuki，未复制Mac，未commit/push；未改PROGRESS/RESULTS/source/profile/账本。
