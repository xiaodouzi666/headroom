# Tailscale Funnel deployment

This deployment uses a dedicated rootless Tailscale daemon and a separate,
read-only Headroom API process on the existing server. No DNS purchase, paid
hosting plan, credit-card payment, firewall change, or other project's tunnel is
needed. Tailscale Personal pricing and Funnel availability must be checked
against the vendor's current terms.

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
- The public launcher enforces disabled submissions before any uploaded body,
  source preparation, GPU job or paid model dispatch. It does not offer a replay.
  Pages and explicitly published evaluation evidence remain readable.
- Public health/usage responses omit global financial totals and private
  diagnostic details. The existing budget ledger/profile remain configured;
  this deployment does not grant a new spending allocation.
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

Verify public DNS, a trusted HTTPS certificate, the page and Results views, and
503 rejection of POST /api/runs. Confirm no GPU/model dispatch and no financial
ledger change. Service status alone is not public access evidence. Funnel has
bandwidth limits and is a beta service; it is suitable for a lightweight demo,
not an availability guarantee.

## Operations and teardown

```sh
systemctl --user status headroom-public headroom-tailscaled
systemctl --user restart headroom-public
journalctl --user -u headroom-public --since "10 minutes ago"
"$TS" --socket="$SOCKET" funnel --https=443 off
systemctl --user disable --now headroom-public headroom-tailscaled
```

Turning off the dedicated services leaves project code, reports and historical
runs in place. Remove the node from the Tailscale admin console if it is no
longer needed. Do not delete unrelated services, tunnels or account resources.

No notification destination is configured. Human alert delivery and a
phone-network access check remain separate acceptance items.

## Official references

- [Personal plan](https://tailscale.com/pricing)
- [Funnel](https://tailscale.com/docs/features/tailscale-funnel)
- [Persistent Funnel command](https://tailscale.com/docs/reference/tailscale-cli/funnel)
- [Userspace networking](https://tailscale.com/docs/concepts/userspace-networking)
- [Deny-all policy example](https://tailscale.com/docs/reference/examples/acls#deny-all)
- [Static packages and checksums](https://pkgs.tailscale.com/stable/)
