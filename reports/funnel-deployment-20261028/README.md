# Headroom public deployment — 2026-10-28

Demo: https://headroom.tail45186b.ts.net/  
Results: https://headroom.tail45186b.ts.net/results

**The read-only deployment passed verification.** This check adds no model/GPU repair success and does not authorize new spending.

- [Public HTTPS receipt](public-check.json): azuki accessed the original DNS hostname without a fixed-IP override or HTTP proxy. Homepage, Results, config, examples, health, and both evaluation detail endpoints returned 200 with valid TLS. Valid and malformed JSON submissions both returned 503; no public task appeared.
- Only `headroom-public.service` was restarted to load the latest evidence; it became ready in 1.249 seconds. Both public-app and Tailscale user services were enabled/active, linger was enabled, and Funnel matched HTTPS 443 → `127.0.0.1:8766`.
- Public API database, job inventory, and budget-ledger digests remained unchanged. Health was checked against its public field allowlist; provider reachability did not include an authenticated model call.
- Published R5 remains **3/9** and R6 **2/9**, both below the unchanged **6/9** gate. Both have nine unique scenarios. Served identifiers, evidence fields, and source pins matched the curated publication, including s4's corrected numerical basis.

[Mac proxy receipt](mac-proxy-check.json), [Chrome home](chrome-public-home.png), and [Chrome Results](chrome-public-results.png) document ordinary-browser access. This Mac needed a temporary exact-host IPv4 mapping in its existing Clash script, preserving other host entries and proxy selection. Refresh/remove the mapping if DNS changes or the upstream proxy recovers; backup and rollback are recorded in the receipt and [deployment guide](../../docs/FUNNEL.md). The server-side public check did not use that mapping.

[Focused scan receipt](focused-check-receipt.json), [findings](focused-check-findings.json), and [log](focused-check.log) retain the earlier 20-file, zero-finding snapshot. Its hashes define its scope; it predates the final receipts/documentation and is not a scan of the final commit. [origin-check.json](origin-check.json) retains the earlier loopback-only stage.

**Remaining limits:** submissions are intentionally disabled; no independent mobile-network check, machine reboot, or human alert delivery was tested/configured. Funnel availability and bandwidth remain external dependencies.

## Final publication scan

[Final scan receipt](final-publication-scan.json) records the reviewed changed-file snapshot. One earlier generic-key match was verified to be the SHA256 of tests/test_api.py in the scan manifest, not a credential. The public manifest now represents paths and hashes in separate fields; the original private receipt remains intact.
