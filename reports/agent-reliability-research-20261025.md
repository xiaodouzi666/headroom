# Agent reliability：公开方案核实与有限契约修复（2026-10-25）

本报告对应的研究与离线实现环节只执行资料检索、源码/保存证据检查和离线测试，没有发起模型请求、GPU运行、凭据读取或充值；后续真实诊断 probe 的调用与结果另记收据。公开资料提供了可实现的契约与反馈模式，没有证明 Headroom 的九场景准确率会达到原门槛。v7 历史结果仍为目标 1/9，不重算、不改验收标准。

## 核实的主源及适用性

| 主源 | 已核实内容 | 对本项目的适用边界 |
| --- | --- | --- |
| [Nebius Structured output & JSON](https://docs.tokenfactory.nebius.com/ai-models-inference/json) | 区分 JSON schema 与任意 JSON；建议文本指令和请求 schema 一同提供，并处理无效 JSON/拒绝。 | schema 约束输出形式；不能证明配置值、训练数学或显存估算正确。继续使用 Nebius，不切换 provider。 |
| [Nebius Function calling & Tools](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling) | 模型提出工具和参数，客户端负责执行，再把真实结果反馈。 | 工具调用/格式支持不是任务正确性证明。 |
| [Anthropic Building effective agents](https://www.anthropic.com/research/building-effective-agents) | 简单可组合工作流；中间程序检查、环境事实反馈和最大迭代停止条件。 | 借用工程模式，不把 Claude 的效果数字外推给 Nemotron。 |
| [Anthropic Writing effective tools for agents](https://www.anthropic.com/research/writing-tools-for-agents) | 明确输入输出契约，可操作的错误反馈，原始对话审计及独立评测。 | 支持机器事实核对和有限修复；不支持按测试场景硬编码答案。 |
| [Anthropic Effective context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) | 保留高信息量上下文，明确边界，避免堆积大量模糊/冲突提示。 | 优先把观测与来源讲清楚，不能只靠加长 prompt 宣称解决语义错误。 |
| [NVIDIA Nemotron-3-Ultra Dynamo recipe](https://docs.dynamo.nvidia.com/dynamo/v1.5.0/recipes/nemotron-3-ultra) | 特定 bundled OSS vLLM 的 reasoning + constrained JSON/tool 输出存在已记录限制，需验证输出。 | 这是指定 Dynamo/vLLM 运行时限制，未证明 Nebius 有同一问题。当前诊断调用已使用 reasoning=False，不能据此解释 v7 误读。 |

以上页面均已打开正文核对；不采用搜索摘要替代正文证据。Nebius 的 [Observability](https://docs.tokenfactory.nebius.com/ai-models-inference/observability) 是专用端点的指标观测，不能补回本项目历史请求正文。

## 当前代码与历史证据

- `orchestrator.py` 已构建保留执行参数；`diagnose_with_router` 已把 execution_context、candidate_evidence、verification_feedback 传入。此前 evaluation 的 initial-messages 重建副本缺了部分字段，只能证明审计副本不完整，不能反推实际请求没有这些字段。
- v7 nanoGPT 的保存响应一处识别 batch 32，却在计划中使用源默认 12/40 → 8/60。这是响应对配置来源使用不一致，不是已经证明的传输丢失。
- v7 s3 把训练 batch 1 与 eval batch 16 混用；保存响应仍含有效 no_grad 提案但 needs_more_info=true。不能强行清除该标志，或把提案记作执行成功。

## 已实现的通用契约

修改 `headroom/schemas.py`、`headroom/solver_context.py`、`headroom/diagnose.py`、诊断/patch prompts 及 orchestrator 的共享 context 接线；新增 `tests/test_diagnosis_invocation_grounding.py`、`tests/test_runtime_input_observations.py`。

1. 可选 invocation_claims 指定 argv 来源、零基 token 索引和精确原始 token；保持旧响应兼容。仅核对实际保留的可见 token，不解析/执行任意目标 Python，也不把源默认值认作最终配置。
2. 可选 evidence_requests 明确字段、missing/ambiguous/policy_infeasible/insufficient_saving/other 原因及具体说明。只有声称完整提供的 script_args/execution_argv 字段缺失时，才产生确定性矛盾反馈。
3. 具体 token 不符或上述明确矛盾使用原有 max_supplements 额度返修，不增加独立重试池。返回完整诊断后重新验证；从不直接改写 needs_more_info。
4. 截断尾部、脱敏位置、未知字段和真实策略/数学疑问保持 unknown。原始自然语言 notes 不做关键词意图推断。
5. invocation_provenance 区分 unverified、unsupported、contradicted、observed_tokens_verified；后者仅表示模型声明的 token 相符。target_effective_configuration 始终明确 unverified。空声明不得被解释为配置核验通过。
6. 新增 runtime_input_observations，从现有 `pairing_capture` 提取已捕获张量形状和 optimizer 输入关联。必须满足已审核的协议/源合同、当前 source SHA 匹配、当前 run_id、完整捕获及所需 20 次 update；不符则只提供 unsupported/unverified。共享 execution_context 接收 **current_result**，不会偷偷回退到原 baseline 或被拒绝候选。诊断和 patch 都能看到这个范围明确的事实。

### s3 已存在的运行时证据

只读核对 v7 `jobs/52bb8129723241889337486bcb187f63/lab/3809bd3afadd445884873eafdc2041ec/result.json`：pairing_capture.complete=true，实际初始化 train_inputs shape 为 `[1,512,768]`，eval_inputs 为 `[16,512,768]`；20 条 update 的 optimizer-linked effective_batch 均为 1，且每次实际关联一个 training forward/backward。源 SHA `7fedcae13989b309cc5a034e62284094829057654aebb2e716c3413dfb0fea67` 与捕获源相符。这些值由运行时事实进入新 context，未硬编码进生产规则。

现有 adapter 只支持被审核的 standalone 源合同，不能外推到 arbitrary Python。其他 named tensors 的初始化形状有证据，但各自 forward 使用次数未单独记录；不把 eval 初始化形状提升为完整 eval 动态路径证明。

## 离线验证

`pytest -q tests/test_diagnosis_invocation_grounding.py tests/test_runtime_input_observations.py tests/test_diagnose_schema.py tests/test_diagnosis_schema_constraints.py tests/test_solver_context.py`：**175 passed**。覆盖历史响应、错用默认值、真实歧义、完整/不完整参数、脱敏、未知上下文、单次补充和 0/1/3 补充上限；另覆盖实际 runtime 形状、当前选中 run/source 绑定、异源/不完整/伪造合同/错误 update 保持未知，以及共享 prompt 传递。相关文件 Ruff check 通过并已格式化。

这些测试证明契约实现及有限调用控制，不证明模型会总是声明所需 claims，也不证明未来规划正确率。未对历史 v7 响应补造 claims，更没有把其失败转成成功。

## 尚不能由本修复证明的事项

- 任意 Python 目标最终应用了哪些参数，需要目标运行时配置证据或被验证的解析适配器；仅看 argv 或静态默认值不足。
- s3 的 optimizer 输入/初始化形状证据已接入，但模型是否真正正确使用仍需行为 probe；所有 eval forward 的细粒度关联也不是现有 capture 的证明范围。不能把模型 eval 标志等同 no_grad，也不能从同名配置推导相同 batch。
- 模型是否更少误读、是否产生有效 patch、是否达到原数值/吞吐/显存标准，仍须在既有预算与轮次约束内做真实行为评测。没有模型侧 guaranteed accuracy 的公开方案。

## 请求审计实现的独立复核

已只读检查 root 的 client/runtime/store/request_audit/evaluation 改动：捕获点为 SDK 序列化后的 HTTPX pre-transport body，记录精确字节 hash 和独立的脱敏副本 hash；不将此称为 provider 接收确认。副本有 256 KiB 上限，不保留 headers；当前运行凭据、指定敏感字段与 bearer 值脱敏。任意源文本中的未知秘密无法普遍识别，代码已明确这个范围。

request_evidence 只能附到角色/模型/attempt 匹配、未结算且未捕获的 pending 行；后续 settlement 合并保留证据，不修改费用事实。hook/store 失败在发送前阻断，原保守费用记录路径保留。initial-messages 仍明确是重建初始副本，补充轮次及真正 prepared body 以逐调用记录为准。未发现需要阻断实现的生产代码缺陷。

合并 focused 检查发现一项新审计测试夹具错误：candidate_evidence 用 dict，而既有契约要求 list；向 root 报告后已修正，独立重跑 `tests/test_llm_request_audit.py` 为 **9 passed**，`git diff --check` 通过。上述 175 项不含这 9 项。


## 最后一次通用 argv 可读性补强

在既有保留 argv 上新增 `invocation_reading_aid`。仅将可见 `--name=value` 做词法拆分，保留原索引、完整 token、字符串值和重复顺序。space 参数、boolean 和位置参数不猜语义；不选重复项的优先级。秘密位置、原截断尾部、无效完整性 metadata 均保持 unknown。入口脚本和完整启动命令分开呈现；启动 token 可能是解释器、launcher 或直接可执行脚本，不能用入口文件名替换原数组第零项。

reading aid 是独立顶层字段，位于长 evidence_markdown 之前，ASCII wire 大小限制 4 KiB，另有明确视图截断计数；并纳入既有 64 KiB combined solver context 上限。原 execution_context 的 16 KiB 上限、原始 argv、结构化 token checker、needs_more_info 和补充次数均不变。没有针对 nanoGPT、batch 或具体期望数值的规则。

最终相关 focused 组合（含 `test_invocation_reading_aid.py`、grounding、runtime observations、diagnosis/schema、solver context、request audit）：**195 passed**；Ruff 与 diff 检查通过。源码/测试已冻结。这个测试结果证明词法视图和边界处理，不承诺模型在最后一次诊断中会停止误读；不触发新增修复循环。
