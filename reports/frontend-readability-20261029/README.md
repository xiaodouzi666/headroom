# Frontend readability and public workflow verification — 2026-10-29

The requested frontend changes are implemented and deployed at
[Headroom](https://headroom.tail45186b.ts.net/). This report covers frontend
functionality and readability, not a new model/GPU repair campaign.

## Changes

- Removed the decorative upper-right status dot and its “Evidence first” label.
- Increased the default body size to 18px; navigation and form text are 18px,
  with 16.2px secondary controls and 14.4px small labels. Chart ticks use 14px;
  chart legends/tooltips use 16px. Relative CSS sizes respect user font settings.
- Increased line height, darkened low-contrast text, enlarged button targets,
  and made navigation, fields, evidence rows and controls wrap at narrow widths.
- Fixed a genuine About architecture-grid overflow found under CSS 200% zoom.
  The grid now fits available width. Large data tables scroll within their own
  containers instead of widening the page.
- Corrected a stale offline launcher test fixture to match the current
  publication-manifest schema. Production startup checks remain unchanged;
  missing or fake authorization receipts are still rejected before listening.

## Verification

| Check | Result | Evidence |
| --- | --- | --- |
| Frontend unit/component suite | 138 passed in 9 files | [Log](frontend-tests.log) |
| Focused backend routes, ownership, startup and static serving | 66 passed | [Checks](backend-checks.json), [log](backend-tests.log) |
| Production build | Passed using pinned Node v24.22.1 | [Build log](build.log) |
| Public browser workflow suite | 23 checks passed; 153 real GETs, no real POST | [Receipt](browser-check.json), [coverage](browser-check.md) |
| Public gallery and retained downloads | 6 cards, 54 stack toggles, 5 patch toggles; 23 distinct current/historical downloads match SHA256 | [Receipt](browser-check.json) |
| Existing real run detail | 21 timeline events, chart, 11 stack toggles, 10 details, 6 downloads; 4 layouts passed | [Owner check](owner-browser-check.json) |
| Responsive layouts | 25 public-page layout states plus 4 existing-run layouts passed | [Main](browser-check.json), [supplement](browser-readability-supplement.json) |
| Text contrast sampling | Passed for 5 public pages and the existing run detail | [Supplement](browser-readability-supplement.json) |
| About official-source links | All 3 destinations returned HTTP 200 | [Links](external-links.json) |

The functional pass includes Home links; navigation/current-page state; all 9
example configurations; 3 target modes, 2 search modes and policy controls;
judge-script fields; all 5 Results selections and expandable measurements;
the ablation table; Verified cards, cited stacks, patches and downloads; and
the previously completed real run's timeline, diagnosis, memory chart,
verification, diff, sources and files. Anonymous run history stays private.

Public layouts cover desktop 1440px, phone 390px, tablet 768px, CSS zoom 200%,
and 720 CSS pixels at DPR 2. The last setting approximates the layout/pixel
density of a 1440px desktop at 200%; it is not an actual browser-toolbar zoom
action. Stable page widths fit their viewports. Text contrast samples use
visible direct text against composited solid ancestor colors, excluding
disabled controls; gradients, images and pseudo-elements are outside this
check. This is not a complete accessibility certification.

The public and owner suites recorded no real HTTP, page or console errors.
Two intentional mock submissions test validation, a synthetic 429 response
and token clearing; those requests never reach the server. Their two expected
console messages are reported separately. Unit/component tests cover further
SSE/reconnect, report, form and snapshot states.

## Real versus simulated coverage

No new model call, GPU job, paid repair, live cancellation, judge-token
authentication or snapshot upload was triggered in this round. Snapshot
submission remains paused and its paused state is tested. The owner detail
uses the original project-generated test session for an existing completed
run, mounted read-only; no cookie or session secret is published. This is
historical result rendering, not a rerun or a Replay feature.

The first backend test pass recorded 65 passing tests and one stale-fixture
failure; [that log](backend-tests-initial.log) is preserved. Browser attempts
and the About overflow screenshot are retained in this directory. An initial
run-detail width reading was taken before the chart's resize observer had
settled; after waiting for reflow and two animation frames, phone width fits.
The original reading is retained, and no CSS overflow hiding was added to
conceal it.

## Deployment and screenshots

[Deployment receipt](deployment.json) binds the deployed assets to source-file
SHA256 values. Content-hashed assets were copied first and the index replaced
atomically. Previous assets remain available. No backend restart was needed;
health returned HTTP 200. Browser tools and script hashes are recorded in
[browser-reproduction.json](browser-reproduction.json); temporary execution
scripts remain in the server's private cache.

Final main assets: index-Bx8W0QPJ.css and index-BvZbRzgV.js.

- [Desktop Home](desktop-home.png) / [phone Home](mobile-home.png)
- [Desktop Run](desktop-run.png) / [phone Run](mobile-run.png)
- [Desktop Results](desktop-results.png) / [phone Results](mobile-results.png)
- [Desktop Verified](desktop-verified.png) / [phone Verified](mobile-verified.png)
- [Desktop About](desktop-about.png) / [enlarged About](zoom200-about.png)
- [Existing run desktop](run-detail-desktop.png) / [phone](run-detail-mobile.png)

The tracked docs/media/final/home.png is refreshed from desktop-home.png.
Earlier raw video clips retain their original visual styling and measured
outcomes; they are not newly recorded or the final edited submission video.

## Whole-project acceptance remains incomplete

The latest fixed-nine campaign remains **1/9**, below the unchanged **6/9**
requirement. Saved-snapshot diagnosis remains **0/2**. The extra s2 precision
tests, HF repair and Watch repair failed; clean-checkout recovery ended asking
for more evidence without a patch. The separate successful s3 browser demo
is not added to R7. All historical results and original plans are preserved.

Final video, Devpost submission, judging-period access arrangements and the
scheduled closing checks are separate remaining delivery work. See the
[current delivery report](../final-summary.md). Frontend test success does
not establish full product or competition acceptance.
