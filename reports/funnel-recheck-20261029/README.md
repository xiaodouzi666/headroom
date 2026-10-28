# Headroom 公网访问复核（2026-10-29，北京时间）

公网网址：https://headroom.tail45186b.ts.net/

## 当前结论

部署侧没有发现缺失配置。已在用户真实 Chrome 刷新首页并进入 Results，完整表格正常加载；现有系统代理保持开启。访客不需要安装 Tailscale 或加入账号。

- 服务器上独立的网页服务、Tailscale 服务均 active/running、enabled；用户 linger 为 yes。
- Funnel 已启用，公网 HTTPS 443 转发到专用本地服务 127.0.0.1:8766。
- 服务器不使用 HTTP 代理或固定 IP 覆盖，对首页、Results、Run、About、健康及配置接口的访问均为 HTTP 200，TLS 验证正常；首页引用的 JS/CSS 也返回 200。
- Google 和 Cloudflare 的 DNS-over-HTTPS 都返回三个一致的公网 IPv4 地址。
- 每五分钟健康检查的 timer enabled/active/waiting；最新记录正常，连续失败为零。
- Mac 显式走当前 HTTP 代理的首页请求 HTTP 200，约 0.83 秒；绕过 HTTP 代理的 GET 也为 200，约 1.05 秒。请求耗时不等于页面完整加载时间，后者也不代表独立手机网络。
- 公网新任务仍关闭，未发生模型调用、充值或增加运行预算。

## 代理问题的解释与边界

公网表示访客可以通过普通 HTTPS 访问，不表示任何代理、DNS 或网络线路都一定能到达。代理可能改变解析结果或出站路径。

此前留下的精确域名 IPv4 兼容映射仍存在，本轮没有修改或移除。绕过 HTTP 代理也不能排除 OS 级 TUN 或该映射的影响。因此目前能证明两种请求方式和 Chrome 正常，不能证明之前失败的唯一根因，或该映射已无必要。

官方状态页仍在调查部分 Funnel 域名公网 DNS 缺失事件，但本项目域名在本次两家公共 DNS 查询中都有正确地址；不能把官方事件直接认定为本项目故障原因。

## 尚未覆盖

独立手机蜂窝网络的实际加载未测；没有重启共享服务器。专用 daemon 的重启持久性已在前一份报告验证，本轮只核对现状。健康检查只在服务器保存状态，尚未配置向人的告警通知。

## 证据与官方说明

- server.json：本轮服务、DNS、HTTP 和 TLS 检查。
- chrome-home.png、chrome-results.png：真实 Chrome 当前页面截图。
- https://tailscale.com/docs/features/tailscale-funnel
- https://status.tailscale.com/incidents/01M5YVH12FKFH765E1J7PGW4B5
