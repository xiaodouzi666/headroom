# Headroom Phase 1 final authorized extension handoff

Generated 2026-10-25T03:44:07.443201+00:00

All project code, dependencies and runs remain on azuki. This is a text-only handoff. Phase 1 overall acceptance is failed; no automatic v8 is authorized.


----- BEGIN reports/phase-1-summary-20261025-mvp-v7.md -----

# Phase 1 — MVP v7 最终授权轮结果（2026-10-25）

**整体 MVP 未通过。** 固定九场景真实目标 1/9，低于原 6/9；首因类别原始匹配 6/9，加入 diagnosis.valid 后为 4 真、3 假、2 未知。真实 CLI 九条执行链全部核实，但只有 s8 退出 0，其余八项退出 78。未把部分显存改善或传输协议通过算作整体通过。

本次追加授权 v5/v6/v7 共三轮已全部完成。原 PLAN §0.6 的停止边界现已触发：完成审计、报告、提交和交接后等待 Frank 决定，不自动开始 v8 或后续 Phase 2 实测。所有阈值、原场景、策略、旧 runs 和原预算池保持不变。

执行源码 cb9da81405d5c4f77a5d6d9c1f7a1ee07ad27f32；campaign 为 runs/evaluation/live/20261025T033333928331Z-1b228422/campaign.json，SHA256 cb78766a21e16ba2244b371ca460ec394cd8ad85e6015548fe036f0a82b97cdb。北京时间 2026-10-25 11:33:33–11:39:10，336.93 秒；九场景完整、无质量提前终止、无预算 halt。

## 固定九场景结果

| 场景 | 首因含有效性门 | 静态应用 | 目标 | 实际 CLI | 费用或上界 USD | 秒 |
|---|---|---|---|---|---|---|
| s1_batch_too_big | 未通过 | 未形成候选 | 未达标 | 78 | 0.0370895 | 20.55 |
| s2_fp32_adamw_1b | 正确 | 未形成候选 | 未达标 | 78 | 0.048574428 | 57.07 |
| s3_eval_no_grad_missing | 未通过 | 未形成候选 | 未达标 | 78 | 0.05275352 | 30.78 |
| s4_loss_accumulation_graph | 正确 | 是 | 未达标 | 78 | 0.068272628 | 62.11 |
| s5_fragmentation_varlen | 未知 | 未形成候选 | 未达标 | 78 | 0.040313208 | 32.20 |
| s6_full_vocab_logits_fp32 | 未通过 | 未形成候选 | 未达标 | 78 | 0.033068228 | 18.01 |
| s7_frozen_params_optimizer_state | 正确 | 是 | 未达标 | 78 | 0.062629008 | 54.95 |
| s8_two_models_resident | 正确 | 是 | 达标 | 0 | 0.048958968 | 34.82 |
| nanogpt | 未知 | 未形成候选 | 未达标 | 78 | 0.063958528 | 25.46 |

表中费用是 exact 或经核实保守上界；两个 bounded run 的 actual 仍未知。全部九项在原 $0.6 / 480 秒验收线内。原审计器保留 CLI“未观测”占位，真实退出码以独立 literal-cli 审计为准。

## 本轮实现及质量

两模型共享实际启动参数、当前保留源码身份、失败补丁内容及哈希、结构错误和详细验证反馈。组合上下文限制 64 KiB；截断/缺失明确标为未知，凭据类参数仅在提示词脱敏，真实执行 argv 不改。基线 OOM 且候选未完成时，参考运行说明改为如实说明未执行参考，控制流和比较门不变。

完整 guarded 回归 **2,218 passed，560.90 秒，无跳过**；247 个生产/配置/测试/提示词条目在前后和当前一致，原 PLAN/guard 不变。Ruff、格式、diff 检查通过；源码提交前 gitleaks 零发现。原始源码摘要被扫描器误识别的五项均逐文件重新计算证实非凭据，重复审批映射保留在私有执行凭据，公开 before/after 清单完整保留；未放宽扫描配置。

本轮只有三次补丁生成，全部一次应用并编译（s4/s7/s8）；source-span 独立审计三条转换/实际候选/选择链完整，无 unknown 或矛盾。T1.5 仍仅 3/8，低于原 6/8。其余六场景未形成候选；八个失败 run 最终均为 needs_more_info。

## 成功与失败的准确边界

- **s8 真实目标成功**：只把停用教师模型的构造设备移至 CPU，保留模型与参数；完成 20 次更新，峰值 3.100141568→0.121791488 GB，下降 **96.0714217293%**。记录的 scalar loss identical、最大差值 0，参数量 747,474,432 不变；原数值、精度、参数、吞吐和显存目标门通过。same_inputs / same_effective_batch / same_objective 均为 unknown，故这是原标量比较门通过，不能称完整配对数学等价。
- s8 公开 patch 在干净原始源码上 git apply --check / apply 均退出 0，静态解析通过，所得源码与实际 GPU 候选逐字节一致。公开 patch 比原始尝试仅多一行 diff --git 标头；两者的修复正文一致。没有再次调用模型或 GPU。
- s4 / s7 均完成 20 步并降低显存，仍被原数值门拒绝；s4 是不同 batch 参考比较，s7 配对关系未知。保留 revert，不能仅据 scalar 差值证明相同工作负载下数学行为改变。
- s3 本轮没有生成补丁；历史 v6 的 s3 73.378694% 降幅、完整配对门及干净重应用证据继续保留，但不能拼成 v7 的第二个成功。
- nanoGPT 真实启动 batch_size=32、gradient_accumulation_steps=1，模型仍按源码默认 12/40 解释并提议 8/60，最终需补充信息，未形成补丁。这表明新增上下文尚未被可靠利用。

## 上下文观测局限

冻结源码和请求捕获单测证明两模型的上下文组装/传递路径；s4/s7 第二轮实际回复引用了前轮峰值、loss 和配对失败信息，提供行为佐证。可是 11 份 condition 初始请求审计副本由 evaluator 另行重建，未包含新增 execution/candidate/verification 字段；provider wire 和 Super 完整请求未单独留存，实际完整输入不可据这些副本逐字节证明。保留该缺口，不把副本缺字段直接等同生产漏传，也不声称所有 CLI 参数被模型正确理解。

wrapper seed 与脚本自身重设 seed 分开记录；s4 默认脚本 seed 7、s8 默认 17，不因 wrapper seed 1337 就判其错误。后续若获授权，需补全实际请求记录并验证语义使用；本轮不修改正在验收的源码或追加试跑。

## 费用及历史

本轮 25 次调用：全调用已知小计 **$0.454596996**，两条经核实未知费用上界合计 **$0.001021020**，保守总额 **$0.455618016**。actual 总额仍未知。campaign.summary 的 $0.365774996 只计七个费用完全已知的整 run，另 $0.088822000 已知调用位于两个 bounded run 内，不能遗漏。

全 runtime 457 attempts / 76 runs 全部结算关闭，pending/unresolved/halt 均 0；已知 $4.936747036、保守 $4.968399436，原 $9.99964904 运行池余额 **$5.031249604**。这不是控制台赠送余额。外部探测已知或保留 $1.82224246 单列，合并保守净额 $6.790641896；不是含税发票或信用卡充值金额。未充值、未扩池、未超额，旧 432 attempts / 67 runs 的历史投影完整重建。

| 追加轮 | 单轮目标 | 成功案例 |
|---|---|---|
| v5 | 0/9 | 无 |
| v6 | 1/9 | s3 |
| v7 | 1/9 | s8 |

不同源码版本的成功不合并为统一成功率；没有声称主评测或消融通过。

## 交付和下一步决策

最终文件：README、PROGRESS、RESULTS、FEEDBACK、DEVPOST 草稿、此 summary、三项审计、独立财务与候选审查、干净重应用记录，以及纯文本 handoff。旧版本全部保留；原计划未改。后续主评测/消融、真实完整 UI 流程、合格修复回放、干净 clone 实测、公网域名与告警、视频和 Devpost 提交仍未验收，不创建发布标签。

具体后续范围见 reports/final-decision-20261025-v7.md；完整余项清单见 reports/remaining-acceptance-20261025-v7.md（其编写时 v7 尚在运行，结果以本摘要为准）。建议先逐项讨论已知验收冲突与模型拒绝/误读原因，再决定是否追加有限修复；在决定前继续保留原标准。

审计索引均在 reports/live-campaign-20261025：mvp-v7-audit-v2.json、mvp-v7-source-span-review.json、mvp-v7-literal-cli-audit.json、mvp-v7-finance-review.json、mvp-v7-candidate-review.json、mvp-v7-s8-clean-reapply.json、mvp-v7-audit-execution.json。

----- END reports/phase-1-summary-20261025-mvp-v7.md -----


----- BEGIN reports/final-decision-20261025-v7.md -----

# Headroom — v7 完成后的具体决策（2026-10-25）

三轮追加授权 v5/v6/v7 已完成，最新固定九场景 1/9（s8），原 6/9 门未过；首因含有效性门为 4 真、3 假、2 未知。所有实现、回归、真实试跑、费用审计及交接证据见 phase-1-summary-20261025-mvp-v7.md。当前阻力是修复可靠性和未解决的验收问题，账号及赠送额度已可用。

## 为什么现在需要决定

原 docs/PLAN.md §0.6：若 MVP 未达标，“最多再修 3 轮，仍不达标则停下等 Frank”。Frank 后来又明确批准最多三轮，范围为 v5/v6/v7；本次已经用完。现有赠送额度调用授权仍有效，但不等于取消明确轮数上限。没有自动开始 v8、后续 Phase 2 实测、充值或扩池。

## 范围 A：先逐项讨论验收冲突（建议）

保留原结果和阈值，先分别决定下列事项，而非一揽子改验收：
1. 小 batch 参考与候选不同输入/effective batch 时的 scalar 比较：是否另建同工作负载配对验证，原标量结果仍展示，无法比较仍 n/a。s4 本轮已完成并降峰，但原比较拒绝；s7 配对未知。这不是授权将失败直接改为通过。
2. s2 optimizer-state 比例 39.8715% vs 40%，且 baseline 已 fit22：如何定义有效的独立验收目标与 fixture。不得事后降低阈值或改历史记录。
3. 默认禁止精度变化，却要求 bf16 档；default/strict 当前等价：明确政策档与对应评测，精度变化必须显式选择。
4. 模型在已有方案时仍 needs_more_info、nanoGPT 误用默认 CLI：明确缺证据/非法方案/真实需人补充的诊断反馈，补全真实请求保存，随后再确定有界修复实验。

选择本范围只授权讨论并准备具体修改，不默认接受任何指标变动，也不默认增加付费/GPU试跑轮数。

## 范围 B：原门槛下再追加最多三轮

这是待 Frank 批准的新范围，尚未执行。候选工作限定为：
- 保留真实发送请求的有界、脱敏审计，使实际 argv 和候选反馈可逐字节核验；
- 用已存在的通用生产证据改善 needs_more_info 的理由反馈、CLI 覆盖来源及模型对参数的利用；不提供场景答案，不跳过无效诊断或原 GPU 门；
- 每轮完整回归、固定九场景和独立财务/CLI/候选审计，不挑选单项成功拼分数；
- 最多三轮，逐次按现有池余额和完整 provider 上界审核；运行池目前保守剩余 $5.031249604，但不保证足以完成任意轮数；
- 仅现有赠送额度，不充值、不超额、不扩池；原 .6/480/6rounds/默认策略/数值门全部保留。提前遇到不能安全继续的预算状态立即停。

## 尚不能称完成的交付

Phase 2 指定 Sources/Nano/预算专项/HF/Watch 修复、20次政策矩阵、主评测与消融、完整实时 UI 流程、5条合格修复回放、干净 clone 修复；Frank 的设计认可、域名/Cloudflare、告警接收方、录制视频及 Devpost 提交；未来日期的可用性检查。已有代码、基线回放或报告不替代这些验收。

----- END reports/final-decision-20261025-v7.md -----


----- BEGIN docs/RESULTS.md -----

# Results

Measured GPU baselines now cover twelve workloads. The complete 2026-10-24
manifest run reproduced five CUDA OOMs and completed twenty steps in seven workloads.
All captures and cleanup checks passed. This is baseline acceptance, not automated
repair or model-quality evidence.

The final authorized extension, MVP v7, completed all nine cases with one target
success (s8), below the original six-target gate. Raw first-cause matches are
6/9; with diagnosis validity they are four correct, three failed and two unknown.
Nine literal CLI execution chains were verified: s8 exit 0 and eight exit 78.
The s8 patch keeps an unused teacher on CPU, completes 20 updates and lowers
GPU peak 96.071422%, with identical observed scalar losses and unchanged
parameter count. Full workload pairing remains unknown; this is acceptance
under the original scalar gate, not proof of full mathematical equivalence.

The earlier v6 s3 success (73.378694% reduction, full pinned pairing checks) is
preserved separately. Different source versions are not merged into a score.
All three additional iterations v5/v6/v7 are exhausted; further repair work
awaits the owner's decision under PLAN section 0.6. Main evaluation, ablations,
public delivery and full project acceptance remain open. See the final v7
summary and decision report; all historical snapshots below remain dated evidence.

## 2026-10-25 model and isolation evidence

| Gate | Recorded observation | Acceptance boundary |
|---|---|---|
| T0.4 capability matrix | 60 prescribed samples, including five reused historical samples; Super native schema/tools and four-way concurrency passed; Ultra successful server input up to 500,029 tokens | Matrix execution and recorded results accepted; 500,029 is a tested lower bound, not the exact provider maximum or proof of a request at the advertised 1M context. The 900k probe returned 429 and was not retried; its unknown charge remains retained. Nano tools and unverified thinking-budget methods remain disabled |
| T1.3 client/router | Super strict schema and Ultra authentic evidence with 268,920 provider input tokens from 53 unique source records; one attempt each | Accepted transport/schema/usage gate; no filler. The free-text Ultra response overclaimed fragmentation, so this is not diagnosis correctness |
| T1.4 diagnosis v5 | 7/8 first-cause matches, 8/8 valid references, eight stop responses with zero reasoning tokens; usage-priced total USD 0.328770 | Full acceptance remains false: s1/s6 contain forbidden proposals, s7 requests more information, and s5 truth remains unverified. The fixed denominator is eight |
| T1.12 MVP v1 | One of nine attempted: real s1 baseline, then one Nano response; no applied repair and eight unexecuted cases | Failed campaign remains preserved. Its unknown actual Nano charge was not treated as zero or retroactively accepted |
| T1.12 MVP v2 | s1: 22 model calls, 16 Super attempts (10 file-count rejections, six truncation/filtered responses), zero apply/compile/candidate runs; eight later cases stopped at runtime readiness | Not accepted: target success 0/9, first-cause match one with eight unobserved. The eight admission skips are not model quality failures |
| T2.7 isolation parity | Six real CUDA arms: s1, s3 and HF through production Docker and an independent subprocess controller; allocated/reserved peak differences 0% | Accepted original <=1% gate. s3 completed 20 updates in each arm with identical losses; s1 and HF genuinely OOM before the first update, not 20-step successes |

The T0.4 receipt records USD 0.77289846 in known usage-priced charges and
USD 1.049344 permanently retained for the unknown 900k/429 outcome, for a
conservative occupied amount of USD 1.82224246. The T1.3 calls cost
USD 0.0001344 (Super) and USD 0.269367 (Ultra), totaling USD 0.2695014.
These are scoped observations, not an account invoice or additive account-wide
totals; aggregate receipts may already include individual calls.

