# 数值参考方案核实与实施记录（2026-10-25）

本报告属于 Headroom 数值验证子任务。原 PLAN、固定九场景和历史 v7 的 1/9 均未改写。本子任务没有模型 API 调用。新增能力显式 opt-in，默认 small-batch scalar gate 保持不变。

## 官方来源与采用边界

- [PyTorch 2.5.1 numerical accuracy](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/numerical_accuracy.rst)：浮点运算顺序、batch/逐样本、CPU/GPU 均可能改变数值。相同 seed 不证明相同实际工作负载，也不保证位级相等。原 fp32 1e-3 阈值保留。
- [PyTorch 2.5.1 reproducibility](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/randomness.rst)：seed 只是随机性控制的一部分，DataLoader worker、NumPy、算法选择也相关。因此配对依靠实际输入/标签与初始参数指纹。
- [PyTorch 2.5.1 save_on_cpu](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/autograd/graph.py#L300-L355)：forward 保存的张量可复制至 CPU，在 backward 回原设备。本实现使用其 pack/unpack，pin_memory=False；嵌套 hooks 仅最内层有效，故本轮只支持已有 s3/s4 standalone source contracts。
- [官方 saved-tensor hooks 教程](https://docs.pytorch.org/tutorials/intermediate/autograd_saved_tensors_hooks_tutorial.html)及[2.5.1 文档原文](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/autograd.rst#L615-L654)：可将张量保存到磁盘，unpack 可重复调用，不能第一次读取即删除文件。本实现按 packed 对象寿命及运行结束清理。
- [PyTorch 2.5.1 serialization 源码](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/serialization.py)：该版本支持 weights_only=True 和 map_location。本实现只读取本次参考自己写入的张量文件，显式 weights_only=True，恢复原 dtype/device。
- [HF Accelerate 官方累积指南](https://huggingface.co/docs/accelerate/main/en/usage_guides/gradient_accumulation)：变长 token 任务须按整个 effective batch 的有效 token 总数归一化，不能平均各 microbatch 的平均 loss。这里只采用数学原则，没有引入最新版 Accelerate 或自动改写任意训练循环。
- [PyTorch 2.5.1 AMP examples](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/amp_examples.rst#L111-L140)及[checkpoint 源码](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py)：scaler、step、clip 时机按 effective batch；checkpoint 有 RNG 保存及重算条件，推荐明确 use_reentrant=False。不能把多次 backward 的 scalar 直接当一次 optimizer-update loss，也不擅自除以累积次数。

以上是官方事实；将这些机制用于 Headroom 原始工作负载参考是本项目工程设计，并非官方对九场景结果的保证。

## 实施

新增 headroom/verify/offload.py、offload_disk.py，接入 lab/run_target.py、lab/runner.py 和 verify/runner.py、compare.py；测试在 tests/test_verify_offload_reference.py。

调用选择 reference_strategy="original_saved_tensor_offload"，并可显式设置 reference_offload_disk_bytes 与 reference_max_seconds（上限 480 秒）。新的参考必须与 baseline 保存的 manifest argv 一致，实际源码 SHA 匹配 baseline 当时捕获的源码 SHA，初始数据/参数指纹一致，完成规定 20 次更新，并具有真实 hook、同运行环境、完整配对及原始精度证据。未知不会变成通过。reference 与原 baseline 必须已知同精度；candidate 精度变化仍服从原 policy 与原容差。

reference 的内存与时间不计入 candidate 性能评分。nanoGPT 的 repository_no_reference_exception 保留；没有把现有 s3/s4 配对器偷偷扩为通用梯度累积证明器。

Lab 32 GiB 容器内存限不变。CPU 后端限制活跃 saved tensors 16 GiB。显式 disk 后端将全部 CUDA saved tensors 落在当前新 run 的 /out 磁盘独占目录，CPU 只持有单张量传输暂存，单张量不得超过 CPU cap 的一半，为序列化缓冲留余量；这不是进程 RSS<=16 GiB 的声明。磁盘上限 64 GiB 按实际序列化写入字节计算，包含 header/对齐。不用 1 GiB tmpfs /tmp。调查时 /home 盘可用约 5.6 TiB。

临时目录独占创建、权限 700；文件 EXCL+NOFOLLOW、权限 600；文件随 packed 对象释放或参考结束删除。host 仅在容器停止确认后清理本次 run 的遗留目录，保留 cleanup receipt。

## 实测

- CPU 与 CUDA tiny：普通和 CPU offload 均完成 20 更新，loss 最大差 0，三项配对 true；CUDA 420 次真实 copy/unpack，保存张量峰值 2,150,400 bytes。见 offload-calibration.json。
- CUDA tiny disk：20 更新、loss 差 0、三项配对 true；420 次真实 torch.save/torch.load，实际磁盘峰值 2,646,000 bytes，wrapper 与 host cleanup 均 verified。见 offload-disk-calibration.json。
- s4 原 batch8 CPU 后端唯一试验：7 更新后触及 16 GiB cap，saved_tensor_cpu_budget_exceeded；保存张量峰值 17,066,123,264 bytes。前 5 loss 与 v7 候选差 0，但参考未满 20 更新，仍 n/a / target=false。未扩大 cap。见 offload-s4-original-batch.json。
- s4 原 batch8 disk 后端唯一试验 f7c2efd573fb42a1902d973f39092cb6：完成 20 更新，20 个 loss 全部与保存的 v7 候选相同；新 opt-in 补充报告 target=true，实际输入、effective batch、初始参数/目标、原精度和原 baseline 绑定全部成立。实际磁盘峰值 44,302,792,560 bytes（约41.26 GiB），最大单张量暂存 128 MiB，1220 次真实保存/读取，wrapper 与 host 清理均 verified。见 offload-s4-disk-reference.json。SSH 中途断开后只核对了原 host/容器继续运行，没有启动第二次试验；原 host 正常完成并保存结果。最后 proof 补强使用同一收据离线复核通过，没有 GPU 重跑。
- disk 引入前 166 个 Verify/Lab focused 测试通过；最后 proof 补强后 96 个 focused 测试通过，Ruff 通过。额外真实 PyTorch 2.5.1 CPU serializer smoke 验证了非连续 float32[4,3] 的两次 unpack 值/dtype/shape 相同、实际序列化 1180 bytes，以及 64-byte 实际 header cap 阴性与清理。见 offload-real-serializer-smoke.json。完整离线回归由主线程单独记录。

## s4 与 s7 的区别

s4 v7 的原版和 candidate 默认 batch8，旧发现器选 batch1 参考；原标量差 0.052162 不能单独证明删除 retain_graph=True 改了数学。新参考保持原 argv/batch、初始化和精度，补充可检查证据。

s7 不应归因为跨 batch。v7 baseline/candidate 均未改 CLI，默认 batch8。配对 unknown 确因当前观察协议未覆盖 s7；同时 diff 明确把 AdamW(model.parameters()) 改成 AdamW(model.head.parameters())。原版 backbone 仅 eval()、仍 requires_grad=True 且参与 optimizer 更新；candidate 不再更新 backbone。源码没有改 RNG/构造器，不等于已有实际初值指纹证明。

[PyTorch 2.5.1 autograd 文档](https://github.com/pytorch/pytorch/blob/v2.5.1/docs/source/notes/autograd.rst#L97-L142)明确 eval() 不冻结梯度。因此补 capture 不能把 s7 更新集合变化认证为等价。原计划要求保持训练语义，默认保留 backbone 更新，不按注释自动改为 head-only。

[DeepSpeed ZeRO-Offload 官方教程](https://www.deepspeed.ai/tutorials/zero-offload/)给出将 optimizer 状态和计算转到 CPU 的公开路线，可继续更新全部参数。它在本项目仍是后续工程候选：没有实证 optimizer 初态/每步更新、CPU/GPU 数值误差、>=30% 显存降低和 <=25% 吞吐回退，不宣称 s7 已解决。

后续跨 batch 适配还须捕获每次 update 的实际样本/标签、loss 分子和有效计数、初始化与 optimizer 初态、step/zero_grad/scaler 时序，并处理随机层和 BatchNorm 等行为。公开资料不能让任意源码天然满足这些条件；不足就保留未证明。原 6/9 目标及数值/性能门槛均不变。

完整 disk reference 的 host 墙钟为 224.717085 秒，低于 480 秒预算。该时间只属于数值参考，不是候选吞吐。s4 在新显式参考协议下获得补充通过证据，不把历史九场景总分改成 2/9，也不冒充一次新完整 campaign。
