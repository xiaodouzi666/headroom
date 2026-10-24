# Headroom 最终原计划 MVP 交接报告

生成时间：2026-10-24T23:40:32.818654+00:00

**还没有完成整个开发/验收 goal。** 最后第3次MVP修复已完整执行九个场景：目标0/9，诊断首因7/9；原MVP至少需要6/9目标。一个候选完成20步且保留，但仅降峰3.56%，不足20%。2026项后端测试通过，不能替代真实修复成绩。

本轮模型费保守上界1.039832052USD（税前，actual总额仍unknown）；未充值。现有赠送额度授权继续有效；按内部保守账本runtime池仍有6.921755368USD。本次停止来自原PLAN第41行“最多再修3轮，仍不达标则停下等Frank”，不是账号或额度阻塞。

供决定的具体建议：允许最多再做3轮MVP修复，仍保持原9场景、成功/费用/数值阈值、赠送额度总/日上限和不充值。优先改进：具体格式错误反馈、独立原文与准确编辑锚点、实际应用位置核对。**此扩展尚未获得决定，未开始第4轮。** 原计划其他冲突继续保留，不随此建议自动修改。

评测代码版本：78a83df86b181674c37509b192517a9d4101ad92。所有项目代码、依赖、运行与媒体保存在azuki，本机仅保留这份纯文本。当前文档/审计将随交付提交；提交后的确切Git状态由交付回执记录。原PLAN SHA256：e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56。