MVP v1's Nano usage was 3,643 prompt plus 480 completion tokens, with exact
model identity and HTTP 200, but no cache-token count. Its actual charge remains
null. A formal reviewed-retention audit keeps the **original full USD 0.01644864
reservation permanently occupied**. This clears only that reviewed billing
block for future dispatch: the old Store call, report and failed campaign remain
unchanged. At the saved pre-v2 review, runtime known charges were USD 1.37040652
and known-or-retained occupation was USD 1.38685516; the actual total remained
null. These are saved audit values, not a fresh balance reading.

New missing-cache responses can be reported with a verified conservative upper
only after strict identity, tariff, usage, output-cap and ledger settlement checks.
The UI and results keep actual cost unknown, known subtotal separate and the
bound explicit. A verified upper no greater than the original cost threshold
proves that inequality; a larger upper does not prove actual overspending and
cannot certify the threshold. Unreviewed unknown charges still block dispatch.
No original cost, accuracy, numerical or timing gate is lowered.

Sources: [T0.4 receipt](../reports/t0.4-acceptance-20261025.json),
[T1.3 receipt](../reports/t1.3-acceptance-20261025.json),
[diagnosis v5 review](../reports/live-campaign-20261025/diagnosis-attempt4-review.json),
[failed MVP v1 audit](../reports/live-campaign-20261025/mvp-v1-audit.json),
[pre-v2 retained-charge review](../reports/live-campaign-20261025/mvp-v2-cap-budget-review.json),
and [T2.7 independent review](../reports/t2.7-acceptance-20261025.json).
The T2.7 reference runs inside the same Docker isolation envelope, with shared
capture instrumentation/image/source/clock checks; it is not a bare-host backend
or independent allocator instrumentation. It makes no throughput claim.

## MVP v2: real protocol failure before candidate execution

The campaign completed with exit 1. All nine harness workers exited 0 and wrote
reports; that process evidence does not mean successful repair. Only s1 ran the
model/GPU pipeline: one genuine CUDA OOM baseline (24.750424064 allocated GB),
22 model calls (Nano 1, Ultra 5, Super 16), and 283.708064 seconds including
campaign cleanup. Its first cause was activations, matching the authored label,
but target_met=false and there is no selected patch or after-run.

Four patch rounds produced 16 attempts: ten rejected with “diff must touch
between one and twenty files”, and six rejected as truncated/filtered responses.
No attempt reached git apply or py_compile, and no candidate GPU/verification
run occurred. The fifth diagnosis requested more information. Candidate loss
equivalence, parameter equality and memory savings are unmeasured, not failures
of an executed candidate. The original any-applied aggregate remains unknown
where evidence is missing; no nonexistent final patch is manufactured.

For six Super responses completion reached 4000: five also reported 4000
reasoning tokens, and one reported 3962. The ten old raw diff payloads were not
saved, so their error cannot uniquely identify missing headers, escaped newlines
or explanation-only output. An independent standard-diff check accepted both
ordinary unified diff and a matching optional git header; separate malformed
inputs reproduced the same file-count error. There is no evidence of an
inherent prompt/parser format contradiction.

The parent disabled future admission after seeing the common protocol failure.
s2–s8 and nanoGPT therefore produced runtime_not_ready/needs_human reports with
zero model calls and zero GPU runs. They remain in the unchanged nine-case
acceptance denominator, but must not be called eight model quality failures.
The reviewed profile was restored after the campaign ended; this operation did
not change the ledger or regrade any result.

s1 actual cost is still null: known subtotal USD 0.14104766 plus formally
verified Nano upper USD 0.00025122 gives conservative upper **USD 0.14129888**.
The upper certifies the original <=0.6 cost gate; it does not establish exact
actual spend or compensate for target failure. The saved post-v2 ledger review
records known USD 1.51145418, conservative occupation USD 1.52815404 and
remaining runtime pool USD 8.47149500. These are historical local-ledger values,
not a refreshed account balance or invoice.

At the pre-v3 checkpoint, the common patch/fixer fix had been applied:
explicit reasoning=False with the original 4000 cap, clearer existing diff
instructions, and bounded private visible-response evidence. That production-tree
targeted integration passed 294 guarded tests. **At that checkpoint the next
live run had not yet been tested; it subsequently failed as recorded in MVP v3
below.** The earlier 1977 backend/68 frontend results validated the committed
5d3093c baseline, not the then-new protocol revision.

The later line-array protocol revision passed [2026 production regression
tests](../reports/patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json),
with 236 source/config/test/production-prompt hashes unchanged during execution.
This is a separate regression checkpoint, not retroactive evidence for an older
run or a real repair acceptance.

Evidence: [v2 audit](../reports/live-campaign-20261025/mvp-v2-audit.json),
[operational classification](../reports/live-campaign-20261025/mvp-v2-operational-audit-note.json),
[repair findings](../reports/live-campaign-20261025/mvp-v2-repair-findings.md),
[restored-profile ledger snapshot](../reports/live-campaign-20261025/mvp-v2-profile-restored.json),
[standard diff contract](../reports/unified-diff-contract-20261025.json),
[non-unique error controls](../reports/unified-diff-contract-20261025-supplement.json),
and [applied revision](../reports/super-patch-fix-20261025/application.json).
The original failed v1/v2 artifacts remain unchanged.

## Manual GPU verification regression (not model-driven repair)

On 2026-10-24, the new default verifier was exercised on the full-size s3
standalone workload and a **manually authored** one-line `@torch.no_grad()`
evaluation fix. Both ran for 20 optimizer updates in separate network-disabled
Lab containers on the 3090 Ti, seed 1337, with no other GPU process observed.
All captures and cleanup checks passed.

| Measurement | Original | Manual candidate |
|---|---:|---:|
| Peak allocated, decimal GB | 2.435717632 | 0.648419840 |
| Lab optimizer-interval median, ms | 40.896303 | 41.032609 |
| Completed updates | 20 | 20 |
| Parameters | 37,791,744 | 37,791,744 |

Peak reduction was **73.3787%**; the measured optimizer-interval increase was
**0.3333%**. All 20 training losses were identical (`max_loss_delta=0`), and
actual input/target fingerprints, initial parameters and per-update pairing
matched without a caller override. The unchanged reclaim comparison returned
`target_met=true`. These are observed Lab intervals, not an end-to-end training
throughput claim. Initialization hashing is reported separately; it remains
part of total wall time.

Evidence: [manual GPU receipt](../reports/pairing-manual-gpu-20261024T111357Z.json),
with raw source, patch, snapshots and results under
`runs/manual-pairing-gpu-20261024T111357Z/`. The receipt records the exact
reproduction procedure and source hashes. This validates the verifier and new
CUDA instrumentation for one known repair; it contributes **zero model-generated
repair successes** to T1.12/T4.2/T4.3. Automatic pairing remains limited to the
reviewed s3/s4 source contracts; unsupported scripts and old captures remain
unknown. The current verifier evaluates the original C.5 scalar rule without
requiring these optional fingerprints; it reports the comparison basis and
limitations explicitly. Full model-generated T1.6 acceptance remains open.

A later manual command regression exercised `python -O -m train` with a source
outside the pinned pairing contracts. Both 20-update GPU runs had unchanged
parameters and identical observed losses. Allocated peak fell from
2,435,717,632 to 648,419,840 bytes (73.3787%); median optimizer interval moved
from 41.3288 to 40.5021 ms. Pairing remained unknown, and the report used
`original_plan_full_backward_scalar_series` with standard acceptance scope.
See [command-mode GPU receipt](../reports/command-manual-gpu-20261024T113103Z.json).
This also contributes zero model-generated repair successes.

## Preparation checks (not benchmark results)

| Check | Observed outcome | Limit |
|---|---|---|
| CUDA toolchain | torch 2.5.1+cu124 recognizes 3090 Ti; snapshot API returns traces | Small allocation only |
| Synthetic scenarios | 8/8 CPU tiny checks completed 20 steps; full GPU baselines below | CPU smoke itself is not GPU acceptance |
| nanoGPT | Pinned source; tiny CPU run exit 0; full GPU CUDA OOM reproduced below | Exact allocator peak unavailable from upstream output |
| Historical minimal live model calls | Super and Nano each returned HTTP200, matched identity and stop | Two short chats only at that checkpoint; later capability/long-evidence results are recorded above, repair remains unaccepted |
| Tavily | Real search/extract and versioned cache checks passed | Provider-reported credits are separate from account counters |

## T0.6 full default GPU baselines

Current T0.6 evidence is a composition of two measured runs on azuki RTX 3090 Ti,
torch 2.5.1+cu124:

- **A — current s1:** `reports/gpu-baseline-20261023T022519Z-e164c187.json`, measured at 10:25 Beijing time on 2026-10-23.
- **B — unchanged s2–s8 and nanoGPT:** `reports/gpu-baseline-20261023T013238Z-a16fc6fb.json`, measured at 09:32–09:34 Beijing time on 2026-10-23.

Each workload used full default CUDA dimensions in its own network-disabled
Docker container. No foreign GPU compute process was observed in the recorded
samples; all nine containers were cleaned up and none was killed by host-memory
OOM. Source hashes in `reports/t0.6-acceptance.json` match all eight current
synthetic scripts. The old s1 entry in source B is historical and excluded from
the current nine-case acceptance.

| Scenario | Source | Observed status | Completed steps | Runtime s | Peak allocated GiB | Peak reserved GiB |
|---|---|---|---:|---:|---:|---:|
| s1_batch_too_big | A | cuda_oom | 0 | 4.187 | 23.027313 | 23.041016 |
| s2_fp32_adamw_1b | B | completed_20_steps | 20 | 14.615 | 20.026398 | 20.673828 |
| s3_eval_no_grad_missing | B | completed_20_steps | 20 | 6.259 | 2.221808 | 2.314453 |
| s4_loss_accumulation_graph | B | cuda_oom | 12 | 6.260 | 23.147012 | 23.152344 |
| s5_fragmentation_varlen | B | completed_20_steps | 20 | 9.387 | 4.630246 | 18.419922 |
| s6_full_vocab_logits_fp32 | B | cuda_oom | 0 | 5.218 | 20.082430 | 20.103516 |
| s7_frozen_params_optimizer_state | B | completed_20_steps | 20 | 7.311 | 16.549359 | 16.570312 |
| s8_two_models_resident | B | completed_20_steps | 20 | 9.388 | 2.840601 | 2.851562 |
| nanogpt | B | cuda_oom | 0 logged updates | 11.489 | unknown | unknown |

Runtime includes container startup and process monitoring, excludes cleanup,
and is not steady-state training throughput. GiB means 2^30 bytes. Synthetic
peaks are terminal PyTorch historical counters for successful allocations; they
do not include a failed allocation or estimate the memory needed to finish an
OOM run. nanoGPT does not emit those counters, so its exact peak is unknown.
Its traceback confirms a 512 MiB request failed during the upstream GELU forward;
no completed training update was logged. Its initial loss evaluation is not a
training update.

The three synthetic OOM cases finished within 60 s; the five reclaim cases
completed exactly 20 updates and have measured peaks in their READMEs. The
pinned nanoGPT source is clean at `3adf61e154c3fe3fca428ad6bc3818b27a3b8291`, and
`repos/nanogpt.oom.txt` is byte-identical to its raw stderr. These baseline measurements satisfy T0.6 only. T1.1 capture evidence is recorded
separately below; no diagnosis, patch, verification or search result is claimed.

Evidence: source reports A/B above, `reports/t0.6-acceptance.json`, and raw
per-case stdout/stderr/result files under their corresponding
`runs/phase0-baselines/<run_id>/` directories. Each synthetic source SHA-256 and
exact peak byte values are recorded in its README and `scenarios/INDEX.yaml`.
Reproduce on an available GPU from the project root:

```sh
source scripts/env.sh
uv run python scripts/check_gpu_baselines.py --check-only
uv run python scripts/check_gpu_baselines.py
```

An earlier s1 run (`20261023T013012Z-466ebd63`) did reproduce OOM, but its original
peak fields contained only startup counters. That raw report is preserved and
invalidated for peak claims by `reports/gpu-baseline-013012-peak-correction.json`.
Both later source runs use terminal OOM counters and supersede those fields.

The adopted s1 fixture now uses width 256 and depth 192 instead of width 1024
and depth 12. Parameters changed from 100,749,312 to 101,007,360 (+0.256129%);
batch 32, sequence length 2048, float32, SGD and the activation root cause remain
unchanged. This fixture calibration increases genuine allocation-history events.
It is a new baseline version, not a model repair, a memory-savings comparison, or
a numerical-equivalence claim. Its source SHA-256 is
`668fe35db321d1738f42dd576f28f3efebf5b50693556dfdfec7f90c4f10ea28`.
The old source `bd685f1480a2d0d9a5a68af44eaf0f4b325d27f7a1f99ba56d217daae8dd2856`
and source-B s1 result (5.227 s; allocated 24,845,041,664 bytes; reserved
24,857,542,656 bytes) remain historical evidence.


## T1.1 Lab capture acceptance

All original T1.1 clauses are accepted in `reports/t1.1-acceptance.json`, combining
`reports/lab-gpu-acceptance-20261023T022523Z.json` with
`reports/lab-tests-20261023T0212.log` (61 tests passed in 53.15 s).

| Clause | Measured evidence |
|---|---|
| s1 CUDA OOM and snapshot | `oom`; pickle exists; 2050 device-0 trace events > 1000 |
| s1 allocation and traceback | Requested 268,435,456 bytes (0.268435456 GB); traceback contains OutOfMemoryError |
| s3 small-batch completion | Two batch-1, seed-1337 captures each completed 20 updates with 20 losses |
| Determinism | First five s3 losses exactly equal across the two GPU runs |
| Timeout and cleanup | Real infinite loop plus child process; 30-second limit; observed 30.001734 s, TIMEOUT and verified cleanup |
| Credential boundary | Subprocess NEBIUS_API_KEY is null; source/runtime credential files excluded and source read-only |

The 13 GPU report checks are true, all three captures are complete and cleanup
was verified. GPU sharing flags describe recorded samples, not continuous
exclusivity. These results validate the Lab wrapper, not T1.2 peak reconstruction,
a model diagnosis, a repair, or end-to-end acceptance. See `docs/LAB.md` for run
provenance, the binutils symbolizer fix and preserved failed attempts.

## T1.2 evidence-pack implementation and acceptance

The four real Lab captures produce Markdown, structured JSON and PNG timelines.
Their reconstructed physical-block peaks and terminal allocations match native
counters. All source scripts are included in full, with verified hashes, and
each prompt is below the 150,000-token budget. Final regression is 95 passed in 53.54 s (reports/tests-20261023T025427Z-final.log);
Ruff and the actual evidence CLI smoke pass. The final reviewed report is
`reports/t1.2-acceptance.json`; it retains a failed task status.

| Capture | Peak allocated bytes | Optimizer steps marked | Prompt tokens |
|---|---:|---:|---:|
| s1 | 24,750,424,064 | 0 (OOM before first update) | 20,907 |
| s2 | 21,553,250,816 | 20 | 29,970 |
| s4 | 24,768,717,824 | 12 | 29,396 |
| s5 | 5,021,758,464 | 20 | 24,550 |

The Lab captures use seed 1337 and include the capture instrumentation. Their
measurements are separate from the earlier direct T0.6 baselines; their small
differences are not memory improvements.

- **s2 fails the unchanged gate:** optimizer moments at peak are 8,593,604,608
  bytes / 21,553,250,816 bytes = **39.8715009692%**, below 40%.
  Foreach update intermediates remain temporaries; they are not relabeled as
  optimizer state. Scalar step counters are not counted as GPU moment blocks.
- **s4 passes the source-location clause:** actual Top40 includes
  `/source/train.py:107`, the `total_loss += loss` statement. This stack accounts
  for only 512 bytes and is rank 15 of 15. It proves the runtime location,
  not that this small allocation alone caused the retained graph's large footprint.
