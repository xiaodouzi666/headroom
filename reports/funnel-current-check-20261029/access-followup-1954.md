# Headroom Tailscale 当前访问复核

检查时间：2026-10-29 03:54（北京时间）。

公网网址：https://headroom.tail45186b.ts.net/

## 结论
Tailscale 服务端配置已完成。本次没有发现需要补配、重启或更改代理设置的故障。真实 Chrome 首页与 Results 的九行评测表均完成渲染；系统 HTTP/HTTPS/SOCKS 代理仍开启。

## 当前证据
- server-195359.json：服务端以普通公共域名访问首页、Results、健康、配置接口全部 HTTP 200，TLS 校验开启，健康状态 ok。
- Headroom 与专用 Tailscale 服务均 enabled / active / running，Restart=on-failure，NRestarts=0，用户 Linger=yes。
- 持久 Funnel 为 HTTPS 443 → 127.0.0.1:8766；Tailscale Running / Online，Health 为空。
- 每五分钟健康检查 timer enabled / active / waiting；最近源站与公网检查均成功，连续失败数零。
- Mac 经现有 HTTP 代理访问健康接口 200 / TLS 校验通过 / 1.456 秒；不显式使用 HTTP 代理为 200 / 1.091 秒；经代理访问 Results 200 / 1.122 秒。这些是单请求耗时，不是完整页面加载时间。
- Chrome Results 已渲染真实九项数据，当前显示最新单轮结果 2/9；公网可达不等于修复验收通过。
- 网页提交、快照提交、Verified runs 和 judge scripts 公开入口仍关闭。本次未触发模型或 GPU 工作。

## 代理解释与限制
Funnel 面向普通公网访客，不要求安装 Tailscale 或加入 tailnet。代理可以改变 DNS、IP 地址族选择和出口线路，因此公网网址仍可能在特定代理路径上失败。
既有记录保留精确域名 IPv4 兼容映射；本次未修改或移除，也没有通过更改系统代理来做破坏性排查。不显式使用 HTTP 代理不等于已排除 OS TUN 的影响。当前检查证明访问可用，不确定此前故障的唯一根因。
官方说明：https://tailscale.com/docs/features/tailscale-funnel

## 尚未覆盖
独立手机蜂窝网络实测、共享服务器整机重启、向人的故障通知投递。未配置通知渠道，不宣称能自动通知用户。以上不属于当前 Funnel 入口缺失配置。
