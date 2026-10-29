# Judge routing and staged frontend — 2026-10-29

Base HEAD: `8a10eaba91d8239221b65d868aced089b0b81dbd`. Reviewed source hashes are in [source-hashes.json](source-hashes.json). Judge allocation accounting is documented separately in [the binding receipt](../judge-access-20261029/binding-check.json).

The API selects the allowance from server-validated Authorization. Anonymous examples retain DemoAllocation; a valid Bearer selects the configured JudgeAllocation for examples or scripts. Preparation gets a request-specific settings copy containing that allocation's profile and daily allowance, with no mutation of shared settings or the anonymous process environment. Invalid, empty or duplicate Authorization is rejected before admission. HTTP cannot supply funding kind, pool, profile, binding or worker.

RunQueue persists the trusted funding kind separately from HTTP source data. Its thread/spawn dispatch and finish use the corresponding wrapper/allocation. Missing judge bindings fail closed. Both channels retain the same admissions database, one attempt per IP per hour, common queue capacity, public 480-second deadline and cleanup gates.

No judge allocation configured preserves the explicitly requested legacy compatibility behavior. An explicitly configured but invalid judge receipt prevents launcher startup. An unavailable configured judge allocation rejects Bearer work without falling back to the anonymous allowance.

Public config/health follows current request credentials, exposing readiness without amounts or paths. The optional token field is available even when the anonymous pool is paused; the form waits for server health verification before restoring submission. Tokens apply to either input mode, use React state only, and are cleared after submission. Snapshot submission remains closed. No replay or breathing indicator was added.

## Focused verification

| Check | Outcome | Evidence |
|---|---:|---|
| Initial routing and existing public/demo/launcher compatibility batch | 35 passed, 9.59 s | [initial log](focused-initial.log) |
| Final expanded API tests | 13 passed, 5.33 s | [final API log](backend-final-confirmed.log) |
| Independent-review empty/duplicate/invalid-auth and zero-admission case | 1 passed, 1.50 s | [auth log](backend-auth-review.log) |
| Run-form UI tests | 28 passed | [UI log](frontend-final-0.log) |
| TypeScript | passed | [UI check receipt](frontend-final-checks.json) |
| Global Ruff, scoped format/Prettier/diff checks | passed | [global Ruff](global-ruff.log), [scoped checks](static-final-checks.log) |
| Production build to separate staging directory | passed | [build receipt](staging-build.json) |

The API tests include actual JudgeAllocation → API → SDK MockTransport → the new fixture ledger in both thread and spawned-process modes, with synthetic Lab evidence; they confirm the anonymous fixture ledger is untouched. Launcher cases cover explicitly invalid receipts and preservation of the anonymous process environment. DOM tests cover exhausted-anonymous/healthy-judge readiness and rejection of invalid tokens. Backend tests used the unchanged v4 isolation guard with parent and spawned negative probes. No real provider/model calls, GPU jobs, production database mutations, or real credential/profile/ledger reads occurred.

These are separate focused batches, not a new full regression or new GPU repair acceptance. Earlier acceptance failures and original full-suite evidence are unchanged.

## Staged build for controlled publication

Built with installed Node 24 to `/home/xiaodouzi/workspace/headroom/.cache/judge-access-review-20261029/web-dist`; current served `web/dist` was not overwritten. Live index hash before and after: `20136f6b029c3b22e8e72b8595fb999276680cc9cf56f6f484f9abe3c7e18d72`.

Staged index hash: `bc3fd6ab052b6c7fed72631df146eebe579860bd0746286631f8c65dbd90a03b`; main asset: `assets/index-HPFAs9Jj.js`. All artifact hashes are in [staging-build.json](staging-build.json). There were no web environment files; provider/VITE environment was scrubbed for build. Synthetic token/key markers were absent from the bundle. No actual token was read or embedded; root retains the final publication scan and deployment step.

## Preserved intermediate failures

The system Node typecheck passed, but its Vitest startup lacked `node:util.styleText`; no tests ran in that startup attempt. The installed Node 24 fixed the runtime requirement without downloads. The first Node-24 UI run had two old tests requiring updated expectations: await server credential checking, and send the optional token for an example. Its failing [log](frontend-1.log) is retained.

Two added integration tests initially had fixture registration errors after Ruff removed an unused fixture alias. Explicit fixture wrappers fixed registration; the [error log](backend-final-0.log) is retained. The final empty-header test update required a formatting-only tuple wrap; initial [static-checks.log](static-checks.log) and the successful follow-up both remain. No production assertion or funding check was relaxed.
