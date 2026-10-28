# Headroom — 最终执行计划 v5.1（2026-10-28，自包含；取代 v5）

- 截止：**2026-10-30 10:00 PT = 10/30 18:00 CET = 10/31 01:00 北京**。本文件写于 10/28 ~17:00 CET。
- 参与者：**Codex**（工程与素材）、**Opus 5.5 / Claude Code**（视频生成，§4）、**Frank**（决策、Tailscale/YouTube/Devpost 这些需要本人账号的事）。
- Codex 把本文件保存为 `docs/FINAL_48H.md`；docs/PLAN.md 不动。本文件中 Phase 3–6 的安排取代 PLAN.md。

---

## 0. Codex 必读：工作方式的四条改变

1. **公开文档改用人类语言。** README、docs/RESULTS.md 顶部摘要、docs/DEVPOST.md、docs/FEEDBACK.md、前端界面里的所有文案，都是写给评委看的产品文档。禁止出现：内部验收线（"6/9 gate"、"T1.12"、"acceptance v2"、"R3/R4"）、账务术语（"unknown charge"、"ledger"、"halt"、"HTTP 529"、"reservation"、"conservative upper"）、以及任何 "no claim is made / not presented as first-of-its-kind / competitive advantage is unproved" 句式。诚实的边界只写在一个 **Limitations** 小节里，用正常句子。审计细节全部留在 `reports/`，README 只链接一次。
2. **§3 的 README 与 DEVPOST 英文全文是定稿，原样替换**，只把 `{{...}}` 占位符换成 reports 里的真实数字；没有真实数字的占位符连同所在句子删掉。不要加免责声明。
3. **不再跑 3000+ 的全量回归。** 每个任务只跑相关 focused tests + ruff + gitleaks；全量回归只在 F8 前跑一次。
4. **预算准入改为实际预估**：每次 Ultra 调用按"输入 token × 单价 + 2k 输出"预估准入，不再按 8192 输出的最坏情况预留。Frank 给出新运行池金额（§1-A）后记为新 allocation；历史的"unknown charge"保留在账本里，不再作为阻断依据。
5. 顺序：F0 → F1 → F2 → F2b → F3（夜间）→ F3b-1 → F4（含 F3b-4）→ F5 → F6（Opus）→ F3b-2 → F7 → F8。F3b-3 已取消。任何任务超过预估 1.5 倍时间就停下，写明现状，进入下一项。F3b-1 做完后在 README §3.1 的 "What it does" 后加 "Diagnose your own OOM" 小节，视频第 4 段可顺带展示上传入口（不强制）。

---

## 1. Frank 的决策与待办（按时间）

### A. 预算授权（今晚，1 分钟）
先在 https://tokenfactory.nebius.com 看当前余额，并确认 Builders Program（https://dev.nebius.com/builders）的另 $25 是否到账（没到就申请）。然后对 Codex 说一句：
> 授权新建运行池 $X 用于 FINAL_48H（X = 余额 − 8，为 12 月评审期保留 $8；余额不足 $15 时 X = 余额 − 5）。不充值。准入按实际预估成本，不按最坏情况预留。

### B. Tailscale Funnel（今晚，约 10 分钟，需要你本人；服务器 sudo 要密码，所以这三条命令你自己敲）
1. 注册：https://login.tailscale.com （GitHub/Google 登录即可，免费，不要信用卡）。
2. 在 azuki 的 tmux 里执行：
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up            # 终端会打印一个登录链接，用浏览器打开并授权这台机器
   sudo tailscale set --operator=xiaodouzi   # 之后 Codex 不用 sudo 也能管理 funnel
   ```
3. 管理后台 https://login.tailscale.com/admin ：
   - **DNS** 页：确认 MagicDNS 开启，点 **Enable HTTPS**（Funnel 需要）。
   - **Access controls** 页：在策略 JSON 里加（或合并）：`"nodeAttrs": [{"target": ["*"], "attr": ["funnel"]}]`，保存。
4. 回到 tmux 告诉 Codex："Tailscale 已就绪，请做 F2 的 funnel 部署"。URL 形如 `https://azuki.<tailnet>.ts.net`（无需端口）。

### C. 回复"确认恢复 Verified runs"（今晚）
之前移除的 Replay 以 **Verified runs** 的形式恢复：只读页面，展示真实历史运行的快照/诊断/补丁/验证表，不是回放动画。

### D. 明天（10/29）
- 14:00 前看 Opus 生成的 `headroom-demo.mp4`，有问题让 Opus 改；满意就上传 YouTube（**Public**），把链接贴给 Codex。
- 19:00 前按 F7 提交 Devpost（用 docs/DEVPOST.md 逐段粘贴）。

### E. 10/30
- 09:00–15:00 CET 配合 F8 最终检查；15:00 前 Devpost 最终保存。
- 12/1–12/15 评审期：机器不关、Tailscale 不退出、余额 ≥ $8。

---

## 2. 任务清单（Codex；每项含验收）

