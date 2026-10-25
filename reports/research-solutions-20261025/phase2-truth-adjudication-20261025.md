# Phase2 首因真值独立审核（2026-10-25）

结论：建议仅对**未来版本**的 `nanogpt`、`hf_trainer` 事前裁定首因 `activations`；`s5_fragmentation_varlen` 继续 `unverified`。这是根代理复核前的证据建议，未修改 manifest、生产代码或历史分数，也不保证修复成功。

本次刻意不读取模型诊断、候选补丁或模型首因。使用固定源代码、原设计、原始 baseline result/manifest/JSON snapshot，以及对应公开版本主源。没有模型、Tavily、GPU 新调用。计算收据是 [phase2-truth-baseline-evidence-20261025.json](phase2-truth-baseline-evidence-20261025.json)，输入路径与 SHA 采用数组记录；保留源码副本与当时 manifest 的逐项 SHA 全部一致。

| 场景 | 建议未来首因 | 核心独立观测 | 置信边界 |
|---|---|---|---|
| nanoGPT | activations | 初次训练 forward/GELU OOM，0 更新；原生峰值 24,705,183,744 B；历史事件峰值中 forward 来源 23,286,259,712 B（94.26%） | 高置信于该原始 FP32、batch 32、sequence 1024 配置的首次 OOM；不等于完整训练峰值或逐个 saved tensor 身份证明 |
| HF Trainer | activations | 初次训练 forward/MLP GELU OOM，0 更新；原生峰值 24,805,119,488 B；历史事件峰值中 forward 来源 23,360,249,896 B（94.18%） | 高置信于该原始 FP32/eager attention 配置的首次 OOM；优化器状态将来的需求是另一命题 |
| s5 | unknown，保持 unverified | 20 更新完成、无 OOM；终态 inactive 19,124,731,904 B，其中整段全空闲 18,597,543,936 B，混有活跃块的 inactive 527,187,968 B | 有变长分配/缓存增长，尚不能裁定有害碎片化是首因 |

## 可复核证据

**nanoGPT**：`repos/nanogpt.yaml` 固定 upstream commit `3adf61e154c3fe3fca428ad6bc3818b27a3b8291`；`reports/nanogpt-lab-baseline-20261024.json` 与 `runs/nanogpt-lab-validation/5e5566267e7b45a3a7e6f75fe738ed08/{manifest.json,result.json,artifacts/snapshot.json}` 相互对应。实际参数包含 batch=32、block_size=1024、24 层、hidden=1024、accumulation=1、float32。源 train.py:300 的训练 forward 在 model.py:89 GELU 失败；backward 位于 305、optimizer step 位于 311，尚未到达。不是此前 0 次更新期间的 no-grad eval 路径。

原快照 2,575 条完整事件按地址重放，没有未知 free 或重复 alloc；重建 requested-byte 峰值恰与原生峰值相等。forward 中仅 MLP linear/GELU 两组就有 5,905,580,032 B 与 5,368,709,120 B；参数为 354,599,936 个，FP32 参数容量约 1.4184 GB。峰值没有 optimizer 路径分配。现有大部分活跃内存来自各层前向中间结果；最后失败的 512 MiB 请求并不代表问题只是一块短暂缓冲。

**HF**：`repos/hf_trainer/train.py:43–82` 固定随机 GPT2-medium、eager attention、batch 16、sequence 1024、FP32、gradient_checkpointing=False、adamw_torch；源 SHA 为 `7d3a714264fc76371c1183da125ec0ffa550bc78c68bbe2acd7868870684923a`。`reports/hf-trainer-baseline-20261024.json` 与 `runs/hf-full-baseline-20261024/77c5ef8e0948458688116ff68f38c586/` 对应，原 traceback 在 transformers 4.46.3 的 `modeling_gpt2.py:576` / `activations.py:56` 失败，失败请求 256 MiB，0 更新。参数数目 354,823,168；约 1.4193 GB FP32 参数远小于前向分配。

