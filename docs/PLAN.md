# Headroom v4.2 — Autoresearch for GPU memory：Codex 开工指令 + 产品定义 + 先例分析 + 逐步执行计划（含验收指标）

- 版本：v4.2，2026-10-23（格罗宁根时间）。v4.1→v4.2：本文件改为**自包含的 Codex prompt**（新增 §0 开工指令与 §G 比赛要求速查），T0.1 改为 Codex 主导，§B 的停止/继续与 push 规则更新。产品定义与 Phase 1–6 任务不变。
- 执行者：Codex（同样适用于 Claude Code）。Frank 的角色：提供无法自动化的账号/密钥、看阶段报告、录视频、提交 Devpost。
- 截止：**2026-10-30 10:00 PT = 10/30 18:00 CET（格罗宁根）= 10/31 01:00 北京**。排期按格罗宁根时间（10/25 03:00 CEST→CET）。
- 目标机器：3090 Ti 单卡机 `azuki`（`ssh -p 40022 xiaodouzi@azuki.ubj.ink`），工作目录 `/home/xiaodouzi/workspace/headroom`。

---

## 0. Codex 开工指令（本文件就是你的 prompt，从这里开始执行）

### 0.1 你是谁、在哪干活
- 你是 Headroom 的唯一开发者。所有开发、运行、测试都必须发生在服务器 `azuki`（RTX 3090 Ti，用户 `xiaodouzi`，工作目录 `/home/xiaodouzi/workspace/headroom`）。
- **文件位置铁律：Frank 的 Mac 磁盘几乎满了（约 3.5 GB 可用）。本项目的一切文件——代码仓库、uv/pip 依赖、Docker 镜像、Hugging Face 模型缓存、显存快照（`*.pickle`）、`runs/`、`web/node_modules`、截图、视频素材——只能存在于服务器 `azuki`，Mac 上不保存任何项目文件、不 clone 仓库、不下载依赖。** 唯一允许进 Mac 的东西是给 Claude 看的报告：每个 Phase 结束时你把 `reports/phase-N-summary.md`、当前 `docs/RESULTS.md`、当前 `PROGRESS.md` 合并成一个纯文本 `reports/handoff-phase-N.md`（<1 MB，不含图片二进制），并在终端打印一条 Frank 可直接执行的拉取命令：`scp -P 40022 xiaodouzi@azuki.ubj.ink:~/workspace/headroom/reports/handoff-phase-N.md ~/Downloads/`。截图只放服务器 `docs/media/`，需要给 Claude 看时在 handoff 里写路径与文字描述。
- 如果你是在 Frank 的 Mac 上运行的：所有命令一律通过 `ssh -p 40022 xiaodouzi@azuki.ubj.ink '<cmd>'` 在服务器执行，必要的小文本文件用 `scp -P 40022` 传，严守上面的文件位置铁律。如果 ssh 不可用或没有凭据，停下告诉 Frank。更推荐 Frank 直接在服务器的 tmux 里运行你（`ssh -t -p 40022 xiaodouzi@azuki.ubj.ink 'tmux new -A -s headroom'` → `cd ~/workspace/headroom && codex`，以允许网络 + 完整文件系统访问的模式）。
- 本项目需要出网：Token Factory、Tavily、GitHub、pip/uv、Hugging Face。

### 0.2 第一步：固化本文件
- 执行 `mkdir -p /home/xiaodouzi/workspace/headroom/docs`。若 `docs/PLAN.md` 不存在，把你此刻看到的本文件**全文原样**保存为 `docs/PLAN.md`（不要改写、不要摘要）。之后一切以 `docs/PLAN.md` 为准；需要修改计划时另写 `docs/PLAN_CHANGES.md` 记录变更与理由，不直接改 PLAN.md。

### 0.3 项目一句话（给你的上下文）
Headroom：输入一个会 OOM 或浪费显存的 PyTorch 脚本和一个显存预算，它在本机 GPU 上开启 allocator 历史运行脚本，在 OOM/峰值时刻抓取完整显存快照，压成证据包整份交给 Nebius Token Factory 上的 NVIDIA Nemotron 3 Ultra（1M 上下文）做根因诊断与修复规划，用 Nemotron 3 Super 写补丁，同种子重跑验证（不再 OOM、峰值、step 时间、loss 等价），keep-or-revert 搜索修复组合直到达到预算，输出补丁 + 显存-吞吐 Pareto 前沿 + 前后证据报告；Tavily 负责查所用 API/flag 在当前 PyTorch 版本的文档。参赛 Nebius x NVIDIA Global AI Hackathon，Coding and Agentic Engineering 赛道。细节见 §A–§C。

### 0.4 执行顺序
1. 通读全文（§A–§G）。
2. 建 `PROGRESS.md`：列出 §E 全部任务编号，状态初始为「未开始」。
3. 从 **T0.1 开始**（T0.1 由你主导：能自动化的你做，不能的生成清单让 Frank 提供），然后 T0.2 → T0.3 → … 严格按 §B 的验收制推进。
4. 开场先用 ≤15 行汇报你对任务清单的理解，然后立刻开始 T0.1。

### 0.5 硬性纪律（违反任何一条视为任务失败）
- **Git**：author/committer 只用 Frank 在服务器上已配置的 git 身份；commit message 不加任何 AI 署名或 `Co-authored-by`；每次 commit 前运行 `gitleaks detect`，必须 0 findings。Frank 已授权你对 `headroom` 这一个仓库 push（见 §B.4），其他仓库一律不 push。
- **密钥**只能存在于 `.env`（权限 600，已 gitignore）；仓库只放 `.env.example`；日志、报告、PROGRESS.md、对话回显里不得出现 key 的明文（只显示前 6 位 + `…`）。
- **用户脚本一律在 Lab 沙箱里运行**（子进程或 Docker，`--network none`，工作目录隔离，不传入 API key）；Headroom 自身不在 GPU 上训练任何东西。
- **GPU 是共享单卡**：显存峰值指标不受影响；比较 step 时间前检查 `nvidia-smi`，有其他进程则标记 `shared_gpu=true`；不要 kill 别人的进程。
- **所有 LLM 调用必须走 Token Factory**（§C.1 的 base_url 与模型 ID），不得用任何其他 provider。
- **补丁不得通过缩小模型、截断训练来"达标"**（T1.10 的 Honesty 检查）。
- 不做计划之外的"顺手优化"；计划与现实冲突时按 §F 裁剪并记录到 `docs/PLAN_CHANGES.md`。
- **需要花钱、开放端口、删除数据、偏离计划时：停下**，在 `PROGRESS.md` 的「待 Frank 决策」区写清问题与建议方案，等待 Frank。

### 0.6 停止 / 继续规则
- Phase 1 的 T1.12 验收完成后：写 `reports/phase-1-summary.md`。若 MVP 通过线达标 → **直接继续 Phase 2 的 P0 任务**（T2.1、T2.2、T2.4、T2.8），不必等 Frank；若未达标 → 按 §F 第一条最多再修 3 轮，仍不达标则停下等 Frank。
- Phase 2 结束写 `reports/phase-2-summary.md` 后继续 Phase 3 的 T3.1–T3.3（不需要 Frank 的部分）；T3.5 公网部署需要 Frank 提供域名/Cloudflare 权限，到此停下等他。
- Phase 4 评测可在 Frank 不在时夜间自治运行（§B.4 的自治规则）。Phase 5 中 README/RESULTS/FEEDBACK/DEVPOST 初稿由你写，视频与 Devpost 提交由 Frank 做。
- 每个 Phase 结束的 summary 都要同时输出到终端（Frank 可能只看终端）。

---

## A. 产品定义

