# Product cleanup after protocol-v2 R3 — 2026-10-25

The user removed the Replay product feature. Home/Results replay cards, their
API requests and query mode, GET /api/replays, the public_replay access exception
and the dedicated CLI replay command have been removed. Owner run status,
historical events, result downloads, actual training reruns and allocator-history
reconstruction remain. Historical runs/reports and original PLAN bytes are retained.
Former T3.3 is user withdrawn, not a benchmark pass or an outstanding feature.

Two previously prepared development changes are also integrated: an explicit
existing shared budget database path for checkouts, and the opt-in
common-diagnosis-4000-v1 comparison protocol. Ordinary diagnosis stays at 16384
completion tokens. The study fixes all three diagnosis arms at 4000 and keeps
patching at 4000; it records role-specific thinking, complete control fields and
seed 1337, and rejects incompatible rows. No study was executed, no superiority is
claimed, and these changes do not add another MVP repair round.

The unchanged R3 evidence records 3/9 targets and 4/9 valid correct first causes,
below the retained six-required gates. Its HTTP529 unknown charge is still held;
no budget reset, manual settlement, recharge, paid call or GPU acceptance is
part of this product cleanup. Public deployment remains deferred for final
owner confirmation.

## Verification status

The frozen frontend candidate passed all 73 tests in 2.40 s at stable load after
the campaign. The integrated frontend TypeScript/Vite build passed (Vite 1.22 s).
Earlier 72/73 and 8/9 runs under concurrent load remain private evidence; the
unchanged original UI reproduced the same timing failure. No production timeout
or assertion was loosened.

Ruff check passed for headroom/tests and format left all 21 changed Python files
unchanged. The full guarded backend suite passed **3121 tests in 758.04 seconds**, with
all **310 source entries**, the original PLAN and the offline guard unchanged.
The [full receipt](full-regression-20261025T124628Z-90d44e1f-receipt.json) qualifies
these integrated bytes. The localhost preview was refreshed successfully;
its ledger rows and original limits stayed unchanged and billing remains blocked.

The full guard denies provider/network access, real credentials, real runtime
profiles and the real ledger in both parent and spawned processes. CLI, API,
shared-ledger and study tests use private fixtures.

## Evidence boundaries

- [R3 independent acceptance summary](../acceptance-v2-r3-20261025/independent-audit-summary.md)
- [Initial integration record](integration-initial.json)
- [Frontend build log](web-build.log)
- Private frozen patches and independent reviews remain under .cache.
- No current read-only preview or archived result counts as a new repair.

Browser checks confirmed that Home and Results contain no Replay section or controls.
The loaded Home shows the unresolved-billing notice and a disabled Start analysis
button. Results still displays an explicitly labelled archived offline integration
fixture; this is not publication of R3 or a new live evaluation. No task was
started through the browser. GET /api/replays and legacy public run access both
return 404. Historical experiment files were not deleted.
