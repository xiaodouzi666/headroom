# Deployment preparation

No public tunnel, hostname, service installation, persistent timer, or notification destination has been enabled. The default API listens on localhost only. The development preview uses an SSH loopback tunnel; it does not expose an Internet service.

`deploy/headroom-api.service` is a user-systemd template for this server. It restarts failures and terminates its process group on stop. Production jobs are separately supervised spawn processes: 600 seconds maximum, termination grace, then hard stop, followed by owned-container cleanup. An unconfirmed cleanup freezes the queue. After a server restart, paid/GPU jobs are not silently resumed.

The API admits at most three total running/queued jobs and two new runs per client IP per hour. Session cookies separate private uploads. Repository preparation happens after admission checks. Uploaded code still runs only in the read-only, no-network Lab.

## Public tunnel prerequisites

The owner must supply an approved hostname, an existing Cloudflare tunnel and its private credentials. Keep origin listening on 127.0.0.1:8000. Fill the Cloudflared template and set `HEADROOM_PUBLIC_HOST` to that exact bare hostname plus `HEADROOM_TRUST_CLOUDFLARED=true` on the API service. This enables Secure cookies and uses validated `CF-Connecting-IP` only from loopback requests. The trust assumption is that Cloudflared overwrites this header and is the only public path to the origin. Direct Internet binding or arbitrary reverse proxies do not satisfy it.

Review the full queue, cookie, allowed-host, origin and rate-limit behavior before exposing the service. Do not put keys into Cloudflared configuration or URLs. Token Factory/Tavily keys stay in the server-private .env and never enter a target container.

## Health and remaining acceptance

`scripts/check_health.py` records local DB/queue health and marks an alert due after two continuous minutes of failure. It does not send messages. The health service/timer templates are uninstalled. A notification channel and recipient remain required for an actual alert.

Pending T3.5 acceptance: public HTTPS from a phone network, real tunnel IP rate-limiting, ten-second service restart recovery, and delivery of the two-minute failure alert. A valid template or local unit test does not establish any of these outcomes.
