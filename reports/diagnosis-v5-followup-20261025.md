# T1.4 v5 三个未完成诊断：只读复核与待比较候选

状态：仅复核既有响应与当前源码。未改生产代码、提示词、schema、真值或评分，未重跑诊断/模型/GPU；原 v5 失败保留。本报告不预测下一次 MVP 会成功，也不把下面建议视为已实施。

## 可确认的事实

三例均有有效实际栈引用、首因与既有判分真值一致，但这不等于可执行诊断通过。三份冻结 messages 的 system 文本均与当前 headroom/prompts/diagnose.md 完全一致；动态 schema 只约束字段值，不能证明 title/description 中的建议语义遵守政策。

| 案例 | 原 v5 结果 | 具体原因及证据 |
|---|---|---|
| s1 | valid=false，needs_more_info=true，requires_supplement=false | fix3 缩短序列、fix4 缩小 width、fix5 缩小 depth；全部不允许。原报告记录 fix3/fix5，width/decrease 文本匹配漏项已在之后单独修正，原结果没有重评。fix1 说 batch=32,width=256,depth=2，但冻结 evidence 源码行72明确非 tiny 为 (256,192,2048)；还建议不存在的 --sequence/--width/--depth 参数。fix1/2 将 batch 降低与有效 batch 保持拆成两项，且响应自己说明节省重叠。required_saving_gb=null 是 OOM 完整需求未知的真实状态，不能用一次 failed allocation 伪造精确削减量。 |
| s6 | valid=false，needs_more_info=true，requires_supplement=false | fix2 明确提出 bf16/autocast，却填 numerics_impact=none,requires_policy=[]；fix3 改词表/损失近似。同一条建议的 risk 再附“若不允许则不要用”不能使非法建议合法。fix1 声称要把手写 log_softmax+nll_loss 换成 F.cross_entropy，但冻结源码行107已经是该调用；内部 _log_softmax 栈不等于用户手写该操作。label smoothing 也不是原目标的等价默认变换。模型把栈内部实现误当可直接消除的用户代码，证据并未缺失这一行。 |
| s7 | valid=true，needs_more_info=true，requires_supplement=false | 没有政策/ref/schema issue；自身估计 8–9 GB 大于请求5.3459426304 GB，但仍因 unknown 类别和“需要重测”而要求信息，因此 ready_for_patch=false。fix3 把 foreach=True 称为 fused，且无实测支持其省显存/等价保证，不能据此认定可行。源码本来是 foreach=False；freeze/head-only 的意图来自源码注释，不能把意图自动当成与现 baseline 数学等价的证明，仍须原数值门。 |

## 当前为何没有自动补充

- diagnose.py:383–406 仅在 needs_more_info=false、required saving 已知、估计总和不足时产生 INSUFFICIENT_EXPECTED_SAVING 补充。三例都显式 needs_more_info=true，因此不满足触发条件；s1/s6 的所需削减量还是未知。
- diagnose_with_router 默认最多一次 supplement，但只在上述 requires_supplement 为真时调用。T1.4 acceptance 独立驱动显式 max_supplements=0，三例各只有一次真实调用，符合其诊断单次验收范围。
- orchestrator.py:606–633 对显式 needs_more_info 停止，不会跳过该标志给 Super，亦不会静默删除非法步骤后执行其余步骤。此 fail-closed 行为应保留。
- 当前 schema 的 permission enum / numerics enum 阻止非法字段值，但模型仍可在自由文本中提出违规操作并填合法字段；后置语义/patch/honesty/真实数值校验不可移除。不能从这些响应归因“reasoning=False导致失败”或推断再次增加同义警告有效。

## 等待真实 MVP 后再决定的通用候选（未实施）

