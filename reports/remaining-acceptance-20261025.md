# 回放准备后续修复状态（2026-10-25）

主代理在上述只读调查后批准了最小修复。生产 `headroom/replay_curation.py` 现已接受真实 `patcher`，同时保留旧 `patch` / `patch_fix`；其余真实性、身份、所有权、费用一致性、candidate 验证、artifact 白名单和事务恢复门未改。对应 41 项独立 guarded 离线测试通过（5.08 秒），Ruff/check/format 通过；父进程与 spawn 均验证真实网络、`.env`、profile、生产 Store/ledger 被阻断。生产和测试已冻结，未执行实际 curation、模型、GPU 或真实 API。

证据为 `reports/replay-ui-preparation-20261025/curation-role-fix-receipt.json`；真实 404 的只读同库/私有 owner 状态证据为同目录 `preview-404-readonly-evidence.json`。以下准备文中的“角色缺口尚未修复”与“本次只读”是先前调查快照，保留原字节；本段只更新该修复状态。它不表示 MVP v3 已通过，也不表示某个 run 已发布或满足五条 replay 门。必须待主代理选择真实、完整、合格的 repair ID 后执行读检查及 curation；v2 仍因无 candidate repair 验证不合格。

---

# MVP v3 后的真实修复回放 / UI 验收准备（只读审计）

审计时间：2026-10-24T23:00:57.529329+00:00。代码基点 `1a935c8716cee05edf2b1ad1d3e37d35f52a5ef3`。MVP v3 在主代理发出本任务时正在运行；本节未查看/接受其最终结果、未选择或发布任何 v3 run。preflight 为 `reports/live-campaign-20261025/mvp-v3-preflight.json`，SHA-256 `f47efd59142d5e3681d5b10b93387a3ed2931419127d382af227f01c15f71b3d`。下面是执行准备，不是任何 UI、回放或模型验收通过记录。原 PLAN 和后面的历史审计正文保持不变。

此次只读取源码、既有报告，以及预览服务的监听 PID/cwd/打开文件描述符；没有打开 SQLite 连接、读取 `.env`、调用 API/模型/Tavily、运行 GPU/测试、截图、Lighthouse 或执行 curation。只更新本报告。

## 1. 已确认 404 的边界：默认预览与 live campaign 共用 Store

- `headroom/evaluation.py:1472–1477`：`provenance == "live"` 使用 `<project>/runs/headroom.db`；只有 fixture campaign 使用自己的 `fixture.db`。不能把 fixture 的隔离 DB 设计推及真实 MVP。
- `headroom/api/app.py:85–87`：默认 DB 同样是 `runs/headroom.db`，API 展示文件根为 `runs/jobs`。
- 实际预览服务监听 `127.0.0.1:8765`，PID `3842066`，cwd 为 azuki Headroom 根目录。只读 `/proc/3842066/fd` 观察到其打开的是 `/home/xiaodouzi/workspace/headroom/runs/headroom.db` 及对应 WAL/SHM。因此当前默认预览无需数据库导入，也不能通过复制整库来处理 404。
- `headroom/api/app.py:283–290`：run 不属于当前 `api_owner` 且未标 `public_replay`，会返回 404。campaign run 未经 curation 直接访问即可能命中这一会话边界；404 本身不证明数据丢失。
- 另有独立的文件定位差异：campaign 原始 artifacts 位于 `runs/evaluation/live/<campaign>/jobs/<run_id>`，API 下载从 `runs/jobs/<run_id>` 读取（`app.py:412–424,482–490`）。既有 curation 的职责是验证并镜像白名单文件，再标公开回放；不导入/复制 calls、events 或账单。
- 若以后显式启动使用其他 `ApiSettings.db_path` 的预览，应重新核对实际路径。现有 CLI 没有 `--source-db` / `--destination-db`，不可声称它支持跨 Store 导入。

## 2. 发布前的一个真实阻碍：patch 模型角色名不一致

当前 `headroom/replay_curation.py` SHA-256 为 `3a52683dc9b0af2f2f73cc0bae231bca492daaf780dbdc1441b8bdb1c06e9f9b`。

`replay_curation.py:166–179` 要求成功模型响应含 `diagnose` 和 `patch` / `patch_fix` 中至少一种角色；生产 `headroom/patch.py:574–579` 的初次和修复调用统一使用 `patcher`。真实、具有完整验证证据的生产 run 也会因此被错误拒为 `REAL_MODEL_RESPONSE_RECORDS_MISSING`。本次只报告，未更改代码、未运行 curation，也未借此降低身份/响应/验证门。

最小修正方向是让筛选接受真实生产角色 `patcher`，保留必要的历史兼容名称，并补真实 router role → curation 的离线回归；其余 live provenance、精确响应身份、CUDA repair、report/round/event/capture/patch 一致性仍须保留。由主代理安排，当前版本不能标记“已可发布真实 repair”。

## 3. v3 结束并修复上述角色缺口后的最短命令路径