- **s5 passes the stated header/indicator clause:** terminal reserved minus
  allocated is 19,124,731,904 bytes, and the indicator is `high`. The run has
  no OOM, so `fragmentation_confirmed=false`; harmful fragmentation is unproven.
- OOM positions and the available timestamp-aligned optimizer boundaries are
  drawn at allocator event indices. Missing timestamps are never fabricated.

## Unresolved later acceptance requirements

- T1.2 remains unaccepted because s2 falls below its original >=40% gate.
  No threshold or category has been changed to force a pass.
- The s2 baseline is already below 22 GB. It does not demonstrate T2.1's
  required two-round fit:22GB improvement.
- MVP v6 demonstrates one authenticated model-generated GPU repair (s3),
  with the original gates preserved. That single success does not establish
  overall MVP, main benchmark or ablation acceptance.
- Capability and long-evidence client gates are accepted as recorded above.
  The reviewed runtime and gifted-credit authorization are available; actual
  overall repair, main evaluation and ablation acceptance are still pending. No recharge
  or exceeding the shared global/day pools is authorized. Tavily component
  evidence remains distinct from Sources on a complete model-generated repair.

## Historical CPU source smoke evidence

| Scenario | Steps | Process exit | Wall seconds |
|---|---:|---:|---:|
| s1_batch_too_big | 20 | 0 | 4.047 |
| s2_fp32_adamw_1b | 20 | 0 | 4.034 |
| s3_eval_no_grad_missing | 20 | 0 | 4.046 |
| s4_loss_accumulation_graph | 20 | 0 | 3.997 |
| s5_fragmentation_varlen | 20 | 0 | 4.047 |
| s6_full_vocab_logits_fp32 | 20 | 0 | 4.002 |
| s7_frozen_params_optimizer_state | 20 | 0 | 4.047 |
| s8_two_models_resident | 20 | 0 | 4.02 |

This smoke table predates the s1 default-fixture calibration; its tiny dimensions
are unchanged, but it is not a new current-source run. These wall times include container startup and are not training throughput measurements. Sources and commands are in reports/scenario-cpu-smoke-summary.json and its referenced logs. CPU tiny changes model dimensions for plumbing checks only; those runs are not submitted as memory optimization results.

The pinned nanoGPT smoke retains vocabulary 50304 but uses tiny depth/width/sequence/batch to check loading and training in isolation. GPU acceptance uses the separate unmodified baseline configuration in repos/nanogpt.yaml.


## 2026-10-24 complete evaluation baseline pass

Source: [evaluation-baselines-20261024.json](../reports/evaluation-baselines-20261024.json).
Every row links a preserved raw Lab result and source SHA. The manifest's SHA is
`c494865118285ab75a96bf2eeacbc67b1048d962ba5d9ebecadd0ff0d47a637d`. The new ViT and T5 workloads use actual Transformers
implementations with random initialization and synthetic inputs, not pretrained
task-quality tests. HF Trainer's first-step OOM occurs before optimizer state is
initialized; optimizer-state causation is therefore not established by that run.

| Scenario | Actual baseline | Steps | Peak allocated GB | Wall seconds |
|---|---|---:|---:|---:|
| s1_batch_too_big | oom | 0 | 24.750424 | 3.181 |
| s2_fp32_adamw_1b | completed | 20 | 21.553251 | 21.190 |
| s3_eval_no_grad_missing | completed | 20 | 2.435718 | 5.987 |
| s4_loss_accumulation_graph | oom | 12 | 24.768718 | 4.498 |
| s5_fragmentation_varlen | completed | 20 | 5.021758 | 6.885 |
| s6_full_vocab_logits_fp32 | oom | 0 | 21.588380 | 1.437 |
| s7_frozen_params_optimizer_state | completed | 20 | 17.819809 | 6.164 |
| s8_two_models_resident | completed | 20 | 3.100142 | 5.827 |
| nanogpt | oom | 0 | 24.705184 | 8.358 |
| hf_trainer | oom | 0 | 24.805119 | 7.266 |
| vit_random | completed | 20 | 2.082593 | 20.158 |
| t5_random | completed | 20 | 8.042537 | 53.254 |

GB here is decimal bytes / 1e9. Peaks are successful allocations observed by the
Lab; an OOM peak does not estimate total memory required to finish. Wall time is
not steady-state throughput. All twelve runs have capture_complete=true,
cleanup_verified=true and shared_gpu=false in the recorded samples. A lost SSH
attach connection did not restart the campaign; its supervised server process
completed the remaining rows.

### Component evidence, separate from benchmark results

- Parameter capture regression: `reports/lab-gpu-acceptance-20261024T021625Z.json`.
  Real s1 OOM trace and repeated s3 twenty-step loss agreement passed.
- New pinned nanoGPT preparation/Lab path: `reports/nanogpt-lab-baseline-20261024.json`.
- HF Trainer CPU pairing and full GPU OOM: `docs/WATCH_HF.md` and
  `reports/hf-trainer-baseline-20261024.json`.
- Tavily versioned checkpoint/allocator retrieval: `reports/research-component-20261024T022414Z.json`.
  Four live methods reported three credits total; repeated queries had zero API
  calls and zero credits from the local cache. Store contains eight operation rows.
  This does not yet establish Sources on a complete s1/s5 model-driven repair.
- Five imported real baseline replays: `reports/baseline-replays.json`.
  They contain no model diagnosis, patch, repaired after-run or invented agent trace.
- Offline SDK responses, patching, keep/revert and reporting remain separately
  labeled fixtures. They do not enter the main or ablation score table.

### Main and ablation results

| Evaluation | State | Success / diagnosis / cost claims |
|---|---|---|
| Ten original workloads, original two-policy requirement | Runtime available; original full matrix not yet executed | Not measured; current default/strict are equivalent and original wording remains unresolved |
| Full evidence + Ultra | Final MVP v7: 1/9 targets; 6 raw / 4 valid first causes. Versioned MVP trials are not a fixed-protocol main benchmark | One s8 original-scalar-gate repair; v6 s3 separate historical evidence. No main benchmark or ablation advantage claimed |
| Traceback + memory_summary + Ultra diagnosis | Not yet executed under a fixed comparable protocol | Not measured |
| Full evidence + Super diagnosis | Not yet executed under a fixed comparable protocol | Not measured |

The evaluator records first-round diagnosis, all failure/unknown charges, source
pins and per-condition evidence provenance. Unverified root-cause labels remain
unscored. No expected ablation advantage is reported as an observed finding.
Original s2 40% and two-round fit acceptance remain unresolved; no gate was lowered.

### Policy-campaign implementation update

The evaluator now records full effective policies per row and supports explicit
`default`, `strict`, and `allow_precision` selections; the default remains a single
policy. `--plan-only` exposes the matrix multiplier and unchanged spend cap without
running workloads or using a provider. The current default and strict policies
both prohibit numerical changes. The optional precision-permitting selection
does not resolve or replace the original T2.8 wording. Aggregate and per-policy
metrics preserve unknown values and scored/comparable denominators. Real
two-policy results, the at-most-three-round optimization study, and the original
target_met >=75%, first-cause agreement >=75%, and USD 12 gates remain unmeasured. See [EVALUATION.md](EVALUATION.md).


## Evaluation application and completion evidence

The campaign table now preserves successful patch/configuration application
separately from the final retained configuration. It reports the selected round,
its verified completion, and per-round candidate outcomes, including reverted
attempts. Missing historical facts stay unknown. Empty source diffs do not
invalidate an applied argv/environment change.

This is reporting functionality, not a new model benchmark. Offline fixtures and
the manually authored GPU regressions above do not add live repair successes.
MVP v1, v2 and v3 failed before an accepted repair; the eight later v2 cases
were operational skips. Accepted main evaluation and ablation results remain
pending. Historical v4 failed with target0/9; v6 later passed s3 only (1/9 overall). Both records are preserved below.

## First Token Factory connectivity measurements — not repair results

Evidence: reports/tokenfactory-minimal-20261024.json, source commit269efd0.
Both official authenticated catalogues returned200. One chat each ran on US:

| Role | Prompt tokens | Completion tokens | Total seconds | Usage-priced estimate USD |
|---|---:|---:|---:|---:|
| Super | 23 | 19 | 0.670570 | 0.000024 |
| Nano | 23 | 47 | 1.506663 | 0.00001266 |

Both finish_reason=stop, identity matched, no retry, max_completion_tokens=128.
Total0.00003666USD; with21% tax reserve0.0000443586USD. Pricing uses ordinary
input conservatively and is not an independently reconciled invoice. These are
single observations, not model speed benchmarks or completed repair scores.
At that historical checkpoint all later gates remained open. T0.4 and T1.3 are
now accepted with the limitations recorded above; original repair gates remain
open. This historical two-chat record is not rewritten as later acceptance.

## MVP v3 — second repair iteration, failed (2026-10-25)

Source commit: 1a935c8716cee05edf2b1ad1d3e37d35f52a5ef3. Original nine-case manifest and thresholds were unchanged. All nine harness child workers recorded worker_exit_code=0 and cleanup_verified=true in matching campaign/report timing records; this is not a CLI fix invocation. The campaign exited1 because the original success gate failed. Five cases ran with models; four later cases were operational admission stops with zero GPU/model work, not four observed model-quality failures. Fixed denominator: target0/9; first cause3/9 true,1/9 false,5/9 unknown.

| Scenario | First cause | Target | Model calls | Cost upper USD | Wall seconds | Outcome |
|---|---:|---:|---:|---:|---:|---|
| s1_batch_too_big | yes | false | 27 | 0.12610878 | 83.213 | diagnosis_needs_more_info |
| s2_fp32_adamw_1b | yes | false | 7 | 0.07339602 | 57.965 | diagnosis_needs_more_info |
| s3_eval_no_grad_missing | no | false | 8 | 0.08762380 | 44.520 | diagnosis_supplement_exhausted |
| s4_loss_accumulation_graph | yes | false | 31 | 0.16205718 | 96.722 | max_rounds_reached |
| s5_fragmentation_varlen | unknown | false | 5 | 0.05945934 | 34.306 | diagnosis_needs_more_info |
| s6_full_vocab_logits_fp32 | unknown | false | 0 | n/a (no calls) | 0.954 | runtime_not_ready |
| s7_frozen_params_optimizer_state | unknown | false | 0 | n/a (no calls) | 0.930 | runtime_not_ready |
| s8_two_models_resident | unknown | false | 0 | n/a (no calls) | 0.922 | runtime_not_ready |
| nanogpt | unknown | false | 0 | n/a (no calls) | 1.061 | runtime_not_ready |

Across54 Super responses, all finish=stop and reported reasoning_tokens=0. Fifty-two nonempty diff strings had no physical linefeeds and were rejected before application; a separate empty diff was rejected as NO_CHANGE. The other empty-diff CLI-only proposal was statically accepted but the actual s5 candidate rejected its unsupported --grad_accum_steps=4 argument (SystemExit2). Thus git-apply-plus-compile success=0 and verified repair success=0. Workflow status completed on s4 means loop completion only.

Exactly78 model calls were joined to their authoritative budget attempts: known0.50587762USD plus5 settled Nano missing-cache bounds0.00276750USD yields conservative0.50864512USD; actual total remains null. As of the saved post-v3 ledger snapshot at 2026-10-24T23:01:44.356938Z, runtime cumulative conservative2.03679916USD left7.96284988USD under the unchanged9.99964904USD allocation. This is a historical local-ledger reading, not the current balance or an invoice. Historical unknown reservations remain occupied.

Evidence: reports/live-campaign-20261025/mvp-v3-audit-v2.json; mvp-v3-repair-review.json; mvp-v3-repair-findings.md; mvp-v3-protocol-stop.json; mvp-v3-profile-restored.json. At this v3 checkpoint, final original repair iteration3 was being prepared. That v4 iteration subsequently failed; its final evidence is appended below.


## MVP v4 — final third repair iteration, failed

**结论：MVP 未通过，完整 goal 尚未完成。** 九个原定场景均真实执行，目标达成 **0/9**（原门至少6/9），首因命中 **7/9**（另2项unknown，不从分母剔除）。本轮是初次MVP之后的第3次修复迭代；原 PLAN §0.6 的修复轮数已用完，停止进一步修复试错，等待 Frank 决定是否扩展轮数。账号、密钥和赠送额度已就绪，不是本次停止原因。

实现/评测来源：78a83df86b181674c37509b192517a9d4101ad92。全部代码、依赖、GPU数据和媒体在azuki；Mac仅接收本报告。原PLAN、9场景、精度策略、阈值和失败历史均未改动。本轮结束于2026-10-24T23:31:55.358346+00:00，driver退出1，总墙钟735.240秒。

## 九场景结果

下表的“候选”与“最终选中”分开：s1有实际候选但OOM后revert；s8第2轮keep，后续失败不覆盖它，保留一个未达目标的小改善。其余没有验证成功的候选。completed工作流状态仅表示搜索结束。

| 场景 | 原标签 / 诊断首因 | 首因命中 | apply+compile | 候选完成 | 最终选中轮 | target |
|---|---|---|---|---|---|---|
| s1_batch_too_big | activations / activations | 是 | 1 | 否 | 无 | false |
| s2_fp32_adamw_1b | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s3_eval_no_grad_missing | activations / activations | 是 | 0 | 未执行 | 无 | false |
| s4_loss_accumulation_graph | retained_graph / retained_graph | 是 | 0 | 未执行 | 无 | false |
| s5_fragmentation_varlen | fragmentation_candidate / activations | unknown | 0 | 未执行 | 无 | false |
| s6_full_vocab_logits_fp32 | temporaries / temporaries | 是 | 0 | 未执行 | 无 | false |
| s7_frozen_params_optimizer_state | optimizer_state / optimizer_state | 是 | 0 | 未执行 | 无 | false |
| s8_two_models_resident | params / params | 是 | 1 | 是 | 2 | false |
| nanogpt | unknown / activations | unknown | 0 | 未执行 | 无 | false |

## 峰值、数值、费用与时长

GB使用十进制字节/1e9。after仅列最终选中配置，不用失败候选冒充修复结果。费用“≤”表示已核验保守上界，actual仍为null；无“≤”为完整usage-priced已知费用，不是独立核销发票。

| 场景 | peak before GB | selected after GB | 降幅% | step时间变化% | 数值状态 | 调用数 | 模型费用USD | 秒 |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| s1_batch_too_big | 24.750424064 | — | — | — | unknown | 28 | ≤0.12634370 | 91.948 |
| s2_fp32_adamw_1b | 21.553250816 | — | — | — | unknown | 8 | 0.068768988 | 54.264 |
| s3_eval_no_grad_missing | 2.435717632 | — | — | — | unknown | 34 | 0.192787128 | 139.395 |
| s4_loss_accumulation_graph | 24.768717824 | — | — | — | unknown | 34 | 0.175681208 | 128.276 |
| s5_fragmentation_varlen | 5.021758464 | — | — | — | unknown | 19 | 0.112660608 | 112.125 |
| s6_full_vocab_logits_fp32 | 21.588379648 | — | — | — | unknown | 2 | ≤0.03223954 | 18.110 |
| s7_frozen_params_optimizer_state | 17.819808768 | — | — | — | unknown | 23 | ≤0.11876024 | 88.777 |
| s8_two_models_resident | 3.100141568 | 2.989897728 | 3.556091 | 0.941755 | identical | 14 | ≤0.12185840 | 62.184 |
| nanogpt | 24.705183744 | — | — | — | unknown | 3 | ≤0.09073224 | 39.175 |

