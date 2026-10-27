# R6 automatic repair implementation and bounded continuation

The owner requested continued repair to at least 6/9 using existing gifted credit only. The last independently measured result is R5: 3/9 targets and 6/9 valid correct first causes. Earlier campaigns and human controls are not pooled. R6 now has a separately audited result below.

## R6 measured result — 2026-10-27

The finished nine-slot R6 campaign at source commit `4f4e67d` reached **2/9 automatic targets (s3, s4)** and **3/9 valid correct first causes**, with five unknown causes. The unchanged minimum of six is not met. R5 remains a separate complete campaign with 3/9 targets and 6/9 valid causes. Scores are never pooled across campaigns.

| Scenario | R6 outcome | Evidence boundary |
|---|---|---|
| s1 | needs_human | Candidate completed 20 updates, peak 24.750 to 17.112 GB, but 160 backward scalars could not be compared under the supported reference contract. No numerical mismatch was measured. |
| s2 | needs_human | Generated forbidden `--accum-steps` and invalid source quoting. Existing policy correctly rejected it; exact allowed aliases were not provided in feedback. |
| s3 | target met | All observed per-run acceptance gates passed. |
| s4 | target met | All observed per-run acceptance gates passed. |
| s5, s6, s7, s8, nanoGPT | budget_exceeded | Each completed a baseline and one Nano annotation attempt; no Ultra diagnosis or Super patch request was dispatched. The new diagnosis/precision paths were not tested on them. |

The reason for the five budget stops was **insufficient room for the complete next-request reservation**, not a new HTTP 529 or a confirmed empty provider account. Ultra requires $1.097728 under the unchanged verified full-context upper bound. After s5 annotation, only $1.095801704 remained; the final original development allocation has **$1.082960504 net** left. No estimate-based admission, recharge, reserve transfer, unknown-cost release or new pool was used. See [reservation boundary](reservation-boundary.md).

R6 conservatively charged **$0.50181554 net**: known actual subtotal $0.47373284 plus $0.02808270 retained unknown. Its actual total remains null. The final ledger contains 143 closed runs, 812 settled attempts and two retention reviews, with zero pending/unresolved charges. All prior rows/amounts are preserved; overall conservative usage is $13.094797036 against the original $14.17775754 runtime limit. These are application ledger amounts, not a provider invoice or card charge.

The independent [history audit](independent-audit-history-v4.json) binds the executed source inventory, original funding chain, all nine run IDs, CLI evidence and preserved failed/unknown gates. It does **not** accept the campaign. The unchanged wire contract [refused the campaign](reasoning-wire-refusal.json) because five runs had no diagnosis/patch attempts; no wire-audit success is claimed. Seven nonzero CLI exits and incomplete candidate evidence remain visible.

Historical artifacts and the original PLAN are unchanged. Follow-up feedback fixes are qualified separately; they cannot retroactively change this score.

## Failure-specific implementation

- Feed the patcher bounded, hash-bound excerpts for the host's existing undefined-name rejection. Coordinates identify the rejected candidate, while edits must still use original source spans.
- Explain exactly which source binding triggered an existing MODEL_CHANGED rejection, including before/after counts and source coordinates. This does not relax that policy, whitelist logging, or prove model equivalence.
- Classify the exact host failed/NEW_UNDEFINED_NAME outcome as rejected before execution, only when owned patch evidence and absent verification support it. Contradictions and unrelated failures remain unknown.
- Clarify source-defined loss reductions, required versus unused alternative dependencies, and overlapping phase peaks. Original workload, precision, whole-plan feasibility, numerical tolerances and scoring gates remain unchanged.

- Add precise precision-intent rejection clauses and terminal failure metadata. Only an initial truncated/length diagnosis can use its existing one supplement with Ultra thinking disabled, under the existing verified control and unchanged 16384-token/two-call limits. This is requested-mode evidence, not a promise of server behavior or numerical success.

The first promoted feedback integration passed 136 guarded tests. Candidate-specific isolated test results are retained in the server cache; the diagnostic integration passed 156 tests. The full unfiltered guarded suite passed **3649 tests in 776.43 seconds**, with all 333 source entries, original PLAN and guard unchanged. These tests qualify the executed R6 sources; they do not establish repair success.

## Finance and historical failures

R5's original technical failures remain recorded. Any optional continuation must independently preserve its exact financial/history/source proof, retain its nonzero exits and missing candidate evidence, and avoid treating financial continuation as technical acceptance. The original runtime allocation has $1.584776044 net remaining after R5. Admission must still reserve each request's full verified upper bound. No recharge, new pool, or transfer from the judging reserve is authorized by this implementation.

A retained scope limitation: detailed name/model-binding excerpts go to the current patcher repair request. If a new problem appears only on the final allowed patch attempt, the next outer diagnosis still receives the general detail/policy feedback rather than those new precise excerpts. No extra retry is added.

Original PLAN and historical manifests/runs remain unchanged. Public deployment stays deferred. Replay remains removed.