### A.1 一句话
**Headroom is autoresearch for GPU memory.** Give it a PyTorch training or inference script and a memory budget ("fit this on 24 GB", "cut peak memory 40%"). It runs the script on a real GPU with allocator history on, captures the full memory snapshot at the point of failure or peak, hands the entire evidence pack to NVIDIA Nemotron 3 Ultra's 1M-token context on Nebius Token Factory, and then *searches* — proposing combinations of memory techniques (checkpointing granularity, precision per tensor class, optimizer variants, batch/grad-accumulation, allocator settings, sequence bucketing, chunked losses, offloading), writing each as a patch with Nemotron 3 Super, re-running under the same seed to verify no OOM, peak memory, step time and loss equivalence, keeping what works and reverting what doesn't — until it hands you the memory-vs-throughput Pareto frontier and the patch that meets your budget, with before/after evidence and the PyTorch docs it consulted via Tavily. Nobody has built an agent whose objective is memory; existing autoresearch loops (AutoKernel) optimize speed.

### A.2 用户故事
> 我在一张 24GB 卡上微调一个 1B 模型，`torch.OutOfMemoryError`。我把脚本（或仓库 + 命令）交给 Headroom，选目标"fit on 24 GB, keep numerics"。几分钟后：它告诉我峰值 31.4GB 里 14GB 是 fp32 AdamW 状态、9GB 是没做 checkpointing 的激活、2.1GB 是碎片（reserved 比 allocated 多），给我一个三处改动的补丁（bf16 autocast + 激活 checkpointing + `expandable_segments`），已经同种子跑了 20 步：峰值 17.9GB、step 慢 11%、loss 曲线与 CPU 参考一致。我 `git apply` 就能继续训练。

### A.3 输入 / 输出
- 输入：Python 脚本路径或仓库路径 + 启动命令；目标（`fix-oom` | `fit <GB>` | `reclaim`（在不回归前提下尽量降峰值））；策略开关（允许改变数值精度？允许吞吐下降上限？允许改 batch/grad-accum？）；可选 `headroom.yaml`。
- 输出：`patch.diff`（可 `git apply`）、`env.sh`（allocator/环境变量变更）、`report.md` + `report.json`（根因、证据、每轮修复与验证结果、前后对比、Sources）、`evidence/`（快照、证据包、时间线图）、结构化记录（SQLite）。

### A.4 先例与差异（README "Related work" 必须如实写）
| 现有 | 做什么 | Headroom 的不同 |
|---|---|---|
| PyTorch `memory_viz` / `torch.cuda.memory._snapshot` | 给人看的快照可视化 | Headroom 让模型读完整快照并据此修代码 |
| 博客/指南/"OOM 诊断" agent skills（Claude 插件等） | 静态清单、通用建议 | 证据驱动（快照 + 栈）、自动打补丁、真实重跑验证、迭代到目标 |
| GPU-Boost（静态分析 + 建议补丁，不执行不验证） | 静态模式匹配 | 运行时证据、验证闭环、allocator 级修复、数值等价检查 |
| NeMo Megatron-Bridge memory-snapshot skill | 供人用的快照解析脚本 | 自动化端到端 + 适用任意脚本 |
| loadtune（DataLoader 参数调优） | 吞吐/数据管线 | 显存根因与修复 |
| AutoKernel / Karpathy autoresearch（keep-or-revert 循环） | 目标是速度/val loss | Headroom 是第一个以**显存**为目标的 autoresearch 循环，且以快照为证据 |
| Checkmate / ZeRO-Offload / Mist / Galvatron（研究：最优 checkpointing、卸载、并行规划） | 分布式训练编译器/规划器层面，需要用户按其框架改写模型 | 作用于任意用户脚本，补丁可读可审，GPU 在环验证数值等价 |
- 定位结论（README 原话可用）：**No existing tool reads a full CUDA memory snapshot, diagnoses it, patches the script, verifies on hardware and iterates to a memory budget. The pieces exist as human-facing visualizers, static linters and prompt skills; the autonomous, verified loop does not.**

### A.5 对照评分标准
| 标准 | 评委问什么 | Headroom 的回答 |
|---|---|---|
| Technological Implementation（平局首项） | 多有效地用 Token Factory + Nemotron | Ultra 1M 上下文读整份证据包（几十万 token 的机器证据，不是文档）+ Token Budget 控制推理成本；Super 写补丁/写验证脚本；Nano 批量标注分配栈类别；tool calling 调 Tavily；真实 GPU 运行、沙箱、确定性等价检查；全链路 token/cost 透明 |
| Design | 完整产品 | 粘脚本/选示例 → 目标与策略 → 实时时间线 → 前后显存时间线图 → 峰值组成（栈树）→ 诊断卡（证据引用）→ 补丁 diff → 验证表 → 下载；CLI；Replay |
| Potential Impact | 真实受众与问题，demo 能证明 | 受众：所有 PyTorch 用户，尤其 24GB 消费卡；问题：OOM 调试吃掉工程师小时与 GPU 小时，显存浪费限制 batch/吞吐；证明：12+ 场景的解决率与峰值降幅、消融证明"完整快照 + 1M 上下文"的价值 |
| Quality of the Idea | 非显而易见、懂问题域 | 把 1M 窗口用于机器证据而非长文档；第一个以显存为目标的 autoresearch（keep-or-revert）循环，输出显存-吞吐 Pareto 前沿而非单一建议；allocator（碎片、expandable_segments、max_split_size_mb）级别的诊断；数值等价与吞吐代价一起报告 |
| Bonus: Tavily | 运行时真实调用且有机 | 为每个拟采用的修复查当前 PyTorch 版本的 API/flag 文档与已知 issue（如 `use_reentrant=False`、`expandable_segments`、FSDP 参数），引用进报告 |

### A.6 GPU
需要一张 CUDA GPU（RTX 3090 Ti，24GB）：运行用户脚本、抓快照、验证。不跑本地 LLM。**显存指标是确定性的，GPU 被其他进程占用不影响峰值数字**（只影响 step 时间，harness 对此标记 `shared_gpu=true`）。12 月评审期机器保持在线。

### A.7 范围
- MVP（v1）：CLI `headroom fix <script.py> [--target fit:20GB]`；单 GPU；子进程隔离（Docker 可行则用）；证据包 + Ultra 诊断 + Super 补丁 + 验证重跑 + 报告；8 个合成场景 + 1 个真实仓库（nanoGPT）。
- v2：多轮求解循环、Tavily、Nano 栈标注、预算守卫、Docker、HF Trainer 场景、Watch 模式（包装任意命令，OOM 时自动触发）。
- v3：Web UI + API + Replay + 公网 + 评测（场景集 + 消融）+ 提交包。
- 不做：多 GPU/分布式（FSDP/DeepSpeed 只作为建议方向）、非 PyTorch 框架、本地模型。

---

## B. 给 Codex 的工作协议
1. 通读本文件；建 `PROGRESS.md`（全部任务编号，状态 `未开始`，末尾留「待 Frank 决策」与「Frank 待办」两个区块）；从 T0.1 开始（Codex 主导，见 T0.1）。
2. **验收制**：每个任务按「验收指标」逐条执行，命令与输出摘要写入 `PROGRESS.md`，状态改 `已验收` 后才开始下一任务。新会话先重跑上一任务验收命令。
3. **停止/继续**：按 §0.6 执行；每个 Phase 结束写 `reports/phase-N-summary.md` 并同时打印到终端。
4. **Git**：author/committer 只用 Frank 在服务器上已配置的身份（`git config user.name/user.email` 必须已存在，否则停下问 Frank）；commit message 不加 AI 署名；**仅对 `headroom` 仓库允许 push**（Frank 已授权；用服务器上已有的 `gh auth` 或 Frank 提供的 deploy key），其他仓库一律不 push；每次 commit 前 `gitleaks detect` 0 findings；每个 Phase 结束至少 push 一次，让 Frank 能在 GitHub 上看进度。
5. **Secrets** 只在 `.env`（600，gitignored）；仓库只有 `.env.example`。
6. **自治边界**：花钱、开端口、删数据、改方案 → 停下写 `PROGRESS.md` 等 Frank。
7. **运行模式**：需要出网（Token Factory、Tavily、GitHub、pip、HF 模型下载）。Codex 以允许网络与完整文件系统访问的模式运行。
8. 持续维护 `docs/FEEDBACK.md`（Token Factory / Ultra / Super / Nano / Tavily 的真实体验，具体到参数、文档页、报错）与 `docs/RESULTS.md`（所有数字含失败 + 复现命令）。
9. 用户脚本一律在 Lab 沙箱（子进程/Docker，`--network none`，工作目录隔离）里运行；Headroom 自身代码不在 GPU 上做任何训练。
10. **所有文件只放服务器**（§0.1 文件位置铁律）；Mac 上只出现每个 Phase 的 `handoff-phase-N.md` 纯文本报告，由 Frank 用你打印的 scp 命令拉取后转给 Claude。每个 Phase 结束，`reports/handoff-phase-N.md` 与 scp 命令是必交付物（计入该 Phase 的验收）。

