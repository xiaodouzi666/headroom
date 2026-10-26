# Headroom 差异化方案的一手先例核查

日期：2026-10-27（Asia/Shanghai）。本报告为有限范围检索，不是系统综述、专利检索或“不存在同类工作”的证明。仅研究与建议；不包含新增模型调用、GPU 验收或历史重评分。

## 结论

建议新增“修复适用性记录与反例查询”：把补丁、运行条件、数值约束和真实测量绑定，只对已测的精确条件报告结果；超出证据覆盖返回未知，保留失败反例。

这可作为 GPU 内存修复场景的工程差异化，不能称为“完全没人做过”。自动内存优化、输入条件守卫、带范围的经验性修复证据均有先例。CertiPatch 是后两者组合的重要邻域先例，不能省略。现阶段没有证据表明 Headroom 比下列系统更好，亦不能从本功能推导原 6/9 验收已通过。

## 检索范围

已检索的关键词族：

- AutoChunk automated activation chunk memory inference neural networks paper
- Dynamic Tensor Rematerialization Checkmate memory efficient deep neural networks paper
- GPU memory optimization validation proof repair agent workload numerical equivalence certificate
- DeepSpeed autotuning optimal micro batch ZeRO；PyTorch activation checkpointing memory budget API
- MOA memory optimization agent profiling Analyzer Patcher
- torch compiler guards recompilation shape constraints
- CertiPatch empirical behavioral certificate automated program repair；“CertiPatch”

依据为作者论文、官方项目仓库及框架官方文档。下面选取 8 个直接相关的一手来源；没有穷尽所有语种、商业未公开方案或相关工作引用网络。未检索到某个精确组合，不等于该组合不存在。

## 八项直接先例

| 来源 | 核查到的能力与边界 | 对我们的约束 |
|---|---|---|
| [AutoChunk，ICLR 2024](https://arxiv.org/abs/2401.10652) | 自动搜索分块方案，并生成代码以降低长序列推理的激活内存；其论文主要针对推理。 | 自动分块、生成优化代码、显存与速度权衡不是原创。 |
| [Dynamic Tensor Rematerialization，ICLR 2021](https://arxiv.org/abs/2006.09616) | 支持动态图的在线张量驱逐与按需重计算，并讨论内存预算。 | 运行时自动适配内存预算不是原创。 |
| [Checkmate，MLSys 2020](https://arxiv.org/abs/1910.02653) | 基于硬件性能模型和优化求解选择重计算调度。 | 在内存限制下自动搜索时间与内存的权衡不是原创。 |
| [DeepSpeed Autotuning，官方仓库](https://github.com/deepspeedai/DeepSpeed/blob/master/deepspeed/autotuning/README.md) | 搜索 ZeRO、micro-batch、梯度累积等配置；说明最优配置依赖硬件。其最大训练 batch 配置不等同于保证保持原始 effective batch。 | 多配置调优及 batch 关系本身不是原创，严格语义约束需要单独验证。 |
| [PyTorch Memory Budget API，官方说明](https://pytorch.org/blog/activation-checkpointing-techniques/) | 对编译区域自动选择 selective activation checkpointing 策略；预算参数 0–1 表达重计算策略范围。 | 不能将其描述为任意绝对 GB 的显存保证；自动 checkpoint 策略已有先例。 |
| [PyTorch compiler guards，官方 DevLog](https://docs.pytorch.org/devlogs/dynamo/2025-06-04-inside-torch-compile-guards/) | 将 shape、dtype、device 等假设绑定到编译产物，条件失效时重新编译。 | 改变输入后失效或重验的设计不是原创。 |
| [MOA，2026 预印本全文](https://arxiv.org/html/2606.31368v1) | profiling、LLM 模式分析、检查器生成及补丁迭代；§3.4 的自动补丁验证使用 clangd 语法分析，评测另包含人工语义审核。对象为 OpenHarmony C/C++ 内存优化。 | 不能声称第一个 profiling→LLM→补丁闭环；该文未展示 GPU 训练多配置的配对数值适用性记录。后一句仅限所读论文内容。 |
| [CertiPatch，作者项目仓库](https://github.com/aliuyar1234/certipatch) | 冻结语言模型的行为修复；声明范围与覆盖，绑定产物，生成可重新核验且验证失败即拒绝的经验性证据。README 明示 deterministic train→certify→verify、artifact-locked certificates 及 scope/coverage semantics。 | “带范围、hash 和拒绝机制的修复证据”已存在邻域先例；我们的可能差异是 GPU 内存补丁、训练不变量及真实资源测量的领域组合，不是经验性证书概念首创。 |

CertiPatch 的作者页面可通过检索读取，但直接打开作者站点与 DOI 在本次浏览工具中失败；上表以成功打开的作者 GitHub README 为能力证据。未独立复现其结果，也不据此宣称其数值结果可靠或已同行评审。其“replayable”是证据重新计算，不是恢复 Headroom 已撤销的前端 Replay 功能。

## 建议功能边界

- 原始及候选源码、命令参数、策略、模型与输入身份、随机种子、有效 batch、精度、优化器配置、GPU 和软件环境应明确绑定。
- 导入 baseline、candidate、数值参照及文件 hash，保留 OOM、峰值、更新步数、数值误差和失败原因。
- 输出至少区分已测通过、已测失败、未知与证据无效。缺少必要数值参照不能获得严格通过。
- 同条件出现矛盾结果时保留全部证据，不能择优展示；batch 4 与 16 通过，不能推断未测试的 8 也通过。
- hash 仅说明内容一致，不是可信执行证明；有限次测量不是全输入语义证明或未来运行保证。硬件空闲显存等动态条件也不能由静态硬件名称代替。
- 读取历史产物必须按其原有条件解释，不补造字段、不改历史结果、不增加原 MVP 成功数。
- 该功能的价值是使失败、未知和适用范围可查，而不是生成一个“已安全”的标签。

## 拟验证用例

1. 正常候选在精确已测条件通过；改源码、精度、effective batch、设备或策略后，拒绝沿用原结论。
2. 仅针对固定 batch 写死的候选在另一配置失败；反例必须保留。
3. 显存降低但漏样本、少更新、改变 loss 权重时，不得严格通过。
4. 缺数值参照、NaN、缺测量、hash 损坏、重复或矛盾记录得到可解释状态。
5. 两端通过而中间失败的合成记录，证明查询实现不插值、不假定单调性。此用例是验证软件行为，不宣称已发现真实 GPU 同类现象。
6. 使用已有真实结果验证导入与追溯，但清楚标为历史记录；新多点 GPU 实测与模型自动修复效果单独验收。
7. 新测量应先固定配置点、对照、容差与重复规则；测试集和人工控制不得混入原九场景自动修复分子。

建议对外用语：“Headroom 为 GPU 内存修复生成可核查的实测适用性记录，联合保留训练约束、运行条件和失败反例；对未测试配置明确返回未知。”

不支持的用语：世界首创、完全无人做过、形式化证明安全、连续安全区间、已超过现有优化器。