s1第3轮实际应用并编译，但仍OOM、0训练步，peak=24.750424064GB，loss=n/a，参数量未变。s8第2轮完成20步，peak从3.100141568降至2.989897728GB，仅3.556090507%（要求20%）；记录的backward标量loss序列identical，原口径numerical_acceptance=true，但same_inputs/effective_batch/objective仍unknown，不能扩写为新的配对数值等价证明。s8实际step时间增加约0.941755%，throughput gate通过。

本轮165次模型调用：已知小计1.037464332USD，加5条Nano可核验上界0.00236772USD，保守合计1.039832052USD；实际总额null。9项均≤0.60USD且≤480秒。campaign.summary.known_cost_usd=0.549897932仅汇总4个总费用完全已知run；另外5个bounded run内的已知调用0.487566400USD也属于已知小计，不能遗漏。

## 原验收门逐项状态

- T1.5：8个合成场景中仅2个有真实git apply命令/direct fallback及compile0，低于6/8；所有patch轮均初稿+最多3次fixer，Super调用均≤4000 completion tokens。direct fallback不冒充三方合并成功。
- T1.6：s1未完成；s3未产生候选，30%降幅门未通过。旧手工/负例GPU与单元测试证据保留，不充当模型修复成绩。
- T1.7：s1有49事件、28模型调用及所需事件顺序；但本次通过eval worker调用核心流程，字面headroom fix命令未观察。九个worker均exit0不等于九个CLI exit0；根据已核对状态推导CLI码为0,78,0,0,78,78,78,78,78。
- T1.8：九份JSON/Markdown报告均存在、均≥7个二级标题；实际scripts/check_report_numbers.py逐份运行9/9通过。唯一最终选中patch的独立apply-check收尾证据见mvp-v4-s8-selected-apply-check.json；没有选中patch的八项为n/a。
- T1.9：nanoGPT无候选、fit22未通过，loss unknown；≤0.8USD费用门单独成立，不能替代MVP≤0.6门或22GB门。
- T1.12：报告/来源/清理/费用/时长门成立；目标0/9和真实CLI入口门未通过，不能进入“已验收”。
- T2.2：真实模型工具循环形成9条research记录、8次API、7个记录credits；s4成功提取匹配PyTorch2.5的checkpoint文档，s5命中s3缓存且API/credits均0。但原要求的s1 checkpoint Sources与s5 CUDA memory Sources均缺，完整门未过。
- T2.3：8场景仅4项完整标注；这4项40个可评分栈中仅3个类别与启发式一致，其他4项失败不能被剔除。每项费用上界≤0.02成立，完整覆盖/≥80%一致率门未过。

## Top 3失败模式与已经做过的调整

1. **补丁结构仍不可靠。** v2的reasoning耗尽已通过显式reasoning=False处理；v3的无换行字符串已改成diff_lines并保留原响应与规范diff。v4共110次patch尝试：88格式/安全拒绝、19应用失败、1响应拒绝、2应用编译成功。109个非空diff中107个被拒，另1个响应形态unknown。实证包括缺前缀、hunk计数不符、复制展示行号及缺少上下文；JSON合法不代表可应用。
2. **静态成功不保证有效修改执行路径。** s1零context hunks把代码追加到main调用/异常分支之后，原forward仍OOM。s8先在GPU创建teacher再搬到CPU，保留小幅改善但未消除先前峰值。真实Lab与keep/revert正确保留失败或不足目标的事实；没有手工替模型写场景答案。
3. **诊断/证据附属门仍有缺口。** 多项搜索以needs_more_info结束；Nano出现标签覆盖/类别不一致；Tavily虽有真实调用和缓存，指定Sources未齐。s2原39.8715%<40%、已fit22却要求两轮才fit22、默认禁精度变化却要求bf16档等原计划冲突仍需逐项讨论。

## 模型、服务与验证体验

T0.4全部60项探测已执行并保留失败；Ultra实测500029输入token成功，900k返回429，其未知1.049344USD上界继续占用，不宣称完整1M请求成功或精确最大上下文。T1.3真实53记录/268920输入token通过。独立诊断v5首因7/8且引用8/8有效，但完整政策/计划门未过。Super通用docstring组件最终经正常fixer应用/编译通过，只证明组件，不计MVP成功。Nano缺cache split时actual保持null，独立核验上界；Tavily工具与费用记录见上。

当前源码完整回归2026 passed（551.34秒），运行期间236项源/配置/测试/生产prompt哈希不变；后续仅泄密扫描器精确非秘密哈希例外发生配置变化，生产代码/测试/prompt未变。前端68测试、typecheck、build既有结果保留，未伪称本次重跑。当前Home单次Lighthouse99，390px无横向溢出；这不是浏览器实时修复验收。T2.7三场景六GPU臂峰值差0%，独立Popen控制器在Docker内、共享采集协议，宿主EPERM历史保留。

## 赠送额度与后续预算

截至最终财务复核，总账298次attempt全部结算、46个run全部关闭，无pending/unresolved/halt。runtime已知3.056058592USD，保守3.077893672USD；既定9.99964904USD runtime池剩6.921755368USD。加外部探测保守占用1.82224246USD，总净保守占用4.900136132USD；21%税预留后5.92916471972USD。这是内部保守核算，非账户实扣/发票，也不使用旧UI余额当现时余额。原16USD净总包络、税/备用与10USD评审储备未调整；未充值、未转移未用探测池，历史未知费用未释放。

## Phase 2建议与必须由Frank决定的下一步

先解决MVP补丁可靠性，再做完整Phase2与主表/消融。只读提案mvp-v4-next-repair-options.md给出三项具体方案：有界结构化格式错误反馈；将原文与展示行号分离并验证基线hash/精确旧块锚点；验证实际应用位置与锚点一致。全部保留原数值、参数量、吞吐、4000token和每patch三次修复门，不预写场景答案。方案尚未实施。

原docs/PLAN.md第41行：若未达标，“最多再修3轮，仍不达标则停下等Frank”。v1初次失败、v2/v3/v4三次修复均已保留。当前需要的是是否允许追加有界MVP修复轮数，不是重新索要已授权的赠送额度调用许可；本次不自行开始第4轮或更改阈值。

真实五条规定修复回放、浏览器完整运行、HF修复、Watch真实修复、10×2/12主评测与消融仍未通过。设计稿/还原认可、域名/Cloudflare和告警收件渠道、视频/Devpost最终提交及未来日期在线检查仍各有独立门。没有发布evaluation/release标签、公开服务或提交比赛。

## 证据与交付

- 原campaign：runs/evaluation/live/20261024T231940915002Z-2098d11d/campaign.json（私有原始运行）。
- 固定九项：reports/live-campaign-20261025/mvp-v4-audit-v2.json。
- 费用/CLI：同目录mvp-v4-finance-review.json、mvp-v4-cli-exit-semantics.json。
- 候选与子门：同目录mvp-v4-candidate-verification-review.json、mvp-v4-candidate-verification-supplement.json。
- 报告数字：同目录mvp-v4-report-number-checks.json；选中patch：mvp-v4-s8-selected-apply-check.json。
- 后续提案：同目录mvp-v4-next-repair-options.md；完整未完成门：reports/final-decision-20261025.md。
- 当前完整回归：reports/patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json。
- 本任务既有localhost preview已重启加载78a83df，health/Home200，无UI提交；mvp-v4-final-source-check.json与final-preview-restart.json保留收尾证据。
- 最终handoff合并本页、RESULTS和PROGRESS，纯文本小于1MiB。提交前扫描/交付状态单独记录；原失败和旧summary保留。

## MVP v5 — 2026-10-25

Original target gate:0/9. First-category match:7/9 (2 unknown); unchanged auditor also requires valid diagnosis, giving6 true/1 false/2 unknown.17/52 patch attempts applied/compiled with independently verified source-byte chains;5/8 synthetic scenes had an applied candidate. s4 completed20 steps and reduced measured peak89.769367%, but the original scalar-loss check compared batch1 reference with batch8 candidate and rejected it. No final configuration selected. All nine scenes executed; PLAN and manifest unchanged. Details: reports/phase-1-summary-20261025-mvp-v5.md.

98 calls: all-call known$0.89236424, verified bounded remainder$0.00460392, conservative$0.89696816, actual-total null. Campaign known0 is its fully-known-run-only subtotal, not all-call known cost. Real CLI invocation still not observed in v5.

## MVP v6 — fixed-nine live evaluation, 2026-10-25

Source765b64d; original9 executed,1target(s3),6valid firstcauses/1invalid/2unknown. s3:20updates,2.435717632→0.64841984GB (73.378694%),identicalloss,maxdelta0,params37791744unchanged,CLI0,finalpatchclean-reapplybytesmatch. OthersCLI78;all9literalexecutionchainsverified. 32calls knownsubtotal0.531157108USD,verifiedboundedremainder0.00419238,conservative0.535349488;actualtotalunknown. No changedthresholds, no recharge. Full details: reports/phase-1-summary-20261025-mvp-v6.md.

V7 quality checkpoint: full guarded backend 2,218 passed in 560.90s; 247 source entries and original PLAN/guard unchanged, no skips. This is software regression evidence; the final nine-case live result is pending.

## Final authorized MVP v7 — 2026-10-25



| 场景 | 首因含有效性门 | 静态应用 | 目标 | 实际 CLI | 费用或上界 USD | 秒 |
|---|---|---|---|---|---|---|
| s1_batch_too_big | 未通过 | 未形成候选 | 未达标 | 78 | 0.0370895 | 20.55 |
| s2_fp32_adamw_1b | 正确 | 未形成候选 | 未达标 | 78 | 0.048574428 | 57.07 |
| s3_eval_no_grad_missing | 未通过 | 未形成候选 | 未达标 | 78 | 0.05275352 | 30.78 |
| s4_loss_accumulation_graph | 正确 | 是 | 未达标 | 78 | 0.068272628 | 62.11 |
| s5_fragmentation_varlen | 未知 | 未形成候选 | 未达标 | 78 | 0.040313208 | 32.20 |
| s6_full_vocab_logits_fp32 | 未通过 | 未形成候选 | 未达标 | 78 | 0.033068228 | 18.01 |
| s7_frozen_params_optimizer_state | 正确 | 是 | 未达标 | 78 | 0.062629008 | 54.95 |
| s8_two_models_resident | 正确 | 是 | 达标 | 0 | 0.048958968 | 34.82 |
| nanogpt | 未知 | 未形成候选 | 未达标 | 78 | 0.063958528 | 25.46 |

表中费用是 exact 或经核实保守上界；两个 bounded run 的 actual 仍未知。全部九项在原 $0.6 / 480 秒验收线内。原审计器保留 CLI“未观测”占位，真实退出码以独立 literal-cli 审计为准。

## 本轮实现及质量

两模型共享实际启动参数、当前保留源码身份、失败补丁内容及哈希、结构错误和详细验证反馈。组合上下文限制 64 KiB；截断/缺失明确标为未知，凭据类参数仅在提示词脱敏，真实执行 argv 不改。基线 OOM 且候选未完成时，参考运行说明改为如实说明未执行参考，控制流和比较门不变。

完整 guarded 回归 **2,218 passed，560.90 秒，无跳过**；247 个生产/配置/测试/提示词条目在前后和当前一致，原 PLAN/guard 不变。Ruff、格式、diff 检查通过；源码提交前 gitleaks 零发现。原始源码摘要被扫描器误识别的五项均逐文件重新计算证实非凭据，重复审批映射保留在私有执行凭据，公开 before/after 清单完整保留；未放宽扫描配置。

本轮只有三次补丁生成，全部一次应用并编译（s4/s7/s8）；source-span 独立审计三条转换/实际候选/选择链完整，无 unknown 或矛盾。T1.5 仍仅 3/8，低于原 6/8。其余六场景未形成候选；八个失败 run 最终均为 needs_more_info。

## 成功与失败的准确边界

- **s8 真实目标成功**：只把停用教师模型的构造设备移至 CPU，保留模型与参数；完成 20 次更新，峰值 3.100141568→0.121791488 GB，下降 **96.0714217293%**。记录的 scalar loss identical、最大差值 0，参数量 747,474,432 不变；原数值、精度、参数、吞吐和显存目标门通过。same_inputs / same_effective_batch / same_objective 均为 unknown，故这是原标量比较门通过，不能称完整配对数学等价。
- s8 公开 patch 在干净原始源码上 git apply --check / apply 均退出 0，静态解析通过，所得源码与实际 GPU 候选逐字节一致。公开 patch 比原始尝试仅多一行 diff --git 标头；两者的修复正文一致。没有再次调用模型或 GPU。
- s4 / s7 均完成 20 步并降低显存，仍被原数值门拒绝；s4 是不同 batch 参考比较，s7 配对关系未知。保留 revert，不能仅据 scalar 差值证明相同工作负载下数学行为改变。
- s3 本轮没有生成补丁；历史 v6 的 s3 73.378694% 降幅、完整配对门及干净重应用证据继续保留，但不能拼成 v7 的第二个成功。
- nanoGPT 真实启动 batch_size=32、gradient_accumulation_steps=1，模型仍按源码默认 12/40 解释并提议 8/60，最终需补充信息，未形成补丁。这表明新增上下文尚未被可靠利用。

## 上下文观测局限

冻结源码和请求捕获单测证明两模型的上下文组装/传递路径；s4/s7 第二轮实际回复引用了前轮峰值、loss 和配对失败信息，提供行为佐证。可是 11 份 condition 初始请求审计副本由 evaluator 另行重建，未包含新增 execution/candidate/verification 字段；provider wire 和 Super 完整请求未单独留存，实际完整输入不可据这些副本逐字节证明。保留该缺口，不把副本缺字段直接等同生产漏传，也不声称所有 CLI 参数被模型正确理解。

wrapper seed 与脚本自身重设 seed 分开记录；s4 默认脚本 seed 7、s8 默认 17，不因 wrapper seed 1337 就判其错误。后续若获授权，需补全实际请求记录并验证语义使用；本轮不修改正在验收的源码或追加试跑。

## 费用及历史

本轮 25 次调用：全调用已知小计 **$0.454596996**，两条经核实未知费用上界合计 **$0.001021020**，保守总额 **$0.455618016**。actual 总额仍未知。campaign.summary 的 $0.365774996 只计七个费用完全已知的整 run，另 $0.088822000 已知调用位于两个 bounded run 内，不能遗漏。

全 runtime 457 attempts / 76 runs 全部结算关闭，pending/unresolved/halt 均 0；已知 $4.936747036、保守 $4.968399436，原 $9.99964904 运行池余额 **$5.031249604**。这不是控制台赠送余额。外部探测已知或保留 $1.82224246 单列，合并保守净额 $6.790641896；不是含税发票或信用卡充值金额。未充值、未扩池、未超额，旧 432 attempts / 67 runs 的历史投影完整重建。

| 追加轮 | 单轮目标 | 成功案例 |
|---|---|---|
| v5 | 0/9 | 无 |
| v6 | 1/9 | s3 |
| v7 | 1/9 | s8 |

不同源码版本的成功不合并为统一成功率；没有声称主评测或消融通过。

## 交付和下一步决策

最终文件：README、PROGRESS、RESULTS、FEEDBACK、DEVPOST 草稿、此 summary、三项审计、独立财务与候选审查、干净重应用记录，以及纯文本 handoff。旧版本全部保留；原计划未改。后续主评测/消融、真实完整 UI 流程、合格修复回放、干净 clone 实测、公网域名与告警、视频和 Devpost 提交仍未验收，不创建发布标签。

具体后续范围见 reports/final-decision-20261025-v7.md；完整余项清单见 reports/remaining-acceptance-20261025-v7.md（其编写时 v7 尚在运行，结果以本摘要为准）。建议先逐项讨论已知验收冲突与模型拒绝/误读原因，再决定是否追加有限修复；在决定前继续保留原标准。