---

## C. 技术规格速查

### C.1 Token Factory（OpenAI 兼容）
- Base URL：`https://api.tokenfactory.us-central1.nebius.com/v1/`（Nemotron 3 所在区域）；默认区域 `https://api.tokenfactory.nebius.com/v1`。`GET /v1/models?verbose=true` 以实测为准。
- 角色 → 模型：
  - **Diagnostician / Planner**：`nvidia/Nemotron-3-Ultra-550b-a55b`（1M ctx；$1.00/$3.00 per 1M；reasoning + tool calling；支持 Token Budget 控制推理 token——实测参数名）
  - **Patcher / Verifier-script writer**：`nvidia/nemotron-3-super-120b-a12b`（$0.30/$0.90；structured output + function calling）
  - **Stack annotator / Summarizer**：`nvidia/nvidia-nemotron-3-nano-30b-a3b`（备选 `nvidia/Nemotron-3_5-Lightning`，1M ctx）
- **必须在 T0.4 实测 Ultra 在 Token Factory 上的真实最大输入长度**（分别发 64k / 200k / 500k / 900k token 的填充提示，记录成功/报错/延迟/费用），证据包的默认 token 预算据此设定（目标 ≤ 实测上限的 60%）。
- reasoning 开关候选：`extra_body={"chat_template_kwargs":{"enable_thinking":True|False}}`；system 首行 `/think` 或 `/no_think`；`extra_body={"reasoning_effort":...}`；Token Budget 候选：`extra_body={"reasoning_budget": N}` 或 `max_thinking_tokens`（实测）。
- structured output 候选：`response_format={"type":"json_object"}` → `json_schema` → 围栏 + 容错解析。
- 重试：429/5xx 指数退避 1/2/4/8/16s ≤5 次；超时 Ultra 600s（长输入）、其他 120s。成本 = usage × pricing。

### C.2 Tavily
`pip install tavily-python`；`search(query, search_depth, max_results)`、`extract(urls)`；免费 1,000 credits/月；每次 run ≤4 次；同 query 24h 缓存。

### C.3 Lab：运行用户脚本并抓证据
- 包装器 `headroom/lab/run_target.py`（在沙箱子进程中执行）：
  1. 设置 `PYTORCH_CUDA_ALLOC_CONF`（来自当前策略）；`torch.cuda.memory._record_memory_history(max_entries=200_000)`。
  2. **Step 计数与截断**：monkeypatch `torch.optim.Optimizer.step`（记录每步后 `max_memory_allocated/reserved`、墙钟；达到 `--max-steps`（默认 20）抛 `StepLimitReached`）；对无 optimizer 的推理脚本用 `--max-seconds`（默认 120）。
  3. **Loss 序列**：monkeypatch `torch.Tensor.backward`，若张量 `numel()==1` 记录 `float(t)`（即 loss）；得到 `loss_series`。
  4. `runpy.run_path(script, run_name="__main__")`（或 `subprocess` 运行用户命令 + `sitecustomize` 注入同样的 hook；两种模式都支持）。
  5. 捕获 `torch.OutOfMemoryError`（旧版 `torch.cuda.OutOfMemoryError`）：立即 `torch.cuda.memory._snapshot()` → `snapshot.pickle`；记录 `memory_stats()`、`memory_summary()`、traceback、OOM 请求字节数、`nvidia-smi` 快照、环境（torch/cuda/driver 版本、`PYTORCH_CUDA_ALLOC_CONF`）。
  6. 非 OOM（`reclaim` 模式或验证运行）：在 `StepLimitReached` 时同样抓快照（峰值证据）。
  7. 输出 `result.json`：`{status: "oom"|"completed"|"error"|"timeout", steps, peak_alloc_gb, peak_reserved_gb, step_ms_median, loss_series, oom:{requested_gb, free_gb, traceback}, shared_gpu, env}`。
- 隔离：`--network none`（Docker）或子进程 + 环境变量白名单（不传 API key）；工作副本（`git worktree`/复制）；超时 kill 进程组；`--read-only` 用户源码目录，只允许写 `run_dir`。
- 模型权重下载（HF）在沙箱外预先完成（`HF_HOME` 缓存只读挂载）。

### C.4 证据包（Evidence Pack）
`headroom/evidence.py` 解析 `snapshot.pickle`（`segments[].blocks[]`、`frames`、`device_traces[]`），生成分层 Markdown/JSON，受 token 预算控制（默认 150k，可调）：
1. **Header**：GPU、torch/cuda 版本、allocator 配置、目标与策略、OOM 请求/可用、峰值 allocated/reserved、碎片（reserved−allocated、最大空闲块 vs 请求）。
2. **Timeline**：按事件桶（200 桶）给出 allocated/reserved 曲线（文本表 + PNG 供报告）；标出 optimizer step 边界与 OOM 点。
3. **Peak composition**：峰值时刻存活块按**折叠栈签名**聚合，Top-40（字节、块数、代表性栈：过滤到用户代码帧 + 关键库帧 `backward/autograd/optimizer/nn.Module.__call__`）；类别启发式：params / grads / optimizer_state / activations / temporaries / cache / unknown。
4. **Allocation hot paths**：按分配字节总量 Top-20 栈；短寿命大块（temporaries）识别。
5. **Source**：用户脚本全文 + 被其引用的本地模块（总量 ≤ 预算的 30%），带行号。
6. **Nano 标注（P1）**：对 Top-40 栈由 Nano 产出一行类别/解释，附在条目后。
- 预算裁剪顺序：先减少 Top-N，再截断源码非热点区域，最后压缩时间线桶数。

### C.5 诊断 / 计划 / 补丁 / 验证
- **Diagnose（Ultra）** 输出 JSON：`{root_causes:[{id,title,category,bytes_gb,evidence_refs:[stack_ids],confidence}], plan:[{fix_id,type:"code"|"config"|"env",title,description,expected_saving_gb,numerics_impact:"none"|"minor"|"significant",throughput_impact:"none"|"minor"|"major",risk,requires_policy:[...]}], verification:{max_steps, compare_loss:bool, tolerance}, needs_more_info:bool, notes}`；计划须满足用户策略（如 `allow_numerics_change=false` 时不得提 bf16）。
- **Patch（Super）**：输入计划步骤 + 相关源码片段（带行号）→ 输出统一 diff（相对工作副本）+ `env_changes`（字典）+ `cli_changes`（可选）；`git apply --3way`；`python -m py_compile`；失败 → Patch-fixer ≤3 次。
- **Verify（Lab）**：同种子（harness 在包装器里设 `torch.manual_seed`、`random`、`numpy` 种子）、`--max-steps 20` 跑补丁版：`status`、`peak_alloc_gb`、`peak_reserved_gb`、`step_ms`、`loss_series`；与基线比较：
  - 若基线 OOM：要求补丁版 `completed`，loss 有限且首末下降，且**与"小 batch 参考运行"（harness 自动把 batch 缩到能跑的最小值作为 numerics 参考，仅当脚本的 batch 可通过 `--batch`/配置发现时）**的 loss 前 5 步差值 ≤ 容差（numerics_impact=none 的修复）；否则只报告。
  - 若基线可跑（reclaim）：`max|Δloss| ≤ 1e-3`（fp32）/`≤ 2e-2`（bf16 改动须标注 `numerics changed`）；`peak_alloc` 降幅 ≥ 目标；`step_ms` 增幅 ≤ 策略上限（默认 25%）。