先对 v3 campaign 作既有只读验收；主代理明确选择实际 ID。选择依据是完成的真实候选验证证据，不是仅 `target_met`、baseline OOM、模型生成了 diff 或工作流结束。v1/v2 没有候选 repair 验证，不能充作真实 repair replay。失败但已真实应用并验证的 run 可以保留失败状态展示；它不能冒充成功修复。

在 azuki 项目根，下面只列模板，本次均未运行：

```sh
source scripts/env.sh
uv run --offline python scripts/curate_repair_replays.py --run-id SELECTED_RUN_ID
```

重复 `--run-id` 可组成明确的批次，最多 16 个唯一 ID；任一不合格拒绝整批。脚本默认只读，固定检查 `runs/headroom.db`，不构造 Store、不创建表/文件、不写事件/flag。读检查 exit 0 仅表示该批当前 eligible；exit 1 表示存在不合格行；输入/读取错误 exit 2。参数见 `scripts/curate_repair_replays.py:11–38`。

审阅返回的 source/asset hash、真实状态、`verified_attempt_rounds`、下载清单，以及 public 内容是否符合当前发布范围后，主代理才执行相同 ID 集合：

```sh
uv run --offline python scripts/curate_repair_replays.py --run-id SELECTED_RUN_ID --execute
```

执行仅在已存在 row 上增加 `public_replay` / curation metadata，并将展示白名单逐 hash 镜像到 `runs/jobs/<id>`；不复制源码、allocator snapshot、env 或私有模型响应，也不改模型调用、账单、target、round 或原报告字节。预存文件冲突不覆盖；重复执行须元数据与资产仍相同。提交/回滚不确定时保留资产与异常，不能凭失败退出盲目清理/重试。完整约束见 `docs/REPAIR_REPLAYS.md`。

既有筛选还检查：terminal live、未 pending report、完整连续 events、真实诊断/patch response、报告用量与 calls 一致、至少一个真实 CUDA candidate、原 verification/patch-result/source manifest 一致、patch.applied 先于 verify.done、kept 属于已验证 round。`target_met=false`、unknown actual、keep/revert 原事实均不被改写。对新 bounded 费用，实际未知仍 null；必须另外核对正式 billing proof，curation 本身不创造财务证明。

## 4. 尽量复用现成 run，逐个验真实 API/显示，不新增模型

主代理完成 curation 后，首先只打开已发布回放：

1. `/api/replays` 列出选中 ID；`/api/runs/<id>` 可访问且保留原 provenance/status/target/selected round。报告、patch、evidence 与 configuration 下载只使用接口返回的真实链接；逐项核对响应内容/hash，不猜测 URL、不把隐藏按钮当 artifact 已存在。
2. SSE 读取保存的事件 sequence，检查无遗漏/重复及末尾 `stream.end`。`app.py:427–470` 对终态 public replay 会发送历史及尾部事件后结束；这只能证明**历史 SSE 回放**，不是模型正在执行或浏览器已创建 live run。
3. UI 对照同一 report：before/after 是 selected 配置；每轮 applied/verified/keep/revert 分开；actual 未知显示 Unknown，费用上界单独标注，不能把 conservative upper 显示为已知 actual。检查回放启动耗时是否 ≤2 秒（T3.3），手机宽度是否溢出、完整下载是否可读；这些均须真实测量，本次未执行。
4. 从这一套真实页面可截取 T3.6 的 ≥8 张素材，并在服务/页面稳定后做一次 Lighthouse Performance ≥70。一次截图或历史测试不能代替测量；本任务没有启动截图/性能负载。
5. 复用同 run 的 `headroom report` / `headroom replay` / `headroom usage` 读入口和报告数字检查，可补 T1.8 展示/报告核对，不触发模型/GPU；但 CLI `report/replay` 不能证明 CLI `fix` 入口通过。

T3.3 原门为 ≥5 条且包含 s2 两轮求解、nanoGPT 和一个 reclaim（PLAN:333）。目前默认五条 baseline 即便可打开，也不能代替这些 repair 内容；不能挑五个失败/相同 run 的副本充数，更不能把 s2 baseline 已 fit22 或人为重复回放算两轮求解。v3 只有实际达到这些内容时才能复用；不足项仍明确 pending。当前没有选定 v3 ID，也未声称五条已满足。

## 5. 一次后续真实 UI run 可合并的门，以及不能合并的门

| 实际执行 | 可直接复用的证据 | 仍独立的原门 |
|---|---|---|
| 浏览器 Home 真实提交一个必要场景，连同正在发生的 SSE 一直看到最终报告 | T3.2 浏览器入口/实时事件/最终报告；T3.1 单请求实时 SSE；同次真实模型用量、run 预算事实、下载；若选择尚缺的 s3 且目标/策略一致，实际 reduction≥30% 时可同时补 T1.6 | 单请求不证明两请求排队；也不证明 .05 run / .1 daily 拒绝、公网限流/告警或 CLI/Watch 入口 |
| 已保存真实 repair 的 curation + 页面回放 | T3.3 的真实内容、历史 SSE、启动时间；T1.8 报告展示/下载；T3.6 素材 | 不证明浏览器新提交 live run、实时模型运行、实际新修复成功；失败仍失败 |
| 干净 clone 按 README 实际执行 s1 `headroom fix` | T5.1 与 T1.7 的真正 CLI/事件/exit；满足时兼得 T1.11 Docker 路径 | evaluation harness child exit 0、CLI `report/replay` 或浏览器 API 不能替代此入口 |
| 真正 Watch 包装 OOM 入口 | T2.6 Watch 识别→Lab→报告及其退出语义；若 HF 场景/约束适合可同次补 HF 特定门 | 不能从 fix/eval/API 成功推导 Watch 已执行 |

