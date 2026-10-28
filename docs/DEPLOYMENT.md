# Deployment preparation

The original deployment preparation is retained below. A dedicated Tailscale Funnel deployment is now being configured; see [FUNNEL.md](FUNNEL.md) and reports/funnel-deployment-20261028 for its current verification status. The development preview remains separate and localhost-only. No notification destination has been configured.

`deploy/headroom-api.service` is a user-systemd template for this server. It restarts failures and terminates its process group on stop. Production admission creates one deadline (default/max 600 seconds) shared by source preparation, queue waiting, process startup and worker execution. Preparation runs in an owned spawn session, with remaining-time Git and publication-lock limits; timeout kills that group, including its Git descendants, before returning. Expired queued jobs never start a worker. The executing worker uses only the time remaining, then TERM cleanup grace and hard stop, followed by owned-container cleanup. HTTP upload/validation before admission and cleanup/report finalization afterwards are explicitly outside this execution bound. An unconfirmed cleanup freezes the queue. Linux parent-death notification also cleans the owned preparation group if its supervisor disappears. After a server restart, paid/GPU jobs are not silently resumed.

The API admits at most three total preparing/running/queued jobs and two new runs per client IP per hour. Session cookies separate private uploads. Repository preparation happens after admission checks. Uploaded code still runs only in the read-only, no-network Lab.

## Explicit reviewed runtime profile

The module entrypoint and service template accept an optional environment
override, `HEADROOM_RUNTIME_PROFILE`. A reviewed user-service drop-in can contain:

```ini
[Service]
Environment=HEADROOM_RUNTIME_PROFILE=/home/xiaodouzi/workspace/headroom/.cache/tokenfactory-runtime.json
```

This is a profile path, not an API key. Do not use `EnvironmentFile=.env` to wire
this option. Profile validation and all existing credential, credit and budget
guards remain in force. Leave the variable unset to retain the existing default
reviewed-profile lookup; no profile is created or enabled by service startup.
For CLI previews, `headroom serve --runtime-profile PATH` overrides this variable.
Use the currently reviewed `HEADROOM_RUN_BUDGET_USD` /
`HEADROOM_DAILY_BUDGET_USD` deployment limits; a profile path does not change
the allocation. Both launchers stay on loopback with `proxy_headers=False`.
No service installation, preview restart, public bind or model call was performed
while adding this startup routing.

## Public tunnel prerequisites

The owner must supply an approved hostname, an existing Cloudflare tunnel and its private credentials. Keep origin listening on 127.0.0.1:8000. Fill the Cloudflared template and set `HEADROOM_PUBLIC_HOST` to that exact bare hostname plus `HEADROOM_TRUST_CLOUDFLARED=true` on the API service. This enables Secure cookies and uses validated `CF-Connecting-IP` only from loopback requests. The trust assumption is that Cloudflared overwrites this header and is the only public path to the origin. Direct Internet binding or arbitrary reverse proxies do not satisfy it.

Review the full queue, cookie, allowed-host, origin and rate-limit behavior before exposing the service. Do not put keys into Cloudflared configuration or URLs. Token Factory/Tavily keys stay in the server-private .env and never enter a target container.

## Health and remaining acceptance

Cached GPU/provider observations and the separate local authorization budget are
documented in docs/AVAILABILITY.md; they do not establish model access or account
balance.

The health checker records local DB/queue health and marks an alert due after
120 seconds of continuously observed failure. Its HTTPS webhook adapter is
implemented but disabled by default. The service/timer templates remain
uninstalled, and no notification destination has been configured or contacted.
Actual recipient delivery remains a separate authorized acceptance step.

Pending T3.5 acceptance: public HTTPS from a phone network, real tunnel IP rate-limiting, ten-second service restart recovery, and delivery of the two-minute failure alert. A valid template or local unit test does not establish any of these outcomes.


## Admission deadline verification

Offline checks use short-lived owned preparation/worker fixtures only. They cover
preparation cancellation with a child process, queue expiry, worker remaining
time, slow expiry-report isolation from the watchdog, cleanup uncertainty,
shutdown, expired startup, Git remaining-time limits and cache-lock timeout.
No model calls or GPU workload are needed for these checks. Preparation process
reaping/group verification may take up to two seconds after its immediate stop;
worker TERM grace defaults to five seconds (maximum ten). Neither grants a fresh
execution budget. Original public deployment, phone-network, restart and alert
acceptance remain pending.

## Opt-in health webhook

scripts/check_health.py checks only the existing localhost /api/health endpoint.
Its default command writes runs/health.json and does not read a credential file
or contact a receiver. The shipped service deliberately omits --notify.