- **Loop**：Ultra 读验证结果决定继续/停止；最多 4 轮；达标即停；预算守卫。
- **Report**：Summary（目标、达成、峰值 before/after、吞吐变化、数值等价）/ Root causes（证据引用）/ Fixes（每轮 diff 摘要 + 验证表）/ Timeline 图 before/after / Allocator notes / Sources（Tavily）/ Model usage & cost。

### C.6 事件类型
`run.started, baseline.started, baseline.oom, baseline.completed, evidence.built, annotate.done, diagnose.started, diagnose.done, research.called, research.done, patch.written, patch.applied, patch.failed, verify.started, verify.done, round.done, target.met, budget.exceeded, run.done, run.failed, needs_human`。

### C.7 仓库结构
```
headroom/
├── LICENSE(Apache-2.0) README.md pyproject.toml .env.example .gitignore .pre-commit-config.yaml PROGRESS.md
├── headroom/
│   ├── cli.py            # fix / reclaim / report / replay / usage / snapshot / evidence
│   ├── config.py  schemas.py  orchestrator.py  report.py
│   ├── lab/{runner.py, docker.py, run_target.py, hooks.py, envs.py}
│   ├── evidence.py  timeline_plot.py
│   ├── llm/{client.py, router.py, cost.py}
│   ├── prompts/{diagnose.md, patch.md, patch_fix.md, annotate.md, summarize.md}
│   ├── research/tavily_tool.py
│   ├── verify/{compare.py, policy.py}
│   ├── store/{db.py, models.py}
│   └── api/ (Phase 3)
├── scenarios/            # 合成 OOM/浪费场景脚本（每个带 README 与真值根因）
├── repos/                # 真实仓库场景的 pin（nanoGPT 等，脚本自动 clone）
├── eval/{scenario_set.yaml, run_eval.py, ablations.py}
├── lab-image/Dockerfile (Phase 2)   web/  design/  deploy/  docs/  reports/  tests/  scripts/
```

---

## D. 排期总览（格罗宁根时间）
| 日期 | Phase | 目标 |
|---|---|---|
| 10/23 周五 | Phase 0 + Phase 1 前半（T1.1–T1.6） | 环境/账号/探测（含 Ultra 最大输入实测）；场景集；Lab 包装器抓快照；证据包；Ultra 诊断 |
| 10/24 周六 | Phase 1 后半（T1.7–T1.12） | 补丁、验证、单轮闭环、DB/CLI/报告；**MVP 验收** |
| 10/25 周日 | Phase 2（T2.1–T2.8） | 多轮求解、Tavily、Nano 标注、预算、Docker、真实仓库、Watch（P2）、小评测（夜间） |
| 10/26 周一 | Phase 3 前半 | FastAPI+SSE、前端素版、Replay |
| 10/27 周二 | Phase 3 后半 + Phase 4 | 公网/限流/监控；评测战役 + 消融（夜间） |
| 10/28 周三 | Phase 5 | README/RESULTS/FEEDBACK/Devpost/视频；**首次完整提交** |
| 10/29 周四 | Phase 5 | 自检、干净环境复跑、再提交 |
| 10/30 周五 | 最终 | 15:00 CET 前定稿（截止 18:00 CET） |

---

## E. 任务清单（逐步 + 验收指标）
> 字段：目的 / 做什么 / **验收指标**。P0 = MVP 必需；P1 = 加分；P2 = 富余再做。

### Phase 0 — 准备（10/23 上午，~4h）

#### T0.1 账号、额度、密钥、仓库（P0，Codex 主导，Frank 只补无法自动化的部分，~40min）
- 做什么（按顺序）：
  1. **检查现状**：`test -f ~/workspace/headroom/.env` 并检查是否含 `NEBIUS_API_KEY`、`NEBIUS_BASE_URL`、`TAVILY_API_KEY`；`gh auth status`；`git config --global user.name && git config --global user.email`；`gh repo view <frank-github-username>/headroom` 是否存在。
  2. **GitHub 仓库（你来做）**：若 `gh auth status` 正常且仓库不存在：`gh repo create headroom --public --description "Autoresearch for GPU memory: an agent that reads full CUDA memory snapshots, patches your PyTorch script and verifies on hardware. Built on NVIDIA Nemotron 3 via Nebius Token Factory." --license apache-2.0 --clone=false`，然后在本地 `git init` + `git remote add origin <url>`；把 Apache-2.0 全文放在根目录 `LICENSE`。若 `gh` 未登录：在 `PROGRESS.md`「Frank 待办」写明两种方案（a. 在服务器运行 `gh auth login`；b. 自己在网页建公开仓库 `headroom` 并选 Apache-2.0 LICENSE，然后把 URL 贴给你）。
  3. **无法自动化的账号（生成清单给 Frank，原样打印到终端）**：
     - Devpost：注册并在 https://nebiusglobalaihackathon.devpost.com/ 点 "Join hackathon"。
     - Token Factory：在 https://tokenfactory.nebius.com 开户 → 填促销表 https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 （激活码 `NEBIUS-DEVPOST-GLOBAL26`，$25）→ 加入 Builders Program https://dev.nebius.com/builders （再 $25）→ 在控制台创建 API key → 把 key 贴到本对话。
     - Tavily：https://tavily.com 注册 → 取 `tvly-…` key → 贴到本对话。
     - 可选 HF_TOKEN（下载需授权的模型时才需要）。
     清单打印后**不要空等**：转去做 T0.2、T0.3、T0.6（不依赖密钥），Frank 贴来 key 后再回来完成下面第 4 步。
  4. **写 `.env`（你来做）**：收到 key 后写入 `~/workspace/headroom/.env`（`NEBIUS_API_KEY=…`、`NEBIUS_BASE_URL=https://api.tokenfactory.us-central1.nebius.com/v1/`、`TAVILY_API_KEY=…`、可选 `HF_TOKEN=…`），`chmod 600 .env`，确认 `.gitignore` 含 `.env`；对话里回显时只显示前 6 位。
- 验收：`set -a; source .env; set +a; curl -s -H "Authorization: Bearer $NEBIUS_API_KEY" "$NEBIUS_BASE_URL/models" | grep -ci nemotron` ≥3；`curl -s -X POST https://api.tavily.com/search -H "Content-Type: application/json" -d "{\"api_key\":\"$TAVILY_API_KEY\",\"query\":\"triton language dot\",\"max_results\":1}" | grep -c results` ≥1；`gh repo view <user>/headroom --json licenseInfo -q .licenseInfo.name` 输出含 `Apache`；`stat -c %a .env` 为 `600`；Frank 在 Token Factory 控制台确认余额 ≥$25（他回复"额度已到"即可，截图可选）。

#### T0.2 服务器环境勘察（P0，~30min）
- 做什么：`docs/ENV.md` 记录：`nvidia-smi`（驱动/CUDA/显存/占用进程）、`lsb_release -a`、`df -h ~`、`free -g`、`python3 --version`、`which uv docker git`、`docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`、`sudo -n true && echo SUDO_OK || echo NO_SUDO`、出网 `curl -sI https://huggingface.co | head -1`、磁盘可用空间（HF 缓存需 ≥30GB）。
- 验收：每条有原始输出；结论 `DOCKER_GPU=ok|needs_install|unavailable`、`NET=ok`、`DISK_FREE_GB=<n>`；非 ok 写入 `PROGRESS.md`。

