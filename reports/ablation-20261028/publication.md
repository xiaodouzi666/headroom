# Diagnosis comparison publication

The completed study is now included in README, Results, the Devpost draft and the Results page. Primary category matches remain separate from fully valid correct diagnoses; historical repair counts and the original Results history are unchanged.

The document checker verifies all three measured rows against the frozen public JSON, including both scores, the fixed denominator, input means, costs and elapsed times. The 33 focused document-check tests pass, including rejected swapped scores, changed costs and source tampering. Existing frontend checks cover 56 relevant tests and the production build.

The frontend was deployed without a backend restart. All five public routes rendered at 390px without page overflow. This first browser pass was not accepted as fully healthy: the ongoing SQLite incident caused three API 500 responses. Its screenshots and failed receipt are retained under reports/final48h-ablation-ui-20261029; a new pass is required after database recovery.