审计索引均在 reports/live-campaign-20261025：mvp-v7-audit-v2.json、mvp-v7-source-span-review.json、mvp-v7-literal-cli-audit.json、mvp-v7-finance-review.json、mvp-v7-candidate-review.json、mvp-v7-s8-clean-reapply.json、mvp-v7-audit-execution.json。

----- END docs/RESULTS.md -----


----- BEGIN PROGRESS.md -----

# Headroom Progress

Initialized: 2026-10-23T00:44:58.397951+00:00
Canonical plan: docs/PLAN.md (v4.2, preserved verbatim).
All work, caches, runs, and media remain on azuki.

## Tasks

| Task | Description | Status | Evidence |
|---|---|---|---|
| T0.1 | 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min） | 已验收 | reports/t0.1-acceptance-promo-20261024.json; official promo face25USD redeemed, UI30.25USD incl.tax; current matching key/0600/env and both authenticated catalogues200 with4/5Nemotron models; public Apache2 and retained live Tavily proof verified; further inference authorization remains separate |
| T0.2 | 服务器环境勘察（P0，~30min） | 已验收 | docs/ENV.md; reports/env-preflight.json; Docker GPU ok, NET ok, 5694.85 GiB free; shared GPU and no sudo recorded |
| T0.3 | 仓库骨架与工具链（P0，~40min） | 已验收 | reports/toolchain-checks.json; reports/pre-commit-t0.3.log; commit ca6c86ad099c519b92d1ccb88219b08450aa8da6, Frank author/committer, pushed origin/main |
| T0.4 | Token Factory 探测（P0，~1h） | 已验收（失败/未支持项保留） | reports/t0.4-acceptance-20261025.json; all60 prescribed samples executed; Ultra500029 provider tokens verified,900k429 retained; Super JSON/tools/concurrency pass; config500029/150000/json_schema/chat_template_kwargs,8 new feedback entries; Nano tools and thinking-budget failures disabled |
| T0.5 | Tavily 探测（P1，~15min） | 已验收 | reports/t0.5-acceptance.json; live exit0, 4/4 operations, 2 factual FEEDBACK entries, observed schema; API total3 credits matches UI3/1000 |
| T0.6 | 场景集 v0（P0，~2h） | 已验收 | reports/t0.6-acceptance.json; 3 synthetic CUDA OOM <7s, 5 reclaim completed20 steps with measured README peaks; pinned nanoGPT CUDA OOM11.489s; all cleanup verified |
| T1.1 | Lab 包装器：运行并抓证据（P0，~3h） | 原验收保留；绝对截止及部分证据GPU增强通过 | reports/t1.1-acceptance.json retains original checks; reports/deadline-manual-gpu-20261024T131612Z.json verifies shared hard deadline, natural/small-timeout full captures, stress timeout explicit partial, canonical s3 twice20updates; no invented inference training steps |
| T1.2 | 证据包生成（P0，~3h） | 实现完成，验收未通过 | reports/t1.2-acceptance.json; s1/s2/s4/s5 artifacts and real peak replay verified; s2 optimizer-state fraction 39.8715% < original 40% |
| T1.3 | LLM 客户端与路由（P0，~1.5h） | 已验收 | reports/t1.3-acceptance-20261025.json; actual client/router Super schema passed; authentic53-record Ultra evidence returned268920 server input tokens; both1attempt/exact ID/known cost total0.2695014USD; free-text fragmentation overclaim recorded, not diagnosis acceptance |
| T1.4 | Diagnose（Ultra）（P0，~2.5h） | 首因7/8及全部引用有效；完整验收未通过 | reports/live-campaign-20261025/diagnosis-attempt4-review.json; v5八次真实响应stop/0 reasoning，cost0.328770USD；s1/s6禁止改动及s7需补充信息保留；原6/8与政策门未改 |
| T1.5 | Patch（Super）与应用（P0，~2.5h） | v7真实3/8应用编译；原≥6/8未通过 | v7 three attempts all applied/compiled(s4/s7/s8); source-span conversion/application/selected chains independently verified; original<=3fixers/4000tokens retained |
| T1.6 | Verify 与比较（P0，~2h） | 历史v6 s3通过；v7 s8标量门通过；s1仍未通过 | v7 s8 20updates/96.0714217%reduction/scalaridentical/paramsunchanged; pairingunknown; v6s3 fullpairing success preserved; v7s1 no candidate |
| T1.7 | 单轮编排 + 存储 + 事件（P0，~2h） | 九条真实CLI链已核；原s1事件及全零退出门未通过 | v7 9CLI chainsverified; s8exit0/others78; s1 stopsbeforepatch and full ordered eventgate notpassed |
| T1.8 | 报告（P0，~1.5h） | 九报告数字及s8选中补丁干净重应用通过 | mvp-v7-audit-v2.json and mvp-v7-s8-clean-reapply.json; publicpatch reapplies to exact GPUcandidate bytes |
| T1.9 | 真实仓库：nanoGPT（P0，~2h） | 真实nanoGPT已执行；修复门未通过 | v7 realCLI32/1 but modelplan defaults12/40;needs_human/no candidate/CLI78;cost0.063958528USD |
| T1.10 | Honesty 与安全（P0，~1h） | 静态与CPU真实性检查通过；完整修复待办 | docs/PATCH.md; model shrink/truncation/escape checks and observed parameter counts |
| T1.11 | Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h） | 自有Python镜像、干净目录CPU及隔离组件通过 | docs/LAB_RUNTIME.md; hash-locked image-owned Python3.12, verified immutable image ID, no host venv mount; clean candidate tree script/module each3updates with capture/cleanup verified |
| T1.12 | MVP 整体验收 + 报告（P0，~1.5h，10/24 晚） | 追加三轮已用完；v7目标1/9未通过，待Frank决定 | v7 all9live/25calls; target1/9; cause raw6/valid4true3false2unknown;9CLIchains 1zero8exit78; originalPLAN0.6 stop |
| T2.1 | 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h） | 有界搜索与逐轮验证反馈完成；真实验收待办 | docs/SEARCH.md; selected state survives revert; per-round verification-feedback.json exposes actual loss/check/error facts to later rounds; original s2/bf16 policy gates unchanged |
| T2.2 | Tavily Research（P0，~2h） | 真实模型研究与缓存已测；指定Sources门未通过 | v4 research9rows/8API/7credits;s4PyTorch2.5checkpoint extract;s3->s5cache0API0credits;s1checkpoint/s5CUDA memorySources absent |
| T2.3 | Nano 栈标注（P1，~1h） | 真实8场景已测；覆盖和一致率未通过 | v4 4/8complete;completed outputs3/40heuristic matches;failed4not excluded;all<=0.02certified upper |
| T2.4 | 预算守卫与成本面板（P0，~45min） | 真实费用链复核通过；原额外预算门待办 | 457settledattempts/76closedruns/0pending unresolved halt; runtimeconservative4.968399436/remaining5.031249604;original.05/.1 cases unexecuted |
| T2.5 | HF Transformers 场景（P1，~2h） | HF场景CPU/GPU基线通过；修复待办 | reports/hf-trainer-baseline-20261024.json; real Trainer OOM; configuration-only repair gate pending |
| T2.6 | Watch 模式（P2，~1.5h） | shell/Python启动器可定位唯一CUDA OOM子进程并重跑；真实模型修复验收待办 | docs/WATCH_HF.md; preserved multi-process inventory and selected capture binding; exact target replay; manual real GPU helper+s1 OOM selected correctly; candidate/reference each20updates passed; duplicate/OOM ambiguity and root failures rejected; no host fallback |
| T2.7 | Docker/HF 缓存稳健性（P1）：验收：三个场景在 Docker 路径下结果与子进程路径一致（峰值差 ≤ 1%）。 | 已验收 | reports/t2.7-acceptance-20261025.json; six actual GPU arms independently audited; s1/s3/HF allocated/reserved peak differences 0% <=1%; s3 both20updates/identical losses, s1/HF genuineOOM; Docker-contained independent subprocess controller, source/image/seed/capture/cleanup verified; original hostEPERM retained |
| T2.8 | 小评测 + 自优化（P0，可夜间自治，~4h） | 显式策略矩阵与离线统计完成；原真实验收待办 | docs/EVALUATION.md; default/strict 实际等价，allow_precision 必须显式选择；全矩阵共享预算，逐行完整 Policy；原两档歧义、≤3轮优化、target_met/首因各≥75% 和 $12 实测均未关闭 |
| T3.1 | FastAPI + SSE（P0，~3h） | API队列/SSE/选中轮次下载已实现并测 | docs/API.md; selected round after PNG/JSON and configuration manifest; missing selected evidence never falls back to stale files; existing ownership/nofollow/deadline rules retained |
| T3.2 | 前端素版（P0，~4h） | 当前Home性能99及390px无溢出；真实修复UI待办 | reports/home-performance-20261025/receipt.json;one completed Lighthouse13.5/Chrome151 sample,FCP1.36s/LCP1.51s/TBT0/CLS0.0396;currentdist unchanged,390px widths390/no overflowing elements;68frontend tests/typecheck/build retained. Baseline Home only,no live run submitted;browser processes cleaned beforeGPU |
| T3.3 | Replay（P0，~1.5h） | 5条真实基线回放可用；规定修复回放待办 | reports/baseline-replays.json; explicitly baseline-only; s2 two-round/nanoGPT/reclaim repair replay not fabricated |
| T3.4 | Claude Design 对齐（P1，~3h；设计稿 10/25–10/26 由 Frank+Claude 产出到 `design/`） | 待Frank设计稿与认可 | No design package has been supplied; theme implementation exists |
| T3.5 | 公网部署、限流、监控（P0，~2.5h；Frank 提供域名/Cloudflare） | 默认关闭的告警投递已实现；公网/真实收件待办 | docs/DEPLOYMENT.md; explicit HTTPS webhook, durable incident/attempt state, bounded retry, identical idempotent payload and unknown delivery; 57 guarded tests and systemd template verification; no channel configured or service/timer installed |
| T3.6 | 预录素材（P0，~1h） | 8张真实基线UI素材完成；完整修复素材待办 | docs/media/ui-20261024T025659Z-baseline-only; baseline-only labels, desktop/mobile Home/Results/About/Run; no repaired before-after/diagnosis/diff fabricated |
| T4.1 | 评测集定稿 | 基线范围已验收 | reports/evaluation-baselines-20261024.json; all12 matches, 5 OOM/7 completed20, full capture/cleanup; source pins |
| T4.2 | 主评测 | 工具与表格已准备；真实主评测待办 | docs/EVALUATION.md; docs/RESULTS.md; Nebius live model run required |
| T4.3 | 消融 | 三条件消融工具完成；实测待办 | full Ultra / traceback+summary Ultra / full Super; no predicted gain presented as measured |
| T4.4 | 冻结 | 待真实评测后冻结 | No v0.9-eval tag created before acceptance |
| T5.1 | README | 五命令Quickstart与干净目录CPU通过；真实repair待办 | README.md; locked Python3.12 and self-contained Lab image; reports/portable-lab-20261024 proves script/module capture without local .venv/.env; clean-clone live fix remains pending |
| T5.2 | docs 定稿 | v7最终结果与交接已整理；完整项目验收未完成 | Versionedv5/v6/v7 summaries and finance/CLI/candidate audits; final-decision-20261025-v7.md; no release or submission claimed |
| T5.3 | Devpost 描述 | Devpost本地草稿完成；未保存表单 | docs/DEVPOST.md; owner final review/submission pending |
| T5.4 | 视频 | 视频脚本完成；待真实修复与录制 | docs/VIDEO_SCRIPT.md; <=2:50 storyboard, actual evidence required |
| T5.5 | 首次完整提交 | 未开始 | — |
| T5.6 | 评委视角自检 | 当前就绪审阅完成；发布前复检待办 | reports/submission-readiness-20261024.md; actual repair, public demo/video and submission gate remain pending |
| T5.7 | 最终提交 | 未开始 | — |
| Phase 6 | Weekly health/alerts; balance by Nov 25; manual Dec 1 and Dec 8 access | 未开始 | Future dated acceptance |

## Next acceptance and remaining deliverables

- 2026-10-25T02:08:17.732199+00:00: Frank explicitly authorized up to3 additional MVP repair iterations (v5/v6/v7), with original thresholds/policies and existing gift-only global/day limits unchanged. Extension1 implements exact source-anchored line edits, detailed errors and exact application verification; no success is claimed before integration and real9-case acceptance. The prior stop and failedv1–v4 remain historical evidence.

- Historical v4 checkpoint (superseded by the explicit v5/v6/v7 authorization above; 2026-10-24T23:31:55Z): all9 genuinely executed;0/9targets,7/9firstcauses. Original three repair iterations exhausted. Finish reports/commit/handoff, then stop additional repair work for Frank under PLAN§0.6; no new budget approval is needed for the existing gift-only authorization.

- The dedicated T1.3/T1.4 drivers and native model tool loop are implemented and have now been exercised live. Accepted client capability, partial diagnosis/research evidence and failed repair outcomes remain separately recorded below.
- The owner authorizes remaining original-plan model work using existing gifted credit only, with no recharge/overrun. reports/live-campaign-20261025 records authorization, allocation and the enabled actual_usage profile with verified provider global/day reservations. All60 original T0.4 samples are finalized with failures retained; Ultra900k429 permanently occupies1.049344USD under the completed conservative continuation review. Runtime all-time/current UTC2026-10-24 daily ceiling is9.99964904USD, including spent usage; combined external probe plus maximum runtime day total11.82189150USD remains below12. No unknown charge is treated as zero. T1.3 is accepted; latest T1.4 v5 is7/8 exact first causes with8/8 valid references but incomplete policy/readiness. Its0.328770USD calls are known; subsequent MVP Nano missing-cache usage retained0.01644864USD and halted the runtime. Earlier v2/v3/v4 failures remain preserved.
- Keep original failed gates and procedure conflicts visible: s2's 39.8715% optimizer fraction versus40%, default precision policy/bf16 tier. T2.7 isolation comparison is now accepted with its Docker-contained reference boundary.
- Final authorized T1.12 v7 completed all nine: target1/9, raw cause6/9, valid4true/3false/2unknown; one actualCLI0/eight78, all original cost/time bounds pass. Additional three iterations exhausted; no failed run replaced by offline success.
- T3.5 / Phase6 webhook delivery is implemented but disabled. The owner must select/authorize a real destination and supply public domain/Cloudflare access before deployment and delivery acceptance; no recipient message or unit installation has occurred.
- Current requirement-by-requirement source audit found no additional independently implementable feature gap at1452d27; see reports/readiness-after-outcomes-20261024.md. This does not establish full acceptance or release readiness. Owner design, genuine repair replay/media, final review/video/submission and future dated uptime checks remain separately open.
- No original threshold is lowered, no old run is replaced, and no evaluation/release tag is created before acceptance.

## Acceptance log

- 2026-10-24T21:22:45.657445+00:00: T0.4 accepted from all60 actual prescribed samples (55 new,5 historical); Ultra64k/200k/500k exact retrieval succeeded,900k hit429 and was not retried. Super4 concurrency passed. Installed tested input lower bound500029 and evidence budget150000; no exact-maximum claim. Known usage-priced total0.77289846USD, plus permanent unknown upper1.049344USD gives conservative occupied1.82224246USD. Native schema and template reasoning chosen; Nano tools and unproven thinking-budget methods disabled. Original PLAN unchanged; T1.3/T1.4/repair gates remain separate.

