# Public snapshot funding binding — offline verification

The snapshot route now has a dedicated binding to the existing server-owned judge allocation. It uses SnapshotDiagnosisRequest and the three input-file hashes directly. It does not manufacture a training request or create a new funding pool.

## Contract

- SnapshotPublicAllocation(judge_allocation, project_root=...) exposes project_root, profile_path, daily_limit_usd, available, claim(request, run_id), and finish(binding, execution_terminal=..., cleanup_verified=...).
- The discriminator is snapshot_protocol = headroom.public-snapshot.judge.v1, with the existing v3 judge-period schema.
- claim uses the same claims transaction as ordinary judge runs. The queue must use binding.run_limit_usd when remaining credit narrows the requested amount.
- snapshot_public_budget_factory(binding, project_root=...) supplies the normal live runtime's BudgetLedger. It selects the receipt-bound database explicitly, without changing process-wide environment variables.
- open_run, reserve and mark_dispatched verify the recorded claim, current receipt/profile and database identity, effective credit extension, strict request limit, expiry and all uploaded input bytes. Only the exact unsent current reservation is exempted from the unknown-cost check during mark_dispatched.
- Settlement uses the registered binding and recorded costs after cleanup; deleted inputs or expiry do not prevent honest settlement. Unknown costs and unverified cleanup remain blocking.
- Effective cumulative judge funding may exceed the immutable base profile amount. The existing reviewed extension remains authoritative; no amounts, credentials, receipts or histories are changed by this module.
- A request limit under the existing local-estimate admission policy is an application admission limit, not a mathematical upper bound on the provider bill.

## Evidence

Final focused command: .venv/bin/pytest -q tests/test_snapshot_public_binding.py

Result: **28 passed in 2.16s**. Ruff check and format --check passed. The earlier 26-case pass is superseded by this final 28-case run; they are not additive.

The inherited autouse guard rejects DNS/socket connections, subprocess dispatch, production .cache/runs files or databases, and .env-named files. Every pool, receipt, profile, credential and ledger used by these tests is a temporary synthetic fixture.

Coverage includes shared ordinary/snapshot claim races; all three input files changing before reserve and dispatch; profile, receipt, credit extension, registry state, database identity, expiry, budget mode and request limit changes; rehashed funding/protocol tampering; exhausted or narrowed remaining credit; unknown costs and cleanup failures; exact own-pending handling; post-expiry settlement; and the real build_live_runtime → SDK MockTransport path after cumulative spending exceeds the immutable base-profile amount.

The runtime integration test uses one synthetic SDK response and no provider connection. It also confirms that an unrelated HEADROOM_BUDGET_DB_PATH cannot select a different ledger.

## Read-only integration review

The API queue supplies the server-selected profile, binds actual uploaded files, copies the narrowed run limit into the worker request, and passes the binding with the real project root through the snapshot context bridge. The public discriminator selects this factory; the previous F3b path remains unchanged. Legitimate judge profiles already require strict_reservation at preparation and receipt verification, so the core's strict-mode copy preserves the compared profile.

Separate API/spawn/resource tests belong to the API owner and are not counted here. These checks establish offline implementation behavior only. They do not establish a successful live snapshot diagnosis, public deployment, new credit authorization or new competition result.

Files owned by this change:
- headroom/acceptance/snapshot_public_binding.py
- tests/test_snapshot_public_binding.py
