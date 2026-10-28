# Results page: measured diagnosis comparison

The staged Results page retains the existing historical repair view and adds a separate three-condition diagnosis table after it. Its metrics are copied without recalculation from [the published experiment data](../ablation-20261028/ablation.json). First-cause matches (6/9, 2/9, 6/9) and valid, correct first causes (4/9, 2/9, 4/9) are separate columns. Both unknown reference causes remain in each denominator of nine. The text explains the single-pass scope, elapsed-time definition, provider-reported input counts, cache discounts and tax exclusion. It does not turn diagnosis matches into repair successes.

Only web source/static JSON changed; no application Python, prompts, scripts or dependency locks changed. No model, GPU or submission request was made.

## Verification

- Two new component tests passed. They check the exact source SHA and every displayed data field, fixed denominators and metric wording.
- The 26 App and 28 EvaluationView tests passed. An initial new-test file-URL issue was fixed in the test harness; the 54 passing existing tests were not rerun.
- TypeScript, Prettier, scoped secret scan and the requested frontend literal scan passed; the literal scan has zero matches.
- The production build completed in `.cache/final48-ablation-dist-20261029`. Vite only noted that this separate output directory is outside web/. Hashes confirm `web/dist` remained unchanged throughout the build.
- No browser visual check or production deployment was performed. The root task can review/deploy the staged bundle after the active recording.

See [receipt.json](receipt.json), [focused-tests.txt](focused-tests.txt), [build.txt](build.txt), and [online-dist-unchanged.json](online-dist-unchanged.json). Source links point to the real report/data paths in the public repository and will resolve to this experiment after the root task pushes its report commit.

## Deployment and first browser pass

The staged build was published without restarting the backend. The five routes rendered at 390px without page overflow, and the measured comparison appeared with the expected values. API health and run-list requests returned 500 during the separate SQLite incident, so the overall browser check is failed pending database recovery. See deployment.json and browser-check.json; these initial records will be retained.

## Recovery check and copy correction

After the database recovery all five routes passed the same read-only browser check: HTTP 200, no console/page errors, no failing API requests and no page overflow at 390px. The original failed check remains unchanged. See recovered/browser-check.json.

Visual inspection found an old historical-results sentence saying the diagnosis comparison was unavailable. That sentence now says the diagnosis-only measurements are reported separately; all result data is unchanged. Node 18 could not build the current Vite version; the existing pinned Node 24.22.1 runtime built successfully and the corrected static assets were deployed without a backend restart.
