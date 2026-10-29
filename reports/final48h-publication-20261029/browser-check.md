# Public publication browser check

Result: passed. Public HTTPS, Chromium at 390 × 844, a new anonymous session, and GET/HEAD requests only.

The five evaluation APIs retain 9/9/9/1/1 rows for the latest evaluation, the two previous evaluations, Watch, and the independent browser demonstration. The latest result defaults to one repair among nine; the page distinguishes seven raw category matches from five valid correct diagnoses. Watch is labeled as an OOM trigger with an unsuccessful repair. The independent s3 browser run remains a separate successful demonstration.

| Page | HTTP | Width / viewport | Horizontal overflow |
| --- | --- | --- | --- |
| home | 200 | 390 / 390 | False |
| verified | 200 | 390 / 390 | False |
| run | 200 | 390 / 390 | False |
| results | 200 | 390 / 390 | False |
| about | 200 | 390 / 390 | False |

Console errors: 0; uncaught page errors: 0; failed HTTP responses: 0; failed requests: 0. Live repair and snapshot submissions remained paused.

This check did not submit work, invoke a model or GPU workload, change configuration, or use a saved owner session. It checks this remote browser path; it does not establish every visitor's mobile network route.

[Machine-readable receipt](browser-check.json)

The final check uses the configured 390px viewport, so mobile Chromium cannot hide overflow by expanding innerWidth. Document width, body width, and innerWidth are all 390px on all five pages. The latest result explicitly displays “1 of 9 workloads met the memory target.” The earlier 411px selector failure remains preserved in [the pre-fix receipt](browser-check-before-layout-fix.json) and [overflow investigation](overflow-investigation.json); [the deployment receipt](mobile-layout-deployment.json) records the fix rollout.