#### T0.3 仓库骨架与工具链（P0，~40min）
- 做什么：按 C.7 建目录；`uv init --package headroom`；`uv add torch openai tavily-python typer rich sqlmodel pydantic httpx python-dotenv matplotlib gitpython unidiff`，`uv add --dev pytest ruff pre-commit`（torch 版本对应 CUDA；需 torch ≥ 2.5 以获得 `torch.OutOfMemoryError` 与完整快照 API）；pre-commit（ruff、ruff-format、gitleaks）；`.env.example`；`.gitignore`（`.env`、`*.db`、`runs/`、`*.pickle`、`web/node_modules`）；`PROGRESS.md`；首个 commit。
- 验收：`uv run python -c "import torch;print(torch.__version__,torch.cuda.is_available(),torch.cuda.get_device_name())"` 含 `True` 与 `3090 Ti`；`uv run python -c "import torch;torch.cuda.memory._record_memory_history();x=torch.randn(1024,1024,device='cuda');s=torch.cuda.memory._snapshot();print(len(s['segments'])>0, 'device_traces' in s)"` 输出 `True True`；`uv run pre-commit run --all-files` 全 Passed；`git log -1 --format='%an <%ae>'` 为 Frank；`gitleaks detect` 0。

#### T0.4 Token Factory 探测（P0，~1h）
- 做什么：`scripts/probe_models.py`：两个 base_url 的 `GET /v1/models?verbose=true` → `docs/MODELS.md`；Ultra/Super/Nano（及 Lightning）：普通对话、JSON 三种方式、tool calling、reasoning 开/关三种方式、Token Budget 参数；**Ultra 长输入阶梯测试**：64k / 200k / 500k / 900k token 的填充提示（在末尾放一个"针"要求复述），记录成功/报错信息/首字延迟/总时长/费用；并发 4 路 Super 的 429/延迟。
- 验收：`docs/MODELS.md` ≥3 个 `nvidia/` 模型含价格；能力矩阵（chat/json/tools/reasoning_toggle/token_budget）每格为 `ok(method=...)` 或 `fail(error=...)`，Super 的 json 与 tools 各至少一种 ok；**长输入表**写明 Ultra 在 Token Factory 的实测可用最大输入（`ULTRA_MAX_INPUT_TOKENS`）与 500k 级请求的延迟/费用；`headroom/config.py` 的模型 ID、`REASONING_METHOD`、`JSON_METHOD`、`EVIDENCE_TOKEN_BUDGET=min(150k, 0.6×ULTRA_MAX_INPUT_TOKENS)` 与实测一致；`docs/FEEDBACK.md` 新增 ≥5 条。

#### T0.5 Tavily 探测（P1，~15min）
- 验收：`scripts/probe_tavily.py` 退出码 0（search basic/advanced 各 1；extract：PyTorch `torch.utils.checkpoint` 文档页 + 一个 pytorch GitHub issue）；`docs/FEEDBACK.md` 新增 2 条；`docs/TOOLS.md` 定义返回 schema。

#### T0.6 场景集 v0（P0，~2h）
- 做什么：`scenarios/` 建 8 个合成场景（每个含 `train.py`、`README.md`（真值根因、预期修复类别、预期峰值）、可选 `headroom.yaml`），均在 24GB 上 OOM 或明显浪费，模型用随机初始化的小型 Transformer/MLP/ViT 以免下载权重（nanoGPT 结构即可）：
  1. `s1_batch_too_big`：激活爆炸 → grad accumulation / checkpointing
  2. `s2_fp32_adamw_1b`：fp32 全参数 + AdamW 状态 → bf16 autocast + 8-bit/fused 优化器建议（真值：优化器状态占比）
  3. `s3_eval_no_grad_missing`：评估循环没 `torch.no_grad()`
  4. `s4_loss_accumulation_graph`：`total_loss += loss`（未 `.item()`）保留计算图
  5. `s5_fragmentation_varlen`：变长序列反复 alloc/free → `expandable_segments:True` + 长度分桶
  6. `s6_full_vocab_logits_fp32`：大词表 logits fp32 物化 → 分块 CE / 不 `.float()`
  7. `s7_frozen_params_optimizer_state`：冻结参数仍进优化器 / `requires_grad` 未关
  8. `s8_two_models_resident`：不需要的第二模型/参考模型常驻 GPU → 卸载到 CPU / 按需加载
  另加 `repos/nanogpt.yaml`：pin `karpathy/nanoGPT` 某 commit，`train.py` 配置使 24GB OOM（如 `--batch_size=32 --block_size=1024 --n_layer=24 --n_embd=1024`），目标 `fit:22GB`。
- 验收：8 个脚本直接运行均在 60s 内 OOM（或 `reclaim` 场景在 20 步内完成且峰值被 README 记录）；每个 README 含真值根因与预期修复类别；`scenarios/INDEX.yaml` 列全；nanoGPT 配置在本机复现 OOM（记录 traceback 到 `repos/nanogpt.oom.txt`）。

### Phase 1 — MVP 核心闭环（10/23 下午 – 10/24 晚，~18h）

#### T1.1 Lab 包装器：运行并抓证据（P0，~3h）
- 做什么：按 C.3 实现 `lab/run_target.py` + `lab/hooks.py`（Optimizer.step 计数与峰值记录、Tensor.backward loss 捕获、种子设置、OOM 捕获与快照落盘）；`lab/runner.py`（子进程、超时、环境白名单、`result.json` 协议）；`headroom snapshot <script.py> [--max-steps 20]` 命令。
- 验收：对 `s1`：`result.json.status == "oom"`，`snapshot.pickle` 存在且 `len(snapshot['device_traces'][0]) > 1000`，`oom.requested_gb > 0`，`traceback` 含 `OutOfMemoryError`；对 `s3`（改小 batch 使其可跑）：`status == "completed"`，`steps == 20`，`loss_series` 长度 ≥ 20；`tests/test_runner.py`：死循环脚本 30s 超时 `TIMEOUT` 无残留进程；子进程内 `NEBIUS_API_KEY` 为 `None`；同种子两次运行 `loss_series` 前 5 步完全一致（确定性）。

#### T1.2 证据包生成（P0，~3h）
- 做什么：按 C.4 实现 `evidence.py`（解析、聚合、类别启发式、预算裁剪）与 `timeline_plot.py`（PNG）；`headroom evidence <run_id> [--budget 150000]`。
- 验收：对 `s1/s2/s4/s5` 的快照均生成 `evidence.md` 与 `evidence.json`；token 数（用 tiktoken `cl100k_base` 近似）≤ 预算的 105%；`s2` 的 Peak composition 中 `optimizer_state` 类别字节 ≥ 总峰值的 40%（与真值一致）；`s4` 的 Top 栈能定位到 `train.py` 中 `total_loss +=` 所在行；`s5` 的 Header 显示 `reserved - allocated ≥ 1GB` 且碎片标记为 `high`；`tests/test_evidence.py` 用小合成快照覆盖聚合与裁剪逻辑；PNG 时间线存在且标出 OOM 点。

#### T1.3 LLM 客户端与路由（P0，~1.5h）
- 做什么：`llm/client.py`（OpenAI SDK、base_url、超时、重试、usage/cost 记账、reasoning/Token Budget 注入）；`llm/router.py`（`chat(role, messages, json_schema=None, tools=None, ...)`；JSON 容错解析）；`prompts/` 文件化。
- 验收：mock 测试覆盖路由/重试/成本；真实调用 Super 返回 schema 合法 JSON；真实调用 Ultra 一次 200k token 输入（证据包）成功并记录延迟与费用到 `docs/FEEDBACK.md`。

#### T1.4 Diagnose（Ultra）（P0，~2.5h）
- 做什么：`prompts/diagnose.md`（角色：PyTorch 内存专家；输入：证据包 + 目标 + 策略 + 环境；输出 C.5 JSON；要求每个根因引用 `stack_ids`，计划按预期节省排序并标注数值/吞吐影响；禁止违反策略）；schema 校验与规则后处理（引用的 stack_id 必须存在；`expected_saving_gb` 之和 ≥ 需要削减的量，否则要求补充）。
- 验收：8 个合成场景的诊断中 **≥6/8 的首要根因类别与 README 真值一致**（表格记录）；每个根因均有 ≥1 个有效 `stack_ids`；单次 Ultra 调用 cost ≤ $0.35（150k 输入）；`tests/test_diagnose_schema.py` 通过。