优先让必须新增的 UI run 覆盖 MVP 尚缺的实际场景门，避免仅为界面再次生成相同修复。若 MVP 已覆盖全部 s3 数值门，则选已验证最稳定场景，以实际完成情况记验收；不预承诺新调用次数/费用或成功。原 default policy、completion cap、run/day/global 额度及数值门均不改变。

费用展示与费用行为也须区分：一次普通 0.6 运行能证明其本次费用与 Store/ledger 一致，不能证明 `--budget 0.05` 部分报告或日额度 0.1 的拒绝行为。先复用已有受控 guard/账本专项证据；缺真实门再由主代理在统一预算池内安排，不清账、不伪造余额、不故意耗光赠送池触发 banner。GPU 忙/预算耗尽 banner 只在真实状态已自然发生或明确标测试状态时验证；状态 unknown 不算 busy/empty。

并发第二请求 queued、上传 socket 静态拒绝、公共 HTTPS/429/restart/通知仍按各自真实入口检验；不能以此次回放一次性声称全部通过。Frank 的域名/设计/告警接收方等交付依赖不由回放解决。

---

以下为原有审计快照，按原字节保留；其中“v2 未执行”等是当时状态，已由本节及真实 v2 失败报告明确覆盖。v2 最终失败：s1 22 calls / 16 Super attempts、0 apply/compile/candidate，actual null / certified upper 0.14129888；后八项为运营停止导致 0-call/0-GPU skip，不是八次模型质量失败。对应 `reports/live-campaign-20261025/mvp-v2-audit.json` 与 `reports/phase-1-summary-20261025-mvp-v2.md`。v3 尚待主代理审计；任何新验收结论均不从本准备文档推导。

# 原计划后续真实验收顺序（2026-10-25）

## MVP v2 前更新：先复用证据，再补缺项

本节替代下方早期快照中的“当前状态”；早期审阅正文完整保留以便追溯。此次仅读取已保存文件并更新本报告和 docs/RESULTS.md，没有运行模型、Tavily、GPU、测试、SQLite/账本操作或读取 .env。完整后端回归由主代理运行，本文不提前宣称其结果。**MVP v2 此时尚未执行；以下顺序以其真实结果到齐为前提，不是 v2 成功声明。**

读取基点 HEAD 为 7d54abe37defcec1755add13b1c1f27da3781bb7；原 PLAN SHA-256 仍为 e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56。当前 PROGRESS 快照 SHA-256 为 1aa898e61b3ea62bcb9a474b272d3f4a25139f8ee2c5fd6b466ad1243fd69011。它会继续更新，不将该快照视为后续实时状态。

### 已有事实：不必为它们再付费或重跑 GPU

- **T0.4 已验收能力矩阵的执行及结果记录**：60 个原定样本，Ultra 最大成功 server prompt 为 500,029 tokens；900k 请求 429 保留失败和 1.049344 USD 完整未知上界，没有重试。500,029 是已测成功下界，不是精确最大上下文。Nano tools、未证实的 thinking-budget 方法未采用。见 reports/t0.4-acceptance-20261025.json。
- **T1.3 已验收真实客户端/路由**：Super schema 和同一真实 capture 的 53 条唯一原始记录，Ultra provider input 268,920 tokens，合计 usage-priced 0.2695014 USD。长证据传输能力不证明根因正确。见 reports/t1.3-acceptance-20261025.json。
- **T1.4 v5 只证明部分门槛**：7/8 首因一致、8/8 引用有效、8 次 stop/0 reasoning，已知费用 0.328770 USD；s1/s6 政策违反、s7 补充信息需求及 s5 真值未知保留，完整验收仍失败。MVP 每个场景本来就需要诊断，先核查其新结果，不为同一首因事实再单开八次 diagnosis-only。见 reports/live-campaign-20261025/diagnosis-attempt4-review.json。
- **MVP v1 永久保留失败**：仅 s1 在真实 GPU 基线后调用一次 Nano，缺 cached_tokens 导致当时 fail-closed，未执行补丁，其余八场景未运行。之后经正式 reviewed-retention 保留完整 0.01644864 USD 占用，actual 仍 null；只是允许今后安全继续，旧 Store/report/campaign 没有重写或改判。见 mvp-v1-audit.json、mvp-v2-cap-budget-review.json（同 reports/live-campaign-20261025 目录）。
- **T2.7 已真实验收，撤销旧待办**：s1、s3、HF 六个 GPU arms 的 allocated/reserved 峰值差均为 0% ≤1%；s3 两条路径各 20 updates/loss 相同；s1/HF 两条均真实 OOM，不算训练完成。参考路径是同一隔离容器环境中的独立 subprocess controller，非裸宿主执行，未声称独立 allocator instrumentation。见 reports/t2.7-acceptance-20261025.json。
- **T4.1 十二条真实基线与 Tavily 组件证据继续有效**：源/运行条件未实质变化时无需仅因阶段切换重测十二条基线；已有 search/extract/cache 组件证据也无需重复购买。它们不代替完整修复中的 Sources 或真实研究工具循环。

