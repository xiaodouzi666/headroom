# Headroom Phase 0 验收交接 — 2026-10-25

Phase 0 的 T0.1–T0.6 已完成验收。所有代码、依赖、运行数据和密钥仍位于 azuki 的 /home/xiaodouzi/workspace/headroom；本机只保留这份文字报告。

本次完成原定60个模型探测样本（包含历史5个）。Super 的 JSON、工具调用生成和4路并发通过；Ultra 用64031、200031、500029个服务端输入token完成检索。900k请求被429限流拒绝，保留失败，未重试，不能据此宣称上下文上限。配置采用500029的已测下界、150000的证据预算，以及通过实测的json_schema和chat_template_kwargs开关。

Nano工具调用失败、/no_think未关闭推理、thinking-budget参数未验证或无效，均保留，不启用为已证实能力。60样本按usage计算已知费用$0.77289846，另为429未知账单永久保留$1.049344，合计保守占用$1.82224246；不等于最终发票。未充值。赠送额度工作池、税费余量、评委保留额和共享账本均有独立记录。

后续T1.3实际客户端验收也已通过：真实GPU快照53条原始记录经Ultra处理，服务端输入268920tokens；Super JSON通过，两次总费用$0.2695014。该长文本回答存在碎片化推断过度，已记录。T1.4首次实测第一场景正确，第二场景达到4000输出token并发生结构校验错误，总费用$0.088117；其余六场景未执行，该轮不通过，正在修复输出上限和失败响应保存后再测。

证据：reports/t0.4-acceptance-20261025.json、reports/t1.3-acceptance-20261025.json、reports/live-campaign-20261025/、PROGRESS.md。原计划与失败门槛保持；s2的39.8715%低于40%、隔离权限、后续真实修复评测、设计/域名部署、视频提交及未来日期检查仍有独立待办。整个项目尚未宣称完成。

复制命令：
scp -P 40022 xiaodouzi@azuki.ubj.ink:/home/xiaodouzi/workspace/headroom/reports/handoff-phase-0.md ~/Downloads/