#### T1.5 Patch（Super）与应用（P0，~2.5h）
- 做什么：`prompts/patch.md`（输入：计划步骤、相关源码片段（带行号）、约束（最小改动、保持接口、添加注释说明理由）→ 输出：统一 diff + `env_changes` + `cli_changes`）；`patch_fix.md`（apply/compile 失败修复）；`verify/policy.py`（检查补丁不违反策略，如禁止 bf16 时 diff 不得含 `autocast`/`bfloat16`）。
- 验收：对 8 个场景按各自诊断计划生成补丁：**≥6/8 `git apply --3way` + `py_compile` 一次或经 ≤3 次修复后成功**；策略测试：`allow_numerics_change=false` 下 `s2` 的补丁不含 `autocast`（policy 检查拦截并要求重出）；每次 Super 调用 `completion_tokens ≤ 4000`。

#### T1.6 Verify 与比较（P0，~2h）
- 做什么：`verify/compare.py`：按 C.5 比较基线与补丁运行；小 batch 参考运行（当 `headroom.yaml` 或脚本 argparse 暴露 batch 参数时自动尝试）；输出 `VerifyReport {completed, peak_before, peak_after, reduction_pct, step_ms_before, step_ms_after, loss_equivalence: "identical"|"within_tol"|"changed"|"n/a", target_met, notes}`。
- 验收：`s1` 补丁后 `completed=true`、`peak_after < 24GB`、`loss_equivalence ∈ {identical, within_tol}`（grad accumulation + checkpointing 为数值保持型）；`s3` 补丁后 `reduction_pct ≥ 30`；人为给 `s1` 一个"把模型层数减半"的假补丁 → loss 偏差超容差被判 `changed` 且 `target_met=false`（防止"靠改模型过关"）；`tests/test_compare.py` 覆盖四种等价状态。

#### T1.7 单轮编排 + 存储 + 事件（P0，~2h）
- 做什么：`orchestrator.py`：baseline → evidence → diagnose → patch → verify → report（单轮，Phase 2 扩为多轮）；SQLModel 表 `runs / rounds / events / llm_calls / research`；rich 时间线；`headroom fix <script> [--target fit:22GB|fix-oom|reclaim] [--allow-numerics-change] [--max-steps 20] [--budget 0.6]`。
- 验收：`uv run headroom fix scenarios/s1_batch_too_big/train.py --target fix-oom` 退出码 0，终端时间线含 `baseline.oom → evidence.built → diagnose.done → patch.applied → verify.done → run.done`；`events` ≥ 15 行，`llm_calls` ≥ 2；`headroom usage` 与 `sum(cost_usd)` 一致。

#### T1.8 报告（P0，~1.5h）
- 做什么：`report.py` 渲染 `report.md`（C.5 结构）+ 内嵌 before/after 时间线 PNG + 峰值组成表 + diff + 验证表 + 模型用量；`headroom report <run_id>`、`headroom replay <run_id>`。
- 验收：`grep -c '^## ' report.md` ≥ 7；报告中所有 GB/% 数字能在 `report.json` 中找到（`scripts/check_report_numbers.py` 通过）；`patch.diff` 可对原场景 `git apply --check`。

#### T1.9 真实仓库：nanoGPT（P0，~2h）
- 做什么：`repos/` 支持 `--repo <url> --ref <sha> --cmd "python train.py ..."` 模式（命令模式用 `sitecustomize` 注入 hooks）；跑 nanoGPT OOM 配置 → 修复到 `fit:22GB`。
- 验收：`headroom fix --repo ... --target fit:22GB` 完成，`peak_after ≤ 22GB`，`completed=true`，补丁只改 nanoGPT 的 `train.py`/配置（diff 行数 ≤ 60），`loss_equivalence ≠ changed`（允许 `n/a` 若无参考）；总 cost ≤ $0.8。

#### T1.10 Honesty 与安全（P0，~1h）
- 做什么：补丁静态检查：禁止删除/缩小模型结构（层数、hidden size、vocab、seq_len）除非策略允许并明确标注；禁止跳过训练步/截断数据作为"修复"；禁止网络/文件系统越界；`verify` 对比模型参数量（补丁前后 `sum(p.numel())` 必须一致，除非策略允许）。
- 验收：`tests/test_honesty.py`：三类作弊补丁（减层、改 vocab、`max_steps=1`）被拒且原因码正确（`MODEL_SHRUNK`、`TRAINING_TRUNCATED`）；正常补丁 0 误杀；参数量一致性检查对 `s1` 通过。

#### T1.11 Docker Lab（P1，仅 `DOCKER_GPU=ok`，~1.5h）
- 验收：容器内无网络；`headroom fix s1` 默认 Docker 路径成功；超时容器被清理；HF 缓存只读挂载可用。

#### T1.12 MVP 整体验收 + 报告（P0，~1.5h，10/24 晚）
- 做什么：清空 `runs/`；8 个合成场景 + nanoGPT 各跑 `headroom fix`（默认策略，`--budget 0.6`）；汇总 `docs/RESULTS.md`（表：场景、真值根因、诊断首因是否一致、补丁应用、completed、peak before/after、降幅、step 时间变化、数值等价、cost、时长）；写 `reports/phase-1-summary.md`。
- 验收（MVP 通过线）：
  1. 9 个 run 全部退出码 0 且生成报告（无崩溃）。
  2. **≥6/9 `target_met=true`**（OOM 场景不再 OOM；reclaim 场景降幅 ≥20%）；**≥6/9 诊断首因与真值一致**。
  3. 单 run cost ≤ $0.6、wall-clock ≤ 8 分钟（不含首次依赖安装）。
  4. `pytest` ≥ 25 通过；`ruff check .` 0；`gitleaks detect` 0。
  5. `reports/phase-1-summary.md` 含：上表、Top3 失败模式与已做调整、Ultra 长输入实测体验、Token Factory / Super / Nano 体验、Phase 2 建议。→ 停下等 Frank。

### Phase 2 — 增强（10/25，~10h；Frank 确认后）

#### T2.1 显存求解循环：keep-or-revert 搜索 + Pareto 前沿（P0，~3h）
- 做什么：把单轮闭环扩成搜索：Ultra 从诊断计划中按"预期节省/代价"排序出候选修复集合（技术类别：checkpointing 粒度、精度（autocast/参数 dtype）、优化器（fused/8-bit/paged）、batch×grad-accum 重组、allocator 配置、序列分桶、分块 loss/logits、按需加载/卸载）；每轮应用 1 个修复（或 1 个有依赖关系的组合），验证后 **keep**（峰值下降且数值等价/吞吐在策略内）或 **revert**（否则），记录到 `rounds` 表；每个被 keep 的配置记为 Pareto 候选 `(peak_gb, step_ms, numerics)`；达到预算即停，或最多 6 轮；最终输出 Pareto 前沿（例如：`fit 22GB, +11% step time, numerics identical` 与 `fit 18GB, +4% step time, numerics changed(bf16)` 两档）与各档的 patch。策略约束（如禁止数值改变）作为硬约束。
- 验收：`s2` 在 `allow_numerics_change=false` 下通过 ≥2 轮达到 `fit:22GB`（第 1 轮优化器状态，第 2 轮激活）；默认策略下 `s2` 的报告给出 ≥2 个 Pareto 档位（含一个 numerics identical 档与一个更省显存的 bf16 档），每档有独立 `patch.diff`；回退测试：注入一个会使 loss 偏离的修复，系统 revert 并在报告中记录；总轮数 ≤ 6；`rounds` 表每行含 `decision ∈ {keep, revert}` 与理由。