### MVP v2 结果到齐后先做一份只读复用索引

每个引用保留唯一 run_id、原 source/manifest/report/call hash、有效策略、目标、search mode、prompt/schema 与运行版本。不能改写失败历史、把同一次运行复制为两次独立试验，或以工作流状态猜测缺失的测量。

| 事实及原 PLAN 行号 | v2 可以直接复用的原始证据 | 不能顺带接受的事项 |
|---|---|---|
| T1.12，285–291 | 固定九分母；逐 worker exit 0、cleanup、wall≤480、九报告；≥6 target 和≥6首因；应用/selected completed 事实及每 run≤0.6 的费用证明 | 先核查九条完整性；target≥6/9 不意味着八个 synthetic 中应用成功≥6/8；harness exit 不是 CLI/browser 入口 |
| T1.5，259 | 八个 synthetic 的 patch-result、compile、修复次数和 Super completion usage；曾应用后 revert 仍是 applied | 必须≥6/8 apply+compile、每个 patch/fixer 调用≤4000，不能用九分母或空 diff 猜应用 |
| T1.6，263 | s1 selected completed/peak<24GB/原数值门、s3实测 reduction、参数量/参考记录 | MVP reclaim20% 不能替代 s3≥30%；若实测已≥30%，只核验无需再跑 |
| T1.8/T1.9，271/275 | 报告数字、≥7标题、最终选择配置与 nanoGPT fit22/completed/numerics、≤60行 train/config diff | 在保留原源副本做 git apply --check 不需模型/GPU；非最后候选即最终选择；repo CLI 入口另查 |
| T2.2/T2.3，301/304 | s1/s5研究 Sources+research表+cache credits0，八场景 Nano Top40标签/交付/费用/与heuristic一致率 | add工具生成不是 Tavily；optional/skipped不是交付；未附证据不能算 Ultra 已看；Nano≥80%门仍须实际统计 |
| T2.4，307 | 某个真正多轮 run 的费用≤1.2、预算事件和部分报告 | 不为相同费用事实再跑一个多轮；.05 run/.1 day 行为需各自证据，不能清空/换账本伪造余额 |
| T3.3/T3.6，333/342 | 符合内容要求的真实 run 可直接用于受控回放镜像和截图 | ≥5且包含 s2两轮/nanoGPT/reclaim；五条 baseline 与离线fixture不算；启动耗时/界面仍实测 |
| T4.2/T4.3，346–347 | 同 source、条件、有效policy、search mode、版本和目标的完整 full-Ultra 行 | MVP20%与主表默认30%不能无声混用；变更后的prompt/schema不能当相同消融协议；不能预期优势当结果 |

费用复用须区分两种证明：精确 usage-priced actual 与 runtime/ledger 正式验证的 conservative upper。actual 仍 null 时，只在逐 call 有成功结算的 billing_status=bounded、verified_provider_bound、正确 basis/身份/usage/cap/价格及 budget_attempt_id 账本对应，且总上界≤原门槛时，才能证明“费用不高于门槛”。nested cost.upper_usd、本地 tokenizer 估算、普通未决 reservation 均不够；上界高于门槛不能断言 actual 超额，也不能接受。旧 v1 reviewed_retained 不回填成新 v2 bounded success。headroom usage 的 actual/known subtotal/unknown 必须与原 calls 一致；保守总额另列，不能冒充 sum(cost_usd) 全已知。该核查复用已保存证据，不要求 provider 发票或新的付费请求。

### 最少的后续真实执行顺序

