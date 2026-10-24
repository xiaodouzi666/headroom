# Headroom 原计划续建报告 — 2026-10-24

完整 goal 仍未完成。本轮补齐可独立推进的功能缺口，原始 PLAN 和验收门槛没有修改。全部代码、依赖、运行和快照仍在 azuki；Mac 只接收这份文字报告。

## 完成的功能

1. 诊断要求补充信息时保存请求并返回 needs_human，含空 plan 的正常缺信息响应；不再重复同样证据。reclaim 节省量针对固定原始基线30%目标计算剩余差额。
2. 报告和 Run 展示各轮实际 diff、验证值、检查与来源，包括已回退补丁；可单独下载完整补丁。
3. Results 接入精选 campaign，补齐逐场景表、汇总行、三条件配对消融和未知分母。默认明确待发布，没有发布fixture或虚构真实模型评测。百分比字符串显示/汇总问题已修正。
4. 默认验证器新增真实输入/目标、初始参数指纹和每次更新观测。当前仅支持完整s3/s4源码及列明的内存变换；未知脚本、旧记录和不同effective batch不自动通过。
5. README 补齐原计划指定的 Related work，按上游资料纠正比较范围，不宣称未经证明的首创性。

## 验证

- 完整后端：923 passed，160.25s；独立守卫阻止真实凭据读取和DNS/INET，CPU Docker无网。前后源码哈希一致。
- 前端：38 tests、typecheck、build通过。
- Chrome最终Results检查：评测待发布、旧needs_human记录及5个真实baseline回放均保留。
- 真实GPU：full-size s3与人工添加no_grad的修复各20步，seed1337、无网Lab、独立容器，捕获/清理/无其他GPU进程观测均通过。

| 指标 | 原始 | 人工修复 |
|---|---:|---:|
| peak allocated GB（十进制） | 2.435717632 | 0.648419840 |
| Lab optimizer interval median ms | 40.896303 | 41.032609 |
| 参数量 | 37,791,744 | 37,791,744 |
| 更新步数 | 20 | 20 |

峰值下降73.3787%，20步loss完全一致，原reclaim比较target_met=true。此补丁是人工编写，不计入模型MVP/主评测/消融成功率。初始化哈希开销单列、总wall保留；interval不是完整训练吞吐结论。

## 仍待完成

Promo页面本轮仍显示trial $1.00、cash $0.00（UI舍入值，不是账单核销）。没有充值或新增付费模型调用。当前仅批准试用额度内最多$0.10的最小连通性验证；完整评测预算、至少$25额度和Ultra能力/长输入/计费边界尚未闭合。

原s2 optimizer-state39.8715%低于40%、原baseline已fit22GB与两轮要求的矛盾，以及小batch数值参照问题均保留。自动配对还不是任意Python的通用证明，未支持脚本明确unknown。真正模型驱动MVP9例、主评测12+例、消融、5个真实修复replay、公网部署、本人视频与正式提交均未完成。

## 证据

项目：/home/xiaodouzi/workspace/headroom
总记录：reports/plan-completion-20261024/verification.json
完整测试：reports/continuation-full-tests-20261024T111506Z.json
人工GPU：reports/pairing-manual-gpu-20261024T111357Z.json（含精确复现步骤）
原始GPU产物：runs/manual-pairing-gpu-20261024T111357Z/
发布格式：docs/PUBLISHED_EVALUATIONS.md
配对边界：docs/VERIFY.md
数值与保留失败：docs/RESULTS.md、PROGRESS.md

初始失败及复审修订记录均保留。交付版本以Git提交和总验证记录为准。
