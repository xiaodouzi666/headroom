# Local API and supervised queue

Status: offline implementation, verified with FastAPI TestClient, injected
workers and real short-lived fake worker processes. No listener, model API, GPU
workload or .env access was used by these API tests. Public HTTPS/authentication,
live reachability, five curated successful replays, and actual curl/systemd/monitoring acceptance remain pending.

## Configuration and source input

Factory: headroom.api.app.create_app(ApiSettings()). Importing the module binds
no port and starts no worker. Lifespan starts one scheduler thread. Production
runs each job in a supervised multiprocessing spawn process with its own Store.

ApiSettings accepts project_root, data_root, db_path, run_root, web_dist,
runtime_profile, runtime_configured, deadline_seconds (default/max 600),
shutdown_grace_seconds (default 5, max 10), event_poll_seconds, allowed_hosts,
public_host and trust_cloudflared.
Defaults use runs/headroom.db, runs/jobs and runs/api inside the project.

The explicit local launch command is:
```sh
python -m headroom.api.app
```
It binds only 127.0.0.1:8000 and disables proxy-header rewriting. This command has
not been run for these offline tests. Public deployment needs a reviewed hostname,
HTTPS and authentication configuration.

POST /api/runs accepts exactly one source form: script_text, example_id, or all
three of repo/ref/cmd. It also accepts target, canonical policy and budget. Budget is a decimal string, default "0.6", positive
and at most 5 USD; the separate reviewed runtime/budget guard must still authorize
any spending. Targets: fix-oom, reclaim, fit:22GB, or explicit fit:22GiB.
Policy keys are allow_numerics_change, allow_model_change,
allow_batch_grad_accum and max_throughput_regression_pct.

Uploads are UTF-8 text <=1 MiB, copied to a fixed train.py in a fresh server-owned
directory. No HTTP field accepts credentials, filenames, host paths or runtime
profile paths. Request bytes are separately bounded. Static policy scanning
precedes admission; import socket is HTTP 400 with safe reason codes. Docker
isolation remains required. Examples are resolved only from the real scenario
catalog and matching scenario script paths. Repository input requires a public
HTTPS github.com URL without credentials/query, an exact lowercase 40-character
commit SHA, and `python|python3 relative_script.py [argv...]`. Preparation fetches
and extracts data only; it does not execute setup, install dependencies or run
repository code on the host. Archive paths, links, source sizes and source-policy
checks remain enforced before scheduling. The reviewed nanoGPT pin additionally
retains only its three fixed source files and deterministic synthetic input.

Every admitted API job uses max_steps=20 and max_seconds=180 for each Lab run,
plus the independent whole-worker deadline. Returned HTTP 202 data:
```json
{"run_id":"generated-uuid-hex","status":"queued","queue_position":1,
 "run_url":"/api/runs/generated-uuid-hex",
 "events_url":"/api/runs/generated-uuid-hex/events"}
```
The worker may start before the next status request.

## Read API contract

| Endpoint | Result |
|---|---|
| GET /api/runs | {runs: current-session summaries, queue} |
| GET /api/runs/{id} | Summary, usage and available artifact URLs |
| GET /api/runs/{id}/events | Historical and live SSE |
| GET /api/examples | {examples:[{id,title,expected_mode,root_cause,baseline_verified}]} |
| GET /api/usage | Current-session calls, known subtotal, unknown count, nullable total, per-run usage |
| GET /api/health | DB and queue state; explicitly unprobed GPU/model reachability |
| GET /api/replays | Server-curated public_replay rows, count and provenance note |

Summaries include status, target, policy, target_met, timestamps, reason,
provenance, elapsed_seconds, api_worker_finished and api_cleanup_verified.
They do not expose uploaded text or absolute host paths. Usage preserves unknown
costs; a nullable total never silently becomes zero. Health's configured flag is
server-supplied configuration state, not proof of working credentials or credit.
GPU availability and Token Factory reachability remain null/not_probed; health
does not make model requests.

Each SSE event has id=sequence, event=kind, and JSON data:
```json
{"sequence":3,"kind":"verify.done","data":{"target_met":false},"created_at":"..."}
```
Last-Event-ID or ?after=N resumes strictly after that event. Historical and newly
persisted events are emitted, with a final reread after terminal state. The stream
ends with event: stream.end and data containing status, cleanup_verified and
last_event_id. An early needs_human event does not end the stream before worker
finalization. Idle comments keep the connection alive. Unknown cleanup ends the
affected stream explicitly with that uncertainty.

Whitelisted artifacts: report.md, report.json, patch.diff, env.sh, cli.json,
pareto.json, pareto.md, annotations.json, evidence.json, evidence-after.json,
evidence.md, timeline-before.png and timeline-after.png. They map only to generated
paths beneath run_root/{generated UUID}. Every directory and leaf is opened with
NOFOLLOW; the already-open descriptor is streamed, preventing path replacement
from redirecting the read. Nonregular/missing/oversized files are rejected.
There is no arbitrary path download endpoint. Files use attachment and nosniff
headers. Existing web/dist is safely served with an index fallback for frontend
routes; static symlinks and traversal are rejected, and API 404s stay API 404s.

## Isolation, limits and lifecycle

Private runs use a random 128-bit HttpOnly, SameSite=strict cookie. The local HTTP
cookie is not Secure; configuring an explicit public_host enables Secure cookies.
Neither mode provides complete public authentication. Other sessions
cannot inspect a private run, even with its ID. Only server-set public_replay
metadata permits public reads. The API never invents replays or exposes a flag
that lets requesters publish them.