- 2026-10-24T20:43:13.008906+00:00: completed the authorized first model capability checkpoint: exactly1 Ultra chat,1 Super native json_schema,1 Super generated add tool call; HTTP200/exact identity/complete usage, no retries or unresolved charges. Token cost0.0003143USD;21% reference0.000380303USD, not reconciled invoice. Account remained Active with rounded30.25USD incl.tax balance and separate1USD trial. Catalogue prices/context/fees were manually compared before each dispatch; current probe code does not enforce that comparison itself. No Tavily/GPU/repair/runtime activation or recharge. Three-call authorization fully consumed; full T0.4/T1.3/MVP and original failed gates remain open. Evidence: reports/model-checkpoint-20261025/verification.json.

- 2026-10-24T14:54:54.961187+00:00: completed T0.1 account/credit gate: official received25USD promo redeemed in the existing Token Factory organization, refreshed transaction shows AI Builder Program Credits +30.25USD including tax, trial separately1USD. Existing console/server key mask matches, both fresh official GET catalogues200 with4/5Nemotron models, private0600 ignored env and public Apache2 repository verified; prior accepted live Tavily evidence retained. No card top-up, new key/terms or new model/Tavily/GPU work. First1.25USD token/2USD total checkpoint requested, not yet authorized; live profile remains absent. Promo-arrival heartbeat paused after fulfillment. Reports: reports/promo-redemption-20261024.json and reports/t0.1-acceptance-promo-20261024.json. Full goal remains active.

- 2026-10-24T14:43:16.949374+00:00: completed original T1.12 actual patch/config application, selected configuration completion and per-round facts through JSON/Markdown/curated API/UI; reverts retain application facts and ambiguous evidence remains unknown. Default-disabled T3.5/Phase6 HTTPS notification delivery now has durable incident state, bounded retry and safe unknown-delivery handling. Full guarded backend1583passed473.96s; all148 source hashes unchanged and current; frontend66passed/typecheck/build. Four retained offline pipeline outcomes and actual desktop/390px browser layout verified; live score count remains0. Health unit templates validate but are not installed or enabled. New model/Tavily calls/GPU workloads/notifications/cost0; live runtime profile absent; original PLAN/gates unchanged. Reports: reports/outcomes-monitoring-20261024/verification.json and reports/handoff-outcomes-monitoring-20261024.md. Full goal remains active; current requirement audit and external acceptance are separate.

- 2026-10-24T14:23:27.338609+00:00: implemented dedicated T1.3/T1.4 prepare/execute acceptance drivers over the actual client/router and shared durable ledger, plus native Super/Tavily tool calling in production search. Independent audit rebuilt authentic s2 evidence byte-for-byte from53 original records (222428 local content tokens), verified all8 diagnosis packages and unchanged source captures; local counts/fixtures do not accept live model gates. Full guarded backend1485passed472.39s; source hashes unchanged and rechecked. Localhost preview health and baseline downloads200; no frontend changes or new frontend suite claimed. New model/Tavily calls/GPU runs/cost0; live profile absent, original PLAN/gates unchanged. Reports: reports/acceptance-integration-20261024/verification.json and reports/handoff-acceptance-integration-20261024.md. Remaining independent gaps: original MVP patch-application/completed columns and default-disabled health notifier delivery. Full goal remains active.

- 2026-10-24T13:56:31.488370+00:00: connected actual bounded round verification feedback, source-bound budgeted Nano opinions in evidence/report/UI, coherent optional-publication recovery and download locators, and pinned bitsandbytes research routing. Final guarded backend1387passed456.37s with unchanged sources; frontend51passed/typecheck/build. Historical real baseline plus14 synthetic offline labels retained all measurements and original hashes; this is not live model accuracy. Initial missing-env failures and interrupted review-fix run preserved. New model-inference/Tavily calls/GPU workloads/cost0; no live profile, PLAN or original gate changes. Reports: reports/diagnostic-context-20261024/verification.json and reports/handoff-diagnostic-context-20261024.md. Genuine client/diagnosis acceptance drivers and model Tavily tool loop remain independently implementable. Full goal remains active.

- 2026-10-24T13:25:14.043559+00:00: portable image now owns Python3.12/hash-locked CUDA dependencies and runs by verified immutable image ID; clean candidate tree with no .venv/.env passed script/module CPU capture. Shared absolute hard deadline and durable partial-first finalization retain timeout facts without inventing success; actual GPU natural/small-timeout complete, continuous stress explicitly partial, and two canonical s3 runs completed20 with deterministic first5 losses. Selected-round after evidence/configuration downloads and report/UI execution metadata fixed; CLI-only empty patch distinguished. Full guarded backend1344passed450.83s with unchanged sources; frontend50passed/typecheck/build and historical browser compatibility verified. Initial GPU serialization failure preserved. New model calls/cost0; no live profile/PLAN/gate changes. Reports: reports/portable-delivery-20261024/verification.json and reports/handoff-portable-lab-20261024.md. Full goal remains active.

- 2026-10-24 bounded Pareto continuation: explicit until_target/bounded_pareto across CLI/YAML/API/Watch/evaluation/UI; default stops at first verified target, bounded stays within <=6 rounds and unchanged policy/budget/deadline. Later revert/budget/error retains selected patch/metrics/verification together; fresh-evidence loss clears stale after image. Search metadata distinguishes baseline goal, first verified target and exploration termination. Cross-mode ablation pairs are excluded; missing historical mode remains unknown. Full guarded backend1266passed322.07s with unchanged sources; frontend47passed/typecheck/build and browser baseline-only display verified. Ruff/precommit/gitleaks passed. Reports: reports/bounded-pareto-20261024/verification.json and reports/handoff-bounded-pareto-20261024.md. New model calls/cost0; no new GPU workload, no live runtime profile. All original failed/external gates remain open.

- 2026-10-24T12:33:06.435709+00:00: multi-process wrappers now select a unique CUDA OOM target and replay the same entrypoint for candidate/reference while preserving all raw captures and wrapper exit semantics. Explicit Ultra local-estimate admission is separate from verified bounds/actual usage; unknown billing persists and blocks further dispatch; default strict/live-disabled retained. Full guarded backend1186tests passed315.96s with source unchanged; frontend42tests/build passed. Real GPU helper+s1 baseline OOM, candidate/reference20updates,101007360parameters, exact compared losses and selected child snapshot peak passed; manual change earns zero model benchmark credit. The first full run found a real concurrent WAL initialization race (1failed1166passed), now fixed with bounded pre-transaction retry and preserved logs. Local preview refreshed; no new model calls/cost or original PLAN change. See reports/multicapture-admission-20261024/verification.json. Full goal remains active; bounded Pareto exploration remains independently implementable.

- 2026-10-24T12:04:28.000883+00:00: runtime precision observation now selects original FP32/BF16 tolerance and records actual precision changes; shell launchers with one mapped Python target preserve wrapper/cwd/module while replaying patched target arguments. Guarded full backend1100tests passed257.33s with source hashes unchanged; frontend39tests/build passed. Actual CUDA FP32/BF16 runs each completed20updates/20losses, observed change and2% tolerance verified (max delta0.0001003146). Stable s2 diagnostic copy explains foreach temporary peak but does not replace canonical acceptance. No new model calls/cost, profile enablement or PLAN changes. Evidence reports/precision-wrapper-20261024/verification.json.

- 2026-10-24T11:37:25.038903+00:00: restored the retained original scalar-loss contract instead of unapproved global pairing gates; optional pairing remains evidence. Added scoped repository no-reference n/a acceptance, CLI/YAML policy controls, exact Python flags/module replay through baseline/candidate/reference/Watch/API/evaluation, and separate nine-case MVP20% reclaim targets (general default30% unchanged). Guarded full backend1035tests passed with unchanged source hashes; frontend39tests/typecheck/build passed. Manual non-pinned Python module GPU regression completed20updates twice,73.3787%peak saving, identical observed losses and unknown pairing; zero model benchmark credit. Local preview refreshed; six-hour read-only promo follow-up installed. New model cost0, no recharge/public submission, PLAN bytes unchanged. Full goal remains active; see reports/original-plan-contract-20261024/verification.json.

- 2026-10-24 11:18UTC: original-goal continuation closed concrete production gaps: explicit diagnosis information requests stop after one call (including empty plan), reclaim planning uses remaining reduction against the fixed original30% target, per-round stored diffs/verification remain visible after revert, curated Results campaigns and measured/unknown summaries/paired-ablation Markdown are implemented. Automatic pairing now derives actual tensor/initial-parameter/per-update evidence for bounded s3/s4 contracts; other sources and historical captures remain unknown. Full guarded backend923tests passed160.25s with unchanged source hashes; frontend38tests/typecheck/build passed. Two full-size manual s3 GPU runs verified20updates, unchanged37,791,744parameters, exact loss equality,73.3787%peak reduction and0.3333%optimizer-interval increase; no model generated this repair and it contributes zero model benchmark successes. No additional model charge, recharge, public port, submission, or original PLAN/gate change. See reports/plan-completion-20261024/verification.json and reports/handoff-plan-completion-20261024.md. Original full goal remains incomplete.

- 2026-10-24T10:54:58.477225+00:00: continuation completed the explicit model output cap/exact Nano ID, CPU-only complete-request audit, shared600s admission deadline, owned preparation cleanup including supervisor death, report-ready SSE, cached read-only availability/local budget, and the host-versus-reviewed HF cache separation. Full guarded backend859tests passed142.74s with source hashes unchanged; frontend33tests/typecheck/build passed on Node24.22.1; four real15s health polls stayed fresh and browser baseline report links worked. Reports: continuation-validation-20261024.json and handoff-continuation-20261024.md. Earlier18 CPU failures, Node startup failure and stale-preview observations remain preserved. Minimal Super/Nano calls are the only new model inference; no further billing, GPU repair, public deployment or submission was performed. Original PLAN/gates remain unchanged.

- 2026-10-24 10:24UTC: user confirmed private key setup and explicitly authorized only up to0.10USD trial credit for minimal connectivity. Both official catalogue GETs succeeded; one Super and one Nano chat each returned200/stop with exact identity, valid usage, zero retries and no cap violation. Usage-priced total0.00003666USD, with21% tax reserve0.0000443586USD; not an invoice reconciliation. Evidence reports/tokenfactory-minimal-20261024.json. No Ultra/full evaluation or recharge authorized; live runtime remains disabled. User also requests continued original-goal development and later use of promotional credits when they arrive. Original PLAN and failed gates remain unchanged.

- 2026-10-24 full-development checkpoint: final backend718tests passed107.57s; frontend27tests/typecheck/build passed; Home Lighthouse90/90/90 and real baseline Run89/98/89. Twelve actual GPU baselines matched5OOM/7completed20 with capture and cleanup verified. Full source-hash receipt: reports/final-validation-20261024.json; handoff: reports/handoff-development-20261024.md. Real Research added3credits; refreshed Tavily total6/1000,994remain, pay-as-you-go off. Nebius key/profile absent; no authenticated Nebius inference or recharge performed. All original failed gates retained.

- 2026-10-24: Frank explicitly requests full original-plan development, continuing every implementable part while only genuinely Nebius-dependent work waits. Implement later components with honest offline/real-evidence verification; retain original acceptance gates and existing failures. Self-funded Token Factory availability is being researched; no payment or paid inference has been authorized by that question.

- 2026-10-24 00:57 UTC: Frank completed hidden-input Tavily import; private .env preflight passed. The authorized four-operation live probe exited0; basic/advanced searches and both exact-URL extracts succeeded. Report: reports/probe-tavily-20261024T005720856027Z-332161bd.json. Two factual feedback entries (TAVILY-001/002) and observed TOOLS schemas are now recorded; independent read-only review confirmed API checks. Full T0.5 acceptance: reports/t0.5-acceptance.json.
- Account usage was independently refreshed before and after this run: free-plan used credits moved0 to3/1000, matching API total3;997 remain, pay-as-you-go and auto-upgrade are off, and the UI says requests stop at plan limit. Evidence: reports/tavily-account-after-20261024T005808Z.json. The two extract responses reporting0 do not prove future extraction is free. Nebius remains deferred/unverified; no model calls or other task acceptance is implied.

- 2026-10-24 offline continuation completed: reports/api-prep-20261023T222659Z.json records 259 passed in53.97s, Ruff and formatting passed, and the default model-probe dry-run planned62 operations with network_requests=0 and accepted=false. New coverage includes55 guarded probe tests,82 LLM client/router/cost tests,25 diagnosis checks and2 SDK/schema/evidence integration tests. Full prior tests remain green; historical runs are preserved. Original PLAN SHA remains e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.
- Independent review fixed native-versus-fenced JSON classification, retry dispatch after a shared budget violation, absolute streaming deadlines, nonfinite JSON, malformed SDK responses missing accounting, and response model identity. Missing or mismatched identity cannot become accepted capability/diagnosis; uncertain billing stays unknown and model probes halt further paid dispatch. T0.4/T1.3/T1.4 remain unaccepted pending real model calls.
- Test-isolation incident retained: an earlier AsyncClient refactor round attempted three official-endpoint transports using only a fixed dummy credential; exact network outcomes are unknown. No real key or .env was used by those tests. Corrected mocks and independent DNS/socket-denial guards passed, including separate reviewer checks. See docs/MODELS.md; do not describe the whole development turn as zero network.
- Historical pre-import credential check (superseded by the verified Tavily import above): server .env was0600; Tavily and Nebius values were empty. Hidden-input Tavily importer syntax validated. No authenticated model/search probe was run; the Tavily four-operation live check remains pending import, and Nebius registration/credit troubleshooting remains deferred at Frank's request.

- 2026-10-24: Frank asked to defer the Nebius registration/credit issue and start previously account-dependent work. Proceed with T0.4/T1.3 offline preparation and T1.4 schema/prompt checks while keeping their live acceptance pending. This sequencing instruction does not waive T1.2, numerical, loop, or cost gates.
- Tavily live UI preflight: Researcher Free, 0/1000 credits used, pay-as-you-go and auto-upgrade off; requests stop at plan limit. Evidence: reports/account-status-20261023T221833Z.json. Existing default key remains in the browser; server import is pending because computer-use access to Terminal was denied. User was given a hidden-input SSH importer; no key was printed, no new key was created, and no paid setting was changed.

- T1.2 final review: reports/t1.2-acceptance.json retains accepted=false. All four real evidence bundles are present, their true peak/terminal replay matches native counters, full source hashes match, budgets pass, and OOM PNGs are visually checked. Nine of ten scenario checks pass; s2 optimizer moments are 8,593,604,608 / 21,553,250,816 bytes =39.8715009692%, below the unchanged40% gate. s4 actual Top40 train.py:107 stack is512 bytes; s5 high denotes a19.125GB cache-gap proxy, not confirmed harmful fragmentation.
- Final regression: reports/tests-20261023T025427Z-final.log, 95 passed in53.54s; exact invocation in reports/tests-latest-final.json. Ruff check and format passed; real evidence CLI smoke passed. No live API calls were made.

- T1.1: all original GPU checks passed in reports/lab-gpu-acceptance-20261023T022523Z.json; s1 CUDA OOM with2050 device0 trace events, valid pickle/native JSON, positive request and traceback; s3 twice completed20 with20 losses and exact first5 equality. 61 tests passed in53.15s including real30s timeout and child cleanup, secret isolation, AdamW step hooks, command capture and symbolizer dependency. CLI CPU smoke reached5 controlled steps.

- T0.6 s1 calibration: original width1024/depth12 baseline produced268 trace events underLab, below unchanged T1.1>1000. Width256/depth192 uses101007360 real parameters(+0.256%); batch32/seq2048/SGD and activation root cause unchanged, no filler. New source separately verified in reports/gpu-baseline-20261023T022519Z-e164c187.json; new model version is never compared to old as a repair. Old evidence retained.