1,071 条 allocator 事件重放无缺配对；requested-byte 峰值 24,805,101,708 B，比原生计数少 17,780 B。这些是 requested size 与原生 allocated 计量的区别，不能把二者说成精确相等。原生计数仍是峰值权威。仅注意力 softmax 和 MLP 激活对应的活跃来源各约 7.516 GB；峰值无 optimizer 来源分配。HF 报告中的“optimizer states + activations”是原设计目标，**不构成当前失败时已经存在 optimizer state 的证据**。单独 HF 验收若要求两个分项诊断，应明确把 optimizer state 写成完整训练的未来风险，而非本次已观察的首因；本建议没有替用户改写那个验收项。

**s5**：原 README 明确 harmful fragmentation pending；`scenarios/s5_fragmentation_varlen/train.py:96–140` 是变长真实 TokenMLP 训练，没有 filler、每步 empty_cache 或人为 OOM。当前原始 baseline 使用 `runs/evaluation/live/20261025T095016638167Z-ad191318/jobs/b8849438af8443f0aa4717e859f4b4aa/lab/4c5d3ed8619340cbabe08ae470b1c51b/`；只读其 Lab baseline，未读同 job 的诊断或候选。6,543 条事件、20 次更新、无 OOM；终态大量 inactive 位于整段全空闲段，符合正常可回收缓存。此前基线 README 还记录 allocation retries=0。既不能把 reserved-allocated 全算碎片，也不能把“缓存很大”改名为 activations 来增加首因可评分数。原生 allocated 峰值 5,021,758,464 B；requested-byte 重建峰值 5,020,708,900 B，差 1,049,564 B，收据如实保留。

## 主源与语义边界

- [PyTorch 2.5.1 CUDA memory management](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/cuda.rst)：缓存分配器的 unused memory 与 tensor 占用不同；expandable segments 面向变化尺寸的分配模式，并不意味着任一 reserved gap 都是有害碎片化。
- [PyTorch 2.5.1 autograd](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/autograd.rst)：前向可为反向保存中间结果。本审核的 frame 归因能证明 forward 来源，不能替代每张量的 saved-state 观测。
- [PyTorch 2.5.1 AdamW](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/optim/adamw.py)：step 路径的状态初始化不能提前归因给首个 forward OOM。
- [固定 nanoGPT model.py](https://github.com/karpathy/nanoGPT/blob/3adf61e154c3fe3fca428ad6bc3818b27a3b8291/model.py)、[transformers 4.46.3 GPT2](https://github.com/huggingface/transformers/blob/v4.46.3/src/transformers/models/gpt2/modeling_gpt2.py) 与 [激活实现](https://github.com/huggingface/transformers/blob/v4.46.3/src/transformers/activations.py)：与原 traceback/分配栈的具体操作一致。

若根代理独立复核接受，未来版本应冻结源/argv/库版本/数据和标签依据；strict 与 allow_precision 的初始 baseline 相同才复用标签，修复后的精度政策不回头改变原 OOM 首因。两个新标签只让固定 20 槽中的最多可判首因槽从 14 增至 18；不能据此声称准确率达 75%，更不能改写历史 unknown。

s5 要升级为已裁定，至少需要同一失败/浪费时点的 allocator/backend/可用显存、完整块历史与失配请求，或预先登记、保持工作负载和数值目标的 allocator 对照证据，并区分 reserved 改善与 allocated 峰值下降。现有观测没有满足这些条件，本轮不追加运行。

## 根代理独立复核

根代理另行重放 alloc/free_completed 并核对当前源/数据，见 [phase2-truth-root-review-20261025.json](phase2-truth-root-review-20261025.json)（SHA-256 `acf5ba774df69edaa91e1753308d57cba90b13851d2489c93eb1b67d6fe93917`）。其 nanoGPT/HF forward 比例分别为 94.2566% / 94.1752%，optimizer 来源均为 0；当前 nanoGPT 三源码及 train/val 数据字节哈希与原 baseline 捕获相符，HF 源码也匹配。根代理同意仅未来版本纳入两项 activations 标签，s5 继续 unknown。此补充不改原始计算收据、manifest 或任何历史分数；未来版本化过渡另行冻结。