#### T2.2 Tavily Research（P0，~2h）
- 做什么：Diagnose/Patch 阶段对每个拟采用的 API/flag（`torch.utils.checkpoint(use_reentrant=...)`、`PYTORCH_CUDA_ALLOC_CONF` 选项、`torch.optim.AdamW(fused=True)`、`bitsandbytes` 8-bit 优化器、`torch.compile` 内存影响等）调用 Tavily search+extract 取**当前 torch 版本**的文档与已知 issue；注入 Patch 上下文；报告 Sources 段；每 run ≤4 次；缓存。
- 验收：`s5` 的报告 Sources 含 PyTorch CUDA 内存管理文档 URL；`s1` 含 `torch.utils.checkpoint` 文档 URL；重复 query 命中缓存（`credits_used=0`）；`research` 表有记录。

#### T2.3 Nano 栈标注（P1，~1h）
- 验收：Top-40 栈每条有 Nano 一行标注；标注调用总 cost ≤ $0.02/run；与启发式类别一致率 ≥ 80%（对 8 个场景统计）。

#### T2.4 预算守卫与成本面板（P0，~45min）
- 验收：`HEADROOM_RUN_BUDGET_USD=0.05` 时优雅停止并产出部分报告（事件 `budget.exceeded`）；日预算 `0.1` 时新 run 立即拒绝；一次完整多轮 run ≤ $1.2。

#### T2.5 HF Transformers 场景（P1，~2h）
- 做什么：`repos/hf_trainer.yaml`：用 `transformers.Trainer` 微调一个小模型（如 `Qwen/Qwen2.5-0.5B` 或随机初始化 `gpt2-medium` 配置），`per_device_train_batch_size` 过大导致 OOM；补丁应改 TrainingArguments（`gradient_checkpointing=True`、`bf16=True`、`gradient_accumulation_steps`）。
- 验收：`target_met=true`，diff 只改配置行（≤ 15 行），报告指出"优化器状态 + 激活"根因。

#### T2.6 Watch 模式（P2，~1.5h）
- 验收：`headroom watch -- python train.py` 包装任意命令，OOM 时自动触发完整流程并输出报告；非 OOM 时正常透传退出码。

#### T2.7 Docker/HF 缓存稳健性（P1）：验收：三个场景在 Docker 路径下结果与子进程路径一致（峰值差 ≤ 1%）。

#### T2.8 小评测 + 自优化（P0，可夜间自治，~4h）
- 做什么：8 合成 + nanoGPT + HF 共 10 个场景 × 2 策略（默认 / `allow_numerics_change=false`）；统计 `target_met` 率、诊断首因一致率、平均降幅、吞吐代价、数值等价率、轮数、cost；失败模式分析；调整 prompt/证据包/策略 ≤3 轮。
- 验收：`docs/RESULTS.md` 新增表；**`target_met` ≥ 75%、首因一致率 ≥ 75%**（目标，如实记录）；总花费 ≤ $12；`reports/phase-2-summary.md`。

### Phase 3 — 产品化（10/26–10/27，~14h）

#### T3.1 FastAPI + SSE（P0，~3h）
- `POST /api/runs`（script_text 或 example_id 或 repo/ref/cmd、target、policy、budget）、`GET /api/runs`、`GET /api/runs/{id}`、`GET /api/runs/{id}/events`（SSE：历史+实时）、`GET /api/runs/{id}/report.md`、`GET /api/runs/{id}/patch.diff`、`GET /api/runs/{id}/evidence.json`、`GET /api/examples`、`GET /api/usage`、`GET /api/health`（DB、GPU、Token Factory 可达）；单工作线程队列；静态托管 `web/dist`；用户上传脚本的运行限制（max-steps 20、max-seconds 180、无网络、无写越界）。
- 验收：`curl -N .../events` 实时收到事件；并发 2 个请求第二个 `queued`；`/api/health` 200；上传含 `import socket` 的脚本被静态检查拒绝（返回 400 与原因）。

#### T3.2 前端素版（P0，~4h）
- 页面：Home（选示例场景卡片 / 粘贴脚本；目标选择器 `Fix OOM | Fit in __ GB | Reclaim headroom`；策略开关；显眼 badge "Powered by NVIDIA Nemotron 3 on Nebius Token Factory · Research by Tavily"）；Run（左：时间线含模型 badge/耗时/cost；中上：显存时间线 before/after 叠加图；中下：峰值组成表/树（点击展开栈）；右：诊断卡（根因、证据引用、预期节省）、补丁 diff、验证表（峰值/降幅/step 时间/数值等价）、Sources、cost 计量；底：下载 patch/report）；Results（评测表）；About（架构 + How we use Nebius/NVIDIA/Tavily + Related work）。Vite + React + TS + Tailwind + Recharts + Shiki/diff2html。
- 验收：浏览器选示例发起 run，实时看到时间线与最终报告；Lighthouse Performance ≥ 70；手机宽度不横向溢出。

#### T3.3 Replay（P0，~1.5h）
- 验收：`/api/replays` ≥5 条（含 `s2` 两轮求解、nanoGPT、一个 `reclaim` 场景）；2 秒内开始回放；预算尽/GPU 忙时首页横幅引导。

#### T3.4 Claude Design 对齐（P1，~3h；设计稿 10/25–10/26 由 Frank+Claude 产出到 `design/`）
- 验收：Home 与 Run 两页还原度 Frank 认可；设计 token 在 `web/src/theme.ts`。

#### T3.5 公网部署、限流、监控（P0，~2.5h；Frank 提供域名/Cloudflare）
- 验收：公网 HTTPS 手机网络可用；同 IP 每小时第 3 个新 run 返回 429；全局队列 ≤3；单 run ≤10 分钟；`systemctl restart headroom-api` 后 10s 恢复；停服务 2 分钟 Frank 收到告警。

#### T3.6 预录素材（P0，~1h）
- 验收：`docs/media/` ≥8 张截图（时间线叠加图、峰值组成、诊断卡、diff、验证表）。

### Phase 4 — 评测战役（10/27 下午起，夜间自治）
- **T4.1 评测集定稿**（P0）：10 场景（8 合成 + nanoGPT + HF）+ 2–4 个新增真实脚本（如 timm ViT-L 训练、diffusers 推理 batch 过大）→ `eval/scenario_set.yaml`。验收：`headroom eval --dry-run` 全部可运行且基线行为（OOM/可跑）与预期一致。
- **T4.2 主评测**（P0）：验收：`docs/RESULTS.md` 主表（每场景：真值、首因一致、target_met、peak before/after、降幅、吞吐变化、数值等价、轮数、cost、时长）+ 汇总行。
- **T4.3 消融**（P0——这是"为什么要 1M 上下文"的证据）：8 合成场景 × 3 配置：(a) 完整证据包 + Ultra；(b) 仅 traceback + `memory_summary()`（无快照）+ Ultra；(c) 完整证据包 + Super。验收：消融表 + 3–5 句结论写入 `docs/RESULTS.md`（预期：(b) 的首因一致率显著低于 (a)）。
- **T4.4 冻结**（P0）：`git tag v0.9-eval`；`reports/phase-4-summary.md`；之后只修 bug。