### F0 固化与准备（P0，30 min）
- 保存本文件为 `docs/FINAL_48H.md`；在 PROGRESS.md 顶部加 "FINAL_48H 执行中" 区块，F0–F8 状态；确认 Frank 的 A/B/C 回复到位（A 没到就先做不花钱的 F2/F2b）。
- 验收：PROGRESS.md 新区块存在；新运行池金额记录在账本（若已授权）。

### F1 消融实验（P0，~1h 机器时间，预算 ≤ $1.5）
- 用已完成的三条件消融工具，对 9 个场景各跑**仅诊断**（不打补丁）：(a) 完整证据包 + Ultra；(b) 仅 traceback + `memory_summary()` + Ultra；(c) 完整证据包 + Super。每条件每场景 1 次调用，reasoning 关。记录首因是否与 README 真值一致、输入 token、费用、延迟。
- 产出：`reports/ablation-20261028/README.md` + `ablation.json`；汇总表写入 docs/RESULTS.md 顶部（§3.3）。
- 验收：27 次调用全有记录；表 3 行 × （首因命中 x/9、平均输入 token、总费用、平均延迟）；总费用 ≤ $1.5；结论 2–3 句人话，**数字必须实测**。

### F2 Verified runs 画廊 + 公网部署（P0，~4h）
1. `/verified` 页：4 个成功运行卡片（s3 73.4%、s8 96.1%、s4、s2，各取最近一次 target_met 的 run）+ 2 个失败卡片（s1、nanoGPT，标 "Not solved — here is why"）。每张成功卡片：场景一句话、峰值 before/after + 降幅、loss 等价状态、参数量不变、补丁 diff、诊断卡（首因 + **可点击的证据栈引用**，点开显示该栈的分配字节与帧）、Sources（有 Tavily 记录就列）、下载 patch/report。
2. 首页第一屏：一句话定位（§3.1 第一段）、badge "Powered by NVIDIA Nemotron 3 Ultra · Super · Nano on Nebius Token Factory — web research by Tavily"、三个按钮：Verified runs / Run an example / Results。"Run an example" 只允许预置示例（公开访客不能上传任意脚本），排队 ≤2，每 IP 每小时 1 次，单次 ≤8 分钟，共享运行池。给评委的"Paste your own script"功能用一个访问令牌 `HEADROOM_JUDGE_TOKEN`（写进 Devpost 测试说明）。
3. 部署：Frank 完成 §1-B 后，Codex 执行 `tailscale funnel --bg 8000`（headroom-api 监听 127.0.0.1:8000），确认 `https://azuki.<tailnet>.ts.net/` 可访问；headroom-api 做成用户级 systemd 常驻（`systemctl --user enable --now headroom-api`，并 `loginctl enable-linger xiaodouzi`——这条需要 Frank sudo，写进 Frank 待办）；`tailscale funnel status` 显示启用。
- 验收：公网 URL 手机网络打开首页 ≤3s；`/verified` 4 成功 + 2 失败卡片，每张成功卡片数字与对应 report.json 一致（脚本核对）；公网点击 "Run an example"（s3）真实完成一次（≤$0.3）；`systemctl --user restart headroom-api` 后 15s 内 `/api/health` 200；URL 写入 README 与 DEVPOST 的 `{{DEMO_URL}}`。

### F2b 前端瘦身（P0，~2h，与 F2 同时）
- 只保留五页：Home、Verified runs、Run、Results、About。删除或隐藏：账本/预算/余额面板（每个 run 只留一行 "Token Factory cost of this run: $0.xx"）、审计 JSON 查看器、repair-scope/context 查询界面、所有含 "unknown charge / ledger / halt / gate / reservation / withdrawn / acceptance" 的文案、调试开关。Run 页保留：时间线（带模型 badge、耗时、费用）、前后峰值图、峰值组成表、诊断卡（可点栈引用）、diff、验证表、Sources、下载。
- 验收：`grep -rniE "ledger|unknown charge|halt|gate|reservation|withdrawn|acceptance" web/src` 为 0；五页在 390px 宽度无横向溢出；Home Lighthouse ≥ 90；`npm run build` 通过；首页第一屏截图放 `docs/media/final/home.png`。

