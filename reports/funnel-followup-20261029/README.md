# Funnel access follow-up — 2026-10-29 (Beijing)

Public URL: https://headroom.tail45186b.ts.net/

## What was verified

The public site was opened in the owner's physical Chrome with the existing proxy still enabled. Home and Results rendered. The visitors' browser does not require a Tailscale client or account.

- [Server check](server-check.json): all six original-hostname requests (Home, Run, Results, About, health, config) returned HTTP 200 with certificate verification enabled and no fixed-IP override or HTTP proxy. This round took 6.20–7.13 seconds, so it is not evidence for a three-second speed target.
- Google and Cloudflare DNS-over-HTTPS both returned the same three public IPv4 Funnel relay addresses from azuki. Queries from the Mac are not treated as independent public DNS evidence because the proxy has an exact-host compatibility mapping.
- [Mac proxy check](mac-check.json): Home, Results and health all returned HTTP 200 with valid TLS. Latency varied from 0.92 to 8.26 seconds. [Home screenshot](chrome-home.png) and [Results screenshot](chrome-results.png) show actual rendered pages. Some navigations briefly showed an empty document before resources completed.
- [Restart check](restart-check.json): only the dedicated Tailscale user service was restarted. It reached Running in 0.773 seconds, retained the identical Funnel forwarding rule, and the public health endpoint subsequently returned HTTP 200 with valid TLS in 8.29 seconds. The application PID and start time were unchanged.
- Both application and Tailscale services are enabled; user linger is enabled. A whole-machine reboot was not performed.
- Public submissions remain disabled. No model or GPU run was dispatched, and no recharge or new spending allocation was made.

## Why a public URL can still fail through a proxy

Funnel uses public DNS and a public relay, then forwards encrypted traffic to the dedicated server process. A proxy can change the DNS answer, address family or outbound route. This does not require the visitor to join a tailnet.

The previous Mac comparison found ordinary domain connections closing while the same proxy reached explicit public IPv4 relays. The existing exact-host IPv4 workaround remains active and its addresses matched the independently checked public DNS in this follow-up. It is temporary; this check did not establish whether the underlying cause was IPv6 reachability, proxy DNS, or the chosen upstream route.

At 2026-10-28 16:34 UTC the official Tailscale status page reported an ongoing investigation into Funnel hostnames missing public DNS records. Our hostname returned valid records in this check, so the incident is a relevant external risk, not a proven cause of our prior failures.

## Remaining evidence boundaries

Independent phone cellular-network timing and human alert delivery remain unverified. The checks do not establish continuous availability or universal network reachability. The service restart validates persistent daemon configuration, not a complete host boot.

## Sources

- [Funnel visitors and public relay mechanism](https://tailscale.com/docs/features/tailscale-funnel)
- [Official public-DNS incident](https://status.tailscale.com/incidents/01M5YVH12FKFH765E1J7PGW4B5)

## Deployed health checks

The dedicated `headroom-funnel-health.timer` is enabled and waiting. Its first production run succeeded: origin HTTP 200 in 85 ms and public HTTP 200 in 253 ms. See [installation receipt](monitor-install.json). A slow successful response is recorded separately from an outage; the monitor uses a 15-second request deadline and a 45-second systemd hard limit.

The check runs every five minutes after the previous one completes, checks the fixed origin and public health endpoints concurrently, verifies public TLS, rejects redirects and oversized/non-JSON responses, and does not use environment proxies. It saves only a private, atomic status projection in `.cache/funnel-health.json`: latest check, HTTP/error code, latency, last success and consecutive failures. It has no notification destination or model credentials.

Validation: 23 focused offline tests passed; Ruff, diff checks and systemd unit validation passed. These are deployment checks, not additional repair acceptance results.

## Latency follow-up

A later bounded [six-request comparison](latency-comparison.json) found origin responses in 2–9 ms and public Home/health around 0.20 seconds. The one public JavaScript request took 4.48 seconds without compression negotiation; the application already supports gzip, so its 304 KB transferred size is not a measurement of Chrome's compressed transfer. These observations support variable public-path latency, not a proven single root cause.

## Final fresh check for the Tailscale follow-up

At 2026-10-28 17:27:58 UTC, both dedicated services were active/running and
enabled, user linger was enabled, and Funnel still forwarded public HTTPS 443
to 127.0.0.1:8766. The health timer was enabled, active and waiting; its latest
recorded sample had zero consecutive failures (origin 79 ms, public 265 ms).
Fresh certificate-verified requests returned HTTP 200 from the origin in
0.083 seconds and from the public hostname without an HTTP proxy in 1.087
seconds. See [current server receipt](current-server-check.json).

The owner's physical Chrome reloaded and rendered the normal public homepage
with the existing system proxy enabled; see [current screenshot](chrome-home-current.png).
The saved [Mac comparison](current-mac-check.json) returned HTTP 200 in 1.918
seconds without an explicit HTTP proxy and 2.243 seconds through the system
HTTP proxy. These routes are not claimed to be independent of OS-level TUN or
the existing exact-host compatibility mapping. No further proxy setting was
changed in this follow-up.

The public interface remains read-only. No new model/GPU operation, recharge,
new spending allocation, public upload or gallery activation was performed.
The temporary private snapshot UI preview and its SSH forwarding session were
stopped after inspection; the two public services remained active.

No current server-side Tailscale configuration gap was found. The remaining
unmeasured items are independent cellular page-load timing, a complete machine
boot, and delivery to a human alert destination. The configured timer writes
local health state only. An attempted fetch via the web research tool returned
an internal access error; it is not treated as an independent successful
external access check or as proof that the site failed.
