# Headroom 本轮交付：模型验收驱动与原生研究工具循环

工作目录：/home/xiaodouzi/workspace/headroom（azuki）。
本轮基于 20e9956，完整 goal 仍在继续。

## 已完成

- T1.3：新增默认仅准备材料的验收脚本，显式执行时走实际客户端、路由及共享预算账本。Super schema 与 Ultra 200k 分开验收；失败、未知费用和重复运行有记录及阻断。
- 用既有 s2 真实捕获的53条原始记录构造长证据包。本地内容计数222428 tokens（含来源标头225303）；逐条原始 JSON pointer、内容哈希和完整证据重建均通过。服务端实际输入 token 仍未知，因此不是200k模型验收通过。
- T1.4：八场景诊断验收驱动和真实输入全部准备完成。原分母8、至少6个首因匹配、实际每次费用不超过0.35美元均保留；s5真值仍未知。没有补充调用、自动修复或重新运行GPU。
- T2.2 / PLAN A5：Super原生选择Tavily search/extract，保留调用ID、真实来源、缓存、费用和部分失败记录。跨修复轮共享5个模型turn、4个工具dispatch额度。已接入生产编排，真实模型工具能力验收仍待后续实测。

## 验证

- 1485项后端测试通过，472.39秒。独立阻断真实DNS/INET及项目.env读取，包含CPU回归；前后源码哈希一致，提交前再次核对。
- Ruff与暂存密钥扫描通过。本轮没有前端源码改动，不声称重新执行了前一轮的51项前端测试。
- 本地预览已更新，健康检查正常；原历史基线report.json、evidence.json、evidence.md均HTTP200。
- 原始捕获和PLAN哈希保持不变；没有新增模型/Tavily请求、GPU运行或模型费用，没有开启live profile。

## 后续工作与保留门槛

下一批可独立开发的是MVP评测表的实际补丁应用/完成事实，以及默认关闭的健康告警投递接口。历史缺值须保留未知，最终保留配置不能混同于被revert的候选。

真实Ultra能力、服务端200k输入、八场景准确率、完整MVP/主评测/消融仍需可用额度和相应调用授权。原s2优化器占比39.8715%低于40%、两轮修复/精度策略冲突、独立子进程隔离条件均未隐藏或改判。设计稿、域名/Cloudflare、真实修复视频和最终提交也尚未完成。

现有每6小时的headroom-nebius检查任务保持ACTIVE；Promo到账后核实当前组织、端点与密钥是否适用，再更新额度状态。当前最多0.10美元试用连通性授权不会被自动扩大。

## 服务器证据

- reports/acceptance-integration-20261024/verification.json
- reports/continuation-full-tests-20261024T141406Z.json / .log
- reports/acceptance-preparation-20261024/independent-audit.json
- reports/client-acceptance-driver-20261024/receipt.json
- reports/diagnosis-acceptance-20261024/receipt-final.json
- reports/research-tool-loop-20261024/receipt.json
- runs/acceptance/client/20261024-offline-s2-v1/prepared.json
- runs/acceptance/diagnosis-prepared-20261024-v2/preparation.json

Mac只同步本纯文本报告；代码、依赖、素材和运行数据均留在服务器。