### F3 R7 修复战役 + 创新点补强（P1，夜间自治，预算 ≤ $4）
1. 两处小改（≤1h，不改任何阈值）：s1 类（activations）计划优先 "grad accumulation 保持 effective batch"，Patch 提示给 `micro_batch × accum_steps = batch` 模板；s6 类（temporaries）提示给 "分块 cross-entropy / 不物化 fp32 logits" 模板。
2. 9 场景各跑一次完整修复（同 R5 协议）。
3. **s2 跑两档**：`strict`（数值逐位相同）与 `allow_precision`（允许 bf16 autocast）各一次，形成两条 Pareto 记录（峰值、step 时间、数值状态）。
4. **HF Trainer 场景**（`repos/hf_trainer`）跑一次完整修复，目标 `fix-oom`，期望是配置级补丁（`gradient_checkpointing=True` / `bf16=True` / `gradient_accumulation_steps`）。
5. 可选（≤30 min，不成就跳过）：`headroom watch -- python scenarios/s1_batch_too_big/train.py` 录一段终端输出，证明 Watch 模式能在 OOM 时自动触发。
- 验收：`reports/r7-20261029/README.md` 表格（每场景：首因、apply/compile、target、before/after、降幅、loss 状态、费用）；docs/RESULTS.md 顶部更新为 "历史最好（按场景取并集，注明来源 campaign/commit）+ 最近一轮"；s2 两档各有独立 `patch.diff` 并进入 `/verified`（卡片标 "numerics identical" 与 "bf16, −x% more memory"）；HF Trainer 结果无论成败如实写（成功则进画廊第 5 张成功卡片）；总费用 ≤ $4。

### F3b 真正新增的功能（创新点补强；优先级 1 > 2 > 3，时间不够砍 3；总预算 ≤ $1）

**F3b-1 Bring your own snapshot（P0-new，~3h）**
- 做什么：
  1. CLI：`headroom diagnose --snapshot snapshot.pickle [--traceback oom.txt] [--source train.py]`：不运行用户脚本，直接走 evidence pack → Ultra 诊断 → 输出 `diagnosis.md/json`（根因、证据栈、修复计划、建议补丁草案由 Super 生成但标注 "unverified: not run on hardware"）。
  2. 文档：README 新增 "Diagnose your own OOM" 小节，给出两行抓快照的代码：
     ```python
     torch.cuda.memory._record_memory_history(max_entries=200_000)
     # ... run ...; on OutOfMemoryError:
     torch.cuda.memory._dump_snapshot("snapshot.pickle")
     ```
  3. Web：Home 加 "Diagnose my snapshot" 入口（上传 pickle ≤50 MB + 可选 traceback/源码），需要 judge token 或排队限流（每 IP 每小时 2 次）；结果页复用 Run 页的诊断卡/峰值组成/证据栈，验证表显示 "not run — bring the patch to your GPU"。上传文件只在服务器 `runs/uploads/` 保留 24h。
  4. 安全：pickle 解析用 Headroom 已有的解析器（只读取 `segments/device_traces` 字段），用 `pickletools`/限制 unpickler 禁止任意对象；超大文件拒绝。
- 验收：对 s2 与 nanoGPT 在本机抓的快照，`headroom diagnose --snapshot` 产出根因与 README 真值一致（至少 1/2）；Web 上传一次真实快照成功并展示诊断卡；用一个恶意 pickle（含 `__reduce__`）测试被拒绝；费用每次 ≤ $0.3。

**F3b-2 Watch 模式演示（P1，~1h）**
- 做什么：确认 `headroom watch -- python scenarios/s1_batch_too_big/train.py` 能在 OOM 时自动进入诊断（修复可失败），终端输出保存为 `docs/media/final/watch-demo.txt`；README Quickstart 加一行 `headroom watch -- <your command>`；若 Verified runs 里能加一张 "Watch-triggered run" 卡片更好。
- 验收：一次真实 watch 触发的 run 存在且在 `/verified` 或 Results 可见；文档有示例。

**F3b-3 显存回归检查——已取消。** 先例核查发现 PyTorch 自身 CI（TorchBench）与 `gpucheck` 已覆盖"峰值显存回归门禁"，不做，不写进 README。

**F3b-4 Related work 补充（随 F4 一起做，10 min）**：README 的 Related work 段加一句："`pt-snap-cli` provides query and MCP access to memory snapshots for humans and agents; Headroom goes from the snapshot to a diagnosis with cited stacks, a patch and a hardware-verified result." 链接 https://pypi.org/project/pt-snap-cli/ 。

### F4 文档替换（P0，10/29 09:00 起，~2h）
- 用 §3.1 替换 README.md 全文；§3.2 替换 docs/DEVPOST.md；docs/RESULTS.md 顶部加 §3.3 的 Summary（旧内容移到 `## Full campaign history` 下，不删）；docs/FEEDBACK.md 按 §3.4 重写成五段人话 + 5 条建议（原始观察条目放文末）。占位符只用 reports 里的数字。
- 验收：README 前 20 行含一句话定位、"Built with NVIDIA Nemotron 3 (Ultra / Super / Nano) on Nebius Token Factory"、"Web research powered by Tavily"、demo URL、视频 URL（录好前留 `{{VIDEO_URL}}`）；`grep -ciE "gate|ledger|reservation|HTTP 529|no claim|not presented|withdrawn" README.md docs/DEVPOST.md docs/FEEDBACK.md` 为 0；数字核对脚本确认 README 每个 GB/%/token 数字能在 reports 中找到；GitHub About 栏 Apache-2.0；`gitleaks detect` 0；push。

### F5 干净环境复跑 + 收尾（P0，10/29 12:00，~1h）
- 验收：新目录 `git clone` 后按 README Quickstart 跑通 `headroom fix scenarios/s3_eval_no_grad_missing/train.py`（≤$0.3）产出 report；`.env.example` 完整；`runs/` 不进 git；`git tag v1.0-submission`；push。

