# Headroom 公网访问复核

复核时间：2026-10-29 03:24 北京时间。

公网地址：https://headroom.tail45186b.ts.net/

Tailscale 公网接入已经完成，本轮未发现需要补配或重启的服务端问题。实际 Chrome 已显示首页与 Results 的九条真实评测记录；首页标签保留在 Chrome。

## 当前实测

- azuki 通过公共域名访问首页、Run、Results、About、健康接口和配置接口：6/6 HTTP 200，证书校验通过。健康接口返回 JSON status=ok。请求耗时约 0.16–0.24 秒，只是这轮请求时间，不是整页加载或可用性保证。
- Mac 通过现有 HTTP 代理访问首页、健康接口和 Results：3/3 HTTP 200，证书校验通过，约 0.78–0.79 秒。
- Mac 绕过显式 HTTP 代理的三次请求也成功，但系统路由仍经过 utun8，因此不称为完全关闭代理后的独立测试。
- 既有精确域名 IPv4 兼容映射仍保留。本轮没有改变代理设置，不能证明映射已可移除，也不能把以前的失败唯一归因于 DNS、IPv6 或出口节点。
- headroom-public 与 headroom-tailscaled 均 enabled、active/running；Restart=on-failure；用户 Linger=yes。Funnel 持久规则仍为 HTTPS 443 → 127.0.0.1:8766，AllowFunnel=true。
- 每五分钟的健康定时器运行中；最近记录的源站与公网均健康，连续失败为 0。

## 使用方式与边界

访客直接在普通浏览器输入上述 HTTPS 网址，无需安装或登录 Tailscale。公网可访问不代表每一条代理或运营商线路都必然可达。

当前公共界面仍为只读，公开提交、上传和图库未在本轮开启。测试没有进行模型/GPU调用、购买或充值。

尚未验证独立手机蜂窝网络、共享服务器整机重启和向人的故障通知投递。既有单服务重启记录不能替代整机重启；当前健康定时器只记录本地状态，尚无通知接收渠道。这些边界不改变当前公网访问已通过的结论。

证据：mac-latest.json、server-latest.json、chrome-home-latest.png、chrome-results-latest.png。官方说明：https://tailscale.com/docs/features/tailscale-funnel
