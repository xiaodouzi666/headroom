# MVP v2 修复路径只读复核

审核时间：2026-10-24T22:40:41.484508+00:00。读取最终 campaign 与已完成 case/attempt，不重写原记录；无模型/GPU调用、无源码或账本写入。

## 最终状态和适用范围

- campaign: runs/evaluation/live/20261024T223453139983Z-b34f1afd/campaign.json，工作流 finished 不表示验收通过；本轮原9场景验收失败保留。
- s1: run e0bde71d5a0e4e67bd33e50acd9956a8，needs_human，target_met=false，最终 stop_reason=diagnosis_needs_more_info；wall=283.708s，未触发480秒deadline。
- 后续8项：运营主动关闭磁盘 runtime profile 后，均 runtime_not_ready/needs_human、0模型调用、0 Lab result，属于**未开展修复的运营收尾**，不是8个独立模型质量失败。未取消 s1 inflight；s1正常完成后才到后续case。
- s1 费用：actual 仍为 null；已知 subtotal 0.14104766 USD + Nano已证明上界 0.00025122 USD = conservative upper 0.14129888 USD；billing_complete=true，无需将上界伪称实际费用。此报告不改账本也不解除任何费用门。

## s1：失败发生在候选执行之前

真实baseline: CUDA OOM，peak_allocated=24750424064 bytes，parameters=101007360，steps=0，capture_complete=True，cleanup_verified=True。唯一 Lab 运行是 baseline。

| Round | Super attempts | 响应截断/过滤 | diff文件结构拒绝 | 已apply/compile |
|---|---:|---:|---:|---:|
| 01 | 4 | 2 | 2 | 0 |
| 02 | 4 | 1 | 3 | 0 |
| 03 | 4 | 1 | 3 | 0 |
| 04 | 4 | 2 | 2 | 0 |

四轮共16次 Super 调用：6次 LLM_RESPONSE_REJECTED，10次 UNSAFE_OR_INVALID_PATCH。所有应用命令为空、compile_exit_code=null；没有 verification.json、candidate GPU结果或最终kept配置。因此 candidate loss、loss delta、candidate parameter equality、peak reduction、目标达成都**未测得**，不能标为数值不等价或修复后仍OOM。

22次模型调用组成：Nano1、Ultra诊断5、Super补丁16。前4次Ultra诊断均 valid=true/ready_for_patch=true；第5次 valid=true 但 needs_more_info=true，正常阻止继续patch。最终诊断主要顾虑未测得的显存缩放和吞吐代价；它没有证明这些候选已真实失败，因为前四轮从未成功应用。

## 已确认的两类协议失败

1. **Super输出上限被reasoning占用。** 共6次Super完成计数达到4000，其中5次reasoning_tokens也为4000，另一次为3962。与6份截断/过滤记录对应。当前 patch.py 的patcher调用没有显式 reasoning=False；原4000总completion门正确保留，但该配置不能保证留出可见JSON空间。下一轮优先评估已证实能力的显式reasoning=False，不能提升4000门来掩盖失败。
2. **非截断响应同样无法构成合法diff。** 10次detail均为“diff must touch between one and twenty files”，在validate_diff内PatchSet无法给出1..20个文件时拒绝；未进入git apply/py_compile。原始parsed.diff未持久化，Store也不保存assistant/proposal，所以目前**不能判定**是缺header、换行转义、只返回说明文字或其他格式。不要据猜测放宽parser、自动修补diff或把空diff当成功。

另一个证据缺口：ResponseValidationError携带response，但patch异常分支仍用尚未赋值的局部response，attempt中的usage/cost为空；完整计费记录仍在Store，没有丢账。下一轮宜复用已有有界响应归档方式，保留可见assistant/parsed proposal和失败diff（权限0600、大小限制、无reasoning/headers/key），再决定精确格式改进。

## 诊断质量附带观察（不是本轮主要阻断）

Round2 notes声称参数1.9M、depth8，而真实baseline参数为101,007,360，原固定源码full depth192。Round1建议F.gelu(inplace=True)及模型.to复制峰值的说法未经源码/API或实测证明。动态schema和valid=true只表明结构/引用/部分政策规则通过，不能当作这些事实或修复机制已验证。

