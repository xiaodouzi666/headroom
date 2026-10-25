# s2 T2.1 的 state-first 路线：只读核实与待测设计

2026-10-25。结论：公开资料支持真正的 FP32 优化器状态卸载；本项目有一个规模较小、值得验证的候选——部分 moments 常驻 CPU，按组搬到 GPU 执行原 AdamW 更新，再搬回 CPU。现有结果没有证明它通过 25% 耗时门，也没有满足模型生成的“第 1 轮状态、第 2 轮激活”验收。本报告不新增运行、不改变 PLAN/manifest/门槛、不计修复分，不作为给模型的人工答案。

## 已读项目证据

原 PLAN T2.1 指定 strict 下至少两轮达到 fit:22GB，并明确先优化器状态、后激活。当前 s2_capacity_v2 是 34 个宽 2048 的 residual MLP block，batch 24、sequence 128、FP32、完整 backward 后一次 AdamW.step，foreach=True；无 AMP、梯度累积、梯度裁剪或跨参数全局更新算法。参数共 1,141,338,112 个，204 个 parameter tensor，原两个 FP32 moments 共 9,130,704,896 bytes。保留 allocator 为 expandable_segments:True。

以下来自既有 v2-c 原始 result.json、补充分析与独立 audit，全部是人工校准控制，不能计模型成功。最初因旧 JSON 大小限制失败的分析收据仍存在；这里采用保留原 raw result 的 supplement/audit，并未把最初失败改成成功。四项 audit 均 accepted=true，状态清单观测于 update 19，Lab 独立记录 20 次更新。

| 既有控制 | peak GB（1e9 bytes） | Lab step median ms | 相对基线耗时 | CUDA moments GB |
|---|---:|---:|---:|---:|
| capacity baseline | 22.919430656 | 951.694498 | 0% | 9.130704896 |
| foreach=False（旧文件名 optimizer_only） | 22.564054528 | 953.124341 | +0.150242% | 9.130704896 |
| checkpoint only | 22.919430656 | 1118.291948 | +17.505350% | 9.130704896 |
| foreach=False + checkpoint | 18.639258624 | 1128.079813 | +18.533817% | 9.130704896 |

因此 foreach=False 的已测收益不是 moments 减少。现有 in-backward helper 也只是更新时机改变并提前释放梯度，其两个 moments 仍按参数创建；不能把梯度缩减称作状态缩减。

Lab 的 step_ms 是已完成 optimizer updates 之间的区间，完成处先 CUDA synchronize；第一条包括 setup（这些运行约 9.3–9.6 秒），中位数没有被第一条支配。计时包含观测开销，不是纯 GPU kernel 或 optimizer-only 时间。既有数据没有独立测量 H2D/D2H 带宽、CPU Adam 时长或每阶段 compute 时间。校准早于后续 checkpoint worker precision 修复，所以本表是历史的设计依据，不能替代新源码下的资格测量。原 scalar 比较的 combined 最大 loss 差为 4.76837158203125e-7；强输入/有效 batch/目标配对仍未建立，不能把 same seed 当运行配对。

数据与 SHA 见同名 JSON；主要入口为 reports/s2-calibration-v2-20261025-c/audit.json、descriptive-control-comparison.json、human-control-standard-verification.json。

## 官方方案实际支持什么

