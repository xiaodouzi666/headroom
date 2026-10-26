# Partial-run known-cost aggregation

Development date: 2026-10-27 (Asia/Shanghai). This is an offline reporting fix, not a new model campaign.

## Problem and behavior

A run can contain known charges and one or more unknown charges. Its exact total correctly remains null, but the old campaign summary added only exact run totals. Consequently, all nine R3 rows had null actual totals and the saved campaign's known subtotal was incorrectly zero, although known individual charges totaled $1.20596190.

The campaign and per-policy summaries now add each row's known actual subtotal, falling back to the legacy usage.known_cost_usd field when necessary. Fully known rows contribute their exact total exactly once. New normalized rows expose known_cost_usd directly; publication permits only that validated amount and does not expose the underlying usage object.

Actual totals, unknown-run counts, conservative bound accounting, billing completeness, and dispatch halts are unchanged. Reservations and upper bounds never become known actual charges. Missing/invalid subtotals remain absent at row level; the aggregate is the sum of accepted known amounts, not a declaration that unresolved calls cost zero.

## Validation

- Existing pinned offline guard denied real credentials, production databases, DNS/INET and GPU in parent and spawned processes.
- Focused regression: **137 passed in 2.43 seconds**, covering new known-cost tests plus existing evaluation, bounded-billing and published-evaluation tests.
- Cases include Store normalization with an unresolved HTTP 529 call; legacy rows; exact/partial mixed policies; no double counting; pending/fixture exclusions; nonfinite, negative, excessive precision, bool and float inputs; decimal magnitude span; allowlisted public projection; read-only publication.
- Ruff check and format passed on the three changed source/test files.
- Root owns final combined regression. This report does not claim that full regression has completed.

## R3 read-only reconstruction

The original campaign remains byte-identical:

`runs/evaluation/live/20261025T121115251021Z-2fe7da84/campaign.json`

SHA-256: `5ef7f80eed43b5a68bf660be9286b1d815ec9a1f01beca6e159582e617ffd175`.

| Field | Saved historical summary | Recomputed private/public summary |
|---|---|---|
| known_cost_usd | 0 | 1.20596190 |
| total_cost_usd | null | null |
| unknown_cost_runs | 9 | 9 |
| billing_complete | false | false |
| bounded_cost_runs | 8 | 8 |
| unresolved_cost_runs | 1 | 1 |
| conservative_total_usd | null | null |

Receipt: [cost-aggregation-r3-read-only.json](cost-aggregation-r3-read-only.json).
Test log: [cost-aggregation-tests.log](cost-aggregation-tests.log).

No historical campaign or stored summary was rewritten, no ledger/profile was opened or modified, and no provider call or GPU workload was dispatched. The unresolved charge and existing billing halt remain intact. R3 target 3/9 and the original 6/9 gate are unaffected.
