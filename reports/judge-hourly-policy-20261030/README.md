# Judge hourly policy and upload admission protections

Base source: 6d5cd7d15fc5cc27a689686e468e4ad5792ac5d8. These are focused offline checks, not a new full regression or a production execution.

## Behavior

- Only the server-selected, credential-validated judge route skips the hourly run count. Anonymous access retains one admission per IP per hour. Invalid, empty, duplicated or wrong Bearer headers are rejected; request bodies cannot select funding, binding, paths, runtime profiles, hourly exemptions, or daily allowance.
- The original admissions table and all historical rows remain unchanged. A separate hourly_exempt_admissions table marks only new judge admissions. Admission and its exemption marker commit in one transaction. Historical admissions retain their previous conservative counting semantics.
- Both routes keep the shared execution queue and capacity of one active plus two waiting/preparing runs, the 480-second public execution deadline, and the 0.30 USD per-run allowance. A valid token does not bypass unavailable allocation, queue capacity, sandbox policy or cleanup.
- Preparation uses the judge controller's effective_daily_limit_usd rather than changing the original receipt or shared settings/environment. Invalid effective allowance fails with 503 before admission. Config and health expose an explicit hourly_limit_applies flag and nullable runs_per_ip_per_hour, not tokens, private paths or grant amounts. Token possession is not identity verification.
- The UI reads the credentialed health policy, keeps the token only in component state and clears it after submission. Its wording says that no hourly run-count limit applies; runtime, queue and spending limits remain. An invalid credential or failed refresh clears this policy. GPU-busy and queue-full states still disable submission.
- Run upload body reading is limited to three nonwaiting application-level slots and a total 30-second deadline (configurable only downwards). The slot is acquired after authentication, submission availability and origin validation, before body parsing or queue admission. A fourth active upload receives 429; a slow total upload receives 408. Disconnects, cancellation and size errors release the slot without consuming an IP admission. Size is checked before extending the buffer.
- Snapshot uploads keep their existing independent uploading/queued/running capacity of three and total deadline; they are not changed to share this semaphore. The two paths are therefore independently bounded, at most six active uploads combined. Snapshot submission remains disabled in the production deployment configuration managed by root.

## Evidence

- backend-initial.log/json: initial hourly-policy check, 71 passed and 2 real-binding tests deselected, 21.33 seconds pytest time.
- backend-final.log/json: 79 passed in 24.86 seconds, exit 0. Includes real judge binding with fake SDK MockTransport in thread and spawned-process modes, hourly/pool isolation, legacy history, actual prepared daily allowance, invalid effective allowance, and five in-memory ASGI upload cases (slow dripping, capacity, cancellation, disconnect, oversize).
- Each backend run begins with the unchanged v4 guard's parent and spawned-child negative probes: provider environment absent; production secrets/profiles/DBs, network/DNS, GPU commands and unsafe Docker options denied. Test files use temporary roots and offline workers; no provider calls, GPU jobs, production POSTs or production database mutations were performed by this agent.
- frontend-initial.log and frontend-initial-checks.json preserve the first 29-pass/1-fail result. The added busy-GPU fixture omitted the real API's status=busy field; only that fixture was corrected. The product gate was unchanged.
- frontend.log and frontend-final-checks.json: 30 passed, TypeScript typecheck exit 0, staged production build exit 0. These are jsdom component tests, not a new real-browser or Lighthouse run.
- static-checks.log/json: scoped Ruff, format check and git diff whitespace checks.
- source-before.json retains the initial candidate hashes; source-tested.json records the final tested API/UI sources before the separately assigned cleanup_owned_lab safety patch. Future changes to that function need their own validation.
- The staged bundle is in .cache/judge-hourly-review-20261030/web-dist; its hashes are recorded in frontend-final-checks.json. Production web/dist was not overwritten.

## Scope and remaining boundaries

No deployment, commit, push, paid call or GPU work was performed by this agent. A separate security fix for bounded artifact storage and owned-volume cleanup is being developed by other agents; the 79-pass receipt does not certify that later patch. Grant extension/activation is also managed separately. Public reachability and config readiness are not proof of a successful new model run. Existing empirical acceptance failures are unchanged.

## Public preparation and listener follow-up

The API preparation wrapper now applies only when public_host is set. It verifies that the upload data root belongs to storage_scope(run_root), then holds storage_admission(run_root, aggregate=True) while creating the prepared source. The public layout resolves to runs/public-api, covering both submissions/uploads and jobs; local development retains its previous repository-preparation contract.

prepare-storage-backend.log/json preserve the first 79-pass/3-fail observation: the changed cleanup contract needed an isolated legacy discovery fixture, while applying the new public storage wrapper to local fixtures conflicted with existing local concurrent repository preparation and separate evidence roots. The final public-only scope and unchanged local semantics are covered by prepare-storage-final.log/json: **82 passed in 26.01 seconds**, exit 0, all seven recorded source hashes stable. Three new checks explicitly cover existing-upload census, capacity refusal before writing, and rejection of an upload root outside the bounded scope.

scripts/serve_public.py alone now configures Uvicorn with limit_concurrency=64, backlog=64 and timeout_keep_alive=5. The local development launcher is unchanged. public-launcher.log/json record **10 passed in 1.36 seconds**, exit 0, source hashes stable. These are global concurrency/backlog/idle keepalive controls, not complete DDoS protection; neither these settings nor the three upload slots prove arbitrary slow connections cannot affect availability.

These follow-up groups overlap earlier receipts; do not sum them into a unique/full-suite count. The separately assigned artifact-volume implementation has its own unit/CPU-Docker checks and independent review.

## Refuse full public storage before persistent admission

A final API preflight now invokes the same aggregate storage admission check in a worker thread immediately before queue.submit. Full, busy or unsafe storage returns 503 with Retry-After: 60 before any admission row, exemption row, job record or upload is created. The check is nonwaiting on the shared file lock, its census has a fixed entry bound, and it runs outside the ASGI event loop. Preparation and export still repeat their checks while holding the lock around bounded writes; the preflight is not used as a substitute for those checks.

storage-pre-admission.log/json record **11 passed in 2.54 seconds**, exit 0, source hashes stable, with parent and spawn safety probes passing. The focused set verifies five repeated valid-token requests and five anonymous requests at full capacity return 503 with unchanged admission database bytes, zero admission/exemption/job rows and no job/upload filesystem growth; a deliberately delayed census leaves health responsive. Healthy judge admission, anonymous quota, global queue capacity and the three preparation-storage checks also pass. This is a small follow-up, not a rerun of the complete 82-check set or the full suite.