不应把连续patch协议拒绝当作某个micro-batch方案的GPU失败来迭代更小batch；下一轮先解决输出协议及审计证据，再依据真正candidate验证改计划。保留原模型/精度/有效batch/20update/数值/吞吐/成本所有门。不要注入场景答案，不重新给v2打分。

## 只读复核记录

Store投影（ID/role/model/outcome/usage/cost/billing status/attempt ID）的canonical JSON SHA256：ab3e9b9f320bcac5aa7c23d018cbb306e6bc2660ec584d8d6bbfc1faf37635e8。查询均 mode=ro/query_only；该投影没有messages、headers或凭据。

后续运营收尾逐项：
- s2_fp32_adamw_1b: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s3_eval_no_grad_missing: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s4_loss_accumulation_graph: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s5_fragmentation_varlen: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s6_full_vocab_logits_fp32: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s7_frozen_params_optimizer_state: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- s8_two_models_resident: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed
- nanogpt: needs_human/runtime_not_ready, calls=0, Lab results=0, reason=Token Factory live use and credits have not been confirmed

原始文件 SHA256：

- runs/evaluation/live/20261024T223453139983Z-b34f1afd/campaign.json — SHA256 6232791b1a279372ff9c8b84a9d37d2a520171e9bfa352db64d5590d587bae2e
- reports/live-campaign-20261025/mvp-v2-preflight.json — SHA256 f14a485caf8edb3ca703cf2a0c79624f182720a3ab8310a98bb8687c385b8540
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/report.json — SHA256 76fb0fcfd7fb4e0473043c9904d7b6a9abe8d51f63ebfab929f4248de1049833
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/lab/7079f91a6a13452b8dfd15ee0f4adb0b/result.json — SHA256 8273fc1c39da9c74e20610da5a733b1221f3d74bdf11e272ae18eb9581347202
- reports/live-campaign-20261025/mvp-v2-protocol-stop.json — SHA256 a1ef2bf7016be773f49f3dc22040ef85534cecd6defd7484339b7727eaf623a3
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/01/diagnosis.json — SHA256 bfece9e03f4d52afcc916fd26fc5640e95a9930c0a8ae2d3f48e0afb5a850720
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/02/diagnosis.json — SHA256 5636ac14c29503ba40a1e5fec1eec198405c0b22ad2419321db9c8d6c940fb78
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/03/diagnosis.json — SHA256 b96a2ca4ed04922187a5f6d3be09102dfafad023f0f57475739307ac0f110670
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/04/diagnosis.json — SHA256 9b9428f68e88c1ed560462ef66f3abdeaa83a74ae2070ad3cc36e508f42fb590
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/05/diagnosis.json — SHA256 cbfb734499195ee6c799f0ba225654321e81ea081fa42bb47ac73c224e0f1d30
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/01/patch-result.json — SHA256 7de68747b2ce19b4e0d6854d65cee0a7d2a369b307569649f5e5eb65a784797e
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/02/patch-result.json — SHA256 b582f03d02fc661fc834058c2b1c9945b4d5a4038d9c69bdaf49031d081a240e
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/03/patch-result.json — SHA256 8af2efa0739af807296914472336c4e10906eecd808d95b92791e728344c029e
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/04/patch-result.json — SHA256 9e4cf2671a616bd9b5ee0593c2b76725e5ae8ed8c72f68de99a64a5b5a0e990d
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/01/verification-feedback.json — SHA256 8ef1bb549fc34348052d28c4bc71d2b962de4930ed1a4be3790976614b2d75ca
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/02/verification-feedback.json — SHA256 1d19a19e7ddfe8f0112a80521fd6f5589927bc94e843e201374ffe68980358d8
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/03/verification-feedback.json — SHA256 1a6af7a165403d2b35accad9c2c0bc2105b1e2ebef7c652294c13d6c1082c22c
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/04/verification-feedback.json — SHA256 7d6db812807ba10158a97d092834bc37c75c4b8d432911df807e56de9b4f7f22
- runs/evaluation/live/20261024T223453139983Z-b34f1afd/jobs/e0bde71d5a0e4e67bd33e50acd9956a8/rounds/05/verification-feedback.json — SHA256 16f3ccddf73b751f51680d870427e86f120218ead21d0b50e059785b1553fbc9
