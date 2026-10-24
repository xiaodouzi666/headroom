# MVP v3 独立只读审计

原 PLAN 失败后第 2 次修复迭代未通过。固定分母仍为 9；前 5 例实际调用，后 4 例由主代理关闭未来 admission 后运营停止。原 auditor exit 2、accepted=false，未将未执行项缩出分母。

| 场景 | 调用 | Super响应 | git apply + compile 成功 | target_met | 停止原因 |
|---|---:|---:|---:|---|---|
| s1_batch_too_big | 27 | 20 | 0 | false | diagnosis_needs_more_info |
| s2_fp32_adamw_1b | 7 | 4 | 0 | false | diagnosis_needs_more_info |
| s3_eval_no_grad_missing | 8 | 4 | 0 | false | diagnosis_supplement_exhausted |
| s4_loss_accumulation_graph | 31 | 24 | 0 | false | max_rounds_reached |
| s5_fragmentation_varlen | 5 | 2 | 0 | false | diagnosis_needs_more_info |
| s6_full_vocab_logits_fp32 | 0 | 0 | 0 | false | 运营停止，未派发 |
| s7_frozen_params_optimizer_state | 0 | 0 | 0 | false | 运营停止，未派发 |
| s8_two_models_resident | 0 | 0 | 0 | false | 运营停止，未派发 |
| nanogpt | 0 | 0 | 0 | false | 运营停止，未派发 |

全部 54 次 Super 响应均 finish=stop、reasoning_tokens=0，completion 54–557，保持原 4000 上限。52 份非空 diff 均无真实 LF，也没有 literal backslash-n，全部结构拒绝；另有 1 份空 diff 且没有配置变更，被 NO_CHANGE 拒绝。因此总拒绝数为 53，并非 53 份非空 diff。剩余 1 份为空 diff 的 CLI-only 静态应用。visible JSON 解码后的 diff 与 parsed.diff 一致。

唯一静态应用是 s5 的 CLI-only 配置，空 diff 与 grad_accum_steps=4。没有 git apply/py_compile，不计 T1.5 成功。真实候选 Lab 报参数不识别、SystemExit2，验证 completed=false/target=false，随后 revert。s4 workflow completed 仅表示轮数耗尽，无保留配置。

T1.5 原分母 8、门槛 6/8 未改；git apply + py_compile 观察到成功 0/8。原 auditor 的 unknown 项保留，全部 Super 响应均计入输出 cap 检查。

78 次调用逐条 budget_attempt_id 绑定已结算账本；known subtotal USD 0.50587762，五个 Nano verified bounds 合计 USD 0.00276750，保守总占用 USD 0.50864512，完整 actual total 仍 null。累计129 attempts/35 closed runs，无 pending、unresolved 或 halt；known USD 2.01733180，保守 USD 2.03679916，授权池余 USD 7.96284988。旧 runtime .01644864 与外部429 1.049344 未释放；profile 恢复原 a15ee9a357b4e0c41aeb46219081066c4d5a2299a777f8f87127dde60118026c。

此公开报告仅含状态、数量、路径及hash，不复制私有响应正文。审计者未调用模型/GPU、未读取密钥、未重放补丁、未改 source/profile/ledger。

- 原审计 mvp-v3-audit-v2.json：8f154e10dd9205822705bb1f468e2527fce7282c745b38c31e0930eefa7b1fe5
- metadata审计 mvp-v3-repair-review.json：01c7c52bb5f60054ff48972027c381f56fa0cf8c844950018ecf23307c645bc8
- 原campaign：2ff4b0d4ae537eef1026239896f388a592537727dae331d42f643849b12c8b14