### F6 视频素材（P0，10/29 上午，Codex ~1h；生成由 Opus 做，见 §4）
- Codex 准备：(a) `/verified` 可访问且 s3/s8/s4/s2 卡片完整；(b) 一条可重复触发的 s3 live run 入口（URL 或 API），带 `HEADROOM_JUDGE_TOKEN`；(c) 把 s1 的真实 OOM traceback（`runs/.../stderr`）拷到 `docs/media/final/oom-traceback.txt`；(d) 确认 Docker 能跑 `mcr.microsoft.com/playwright/python` 镜像（`docker pull`）；(e) `docs/media/final/README.md` 列出素材路径与 URL。
- 验收：以上五项就绪，PROGRESS.md 标记 "F6 素材就绪，交 Opus"。

### F7 Devpost 提交（P0，10/29 19:00 前，Frank）
- 表单：Project name / Tagline / 七段描述（docs/DEVPOST.md）/ Built With（Nebius Token Factory, NVIDIA Nemotron 3 Ultra, NVIDIA Nemotron 3 Super, NVIDIA Nemotron 3 Nano, Tavily, PyTorch, CUDA, Docker, FastAPI, React）/ Track = Coding and Agentic Engineering / Feedback（docs/FEEDBACK.md 前五段）/ demo URL / 视频 URL / repo URL / Testing instructions（含 `HEADROOM_JUDGE_TOKEN` 与 "one live run per IP per hour; Verified runs needs no token"）。
- 验收：Devpost 显示 Submitted；三个链接可点开。

### F8 最终检查（10/30 09:00–15:00 CET）
- 公网冒烟（首页、/verified、一次 live run）；余额 ≥ $8；一次全量回归（可选）+ ruff + gitleaks；README 数字核对；Devpost 最终保存；`tailscale funnel status` 与 `systemctl --user status headroom-api` 均正常；写 `reports/final-summary.md`。

---

## 3. 定稿文案（英文，原样使用，仅填占位符）

### 3.1 README.md（全文替换）