[GitHub项目](https://github.com/xiaodouzi666/headroom) · [原计划§0.6](https://github.com/xiaodouzi666/headroom/blob/main/docs/PLAN.md#06-停止--继续规则)

## 输入快照与边界

本文合并最新Phase1汇总、RESULTS、PROGRESS，并附具体决策清单及后续方案。仅在PROGRESS快照中移除历史公开promo链接/代码以免混淆注册待办；原始文件不改。没有访问或包含API key、原始私有模型响应、图片/二进制。

- reports/phase-1-summary.md — SHA256 ad51ab875ecb830cb1d1003ab059ed88daf869658bcd3d730fcba1a646e65cee
- docs/RESULTS.md — SHA256 907a746ed96e7c3750fde09fbdc36d9f70123b2c407c6a45b82b22386ac2abac
- PROGRESS.md — SHA256 d231e55de1a683615e31e540fae51f42614eba747c593f7d07cd1ac40f56f758
- reports/final-decision-20261025.md — SHA256 6642f306e0762bab7f2b1c255552912b4a63b8f123ed5c51017f61e1d21bf115
- reports/live-campaign-20261025/mvp-v4-next-repair-options.md — SHA256 fcb01d43a3b071d74474d2c8a9fd78f5d851c56fd33c4c229d182b85d05fa547


---

# 快照：reports/phase-1-summary.md

# Headroom Phase 1 — 最后一次原计划 MVP 修复验收（v4）

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


---

# 快照：docs/RESULTS.md

# Results

Measured GPU baselines now cover twelve workloads. The complete 2026-10-24
manifest run reproduced five CUDA OOMs and completed twenty steps in seven workloads.
All captures and cleanup checks passed. This is baseline acceptance, not automated
repair or model-quality evidence.

No model-generated repair has yet passed the original acceptance gates, and
there is no accepted main repair benchmark or ablation score. Authenticated
capability probing and the real long-evidence client gate are now complete.
Diagnosis v5 has partial measured success; MVP v1 stopped safely after its first
Nano call. **MVP v2 and v3 finished without an accepted repair; their failures and
operational skips are preserved below. The final permitted MVP v4 iteration finished: 0/9 targets, 7/9 first causes. All three original repair iterations are exhausted; further repair work awaits the owner's decision under PLAN section0.6.**
Tavily API/cache component evidence and the independent T2.7 GPU execution-path
comparison have passed. These facts do not substitute for a successful repair.

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
- No authenticated model-generated GPU repair has been demonstrated.
  CPU numerical-pairing checks and offline Pareto/search/report tests exist,
  but do not establish real repaired-GPU memory savings or end-to-end acceptance.
- Capability and long-evidence client gates are accepted as recorded above.
  The reviewed runtime and gifted-credit authorization are available; actual
  repair, main evaluation and ablation acceptance are still pending. No recharge
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
| Full evidence + Ultra | Diagnosis-only v5 and failed MVP v1/v2/v3 recorded here; final v4 target0/9 and first-cause7/9; no accepted repair main table | No repair success or ablation advantage claimed |
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
pending. Final v4 failed with target0/9; its evidence is appended below.

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


---

# 快照：PROGRESS.md

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
| T1.5 | Patch（Super）与应用（P0，~2.5h） | 真实场景2/8应用编译；原≥6/8未通过 | v4 candidate review:110 attempts=88format/safety+19applyfail+1response rejected+2applied;all rounds<=3fixers/Super<=4000;2026 full tests retained |
| T1.6 | Verify 与比较（P0，~2h） | 真实候选已验证；原s1/s3修复门未通过 | v4 s1 candidateOOM0steps/24.750424064GB;s3 no candidate;s8 separate20steps/loss scalar-seriesidentical/3.556%reduction<20% |
| T1.7 | 单轮编排 + 存储 + 事件（P0，~2h） | 真实核心事件及费用链通过；字面CLI门未通过 | v4 s1 events49/calls28/required order;9workerexit0!=9fixCLI0;derived CLI codes0,78,0,0,78,78,78,78,78;literalunobserved |
| T1.8 | 报告（P0，~1.5h） | 九报告数字检查通过；选中patch另验 | mvp-v4-report-number-checks.json9/9;all>=7H2;s8selectedround2 partial improvement;selectedpatchcheck separate,not targetsuccess |
| T1.9 | 真实仓库：nanoGPT（P0，~2h） | 真实nanoGPT已执行；修复门未通过 | v4 needs_human/no candidate,targetfalse,lossunknown,costupper0.09073224<=0.6 and0.8;22GB/diff/literalCLIunmet |
| T1.10 | Honesty 与安全（P0，~1h） | 静态与CPU真实性检查通过；完整修复待办 | docs/PATCH.md; model shrink/truncation/escape checks and observed parameter counts |
| T1.11 | Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h） | 自有Python镜像、干净目录CPU及隔离组件通过 | docs/LAB_RUNTIME.md; hash-locked image-owned Python3.12, verified immutable image ID, no host venv mount; clean candidate tree script/module each3updates with capture/cleanup verified |
| T1.12 | MVP 整体验收 + 报告（P0，~1.5h，10/24 晚） | v1及三次修复v2/v3/v4均未通过；按§0.6待Frank决定 | v4 all9live/165calls,target0/9,firstcause7/9+2unknown;costupper1.039832052;9reports/cost/wall/cleanup pass;literalCLI gatefalse;final phase1summary saved |
| T2.1 | 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h） | 有界搜索与逐轮验证反馈完成；真实验收待办 | docs/SEARCH.md; selected state survives revert; per-round verification-feedback.json exposes actual loss/check/error facts to later rounds; original s2/bf16 policy gates unchanged |
| T2.2 | Tavily Research（P0，~2h） | 真实模型研究与缓存已测；指定Sources门未通过 | v4 research9rows/8API/7credits;s4PyTorch2.5checkpoint extract;s3->s5cache0API0credits;s1checkpoint/s5CUDA memorySources absent |
| T2.3 | Nano 栈标注（P1，~1h） | 真实8场景已测；覆盖和一致率未通过 | v4 4/8complete;completed outputs3/40heuristic matches;failed4not excluded;all<=0.02certified upper |
| T2.4 | 预算守卫与成本面板（P0，~45min） | 真实费用链复核通过；原额外预算门待办 | v4 final298attempts settled/46runs closed/0pending unresolved halt;runtimeknown3.056058592/conservative3.077893672/remaining6.921755368;original.05/.1 cases not executed |
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
| T5.2 | docs 定稿 | 真实失败/服务体验及阶段报告已更新；最终审阅待办 | Finalv4RESULTS/FEEDBACK/phase1summary/cost/CLI/candidate audits;full project acceptance and release review remain open |
| T5.3 | Devpost 描述 | Devpost本地草稿完成；未保存表单 | docs/DEVPOST.md; owner final review/submission pending |
| T5.4 | 视频 | 视频脚本完成；待真实修复与录制 | docs/VIDEO_SCRIPT.md; <=2:50 storyboard, actual evidence required |
| T5.5 | 首次完整提交 | 未开始 | — |
| T5.6 | 评委视角自检 | 当前就绪审阅完成；发布前复检待办 | reports/submission-readiness-20261024.md; actual repair, public demo/video and submission gate remain pending |
| T5.7 | 最终提交 | 未开始 | — |
| Phase 6 | Weekly health/alerts; balance by Nov 25; manual Dec 1 and Dec 8 access | 未开始 | Future dated acceptance |

## Next acceptance and remaining deliverables

- FINAL v4 (2026-10-24T23:31:55Z): all9 genuinely executed;0/9targets,7/9firstcauses. Original three repair iterations exhausted. Finish reports/commit/handoff, then stop additional repair work for Frank under PLAN§0.6; no new budget approval is needed for the existing gift-only authorization.

- The dedicated T1.3/T1.4 drivers and native model tool loop are implemented and have now been exercised live. Accepted client capability, partial diagnosis/research evidence and failed repair outcomes remain separately recorded below.
- The owner authorizes remaining original-plan model work using existing gifted credit only, with no recharge/overrun. reports/live-campaign-20261025 records authorization, allocation and the enabled actual_usage profile with verified provider global/day reservations. All60 original T0.4 samples are finalized with failures retained; Ultra900k429 permanently occupies1.049344USD under the completed conservative continuation review. Runtime all-time/current UTC2026-10-24 daily ceiling is9.99964904USD, including spent usage; combined external probe plus maximum runtime day total11.82189150USD remains below12. No unknown charge is treated as zero. T1.3 is accepted; latest T1.4 v5 is7/8 exact first causes with8/8 valid references but incomplete policy/readiness. Its0.328770USD calls are known; subsequent MVP Nano missing-cache usage retained0.01644864USD and halted the runtime. Earlier v2/v3/v4 failures remain preserved.
- Keep original failed gates and procedure conflicts visible: s2's 39.8715% optimizer fraction versus40%, default precision policy/bf16 tier. T2.7 isolation comparison is now accepted with its Docker-contained reference boundary.
- T1.12 has now executed allnine live cases in v4. Target0/9 fails; cause7/9 and original cost/time bounds pass. No failed model run is replaced by an offline success.
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

- 最后原计划MVP修复v4已完成但target0/9。PLAN§0.6第41行明确最多再修3轮仍失败须停下等Frank；v2/v3/v4已用完。具体方案在reports/live-campaign-20261025/mvp-v4-next-repair-options.md。待决定是否允许额外有界修复轮数，保持原阈值、策略和gift-only/no-recharge/no-overrun；本次没有自行开始第4轮。

- Ultra admission: the reviewed profile is now enabled in explicit actual_usage mode; an8192-output diagnosis still reserves the full1.073152USD verified provider bound in global/day pools, while the original0.35/0.60USD actual-cost acceptance thresholds remain unchanged. A settled call can cross its actual run threshold and must then fail/stop; the provider bound is not a minimum charge or a promise of per-call0.35USD worst-case cost. Current runtime all-time/day allocations and prior charges are recorded in reports/live-campaign-20261025. The optional local_estimate mode remains distinct and is not used for the active strict shared pool. No further authorization is pending for already authorized original-plan work within gifted credit; recharge/overrun and threshold changes remain unauthorized.

- T1.2: s2 optimizer-state peak fraction is39.8715%, below original40%; task remains unaccepted. Its baseline also already fits22GB, so later T2.1 two-round acceptance remains unresolved. Preserve these results for the requested later discussion; no threshold or fixture changes made to force a pass. A separate foreach=False diagnostic copy now has stable runtime hashes,49.4149464840% optimizer fraction and20 matched losses (max delta2.384185791e-7); reports/s2-optimizer-diagnostic-20261024 records it. Canonical/history unchanged; this is not acceptance or a model-generated repair.

- 2026-10-23: Frank requests retaining the original plan; discuss audit proposals individually later. No acceptance threshold or scope change is approved.

- 2026-10-23: Frank explicitly authorized stopping the current llama-server (PID 398152). Fresh identity check found owner chenchunlai; normal SIGTERM failed with PermissionError. The initial permission denial was not bypassed. Frank subsequently stopped it; GPU availability and all T0.6 baselines were verified on 2026-10-23 at09:29–09:34 Beijing time. Evidence: reports/gpu-release.json.

- Historical limited checkpoints remain preserved: two trial-connectivity chats and the later three-call Ultra/Super checkpoint (0.0003143USD) consumed their original scopes. Subsequent explicit authorization now covers remaining original-plan calls using existing gifted credit only, with no recharge/overrun; see reports/live-campaign-20261025/authorization.json. The >=25USD credit gate is accepted from the redeemed25USD face promo/30.25USD gross adjustment. Current spending is bounded by the shared allocation, not inferred from an account balance or card availability.

## Frank 待办

- Devpost: registration and an existing project draft were observed in the logged-in browser on 2026-10-24; final project submission remains pending.
- Token Factory: https://tokenfactory.nebius.com ; promo [historical public promo link omitted] ; activation code [historical public promo code omitted] ($25); Builders Program https://dev.nebius.com/builders (additional $25). NEBIUS_API_KEY is now privately configured and authenticated. Promo credit >=$25 is now verified in reports/promo-redemption-20261024.json; remaining original-plan spending is authorized within existing gifted credit and the reviewed allocation; no recharge/overrun.
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


---

# 快照：reports/final-decision-20261025.md

# 最终决策与未完成门（2026-10-25）

**当前结论：开发已推进到真实修复验收；完整原计划尚未通过。v4已完成：target0/9、首因7/9，原第3次修复仍失败，必须等待Frank决定是否扩展轮数。**

读取基点：`78a83df86b181674c37509b192517a9d4101ad92`。本文件只整理既有记录，不改源代码、计划、策略、阈值、预算或账本；未调用模型/GPU/API。

## v4 结束后的决定

| 原 MVP 门（PLAN 284–291 行） | v4 审核结果（最终审计） |
|---|---|
| 9 个固定场景均退出码0并生成报告；worker与字面fix入口证据分开 | 9份报告/9worker0；字面fix未观察，推导6项78，原CLI门未通过 |
| target_met ≥6/9；诊断首因符合原真值 ≥6/9，unknown 不算命中 | target0/9失败；首因7/9，2unknown |
| 每 run 费用 ≤$0.6、墙钟 ≤480 秒；未知实际费用与保守上界分别陈述 | 9项费用/时长界通过；本轮保守1.039832052USD、actual总null |
| 测试、Ruff、泄密检查及 Phase 1 汇总 | 2026完整测试通过；最终提交前Ruff/泄密扫描及handoff收尾见交付记录 |
| 最终 MVP 结论与原始 campaign/audit 路径 | MVP失败；mvp-v4-audit-v2.json / mvp-v4-cli-exit-semantics.json |

- **若仍未通过：停止继续修复试错和下一轮 MVP，按原 §0.6 第41行交 Frank 决定；不能自行开始第4次修复或下调门槛。**
- 若 MVP 达标，可按已授权原计划继续；但下表的专项失败、入口和交付门不会因此自动变为通过。
- 字面 `headroom fix` CLI 的退出码/事件链尚未观察（T1.7，PLAN 267行；T5.1，351行）；eval worker 退出0不是该CLI的退出0，`needs_human` 在真实CLI映射78（`headroom/cli.py:243`）。

## 已有什么证据

| 状态 | 已确认的范围 | 不能顺带宣称的结论 |
|---|---|---|
| 已开发并回归 | 证据→Ultra→研究/标注→Super补丁→Lab验证→keep/revert、费用守卫、报告/API/UI/回放工具；当前完整回归 **2026 passed**、236项源哈希不变 | 不等于9场景真实修复通过 |
| 已真实验收 | 账号/赠送额度/密钥、环境、模型探测T0.4、Tavily、基线、Lab、T1.3客户端；Ultra已验证500029输入，900k失败保留 | 不声称完整1M请求已成功 |
| 已真实验收 | T2.7三场景、六个GPU对照臂，独立子进程与Docker路径峰值差均0% | 原宿主unshare/bwrap EPERM不是当前待解除阻碍；保留容器外层隔离范围说明 |
| 已测部分产品门 | 当前Home一次Lighthouse **99**，390px宽无横向溢出；前端68测试/typecheck/build通过 | 不是浏览器发起真实修复或Run全流程验收 |
| 仅组件实测 | 通用Super补丁经正常修复后apply/compile通过；真实诊断首因7/8、全部引用有效 | 通用例不计MVP成功；T1.4完整计划/政策验收仍未通过 |

## 必须保留的原失败与计划冲突

- **T1.2未过：** optimizer_state = 8,593,604,608 / 21,553,250,816 = **39.8715009692% <40%**（PLAN 247行）。两份fp32 AdamW moments已完整计入；没有证据支持为达标把临时张量改归优化器状态。
- **T2.1场景冲突：** canonical s2基线已经fit22GB。继续两轮探索或MVP reclaim成功，都不能冒充“至少两轮才达到fit22GB”（PLAN 297行）。固定状态字节要满足40%，峰值须≤21.48401152GB，本来就小于22GB。
- **T2.1/2.8策略冲突：** 当前默认禁止数值改变，却要求默认报告含更省显存的bf16档；default与strict有效策略相同（PLAN 145、297、319行；CLI默认见119行）。不能静默开精度、改场景或替换比较标签；如需修订，应由Frank逐项决定并保留旧结果。
- s5的reserved差值不能证明真实碎片根因；真值unknown继续保留，不更换分母来提高首因命中率。

## v4 后仍须逐项核验的真实门

| 项目 | 原要求与当前缺口 |
|---|---|
| T1.5–1.11 | 从v4实际记录审：8合成中≥6/8场景apply+compile成功；s1完成/原数值门、s3降峰≥30%（MVP reclaim20%不能替代）；nanoGPT fit22/≤60行/费用≤$0.8；真实CLI、报告数字、独立patch与参数量事实。PLAN 259–282行 |
| T2.1–2.6 | 真实keep/revert/Pareto；s1/s5研究来源与缓存；8场景Nano标注≥80%且≤$0.02/run；.05/.1预算门与完整多轮≤$1.2；HF≤15行配置修复；Watch真实入口。组件/手工GPU回归不代替模型修复成绩。PLAN 295–314行 |
| T2.8、T4 | 原10场景×2策略与12场景主表、8场景×3条件消融尚缺真实完整结果；原target/首因各≥75%的目标、≤3轮调整、费用≤$12及统计口径不改。旧不同prompt/策略结果不能随意拼成可比消融。PLAN 319–320、345–348行 |
| T3.2、T3.3、T3.6 | 真实浏览器提交→实时事件→最终报告；≥5条规定修复回放（含s2两轮/nanoGPT/reclaim）、≤2秒启动；≥8张真实修复素材。现有五条baseline回放/截图不能充数。PLAN 330、333、342行 |
| T5 | 干净clone按≤5命令跑通真实fix；最终主表/消融/五段反馈及3–5建议、审阅、v0.9-eval/v1.0和发布前检查仍须完成。PLAN 348、351–357行 |

## Frank 的外部材料/交付范围（不是账号额度阻碍）

- **设计：** `design/`稿及Home/Run还原度认可（T3.4，PLAN 335–336行）。
- **公网与通知：** 域名/Cloudflare接入和明确告警收件渠道；HTTPS手机网络、重启10秒恢复、停2分钟真实收件尚未验收，离线通知器通过不等于已投递（T3.5，338–339行）。
- **视频/Devpost：** 原计划由Frank录制/提交；≤2:55、1080p、YouTube Public视频、保存真实项目草稿、Submitted/赛道/链接/feedback及最终声明仍未完成（T5.3–5.7，353–357行）。开发者可先整理真实素材和文案。
- Nebius注册、key与赠送额度已完成；赠送额度内继续原计划已有授权。仍不充值、不超共享总/日池；本清单没有读取实时余额或宣称当前剩余金额。

## 未来日期，不能今天填“已验收”

- 原PLAN列最终截止为2026-10-30 10:00 PT（北京10月31日01:00）；首次提交/最终保存分别列于10月28日、10月30日任务（PLAN 5、355–357行）。
- Phase6：每周health/告警，11月25日前核对≥$10余额与Tavily credits，12月1日和8日人工访问记录；评审期12月1–15日保持可用（PLAN 359–360、374行）。

## 最少证据索引

- 原门与当前状态：[PLAN](../docs/PLAN.md)、[PROGRESS](../PROGRESS.md)、[剩余验收详表](remaining-acceptance-20261025.md)；原PLAN SHA仍为`e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56`。
- [s2比例原字节审计](t1.2-optimizer-fraction-audit-20261025.json)、[T2.7真实验收](t2.7-acceptance-20261025.json)、[Home性能证据](home-performance-20261025/receipt.json)。
- [当前完整回归](patch-wire-integration-20261025/full-regression-20261024T230712Z-cc548dc9-receipt.json)、[诊断v5独立审查](live-campaign-20261025/diagnosis-attempt4-review.json)、[v4启动预检（不是结果）](live-campaign-20261025/mvp-v4-preflight.json)。

本页已填最终v4结论。具体逐场景表、费用和Top3失败见phase-1-summary.md；未完成项不作成功承诺。


---

# 快照：reports/live-campaign-20261025/mvp-v4-next-repair-options.md

# MVP v4 后续修复选项（只读提案，等待 Frank 决定）

记录时间：2026-10-24T23:30:48.985738+00:00。检查基点为 source 78a83df，campaign 20261024T231940915002Z-2098d11d。只分析已结束的 s1–s4；v4 **仍在执行**，不预判整战役结果。原 PLAN §0.6（40–43行）允许的三轮修复额度已经用到最后一轮：若本轮仍不达标须停止等 Frank，本文不授权第4轮、实施改动或新调用。

## 先区分事实与推论

- 已查看的响应有真实行数组，故本次问题不再是v3的“整份diff没有换行”。合法JSON/逐行运输不等于合法unified diff。
- s1第三轮有真实apply+compile成功，但候选仍OOM、0步；s2–s4已有终态均target=false。这里不把静态成功、模型意图、次数或HTTP200推为修复效果。
- 以下机制来自原wire/normalized diff、固定baseline、实际candidate和保存的Git/Lab结果。仅用本地parser在内存重读选中字符串以取得原始错误，未重跑Git、编译、用户代码、模型或GPU。

## 1. 优先保留可行动的格式诊断，而不是只回传“invalid unified diff”

**已证实：** E1的第6个wire元素为无diff前缀的「import argparse」；原parser明确报「Hunk diff line expected: import argparse」。E2头为「@@ -100,7 +100,6 @@」，下方6条context+1条remove+1条add意味着旧侧7、新侧7，声明的新侧6不符，报「Hunk is longer than expected」。E3更隐蔽：两个拟修改行都以空格开头，parser统计added=0/removed=0，Git报「corrupt patch at line 11」；不能自动把空格猜成“+”。
当前 headroom/patch.py:170–173 把这些parser错误统一压成「invalid unified diff」，734–740只把这一detail和原proposal交给fixer；prompt patch.md:7 / patch_fix.md:7 已说明前缀，所以“再重复同一句规则”没有新实证依据。

**建议：** 保留有界结构化诊断：file/hunk/数组索引、expected/observed old/new counts、非法前缀、zero-change hunk；归类后供既有fixer读取。仍拒绝原补丁，不自动补前缀/改计数/剥编号，不增加4000 cap或初次+3fixer次数。预期是提高反馈信息量，尚未证明能提高模型成功率。

**对应验证：** 用独立通用文件构造缺context前缀、计数差1、纯context无改动、正常多hunk；真实MockTransport→router→engine断言错误结构到下一请求、有效修复可apply/compile、四次上限不变。旧E1–E3只作回归负例，不把其正确修复作为模型提示答案。

## 2. 将展示行号与可编辑原文分开，并验证具体源锚点

**已证实：** headroom/patch.py:250–252 当前只传「0001: ...」拼接的源码；prompt patch.md:5–7却要求从未编号原文精确复制、不得带展示标签。E5将「 0003: import argparse」等标签实际复制进diff，Git不能匹配原文件。E4声明「@@ -84,1 +84,1 @@」，其删除文本在该attempt冻结baseline中仅匹配第86行，第84行是注释；无上下文的声明位置不符，实际Git返回「patch failed: train.py:84」。日志里的missing-blob后紧跟正常direct fallback，不能仅据此认定3way基础设施坏了。

**建议：** 在原128KiB来源预算内，将源码变成独立原文/行号元数据（例如带start_line和source SHA的原文块），不让编号成为可复制源码的一部分；不叠加两份完整源码扩大请求。若 Frank 允许下一版协议，再评估模型返回“路径+基线hash+精确旧块/新块”的锚定编辑，由host确定性生成标准diff及hunk计数；旧块不存在/多处匹配/重叠时明确拒绝，绝不模糊替换。这是待审的通用协议选项，不是已证明有效或已获实施许可。

**对应验证：** 重复相似函数、错误行号、stale hash、缩进/Unicode/空白行、多个不重叠编辑等通用夹具；精确匹配后生成diff仍须通过原path/policy/Git/compile门。真实provider效果只有在Frank决定后、受共享额度和停止规则约束的新组件实测才能确认。

## 3. 核对实际应用位置，避免“编译成功但改到了失效路径”

**已证实：** E6是14个零context插入hunk，首个「@@ -91,0 +92 @@」，其余声明到原106行；Git实际candidate新增代码全部位于124–137行。candidate的117行已调用 main()，123行是异常分支的 raise，原main内的前向/训练逻辑没有被替换。该结果记录 STATIC_CHECKS_PASSED、compile_exit_code=0、three_way_command_direct_fallback；保存的Lab结果仍在原前向OOM，steps=0、peak=24.750424064GB。因此“语法能编译”在此确实不足；本文不推断其他未执行新代码的数值正确性。

**建议：** 对每个应用后的实际变更区间生成可审计映射（原/新行、前后锚点、所在函数/类/模块），并核对它与声明的源锚点一致；没有可验证锚点的零context插入应明确拒绝/请求重出，不能接受Git漂移后的位置为模型本意。将实际位置及Lab异常作为数据交回规划器。仅位置/语法检查不能保证内存或数值正确，原20步/数值/参数量/吞吐与keep门全部保留。

**对应验证：** 通用多函数文件、已有 if __name__ 入口、重复锚点和合法显式EOF插入，断言声明位置漂移可被识别且合法EOF不误拒；有界CPU Lab验证新增语句是否在目标调用前执行，不用scenario专用规则，也不添加固定修复答案。只有之后真实验证通过才能计为修复，不能把静态通过算target。

## 精确证据索引（私有运行记录，不作为公开demo）

所有E项的 parsed.diff_lines 与 normalized_diff 均保留在原私有response；下列仅引用路径/哈希，不复制整份模型输出。
- **E1 s3/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/716fe9f9b3844031a3aa4bb9a9d04d0d/rounds/01/patches/patch-engine-59b5f9833e514d5a960a60c1dbae75b0/attempt-1-response.json；SHA256 89fe1aea3f33d2f54ed947489016eb52d1d0013458f201027fb255e2123ecad6。
- **E2 s4/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/01/patches/patch-engine-ede4f8cf1ec54d2588f5363de0574c0d/attempt-1-response.json；SHA256 efc0a75a97accb08a010fe4e42a17dc826975965dcb36f7880f9946050798898。
- **E3 s4/r05/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/05/patches/patch-engine-d1c454934de248dd85c5b8355eb47ada/attempt-1-response.json；SHA256 146b4d0df851ddba0fae4191749a9c79d0fa027dbbd2a8c571bb1e06942272b8。
- **E4 s2/r01/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/c23a1768850d49c993a891427d4d9c24/rounds/01/patches/patch-engine-4d41da47b8d34b489ce7a692e45c2cf0/attempt-1-response.json；SHA256 9195a90851a4973bccb61e338329b8a2ff60f967a56f3b22de131592b377beb4。
- **E5 s4/r06/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/77a60dc674f2491fb4cb44db8c441b08/rounds/06/patches/patch-engine-4c828765910d459f8d19dc2df9621aae/attempt-1-response.json；SHA256 6732acee622565c83de54aa102c8246bfbb8ef167f57c269e108a3f2e4c4d79c。
- **E6 s1/r03/a1**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/patches/patch-engine-a783b9738f94484e9b31adf972707f26/attempt-1-response.json；SHA256 dbd41352709925ca5f1c02de945b43bc18eaa9a84168c090465b3916bc815344。
- **E6位置/运行核对**：runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/patches/patch-engine-a783b9738f94484e9b31adf972707f26/attempt-1/patch-5b201bb3064e4a1f9b0e66838fc88bf3/candidate/train.py 第115–137行；SHA256 0ecd1483f12e01fc6e393c507fe5e53a6e11e358fc63ef15c653ea55b00ff069；runs/evaluation/live/20261024T231940915002Z-2098d11d/jobs/52d7c368ccca4f639599eedaf0995893/rounds/03/verification.json（after.status=oom/steps=0）。

本提案没有修改source/prompt/tests/PLAN、profile或ledger，没有网络/API/GPU调用；未降低原验收阈值。三个选项均等待Frank决定，不自动开始后续修复。


---

完整报告只读复核已经完成；泄密扫描的12个命中逐项证实为缓存摘要或文件内容摘要，仅添加精确路径+完整摘要例外，随后staged扫描0 findings。Ruff check/format与diff check通过。最终handoff还会随提交前staged扫描一并核验。