- Lab corrections retained with failing evidence: Docker29 lowercase absence text initially caused false cleanup-unverified; fixed case-insensitive exact-owned-container checks. Old image lackedaddr2line; fullC++symbolization failed stoi, fixedbybinutils in image54accb9f... with fullstack capture unchanged. Initial reports/lab-gpu-acceptance-20261023T020307Z-failed.json and020718.json retained.

- 2026-10-23: Frank reports the GPU service stopped and asks to continue other work while he registers accounts. Proceed with API-independent Lab implementation; T0.1/T0.4/T0.5 remain pending, and all original acceptance criteria remain unchanged. No paid call has been authorized by this sequencing instruction.

- T0.6 accepted: `uv run python scripts/check_gpu_baselines.py` exit0, canonical run20261023T013238Z-a16fc6fb launched9 full GPU workloads. All source hashes and raw results independently checked. README allocated/reserved peaks recorded for all8; INDEX provenance updated; nanoGPT.oom.txt matches raw traceback. See reports/t0.6-acceptance.json. No later snapshot/repair criteria certified.

- 2026-10-23T01:29Z: Frank stopped the competing service. Live check: no compute processes, 24055 MiB free, baseline guard ready=true. Full GPU T0.6 calibration resumed. First s1 run reproduced typed CUDA OOM in 5.235s with verified cleanup; its startup-only peak fields are invalidated by reports/gpu-baseline-013012-peak-correction.json. OOM terminal counter instrumentation added before the canonical rerun.

- T0.6 runner preparation: scripts/check_gpu_baselines.py and docs/GPU_BASELINES.md collect full-size default GPU baselines in Docker, distinguish CUDA OOM/host OOM/error/timeout, and retain raw evidence. Actual `--check-only` returned 78 with workloads_launched=0 while the known competing process was still present (historical check). CPU-only Docker canaries: `uv run pytest -q tests/test_phase0_baseline_failures.py` passed 2/2 in 6.19s (reports/phase0-baseline-canaries.log): CPU OOM is rejected; timeout cleans up the owned container. At that preparation checkpoint the full GPU path was unexecuted; it was subsequently verified by the canonical run above.

- T0.6 historical CPU preparation checkpoint: eight source fixtures + README + INDEX prepared. `uv run python scripts/check_scenario_smoke.py` (two four-case batches) completed 20 CPU tiny steps in all 8 cases; evidence reports/scenario-cpu-smoke-summary.json and per-batch logs. This is not GPU baseline acceptance. nanoGPT pinned at 3adf61e154c3fe3fca428ad6bc3818b27a3b8291, deterministic synthetic inputs prepared, original upstream CPU tiny run exit 0 (upstream max_iters=20 emits iterations 0 through 20). At that checkpoint no full-size GPU OOM trace or peak measurement existed; the later canonical run supplies both. Live model calls and repairs remain unverified.

- T0.3: `uv run python scripts/verify_toolchain.py` exit 0: torch 2.5.1+cu124, CUDA True, NVIDIA GeForce RTX 3090 Ti; snapshot True True; .env ignored and mode 600. `uv run pre-commit run --all-files`: all three hooks Passed. `gitleaks detect` and staged scan: 0 findings. Commit ca6c86ad099c519b92d1ccb88219b08450aa8da6 author and committer both match existing Frank identity; push origin/main succeeded.

- T0.2: `python3 scripts/inspect_env.py` exit 0. All checks retain original stdout/stderr/exit code. DOCKER_GPU=ok; NET=ok; disk=5694.85 GiB. Existing other compute process is noted. sudo requires password; uv/gitleaks not initially installed.
- T0.1: public https://github.com/xiaodouzi666/headroom created with Apache-2.0; server .env initialized with empty keys, permissions 600, gitignored. PLAN SHA-256 matches attachment e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56.

- Bootstrap: SSH verified; project did not exist; git identity is already configured; gh authenticated as xiaodouzi666; repository did not exist.

## 待 Frank 决策

- 追加 v5/v6/v7 已全部完成，目标分别0/9、1/9、1/9；最后v7未过原6/9门。按照原PLAN§0.6停止新增修复和后续Phase2实测，完成报告/提交/handoff后等待Frank决定。具体两种范围见reports/final-decision-20261025-v7.md；赠送额度仍可用，但未自行扩展轮数。

- Ultra admission: the reviewed profile is now enabled in explicit actual_usage mode; an8192-output diagnosis still reserves the full1.073152USD verified provider bound in global/day pools, while the original0.35/0.60USD actual-cost acceptance thresholds remain unchanged. A settled call can cross its actual run threshold and must then fail/stop; the provider bound is not a minimum charge or a promise of per-call0.35USD worst-case cost. Current runtime all-time/day allocations and prior charges are recorded in reports/live-campaign-20261025. The optional local_estimate mode remains distinct and is not used for the active strict shared pool. No further authorization is pending for already authorized original-plan work within gifted credit; recharge/overrun and threshold changes remain unauthorized.

- T1.2: s2 optimizer-state peak fraction is39.8715%, below original40%; task remains unaccepted. Its baseline also already fits22GB, so later T2.1 two-round acceptance remains unresolved. Preserve these results for the requested later discussion; no threshold or fixture changes made to force a pass. A separate foreach=False diagnostic copy now has stable runtime hashes,49.4149464840% optimizer fraction and20 matched losses (max delta2.384185791e-7); reports/s2-optimizer-diagnostic-20261024 records it. Canonical/history unchanged; this is not acceptance or a model-generated repair.

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. The initial permission denial was not bypassed. Frank subsequently stopped it; GPU availability and all T0.6 baselines were verified on 2026-10-23 at09:29–09:34 Beijing time. Evidence: reports/gpu-release.json.

- Historical limited checkpoints remain preserved: two trial-connectivity chats and the later three-call Ultra/Super checkpoint (0.0003143USD) consumed their original scopes. Subsequent explicit authorization now covers remaining original-plan calls using existing gifted credit only, with no recharge/overrun; see reports/live-campaign-20261025/authorization.json. The >=25USD credit gate is accepted from the redeemed25USD face promo/30.25USD gross adjustment. Current spending is bounded by the shared allocation, not inferred from an account balance or card availability.

## Frank 待办

- Devpost: registration and an existing project draft were observed in the logged-in browser on 2026-10-24; final project submission remains pending.
- Token Factory: https://tokenfactory.nebius.com ; promo https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 ; activation code NEBIUS-DEVPOST-GLOBAL26 ($25); Builders Program https://dev.nebius.com/builders (additional $25). NEBIUS_API_KEY is now privately configured and authenticated. Promo credit >=$25 is now verified in reports/promo-redemption-20261024.json; remaining original-plan spending is authorized within existing gifted credit and the reviewed allocation; no recharge/overrun.
- HF_TOKEN only if later gated model access requires it.
- Domain/Cloudflare access is needed for T3.5. Video and Devpost submission remain Frank-owned per plan.

- 2026-10-24T22:00:00+00:00: frozen regression1726passed501.32s with208 tracked/nonignored non-Markdown source hashes unchanged (production prompt Markdown was excluded from this historical inventory; next final inventory will include it). v4 diagnosis then returned8 complete JSON responses withstop/0 reported reasoning and7/8 first-cause agreement at0.327699USD; full acceptance remainsfalse because policy/reference validation rejected plans and a genuine workspace/model-shrink text false positive was found. Preservedv2/v3/v4 packages; matcher and request-schema repairs are being integrated without changing original thresholds. Local preview restarted with explicit reviewed profile;health200/configuredtrue/GPUavailable, no UI run submitted.

- 2026-10-24T22:12:48.407604+00:00: T1.4 v5 completed8 single calls,7/8 first causes,8/8 valid refs,0.328770USD known; full gate stillfalse. First actualMVP campaign stopped after s1 GPU baseline and one Nano response: exactidentity200/3643input/480output but cachecountmissing means actualcostunknown. Full0.01644864USD provider bound retained; no retry/remaining8cases dispatched. Runtime known1.37040652USD, external unknown900k1.049344USD unchanged. Read-only audit retained at reports/live-campaign-20261025/mvp-v1-audit.json. Fee-bound continuation is being implemented with independent review, not bypassed.

- 2026-10-24T22:26:44.941692+00:00: reviewed historical Nano retention completed with no new requests; actual remains unknown and original0.01644864 bound remains charged. Old MVP campaign bytes unchanged. T2.7 six-arm raw GPU audit accepted, all peak differences0%, independent receipt2044c67c26f9782e16c1d360802191e742ae8d245194005c4645d464a38574e3. Final guarded full regression running on233 frozen source files including production prompts; no full-suite success claimed yet.

- 2026-10-24T22:33:53.118136+00:00: full guarded regression1977passed549.80s (driver551.38s),233 production/config/test source files unchanged during execution, including production prompt Markdown; PLAN and network/env guard unchanged. Frontend68 tests/typecheck/build passed. Reports-only style fixes preserve original runner bytes in .py.original.txt with SHA mapping; Ruff check/format and git diff check pass. Local preview restarted with current runtime profile, health200/configuredtrue/GPUavailable and billing complete conservative1.38685516USD/remaining8.61279388USD. Historical private MVP ID returned Run not found; later read-only verification at2026-10-24T23:00UTC corrected the initial Store inference: preview and evaluation share runs/headroom.db, but api_owner/public_replay access checks hide private evaluation runs. No run UI acceptance is claimed from that lookup.

- 2026-10-24T22:47:12.092271+00:00: source5d3093c was committed/pushed with matching remoteHEAD, clean tree and0 gitleaks findings before MVP v2. v2 exited1 after292.214s; s1 made22 calls,16 patch attempts all stopped before apply/compile, and no candidate GPU verification. Temporary future admission gating preserved current settlement/480s deadline and blocked next8cases before GPU/model. After evaluator exit all51 attempts were settled and original0600 profile bytes restored. Failed first repair iteration preserved; iteration2 changes only generic Super output control/response evidence and format clarity, with thresholds/fixtures unchanged. Integrated actual-source regression is now running.

- 2026-10-24T22:53:06.120807+00:00: Super protocol repair actual-source integration294passed103.11s;236 frozen source/test/prompt hashes unchanged. Earlier287pass/7fail were solely an offline fixture missing Super reasoning capability; only that fixture metadata changed, all caps/negative assertions retained. Final Ruff/format/diff checks pass. Financial capability preflightv3 passed separately; next complete9-caseMVP is repair iteration2.

- 2026-10-24T23:04:24.343073+00:00: MVPv3 repair iteration2 exited1 after321.560s. Five actual cases78calls,54Super responses stop/zero reasoning;52 nonempty decoded diffs had zero physical linefeeds and failed strict parsing; a separate empty diff was rejected as NO_CHANGE. One CLI-only s5 proposal was statically accepted but failed real candidate argument parsing;0 target successes/0 git apply+compile. Four later cases stopped before any GPU/model dispatch. All129 runtime attempts settled/35runs closed/no halt before exact enabled profile restoration. Independent fixed9 audit retained0targets and3correctfirstcauses. Final permitted iteration3 will use explicit diff_lines boundaries, preserving raw wire evidence and public unified diff validation. No thresholds/source fixtures/budget allocations changed. Private evaluation404 cause was corrected from an unproven different-Store inference to verified ownership/public-replay restrictions.

- 2026-10-24T23:12:06.856017+00:00: explicit diff_lines wire schema is applied, preserving publicPatchProposal.diff, original parser/path/policy/4000token/three-fixer gates.117 isolated draft tests passed; full production regression is running with source frozen. Generic live componentv1 returned correct line boundaries but invalid hunk prefix and failed; unchanged production componentv2 used normal bounded repair, third proposal applied/compiled and AST differed only by requested docstring. Four totalcalls known0.00126246USD; noGPU and zeroMVPcredit. Independent components review and new catalogues/price observation pass;133runtimeattempts settled/37closed/nohalt, conservative2.03806162USD/remaining7.96158742USD. Current gift-only global/day allocations and historicalunknownretentions unchanged.

- 2026-10-24T23:16:51.941872+00:00: actual production full regression2026passed551.34s (driver552.932s),236 complete source/config/test/production-prompt hashes unchanged, original PLAN and parent/spawn network/credentials/live-ledger/GPU guards unchanged. Ruffcheck/format anddiffcheck pass before launch. Source fixes include explicit line-array transport/private dual evidence and productionpatcher replay role compatibility; raw failed live results remain preserved. No additional live model orGPU is part of this suite. Formal final9caseMVP still pending; workerexit0 remains distinct from literalfixCLIexit0.

- 2026-10-24T23:35:38.369724+00:00: finalv4 driver exit1/735.240s,full9 executed. Target0/9;firstcause7true/0false/2unknown. Two applied+compiled candidates:s1OOM reverted,s8round2keep20steps/3.556%reduction/loss originalscalar-seriesidentical,targetfalse. Nine literal report-number checks passed;CLI supplemental fails formal allzero (literalunobserved).165modelcalls known1.037464332/conservative1.039832052;all298attempts settled/46runs closed. Runtime conservative3.077893672/remaining6.921755368;externalincludednet4.900136132;no recharge/allocationchange. Finaliterationlimit reached,stop additional repairs pendingFrank. Reports/README/feedback refreshed,ownedloopbackpreview3915279 loadedfrozen78source;health/Home200/no UI submission.

## MVP v5 extension implementation checkpoint — 2026-10-25

- User authorization: additional repair iteration 1/3, original PLAN/manifest and all acceptance thresholds unchanged.
- Replaced model-authored hunk coordinates with exact original-source SHA256 plus unique physical-line edits; public unified diff API remains unchanged.
- Added bounded structural failure feedback and independent exact application reconstruction before compile; model-conversion expected candidate hashes are checked again.
- Guarded focused integration: 175 passed. Guarded full regression: 2,134 passed in 551.75s; all 241 source entries and PLAN unchanged. Earlier focused run's single outdated rejection assertion is retained as failure evidence, then corrected to assert earlier rejection without any candidate copy.
- Ruff check/format and diff checks passed. Preliminary staged gitleaks: zero findings.
- Real generic anchored-edit component: accepted on one Super call, 130 output tokens, exact cost $0.00054. Raw response, source hash, generated diff, Git application, compile, exact candidate bytes and unchanged executable AST all verified. This is not a benchmark success.
- Full nine-scenario v5 campaign is the next step; no new MVP result is asserted here.

## MVP v5 completed — extension 1/3

原 MVP 未通过。九场景已完整执行，目标 0/9；首因类别匹配 7/9（2 未知），保留旧审计器 diagnosis.valid 条件后为 6 真、1 假、2 未知。未将部分显存改善、组件验证或 worker 退出 0 算作整体通过。

执行源码 d6f29945eaffe2c56a2969d85f23fdfe06f03aa7；campaign 为 runs/evaluation/live/20261025T022454741538Z-8e6e085d/campaign.json。2026-10-25 02:24:53–02:36:26 UTC，共692.93秒。原 PLAN 与九场景 manifest 未修改；额外三轮已使用一轮。

