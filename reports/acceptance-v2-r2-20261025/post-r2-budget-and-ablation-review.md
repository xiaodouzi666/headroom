# r2 后赠送额度、Phase 2 与消融：只读预研

这是运行前方案审查，不是新的花费授权、资金余额查询或验收成绩。没有新增 provider/GPU 调用，也没有修改源码、profile、ledger、manifest 或原 PLAN。金额基于已核的 funding-transition.json 和 r1 结算，不使用网页显示余额扩额。

## 资金条件

转拨后的 runtime lifetime 上限为 $14.17775754 net，每日上限仍为 $9.99964904；既有保守累计 $6.600422176。因此 r2 开始前 lifetime 余量 $7.577335364，同一 UTC 日余量 $6.477120536。外部已用/保守保留 $1.82224246（含未知 $1.049344）不释放。总承诺仍为 $16 net；16×1.21 +0.89 gross buffer +10 gross judging reserve =30.25 gross gift。Trial 与网页账单余额没有计入。

以 r2 最终保守新增费用 C 为准：

- lifetime 后续余量 = 7.577335364 − C；
- 同一 UTC 日后续余量 = 6.477120536 − C；
- 跨 UTC 日只重置日窗口，lifetime 和所有未知费用不重置。
- 每次 POST 仍需完整 provider bound；当前 Ultra 16384 输出的预留为 $1.097728，不能以本地 token 估算或较低 run stop 替代。

$5.4 是九个 $0.6 run 的名义 campaign 开始门。evaluation.py 在 spent+per_run<=campaign_cap 时开下一 run；actual_usage 在本次调用结算达到 run stop 后才停止，因此单次大额/未知结算可越过 $0.6，随后该 run 不合格且 campaign 停止。不能无条件断言最终 C<=5.4。若 r2 九行全部满足原费用/完成范围资格，才可使用 C<=5.4 的条件界。资格不合格时不进入后续 Phase 2。

| 条件情景（不预测实际费用） | lifetime 剩余 | 同日剩余 | 含义 |
| --- | ---: | ---: | --- |
| C=0 | 7.577335364 | 6.477120536 | 仅数学起点，不能把运行当免费 |
| C=0.79925580（仅沿用 r1 费用作为示例） | 6.778079564 | 5.677864736 | r2 cap/搜索行为不同，不能外推为费用承诺 |
| C=5.4 且九行费用资格成立 | 2.177335364 | 1.077120536 | 同日已不足一次 Ultra 16384 完整预留；次日可能具备少量调用条件，仍无法保证完成矩阵 |

Phase 2 的 20×$0.6=$12 和消融的 24×$0.6=$14.4 都是按现有 pipeline run 配置计算的名义总上界，不能当作新增额度。即使 r2 未花费，当前余量也不足同时保留所有 run 的最大值。实际低于上界时可能完成更多槽位；任何未来排程都只能以结算后的共享账本和每次调用的完整预留决定。不能承诺 20 或 24 槽必定全部执行，也不能删除未执行槽位来提高分数。

## 后续真实门槛及依赖

1. 先让新 r2 九场景通过独立 6/9 target +6/9 有效正确首因资格，以及来源、费用、实际运行清理等 gate。现有 phase2-v2-r1 driver 固定绑定失败的 r1 和旧 profile/质量收据，不能直接改路径后冒充旧资格；需新版本绑定 r2、完整当前 source、同 ledger 与资金转拨 receipt。
2. T2.8 固定为 eval/scenario_set_v2.yaml 排除 library 后的十场景 × strict/allow_precision=20。不是 9×2=18，也不是完整十二行×2=24。最多六搜索轮，费用 $12 是阶段 ceiling；实际 campaign admission 仍取 min(12, remaining lifetime, remaining UTC day)。每个政策分别报告，不把两个政策的成功合成一个分子。
3. T2.1 仍需真正的 strict 模型修复：至少两轮、指定 optimizer-state-first/activation-second、fit:22GB、独立 patch/round 决策。人工 foreach 控制只证明临时显存瓶颈，不替代指定持久状态修复。allow_precision 还需实际 BF16 行为、数值变化标记、较低峰值和独立 patch；政策许可不是 BF16 结果。
4. T2.2 的真实 Tavily 来源和缓存证据、T2.3 八场景 Nano 标注覆盖/80%一致率/$0.02 门、HF target+配置-only<=15行仍单独核。HF 已包含在十场景内，不能另跑一次后替换矩阵里的失败。
5. T2.4 的 $0.05 run /$0.1 daily 拒绝已有离线真实编排器+MockTransport/Store 验证，应引用冻结回归，毋须额外花钱刻意制造 provider 错误。另一个完整真实多轮<=1.2的验收须引用真实合格 run。
6. 预算不足时仍可做报告、现有 repair Replay 筛选/打包、UI/API 离线验证、部署材料、来源审查。Replay 本身不耗模型，但不能把 baseline 或人工控制称为模型修复；真实 UI 触发、clean-clone repair、2 个 library case 和 T4.3 消融均还需自己的来源/运行证据。原 $10 gross 评审预留不用于补本阶段资金。

## 75% 首因目标的精确分母边界

原 docs/PLAN.md T2.8（318–320）写十场景×两政策、target_met 与首因一致率>=75%“目标，如实记录”，没有单独定义未知真值如何作分母。不要把它改述成已明确的“只按已知真值75%”。版本化协议 eval/protocol_v2.json 的 scopes.phase2_policy_matrix 固定 scenario_count=10、pipeline_runs=20，两个目标字符串均0.75；既有 planning 另明确 fixed_pipeline_denominator=20、fixed_per_policy_denominator=10，未执行仍unknown。

