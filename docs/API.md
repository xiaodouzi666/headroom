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
inside one admission-to-execution deadline (default/max 600 seconds). Preparation,
queue waiting, process startup and worker execution share that deadline; no stage
receives a fresh 600 seconds. HTTP upload and validation before admission, and
cleanup/report finalization afterwards, are separate. Returned HTTP 202 data:
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
| GET /api/usage | Current-session calls/costs and separate read-only local authorization budget |
| GET /api/health | DB/queue, cached GPU activity, anonymous provider reachability and local budget |
| GET /api/replays | Server-curated public_replay rows, count and provenance note |

Summaries include status, target, policy, target_met, timestamps, reason,
provenance, elapsed_seconds, api_worker_finished and api_cleanup_verified.
The admission boundary is explicit in api_admitted_at, api_deadline_at and
api_execution_limit_seconds; api_cleanup_grace_seconds is the worker's TERM
grace, not extra execution authorization or a bound on all container cleanup.
They do not expose uploaded text or absolute host paths. Usage preserves unknown
costs; a nullable total never silently becomes zero. Health's configured flag describes the reviewed runtime profile, not working
credentials or credit. Cached GPU metadata and anonymous endpoint reachability
distinguish observed, stale and unknown states. Health never makes inference
requests or reads keys; local authorization budget is not account balance.
See AVAILABILITY.md for the read-only observation contract and Home guidance.

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

At the shared deadline, preparation is killed in its dedicated process group;
HTTP submission returns 504 with a safe reason and a persisted timeout/partial
report. The failed attempt still consumes its IP admission. A separate expiry
thread marks waiting jobs timeout and never launches their worker. Its report
rendering cannot hold up the active worker's deadline watchdog. While that report
is being rendered, api_report_pending keeps SSE open. api_worker_finished and
api_report_ready are finalized only afterwards. A rendering failure exposes
api_report_error=partial_report_generation_failed with needs_human and lets the
stream end explicitly, without claiming a report is ready.

An executing worker receives TERM at the same admission deadline, then its
separately configured cleanup grace (default 5 seconds, maximum 10), then KILL
and join if required. Preparation cleanup allows at most two seconds of process
reaping/group verification after its immediate kill. These cleanup intervals,
owned-container checks and partial-report rendering are not execution budget.
The orchestrator's TERM path retains partial reports and budget accounting;
durable pending API calls remain unknown after hard termination. Partial reports
are regenerated from persisted state instead of retaining a stale success claim.
Unverified preparation or worker cleanup freezes admission and subsequent work.

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

The earlier implementation bounded only the executing worker and excluded
source preparation/queue waiting. That limitation was corrected on 2026-10-24:
admission creates one monotonic deadline, shared with a separately spawned,
data-only preparation process and the executing worker. Git operations use the
smaller of 120 seconds and the remaining budget; archive extraction and the
reviewed-cache publication lock also check the remaining budget. The preparation
process receives no credential environment and never executes repository code.

Before preparation begins, the supervisor verifies the child handshake. On
success/error the preparation child keeps its dedicated session leader alive
until cleanup, so its PID cannot be recycled first. Cleanup checks the owned
process start identity and session/group, kills only that group (including Git
descendants), and verifies that no live group member remains. Linux parent-death
notification kills the same owned group if the supervisor crashes; a post-arm
parent-PID check covers death before the notification was installed. An expired or
cancelled preparation cannot later enqueue work. Worker entry rechecks the
deadline before calling the runtime, covering slow process startup.

This establishes the admission-to-execution boundary, not a ten-minute bound on
HTTP upload/validation or final cleanup, and does not establish original public
deployment acceptance. Old runs and earlier test evidence remain preserved.

Focused review evidence: `runs/root-integration-review-20261024-a` passed
83 tests in 11.20 seconds (runtime/budget/repository/annotations/cost/API);
`runs/root-integration-review-20261024-b` passed 135 tests in 3.92 seconds
(LLM client/router, orchestration, diagnosis contracts, search and reports).
Ruff passed for the affected files. Tests used MockTransport, in-process ASGI and
owned fake worker processes; no real model requests, GPU workloads, listener,
public tunnel or payment was used during this review. The independently captured
HF CUDA baseline is documented separately in WATCH_HF.md, not counted as API or
model-repair acceptance.


## Shared admission deadline regression

The final scoped run, reports/api-admission-deadline-20261024/tests-e.log,
passed 88 tests in 32.06 seconds across API/deadline, repository and CLI contracts.
Owned fake processes establish cancellation of slow preparation and descendants,
shared remaining worker time, queued expiry, report/watchdog isolation, cleanup
uncertainty, shutdown, stale-PID refusal and supervisor-SIGKILL recovery both
during preparation and while awaiting cleanup. Slow-report SSE tests establish
that final artifact availability (or an explicit rendering failure) is published
before the stream ends. Git and cache-lock tests are offline; no real provider,
GPU workload, public listener, key read, recharge or system service change was
performed. A fake SQLite transaction delay plus wall-clock jump verifies that
the published admission/deadline timestamps are sampled after successful
admission, while the IP quota retains its original attempt timestamp.
Earlier tests-a/b/c/d logs remain present.
