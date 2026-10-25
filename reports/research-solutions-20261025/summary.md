# Headroom 待讨论事项：独立调研与工程修复

日期：2026-10-25。范围依据 Frank 的最新指示：先独立核查所有待讨论项，有公开且适用的方案先实现并验证，最后只讨论未解决的选择。本轮实现和有界实测已完成，完整离线回归收据在同目录单独保存。

原 docs/PLAN.md、eval/mvp_phase1.yaml 与 v7 九场景历史成绩保持原样。新增验证协议不会把不同版本的成功拼成一个九场景成绩，也不会把诊断通过当成实际 GPU 修复通过。

## 已核实的公开依据与适用性

| 待讨论项 | 核实结论 | 实现方向 |
| --- | --- | --- |
| 不同 batch 的 loss 比较 | PyTorch 2.5.1 官方说明浮点求和顺序及批处理会影响结果；同种子和相同 effective batch 都不足以证明同输入、同训练过程 | 明确选择原工作负载参考，绑定原源文件、argv、输入/初始化、更新与运行环境，保留原容差 |
| OOM 原始参考无法运行 | PyTorch 支持 saved-tensor CPU / disk hooks，保持反传所需值而把存储移出显存；这会增加时间/主机资源 | 新增有资源上限、只用于参考的 offload 路径；参考时间与显存不计为候选收益 |
| s2 39.8715% 与 40% | 固定版本 AdamW 的两个 moments 与 foreach 临时内存说明支持现有测量；不是已证明的分类错误 | 新增精确有理数的验收可满足性审计，不调低40%，不改历史结果 |
| default/strict 与 BF16 | 当前两个策略实际等价；BF16 是明确的精度策略选择，官方方法不能替产品决定默认许可 | 保留显式 allow_precision 和已有策略等价标注，未偷偷改变默认值 |
| needs_more_info / CLI 默认误读 | Schema 约束结构，不能保证模型正确理解输入；确定性检查、精确错误反馈和有限重试是公开的工程模式 | 核对声明的 argv 证据；有矛盾才沿用既有 supplement 机会；真正缺证据仍可停止 |
| 真实请求证据缺口 | HTTPX 的 request hook 位于 SDK 完成准备之后、网络发送之前 | 保存实际请求体哈希与有界脱敏副本，关联预留的调用账目；不冒充已送达证明 |