1. **只读验 v2、整理结果和失败类型。** 主代理以 v2 账务证明版本的审计逐项核对上表，再生成 phase-1-summary。原九分母、0.6/480秒/数值门不变；失败只在新 run 中补救。已有 T0.4、T1.3、T2.7 不列重跑。原报告中的 v1 审计脚本为历史 exact-only 版本，不拿它静默接受新 bound。
2. **合并缺失入口和独立专项。** 一次干净 clone 的原 s1 fix 入口可同时补 T5.1、T1.7 和 T1.11 的真实 CLI 事实。浏览器真实发起选用尚缺的场景/目标，例如需要补到30%的 s3；否则从已成功场景做一条稳定的真实UI链。Watch 必须从自己的 OOM 包装入口触发完整修复，不能拿 eval exit 替代；若与 HF 源/目标/权限/参考确实兼容，可把 HF≤15行配置修复与 Watch 合并一次，不预先保证这种组合满足所有门。无 OOM 的退出码透传可用已验证的受控测试，不必模型调用。
3. **补真实专项，不重测完整组件。** 优先审 MVP 的 Nano、research、数值与 patch。只补确实缺少的标注/来源/缓存证据；尽量嵌入上述必要 run。有限多轮搜索同时覆盖 keep/revert、独立 patch 与≤1.2费用；s2原设想/精度政策冲突先按下文决定，不能靠多跑两轮声称修复原冲突。预算.05/.1若现成完整受控入口证据足够，引用它；剩余真实门由主代理按统一池安排，禁止清账或释放未知费用。
4. **固定协议后补 Phase2/4 所缺单元。** 先检查十场景两标签的有效policy，再最多三轮优化，保留所有失败费用；T4主表补 HF/ViT/T5等缺项。full-Ultra消融八行只有条件完全一致才能复用；否则不拼接，先明确新协议。traceback+summary Ultra/full Super 的缺失条件才新增。当前harness没有自动续跑/回填；复用做审计索引，原run不变，必要时说明主表与消融不是同一个实验。保留10×2、8×3及原总花费≤12门，不承诺固定新增调用数或未运行费用。
5. **尽早从已合格修复生成产品证据。** 回放 curation 默认只读，审核后才发布白名单镜像；不会再次调用模型/GPU。用这些修复检查下载、2秒开始、手机布局、当前build Lighthouse≥70并拍≥8素材。实际浏览器run仍须第2步入口，播放旧事件不算实时运行。设计稿到齐后再做外观认可，避免两次录屏。
6. **交付与未来保活独立收尾。** 真实评测后写结论/五段反馈/3–5建议、v0.9-eval，再完成公网告警/视频/Devpost/Stage One检查/v1.0。不在模型成绩未接受前写成功率或消融收益。Phase6未来日期单独记录，不现在填完成。

以上尽量把“确实必须新发起的入口”与“已有MVP缺失的场景门”放在同一 run，但不为节约调用改变目标、策略、场景或证据来源。赠送额度内继续原计划已获授权，不重新把已授权模型工作作为许可阻塞；仍不得充值、扩大池或超额。每次真实执行由主代理复核余量/UTC日池和全provider上界预约，本报告未查账户或账本。

### 真正需要 Frank 的决策或外部输入

| 类型 | 原计划与现事实 | 所需决定；可继续部分 |
|---|---|---|
| s2场景目标冲突，PLAN247/297 | state=8,593,604,608字节；要求≥40%推出peak≤21.48401152GB，已低于22GB；canonical基线本已fit22，实测比例39.8715% | 若要改成版本化校准场景，需明确认可修订与新源，保留原失败/旧runs；不改默认canonical。其他场景、搜索功能和真实keep/revert可先推进 |
| 精度与两策略含义，PLAN296–297/319 | 硬策略禁止数值改变，但默认bf16档要求与当前default=false冲突；default/strict有效相同 | 决定是否保留两个等价标签并如实报告，或明确批准版本化协议修订；未经批准不把allow_precision冒充default，不能为凑Pareto保留被支配点 |
| 设计认可，PLAN335–336 | 尚无Frank+Claude设计稿/Home与Run认可 | 提供design/与最终认可；功能/可用性验证先继续 |
| 公网/实际通知，PLAN338–339/360 | 模板已实现，域名/Cloudflare及接收方未配置/投递 | 提供域名接入和明确告警收件渠道，完成实际HTTPS/重启/停服务通知；不能向猜测的对象发消息 |
| 最终交付，PLAN352–357 | 需Claude审阅、Frank视频/Devpost角色及最终声明 | 可先备真实素材/草稿/自检；视频公开发布、Devpost提交及人身声明按实际授权完成，不能代签未知声明 |
| 未来时点，PLAN359–360 | 11月25日前余额与12月1日/8日访问尚未发生 | 配置既定保活并在届时记录；不是当前源码缺陷或可预先验收项 |

“phase-1结束后等Frank/Phase2确认”的原文（291/293）不能被用来撤回后来“继续原计划全部开发验收、仅赠送额度”的明确授权；但上述改变原场景/默认策略的实质偏离仍需具体决定。当前未发现必须以重复付费能力探测来解除的新阻塞。

本次与早期版本的差异：关闭T2.7旧隔离待办；加入T0.4/T1.3已验收与T1.4v5限制；记录失败MVPv1与透明上界retention；区分v2费用证明与actual已知；将后续步骤收紧为先复用、合并必要入口、只补缺失评测单元。**以上不代表MVP v2、主评测、发布或完整原计划已通过。**

## 早期只读快照（保留原文，状态以本次更新为准）

本报告仅做只读复核和验收安排，未执行模型、Tavily、GPU、全量回归或实际回放发布；未读取凭据，未改变原计划或费用阈值。T1.4 v5 与九场景 MVP 由主代理执行，不在本报告安排中重复启动。以下“可复用”均是待核验的真实产物用途，不是已通过结论。

## 本次读取基线与回放修复复核

