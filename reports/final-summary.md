# Headroom delivery status — 2026-10-29

This is the submission preparation report. It does not record a completed Devpost submission, a final video, or the October 30 closing check.

## Current measured outcome

- Fixed nine-scenario latest campaign: **1/9** memory targets, below the unchanged **6/9** requirement. First saved diagnosis round: **7/9** raw category matches and **5/9** fully valid correct diagnoses. The denominator and all historical campaigns are preserved.
- Historical union across eight campaigns: five distinct scenarios have a configured target success; best individual campaign remains three of nine. Numerical and workload-pairing limits differ by scenario.
- Separate real browser s3 demonstration: **73.378694%** peak reduction, 2,435,717,632 → 648,419,840 bytes; 20 updates and 20 exactly matching loss samples, unchanged parameters and matching workload pairing. Pipeline elapsed 49.7025 seconds. This is not added to the fixed-nine campaign.
- Saved-snapshot CLI validation: **0/2** usable diagnoses. The actual Web upload completed transport and accounting but produced an invalid diagnosis. Prompt-length alignment and error preservation have been fixed offline; no paid repeat or new success is claimed.
- Watch detected a real CUDA OOM and triggered automatic diagnosis/repair. The repair failed. Actual terminal output and its independent public Results entry are retained.
- Two extra s2 precision-policy tests and HF Trainer repair failed. No successful precision trade-off card was invented.
- Clean checkout CLI: the first attempt stopped at the missing private configuration prerequisite, before model/GPU work, with zero cost. The independently reviewed recovery then ran the clean checkout's own installed CLI, GPU baseline and three real model calls in 44.363 seconds. It stopped asking for more evidence, without a patch or target success. Its exact cost was $0.075498372, within the unchanged F5 $0.30 cap. The original baseline already satisfied the requested fix-oom condition; this is not counted as a new repair.

## Evidence and implementation

| Work | Evidence |
| --- | --- |
| Latest fixed-nine and three additional tests | [Campaign report](r7-20261029/README.md) |
| 27-request diagnosis comparison | [Ablation](ablation-20261028/README.md) |
| Successful browser demonstration | [Live demo](final48h-live-demo-20261029/README.md) |
| Snapshot transport and outcomes | [Feature runs](final48h-feature-live-20261029/README.md) |
| Watch | [Watch report](watch-demo-20261029/README.md) |
| Clean checkout attempts | [Original F5 result](final48h-clean-20261029/live.md) and [environment recovery](final48h-clean-20261029/recovery.md) |
| Public release | [Deployment receipt](final48h-publication-20261029/deployment.json) |
| User's mobile data check | [Mobile access evidence](mobile-access-20261029/) |
| Versioned documentation numbers | [R7 supplement](final48h-docs-20261029/numbers-r7-v1.json) |

Post-run fixes preserve invalid diagnosis evidence, align the snapshot prompt and actual output limit, add one narrowly scoped zero-dispatch environment recovery, and publish separate campaign/Watch/browser-demo results. Related focused checks passed: 140 snapshot/orchestrator checks, 51 number-verifier checks, 75 recovery checks, 29 Results UI checks and 10 launcher checks. These groups overlap and must not be summed into a unique test count.

The single final offline full regression on source e6cf7a2 completed with 4,182 passed, 185 failed and 18 setup errors in 653.25 seconds. Its failed receipt is retained. Most failures arose from the external guard misinterpreting directory-relative paths or Docker container command arguments; the exact classification and isolated focused checks are in the closing-regression report. Two stale test fixtures were independently reproduced and corrected, with five related checks passing; see the [fixture repair report](final48h-stale-tests-20261029/README.md). It is not a passing regression result, and no second full run is planned.

The guarded follow-up first returned 136 passed / 22 failed; after temporary-project isolation and harness corrections, separate groups passed 16, 3 and 13 checks. The final excluded-node/deadline group returned 9 passed / 1 failed. The short spawn-deadline failure was then addressed by isolating the second preparation in that test fixture while retaining the first real spawn and all original timing/security assertions. The corrected test plus two unchanged real preparation/deadline checks passed 3/3 in 13.60 seconds; see the [deadline fixture report](deadline-fixture-isolation-20261029/README.md). The original full and focused failures remain preserved. The 23 CPU nodes and two guarded historical/shell cases were not fully revalidated. These groups overlap and must not be combined into a new full-suite total. See the [closing regression report](final48h-closing-regression-20261029/README.md).

The number check verified 1,927 claims against present raw sources, with zero errors, including README and Devpost displayed metrics. It is not a complete automated prose audit of every file. The earlier RESULTS history is retained.

## Publication and access