```markdown
# Headroom

**Headroom turns a CUDA out-of-memory crash into a verified patch.** Point it at a PyTorch script, and it runs the script on a real GPU with allocator history on, captures the full memory snapshot at the moment of failure, hands the evidence to NVIDIA Nemotron 3 Ultra on Nebius Token Factory for a root-cause diagnosis, writes a patch with Nemotron 3 Super, re-runs the script under the same seed, and keeps the patch only if the GPU says it worked: no OOM, lower peak memory, identical losses, unchanged parameter count.

**Built with NVIDIA Nemotron 3 (Ultra / Super / Nano) on Nebius Token Factory.** Web research powered by Tavily.

- **Live demo:** {{DEMO_URL}} — open *Verified runs* to inspect real repairs with their snapshots, diagnoses, patches and verification tables, or run an example on the GPU yourself.
- **Video (3 min):** {{VIDEO_URL}}
- Everything in this repo was measured on a single RTX 3090 Ti (24 GB). Every number below links to the raw run under `reports/`.

## What it does

1. **Capture.** The script runs inside an isolated Docker container (no network, read-only source) with `torch.cuda.memory._record_memory_history` enabled. On OOM — or at the peak of a reclaim run — Headroom dumps the full allocator snapshot, the traceback, the loss series and the step timings.
2. **Diagnose.** The snapshot is compressed into an evidence pack (peak composition by call stack, allocation hot paths, fragmentation, timeline) and sent, together with the source, to **Nemotron 3 Ultra**. Ultra returns ranked root causes, each citing the allocation stacks that prove it, and a repair plan that respects the user's policy (e.g. "keep numerics bit-identical").
3. **Patch.** **Nemotron 3 Super** writes the patch as exact line edits against the original file hash; Headroom applies and compiles it. **Nemotron 3 Nano** labels allocation stacks on the cheap.
4. **Verify.** The patched script re-runs under the same seed. Headroom compares peak memory, step time, the loss series and the parameter count against the baseline. A patch cannot pass by shrinking the model or shortening training.
5. **Search.** Keep what works, revert what doesn't, up to six rounds, until the memory target is met — and, when the policy allows it, report the trade-off tiers (bit-identical numerics vs. bf16) side by side.
6. **Cite.** When a fix depends on version-specific behaviour (`torch.utils.checkpoint`, `PYTORCH_CUDA_ALLOC_CONF`, fused optimizers), Headroom pulls the matching PyTorch documentation through **Tavily** and lists it under *Sources* in the report.

## Results

Nine scenarios with known root causes (eight synthetic PyTorch training scripts plus pinned nanoGPT), each run as a full automatic repair on the 3090 Ti. Peak memory is `torch.cuda.max_memory_allocated` over 20 optimizer updates; "identical losses" means the 20-step loss series matched the baseline exactly.

| Scenario | Root cause (ground truth) | Diagnosed correctly | Verified repair | Peak before → after |
|---|---|---|---|---|
| s3 eval loop without `no_grad` | activations kept during eval | yes | **yes** | 2.44 GB → 0.65 GB (−73.4%), identical losses |
| s8 unused teacher model on GPU | parameters | yes | **yes** | 3.10 GB → 0.12 GB (−96.1%), identical losses |
| s4 `total_loss += loss` retains graphs | retained graph | yes | **yes** | 24.8 GB (OOM) → {{S4_AFTER}} GB (−{{S4_PCT}}%), identical losses over 20 updates |
| s2 fp32 AdamW on 1B params | optimizer state | yes | **yes** | 21.6 GB → {{S2_AFTER}} GB (−{{S2_PCT}}%){{S2_TIERS}} |
| HF Transformers `Trainer` OOM | activations + optimizer state | {{HF_DIAG}} | {{HF_REPAIR}} | 24.8 GB (OOM) → {{HF_AFTER}} |
| s7 frozen params still in optimizer | optimizer state | yes | partial — memory drops, numerics not provably paired | 17.8 GB → {{S7_AFTER}} GB |
| s1 batch too large | activations | yes | {{S1_RESULT}} | 24.8 GB (OOM){{S1_AFTER}} |
| s6 full-vocab logits in fp32 | temporaries | yes | {{S6_RESULT}} | 21.6 GB (OOM){{S6_AFTER}} |
| s5 variable-length fragmentation | fragmentation | unverified | no | 5.0 GB |
| nanoGPT (pinned, 24 GB OOM config) | activations | unverified | no — model asked for more information | 24.7 GB (OOM) |

- Root cause identified from the snapshot in **{{DIAG_HITS}} of 9** scenarios (latest campaign); 6–7 of 9 across the last four campaigns.
- Verified automatic repairs in **{{REPAIRS}} of 9** scenarios (union of the last campaigns; each row links the campaign that produced it in [RESULTS](docs/RESULTS.md)). Best single campaign: {{BEST_SINGLE}} of 9.
- A full nine-scenario campaign costs **about $1.5–2 in Token Factory usage** and 10–15 minutes of GPU time.

### Does the snapshot matter? (ablation)

Same nine scenarios, diagnosis only, one call each:

| Diagnosis input | Model | Root cause correct | Avg. input tokens | Cost |
|---|---|---|---|---|
| Full evidence pack (snapshot + source) | Nemotron 3 Ultra | **{{ABL_A}}/9** | {{ABL_A_TOK}} | ${{ABL_A_COST}} |
| Traceback + `memory_summary()` only | Nemotron 3 Ultra | {{ABL_B}}/9 | {{ABL_B_TOK}} | ${{ABL_B_COST}} |
| Full evidence pack | Nemotron 3 Super | {{ABL_C}}/9 | {{ABL_C_TOK}} | ${{ABL_C_COST}} |

{{ABL_CONCLUSION}}

### Long inputs on Token Factory

Nemotron 3 Ultra accepted a 268,920-token evidence request and a 500,029-token retrieval probe through Token Factory; a 900k-token probe was rejected with HTTP 429. Evidence packs in these runs were 20k–30k tokens; the long-context headroom is what lets Headroom send a snapshot of a large training job whole instead of summarising it first.

## Quickstart

Linux host with an NVIDIA GPU, Docker with GPU support, Python 3.12 and `uv`.

```bash
git clone https://github.com/xiaodouzi666/headroom.git && cd headroom
uv sync --locked --python 3.12
bash scripts/build_lab_image.sh
cp .env.example .env && chmod 600 .env   # add NEBIUS_API_KEY, TAVILY_API_KEY
uv run headroom fix scenarios/s3_eval_no_grad_missing/train.py
```

`headroom fix` prints a live timeline and writes `report.md`, `patch.diff` and the evidence pack under `runs/<id>/`. `headroom snapshot <script>` captures without calling any model; `headroom watch -- <command>` wraps any command and triggers a repair on OOM; `headroom serve` starts the web app on port 8000. See [docs/CLI.md](docs/CLI.md) and [docs/RUNTIME.md](docs/RUNTIME.md).

## How we use Nebius Token Factory and NVIDIA Nemotron

| Role | Model | Why this model |
|---|---|---|
| Diagnosis and repair planning | `nvidia/Nemotron-3-Ultra-550b-a55b` | Reads the whole evidence pack and source in one request; cites allocation stacks; respects policy constraints |
| Patch writing and repair | `nvidia/nemotron-3-super-120b-a12b` | Structured output of exact line edits; function calling for the Tavily research tool |
| Stack labelling, summaries | `nvidia/nvidia-nemotron-3-nano-30b-a3b` | High volume, sub-cent cost |

All calls go through Token Factory's OpenAI-compatible API (`us-central1`). Per-call tokens and cost are recorded in every report. Tavily is called at runtime for version-specific PyTorch documentation and cached per query.

## Limitations

Headroom repairs Python scripts and pinned repositories it can re-run; it does not yet handle distributed training or compiled extensions. {{UNSOLVED_COUNT}} of the scenarios are not solved automatically: the model diagnoses them correctly but either produces patches that do not remove the peak, stops to ask for information (nanoGPT), or cannot be proven numerically equivalent (s7). Step-time comparisons are only reported when the GPU was not shared. Verification covers 20 optimizer updates, not full training runs.

## Related work

Headroom's pieces have precedents; the combination does not. PyTorch's `memory_viz` renders snapshots for humans. GPU-Boost analyses scripts statically and proposes edits. NVIDIA's NeMo memory-snapshot skill provides scripts for humans to inspect traces. MOA (2026) closes a profiling → LLM → patch loop for C/C++ application memory with syntax-level validation. AutoKernel and Karpathy's autoresearch run keep-or-revert loops for speed. Checkmate, DTR and ZeRO-Offload solve memory/time trade-offs inside frameworks. Headroom is, to our knowledge, the first agent that drives PyTorch script repair from a full CUDA allocator snapshot and verifies each patch on the hardware under the same seed. Details and links: [reports/development-20261027/prior-art.md](reports/development-20261027/prior-art.md).

## Repository

`headroom/` (Lab, evidence, LLM routing, verify, search, API) · `scenarios/` (nine scenarios with ground-truth READMEs) · `web/` (React app) · `docs/` (architecture, CLI, evaluation, feedback) · `reports/` (every campaign with raw receipts). Development checks: `uv run pytest -q`, `uv run ruff check .`, `gitleaks detect`.

License: Apache-2.0. Thanks to PyTorch, nanoGPT, Hugging Face Transformers, Nebius, NVIDIA and Tavily.
```