After the owner has explicitly chosen and authorized an HTTPS receiver, place
these settings only in the server-private, gitignored .env, owned by the service
user with mode 0600. Do not put a URL/token on a command line, in a unit file,
in source control, or in a report. Blank examples are in .env.example:

- HEADROOM_HEALTH_WEBHOOK_URL: the exact HTTPS receiver URL (standard port 443).
- HEADROOM_HEALTH_WEBHOOK_TOKEN: optional Bearer token; secret URL paths/query
  values also remain private.
- HEADROOM_HEALTH_WEBHOOK_IDEMPOTENT: false by default. Set true only when the
  receiver guarantees deduplication/replay for the Idempotency-Key header.

Explicit --notify is required in addition to the private destination. A future
authorized service override may append --notify to ExecStart. This development
task did not configure a destination, install a unit, enable its timer, stop the
real API, or send a notification.

The receiver must accept a JSON POST with only event, status, incident_id,
failure_since and observed_at. Timestamps are Unix seconds; event is
headroom.health_failure and status is unhealthy. No full health response, stack,
hostname, URL, credential or other private configuration is included. One random
incident ID and its Idempotency-Key are retained until a healthy sample resets
the incident. The complete first-dispatch payload is persisted and reused byte
for byte on retries; last_attempt_at is maintained separately in local state.

The adapter performs one HTTP attempt per check, ignores proxy/environment
routing, does not follow redirects, and does not save/print response bodies,
URL/token values or raw exception messages. HTTPX INFO request logs are suppressed
only for the sending thread while the private POST is active; unrelated threads
and subsequent logging remain enabled. HTTPX uses 5-second phase/inactivity
timeouts, with 3 seconds for connection establishment and 1 second for pool
acquisition. These are not an absolute five-second POST deadline. The systemd
template separately applies TimeoutStartSec=20s, TimeoutStopSec=2s and
KillMode=control-group: systemd stops an overlong check, then kills the unit's
process group after the bounded stop grace. A persisted sending claim becomes
unknown at the next check; a killed sender is never assumed not to have sent.

## Notification state and retry behavior

A regular state file is atomically replaced and fsynced under an exclusive
nonblocking flock, held across health sampling and any HTTP dispatch. Another
concurrent invocation reports check_already_running without sending. A durable
sending claim precedes the POST, so a process crash or final-state-write failure
cannot silently replay the notification. Malformed, oversized or linked state
files are refused and preserved. Legacy health.json keeps its failure_since,
including a zero timestamp. A backwards observation clock is reported explicitly
instead of inventing elapsed failure time.

At most three attempts are allowed per incident, with 60- then 120-second
minimum backoff:

| Observation | Recorded outcome | Automatic retry |
|---|---|---|
| HTTP 2xx | accepted; notification_sent=true | None for this incident |
| Connection/pool setup fails before HTTP transmission, or HTTP 429 | not_sent | Bounded retry |
| Read/write timeout, connection interruption after dispatch, HTTP 408/5xx, or interrupted sending claim | unknown | Only with the explicit receiver idempotency contract |
| Other 3xx/4xx | rejected | None; redirects are never followed |
| Missing/invalid private destination | configuration_error | No HTTP request; configuration is checked again on a later due sample |
| Attempt limit reached | retry_exhausted | None until recovery/new incident |

2xx means only that the configured HTTP receiver accepted the request. It does
not prove final downstream delivery or that Frank read it. Local state/locking
prevents ordinary concurrent re-sends; it cannot establish network exactly-once
delivery across crashes. Keep a receiver's idempotency contract/destination
stable for an incident. The receiver must deduplicate by the supplied key when
unknown-delivery retries are enabled.

A healthy sample clears the failure timer and notification attempt state.
The next failure receives a new incident ID and a fresh retry allowance. No
recovery message is sent. With the nominal 30-second timer and one-second timer
accuracy, the 120-second threshold is measured from the first failed sample;
threshold crossing may wait another sampling period plus request/scheduling
time. This is not a guarantee that stopping the API results in a human receiving
a message at precisely two minutes.

CLI exit codes remain 0 for healthy, 1 for failure before the threshold and 2
for a due incident, regardless of delivery acceptance. Exit 3 indicates a state
or lock error and leaves delivery unknown rather than claiming success.

Offline evidence is retained in reports/health-notifier-20261024. The independent
runner denies DNS, INET sockets and reads of the real project .env before test
imports. Real HTTPX MockTransport requests cover payload/auth, threshold,
deduplication, idempotent replay, retry limits, unknown outcomes, concurrent
locking, restart, recovery, malformed state and pre/post-dispatch write failures.
These tests are not T3.5 real-recipient delivery acceptance or Phase 6 uptime
observations; those checks remain pending.