- Latest readability release: upper-right decorative status dot removed, body text enlarged to 18px, secondary text darkened, controls and narrow layouts improved. Frontend 138 and focused backend 66 checks passed; real public browser verification covers five pages, 23 current/historical downloads and an existing completed run detail. Responsive and sampled contrast checks passed. No model/GPU rerun was made and snapshot upload remains paused. See [readability report](frontend-readability-20261029/README.md) and [deployment receipt](frontend-readability-20261029/deployment.json).
- A fresh single navigation of the actual public 18px Home build measured Lighthouse **100 performance / 100 accessibility / 100 best practices / 100 SEO**, with the current CSS/JS response hashes recorded. The measurement used mobile emulation/simulated throttling from azuki through Funnel; it is not a physical-phone or cross-network guarantee. The old 97 score belongs to the historical product build. No submission/model/GPU call occurred. See [current-build Lighthouse evidence](final48h-readability-lighthouse-20261029/README.md).
- Public URL: https://headroom.tail45186b.ts.net/
- Source: https://github.com/xiaodouzi666/headroom — independently confirmed public, with GitHub reporting Apache-2.0.
- The public gallery contains four successes and two failures. Its s3/s4 cards use the latest successful browser-demo/campaign records; the old catalog and previously published download URLs remain available. See [gallery refresh](verified-refresh-20261029/README.md).
- Results now contains the latest nine-scenario campaign and separate Watch/browser-demo observations.
- Frank confirmed the homepage opens within three seconds on phone mobile data. This is user-reported, not an instrumented latency measurement.
- The latest gallery release recovered local health HTTP 200 in 1.359 seconds after service restart. Read-only public checks and responsive browser inspection are recorded separately.
- Five public pages passed the real-browser 390px check with no page, console, or API errors. The gallery refresh additionally verified all 23 current and retained downloads, 12 cited stacks, and both new patches, with 390px layout preserved. The initial 411px Results overflow and its corrected follow-up evidence are preserved.
- Preset examples remain enabled and snapshot uploads paused. The demo admission correction is deployed: each new run is capped at $0.30 within the original shared allocation, rather than incorrectly subtracting all past demos from one $0.30 aggregate. All 48 focused checks passed and an independent code review found no remaining blocking issue. The existing service recovered in 1.771 seconds; public health/config returned 200 with unchanged limits. See [implementation](final48h-demo-budget-correction-20261029/README.md) and [deployment receipt](final48h-demo-budget-correction-20261029/deployment.json). No new live smoke or model call was made.
- Rootless Funnel and the user service remain the deployment path; visitors need no Tailscale client.
- Original clips Part1–5 have been delivered to the user's local Downloads folder. They are source material, not the final narrated video. Part5 includes the final Results page, enabled Home entry and the failed clean-checkout recovery. Its ZIP SHA256 is 56a6cbd380320d3b7b3c4ec7c04f6ece4f46a95baf36483f520961e1f898a0ec. A supplemental 42.84-second gallery clip now shows the refreshed s3/s4 cards; headroom-gallery-refresh-20261029.zip was delivered with matching local/server SHA256 febc63add2414f0f55b1b0b7e6d5e39c021101fcf6aaf22b43d0d92cfa03f0f6.

The supplementary Part 6 has also been delivered with matching SHA256: four
1920×1080 clips totalling 120.08 seconds show the new typography and existing
Home/Verified/Results/s3 details. This is read-only footage, not a new live run;
Part 4 remains the actual submission recording. See [delivery receipt](final48h-readability-clips-20261029/delivery.json).

## Funding

The sole FINAL_48H allocation remains $6.43 net / $7.79 gross, gift credit only, no recharge. After the clean-checkout recovery, the conservative charged total is $2.067736672. Some complete actual costs remain unknown; bounds are not relabelled as actual provider bills. The two browser demonstrations together account for $0.06952418. The plan's $0.30 is a per-run limit, not a user-approved aggregate allowance. The corrected default v2 binding is deployed; the previously calculated $0.23047582 is not an authorized remaining aggregate budget. Remaining shared net allowance is $4.362263328. Deployment created no allocation, claim or model attempt; before/after logical hashes match for every registry and old/new accounting table, and receipt/profile/environment bytes are unchanged. Historical records and previous unknown costs remain intact.

A fresh authenticated provider-balance check on 2026-10-29 confirmed that the account remains above the planned $8 reserve. The amount and transaction details are retained in a private receipt. The separate Builder grant was then located and redeemed through the provider promo-code interface; the new gift transaction and increased balance were visibly verified. The promo email states credits do not expire once applied. No card payment or new allocation was made; the approved total allocation and per-run limits remain unchanged.

## Remaining user-dependent steps

1. Finish the local Opus edit, at most 170 seconds, using real footage and the current result wording; upload the final video as Public and provide its URL.
2. Replace the video placeholders and complete Devpost. Record the actual project URL and Submitted confirmation.
3. Agree the judging-period access and gift-credit allowance. The existing judge credential and instructions have already been supplied through the verified private Additional info attachment, after Frank's explicit approval. Current shared request/spending limits have not been confirmed to satisfy the [official access wording](submission-requirements-20261029.md); this is an unresolved arrangement, not a disqualification determination.
4. Perform the planned closing availability and account-balance check before the deadline. The judging period ends on December 16 at 04:00 Beijing time.

The original 6/9 repair requirement and saved-snapshot validation remain unmet. Publishing a report, creating a tag, passing offline tests, or preparing submission fields does not change those outcomes.

## Devpost draft saved — 2026-10-29

The existing entry is now named Headroom and its project story, links, tags and technical feedback are saved. The [project preview](https://devpost.com/software/headroom-8vfuwj) explicitly shows INCOMPLETE SUBMISSION; the workflow remains DRAFT / 3 of 5 steps. The supplied personal declarations and career-value response are saved. The approved Home image and private judge attachment are uploaded and verified. Moderate learning is saved; no IRL city is claimed because Frank confirmed no attendance. The final video, judging-period access arrangements and final submission remain pending. The actual form and saved fields are recorded in [the draft report](devpost-draft-20261029/README.md).

## Scheduled closing check

A one-off task is scheduled for October 30 at 16:00 Beijing time, within the
planned F8 window. It will check service/Funnel/public access, reserve, final
links and publication, and run the one remaining F8 live smoke only if the
existing authorization and readiness checks allow it. It must not repeat this
turn's full regression or create a new spending allowance. Scheduling is not
evidence that F8 has completed.