| 场景 | 首因（含有效性门） | 有静态应用候选 | 最终保留轮 | 目标 | 保守费用 USD | 秒 |
|---|---|---|---|---|---|---|
| s1_batch_too_big | 正确 | 是 | 无 | 未达标 | 0.12525164 | 114.69 |
| s2_fp32_adamw_1b | 正确 | 否 | 无 | 未达标 | 0.04753906 | 44.24 |
| s3_eval_no_grad_missing | 正确 | 是 | 无 | 未达标 | 0.09023786 | 56.42 |
| s4_loss_accumulation_graph | 正确 | 是 | 无 | 未达标 | 0.15481084 | 145.27 |
| s5_fragmentation_varlen | 未知 | 否 | 无 | 未达标 | 0.09600868 | 64.39 |
| s6_full_vocab_logits_fp32 | 未通过有效性门 | 否 | 无 | 未达标 | 0.0336181 | 19.17 |
| s7_frozen_params_optimizer_state | 正确 | 是 | 无 | 未达标 | 0.11522816 | 93.94 |
| s8_two_models_resident | 正确 | 是 | 无 | 未达标 | 0.10851474 | 80.74 |
| nanogpt | 未知 | 是 | 无 | 未达标 | 0.12575908 | 72.97 |

Audit: reports/live-campaign-20261025/mvp-v5-audit-notes.json. Preparing extension 2/3 in isolated server worktrees; original acceptance gates unchanged.

## MVP v6 implementation checkpoint — extension 2/3, 2026-10-25

- New source-span protocol binds exact original file SHA and inclusive line IDs; the host reconstructs old bytes and candidate bytes, then retains existing apply/compile/policy/GPU gates. Generic diagnosis/patch instructions now check actual producer/consumer, train/eval paths, nonempty sample ranges, loss weighting and optimizer update cadence. No original scenario, manifest, policy, numerical threshold or PLAN change.
- Evaluation now executes the installed headroom fix console script with one supervised PID and run UUID. Actual OS exit, CLI receipt, raw result and parsed-request hashes are recorded; legacy worker exit 0 is not retroactive CLI evidence.
- Guarded focused integration: 445 passed. Full regression: 2192 passed in 581.13s (driver 582.74s), all 245 source entries and original PLAN/guard unchanged. Initial fixture-guard failures are retained; no live API/GPU was part of the full suite.
- Initial source-span component used two Super calls, actual $0.0013896. Exact source/application/compile evidence passed, but the docstring-only AST check failed because the model duplicated an unreachable return statement. This remains failed; it does not prove changed mathematical behavior. No benchmark success is claimed.
- Preparing a separate bounded component follow-up with at most two more calls and $0.10 total across both attempts, keeping the original shared credit allocation and all historical costs. The v6 nine-case campaign has not started.

- V6 source-span component follow-up accepted on one call with unchanged executable AST and exact source/application/compile evidence. Both components together: 3 calls, exact $0.0020301; failed V1 preserved. Full-suite 245-file source inventory remains exact. Shared runtime conservative charge 3.977431932 USD; unchanged all-time pool remaining 6.022217108 USD. Original nine-case v6 campaign is now ready; no target success is asserted by this component.

## MVP v6 completed — extension 2/3

固定9已全部实测：目标1/9（s3），首因原始7/9、有效性门后6真1假2未知；真实CLI9条完整链，1次0/8次78。32calls保守0.535349488USD；累计runtime保守4.512781420，余额5.486867620，无未结算/未关闭/halt。原PLAN/manifest/阈值不变。s3完成20步、显存下降73.378694%、loss完全一致、干净重应用字节一致；仍不满足整体MVP门。继续已授权最后v7通用上下文交付修复。详见reports/phase-1-summary-20261025-mvp-v6.md。

## MVP v7 integration checkpoint — extension 3/3

- 最后一轮通用上下文修复已整合：实际 CLI 与保留源码身份、失败补丁与结构错误、详细验证反馈送达两模型，组合上下文限制 64 KiB；仅提示词脱敏，真实执行参数和原门槛未变。
- 独立代码审阅通过；完整 guarded 回归运行在 247 个冻结源码条目上，尚不宣称通过。原 PLAN、manifest、协议核心及预算配置均未改。
- v6 source-span 侧审计 v2 修正“被静态拒绝的 candidate_dir 等于已 GPU 验证”误判；34 项审计器测试通过。新版 v6 覆盖无缺失，但两条响应解析仍未知，整体 sidecar 未通过。旧报告完整保留。

- V7 final full guarded regression: 2218 passed in 560.90s, no skipped tests; 247 source entries unchanged before/after/current, original PLAN and guard unchanged. Root and independent launcher/source review passed; final live campaign pending.

## MVP v7 completed — final extension 3/3


**整体 MVP 未通过。** 固定九场景真实目标 1/9，低于原 6/9；首因类别原始匹配 6/9，加入 diagnosis.valid 后为 4 真、3 假、2 未知。真实 CLI 九条执行链全部核实，但只有 s8 退出 0，其余八项退出 78。未把部分显存改善或传输协议通过算作整体通过。

本次追加授权 v5/v6/v7 共三轮已全部完成。原 PLAN §0.6 的停止边界现已触发：完成审计、报告、提交和交接后等待 Frank 决定，不自动开始 v8 或后续 Phase 2 实测。所有阈值、原场景、策略、旧 runs 和原预算池保持不变。

执行源码 cb9da81405d5c4f77a5d6d9c1f7a1ee07ad27f32；campaign 为 runs/evaluation/live/20261025T033333928331Z-1b228422/campaign.json，SHA256 cb78766a21e16ba2244b371ca460ec394cd8ad85e6015548fe036f0a82b97cdb。北京时间 2026-10-25 11:33:33–11:39:10，336.93 秒；九场景完整、无质量提前终止、无预算 halt。


V7 25calls保守0.455618016USD；runtime457attempts/76runs全settled/closed，余额5.031249604，无halt。完整回归2218passed。后续决策与交接见reports/final-decision-20261025-v7.md及reports/handoff-phase-1.md。

----- END PROGRESS.md -----


----- BEGIN reports/remaining-acceptance-20261025-v7.md -----

# Headroom：v7 结果前的剩余验收与决策范围

本报告仅整理不依赖 v7 具体得分的后续验收、外部输入和原计划冲突。编写时 v7 完整回归及真实评测仍待最终结果；本文不报告 v7 成功率、费用、测试通过数或已关闭子门。最终结论以本轮正式审计及最终更新后的 `reports/phase-1-summary.md` 为准。旧报告、旧运行及原 `docs/PLAN.md` 保留。

**实现完成不等于验收完成。** 已有客户端、搜索、预算、研究、API、界面、回放及部署组件，不自动证明相应真实入口、目标修复、数值、性能、费用、公开可用性或提交状态通过。后续应先复核最终 v7 已有产物，满足同一原门的证据可以直接复用；只有确实缺少的验收才列为新增执行，不为阶段切换重复付费或重跑 GPU。

## 1. Phase 门与本轮结束边界

- `docs/PLAN.md:41`：T1.12 达到 MVP 通过线，才直接继续 Phase 2 P0；未达标最多修 3 轮，仍不达标则停下等 Frank。原固定九场景、目标至少 6/9、首因至少 6/9、九条 CLI 退出 0、单 run 费用及时间限制仍按 `PLAN:284–291` 判断，不以组件成功或个别成功替代整体门。
- Frank 后续追加的是最多 3 轮 MVP 修复，范围为 v5/v6/v7（授权记录 `PROGRESS.md:58`）。若最终 v7 仍未通过，先完成现有结果审计、报告、提交与 handoff，再等待 Frank 决定；不自行启动 v8、更多修复试错，或以 Phase 2 名义继续模型/GPU 评测。已有赠送额度调用授权不等于无限追加修复轮数。
- 不把旧文档中的一般“继续原计划”解释为取消这次明确轮数上限。若 v7 通过，应按最终摘要逐项确认可复用证据及剩余原门，再依 `PLAN:41–43` 推进；下述原计划冲突不能被默认为已解决。
- Phase 2 验收结束后按 `PLAN:42` 继续不依赖 Frank 的产品工作；公网部署需要域名及 Cloudflare 权限。主评测完成后才做 `v0.9-eval` 冻结；发布及提交前再做最终固定版本检查。本文不创建 evaluation/release 标签，不部署、不提交。

## 2. 后续验收清单：以最终结果核对是否已有证据

| 范围 | 必须具备的原验收证据 | 不能替代它的现有实现或组件证据 |
|---|---|---|
| T2.1 搜索/Pareto | 逐轮 keep/revert、真实数值/吞吐约束、各档独立 patch、总轮数不超过 6；s2 专门条件另见下节冲突（PLAN:295–297） | 搜索代码、离线 Pareto 测试或任意两轮探索不等于原 s2 条件成立 |
| T2.2 Research | s1 的 checkpoint 文档 Source、s5 的 CUDA 内存管理 Source、research 表记录、重复 query 缓存 credits_used=0（PLAN:299–301） | Tavily 连通性、任意 search/extract、其他场景 Sources 不自动关闭指定场景门 |
| T2.3 Nano | 八场景 Top-40 栈逐条标注、每 run 标注费用≤$0.02、与启发式一致率≥80%（PLAN:303–304） | 模型响应成功、部分标注或跳过失败样本不等于全覆盖/一致率验收 |
| T2.4 预算 | 0.05 run 预算优雅停止及部分报告/budget.exceeded；0.1 日预算新 run 拒绝；完整多轮 run≤$1.2（PLAN:306–307） | 现有账务结算、组件测试不自动证明所有规定入口；不得清账、释放未知费用或改权威池来凑用例 |
| T2.5 HF / T2.6 Watch | HF 目标达成、配置 diff≤15行及根因报告；Watch 自身包装入口在 OOM 后触发完整流程、非 OOM 退出码透传（PLAN:309–314） | HF 基线、手工修复、普通 eval 入口不等于 HF 模型修复或 Watch 入口验收 |
| T2.8 小评测 | 原 10 场景×2 策略、最多 3 轮优化、目标/首因各≥75%的原目标与总费用≤$12、phase-2 summary（PLAN:318–320） | 当前 default/strict 等价必须明确记录；不能把 allow_precision 当作原 default，不能把旧未知结果变成命中 |
| T3.2 真实界面流程 | 浏览器发起 run，实时事件到最终报告、Lighthouse≥70、手机宽度无横向溢出（PLAN:328–330） | baseline 页面、回放旧事件、前端单元测试不等于真实提交链；已有效的性能/布局证据可复用 |
| T3.3 / T3.6 回放与素材 | ≥5条符合规定内容的修复回放（含 s2 两轮、nanoGPT、reclaim）、2秒内开始；≥8张真实界面素材（PLAN:332–342） | 五条基线回放及基线截图不能充当规定修复集合；从已有合格修复策展不需要重跑模型/GPU |
| T4 主评测/消融 | 完整主表及汇总；八合成场景×完整证据Ultra、无快照Ultra、完整证据Super三条件，固定可比协议与3–5句实测结论；之后冻结（PLAN:344–348） | 不同 source/prompt/schema/policy/search mode 的旧行不能随意拼成配对消融；不把预期优势写成实测结果 |
| T5 交付验收 | 干净 clone 按 README 跑通真实 fix；主表/消融/五段反馈及3–5条建议、最终审阅；评委视角自检及发布前复跑/冒烟（PLAN:350–357） | 本地草稿、CPU干净目录运行、历史回归通过不等于最终交付通过 |

已验收的能力探测、基线、隔离对照等，在来源及执行条件仍匹配时应复用，不仅因 v7 结束而重测。最终 v7 子门逐项审计可能关闭上表部分内容；本文不预先判定关闭或失败。

## 3. 需要 Frank 逐项决定的原计划冲突

1. **s2 归因比例与两轮 fit22 条件。** 原 optimizer_state≥40% 门仍保留实测 39.8715009692%，不得靠四舍五入或改类别算通过；canonical s2 已低于22GB。固定 optimizer state 为8,593,604,608字节时，满足40%意味着总峰值≤21.48401152GB，本来已在22GB内。因此“修至少两轮才达到fit22”不能由继续探索或另一个 reclaim 成功来冒充。见 `PLAN:247、297` 及 `reports/final-decision-20261025.md:33–34`。
2. **默认精度政策与两策略标签。** 原计划既要求禁止数值改变为硬约束，又要求默认报告出现 bf16 档；当前 default/strict 均禁止数值改变。未经逐项批准，不开启精度变化、不把 allow_precision 重命名为 default、不调整原比较分母或保留被支配点凑 Pareto。见 `PLAN:145、296–297、319` 及 `reports/final-decision-20261025.md:35`。
3. **真值与数值口径。** reserved-minus-allocated 差值不是碎片根因证明；没有可靠真值仍为 unknown。不同 batch 的原标量序列比较不能扩写成已证明相同输入/effective batch/objective。原 gate 与现有失败历史都保留；若讨论版本化验收修订，必须单独记录批准、来源、比较边界及新旧结果，不静默替换 canonical。

这些问题不预设以降低门槛解决。Frank 可以保留原要求并接受其仍未通过的状态，也可以逐项审阅另立版本化协议；讨论本身不等于批准变更。

## 4. 外部输入、公开交付与未来日期

- **设计认可（T3.4）：** Frank/Claude 的 `design/` 稿及 Home/Run 还原认可；现有 theme 或功能测试不代替认可（PLAN:335–336）。
- **公网及真实通知（T3.5）：** 批准的域名、Cloudflare 接入权限和明确告警收件渠道。需实际验证 HTTPS 手机网络、真实IP限流、重启10秒恢复、停服务2分钟收到告警；模板和离线通知器测试不等于已投递（PLAN:338–339；docs/DEPLOYMENT.md:30–48）。
- **视频与 Devpost（T5.3–5.7）：** 文案、脚本和真实素材可整理；原计划由 Frank 录制/上传视频及提交。视频≤2:55、1080p、YouTube Public；表单草稿保存、赛道/链接/feedback、Submitted 状态和最终个人声明需分别核验。`docs/DEVPOST.md` 是本地草稿，不能当成已保存或已提交（PLAN:353–357；docs/DEVPOST.md:33–40；docs/VIDEO_SCRIPT.md:15）。
- **未来保活（Phase 6）：** 每周 health/告警、11月25日前确认Token Factory≥$10及Tavily credits、12月1日/8日人工访问记录。未来日期尚未发生，不能预先标为已验收（PLAN:359–360）。

## 5. 最终结果出来后，可交 Frank 选择的两种具体范围

以下仅为待选择范围，**没有在本报告中获得新增执行授权**。若 v7 通过，先按其最终摘要与原 Phase 门处理；若 v7 仍失败，可选择：

- **范围 A：保持原门槛，再授权最多 3 轮有限 MVP 修复。** 仅修通用诊断上下文、补丁生成/应用与反馈链，再按原固定九场景验收；保持场景源码、数值/参数量/吞吐、成本/时长和成功率门。仅用现有赠送额度及已授权共享总/日池，不充值、不扩池、不过额；额度不足即停。保存全部失败及费用，每轮给出明确结果。三轮仍未通过即停下，不自动延长或转入后续主评测。已知原计划冲突仍如实保留未通过，不靠本范围改门槛。
- **范围 B：先逐项决定已知验收冲突，暂停新增 MVP 试错。** 先审阅 s2 的40%/两轮fit22条件及默认精度/Pareto/两策略含义，逐项选择保留原要求或另立版本化协议，并明确新旧证据如何比较。只完成证据梳理、可审阅提案和交付清单，不运行新的模型/GPU评测；待 Frank 明确逐项决定及后续有限执行范围后再继续。不预设任何阈值下降，不把协议修订追溯套用到旧失败运行。

无论选哪种范围，主表、README、RESULTS、Devpost和最终handoff都应引用实际最终结果；历史v1–v7记录保留，当前摘要与历史章节明确区分。已有账号/密钥/赠送额度授权不是此次阶段停止的原因。

## 记录范围

本次只新增这份报告；未修改生产代码、原计划、主文档或旧报告，未调用API，未执行GPU或模型任务，未写真实数据库。本文为计划与验收边界清单，不是重新审计v6/v7结果或宣告完整goal完成。

----- END reports/remaining-acceptance-20261025-v7.md -----
