# FINAL_48H interface and public access preparation

This increment prepares the read-only product interface and the bounded public-run path. It adds no model/GPU repair result and no spending allocation.

## Verified work

- Home, Run, Results and About use product-facing explanations. Historical campaign details and unknown measurements remain available; failed runs are not hidden.
- The public API permits anonymous preset examples only. Custom scripts need a separately configured judge token, which is not exposed in configuration or persisted by the UI. Public repository submissions remain unavailable.
- Public admission enforces one attempt per IP per hour across restarts, at most two waiting/preparing jobs beside one worker, a 480-second total deadline, and a USD 0.30 model allowance. The deployed launcher continues to force submissions off.
- The curated gallery contains four historical target-met runs and two unresolved workloads. Each initial diagnosis binds to its captured request, original evidence and matching stack frames/bytes. See [data selection](../verified-preparation-20261028/README.md).
- Five pages and expanded stack/patch views fit a 390px viewport without page-level horizontal overflow; wide tables scroll inside their own containers. See [responsive check](responsive-390.json).
- One isolated mobile Lighthouse audit scored performance 97, accessibility 95, best practices 100 and SEO 100. Its simulated network is not a physical mobile-network test; [receipt](lighthouse-receipt.json) pins the audited build.

## Validation scope

The integrated backend check passed 111 focused tests in 34.47s. Subsequent bounded-reader path protection passed 22 focused tests; the run-directory fallback fix passed six route tests. Counts overlap and are not a combined total. Frontend integration passed 88 focused tests before the final gallery wording correction; that correction passed seven gallery tests. TypeScript and production Vite build passed. Final source/scan and public deployment checks are recorded separately below.

The source text scan still finds legacy API keys, value mappings, and negative test strings. This is not a passing result for the plan's literal grep-zero condition. Those strings are not displayed as public budget/account/debug panels.

## Remaining acceptance

The gallery is enabled only in a temporary private loopback preview; public activation still awaits the owner's separate decision. The public launcher keeps all live submissions disabled. The new running-pool amount, a real public example, independent phone-network timing, machine reboot, human alert delivery, final video and submission checks remain outstanding. Existing campaign outcomes and the fixed nine-scenario requirement are unchanged.

## Public update and transport follow-up

The new read-only UI is deployed at https://headroom.tail45186b.ts.net/. The public origin restarted in 3.838 seconds; session/run records and the financial database were unchanged, with zero public jobs. Both live submissions and the gallery remain explicitly disabled by the public launcher, even if a gallery environment flag is present.

The [first public check](public-update.json) contains three 20-second connection timeouts and is correctly marked failed. The [follow-up](public-followup.json) then reached all three affected routes with HTTP 200 and valid TLS in 0.16–0.22 seconds. An additional address comparison reached all three published IPv4 relays; this did not isolate a persistent bad relay. The owner's existing proxy also reached Results with valid TLS in 1.19 seconds. The transient failures are retained and do not establish continuous availability.

[Chrome homepage screenshot](../../docs/media/final/home.png) records the deployed interface. No visitor Tailscale client is required. The owner's exact-host proxy workaround remains temporary; independent mobile-network acceptance is still outstanding.

The API request allowance is clamped to USD 0.30. This offline check is not proof of a final bill ceiling; model-output bounds and shared-pool admission must be verified before live public runs are enabled.

Final changed-file [secret scan](source-scan.json): 58 files, zero findings. Final catalog + route integration: 28 tests passed in 1.87s after the nanoGPT correction; the public-launcher check passed five tests after explicitly disabling the gallery. These overlap earlier tests.
