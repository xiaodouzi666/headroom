# Tailscale Funnel deployment

This deployment uses a dedicated rootless Tailscale daemon and a separate
Headroom API process on the existing server. It started in read-only mode;
the current bounded live-access configuration is described below. No DNS purchase, paid
hosting plan, credit-card payment, firewall change, or other project's tunnel is
needed. Tailscale Personal pricing and Funnel availability must be checked
against the vendor's current terms.

## Current access state (2026-10-30)

Commit 3d8112f is deployed with anonymous preset examples and token-backed
examples/custom scripts enabled. Anonymous access retains one attempt per IP
per hour; the verified token route has no hourly run-count quota. Both routes
share one active job, at most two waiting/preparing jobs and a 480-second
admission-to-execution deadline. Snapshot uploads remain paused. Public pages
and Verified runs need no token.

The judging allocation now has an effective $20.92 net total/day ceiling and
$0.30 net per run, using existing gifts only, without recharge and retaining the
$8 gross account reserve. The original $8.00 gross / $6.61 net judging receipt
is preserved; a separate extension supplies the effective limit. The original
anonymous allocation and all historical accounting are unchanged. Admission
uses the existing local input estimate with margins; it is not a supplier
billing hard cap. New judging dispatch expires on 2026-12-15 at 20:00 UTC.

The [deployment receipt](../reports/public-security-20261030/deployment.json)
records public and origin GET checks for anonymous/valid-token access and 401
for an invalid token. [Credit activation](../reports/public-security-20261030/credit-activation.json)
records the extension. Activation and deployment made no model calls or new
judge task; the separate GPU Lab smoke is identified in the deployment receipt.
Readiness is not evidence that a new judge repair has succeeded.

The active private runtime environment is .cache/final48-public.env. It sets
HEADROOM_JUDGE_ALLOCATION_RECEIPT to
/home/xiaodouzi/workspace/headroom/.cache/judge-access/receipt.json.
Do not recreate the allocation or reset its database. The launcher rejects an
explicitly configured invalid receipt; an unavailable configured pool never
falls back to the anonymous allowance. An unconfigured judge allocation retains
legacy routing. Never switch the global accounting environment to the judge
database.

The bearer credential proves possession, not actual judge identity. Its same
existing value is delivered through the approved private Devpost Additional
info attachment. Anyone receiving a forwarded copy has the same access.
The [original judging access closeout](../reports/judge-access-20261029/README.md)
preserves the earlier configuration, checks and draft-state evidence; the
2026-10-30 receipts above describe the current access policy.

## Public URL and access

**https://headroom.tail45186b.ts.net/**

Visitors use a normal HTTPS browser; they do not need a Tailscale account or
client. Public page, config, health and Results requests were verified with
certificate validation, and the ordinary URL was opened in the owner's Chrome.

The owner's existing proxy initially closed domain-based connections, while the
same proxy reached all three public IPv4 addresses successfully. A local
Clash Verge enhancement now appends a mapping for this exact hostname while
retaining all pre-existing subscription mappings. This is a temporary client
compatibility workaround, not a server requirement. If the published addresses
change or the upstream proxy recovers, refresh or remove that exact host entry.
The original script is backed up beside the local script. See
[deployment evidence](../reports/funnel-deployment-20261028/README.md).

## Runtime boundaries

- `headroom-tailscaled.service` uses official static Tailscale 1.104.4, verified
  against its published SHA256. State and certificates are in the private,
  gitignored `.cache/tailscale/state`; the local socket is under the user's
  mode-0700 runtime directory.
- `headroom-public.service` runs `scripts.serve_public` on `127.0.0.1:8766`.
  It has its own API database, submission and job directories under
  `runs/public-api`, separate from the existing development preview.
- The launcher supports a read-only mode that rejects submissions before
  source preparation or dispatch. The current deployment explicitly enables
  bounded live access and has no replay. Snapshot uploads stay disabled.
- Run uploads have three nonwaiting slots and a 30-second total body-read
  deadline. Full slots return 429; slow uploads return 408. Uvicorn additionally
  uses concurrency 64, backlog 64 and a five-second idle keep-alive timeout.
  These are resource controls, not complete DDoS protection.
