# Phase 2 v2-r1：仅离线准备

这份驱动只为未来的 r1 合格结果准备，当前没有 r1 执行结果，也没有 Phase 2 cap/root review、执行收据或已批准执行 commit。离线自测不是全量质量回归、MVP 合格或执行授权。

- 输出只写入本目录；MVP driver、独立 auditor、质量 driver 和质量收据目录绑定到 reports/acceptance-v2-r1-20261025/。旧 acceptance-v2 的 1/9 历史不能用于本版放行，原文件未改。
- 入口保留固定 10 core × 2 policies = 20，strict 与 allow_precision 各 10，不能合并政策成绩，未执行项保留在分母。
- MVP 前置门保持独立固定九项审计的目标 ≥6/9、有效且正确首因 ≥6/9，并核对当前真实 run、campaign、cleanup、成本、完整源码与实际账本。未通过的其它原始验收项继续显示，不擅自改成 9/9 前置门，也不宣布 Phase 1 全部通过。
- 仍只用累计赠送池 $9.99964904，不充值、不建新池。单 pipeline 上限 $0.6、墙钟 480 秒、最多 6 轮；$12 是 20 个单 run 上限的名义合计，实际 campaign cap 为原池和 UTC 日剩余额度与 $12 的最小值。历史支出、未知成本的已核实预留、未结算和不足额拒绝规则全部保留。
- freeze/execute 会复核同版本完整 quality 证据、独立 MVP audit、资源资格、全部当前源码、实际累计账本，以及 clean/pushed commit。缺本版 review/cap 或 r1 MVP execution 时，在 helper/profile/ledger/GPU 访问前拒绝执行；正式运行仍须通过后续全部原有检查。
- helper/auditor SHA 是准备时实际观察到的草案字节绑定。文件未来变化会拒绝执行，须重新审查准备；未伪造 future quality 收据或 execution commit。

离线证据：self-test.json 的 26 项通过；offline-checks.json 保留精确命令、stdout 和 driver hash；planning.json 为 executed=false 的计划；version-diff.patch 是相对旧驱动的完整差异。自测仅用合成账本与模拟缺失资格，不读真实账本，不调用模型或 GPU。Ruff check 与 format --check 均通过。独立只读 review 未发现阻断，未运行 freeze/execute。

新增负例覆盖旧 MVP audit、路径归一化后的旧版本 audit、旧 quality receipt、混用旧 before/after/log，以及缺执行资格时不得导入 helper 或创建子进程。原账本负例继续覆盖未结算、无有效 provider bound、保留历史支出后不足额；6/9 门既不降低，也不提高为所有原验收项全通过。仍共用原 phase2-v2.lock，阻止跨版本同时启动。