### 3.2 docs/DEVPOST.md（全文替换；Frank 逐段粘到 Devpost）

```markdown
## Project name
Headroom

## Tagline
Autoresearch for GPU memory: an agent that reads full CUDA memory snapshots, patches your PyTorch script and verifies the fix on the GPU — built on NVIDIA Nemotron 3 via Nebius Token Factory.

## Inspiration
Every PyTorch engineer has met `torch.OutOfMemoryError` at 3 a.m. The information needed to fix it already exists — PyTorch can record every allocation with its call stack — but a real snapshot is tens of megabytes and hundreds of thousands of tokens, so nobody reads it; we guess at batch sizes instead. Nemotron 3 Ultra's 1M-token context on Token Factory made a different workflow possible for the first time: give the model the whole snapshot and let it reason from evidence, then make it prove the fix on the hardware.

## What it does
Headroom runs your script on a real GPU with allocator history on, captures the full memory snapshot at the point of failure, and sends an evidence pack (peak composition by call stack, hot allocation paths, fragmentation, timeline, source) to Nemotron 3 Ultra for root-cause diagnosis. Nemotron 3 Super writes the patch as exact line edits; Headroom applies it, re-runs the script under the same seed, and keeps the patch only if peak memory drops with identical losses and an unchanged parameter count. It searches keep-or-revert for up to six rounds toward your memory budget, reports trade-off tiers (bit-identical vs. bf16) when the policy allows, and cites the PyTorch documentation it consulted through Tavily.

On nine scenarios with known root causes, run on a single RTX 3090 Ti: root cause identified from the snapshot in {{DIAG_HITS}} of 9; verified automatic repairs in {{REPAIRS}} of 9, including an eval-loop leak (−73% peak memory, losses identical to the bit), an idle teacher model left on the GPU (−96%), and a retained-graph bug (−{{S4_PCT}}%){{HF_SENTENCE}}. In our ablation, {{ABL_SHORT}}.

## How we built it
- **Lab:** Docker-isolated runner (no network, read-only source), `torch.cuda.memory._record_memory_history`, optimizer-step hooks for step counting and loss capture, same-seed re-runs, parameter-count and training-length honesty checks.
- **Evidence pack:** snapshot parser that aggregates live blocks at peak by collapsed stack, estimates fragmentation and renders the timeline; token-budgeted.
- **Models on Nebius Token Factory:** Nemotron 3 Ultra for diagnosis and planning (evidence requests up to 268,920 tokens in production, 500k in probes), Nemotron 3 Super for structured line-edit patches and the Tavily tool loop, Nemotron 3 Nano for stack labelling. Every call's tokens and cost are logged.
- **Verification and search:** keep-or-revert rounds with per-round verification feedback fed back to the planner.
- **App:** FastAPI + SSE backend, React front end with a live timeline, before/after memory charts, diagnosis cards with clickable stack evidence, diff viewer and a gallery of verified runs — including the ones we could not solve.

## Challenges we ran into
Getting a 120B model to emit patches that apply was harder than getting a 550B model to diagnose correctly: free-form unified diffs failed constantly, so we moved to exact line edits bound to the original file hash, with structured error feedback. Honest verification needs care — a patch can "save memory" by shrinking the model, skipping steps or changing the objective, so Headroom checks parameter counts, update counts and loss series, and refuses those wins. Budgeting long-context calls precisely on a small credit allowance took its own ledger.

## Accomplishments that we're proud of
Real, hardware-verified repairs produced end to end by open models; a diagnosis step that cites the exact allocation stacks; an evaluation that reports failures as carefully as successes, with every number traceable to a raw run; and a demo anyone can open.

## What we learned
Nemotron 3 Ultra reads machine-generated evidence remarkably well — it attributes memory to the right call stacks and respects policy constraints — and reasoning mode is unnecessary for this task. Super is a strong patch writer once the output contract is strict. The hard part of "autoresearch" is not the loop; it is making the verifier impossible to game.

## What's next
Grad-accumulation and chunked-loss repairs for the remaining activation/temporaries cases; FSDP/DeepSpeed-aware diagnosis for multi-GPU jobs; a GitHub Action that reviews memory regressions on pull requests.

## Built with
Nebius Token Factory · NVIDIA Nemotron 3 Ultra · NVIDIA Nemotron 3 Super · NVIDIA Nemotron 3 Nano · Tavily · PyTorch · CUDA · Docker · FastAPI · React

## Try it
Demo: {{DEMO_URL}} (no login; open "Verified runs", or click "Run an example" to launch a real repair on our GPU — one run per IP per hour). To paste your own script use the judge token `{{JUDGE_TOKEN}}`. Repo: https://github.com/xiaodouzi666/headroom . Video: {{VIDEO_URL}}
```