- PyTorch 2.5.1 AdamW 按 parameter 建立 exp_avg / exp_avg_sq，并在各 param group 内执行 elementwise 更新；foreach 会生成一组中间张量。分组可以限制中间工作集，但单纯分组不会减少两个 moments 的常驻量。这是源码事实；“分组同时为状态流式搬运提供机会”是本报告的工程推断。[2.5.1 AdamW 源码](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/torch/optim/adamw.py)
- DeepSpeed / Microsoft 的 ZeRO-Offload 公开支持将优化器状态及计算放到 CPU。官方示例使用不同模型、V100 和 CPU 环境，其加速数字不是本机的吞吐承诺。[官方教程](https://www.deepspeed.ai/tutorials/zero-offload/)
- 固定 v0.15.4 的 DeepSpeed CPUAdam 支持 FP32 moments 与 AdamW 模式，要求 CPU master parameters；其 offload ratio 是 ZeRO Stage 3 的参数，不是普通 PyTorch AdamW 的通用开关。相同版本代码已经有分块读写 pipeline 配置。[CPUAdam 源码](https://raw.githubusercontent.com/deepspeedai/DeepSpeed/v0.15.4/deepspeed/ops/adam/cpu_adam.py)、[offload 配置源码](https://raw.githubusercontent.com/deepspeedai/DeepSpeed/v0.15.4/deepspeed/runtime/zero/offload_config.py)
- NVIDIA 建议批量传输及 pinned buffers；真正的传输/计算重叠还需要可并行硬件、非默认流等条件。大量小复制和每步临时 pin_memory 会增加开销。[CUDA Best Practices，10.1](https://docs.nvidia.com/cuda/cuda-c-best-practices-guide/index.html)
- 异步 D2H 后 CPU 不能立即消费数据；H2D 进行中也不能重写其 pinned 源缓冲。需要 events / stream waits 及明确的 buffer 生命周期。[PyTorch 官方传输教程](https://docs.pytorch.org/tutorials/intermediate/pinmem_nonblock.html)、[2.5.1 CUDA semantics](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/docs/source/notes/cuda.rst)
- PyTorch 不保证数学相同的 CPU/GPU 或不同实现路径得到逐位相同结果。因此“不量化地复制状态”不等于“整个更新已证明 identical”。[2.5.1 Numerical accuracy](https://raw.githubusercontent.com/pytorch/pytorch/v2.5.1/docs/source/notes/numerical_accuracy.rst)

兼容性边界：上述 PyTorch 算术与 stream 接口以 2.5.1 为准。DeepSpeed v0.15.4 是已查明的公开设计依据，不是本机已通过的安装组合；当前项目没有声明 deepspeed 或 bitsandbytes 依赖。Lab 仍是网络关闭、32g RAM、8 CPU 的受限容器；不能借主机全核或额外内存得出吞吐结论。较新的教程中的新 API 也不自动视为 2.5.1 可用。

## 25% 时间门留下多大空间

以下全部是计算出的设计筛选值，不是传输实测：

- 基线 B = 951.6944976 ms；原上限 1.25B = 1189.6181220 ms。
- 第一轮最多新增 237.9236244 ms，但第二轮还需要为激活优化付出时间。
- 既有 combined 时间 1128.0798134 ms，距原上限只剩 61.5383086 ms。这只是代理余量；新分组实现可能改变其基础时长。
- 每个相同 block 有 33,568,768 个参数；两个 moments 占 268,550,144 bytes。参数/梯度各占 134,275,072 bytes。

若 CPU 仅保存选中状态、更新仍在 GPU，每步串行搬回与搬出同样大小 S 的 moments，未重叠开销近似为 S/B_H2D + S/B_D2H + launches/synchronization。下表假设两个方向均达到所列持续带宽；12 和 24 GB/s 只是敏感性假设，不是 azuki 带宽。CPU staging、内存分配和额外 observer 开销尚未计入。

| offload 范围（仅容量举例） | CPU moments bytes | 每步往返 GB | 12 GB/s 下 ms | 24 GB/s 下 ms | 吃完 61.538 ms 前所需对称带宽 GB/s |
|---|---:|---:|---:|---:|---:|
| 1 block | 268,550,144 | 0.537100288 | 44.758 | 22.379 | 8.728 |
| 2 blocks | 537,100,288 | 1.074200576 | 89.517 | 44.758 | 17.456 |
| 3 blocks | 805,650,432 | 1.611300864 | 134.275 | 67.138 | 26.184 |
| 全部 34 blocks | 9,130,704,896 | 18.261409792 | 1521.784 | 760.892 | 296.749 |

据此，简单同步全量往返不适合本项目；小部分状态可能有窗口。不能把表的串行公式当成重叠方案的绝对下界；双向 pipeline 与 compute overlap 可改变关键路径，但需要更多 staging memory 和实际调度证据。也不能直接把某个 states 容量从现有 peak 相减并宣布达标，峰值可能移到另一阶段。

## 优先候选：部分 CPU 常驻 moments + 同 GPU 算术的分组更新

这是工程设计建议，尚未实现或验证。

1. 只选择一个有界参数子集，其 m/v 从创建时起保持 FP32 CPU 常驻，保留 step、betas、eps、lr、decoupled weight decay、原参数顺序、所有 trainable parameters、输入、batch 和完整 loss 定义。其他参数照常更新。
2. 全部 backward 完成后，按组更新；一次只把当前选中组的 moments 搬到 GPU，执行 2.5.1 原 AdamW functional 路径，更新结果无 dtype 转换地写回 CPU。恢复或保持 CPU storage 必须发生在逻辑 step 完成前。禁止每步重置 moments，禁止错过首步，禁止 stale/delayed updates。
3. 不能在整个 optimizer.step 前将所有 offloaded states 一次性搬回，再调用原全参数 foreach：那会重新恢复原状态和 foreach 临时张量峰值。分组是此卸载设计的工作集控制；若使用 foreach=False，其临时张量收益也必须单独列出。
4. 保留一个外层 optimizer.step / 一个完整 logical update，内部用 functional kernel；不能把多个小 optimizer.step 冒充多个训练步。固定参数覆盖和每个 state counter，每次完整 step 才推进。
5. 优先从简单、同步、少量 persistent pinned buffers 开始设计；只有同步实现不能满足时间门时，才讨论 event 管理的有界预取。不将“non_blocking=True”视为已经获得 overlap。
6. 证明 state-first 要看 GPU moments 常驻字节实际下降、CPU moments 增加、总 m/v 元素及 FP32 内容保留，同时记录组内 GPU staging 峰值。仅 optimizer 名称、参数总量或 total peak 下降都不够。分组-only 控制能区分 temporary 贡献与真正状态贡献。

相较 CPUAdam，这条路线避免了 CPU 算术差异和新增编译依赖，也没有在 backward 中修改参数；相较全量卸载，它给激活优化留下更多时间。即便同 GPU functional 算术，改变 foreach 分组、kernel 选择或数据排列仍需逐步比对参数与 moments，不能先声明 bitwise identical。

目前 fixture 的 optimizer_inventory 将 moment.device == parameter.device 当作 layout_valid，因此一个合法 CPU 状态方案会使该字段为 false。不得静默忽略它，也不改旧分类验收；未来应另加通用、明确双设备的状态清单，保留旧观测，证明 shape/dtype/total counts 与 CPU/CUDA residence。当前 allocator-origin 分类只覆盖 GPU allocator，不能代替 CPU 清单。

## 其它公开候选与不适用项

| 路线 | 真正减少 GPU state？ | 当前判断 |
|---|---|---|
| 部分 CPUAdam + GPU 参数副本 | 可以 | 需 CPU master、梯度 D2H、更新参数 H2D；每步传输约 8P_selected bytes，相比 moments 往返 16P_selected 少，但增加 CPU 算术与内存带宽压力。8 CPU 容器内未测；可作第二候选，不能引用厂商其它硬件成绩证明本机通过。 |
| DeepSpeed ZeRO-Offload / ratio | 可以 | 公开完整实现可参考，但直接替换引擎会涉及新依赖、编译、distributed/engine step、state/checkpoint 和观察器兼容；比局部状态方案范围大。目前无本机导入、CUDA 12.4 兼容或端到端数值证据。 |
| PagedAdamW32bit | 可以迁移状态，但驻留和观测需证实 | 官方有 32-bit 版本与 Unified Memory 方案；触发条件及速度依赖内存压力。使用非 PyTorch allocator 后，低 torch peak 可能是观测缺口，不能拿来通过 fit:22GB。当前更不适合作为最小修复。 |
| foreach=False、fused=True、仅拆 param groups | 不能据此声称 m/v 常驻下降 | 主要变化是临时张量/调度/融合；须有独立状态证据才能称 state-first。 |
| optimizer-in-backward | 单独使用时不减少 m/v | 主要释放 gradients 或改变其生命周期，不替代优化器状态门。 |
| 8-bit moments、BF16 moments、Adafactor/SGD、冻结部分参数 | 改变状态精度或优化数学/训练范围 | 不作为本 strict 字面要求的保持数学路线；不能靠降低标准通过。 |

Paged 来源：[bitsandbytes v0.43.0 文档](https://huggingface.co/docs/bitsandbytes/v0.43.0/optimizers)、[PagedAdamW32bit API](https://huggingface.co/docs/bitsandbytes/en/reference/optim/adamw)。PyTorch 当前官方文档明确说明直接 CUDA/第三方分配对 allocator profiler 不可见；这里借用的是观测原理，不调用其较新版 host-memory API。[可见性说明](https://docs.pytorch.org/docs/2.14/torch_cuda_memory.html)

## 必须保留的后续证明，不能由文献替代

- 新控制方案先预登记，再由 root 排资源；本报告没有新增运行授权或自动启动任何实验。
- CPU tiny 验证每一步 parameter、m、v、step counter，而非只 loss；真实 GPU 再核同输入和初始化、同原有效 batch、全部参数覆盖、同完整 20 次更新。same seed 不替代输入与初态证据。
- 同原数值容差、25% 时间上限及 22e9 bytes 目标；同时记录 copy/synchronize 完成，最后一次 step 不把未完成卸载藏到 Lab 截停之后。
- 保留 group-only 对照以区分 temporary 与 state 贡献；第二轮才添加激活方案。旧校准数字只帮助选规模，不计正式两轮成功。
- 原 moments 总量仍是 9,130,704,896 bytes；新 GPU/CPU 常驻分布与峰值 staging 的事实必须单独测出。总逻辑 state 和重复 staging storage 分开记账。
- 新方案的 checkpoint、参数组重排、resume state_dict 都要保持映射；目前只支持源码中实际使用的 dense FP32 eager AdamW，无 closure/AMP/gradient clipping/gradient accumulation/DDP 等泛化承诺。
- 最终必须由模型自己生成可移植补丁，在实际沙箱运行并独立获得两轮 keep、数值与吞吐证据；人工研究控制、这个报告或公共文档都不能计模型分，也不向模型塞本场景人工控制代码。

公开资料已足够确定“存在保持 FP32 state 的卸载思路”，无需将 T2.1 改写成“优化器临时内存”。仍未知的是当前容器内的有效搬运带宽、分组和观测器额外开销、跨 kernel 的真实数值轨迹、以及模型能否在预算内独立实现。故 T2.1 state-first 门维持未通过。
