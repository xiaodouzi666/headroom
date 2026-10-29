# Public frontend functional and readability checks

Result: passed.

Public HTTPS, Chromium 156.0.8078.4, anonymous sessions, no real POST, no model or GPU run.

| Check | Evidence | Result |
| --- | --- | --- |
| Public configuration and readiness | real_public | Passed |
| Five-page navigation and active-page state | real_public | Passed |
| Home calls to action and paused snapshot | real_public | Passed |
| Verified cards, cited stacks, diffs and current/historical downloads | real_public | Passed |
| Results campaigns, detailed measurements, rounds, ablation and downloads | real_public | Passed |
| Run scenario, target, policy, search and judge-script controls | real_public | Passed |
| About content and external links | real_public | Passed |
| desktop home readable layout | real_public_render | Passed |
| desktop verified readable layout | real_public_render | Passed |
| desktop run readable layout | real_public_render | Passed |
| desktop results readable layout | real_public_render | Passed |
| desktop about readable layout | real_public_render | Passed |
| mobile home readable layout | real_public_render | Passed |
| mobile verified readable layout | real_public_render | Passed |
| mobile run readable layout | real_public_render | Passed |
| mobile results readable layout | real_public_render | Passed |
| mobile about readable layout | real_public_render | Passed |
| zoom200 home readable layout | real_public_css_zoom_200_percent | Passed |
| zoom200 verified readable layout | real_public_css_zoom_200_percent | Passed |
| zoom200 run readable layout | real_public_css_zoom_200_percent | Passed |
| zoom200 results readable layout | real_public_css_zoom_200_percent | Passed |
| zoom200 about readable layout | real_public_css_zoom_200_percent | Passed |
| Synthetic submission validation, 429 handling and token clearing | mock_network_not_backend_or_model_validation | Passed |

## Coverage limits

- No paid model/GPU rerun; existing model repair failures are unchanged.
- No real script submission, judge token authentication, owner run detail/SSE/cancellation or snapshot upload was exercised by this anonymous read-only suite.
- Mock request checks exercise browser behavior only. Unit/component tests cover additional timeline, report and snapshot states separately.
- 200% uses CSS zoom on the served page. A separate supplemental 720 CSS-pixel viewport at DPR 2 tests the reflow width/pixel density corresponding to a 1440-wide desktop at 200%. These are not an operating-system magnifier or browser chrome zoom test.
- About external destinations were checked as rendered links, not exhaustively fetched.

[Machine-readable receipt](browser-check.json)

## Additional checks after this suite

The [owner suite](owner-browser-check.json) separately verifies an existing completed real run, and the [supplement](browser-readability-supplement.json) adds tablet/reflow and text-contrast checks. The three About destinations subsequently returned HTTP 200 in [external-links.json](external-links.json). These do not add a new paid run or live upload.