### 3.3 docs/RESULTS.md 顶部 "Summary" 节
- 表 1：九场景（+HF Trainer）历史最好结果（README 同表 + campaign/commit 列 + 报告链接）。
- 表 2：最近一轮（R7）完整结果。
- 表 3：消融。
- 表 4：s2 两档 Pareto（峰值、step 时间、数值状态、补丁链接）。
- "Cost and time"：每轮费用、总花费、单次 live run 费用与时长。
- "Unsolved scenarios and why"：每个一句真实原因。
- 旧内容整体放在 `## Full campaign history` 下。

### 3.4 docs/FEEDBACK.md 结构（人话，每段 4–8 句，全部用真实观察）
1. Nebius Token Factory：onboarding 用时与促销码流程；OpenAI 兼容性（`chat_template_kwargs`/`json_schema`/tools 哪些生效）；Nemotron 3 只在 us-central1；900k 长输入 429；usage 缺 cached tokens 导致那次费用不可知；会不会再用及原因。
2. Nemotron 3 Ultra：268k/500k 长输入延迟与稳定性；reasoning 关掉更好；诊断质量与栈引用准确性；"needs more info" 的触发。
3. Nemotron 3 Super：结构化输出与行编辑契约；unified diff 失败模式（无换行/截断）；tool calling 调 Tavily。
4. Nemotron 3 Nano：栈标注覆盖率与一致率不足；什么时候值得用。
5. Tavily：版本化文档抽取、缓存、credits。
6. 5 条可执行建议（公开各区域模型清单与上下文上限；usage 始终返回 cached tokens；Super 的 diff 输出模板；Ultra reasoning 默认建议；长输入 429 的文档说明）。

---

## 4. 视频生成 brief（给 Opus 5.5 / Claude Code，在 azuki 的 `~/workspace/headroom` 目录启动 `claude` 后整段粘贴）