Cross-origin POSTs and untrusted Hosts are rejected. A Vite same-origin proxy
should preserve Host (changeOrigin:false), matching the browser Origin.
Rate limits use the ASGI server's client address, not arbitrary X-Forwarded-For.
The provided entry point disables uvicorn proxy-header rewriting. Explicit
trust_cloudflared requires a configured public hostname, and uses a validated
CF-Connecting-IP only when the actual peer is loopback. Otherwise the peer IP is
used and forwarded headers are ignored. The deployment assumption is that
Cloudflare overwrites CF-Connecting-IP and Cloudflared is the only public path to
the loopback origin. This is not safe for an arbitrary reverse proxy or direct
Internet binding. No real tunnel/header behavior was established by the tests.

The third admitted new-run attempt per IP within a rolling hour receives 429.
Admissions are persisted in local SQLite, so changing cookies or restarting does
not reset them. **A repository preparation failure still consumes its admission**:
otherwise repeated bad repositories could bypass the limit on expensive fetches.
Validation failures before admission do not consume a slot. Running, pending and
preparing requests together are capped at three; queue snapshots expose
`preparing` separately. A preparation failure releases its capacity slot.

Admission and slot reservation hold only short locks. Git preparation and static
source inspection run outside the queue condition and SQLite transaction, so
health, SSE, worker completion and shutdown remain responsive while a repository
is being prepared. Scheduling rechecks shutdown/cleanup state after preparation.
One scheduler serializes API workers. The Lab GPU lock separately guards against
concurrent CLI GPU work.

At 600 seconds, the supervisor sends TERM, allows a short cleanup grace, then
KILLs a remaining owned process and joins it. The orchestrator's TERM path retains
partial reports and budget accounting; durable pending API calls remain unknown
after hard termination. Partial reports are regenerated from persisted state
after cancellation/failure instead of retaining a stale success claim.

Container recovery considers only Lab manifest directories under this job's
lab/{UUID}. It inspects the manifest-derived name, verifies /source and /out
mounts exactly match that Lab directory, then removes the inspected immutable
container ID. It never kills arbitrary host PIDs or broad container-name matches.
Cleanup must be verified; otherwise the run becomes needs_human and the queue
halts before starting another job.

Shutdown cancels the supervised worker and preserves pending jobs as needs_human.
On restart, queued jobs are not automatically rerun. Any prior API job lacking
verified supervisor completion halts admission for operator review—even if its
computation had already written a terminal status. That terminal status alone
does not prove GPU cleanup. Public restart/recovery/alert acceptance is still
pending.

## Offline test evidence

For trusted tests, create_app(settings, worker=fake) uses a thread callable with
signature worker(FixRequest, *, store, run_root, run_id) -> dict. Explicit
worker_mode="process" with a top-level picklable fake tests actual supervision.
HTTP callers cannot choose either worker injection or execution mode.

```sh
uv run pytest -q tests/test_api.py --basetemp=runs/api-tests-<fresh-id>
uv run ruff check headroom/api tests/test_api.py
```

The first retained invocation, runs/api-tests-20261024-a, passed 15 checks.
The second, runs/api-tests-20261024-b, passed 18 in 9.58 seconds, including a real
fake worker that ignores TERM, hard deadline/partial-report recovery, shutdown
cancellation, queue freezing on uncertain cleanup, immutable container ownership,
session isolation, SSE history/live/resume, upload/rate/path boundaries and static
serving. All tests were offline and GPU-free. Use fresh basetemp directories
because pytest clears an existing basetemp.


Final focused verification: runs/api-tests-20261024-c, **19 passed in 9.63
seconds**, Ruff clean. This adds restart recovery for a terminal run whose
supervisor cleanup had not finished. No prior test directory was overwritten.


## Integration review on 2026-10-24

Fixed Pareto configuration downloads use
`GET /api/runs/{id}/configurations/{tier}/{artifact}`. Tier is strictly
`round-01` through `round-06`; artifact is exactly `patch.diff`, `env.sh`,
`cli.json` or `manifest.json`. The same session/public-replay authorization and
NOFOLLOW directory/leaf checks apply. The route maps only to
`configurations/{tier}/{artifact}` below that run; it never accepts an arbitrary
report-provided host path. Tests cover valid downloads, other sessions, path
injection and both directory and file links.

Repository Git operations disable hooks, credential helpers and fsmonitor hooks,
ignore ambient Git/home configuration, disable redirects and apply Linux
`prlimit` with a 256 MiB file limit. Fetches retain packs rather than unpacking
unbounded loose objects. Extraction still enforces its own file-count/total-byte
limits. A clean install can publish nanoGPT's three reviewed, fixed-hash original
files under `.cache/reviewed/nanogpt/<exact-ref>` for policy validation; publication
is atomic, validates existing files and never overwrites a differing baseline.
The source profile remains restricted to the exact reviewed pin.

The 600-second supervisor bounds the executing worker. Source preparation and
queue waiting occur before that worker; Git operations have their own 120-second
timeout. The current tests do not establish a ten-minute end-to-end guarantee for
a repository submission, or the original public deployment acceptance. They do
verify that slow preparation cannot hold the queue lock or block another ready
job, and failed preparation cannot bypass the IP admission limit.

Focused review evidence: `runs/root-integration-review-20261024-a` passed
83 tests in 11.20 seconds (runtime/budget/repository/annotations/cost/API);
`runs/root-integration-review-20261024-b` passed 135 tests in 3.92 seconds
(LLM client/router, orchestration, diagnosis contracts, search and reports).
Ruff passed for the affected files. Tests used MockTransport, in-process ASGI and
owned fake worker processes; no real model requests, GPU workloads, listener,
public tunnel or payment was used during this review. The independently captured
HF CUDA baseline is documented separately in WATCH_HF.md, not counted as API or
model-repair acceptance.