- Git HEAD：`7d54abe37defcec1755add13b1c1f27da3781bb7`。这是当前提交基点，不代表本轮未提交修改已经提交或全量验收。
- 原 `docs/PLAN.md` SHA-256：`e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56`。
- 本次读取 `PROGRESS.md` SHA-256：`6504558bc2f264dde607bebbde406061bd5158bdaf81c3a4e58153d272896852`。该文件会随主代理真实验收继续更新；本文没有把尚未读到的 v5/MVP 结果计入。
- `headroom/replay_curation.py` 最终 SHA-256：`3a52683dc9b0af2f2f73cc0bae231bca492daaf780dbdc1441b8bdb1c06e9f9b`。
- 在内存中仅去掉 `except BaseException` 行的 Ruff `noqa` 注释后，文件精确还原此前已审版本 `d80e9efd9d81a0fa7ac7790287dd82301bee3c4fdf1d8b1ec3ecd41a3b99b3ef`。没有行为变化遗漏，也未改写文件。
- `reports/repair-replay-curation-20261025/receipt-transaction-recovery.json` 的四个源文件哈希及测试日志哈希均与当前文件一致；日志确认 **29 passed / 3.11s**。本次复核没有重跑这些测试。
- 已关闭的两项故障：成功提交后异常不再删除已公开镜像；独占创建后的部分写入/权限/关闭失败仅清理本次新文件。事务回滚未获确认时保留资产及审计清单并传播异常。收据明确实际 curated run 数为 0，离线夹具不算真实修复回放。

## 最短顺序

1. **先只读盘点 MVP，不立即再跑九次。** 用已准备的 `.cache/setup/audit_mvp_acceptance.py` 审核 campaign、原始轮次、实际 worker 退出、报告、Store 与共享账本；整理下面的复用清单。仅对缺少的具体门槛安排额外工作。harness worker 的真实退出 0 不能冒称实际 `headroom fix` CLI 或浏览器调用的退出/交互证据。
2. **补单例缺口并复用其产物。** 优先选择一次干净克隆的 s1 CLI 修复，覆盖 T5.1 和 T1.7 的真实入口；s3 只在 MVP 未达到原 T1.6 的 30% 时补目标；新增 HF 的配置补丁验收，同时为十场景矩阵补第十个场景。Watch 和浏览器各自需要其真实入口证据，不能把普通 eval 的结果当成这些入口已执行。
3. **完成 Phase 2 专项与小矩阵。** 先处理下文 s2/策略/隔离的明确差异，再做必要的有限搜索、预算控制、Tavily/Nano 缺项与十场景两策略评测。保留不成功的结果和所有费用，最多三轮优化，写 phase-2-summary。不得为凑分删除旧历史。
4. **固定最终协议后做 Phase 4 主表和消融。** 已有十二场景基线验收可以复用；真实主表缺少的 HF/两个新增库场景及消融条件再按同一版本执行。原 T4.3 的八场景 × 三条件保持，只有符合全部可比条件的已有 full-Ultra 行才可引用，不能把不同诊断 prompt/schema/search mode 的旧行当同轮对照。完成结果、限制与 phase-4-summary 后才创建 v0.9-eval。
5. **从真实修复产物完成产品验收。** 显式挑选五条合格修复回放，先只读 curation，再发布白名单镜像；随后检查真实浏览器实时流程、回放启动、下载、移动端、Lighthouse 和至少八张修复素材。已通过的队列/限流/拒绝/组件测试只在相应实现变化或尚缺真实入口证据时补测。
6. **部署、提交、保活按原门槛收尾。** 公网与告警须有可用域名/渠道；设计认可与视频/Devpost 由原计划角色完成。README、主表/消融和五段反馈引用实际结果；提交前进行最终固定版本 QA/泄密检查，再按原时点发布标签、复跑与未来访问记录。后续全量源码清单应包含生产输入 `headroom/prompts/*.md`，不能因排除一般文档而漏掉 prompt。

所有付费步骤仍使用现有赠送额度、共享持久账本与原全局/日池保护；不充值、不增加授权池，不把本地估算当硬上限。实际余额、剩余额度和未决账单必须由主代理执行前核对，本文没有实时账户结论。不能因 run 实际费用门槛为 0.6 而跳过 POST 前的完整 provider 上界预留。

## MVP 可以复用什么，哪些不能顺带宣称通过

