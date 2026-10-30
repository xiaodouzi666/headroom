# Snapshot CLI 两案例真实流程验收与内容质量边界

本轮 s2 r6 与 nanoGPT r3 均走真实 Nebius SDK，首次回答失败后最多一次具体反馈修正，最终产出结构合法、引用峰值数值可核对的诊断。两例都是 needs_human，均未生成补丁、未运行新的 GPU 验证，不能计作自动修复成功或全量诊断准确率提升。

| 案例 | 独立运行 ID | 真实调用 | 报告费用（模型美元） | 终态 | 补丁 / GPU验证 |
|---|---|---:|---:|---|---|
| s2 r6 | d85f43185b5a448fad52d2a1761b9926 | 2 | 0.04389244 | needs_human；合法诊断 | 无 / 未运行 |
| nanoGPT r3 | 3d805a25b68943caac2f5b64b14bb6a6 | 2 | 0.04495420 | needs_human；合法诊断 | 无 / 未运行 |

两次费用合计 $0.08884664，仅是这两个运行；此前失败与费用仍保留并累计，不能把此数当整个 F3b 支出。结算由执行控制器确认，本次独立审阅没有重新打开金融账本。两个 private/cleanup.json 均为 cleanup_verified=true。

## 通过的实际功能

- 原始上传快照、提供的源代码、完整 evidence、原始模型 intent、程序派生量纲与公开诊断 SHA 绑定一致。
- s2 三组引用值为 9.130704896、4.564795392、4.565352448 GB；nano 四个引用栈之和为 17.202937856 GB。全部与所引用重建峰值栈的去重字节和精确一致，并且引用栈均在公开证据中可见。单位是十进制 GB；这些数值只指所引用栈，不自动代表整个类别、因果贡献或节省。
- 一次反馈修正真实生效：第一次失败和原始回答仍保留，第二次通过原有结构、政策与量纲验证；真实未知没有被清空。
- s2 指定的 source:119、132–133 和 nano 的 import、configure_optimizers 行均与提供的源码相符。提供源码仍不是经过认证的运行时源码，原生峰值计数缺失、分配器设置未知等限制继续展示。

## 仍存在的实际内容问题

s2：notes[0] 把 optimizer_state 称为最大类别，错误。temporaries 为 9,164,259,328 字节，optimizer_state 为 9,130,704,896 字节，前者多 33,554,432 字节。原始文字没有被修改。另外，“不改精度/参数就不可能减少”“不存在合规计划”属于未证明的排他结论；严格政策可以解释未给出补丁，不能证明所有参数保持策略都不可能。

nanoGPT：notes[0] 把四个引用栈说成整个 activation 类别，错误。引用仅 17,202,937,856 字节，类别共 23,286,259,712 字节，相差 6,083,321,856 字节；程序展示的引用量仍正确。notes[5] 把 GradScaler 描述为 float16/bfloat16 都启用，与 source:196 仅 dtype == 'float16' 才启用相矛盾。零梯度/优化器类别不能证明其 scaler 因果解释。checkpointing 的 3 GB 节省与 minor 吞吐影响也是未验证的预测，不能据此宣称满足零吞吐回退政策；model.py 缺失实际保留，计划因此未执行。

## 原计划验收口径

FINAL_48H §F3b-1 要求两个 CLI 快照的首因至少一个与真值一致。s2 的 optimizer_state 首因与 eval/mvp_phase1_v2.yaml 中 authored 标签一致，足以记录这一项的至少一个标签匹配；这不是独立因果验证。nanoGPT 在该 manifest 中明确 ground_truth=null / truth_status=unverified，虽然 activations 占重建类别大多数，不能冒充第二个独立真值命中或报告“准确率 2/2”。

本报告只完成两例 CLI 流程与人工质量复核。它不代替公网真实上传、恶意 pickle 拒绝、完整 F3b 其他要求或固定九场景验收。公开网页应继续显示 needs_human / not run，并保留模型解释可能出错的界限。

证据：s2-r6-independent-review.json；nano-r3-independent-review.json；两个 run 的 public-report.json、evidence.json、private/diagnosis-correction.json 与量纲来源记录。只新增审查报告，未改源码、历史回答或运行结果，没有新增付费调用。