```
你是本项目的视频制作者。目标：用脚本在服务器上生成一支 ≤2:50、1920×1080、带英文旁白与字幕的 Headroom 演示视频 docs/media/final/headroom-demo.mp4，供 Nebius x NVIDIA Global AI Hackathon 提交。不要用鼠标录屏；一切用 Playwright + edge-tts + ffmpeg 脚本化完成，可重复生成。先读 docs/FINAL_48H.md §4 与 docs/media/final/README.md（素材清单）。

环境约束：无 sudo。Playwright 用 Docker 镜像 mcr.microsoft.com/playwright/python（--network host 以访问 http://127.0.0.1:8000 和公网 URL）；ffmpeg 用 `pip install imageio-ffmpeg` 自带的二进制或静态构建；旁白用 `pip install edge-tts`（免费，需出网），声音 en-US-AndrewNeural（或 en-GB-RyanNeural），语速 -5%。不加音乐，不出现任何第三方 logo 图片（文字提及 NVIDIA/Nebius/Tavily 可以且必须）。所有素材放 docs/media/final/，脚本放 scripts/video/，产物不进 git（.gitignore 加 docs/media/final/*.mp4、*.webm、*.mp3）。

分镜（每段：先生成旁白 mp3，测时长，再把该段画面裁/拉到同样时长；画面之间 0.4s 交叉淡入；字幕用 ffmpeg subtitles 滤镜烧录，字号 36，底部）：

1. 0:00–0:15 「崩溃」：用 web/ 里的一个静态页（或临时 HTML）模拟终端：深色背景、等宽字体，逐行打印 docs/media/final/oom-traceback.txt 的真实 traceback，最后一行高亮 "torch.OutOfMemoryError: CUDA out of memory"。旁白："Every PyTorch engineer knows this screen. The information to fix it is already in the allocator — a memory snapshot with every allocation and its call stack — but a real snapshot is tens of megabytes. Nobody reads it. We guess."
2. 0:15–0:40 「它是什么」：Home 第一屏（含 badge），缓慢滚动到三个按钮。旁白："Headroom reads it. It runs your script on a real GPU with allocator history on, captures the full snapshot at the moment of failure, and hands the evidence to NVIDIA Nemotron 3 Ultra on Nebius Token Factory. Nemotron 3 Super writes the patch, and Headroom re-runs the script under the same seed to prove the fix on the hardware. Web research comes from Tavily."
3. 0:40–1:40 「一次真实运行」：用 judge token 触发 s3 的 live run，Playwright 以 recordVideo 录 Run 页的时间线直到完成（真实 3–6 分钟），后期把等待段加速到总长 ≈60s（ffmpeg setpts），事件出现的瞬间保持正常速度；然后依次停留：前后峰值图（3s）、诊断卡并点开一个栈引用（4s）、diff（3s）、验证表（4s）。旁白："Here is a live run. The evaluation loop in this training script forgets no_grad. Ultra's diagnosis cites the exact allocation stacks that hold the activations. Super's patch is one decorator. The verifier re-runs 20 updates: peak memory drops 73 percent, the loss series is identical to the bit, and the parameter count is unchanged — so the patch is kept."
4. 1:40–2:05 「画廊与失败」：/verified 页，依次悬停 s8（−96%）、s4、s2 两档，滚到 s1 失败卡片并点开 "here is why"。旁白："Verified runs shows every repair with its snapshot, diagnosis, patch and verification — including the trade-off tiers, and the cases Headroom could not solve. A memory tool should show its failures as clearly as its wins."
5. 2:05–2:30 「证据」：Results 页的消融表与结果表（数字以 docs/RESULTS.md 顶部为准；旁白里的数字必须与表一致，先读表再写旁白）。旁白模板："Does the snapshot matter? Same nine scenarios, diagnosis only: with the full evidence pack, Ultra finds the root cause in {A} of nine; given only the traceback, {B}. That is what a million-token context is for — reading evidence, not just documents. Verified automatic repairs: {R} of nine, on a single RTX 3090 Ti, for about two dollars of Token Factory usage per campaign."
6. 2:30–2:50 「收尾」：GitHub README 顶部（公网页面）与 Quickstart 五行。旁白："Headroom is open source under Apache 2.0. Clone it, point it at your script, and get your GPU memory back. Thanks to Nebius, NVIDIA and Tavily."

验收：ffprobe 显示 1920×1080、时长 ≤ 170s、含音轨；每段字幕与旁白一致；旁白中出现 "NVIDIA Nemotron 3 Ultra"、"Nebius Token Factory"、"Tavily"；第 3 段的 live run 是真实运行（保留 run id 到 docs/media/final/README.md）；所有数字与 docs/RESULTS.md 一致。完成后把 mp4 路径、时长、run id 写进 docs/media/final/README.md，并在终端打印：`scp -P 40022 xiaodouzi@azuki.ubj.ink:~/workspace/headroom/docs/media/final/headroom-demo.mp4 ~/Downloads/`（Frank 用它取回并上传 YouTube）。若 Frank 要自己配音：生成一版无旁白但带字幕与时间戳的 mp4 和一份 narration.txt。
```

---

## 5. 时间表（格罗宁根时间）
| 时间 | 事项 |
|---|---|
| 10/28 17:30 前 | Frank：A 预算、B Tailscale、C 确认画廊 |
| 10/28 晚 | Codex：F0、F1 消融、F2 画廊+部署、F2b 瘦身；夜间 F3 |
| 10/29 09:00 | Codex：F4 文档（填数字）、F5 复跑、F6 素材 → Opus 开始 §4 |
| 10/29 13:00 | Frank：看 mp4，上传 YouTube，链接给 Codex |
| 10/29 19:00 前 | **Frank：Devpost 提交** |
| 10/30 09:00–15:00 | F8 最终检查；15:00 CET 锁定（截止 18:00） |

## 6. 前端检查清单（F2b 验收用）
- 五页：Home / Verified runs / Run / Results / About；导航只有这五项。
- Home 第一屏 10 秒内能回答"这是什么、怎么证明、我能点什么"。
- 没有账本、预算、余额、审计 JSON、调试开关；每个 run 只显示一行费用。
- 没有 "gate / ledger / reservation / unknown charge / withdrawn / acceptance / halt" 等词。
- Run 页：时间线（模型 badge、耗时、费用）、前后峰值图、峰值组成表、诊断卡（可点栈引用）、diff、验证表、Sources、下载。
- 390px 无横向溢出；Lighthouse ≥ 90；`npm run build` 无告警级错误；浏览器控制台无报错。