- Each target's /out is a tmpfs volume limited to 512 MiB and 4,096 inodes,
  with no writable host output mount. After verified target removal, only
  bounded allowlisted regular artifacts are exported; keeper/volume cleanup
  is verified.
- Public storage admission covers runs/public-api, including submissions and
  jobs. It checks retained logical bytes plus a 1 GiB reservation against
  16 GiB, and requires at least 8 GiB free after that reservation. Checks run
  before persistent admission and again around preparation/export writes.
  This is an application-scope admission policy, not a whole-machine filesystem
  quota or a guarantee against unrelated processes using disk.
- Public health/usage responses omit global financial totals and private
  diagnostic details. The original anonymous ledger/profile remain configured;
  the separately authorized judging receipt selects its own ledger per request.
- Tailscale does not set system DNS, accept routes, advertise routes, act as an
  exit node or enable Tailscale SSH. Cloudflare header trust remains disabled.
- `Linger=yes` and enabled user units allow the services to survive SSH logout
  and start on boot. `funnel --bg` persists the selected HTTPS forwarding rule.
  This is a configuration property; a real machine reboot is not part of the
  non-disruptive deployment check.

## Tailnet isolation before enabling Funnel

Userspace Tailscale can forward ordinary peer traffic to localhost ports.
Do not use the default allow-all tailnet policy on a shared server. Initial
login uses `--shields-up=true`; Funnel refuses to run with shields-up enabled.

For a **new dedicated tailnet with no other devices**, this policy explicitly
denies normal peer traffic and limits Funnel eligibility to the Headroom tag:

```json
{
  "acls": [],
  "grants": [],
  "ssh": [],
  "tagOwners": {"tag:headroom-public": ["autogroup:admin"]},
  "nodeAttrs": [{"target": ["tag:headroom-public"], "attr": ["funnel"]}]
}
```

Do not replace an existing tailnet policy with this template. Preserve unrelated
rules and verify that no wildcard grant still permits access to the Headroom
node. Save and verify the policy and apply the tag before disabling shields-up.
Then enable HTTPS/Funnel as required by the admin console.

## Launch and verify

Use the private local socket for every CLI invocation:

```sh
TS=./.tools/tailscale_1.104.4_amd64/tailscale
SOCKET=/run/user/1000/headroom-tailscale/tailscaled.sock
"$TS" --socket="$SOCKET" status
"$TS" --socket="$SOCKET" funnel --bg http://127.0.0.1:8766
"$TS" --socket="$SOCKET" funnel status
```

The actual bare ts.net hostname belongs in the mode-0600
`.cache/funnel-public.env` as `HEADROOM_PUBLIC_HOST=...`.
Never put node keys, login links, auth keys, or Tailscale state in Git.

Verify public DNS, a trusted HTTPS certificate, the page and Results views,
and current config/health readiness. In read-only mode, verify 503 rejection of
POST /api/runs; the active live mode instead requires a separately bounded smoke
test when one is planned. Read-only checks must cause no GPU/model dispatch or
financial ledger change. Service status alone is not public access evidence. Funnel has
bandwidth limits and is a beta service; it is suitable for a lightweight demo,
not an availability guarantee.

## Operations and teardown

```sh
systemctl --user status headroom-public headroom-tailscaled
systemctl --user restart headroom-public
journalctl --user -u headroom-public --since "10 minutes ago"
"$TS" --socket="$SOCKET" funnel --https=443 off
systemctl --user disable --now headroom-funnel-health.timer headroom-public headroom-tailscaled
systemctl --user stop headroom-funnel-health.service
```

Turning off the dedicated services leaves project code, reports and historical
runs in place. Remove the node from the Tailscale admin console if it is no
longer needed. Do not delete unrelated services, tunnels or account resources.

No notification destination is configured. Human alert delivery remains a
separate acceptance item. The owner later confirmed the public Home opened
within three seconds on a phone using cellular data.

## Official references

