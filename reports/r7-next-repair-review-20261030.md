# R7 主诊断剩余阻断只读审查 — 2026-10-30

审查 HEAD：06f99fc19d4849d8589b701de908ce35620f3823；工作树含其他代理正在冻结/验证的候选。只读保存的 R7 九场景诊断、report、source 与当前主提示，不改源码、历史、validator、阈值，不调用模型/GPU。当前主提示与 R7 release 6c7cde25 的 diagnose.md 无差异，已有 515 行；不能把追加重复规则当成已解决。

原结果仍为目标 1/9（要求 6/9），类别文字匹配 7/9，要求诊断有效后 5/9，首轮有效且可补丁仅 2/9。下列是修复候选，不是新实测。

## 九场景实际阻断

| 场景 | 保存的实际阻断 | 本轮已在其他工作覆盖 / 仍缺 |
|---|---|---|
| s1 | 首轮诊断可执行；补丁 overlap，随后三次删掉原外层 update 循环，TRAINING_TRUNCATED 正确拒绝；第二轮又说源码 hidden/block 未定义，实际 lines 27–29 可见；OOM 前零已完成更新也是真未知 | root 的 step/loop anchors 直接针对补丁；字面源码误读与真实未观察更新仍须区分 |
| s2 | 完成 20 更新，但旧 pairing_capture 不支持此 source；模型还没看到输入/update 关联就终止 | plan 代理正在加 s2 source-pinned pairing；旧观察不回填 |
| s3 | 两次完整回答均提出 eval no_grad，再附加已 batch=1 的拆分/检查点“备选”；备选 blocked IDs 与 scope 不合约，且把已提供 input/update 字段当缺失 | root 的 availability 叶字段可纠正字面缺失；仍需避免把不必要备选放进当前 plan |
| s4 | 唯一目标达成；首 5 个 backward-loss 与 offload reference delta 0，并非 20 loss/参数 bitwise | 保持历史，不纳入新修复宣传 |
| s5 | 有效但 needs_more_info；把未来候选的实测 saving 当成当前缺失输入，另混入手写 GELU backward；真实未知 stack/参考能力不可清除 | 提示已写 planning≠verification，仍未遵守；不把缓存差解释为碎片 |
| s6 | 有效但 needs_more_info；计划写按 vocabulary 分块独立 log_softmax/nll_loss，同时又要求每 token 见完整 vocabulary；还缺实际更新关联/producer 证明 | 语义矛盾未进入执行，不是已验证实现；不能仅关闭 blocker 后执行此计划 |
| s7 | 首因 optimizer_state 对，但诊断 invalid；按“想只训 head”注释提议冻结实际全量训练 backbone，另凭空引入 vocabulary-chunked CE；source-visible 的请求又标 missing | 实际 AdamW(...foreach=False) 已设置，不存在“关 foreach”简单收益；冻结会改变既有目标；此问题不是再添一条禁止冻结规则可证明解决 |
| s8 | 提议去掉当前 distillation_weight=0 的 teacher，再额外加仅估 .025 GB 的 microbatch；后者 missing prerequisites 阻断全局 | 保存的主步估算 2.78 GB 已高于所需约 .62 GB；需源码/RNG/placement/验证约束，不能自动删除 teacher 或强清 global flag |
| nanoGPT | 保存 report 为 ResponseValidationError，无 diagnosis.json/无 patch；两次 Ultra 合计 4,000 output tokens（各调用单 cap 2,000），无保留在该 report 中的 finish_reason | 与 cap-bound 输出一致，但仅凭数量不能证明两次都是截断；不能误归为 GPU candidate failure，更不能用扩大 tokens/calls 替代定位 |

s3 独立主步保存估算 .805306 GB 高于约 .487 GB 需求；这只是模型估算，不是有效性/数值/真实节省证明。

## 最多两个建议，按优先级

### A. 收紧策略选择的顺序，替换已有泛化 microbatch 优先段（小提示修改）

