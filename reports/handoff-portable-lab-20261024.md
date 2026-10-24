# Headroom 本轮交付：Lab 运行环境、超时证据与配置下载

更新时间：2026-10-24T13:25:14.043559+00:00
项目位置：azuki /home/xiaodouzi/workspace/headroom
本轮基础提交：ffb08a84155f7861a6e8bb8d9c6d4b3a84bc091f
完整 goal 继续执行，尚未完成。

## 已完成

- Lab 镜像自带 Python 3.12 与 hash 锁定的 PyTorch/CUDA 依赖，不再挂载宿主 .venv。启动使用预检通过的不可变镜像 ID。无 .venv/.env 的候选目录已完成脚本与 module 两种 CPU 捕获。
- 共享绝对硬截止；软超时先保存已有事实，再序列化大快照。持续分配压力下，不能完成的证据明确标为 partial，保留真实 timeout/步数/峰值，不能通过修复验收。原压力失败记录保留，未延长硬时间或缩减历史门槛。
- 选中轮次的 after PNG/JSON、CLI 参数和 configuration manifest 可以正确下载；报告和网页展示选中配置。空 diff 与尚未生成补丁分开显示。

## 验证

- 完整后端：1344 passed，450.83 秒；测试前后源码哈希一致，独立阻断真实密钥读取及模型网络。
- 前端：50 passed，typecheck/build 通过；浏览器旧基线回放兼容。
- 新镜像 GPU：自然推理和小历史超时完整捕获；连续分配压力真实超时并保留明确部分证据；原始 s3 两次完成20步，前5个 loss 完全一致；全部容器清理验证通过。
- Ruff、格式、pre-commit、暂存密钥扫描和差异检查已通过，提交钩子还会检查最终暂存内容。
- 本轮模型调用0、模型费用$0；未开启 live profile，未充值。

## 保留的待办

真实 Ultra 能力探测、模型修复、MVP/主评测/消融仍待对应账户额度与执行授权。promo 到账后先核对账户、现有 Key 与优惠额度，再优先使用该额度；当前0.10美元最小连通性授权不自动扩大。

原 s2 39.8715% 对40%的门槛、已满足22GB导致的两轮修复问题、精度策略及独立子进程隔离门槛均未改动。公网域名/部署、设计认可、真实修复视频、最终 Devpost 提交及未来访问检查仍在原计划内。

所有代码、依赖、镜像、原始运行和证据留在 azuki；本机只保存这份文本报告。

## 证据索引

- reports/portable-delivery-20261024/verification.json
- reports/continuation-full-tests-20261024T131727Z.json
- reports/deadline-manual-gpu-20261024T131612Z.json
- reports/deadline-manual-gpu-20261024T131014Z-failed.json
- reports/portable-lab-20261024/receipt.json
- reports/lab-deadline-20261024/receipt-partial-first.json
- reports/artifact-delivery-20261024/