当前 eval/scenario_set_v2.yaml 的 scenarios 数组（从1开始）：

| 行/ID | group | ground_truth | truth_status |
| --- | --- | --- | --- |
| 5 / s5_fragmentation_varlen | synthetic | fragmentation_candidate | unverified |
| 9 / nanogpt | repository | null | unverified |
| 10 / hf_trainer | repository | null | unverified |

排除 library 后仅另七行具有 authored 真值。headroom.evaluation.summarize_rows（约980–1022行）保持三个不同量：first_cause_accuracy 在任何 measured 行未知时为 null；first_cause_accuracy_among_scored 只用已有布尔匹配的行作分母；first_cause_success_lower_bound 用全部 attempted measured 行作分母。未执行槽还需固定20槽审计另行保留，不能因 summarize 的 measured 过滤丢掉。

因此，若二十行都执行且现有真值不变，已知正确首因最多14，固定20槽成功下界至多70%，完整 first_cause_accuracy 仍未知。即便已评分部分14/14=100%，也不能无条件宣称完整75%目标已达到。T4.3 的八合成×三条件同理：当前 s5 未裁定，最多七组可进入已有 paired-cause summary；八个 planned 场景仍须完整列出。

后续应先独立裁定真值：只依据冻结源码、真实 baseline/分配栈和官方机制资料，预先说明可判定的类别与无法确定的理由；形成新版本 manifest/receipt，保留当前 unknown 与全部旧分数。不能用任何模型答案当真值，不能为了75%倒推一个类别。本报告不进行裁定。

## full_super 16384/8192 不兼容与最小正确选择

实际代码中 condition_services(full_super) 用 _SuperDiagnosisRouter 将 diagnose 请求映射为 patcher/Super，但继承全局 DIAGNOSIS_MAX_COMPLETION_TOKENS=16384；新 r2 profile 只提高 Ultra ceiling，Super reviewed ceiling 仍8192。故当前 full_super 会在 runtime billing-cap 检查前置拒绝，不能解释为模型诊断失败。现有 schema/mock 路由测试只证明格式运输，不证明这次 live 资格。

最保守的未来方案是预登记一个独立消融协议：八个 synthetic、同一明确政策、相同 source/argv/search-mode，三臂诊断均4000 completion tokens；所有 patch 请求也仍4000。它遵守 T1.5“每次Super调用 completion_tokens<=4000”的字面边界，且无需增加 Super profile ceiling。这是独立的受控消融设置，不改变 r2 MVP 的 Ultra16384，也不代表4000一定足以产出 JSON。截断/未知原样计入。报告应说明该消融比较发生在4000输出预算下，不能把 r2 16384结果混入其中。

工程上应显式传递内部、预登记的 diagnosis completion cap：初始和补充调用相同；system prompt 的预算文字同值；condition provenance 与实际 wire audit 固定该值。不要在底层 router 偷偷 clamp；仍由 profile 拒绝超上限请求。MVP/standalone diagnosis acceptance 默认仍16384、原 prepared-payload/source pins 不变更为“兼容旧包”。新增正反测试应验证三臂实际字段/role/schema、无静默降档、wrong cap零HTTP和完整provider预留。此处只提出方案，不修改源。

若选择 full_super8192，技术上可落在现profile ceiling内，但需要明确解决 T1.5作用域，并把三臂输出预算一并固定8192才便于解释模型差异；不能因配置中已有8192就自动认为原验收允许。若选择 full_super16384，需要新的 Super billing evidence/profile ceiling、同池完整预留和实际端点验证；本次未进行。单纯提高 profile 标志并不能证明模型/端点接受，亦不得添加未经 Nebius 验证的 reasoning_budget、low_effort 或 reasoning_effort。

完整 provider 预留（使用现有已核费率/输入 ceiling）：

| 诊断 cap | Ultra：1048576 input，$1/$3 per million | Super：262144 input，$0.3/$0.9 per million |
| --- | ---: | ---: |
| 4000 | 1.060576 | 0.0822432 |
| 8192 | 1.073152 | 0.086016 |
| 16384 | 1.097728 | 0.0933888 |

full_ultra 与 full_super 的完整证据还需在各自已核输入/UTF8上限内；不能只缩短 Super 的证据却仍声称只有模型不同。若完整输入不能同时承载，应预登记共同输入范围或明确该对照不可配对，保留超限事实。三条件 table 应比较首轮诊断，不能把后续工具交互、额外修复轮或政策差异当作单一模型/快照效应。

## 官方主源及适用范围

- [Nebius Create chat completion](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)：max_completion_tokens 同时包含可见输出和 reasoning；max_tokens 的8192是默认值，不是文档规定的全局最大值。通用 schema 没有证明具体模型接受16384，也没有证明 Nemotron 特定 reasoning_effort 参数支持。
- [NVIDIA Super 官方模型卡](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8)：本地 serving 示例使用 enable_thinking 与16000输出，并有更大输出配置；说明8192不是模型架构的必然硬限。这些 localhost/vLLM/SGLang/TRT-LLM例子不是 Nebius 服务配置或计费能力证明。
- [NVIDIA NeMo Evaluator reproducibility](https://github.com/NVIDIA-NeMo/Evaluator/blob/main/packages/nemo-evaluator-launcher/examples/nemotron/nemotron-3-super/reproducibility.md)：其 NVIDIA 端点评测将输出长度、温度、重试、任务特定配置显式列入复现设置，部分任务单独8192。这里引用的工程启示是记录并固定配置；不复制其不同provider、131072上限或10次重试到本项目。

这些公开来源于2026-10-25重新打开；预算推算来自本项目已冻结凭据外的账务收据。报告不读取或发布密钥、完整私有请求、卡号或账单地址。
