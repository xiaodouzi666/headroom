# Verified runs publication — 2026-10-29

Published the authorized read-only historical gallery at **https://headroom.tail45186b.ts.net/verified**. It contains four recorded repairs and two unresolved workloads. The original first-round diagnosis, bound stack evidence, measurements, patches and reports are inspectable. Replay animation was not restored.

## Verification

- Existing preparation check passed: 18 files, four target successes and two failures. Published measurements, diagnosis bindings and stack contents match those prepared files.
- Public HTTPS /verified, /api/config, /api/verified, /api/health and all **17 downloadable artifacts** returned 200 with certificate verification. Every downloaded byte length and SHA256 matched the prepared catalog. The 18-file total includes the catalog itself; it does not mean 18 downloads.
- Physical Chrome rendered all six cards. Clicking the first s3 stack showed its initial-capture frames, 830,472,192 live bytes at the recorded peak and 19,126,026,240 lifetime allocated bytes, separately labelled. [Published page screenshot](chrome-verified.png).
- s2 retains tolerance-based losses and unknown pairing; s4 retains its five compared losses and twenty candidate updates. Both unresolved cards remain failures. nanoGPT has no code patch download because the recorded change was configuration-only.
- The seven launcher checks passed in 1.06 seconds; Ruff, format and whitespace checks passed. No frontend build was needed because its code/assets were unchanged.
- The dedicated application restarted and origin health returned after 1.389 seconds. A subsequent process check found it active/running. Other services were not restarted.

## Changes and restoration

The launcher now uses the existing HEADROOM_VERIFIED_RUNS_ENABLED setting, whose default is false, instead of hard-coding the gallery off. Its test covers default, explicit false and explicit true. Run submission and snapshot submission remain explicitly disabled; public judge scripts remain unavailable.

Only the dedicated user-service drop-in ~/.config/systemd/user/headroom-public.service.d/verified.conf was added, setting HEADROOM_VERIFIED_RUNS_ENABLED=true. To close the gallery again, set that value to false, run systemctl --user daemon-reload, then restart headroom-public.service. Its disabled state is visible in /api/config, and /api/verified should return 404.

No historical records, curated data, frontend assets, experiment preparation packages or spending settings were changed. No new model/GPU workload, allocation or payment was made. The main task owns the final source commit and the required refresh of the repair experiment's source pins.

Detailed HTTP, asset, configuration and process evidence: [receipt.json](receipt.json).
