# Phase 2 r2 draft review

This is an offline preparation, not an execution qualification. No cap-review, root-review, preflight, or execution receipt was created. Default planning and 48 synthetic self-checks read neither the runtime profile nor the live ledger and made no provider or GPU call.

## Versioned changes

The r1 driver is preserved. The new r2 driver binds the r2 MVP driver, independent auditor, quality evidence directory, funded runtime profile, funding transition, and separate read-only Phase 2 budget helper. It retains ten core scenarios times strict/allow_precision, a fixed denominator of 20, separate per-policy denominator 10, bounded_pareto, at most six rounds, 480 seconds per run, and USD 0.60 per-run ceiling. The USD 12 nominal campaign ceiling is not new money.

The same reviewed runtime allocation has a lifetime ceiling of USD 14.17775754 and an unchanged daily ceiling of USD 9.99964904. Old known and unknown charges remain in the same ledger; the old helper's globals are not changed. A future Phase 2 cap must use a fresh post-MVP ledger snapshot and the smaller of USD 12, remaining lifetime allocation, and remaining UTC-day allocation. A fresh snapshot includes charges added by MVP. It is distinct from the immutable 97-run/517-attempt snapshot used to document the earlier zero-sum funding event. The profile's available_credit_usd records the funded lifetime allocation, not a live provider balance.

Before any future freeze, the actual r2 fixed-nine campaign must have at least six target successes and six valid/correct first causes, with source, identity, finance, cleanup, and independent-audit evidence. This does not raise the MVP requirement to 9/9 or silently certify its separate unfinished items. A passing current full-suite receipt must bind the same complete source inventory; clean/pushed/current-source and actual-budget checks are retained. Missing own review/cap/MVP execution is rejected before execution imports helpers or reads financial state. No actual r2 outcome was fabricated for this preparation.

The driver and helper pass Ruff check and Ruff format --check. All 26 inherited self-checks remain, with 22 new checks covering funding/profile/helper drift, unchanged daily budget, pending or missing funding, cumulative history across UTC rollover, lifetime reservation exhaustion, stale pre-MVP snapshots, newly charged history in a fresh cap, and historical-helper immutability. The mocked execution test refuses missing qualification before subprocess dispatch. See selftest.json and version-diff.patch.

## Unresolved ground truth

The current unmodified scenario_set_v2 manifest has authored truth for seven of the ten core scenarios. s5_fragmentation_varlen, nanogpt, and hf_trainer remain unverified. Repeating both policies does not create ground truth: at most 14 of the fixed 20 rows can currently receive a verified-correct first-cause result. This is an upper bound, not a measured score. The ordinary aggregate accuracy remains unknown while any required truth is unknown; the 75% first-cause gate cannot be certified by dropping those rows or reporting only the scored subset.

This draft preserves that limitation, the current manifest, and every numerical/target/first-cause gate. An independent adjudication may be useful, but a source name or authored bug story is not runtime proof. Reliability is reviewing the existing source and baseline evidence separately. This draft does not pre-judge that investigation or assign replacement labels.

## Prospective metadata-only qualification proposal

If independent evidence later supports a root-cause label, create a new prospective Phase 2 manifest and a versioned adjudication receipt before its execution. Preserve the old v2 manifest, historical campaign rows, audits, and scores. Bind the adjudication to exact source, arguments, baseline artifacts, root-cause reasoning, limitations, and an independent review. It must not count a manually written repair as a model result.

The current draft deliberately still requires exact inventory equality with the audited MVP; merely adding or changing an evaluation manifest therefore does not bypass that check. A future separately reviewed driver revision could distinguish the already completed MVP qualification from the new Phase 2-only metadata:

1. Revalidate the original r2 audit against its original pinned execution, campaign, and source inventory. Its old 6/9 target and 6/9 valid-cause counts remain unchanged. If it did not meet those counts, new labels cannot retroactively qualify it.
2. Bind a new source-transition receipt that lists every old/new path and digest. Permit only the explicitly reviewed prospective manifest and adjudication metadata; require all runtime programs, validators, evaluation implementation, source files, arguments, target thresholds, reference strategies, policies, and resource/budget settings to remain byte-identical or structurally identical as appropriate. Compare normalized old/new manifest objects after removing only the explicitly allowed truth/provenance fields. Do not use a broad ignore pattern.
3. Run a new complete quality check on the new inventory and bind that receipt to the prospective Phase 2 driver and manifest. The original MVP receipt continues to describe the original inventory; the new quality receipt describes the later metadata-bearing inventory.
4. Establish a fresh ledger cap and dispatch qualification for that prospective version. Reject any extra change, incomplete evidence, changed runtime semantics, missing quality, or source drift. Any runtime change requires its own appropriate acceptance, rather than the narrow metadata transition.

This is a proposed reviewable route, not an implemented exemption. It avoids rewriting or pretending to rerun old r2 MVP results while still requiring fresh quality for newly added metadata. No production source, tests, protocol, or manifest was changed for this draft.

## Independent review

The memory-policy agent independently read the final driver (SHA 6ec6ac9c667bc79b0ab3e936941e7e6975a7077da414e550468b77906917ecad) and helper (SHA 14ac606a5c26c013b6059aac57d9c4186f800597962689bd5bcabab4419411c1) and found no material blocker to committing this planning draft. The review confirmed the fixed matrix, original MVP 6+6 gate, immutable funding source versus fresh ledger cap, lifetime/daily split, retained unknown charges, shared lock, and early missing-qualification rejection. It did not repeat tests, freeze/execute, or read live profile/ledger data. The USD 0.60 next-case floor is not proof that an individual Ultra request fits: each actual POST must still reserve its full provider bound through the pinned production runtime.