### Phase 5 — 提交包（10/28–10/29）
- **T5.1 README**（P0）：What it is（1 段 + 架构图）/ How we use Nebius Token Factory & NVIDIA Nemotron（角色表 + 长输入实测 + 成本）/ Tavily in the loop / Quickstart（≤5 命令）/ Public demo + Replay / Results（主表 + 消融）/ Related work（A.4，如实）/ Safety & honesty checks / Limitations / License / Acknowledgements。前 20 行出现：一句话、"Built with NVIDIA Nemotron 3 (Ultra/Super/Nano) on Nebius Token Factory"、"Web research powered by Tavily"、demo 链接、视频链接。验收：干净环境 `git clone` 后按 README 跑通 `headroom fix scenarios/s1_batch_too_big/train.py`；GitHub About 栏 Apache-2.0；`gitleaks` 0。
- **T5.2 docs 定稿**（P0）：`ARCHITECTURE.md`、`RESULTS.md`、`FEEDBACK.md`（Token Factory / Ultra（含 1M 长输入体验）/ Super / Nano / Tavily 五段 + 3–5 条可执行建议）。验收：Claude 审阅通过；无敏感信息。
- **T5.3 Devpost 描述**（P0，Claude 起草 → Frank 提交）：`docs/DEVPOST.md`。验收：粘贴到 Devpost 草稿并保存。
- **T5.4 视频**（P0，Claude 脚本 → Frank 录）：0:00–0:20 问题（`torch.OutOfMemoryError` 画面 + "每个 PyTorch 工程师都在凌晨三点见过它"）；0:20–0:50 Headroom + 架构（口播 "built on NVIDIA Nemotron 3 Ultra, Super and Nano served by Nebius Token Factory; the full memory snapshot goes into Ultra's million-token context; web research by Tavily"）；0:50–2:10 实机：选场景 → 基线 OOM → 证据包（峰值组成）→ 诊断卡 → 补丁 → 验证通过 → 前后时间线叠加；2:10–2:40 数字（target_met 率、平均降幅、消融：没有快照时首因一致率掉到 X%）；2:40–3:00 受众 + What's next（Watch 模式、FSDP）。验收：≤2:55；YouTube Public；无版权音乐/商标；1080p；前 60s 有界面与口播点名。
- **T5.5 首次完整提交**（P0，Frank，**10/28 晚前**）。验收：Devpost Submitted；track=Coding and Agentic Engineering；三个链接可点开；feedback 已填。
- **T5.6 评委视角自检**（P0，10/29）：4 项 1–5 自评 + 每项 +1 分最便宜改动；Stage One 自检。验收：写入 `reports/final-summary.md`。
- **T5.7 最终提交**（P0，10/30 ≤15:00 CET）：`git tag v1.0`；干净环境复跑；公网冒烟；Devpost 最终保存。

### Phase 6 — 保活（10/31–12/15）
每周检查 `/api/health` 与告警；11/25 前确认 Token Factory 余额 ≥$10、Tavily credits；不关机；评审期只修 bug。验收：12/1 与 12/8 两次人工访问记录。

---

## F. 风险与裁剪
- Ultra 在 Token Factory 的实际最大输入低于预期（如 128k）→ 证据包预算按实测设定，分层裁剪保证关键证据在前；消融仍能证明"快照证据"的价值。
- 快照解析在特定 torch 版本有差异 → 固定 torch 版本并在 README 写明；`evidence.py` 对缺失字段容错。
- 用户脚本结构多样（无 optimizer、自定义训练循环）→ step 截断用 `--max-seconds` 兜底；loss 捕获失败则 `loss_equivalence=n/a` 并如实报告。
- 补丁"作弊"（改小模型）→ Honesty 检查 + 参数量一致性。
- Docker 不可行 → 子进程隔离 + 静态检查 + 环境白名单，README 如实说明；不超过 1.5h。
- 时间不够 → 砍 T1.11、T2.3、T2.5、T2.6、T2.7、T3.4；保留全部 P0（含消融 T4.3）。
- 同机其他任务：显存峰值指标不受影响；只在 step 时间比较时要求独占并标记。

## G. 比赛硬性要求速查（自包含；提交相关任务以此为准）
- 比赛：Nebius x NVIDIA Global AI Hackathon（Devpost）。提交期至 **2026-10-30 10:00 PT**；评审期 **12/01–12/15**（demo URL 与仓库须在此期间可用）；公布约 2027-01-11。
- Stage One（pass/fail）：项目运行时调用 Nebius Token Factory 推理 API（或部署在 Nebius AI Cloud）；使用至少一个 NVIDIA 开源模型；真实属于所选赛道（Coding and Agentic Engineering：agents that write, run, and test code）。不得经其他 provider 调用 NVIDIA 模型来满足要求。
- Stage Two（1–5 分，等权重，平局按顺序比）：Technological Implementation（怎么用 Token Factory + Nemotron）→ Design（完整产品体验）→ Potential Impact（真实问题/受众/demo 证明）→ Quality of the Idea（非显而易见 + 懂问题域）。
- 提交物：可运行项目；赛道选择；文字描述（Inspiration / What it does / How we built it / Challenges / Accomplishments / What we learned / What's next）；**可用 demo URL**；**≤3 分钟公开 YouTube 视频**（展示运行、口播点名 Nebius Token Factory 与 NVIDIA Nemotron、无版权音乐/第三方商标）；**公开仓库**（GitHub，根目录开源 license 文件使 About 栏可见；README 含安装运行指引并明确标注 Nemotron/Token Factory/其他 Nebius 工具的用法）；**Feedback**（对 Token Factory、AI Cloud、所用 NVIDIA 工具/模型的具体反馈——必填）；全部材料英文。
- 奖项：Grand $20,000 / 2nd $10,000 / 3rd $6,000；4 个赛道奖各 1 台 Jetson Orin Nano；Bonus：Best Use of Tavily $3,000（需运行时真实调用 Tavily API）、City Winner $500×20（需线下到场，我们不适用）、Most Valuable Feedback $100+swag×10。每个项目最多 1 个 Overall **或** 1 个 Track + 1 个 Bonus。
- 组织方 tips：项目名像人起的；API key 不进代码；在描述、Built With、视频口播里把 Token Factory/Nemotron 说得"不可能漏看"；视频当 pitch 不当教程。
- 额度：Token Factory 促销码 `NEBIUS-DEVPOST-GLOBAL26`（$25，表单链接见 T0.1）+ Builders Program（$25）；Tavily 免费 1,000 credits/月。问题找 Nebius Discord https://discord.gg/eXYTGhgnhK 。

## 附录 1：Diagnose 输出示例（节选）
```json
{"root_causes":[
  {"id":"rc1","title":"fp32 AdamW states for all 1.1B params","category":"optimizer_state","bytes_gb":8.9,"evidence_refs":["stk_03","stk_07"],"confidence":0.9},
  {"id":"rc2","title":"Activations retained for 24 layers, no checkpointing","category":"activations","bytes_gb":9.4,"evidence_refs":["stk_01","stk_02"],"confidence":0.85},
  {"id":"rc3","title":"Fragmentation: 2.1 GB reserved but unallocated at OOM","category":"fragmentation","bytes_gb":2.1,"evidence_refs":["hdr"],"confidence":0.7}],
 "plan":[
  {"fix_id":"f1","type":"code","title":"Enable activation checkpointing per block","expected_saving_gb":7.0,"numerics_impact":"none","throughput_impact":"minor","risk":"low","requires_policy":[]},
  {"fix_id":"f2","type":"env","title":"PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True","expected_saving_gb":1.5,"numerics_impact":"none","throughput_impact":"none","risk":"low","requires_policy":[]},
  {"fix_id":"f3","type":"code","title":"bf16 autocast for forward/backward","expected_saving_gb":4.5,"numerics_impact":"minor","throughput_impact":"none","risk":"low","requires_policy":["allow_numerics_change"]}],
 "verification":{"max_steps":20,"compare_loss":true,"tolerance":1e-3},"needs_more_info":false}
```

## 附录 2：关键链接
- 比赛页/规则/FAQ：https://nebiusglobalaihackathon.devpost.com/ ｜ `/rules` ｜ `/details/faqs`
- 额度：促销表 https://nebius.com/promo-code?utm_promo_event_code=2026-devpost-global-ai-hack&utm_promo_code_type=Token_Factory&utm_promo_activation_code=NEBIUS-DEVPOST-GLOBAL26 （激活码 NEBIUS-DEVPOST-GLOBAL26）；Builders Program https://dev.nebius.com/builders ；Discord https://discord.gg/eXYTGhgnhK
- Token Factory cookbook：https://github.com/nebius/token-factory-cookbook/tree/main/models/nemotron
- PyTorch 内存快照文档：https://docs.pytorch.org/docs/main/torch_cuda_memory ；可视化 https://pytorch.org/memory_viz
- 先例（README 引用）：GPU-Boost https://github.com/its-arnavtech/GPU-Boost ；NeMo memory-snapshot skill（docs.nvidia.com）；loadtune（PyPI）
- 真实仓库：https://github.com/karpathy/nanoGPT
- Tavily docs：https://docs.tavily.com