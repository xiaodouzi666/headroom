# Health notifier — offline handoff

Base 0e7a9d9; source and tests frozen. No commit/push.

The previously notification-only state recorder now has an opt-in HTTPS webhook
adapter. Default checks do not read credentials or contact a receiver. A future
authorized --notify invocation requires a valid private .env destination.

Continuous failure is due after 120 observed seconds. A durable sending claim
and exclusive lock protect local dispatch; accepted incidents are not resent.
Recovery resets the incident. Three bounded attempts use 60/120-second backoff.
Unknown delivery is not automatically retried unless the receiver's idempotency
contract is explicitly configured; retries retain the same key and byte-identical
payload. 2xx means HTTP acceptance only, not a human receiving or reading it.

57 guarded tests passed in 0.53 seconds, including the actual HTTPX sender through
MockTransport, concurrent locking, lost response/restart, state write failures,
legacy zero timestamp, secret permissions, redirects, payload deduplication and
INFO log privacy. Scoped Ruff and git diff --check passed.

The templates remain uninstalled and notifications disabled. HTTP timeouts are
phase/inactivity bounds; systemd is separately configured for a 20-second start
deadline, 2-second stop grace and process-group cleanup. No service was stopped
or timer enabled; no real .env was read and no recipient was contacted.

See receipt.json for exact file/log hashes and evidence limitations.
