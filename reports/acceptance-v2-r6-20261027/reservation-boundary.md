# R6 Ultra 请求预留上界核查

核查日期：2026-10-27。范围：只读代码、冻结的历史价格/能力证据和公开官方文档；未调用推理、计数或模型目录 API。仅新增本文档，不修改 profile、cap、budget、ledger 或评测标准。

**结论：保留当前 full-context 预留规则。** 原计划没有明确要求“每次请求都按 1,048,576 输入 token 预留”；这是后来审查形成的保守成本上界。当前没有已验证的、可替换它的逐请求 provider 输入 token 上界。预算不足不能通过近似 token 数、预计实际费用、释放未知费用或转移评审预留额度来绕过。

## 当前数值从哪里来

冻结的 `reports/live-campaign-20261025/pricing-reviewed.json` 将 Ultra 的输入上界记录为 1,048,576，依据为完整 advertised provider context，并明确不依赖本地 tokenizer 上界。其输入/输出价格分别为每百万 token $1 / $3，缓存输入为 $0.12。

`headroom/runtime.py:27` 的 `BillingBound` 及 `upper_usd` 使用：

```text
(prompt_token_ceiling × max(普通输入价, 缓存输入价)
 + 本次输出 cap × 输出价) / 1,000,000
= (1,048,576 × 1 + 16,384 × 3) / 1,000,000
= $1.097728
```

这里的输入 ceiling 是 profile 中已审查的固定值；请求体检查只确认请求处于已审查的字节数域（当前 8,000,000 bytes）和输出 cap 域，并不据本次文本长度降低输入 ceiling。即便一次既有补充请求关闭 thinking，只要输出 cap 仍为 16,384，预留上限也不变。

**预留不等于实际扣费。** 已知有效 usage 结算后按实际费用记账；没有实际费用但有有效上界的记录仍保留相应金额。账本的 `actual_total_usd=null` 不能解释为零费用。当前这条规则限制的是派发前能够担保的最坏费用。

## 原计划与已实现机制的区别

`docs/PLAN.md:135` 和 `:247` 的证据包 token 预算/裁剪，使用本地近似计数来控制证据量；`:306` 的预算守卫要求预算耗尽时停止。这些要求没有规定按 full context 预留，也没有把近似计数定义为 provider 计费上界。

| 现有机制 | 可以证明 | 不能证明 |
|---|---|---|
| `BillingBound` | 冻结上下文 ceiling、价格、输出 cap 下的保守预留 | 本次请求实际输入只有多少 token |
| `PromptAuditor`（`headroom/llm/preflight.py:306`） | 固定 NVIDIA tokenizer/template、指定开关下的本地渲染与计数 | Nebius 部署的 tokenizer、模板、默认值、预处理和额外 schema 注入完全相同 |
| `LocalEstimateAdmission`（`headroom/llm/admission.py:91`） | 本地计数乘安全系数、加常数后的估算 | 确定性 provider 成本上界；代码明确实际费用可能超过该预留 |
| 返回的 `usage.prompt_tokens` | 那一次已完成响应的 provider 用量证据 | 下一次不同请求派发前的上界 |

`PromptAuditor` 明确输出 `provider_tokenizer_match_verified=false`、`provider_billable_token_ceiling=null`、`provider_cost_upper_usd=null`；并记录固定 NVIDIA tokenizer 配置为 262,144，而当时 Nebius 目录为 1,048,576，二者不能直接当作同一部署证明。JSON schema 等 provider-only 字段也单列为未建模域。

`headroom/budget.py:259` 起的共享 strict-pool 门禁和 `:343` 起的 `reserve` 拒绝将 local estimate 用于当前 actual-usage 严格资金池。因此，已有本地 tokenizer 工具并不意味着已有可安全切换的较小计费上界。

## 官方资料支持到什么程度

- [Nebius Chat Completion API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion) 明确 `max_completion_tokens` 覆盖可见输出及 reasoning；返回示例包含事后 `usage.prompt_tokens`。它还在 `max_tokens` 项下描述输入加输出不能超过 context length。这没有给本次请求提供一个派发前、更小的实际输入保证，也不能未经验证就把另一输出参数的约束搬到当前 Ultra 配置。
- 本次查阅的 [Nebius 官方文档索引](https://docs.tokenfactory.nebius.com/llms.txt) 和上述接口页，未找到为当前 Ultra 部署提供计费一致性保证的计数端点或已承诺的硬输入 cap。这里的结论是“未找到足够保证”，不是断言 Nebius 绝不存在其他能力。
- [Nebius Structured Output 文档](https://docs.tokenfactory.nebius.com/ai-models-inference/json) 区分消息文本与 `response_format` schema，建议同时提供。仅计消息正文不能自动覆盖所有服务端处理。
- [Hugging Face chat template 文档](https://huggingface.co/docs/transformers/en/chat_templating) 说明聊天模板、特殊 token 和 generation prompt 都影响实际 token 序列。这支持固定本地模板的诊断用途，不能证明服务商采用完全相同的处理。
- [vLLM 官方 OpenAI-compatible API 文档](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/) 提供渲染/预处理及 `truncate_prompt_tokens` 等机制，说明实现服务端可控输入是可行的；**不能据此推断 Nebius 的托管接口暴露或执行同样能力**。截断还会改变输入证据，不能静默启用。

## 若以后需要更紧上界

至少需要新的独立保证，例如：

1. Provider 提供与计费处理一致、绑定相同部署版本及完整请求的预处理/计数保证，并处理计数与派发间的版本漂移；或提供确实执行的硬输入 cap 和超限拒绝保证。
2. 对 tokenizer、chat template、所有默认值、schema/tools 注入及预处理建立与当前部署一致的完整证明，再限定可接受请求域。样本 usage 一致只能支持测试样本，不能单独证明普遍上界。
3. 重新审查 admission/profile 的变更、财务守卫、反例测试和冻结证据。任何无法覆盖的请求继续拒绝或沿用当前上界。

当前不实施这些变更。也不根据“UTF-8 字节数通常大于 token 数”作计费保证，因为未经验证的模板扩展、额外注入和 provider 预处理仍是缺口。

## 资金边界

“原开发预算尚有余额，但下一次 Ultra 无法预留完整上界”与“provider 账户余额耗尽”是不同状态。账本只反映本项目获准使用的开发额度及保守费用；本轮未查询 provider 账户余额，不作余额耗尽判断。

现有评审预留、税费/舍入预留及所有历史未知费用保持不变。是否可派发仍由当时同一账本事务中的 run、daily、lifetime 与完整请求预留检查决定，本文不授予新额度或新调用权限。

## 本地证据版本

- `docs/PLAN.md`: `e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56`
- `headroom/runtime.py`: `d35ed92b01c1559337dd5f921c58132d7e6e4c8134701495466a1e1290209bc9`
- `headroom/llm/preflight.py`: `4b8871d9b7ba6084bea8b42d3f8e55c8762f1d08650e417982c8835e5d87e5ae`
- `headroom/llm/admission.py`: `a218e98d8c39fbebc1233ccc48b8fc7cfd196c33698692aaeb8de62c0ec3bb5c`
- `headroom/budget.py`: `158e6a1aaa9dc505e09cb47e9ca657ccf7bdffbbdb49bddea7d78cc75110fb4c`
- `reports/live-campaign-20261025/pricing-reviewed.json`: `635c6b90216acfe0505e4f53f0685c8183bc3bc632fff376c3bfcefd7e7eb829`
- Active profile SHA：`e115c2ff818c8a87853771742deff65dbba1f3a944ff6eae7636bf617bc7149e`（本次未修改）。
