# Stored-capture independent security review

Reviewed at 2026-10-30T05:56:46.097512+00:00. **PASS**; no remaining blocking finding.

The reviewed API accepts only an explicit fixed example ID. No client path, model profile, budget or arbitrary run directory is accepted. The list returns two shared examples as safe metadata; it does not enumerate private judge jobs. POST requires the existing judge bearer and owner session, checks same-origin, strictly parses at most 1 KiB of JSON within five seconds, and rejects duplicate/extra fields before admission.

Each source is opened through every ancestor with NOFOLLOW, with a nonblocking regular single-link leaf and pinned size. The copy has a fixed byte bound and SHA, verifies descriptor identity before and after reading, and writes an exclusive private 0600 copy without changing the original. Symlinks, hardlinks, FIFOs, missing files and changed content/identity are rejected. Cancellation signals and joins the copy before failing admission, so a late copy cannot queue a job after HTTP cancellation.

The existing queue remains authoritative: at most three receiving/queued/running requests, at most $0.30 per request, admission-to-completion deadline at most 480 seconds, owner-scoped polling/downloads, 24-hour analysis retention, existing storage bounds and conservative financial settlement. The same snapshot worker hides GPU devices and parses data only; no new GPU training is dispatched by this path.

Read the final guarded test log: **84 passed in 23.64s**. Reviewed meaningful cases include fresh private copies, owner isolation, authentication and body rejection before reserve, unsafe source types, same-size hash mutation, mutation after read, deadline/cancellation, existing destination preservation, and cancelled HTTP joining with no dispatch. The initial 56-pass/one-failure receipt is retained: nested TestClient closed the shared app lifespan; the fixture was corrected without relaxing production validation.

Frontend review passed for opaque-ID submission, bearer header only, cleared token/result state, bounded identifier handling, exact artifact URL checks and real job polling. Its offline UI/typecheck receipt is separate. Static and offline tests are not proof of a successful live provider analysis; deployment and browser live verification remain the root task. This review made no model, GPU or provider calls and did not modify business source.

## Reviewed source SHA-256

- `headroom/api/snapshot_examples.py`: `4364c599648b2309f99fdf886e2ca20519f3f65d8c7fac041b5a2e80aaa8bf79`
- `headroom/api/snapshot_routes.py`: `09213933bdc48b5576c698a6ada7d2b7421e4162e4b959bae82f7d5eda0e371d`
- `tests/test_snapshot_examples.py`: `1237630bebba4657a3e7a4d26e0db0f595e5e431c7f410c4e4496249ed3cefad`
