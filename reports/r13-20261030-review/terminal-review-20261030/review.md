# R13 终态独立审阅

R13 已执行完整固定九项，新结果为 **1/9**，仅 `s8_two_models_resident` 达到内存目标；原门槛 **6/9** 未达到。没有混入旧 best、跨轮 union 或 R12 的结果。

首因原始类别匹配为 5/9，其中通过诊断合同且类别正确的只有 2/9；可进入补丁阶段的诊断为 1/9。保存的 round 01 可能包含同轮有界补充，并非必然是第一次 HTTP 回复。s5 与 nanoGPT 的首因真值仍未验证，未当作对或错计入。

| 场景 | 状态 | 目标 | 首轮诊断 valid / ready | 阻塞 |
|---|---|---|---|---|
| s1_batch_too_big | needs_human | 未通过 | False / False | INVALID_EVIDENCE_DEPENDENCY |
| s2_capacity_v2 | needs_human | 未通过 | False / False | INVALID_EVIDENCE_DEPENDENCY, INVALID_EVIDENCE_DEPENDENCY |
| s3_eval_no_grad_missing | needs_human | 未通过 | False / False | INVALID_EVIDENCE_DEPENDENCY |
| s4_loss_accumulation_graph | needs_human | 未通过 | False / False | INVALID_EVIDENCE_DEPENDENCY |
| s5_fragmentation_varlen | needs_human | 未通过 | True / False | needs_more_info |
| s6_full_vocab_logits_fp32 | needs_human | 未通过 | False / False | NUMERICS_CHANGE_FORBIDDEN |
| s7_frozen_params_optimizer_state | needs_human | 未通过 | True / False | needs_more_info |
| s8_two_models_resident | completed | 通过 | True / True | — |
| nanogpt | needs_human | 未通过 | True / False | needs_more_info |

s8 第 1 轮补丁被保留，峰值从 3,100,141,568 降到 121,791,488 字节，下降约 96.07%；保存的完整 backward scalar series 比较为 identical。其他八项均停在 needs_human。九项均有 cleanup、时限与执行认证记录通过；这不代表九项修复成功。

费用使用模型账本美元口径，不能当作含税账单或已知实际总支出：

- R13 新运行的保守计入/保留额：**$0.64941416**。实际总额仍为 `null`；其已知实际部分小计为 $0.62119778，不能替代未知总额。
- 旧 R12 完整保留额：**$0.01644864**，实际仍未知，完整保留在 starting pool。
- 整个开发池合计：**$0.66586280**；剩余 **$4.224641600**。费用边界全部 resolved，实际并非全部已知。没有充值、放大预算或释放 R12 保留款。

API 可读 staging 已生成且通过现有 registry reader 与 product projection；没有写入 live public-evaluations/public-evidence，没有发布。源 campaign、报告、模型调用、控制器与代码均未修改。独立 source pins 审核由另一审阅报告记录。

可审文件：`summary.json`、`terminal-audit.json`、`projection-receipt.json`、`staging/public-evaluations.json`、`staging/published-evaluations/r13-terminal-20261030.json`。
