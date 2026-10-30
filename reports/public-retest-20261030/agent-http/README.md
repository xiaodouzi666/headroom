# 公网只读 HTTP 与部署复查

检查时间：2026-10-30 03:41–03:45 UTC（北京时间 11:41–11:45）。本代理仅向 `https://headroom.tail45186b.ts.net` 发出 **85 个 GET**，没有 POST、模型调用、GPU 作业、代码修改、重启或账本修改。浏览器操作、新任务成功与费用结算须使用主线程的独立收据。

## 已确认

- Home、Run、Results、Verified、About 五条页面路径全部 200，返回同一 SPA 入口；HTML 的 SHA256 与当前 `web/dist/index.html` 一致。这证明路由和静态入口可达，不单独证明浏览器交互、移动端布局或新任务成功。
- 5 个 Results campaign 的原始详情与 product-v1 展示投影全部可读；固定九场景仍保留 R7 1/9、R6 2/9、R5 3/9，Watch 和浏览器示例各有独立记录，未改写历史结果。
- 当前 Verified 有 6 条记录、17 个下载；另验证历史白名单仍可访问的 6 个文件。**23/23 下载**均 200，长度和 SHA256 与服务端公开清单逐一相符，全部带 attachment Content-Disposition。7 个 patch 含统一差分文件头与 hunk；8 个 JSON 可解析且 run_id 匹配；8 个 Markdown 内容可读。当前详情已内嵌于 gallery；不存在单独的公开 owner-run 详情授权。
- 全部 5 个非 HTML 静态资源（3 JS、1 CSS、favicon）与本机 serving dist 字节哈希相同；包括 HTML 在内的 6 个文件也匹配部署收据。
- 匿名 config/health 可读，匿名仍为 1 次/IP/小时；有效私有 token GET 返回无小时次数限制（null/false），但保留最多 2 个等待任务和 480 秒期限。config 不回显凭据或资金路径。无效、空、重复 Authorization 均 401；HTTP 自填 funding_kind 或伪造 funding header 不会变为 judge。
- 不带 owner session 的既有 run、report、events 均 404；未知公开 run/kind/campaign 与路径穿越尝试均 404；错误 Host 为 400。
- health 当时报告队列 running=false、pending=0、preparing=0，run submissions enabled=true，snapshot=false；GPU available。Token Factory 状态只说明 reachable/configured，明确 authentication_checked=false；这不是新的 provider 鉴权或模型成功证明。

## 下载监听超时的边界

s3 下载 URL：
`/api/verified/d9926ee7bb624e7fb22540bbc4c92cdc/download/report_json`

本轮 HTTP 200，130636 bytes，SHA256
`7a9370397c1e286266d28e5c7c538e678ab241bd134aeeb0d4d8e5b97b9f40a8`；
`Content-Type: application/json`、
`Content-Disposition: attachment; filename="d9926ee7bb624e7fb22540bbc4c92cdc-report.json"`、
`Cache-Control: no-store`、`X-Content-Type-Options: nosniff`。
因此服务器公开下载接口在这次读取中正常。主线程浏览器下载事件/工具监听超时，需要由客户端证据另行区分，不能从超时本身推断接口故障，也不能据 HTTP 成功宣称浏览器已经保存文件。

## 部署与资源

- 工作树 HEAD 和缓存的 origin/main 均为 `3425964fe183886b984739bbece5c5570a902e5b`。本任务未 fetch 远端，因此“origin/main 相同”是本地跟踪引用比较。
- 运行中部署代码收据为 `3d8112fbe92eb7d7907eef6ebb194e2f3619c904`。它与 HEAD 的 `headroom/`、`scripts/`、`web/` 无差异；这些目录检查时无未提交改动。之后文档提交不改变部署代码。
- systemd 服务 active/running，PID 2167040，命令为仓库 `.venv/bin/python -m scripts.serve_public`，工作目录与仓库相同。启动时传入正式 demo/judge allocation，没有注入测试 worker 或 runtime factory。
- `create_app` 在没有显式 offline worker 时选 supervised process 模式；队列按可信绑定进入 `run_bound_demo`/`run_bound_judge`，其默认 worker 为正式 `run_fix`。这是部署源码和启动入口检查，非新任务运行结果；只读 gallery 是记录，不能误作 mock 模型输出或当次执行。
- GPU 只读瞬时值：RTX 3090 Ti，24564 MiB 总显存，57 MiB 已用，0% 利用率。闲置观测不保证后续任意时刻可用。
- public-api scope 的逻辑文件量 22,965,000 bytes；16 GiB 准入阈值、1 GiB 预留、写入后至少 8 GiB 文件系统可用空间。检查时按字节可准入，未执行 storage_admission、写 marker 或修改 DB。该策略不是全机硬磁盘配额。
- 部署源码保留单个 active + 2 preparing/pending、480 秒总期限、每次模型额度限制、512 MiB / 4096 inode 输出 tmpfs、30 秒/3 槽上传；公共 Uvicorn concurrency=64、backlog=64、keepalive=5。HTTP 复查未制造负载或磁盘耗尽来重新验证资源上限。

## 初始检测器误判，原始记录保留

1. `/.env` 原预期 404，实际 200；返回 695-byte text/html，SHA256 与首页完全相同，没有环境文件内容或凭据。这是 SPA fallback，而非该路径的敏感文件泄露。原 `summary.json` 的 negative_checks_ok=false 保留。
2. 初始 patch 检测只接受以 `---` 开头；六个合法差分以 `diff --git` 开头。补充检查按实际 file/hunk headers 验证，7/7 通过，未改原文件。
3. 首轮错误使用 `view=product`；正式参数是 `product-v1`。补充请求已覆盖。投影本身没有顶层 view 标记，suite_result 也仅在原 payload 含 acceptance 时才出现。最终解释按源代码条件转换核对；此前两个探测器布尔 false 不代表产品故障。

## 收据

- `requests.json`：首轮 68 GET 的状态、耗时、长度、哈希和安全响应头。
- `public-json.json`：匿名公开 JSON 内容。
- `details.json`：详情、下载、静态资源、鉴权和负例检查。
- `runtime.json`：进程、版本、GPU 和文件统计。
- `supplemental-checks.json`：额外 12 GET，patch 内容及 product 参数核对。
- `product-projection-checks.json`：额外 5 GET；保留最初过严的 suite_result 判定。
- `final-interpretation.json`：基于上述原始收据和实际转换合同的最终分类，没有删改失败观测。
- `http-audit.py.txt`、`supplemental-audit.py.txt`：执行脚本文本；私有 token 只在内存请求中使用，未写入报告、URL、stdout 或响应头记录。

Snapshot 仍没有修后 LIVE 成功；见 `snapshot-next-steps.md`。本报告没有声称全部功能通过、全量回归通过、比赛合规确认或正式提交完成。