1. **先清楚区分未知和行动阻塞。** 若 MVP 也出现同类停止，可在通用请求/提示中解释：required_saving=null 表示无法从 OOM 证明完整需求，不自动意味着无法提出可验证的保守实验；未经 GPU 验证是每个候选的正常状态。只有缺少会改变计划正确性/政策合规性的输入时才请求更多信息，明确缺什么。保留 needs_more_info=true 的停止权，不将其默认改false，也不强迫给节省数值。
2. **校验反馈驱动的有界重写，先离线证明。** 若 MVP 再次生成政策违规自由文本，可考虑在既有最多一次 supplement 槽内返回精确 issue codes/fix IDs、原 policy 与相同 evidence，要求重新生成整份合法诊断或明确请求更多信息；不追加总调用上限，不吞掉首份失败，不过滤违规条目冒充成功，不自动解除显式信息请求。T1.4 的单次诊断驱动仍保持 max_supplements=0；未知费用/预算阻断仍停止。应由后续授权实施而非本报告直接调整。
3. **让建议先绑定实际源码与运行分支。** 后续只在真实失败复现后评估通用 source-anchor 自检：先核对建议引用的变量/CLI 参数确实存在、运行条件确实被选中、拟替换操作尚未已经存在；库内部栈不是用户源码。使用当前 evidence 的带行号源码，不注入 s1/s6/s7 的名称、真值或预期答案。不能据 AST/注释直接证明损失等价或节省。

最小离线回归边界：含 tiny/full 双分支的通用配置；已调用某库 API 却在其内部出现算子栈；自由文本违规但 enum 字段合法；合法方案仍需实测与真正缺必需信息两类 needs_more_info；违规反馈最多一次且原始失败保存；动态 refs/permission/numerics、8192 output cap、reasoning=False、预算/数值/步数门完全保留。不得用该离线测试重新评分 v5。

观察后再决策：先比较真实 MVP 的 stop_reason、非法 step ID、现有源码锚点、needs_more_info 缺项及下一阶段实测结果；若当前已通过，不应为三个历史响应继续叠加提示词。s7 即使解决“需要验证”的表达歧义，真实数值等价仍可能失败，不能承诺提升通过率。

## 审计输入 SHA256

runs/acceptance/diagnosis-prepared-20261025-v5/preparation.json | 38067 bytes | 593512be812d4d70e852ab9047bee2b1928e334c67c4611eabcb01a7c2bba788

runs/acceptance/diagnosis-prepared-20261025-v5/execution/s1_batch_too_big/diagnosis.json | 11925 bytes | 39a6b0e5948e90968cc8250e51df3d23b35114bc7b36526d7edd824ff5ca7878

runs/acceptance/diagnosis-prepared-20261025-v5/cases/s1_batch_too_big/messages.json | 79825 bytes | 89d51eff84fd44a3e9f7abe8fe8a153c3a750ff81167dde63c98a47411e4b8ca

runs/acceptance/diagnosis-prepared-20261025-v5/execution/s6_full_vocab_logits_fp32/diagnosis.json | 11402 bytes | 49fec436a1d1bd8848b105a2da83daf546caa3ac085cc6c778131dfd8ddccc4c

runs/acceptance/diagnosis-prepared-20261025-v5/cases/s6_full_vocab_logits_fp32/messages.json | 80388 bytes | 2bd6a3600330d215d859a8c24cb3af85dcbd77006a48b13cfc115d1d6c6d6ffe

runs/acceptance/diagnosis-prepared-20261025-v5/execution/s7_frozen_params_optimizer_state/diagnosis.json | 10531 bytes | bc39aac81d20435f596f728715f0b5c868132e263b192ce23bcea77d7f66aee7

runs/acceptance/diagnosis-prepared-20261025-v5/cases/s7_frozen_params_optimizer_state/messages.json | 94372 bytes | 87d7a4e97b9dad90be782a95016bc9d9974d0d2066989ce734fe09fd6e0b2505

headroom/diagnose.py | 18741 bytes | 06d0ffa6043247a6edc3120a5d86b76617aa2ab4285d0f6397c7ddd403cbb33b

headroom/diagnosis_schema.py | 3590 bytes | 194f900ce1bf741566014af6de89f988954e3bd8f7bdd3ba01bd6b7175d32875

headroom/prompts/diagnose.md | 7224 bytes | 861c4cfaecd9462fd1550d313f875249d64ae1a047234c26c404a10273be0871

headroom/orchestrator.py | 49004 bytes | 7d96fb02b7abdcc4a93b5d6c504579fe4d129d8394f8994a6fe7c0e202d5a718

headroom/acceptance/diagnosis.py | 36138 bytes | 5a0599ce624b6761b96e2bc40af690220f4c439a410cbc1e9ef55286b6df6d57

headroom/schemas.py | 1362 bytes | b4d6f8c27a7047b46bd8d4b82f7a109f6f858c741b0c28385d4b3aa03df7a364