当前 279–294 行“activations first consider microbatch”容易让 s3/s8 追加无关训练拆分；更晚 384–392、456–468、508–515 才说明独立主步/最小语义改动。这些规则并非不存在，优先级和结构分散。建议用短决策段替换前者，不增加输出 cap/调用数；其余安全约束继续存在。可审阅替换文字：

> Select a repair for the evidenced producer, lifetime and training/evaluation path before enumerating strategy families. If one supported independent candidate already covers the required saving, return that candidate without adding unrelated batch, checkpoint or loss rewrites. Keep unsupported optional alternatives outside plan and do not borrow their savings. This does not permit a missing prerequisite, an inflated estimate, or a cleared needs_more_info flag. Consider microbatch/accumulation only when the actual training activation peak supports it and the existing policy, weighting, update and numerical-reference prerequisites hold; all existing gates remain unchanged.

这是 selection guidance，不是自动删 plan 的后处理，更不是 validator 放宽。保留真实未满足总 saving 或必要组合时的 needs_more_info。预期 s3/s8 最直接，s5 有机会少生成无根据的 GELU 自定义算子；不保证真实通过。

离线检查：消息仍同 schema/cap/reasoning/call 数；已有 alternative/current scope、batch 禁用、数值拒绝负例仍通过；用保存故障回答确认仍被拒绝，不能将其变“有效”。后续真实调用才可证明模型是否遵守。

### B. 将少量“源码字面事实”提到请求前部，而非增加 500 行后的同类警告

参考现有 patch loop anchors 的方式，增加有上限的 source-only sketch（建议最多 12 条），每条仅原文件 SHA/精确行号/短原文：optimizer constructor 与显式 kwargs/parameter expression；可见 requires_grad 修改与 eval/train 调用；forward 最终返回的 producer/consumer 表达式。用一般 AST 类型选取，不使用 scenario 名或 authored truth；不能推断未出现 requires_grad=False 就一定运行中全量可训练，也不把 .eval 当 freeze。截断/动态/解析失败均显式未知。

s7 可直接把 AdamW(model.parameters(), ..., foreach=False)、backbone.eval()、return self.head(self.backbone(x))、width/depth/classes 的可见 literal assignment 摆在前面，阻止根据名字/注释想象 head-only 已经是许可目标，或虚构巨大 vocabulary logits。s1 的定义/loop 锚点也可同一机制引用。这里是增强输入定位，不填模型结论、不自动认定数学等价。

优先从已有 source span 文档取短段、去掉重复的长语义复述，限制输入增加；输出 schema/tokens/calls 均不变。若本轮需严格极小补丁，只做 A，B 可独立后续提交，不为它增加本轮 live 范围。

离线负例：跨函数/动态 kwargs 不猜；注释含“freeze”不能改变产物；局部 .eval 没有 requires_grad=False 不能产出“已冻结”；同名变量/不完整 source 保持未知；最多条数/文本字节上限；不把源码 literal 标为 runtime observed。之后 s7 才应作最小 live，仍保留所有源绑定、参数更新及数值门槛。

## 不应再当新缺项的内容

当前 orchestrator.py 722–750 已把 invalid + needs_more_info 分类为 diagnosis_validation_failed，不再全称缺证据；R7 旧 report 不改。root 的 availability 叶字段、patch loop anchors、plan 代理的 s2 pairing 正在独立覆盖，不重复建议这些工作。

没有建议第三个泛化 prompt 扩写。仅把已有 515 行再加“不得冻结/按 token 分块/不要索要未来测量”等同义段落，缺少证据证明有收益。

## 证据路径

- reports/r7-20261029/README.md、r7-summary.json、failure-analysis-first3.md
- runs/final48-f3/execution-20261029-v1/jobs/<run_id>/rounds/*/diagnosis.json
- 同目录 report.json、rounds/01/verification-feedback.json 与 lab/*/source/train.py
- s3 ce2e4bf037a84b349d178c5bd661230b；s7 966c277a39cf456f92a58b388a501dbb；s8 f7b8b420a8754127a8e929fe64d81c45；nanoGPT b0a316117611448a8688ceb8fea7781a
- headroom/prompts/diagnose.md 247–257、279–310、337–357、379–392、435–488、508–515
