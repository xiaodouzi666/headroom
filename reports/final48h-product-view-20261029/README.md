# Product view implementation — 2026-10-29

Implemented an explicit `product-v1` response view for the web client. JSON requests use `X-Headroom-View`; SSE uses the matching query parameter. Existing API consumers and ordinary report/patch downloads keep the original contracts and bytes.

The product view gives queue state the `paused` name, gives evaluations `suite_result` / `comparison_scope` / `threshold_met`, and maps system reasons to finite product messages. API error details are no longer copied into browser alerts. Scientific diagnosis/evidence, numerical values, source bindings and exact patch content are preserved, including the newly added numerical requirement evidence. One exact historical protocol note is rephrased in ordinary language while retaining its missing-reference limitation; all original report download bytes remain unchanged. A busy public worker also now counts toward queue capacity when represented as a boolean.

The exact requested source scan returned **zero matching lines** across `web/src`; no scan exclusions, string splitting, encoding or file moves were used. Frontend fixtures now represent the product contract. Raw-input transformation tests live at the new backend projection boundary.

Validation: **80 API/projection tests, 135 UI tests**, Ruff and `git diff --check` passed. TypeScript and Vite build passed into **`.cache/f2b-product-dist`**. See [the receipt](receipt.json) for commands, source pins and asset hashes.

This is an offline implementation receipt. No model, GPU or financial operation ran; no production service, frontend distribution, submission switch or deployment was changed. Root review and a separate deployment decision remain necessary.

Final root review checked five pages at an actual 390-pixel Chrome viewport, with no page-level horizontal overflow, visible forbidden terminology or console errors. The real curated stack citation expanded to 830,472,192 peak bytes and its frames; the patch rendered. A separate private copy of the existing s3 run displayed its actual 20 events, model badges/times/cost states, chart, diff and verification tables. Its request binding was deliberately not copied, so its stack detail correctly remains unavailable; this is not a new live run. See ../final48h-product-browser-20261029/layout.json and historical-preview.json. Home Lighthouse was 97/95/100/100. Final API/projection rerun: 80 passed in 15.53 seconds.

## Subsequent read-only publication

After the frozen implementation commit ab8b4f3, the reviewed build was deployed with the new backend first, old hashed assets retained, and index.html replaced atomically. The origin recovered in 1.190 seconds after its service restart. Public Home, Run, Results, About and both health representations returned 200; the public HTML matched the reviewed build. Physical Chrome loaded the new homepage and nine result rows without console errors. Verified runs, live submissions, snapshot submissions and judge scripts remain disabled. The private preview and local SSH forward were stopped afterward. No model/GPU execution or funding change occurred. See deployment.json and ../final48h-product-browser-20261029/public-home.png.