- [Personal plan](https://tailscale.com/pricing)
- [Funnel](https://tailscale.com/docs/features/tailscale-funnel)
- [Persistent Funnel command](https://tailscale.com/docs/reference/tailscale-cli/funnel)
- [Userspace networking](https://tailscale.com/docs/concepts/userspace-networking)
- [Deny-all policy example](https://tailscale.com/docs/reference/examples/acls#deny-all)
- [Static packages and checksums](https://pkgs.tailscale.com/stable/)


## Live-access controls

The API implementation limits public anonymous callers to the preset example catalogue. A custom script
requires an operator-configured HEADROOM_JUDGE_TOKEN in the Authorization Bearer
header; public repository cloning is not offered. The token is never included in
public configuration or reports. No judge credential is created by these changes.

Anonymous public admission allows one new attempt per IP per hour, persisted
across server restarts. A server-validated token selects the ready judge route
and exempts that request from the hourly count; invalid, empty or duplicate
credentials are rejected without anonymous fallback. Historical admission rows
are retained. Both routes share one active job and at most two waiting/preparing
jobs. A single 480-second deadline covers source preparation, queue waiting and
execution. The server caps each public request's model allowance at USD 0.30;
no hourly count does not mean unlimited funding or compute.

The dedicated origin trusts Tailscale forwarding only from loopback. It requires
the Funnel marker, HTTPS protocol, expected public host, and exactly one valid
client IP. Tailscale 1.104.4 overwrites these values in its
[proxy implementation](https://github.com/tailscale/tailscale/blob/v1.104.4/ipn/ipnlocal/serve.go#L1144).
Caller-supplied forwarded-address chains and non-loopback origins are rejected.
Do not bind this origin to a public interface or enable generic proxy-header trust.

These controls have focused API coverage. The original public allocation and
later independent judging allocation were activated separately; configuring
access does not itself dispatch a model. See the judging closeout for current
production evidence and the preserved historical live-run reports.

## Health checks and access follow-up (2026-10-29)

The deployed `headroom-funnel-health.timer` checks the actual origin on port 8766
and the public Funnel HTTPS hostname every five minutes after completion. It is
separate from the older local-development health template, which targets 8000.
The fixed-target GET-only script does not accept an arbitrary target URL, follow
redirects, send credentials, call a model, or send notifications. A successful
response slower than three seconds is marked slow rather than unavailable.

Each request has a 15-second total deadline and a 64 KiB response cap. TLS
certificate validation stays enabled. The user service has a 45-second hard
limit and cannot overlap itself. Private state is atomically written to
`.cache/funnel-health.json` with mode 0600; it records safe health status,
latency, the last successful check and consecutive failures. No raw health
payload, private account data, or exception detail is retained. Human alerts
still need a separately configured destination.

```sh
systemctl --user status headroom-funnel-health.timer
systemctl --user start headroom-funnel-health.service
journalctl --user -u headroom-funnel-health.service -n 5
systemctl --user disable --now headroom-funnel-health.timer
systemctl --user stop headroom-funnel-health.service
```

[Follow-up evidence](../reports/funnel-followup-20261029/README.md) records
public/browser checks, independent DNS-over-HTTPS results, the dedicated
Tailscale process restart and the initial live monitor run. The restart retained
its forwarding rule and public access; it was not a shared-host reboot. Earlier
slow requests remain recorded. At that follow-up, a phone cellular-network test was unverified; the owner
subsequently confirmed it loaded within three seconds.

The [official Funnel DNS incident](https://status.tailscale.com/incidents/01M5YVH12FKFH765E1J7PGW4B5)
was under investigation at the follow-up. This hostname resolved correctly in
the recorded Google/Cloudflare checks, so the incident is not established as the
cause of its earlier proxy failures. Visitors do not need a Tailscale client.

## Deployment closeout (2026-10-29)

The [latest closeout receipt](../reports/funnel-closeout-20261029/README.md) separates completed service setup from outstanding acceptance evidence. The physical Chrome Home and Results pages loaded with the owner's existing proxy enabled; explicit-proxy and no-explicit-proxy HTTPS checks both succeeded. No additional visitor-side Tailscale installation is required. The exact-host proxy workaround is still temporary and unchanged.
