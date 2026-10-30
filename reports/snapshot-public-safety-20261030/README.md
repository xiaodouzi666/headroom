# 公网 Snapshot 安全接入（准备完成，未启用）

本轮只完成代码、离线测试与独立审阅，没有部署或修改服务开关，没有真实模型调用、GPU任务或实际费用。固定 F3b 验收路径继续保留，公网重复上传走新的 SnapshotPublicAllocation。

## 授权与资金

公网 /api/snapshots 必须携带有效评委 Bearer。令牌只是持有凭据，不证明个人身份；无效、空、重复 Authorization 在读取请求体及建立任务前拒绝。/api/config 可公开显示功能表单，并明确 requires_judge_token: true。匿名预设仍使用原 demo 池。

Snapshot 使用服务器选定的原 JudgeAllocation、同一 claims 事务与账本、已有 credit extension，未创建新额度或新池。请求体只能给三份文件，不能指定 funding、预算或 profile。输入内容 size/SHA、原 receipt/profile/数据库身份、claim、截止时间和 strict reservation 在 open/reserve/dispatch 前重验。普通评委训练与 Snapshot 的同池活动 claim 互斥；期限后允许诚实结算。未知费用、清理不明或未结清 claim 会阻止后续调用。采用原本已审核的估算加余量准入，不能称为服务商最终账单的数学硬上界。

## 上传、进程与存储

上传上限为 snapshot 50 MiB、traceback 256 KiB、source 1 MiB，最多三个 receiving/queued/running Snapshot，上传总时限 30 秒，整项队列截止最多 480 秒。有令牌的 Snapshot 无小时次数限制。请求体取消、断连、超限和慢上传会释放 receiving 状态；存储 census 放到线程，取消过程中仍收尾可能已经落库的 admission。

公网 Snapshot 文件和注册库位于 runs/public-api，与现有 jobs/submissions 共用 16 GiB 累计准入、8 GiB 空闲余量和 1 GiB 写入预留。这里是准入保护，不是整个运行期的文件系统硬配额；并发导出和 Snapshot 写入可在锁释放后发生。每个受信任诊断子进程有 128 MiB 单文件内核硬限、2 GiB 地址空间、60 CPU 秒、no_new_privs 与隐藏 CUDA 设备环境。单任务 512 MiB/4096 项采用 supervisor 检查并终止，不能冒充硬目录 quota。清理或账务不确定则停止派发。

上传源码仅作文本，不执行；pickle 沿用 primitive-only opcode 校验与独立资源受限解析子进程。链接、硬链接、FIFO、路径异常和输出超限被拒绝。该路径不是允许任意敌对代码的独立虚拟机；没有宣称共享内核绝对安全。

新公网 manager 不迁移或清理旧 runs/uploads 的 F3b 历史和旧 registry。重启会将新 registry 中断任务标为失败，仅对新公网归属目录执行既有 24 小时保留策略。

## 验证证据

最终四模块 77 passed / 19.86s，见 [final-isolated.log](final-isolated.log)。包含真实 CPU spawn、FSIZE 超限拒绝、no_new_privs、无 CUDA 可见环境、HTTP→子进程→真实临时账本连续两次结算、未知费用阻断，以及原 F3b 兼容测试。测试中的 .02 是合成账本值，实际支出为 0。

资金模块独立 28 passed，见 [资金报告](../snapshot-public-binding-20261030/receipt.json)。中间重跑组有重叠，不把各日志次数相加。首轮旧 launcher 参数断言失败以及后续 launcher 测试泄露临时环境导致九个 F3b 用例失败均原样保留；最终修的是测试 fixture 的环境恢复，没有放宽资金规则。

测试通过 v4 guard，父进程和 spawn 子进程均拒绝真实凭据、生产数据库、DNS、模型网络与 GPU。真实模型及完整 tokenizer/runtime 在 2 GiB cap 下的首次运行仍需后续实际观察，本轮不声称该 live 路径已经成功。离线结果不是新增自动修复成绩。

生产默认开关仍为 false。后续只有服务器显式启用 HEADROOM_SNAPSHOT_SUBMISSIONS_ENABLED=true、训练入口开启且既有 judge allocation 验证成功，launcher 才接入；本轮未执行启用动作。源哈希见 [source-hashes.json](source-hashes.json)，结构收据见 [receipt.json](receipt.json)。

## 首次真实重试后的最小资源适配

根代理第一次真实 s2 重试已结清为 $0/0 calls，保留 failed/runtime_unavailable 历史。随后另一代理只读复现定位：Transformers 自动发现并导入不需要的 PyTorch/CUDA 动态库，在 2 GiB 地址空间限制下映射失败；并不是需要取消资源限制。

现仅在受信任的 Snapshot 子进程将 USE_TORCH、USE_TF、USE_FLAX 设为 0，在首次 tokenizer 导入前禁用框架自动加载。父服务与 GPU Lab 不改变；2 GiB/60 CPU 秒/128 MiB FSIZE/no_new_privs 均保持。真实 CPU spawn 定向测试确认三个框架 availability 全 false，原资源边界仍成立：1 passed / 1.21s，见 worker-tokenizer-only.log。这是对上述77项之后新增代码的单项复验，不累计成新的78项全组结果。新旧源hash均保存在receipt，历史真实失败不改；完整真实模型链仍等待新proposal后单独实测。
