# Tailscale 公网部署收尾 — 2026-10-29

公网入口：**https://headroom.tail45186b.ts.net/**

## 结论

当前只读公网部署已经完成，没有发现需要补配或重启修复的 Tailscale 服务端异常。用户真实 Chrome 的首页和 Results 实际数据表均正常加载，首页标签已留在 Chrome 中。访客只需普通 HTTPS 浏览器，无需 Tailscale 账号或客户端。

本次是部署收尾检查，没有新模型/GPU调用、充值、新运行池或改变公开功能开关。

## 实测

- [服务器读数](server.json)：公网健康 HTTP 200 / status ok / TLS 有效，约 2.176 秒。网页和 Tailscale 两项用户服务均 enabled、active/running，重启计数为 0；四个已装 unit 与仓库模板一致，无额外 drop-in；用户 linger=yes。
- Funnel 持久配置为公网 HTTPS 443 → 127.0.0.1:8766。Tailscale Running、Online、无警告；设备凭证到期为 2027-04-26。
- 每五分钟健康检查正常，两端最近返回 200，连续失败数为 0；其中公网 3.79 秒被记录为 slow，不能等同故障。oneshot 检查进程结束后 inactive/dead 是等待下一次 timer 的正常状态。
- [Mac 请求对照](mac.json)：现有 HTTP 代理和绕过显式 HTTP 代理均返回 200，TLS 校验通过；保存的最终一轮分别约 5.27 / 5.39 秒。较早同轮检查分别约 0.95 / 1.68 秒，表明公网线路耗时会波动，不能据此承诺三秒完整页面加载。
- [Chrome 首页](chrome-home.png)和 [Results 数据表](chrome-results.png)是实际浏览器截图。Results 不只是返回页面外壳，九项评测行已经渲染。
- 网页研究工具的一次外部抓取返回内部不可访问错误，未取得可归因的 HTTP 状态；不计为成功的独立外网探测，也不据此判定网站故障。

## 代理与公网的含义

Funnel 将普通公网 HTTPS 请求通过中继送到服务器。访问者不必加入 tailnet。代理仍可能改变 DNS、IPv4/IPv6 选择或出口线路，所以公网地址不能保证在每一条代理线路上都可达。

之前的 Clash Verge 精确域名 IPv4 兼容映射仍保留，本次未改代理设置。绕过显式 HTTP 代理也不能排除该映射或 OS TUN。因此已证明当前 Chrome 和两种请求方式可用，但没有把此前失败武断归因为某一个因素，也没有证明临时映射已可移除。

Tailscale 官方状态页在此次核查时仍列出部分 Funnel 域名公网 DNS 解析事件。前一轮本项目域名在两家公共 DNS 均返回有效地址，不能把厂商事件直接认定为本项目故障根因。

## 已完成与待验收分界

已完成：账号与专用设备、隔离策略、HTTPS/Funnel、独立源站、用户级常驻和自启动、持久转发、定时本地健康检查、Chrome 真实页面访问。已更新 DEPLOYMENT 的当前状态，明确区分旧 Cloudflare 准备材料与现用 Funnel 部署。

仍未验收：独立手机蜂窝网络的页面加载；共享服务器整机重启；向人的告警投递。已有单服务重启记录，不能替代整机启动或严格端到端恢复时长。没有为了验收重启共享服务器。

尚未配置告警接收渠道；当前 timer 只保存本地健康状态，不能宣称用户会收到故障通知。未来选定接收渠道后再验证投递。公网提交仍有意关闭，真实客户端 IP 限流与一次完整示例运行属于后续应用验收，不是 Funnel 配置故障。

## 参考

- [Funnel 官方说明](https://tailscale.com/docs/features/tailscale-funnel)
- [官方 DNS 事件](https://status.tailscale.com/incidents/01M5YVH12FKFH765E1J7PGW4B5)
- [前次复核与独立公共 DNS 证据](../funnel-recheck-20261029/README.md)
- [既有专用服务重启与监控安装证据](../funnel-followup-20261029/README.md)