| 原任务及 PLAN 行号 | 可从真实 MVP 提取的证据 | 仍须满足的原门槛或独立入口 |
|---|---|---|
| T1.5，257–259 | 八个合成场景每轮 patch-result、原始 diff、compile/修复记录、精确模型与 completion usage | ≥6/8 实际 git apply --3way + py_compile；最多三次补丁修复；禁精度变更策略必须生效；每次 **Super 补丁调用** completion≤4000。只诊断成功不等于补丁成功；revert 不抹去曾应用事实。 |
| T1.6，261–263 | s1/s3 实际选中配置、paired/reference 验证、数值/参数量记录 | s1 completed 且 peak<24GB、原数值门；s3 降幅≥30%。MVP reclaim 的 20% 不能替代 30%；负面作弊控制的已有独立回归另行引用。 |
| T1.7，265–267 | s1 的完整事件与模型费用；≥15 事件、≥2 次模型调用及费用精确相加 | 原文明确 headroom fix s1 退出 0。eval harness 子进程退出 0 可用于 MVP 无崩溃事实，但不是该 CLI 入口的观察。一次干净克隆的真实 fix 可同时补此项和 T5.1。 |
| T1.8，269–271 | 原报告、≥7 个二级标题、JSON 数值与选中 patch/config | 对保留的原始源副本做 git apply --check，复核全部 GB/% 来源；不能把最后 revert 的候选当成 selected after，空 diff 不能伪造代码补丁。 |
| T1.9，273–275 | nanoGPT 真实报告、选中 diff、completed、实际费用与数值状态 | fit22GB；diff 仅 train/config 且≤60 行；loss≠changed，无参考时原文允许 n/a；cost≤0.8。MVP 的≤0.6 更严，满足时可同时引用，不能提高 MVP 门槛。 |
| T1.10–T1.11，277–282 | 模型参数量、训练步数、真实 Docker 隔离/清理、源码检查结果 | 与已有三类作弊拒绝/网络/超时/只读缓存测试合并审核；成功模型修复必须实际保留这些约束。旧手工修复 GPU 结果不能冒称 Super 生成修复。 |
| T2.2，299–301 | s1/s5 Sources、research 表、真实 tool dispatch 与 cache receipt | s1 checkpoint 文档 URL、s5 CUDA 内存管理文档 URL、同 query 缓存 credits_used=0、每 run≤4 次。已有 Super add 工具调用不是 Tavily 执行；缺 URL/缓存记录才补对应研究过程。 |
| T2.3，303–304 | 八场景原 annotations.json、Top-40 stack_id 绑定、交付状态与 Nano 调用费用 | 每条 Top-40 有一行标注、≤0.02/run、八场景与启发式一致率≥80%。optional/skipped 或生成成功但未交付不能算完成；标签不能覆盖测量类别。 |
| T3.3/T3.6，332–342 | 合格修复 run 的报告、事件、diff、配置和前后图可用于回放/素材 | ≥5 回放且含 s2 两轮、nanoGPT、reclaim；2 秒内开始。五条真实 baseline 不能充当规定修复集合；截图至少八张，必须来自实际修复界面。 |
| T4.2/T4.3，345–347 | 完整 provenance 的 full-Ultra 结果与同协议首轮诊断 | 十二场景主表及汇总；消融三条件唯一配对，源/策略/search mode/诊断版本可比，未知真值不计作命中。并非将多个旧 campaign 简单拼接即可通过。 |

当前生产编排会调用 Nano 并尝试把标注并入同一预算化证据（`headroom/orchestrator.py:459–469`）；research 有版本、启用和实际工具调用条件（同文件 191–224）。因此复用要读各 run 的实际记录，不能从“代码已接入”推断某次 MVP 已执行这些功能。

## 必须保留的专项差异

### T1.2 与 T2.1：s2 的实际基线不符合原设想

- 原 T1.2 要求 optimizer_state≥总峰值 40%（PLAN:247）；PROGRESS:18/141 保留实际 39.8715%，不能按显示四舍五入算过。
- 当前 canonical s2 基线已 completed 且在 22GB 内。原 T2.1 要求至少两轮（先优化器状态、再激活）达到 fit22GB，并有至少两个真实非支配 Pareto 配置（PLAN:295–297）。MVP 的 reclaim 成功、或达标后继续两轮探索都不能伪称“两轮才达到 fit22”。
- 若状态字节固定为 8,593,604,608，40% 条件推出 peak≤21.48401152GB，本就小于 22GB；单改 foreach 参数并不能同时实现“满足40%”和“基线尚未fit22”。
- 版本化场景校准需要明示、审查并保留 canonical/旧 runs，不能当同一场景无记录替换。bf16 档只允许在明确许可精度改变的策略下探索；不得静默改变当前 default=False。
- 可独立复用/补验：已有 keep/revert/负面 loss 回归、真实轮次理由、≤6 轮及逐档 patch。它们不自动关闭上述场景门。

### T2.4：预算保护不是一次昂贵主评测

PLAN:307 的三项分别是：run 预算 0.05 优雅停止并有部分报告和 budget.exceeded；日预算 0.1 时新 run 拒绝；一次完整多轮 run 实际≤1.2。先引用既有独立账本/真实 Router 的受控回归核对状态和记录，再由主代理决定还缺哪种真实入口证据。不能为了日预算测试清空共享账本、释放未知费用或随意下调正在用的权威池。合格有限多轮验收若实际≤1.2，可同时提供第三项证据，不另跑一遍。

### T2.5–T2.7：HF、Watch 与隔离比较是不同事实

