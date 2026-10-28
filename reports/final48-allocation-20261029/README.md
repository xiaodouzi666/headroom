# FINAL48 allocation binding — implemented, not activated

The default command produces a draft with **all money fields null**. No new actual allocation, ledger, runtime profile, or live request was created for this implementation. The owner's concrete amount authorization remains required.

The single FINAL48 pool covers F1, F2_demo, F3, F3b_snapshot, F3b_watch and F5. A reviewed plan can leave a task's cap null to keep that task unavailable. It is not a separate F1-only pool. [plan.json](plan.json) is an inert template, not an authorization or a usable profile.

## Interfaces and checks

- scripts/final48_allocation.py defaults to plan output. Explicit activation requires a reviewed filled plan, a concrete amount-authorization record, and a reviewed profile input.
- Activation binds the authorized net amount to an observed available-gift balance, review reserve and tax reserve. The approved amount must fit that arithmetic; the shared daily and per-task caps cannot exceed it. No new generic risk approval or expiry requirement is added.
- A private, fixed registry prevents a second FINAL48 pool or reuse of the same authorization message reference. The new ledger contains allocation-identity metadata; its canonical path and device/inode, the profile hash, and the receipt hash must match.
- The old ledger is opened read-only for a consistent logical digest and unknown-attempt count. Its unknown values are neither erased nor used to block or deduct the new allocation.
- The existing acceptance_run has an optional allocation binding. That branch takes the exact existing ledger/profile from the receipt, refuses a conflicting budget environment path, and records the allocation and claim identity in its runtime receipt. Other existing callers keep their prior default path behavior.
- F1 live execution now requires --allocation-receipt. Its prepared-input and scoring hashes must match the approved task pins. A durable once-only F1 claim prevents a second execution even if an execution directory is removed. A failed or interrupted claim is retained, never automatically reset.
- F1 rechecks the receipt, profile and ledger identity before each request. Requested limits can be lower than the approved limits; they cannot enlarge them. The shared estimator's margin and 2,000-token output policy remain explicit in the reviewed profile and request package.

The authorization-message reference and content hash are audit evidence supplied from the actual human approval. They are not a cryptographic signature proving consent against a malicious same-user administrator. Activation does not contact the provider or make a payment.

Local input estimates remain estimates, not guaranteed provider billing bounds. The existing runtime settles observed usage, stops on an exceeded estimate or new unknown charge, and preserves unknowns. The balance observation is a point-in-time check; this tool does not control unrelated external clients using the same provider account.

## Scope still pending

Only the common acceptance integration and F1 enforcement are wired in this change. Other CLI/R7 workflows and public services have **not** been switched to the new pool. Their remaining integrations must use this same allocation and explicit task scope, rather than create another ledger. Public model submissions remain unchanged.

The final F1 package must be rebuilt after all shared implementation changes freeze; the older v5 package remains historical preparation evidence and is not the current executable package. Activation is also pending the actual amount approval and reviewed balance/profile inputs.

## Offline validation

The focused allocation and F1 tests initially passed together: 29 passed in 43.30s. They create only temporary fixture ledgers/profiles and use MockTransport with real DNS/INET and project .env access blocked. Coverage includes null default templates, missing authorization, preserving an old unknown charge, shared-pool identity, duplicate activation, changed profile/receipt/copied DB/environment, fixed F1 inputs/caps, durable claims, and a 27-response fixture run through the real common runtime.

Follow-up allocation checks after final cleanup hardening are recorded in validation.json. No full suite, model call, GPU execution, actual activation, or production service change was performed.

Final review also makes every binding revalidation check that its durable run claim remains active. The concurrent F1 once test allows exactly one claimant. A real MockTransport/runtime fixture changes the profile after response one and verifies that response two is never requested. The final follow-up commands and hashes are retained in validation.json; no actual allocation exists.