主源：
- [PyTorch 2.5.1 numerical accuracy](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/numerical_accuracy.rst)
- [PyTorch saved tensors hooks 教程](https://docs.pytorch.org/tutorials/intermediate/autograd_saved_tensors_hooks_tutorial.html)
- [PyTorch 2.5.1 AdamW](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/adamw.py)
- [Nebius structured JSON](https://docs.tokenfactory.nebius.com/ai-models-inference/json)
- [Anthropic agent workflows](https://www.anthropic.com/research/building-effective-agents)
- [HTTPX event hooks](https://www.python-httpx.org/advanced/event-hooks/)

## 工程上已明确解决的证据问题

1. 模型调用链的每次实际 prepared body 可核验，包含 router schema、reasoning 字段及补充轮次；历史不完整审计不回填为真实请求。
2. 声称已经给出的 argv 缺失、或声明的 token 与保留 argv 不一致，会得到具体反馈。旧响应兼容；未声明的事实保持 unverified。
3. s3 的现有完整 runtime capture 已接入共享 solver context：训练输入 batch 1 与 eval 初始化张量 batch 16 有明确来源。不是从场景名称或默认值猜答案；eval 张量被捕获不等于额外证明其每次 forward 使用。
4. s2 现在能在离线阶段直接检查门槛是否互相冲突。当前状态字节 8,593,604,608 / 40% 给出 peak 最大 21,484,011,520 bytes，已经低于22GB；固定此fixture时无法同时要求基线超22GB并满足该比例。

## 不应伪装成技术修复的部分

- s2 的40%分类检查与22GB容量修复需要各自适用的预先校准fixture；是否建立新版fixture是目标设计，不能事后修改历史分数。
- 默认禁止改变数值与要求BF16候选不能同时成立。原默认保留，精度变化继续需要显式 allowing policy。
- s7 原代码仅对backbone调用eval()，并未关闭梯度，优化器仍更新backbone。v7改为仅更新head确实改变训练；不能靠补一个数值标签使其合格。后续方案必须保留原参数更新语义，或者明确另立训练目标与参考。当前按原计划继续保留训练语义。
- 新的单次诊断probe只验证模型是否利用新证据；不证明patch成功、九场景6/9、Phase2完成或未来模型稳定正确。

## 独立细项报告

- [s2 与策略可满足性研究](../acceptance-feasibility-research-20261025.md)
- [精确门槛计算收据](../acceptance-feasibility-20261025.json)
- [诊断可靠性研究与实现](../agent-reliability-research-20261025.md)
- [实际请求审计设计与边界](request-audit.md)
- [数值参考研究与实测](../acceptance-research-20261025/numerical-reference-research.md)；[s4完整20步收据](../acceptance-research-20261025/offload-s4-disk-reference.json)

代码、运行和暂存数据均在azuki；赠送额度与总池不扩充，不充值，不删除既有失败证据。

## 本轮实际结果

- **s4参考问题已获得完整解法**：原始batch8、原源码/argv/初始化与精度，disk reference跑满20更新；20个loss与保存的v7候选差均为0。225秒以内完成，实际磁盘峰值41.26GiB低于64GiB，单张量暂存峰值128MiB，1220次实际保存/读取，wrapper与host清理全部通过。补充协议target=true，原v7的1/9不变。
- s3真实诊断已正确区分训练batch1和eval初始化张量batch16，并给出ready结果；模型无claims，仍是未验证的声明来源状态；没有生成或运行新patch，不能算GPU修复通过。
- nanoGPT最后一次真实诊断已读对32×1，并提出16×2；仍把script_args索引错误声明为execution_argv索引，且提出禁止的block_size缩减，被现有来源/策略检查拒绝。它的完整修复仍未解决。
- 全部4次真实诊断调用均结清，无SDK重试。模型记账费用 **$0.20808488**，仅现有赠送额度；原共享池仍为$9.99964904，保守剩余$4.823164724。79个budget runs关闭、461个attempts结清，无halt或未结清项。没有充值或扩池。
- 未启动新的九场景campaign，不把辅助数值复核或diagnosis-only probe计入整体成功率。

真实诊断报告：
- [首批三次诊断实测](../diagnostic-probe-20261025T045526Z-428b8f41/report.md)
- [最终一次 nanoGPT 诊断实测](../final-nano-diagnostic-probe-20261025T050212Z-b19ed759/report.md)

## 最后仍需讨论的目标选择

1. **s2验收拆分**：建议保留旧结果，另立版本化、预先校准的分类准确性fixture与容量修复fixture。当前固定state下，40%与“基线超22GB再救活”不能同时成立；不建议通过事后降阈值解决。
2. **精度对照政策**：建议产品默认继续禁止精度变化；独立评测显式比较strict与allow_precision。现有default/strict等价不能作为两种不同实验条件。是否采用这个新版对照定义需要决定，旧结果仍保留。
3. **剩余修复可靠性**：s7必须保留原参数更新语义，nanoGPT仍存在来源引用/策略违例和真实信息缺口。公开通用模式已改善观测并拦截错误，但尚未形成满足本项目全部门槛的修复。不能把“存在公开思路”写成已解决。

原6/9目标、fp32/bf16容差、性能门槛与历史失败证据均未降低或删除。

## 集成回归与交付

- 首次集成运行在独立复核加强磁盘证明检查时主动中断；中断日志和收据保留，不记作通过。
- 第二次完整回归为 **2,337 passed、1 failed**。唯一失败是旧测试要求整条调用记录不含提示正文；新增专用 request_evidence 字段本来就保存经过限制和脱敏的请求。修复只涉及测试，明确专用 payload 与实际运输正文相等，预算字段、其他 metadata 和预算数据库仍不包含正文。相关64项测试通过。
- 最终完整回归 **2,338 passed，562.33秒**，257个源码/配置/提示词/测试条目前后及当前一致；原PLAN与guard哈希保持不变。[完整收据](full-regression-20261025T051427Z-c9f092a7-receipt.json)、[完整日志](full-regression-20261025T051427Z-c9f092a7.log)和同名前缀的源文件清单均保留。
- 使用原有离线 guard，禁止真实模型/API、生产凭据/数据库和GPU任务。所有生产代码、提示词和测试在最终运行开始后冻结；原 PLAN、MVP manifest、扫描配置不变。

- Ruff、格式、pre-commit与提交前history/staged密钥扫描全部通过，零密钥发现。源码版本[0792ab7](https://github.com/xiaodouzi666/headroom/commit/0792ab7c288b98489e8f3e68668d8e00eb5e7192)已推送并核对远端一致。
- 现有127.0.0.1:8765预览已刷新到该源码版本：健康、队列空闲、runtime已配置；257个源条目与完整回归一致，旧profile和预算账本不变。没有发起UI修复、模型推理或GPU任务，也不据此声称浏览器全流程验收通过。[预览交付收据](../preview-research-20261025.json)。