- HF（PLAN:309–311）：真实 target_met、仅配置行的≤15行 diff、诊断指出优化器状态与激活。当前只有 Trainer OOM 基线，尚不能满足修复门。
- Watch（PLAN:313–314）：必须经 watch 入口实际捕获 OOM→完整流程→报告，并验证非 OOM 原退出码透传；已有普通 fix/eval 修复无法证明该触发链。
- T2.7（PLAN:316）：三场景 Docker 路径对独立子进程路径、真实 CUDA 峰值差≤1%。现有 CPU run_script/run_command 均走同一 Docker runner，只证明组件一致。
- 既有 unshare/bwrap 的 EPERM 只拒绝了当时的宿主隔离方案。PLAN:33/127/131 没有要求对子进程使用不安全裸宿主执行；由容器提供外层无网/只读/无密钥隔离，内部另设独立 subprocess controller，是可评估的安全替代设计。须先证明是独立路径、相同源/解释器/参数/种子/步数/测量定义且实际三场景≤1%，不能重贴当前 dual-entry 证据。本报告未实现或验收替代路径。

### T2.8 与 T4：复用可以减调用，不能改分母或控制变量

- T2.8 原文是十场景 × default/allow_numerics_change=false，最多三轮调整，target_met 与首因一致率各≥75%作为目标如实记录、总花费≤12（PLAN:318–320）。当前 default 与 strict 有效策略相同，文档已明确该歧义；不能暗换成 allow_precision 并声称完成原两策略。
- s5/真实库的科学真值仍未独立确认时必须 unknown；不得以只统计可评分行的比率冒称原全分母比率。开发者意图不等于测量真值。
- T4.1 十二条基线已实测验收（PROGRESS:43，`reports/evaluation-baselines-20261024.json`），只要源与运行条件没有实质变化，无需仅为进入 Phase 4 再重复全部基线。
- 现 `run_campaign` 不支持自动恢复/重试或从旧 campaign 自动回填（`docs/EVALUATION.md:28–30`）。复用应保留原唯一 run_id、原费用/失败与原协议，另作可审计的结果索引；不改写历史，不把同一 run 复制成多个独立重复试验。
- 消融配对实际代码 `headroom/evaluation.py:979–1045` 拒绝条件缺失/重复、策略不同、已知/未知 search mode 混合、源哈希不同、真值或首因未知。新旧诊断 prompt/schema 的变化也应在实验协议审阅时核对，而非只依赖代码最低门。
- full-Ultra 的可比八行若已齐，只需补 traceback+summary Ultra 与 full Super 两条件的对应数据；若协议不一致则仍需新的完整对照，不预先声称节约的调用次数。必须保留所有真实成本，不能通过分拆 campaign 绕过原总预算。

## 产品与交付：尽量复用产物，不伪造入口或未来事实

- T3.1（PLAN:324–326）：实际 SSE、两请求 queued、health200、静态拒绝上传 socket。可先使用已有受控入口/队列证据；实际浏览器 run 再观察实时时间线。
- T3.2（328–330）：浏览器发起的真实 run、最终报告，Lighthouse Performance≥70，手机不横向溢出。此前浏览器基线/fixture 检查不等于真实修复全流程；取消的 Lighthouse 不产生分数。
- T3.3：先按明确 run_id 只读 `scripts/curate_repair_replays.py --run-id ID`；全部合格后才显式 `--execute`。从保存的真实结果生成 API 白名单镜像，不运行模型/GPU，不改变模型/账单/target 事实。缺 s2 两轮时保持该内容门未通过。
- T3.4/T3.5（335–339）：设计稿/Frank 认可、公网 HTTPS 与手机网络、第三个同 IP 新请求429、队列≤3、单run≤10分钟、服务重启10秒恢复、停2分钟告警送达。现模板和离线 notifier 不等于已部署/已送达；需要实际域名/渠道和受控服务操作。
- T5.1–T5.2（351–352）：干净克隆五命令内真实 fix，README前20行所需品牌/demo/video，主表/消融、五段反馈与3–5条可执行建议、审阅及 gitleaks0。现 clean-checkout CPU 证明可安装，不是 live repair。
- T5.3–T5.7（353–357）：Devpost 草稿真实保存；≤2:55、1080p、YouTube Public 视频，前60秒界面+点名；首次 Submitted/正确track/三个可用链接/feedback；四项评分和Stage One复检；最终 v1.0、干净环境复跑、公网冒烟、最终保存。真实数字出齐前不填成功率或无快照降幅。
- Phase 6（359–360）：每周health/告警，11月25日前余额≥10USD与Tavily credits，12月1日/8日人工访问。现在不能生成未来日期验收，也不能承诺运行账号自动充值。

## 证据位置与本报告边界

原计划、PROGRESS、`docs/EVALUATION.md`、`docs/WATCH_HF.md`、`docs/REPAIR_REPLAYS.md` 及相关函数已只读核对。已有私有 MVP 审计准备见 `reports/live-campaign-20261025/mvp-audit-preparation.json`；它本身明确未执行、未通过。

这是一份最短验收依赖顺序，不是完成证明、预算扩容、发布许可或原计划变更。后续真实运行失败仍应保存原始证据；局部功能/回归通过、已准备驱动、baseline/replay 可用均不能代替各原验收门。
