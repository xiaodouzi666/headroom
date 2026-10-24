# Frontend Lighthouse and screenshot evidence

Final local build, measured on azuki with Chrome 151 / Lighthouse 13.5.0. This is recorded-baseline UI evidence, not a successful model repair.

| Page | Performance, 3 fresh profiles | Median | ≥70 on all three |
|---|---|---:|---|
| home | 90 / 90 / 90 | 90 | True |
| baseline-replay-s1 | 89 / 98 / 89 | 89 | True |

390 × 844 mobile emulation, DPR 2, default Lighthouse simulated mobile network / 4× CPU slowdown. All six runs use fresh server-only profiles and the normal Chrome sandbox; GPU is disabled. Raw reports preserve exact configuration and dist hashes.

Home / Results / About / s1 baseline Run were also captured at mobile 390 × 844 and desktop 1440 × 1000. Automated checks found no horizontal overflow, no JavaScript page error, no blocked request and HTTP 200 throughout. The Run view must contain the explicit recorded-baseline notice and a single Baseline chart legend.

No repair was submitted. Browser network logs contain only GET requests to 127.0.0.1:8765. The red OOM chart marker is the recorded baseline event, not an internal UI error. Fresh-profile Results correctly contains no session runs.

The previous 65 / 66 / 66 Home failures, invalid-route measurements, partial screenshots and intermediate chart-label issue are retained under reports/runs, with explicit notices. The original real model workflow acceptance remains open.

## Files

- [Compact machine-readable summary and SHA256 hashes](validation-summary.json)
- [Capture metadata](manifest.json)
- Raw Lighthouse JSON/HTML/traces: reports/runs/lighthouse-20261024T025553Z-final

- [about-desktop.png](about-desktop.png) — 81e96cb1daebdb9a36d2dc9684e59bccffc3c4d240a8451ed2aab6ffedae0e47
- [about-mobile.png](about-mobile.png) — b2ed12873a223cd02785a46a5cdfeba24c0022e41041febaf3df12e43b2f2b55
- [baseline-run-s1-desktop.png](baseline-run-s1-desktop.png) — 5205b2ecbd8c181b0e8b74584d3497da87afd3892814e583264738a84af4d911
- [baseline-run-s1-mobile.png](baseline-run-s1-mobile.png) — cd291d502ce534600c76ef26945b204190341414e7f19c278e07163ca0368272
- [home-desktop.png](home-desktop.png) — 4f98f55e2ffc1b2beab10089d1d2c4f84058fd6f8ecb634f939030ae52b4ee9f
- [home-mobile.png](home-mobile.png) — 1dfbde22e2f12cce04d0eb71fab1283cbd431539de4fa626cfc3091e10011c33
- [results-desktop.png](results-desktop.png) — 583e7c34af86479d48f1457fa18ee503295df92a456b805b099db64c8622c583
- [results-mobile.png](results-mobile.png) — 37e8e92b9960f7955f1b88a0a1ef6d77f39ab3cf98eb89cb607ba66b243d87d7

Method: [Lighthouse CLI](https://github.com/GoogleChrome/lighthouse) and [emulation documentation](https://github.com/GoogleChrome/lighthouse/blob/main/docs/emulation.md).

## Remaining limits

Accessibility remains 96 due to color contrast. The raw Home Speed Index remains about 33 seconds despite FCP 1.4 seconds / LCP 1.7 seconds; its cause was not established in this measurement. The score passes the plan threshold, but this is not a claim that every performance metric is good.

All eight final PNGs were visually checked directly or by exact byte identity to inspected PNGs. There is no observed clipping or internal error banner; the red OOM marker is actual baseline evidence.

Tracked cross-reference: reports/lighthouse-20261024.json. Original T3.2 live model interaction is still unverified.
