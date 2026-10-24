# Availability and local budget observations

The public health endpoint reports observations, not a successful model run.
Its `gpu`, `token_factory`, and `local_budget` objects distinguish unknown state
from confirmed availability. `GET /api/usage` retains session-scoped run usage
and adds the same global `local_budget` object.

## GPU and provider

GPU metadata comes only from bounded `nvidia-smi` queries for free/total memory
and compute process IDs. No CUDA context or allocation is created. A compute
process makes `status=busy`; public responses contain only a process count,
never IDs, owners, command lines, or raw driver diagnostics. A missing driver
tool is unavailable; malformed output and failed or timed-out queries are unknown.
This is an observation of current compute activity, not a guarantee that the
next workload fits. Each driver subprocess has a one-second timeout.

Token Factory reachability uses an unauthenticated `GET /v1/models` against
one of the two official allowlisted endpoints. It has a two-second HTTP timeout,
does not follow redirects, does not use ambient proxy credentials, and reads
only response headers. HTTP 200, 401, and 403 demonstrate endpoint reachability;
other HTTP responses are marked degraded but reachable. A network failure is
unreachable. No API key, environment credential file, model inference, or
provider billing API is read or used. `authentication_checked` is always false.
Reachability does not prove API credentials, credits, model access, or a completed
inference.

`token_factory.configured` means a reviewed runtime profile can be read
(or an explicit offline settings override is in use). Its
`configuration_scope=reviewed_runtime_profile` deliberately does not assert
that credentials were checked. An absent runtime profile can coexist with a
reachable endpoint. A missing profile also leaves local authorization unknown.

A per-application monitor refreshes GPU/provider observations in one background
thread, independently of HTTP request timing. A completed cycle waits five seconds
before probing again, keeping ordinary observations fresh within their 15-second
TTL even when the browser also polls every 15 seconds. Requests do not wait for
those probes. Each observation includes `checked_at`, `stale`, and `refreshing`.
GPU and provider results are published and timed separately: a slow provider probe
cannot refresh an old GPU timestamp. Fresh observations remain usable while the
next cycle runs; initial and genuinely expired observations expose unknown/null
capability fields. Only one refresh can run at once. Shutdown wakes the scheduled
wait and stops future probes, with a bounded wait for an in-flight probe to finish.
Custom offline workers disable external probes by default; tests inject
deterministic observations and a controllable background schedule instead.

## Local budget

The local budget is **not the Token Factory account balance**. The scope is
`local_application_authorization` and `account_balance` is always null. The
authorized total comes from the reviewed runtime profile; the daily limit is the
smaller of the plan's $12 ceiling and `HEADROOM_DAILY_BUDGET_USD` when supplied.

The observer opens the existing ledger in SQLite read-only/query-only mode,
using a read transaction, a short busy timeout, a bounded query deadline and a
row-count bound. It never constructs `BudgetLedger`, issues DDL, changes rows,
uses a write transaction, or creates a missing database/directory. Symlinks,
malformed data, unreadable ledgers, and invalid limits result in unknown state.
Normal SQLite WAL readers can participate in SQLite shared-memory coordination;
the observer does not take the ledger's application write lock or disregard
committed WAL data.

An open run reserves the larger of its run limit and recorded attempt charges.
A closed run retains recorded charges. Global and current UTC-day commitments
are deducted from their respective caps; `remaining_usd` is the smaller
nonnegative remainder. These are local reservations and charges, not an estimate
of unrecorded manual account spending.

Unknown attempt charges retain their conservative reservation; actual total
remains null. `unknown_attempts` and `pending_attempts` are explicit.
An unresolved billing bound in any run causes
`status=billing_review_required`; a depleted cap causes `status=exhausted`.
Otherwise the ledger is available. Failure to inspect it never becomes zero
cost, exhausted, or available.

## Home behavior and verification

Home refreshes health every 15 seconds. Confirmed fresh GPU activity, local
budget exhaustion, and unresolved billing bounds disable Start analysis and
explain the reason. A replay link appears only when the existing replay catalog
contains saved evidence. The link does not imply that a baseline replay repaired
a workload. Unknown or stale observations are not presented as confirmed blockers.

Offline tests cover probe timeouts and redaction, endpoint allowlisting,
unauthenticated HTTP responses, read-only budget snapshots including concurrent
WAL writers, reservations, unknown usage, billing bounds, cache refresh and
expiration, equal-interval HTTP polling during background refresh, independent
probe timestamps, shutdown, and Home replay guidance. Network access is independently blocked in
the availability test module; GPU commands and HTTP calls are mocked.
