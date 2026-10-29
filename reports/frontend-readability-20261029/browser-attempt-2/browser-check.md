# Public frontend functional and readability checks

Result: needs review.

Public HTTPS, Chromium 156.0.8078.4, anonymous sessions, no real POST, no model or GPU run.

| Check | Evidence | Result |
| --- | --- | --- |
| Public configuration and readiness | real_public | Passed |
| Five-page navigation and active-page state | real_public | Passed |
| Home calls to action and paused snapshot | real_public | Passed |
| Verified cards, cited stacks, diffs and current/historical downloads | real_public | Passed |
| Results campaigns, detailed measurements, rounds, ablation and downloads | real_public | Passed |
| Run scenario, target, policy, search and judge-script controls | real_public | Failed: Locator.uncheck: InvalidSelectorError: Error while parsing selector `checkbox[name=/Allow batch / accumulation changes/]` - unexpected symbol "a" at position 29 during parsing attribute value     at syntaxError (<anonymous>:2048:11)     at readAttribute (<anonymous>:2180:7)     at parseAttributeSelector (<anonymous>:2193:28)     at Object.queryAll (<anonymous>:5527:22)     at InjectedScript._queryEngineAll (<anonymous>:7241:49)     at InjectedScript.querySelectorAll (<anonymous>:7228:30)     at eval (eval at evaluate (:370:30), <anonymous>:2:42)     at UtilityScript.evaluate (<anonymous>:372:16)     at UtilityScript.<anonymous> (<anonymous>:1:44) Call log:   - waiting for internal:role=checkbox[name=/Allow batch / accumulation changes/]  |
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
- 200% uses CSS zoom on the served page. A separate 720 CSS-pixel viewport tests the reflow width corresponding to a 1440-wide desktop at 200%; device pixel ratio remains 1. These are not an operating-system magnifier or browser chrome zoom test.
- About external destinations were checked as rendered links, not exhaustively fetched.

[Machine-readable receipt](browser-check.json)
