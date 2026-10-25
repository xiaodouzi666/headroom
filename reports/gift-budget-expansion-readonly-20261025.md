# Gift-only runtime allocation feasibility — read-only review, 2026-10-25

This review authorizes no dispatch, changes no profile/ledger/allocation, and does not reconcile an invoice. The current first MVP continues with the existing all-time runtime pool **9.99964904 USD** and the existing pinned profile. A browser refresh timed out; **25.28 USD is an unrefreshed observation and cannot authorize expansion**.

## Authorization and preserved obligations

The exact recorded human instruction is: “允许后续模型调用，只用现有赠送额度，不充值、不超额。你继续按原计划把剩下的开发和验收做完。” See reports/live-campaign-20261025/authorization.json:3. It contains no human-imposed 10 USD runtime lifetime cap. The 9.99964904 figure is an internal allocation: 16 total token USD minus 6 for external probes minus 0.00035096 historical external probes. See allocation.json:3–16 and docs/LIVE_EXECUTION_PLAN.md:7–16.

However, the **10 USD judging balance is an original-plan obligation**, not expendable slack: docs/PLAN.md:360 requires Token Factory balance at least 10 USD before November 25. Keep this reserve and the existing **0.89 USD** fee/rounding buffer. The earlier allocation used a 1.21 reference tax multiplier, not invoice reconciliation. The proposed 2.0 multiplier is a more conservative future funding calculation; neither multiplier supplies a missing provider-fee guarantee.

The unused external-probe pool is an allocation, not new account credit. The old unused-probe-allocation-option.json describes a hypothetical transfer to runtime 14.17775754 while retaining external debt; it explicitly was not applied. It cannot simply be added again to either the refreshed balance or a new profile.

## Read-only accounting snapshot

SQLite was opened with mode=ro and query_only, without constructing BudgetLedger, migrating tables, loading .env, or reading a private profile. At 2026-10-25T06:58:55Z:

| Component | Token USD | Treatment |
| --- | ---: | --- |
| Runtime exact known usage, 430 attempts | 5.144831916 | Already included in lifetime charges |
| Runtime reviewed retained, 1 attempt | 0.01644864 | Unknown actual; keep full charge |
| Runtime settled upper bounds, 30 attempts | 0.01520376 | Unknown actual; keep full charge |
| Runtime conservative total C, 461 attempts / 79 runs | **5.176484316** | Same persistent ledger, never reset |
| External historical/new exact known usage | 0.77289846 | Outside runtime ledger; do not import twice |
| External 900k-probe retained debt | **1.049344** | Unknown actual, release_authorized=false |
| All unknown retained U | **1.08099640** | Runtime 0.03165240 + external 1.049344 |
| All runtime + external conservative history | **6.998726776** | Exact actual total remains unknown |

There were zero pending attempts, zero halted runs, and zero open runs. Same-UTC-day runtime commitment was 2.098590644. These are a timestamped snapshot, not immutable future balances. The external figures and permanent retention are preserved in allocation.json:17–34 and mvp-v7-finance-review.json:319–323.

Do not count an unknown charge as zero, release its ledger reservation, or assume an aggregate account balance already reflects it. Even if subsequent billing evidence establishes that a retained amount is reflected in account consumption, its historical ledger receipt must remain intact; any reduction of the separate account-liability allowance needs explicit reconciliation evidence.

## Formula and illustrative limits

Let:

- B = freshly verified remaining gross gifted balance, with its account/credit scope established;
- C = same-ledger conservative lifetime charges at that reconciliation point;
- U = all retained/pending liabilities not proven already reflected in B, both runtime and external;
- M = reviewed gross-cost multiplier (illustration below: 2.0);
- J = 10 USD judging reserve; R = 0.89 USD fee/rounding buffer;
- P = any separately preserved future external-probe allowance in token USD;
- D = any known gross charges not yet reflected in B, or other independently committed gross liabilities;
- L = proposed total lifetime runtime allocation, including all history.

The remaining runtime allowance is L - C, not L. Require:

    M * ((L - C) + U + P) + J + R + D <= B

Equivalently:

    L <= C + (B - J - R - D) / M - U - P

This does not re-charge old known usage: B is already a remaining balance; only future runtime work and not-yet-reflected liabilities are reserved against it. It deliberately reserves unknown history that may still be billed. If billing latency or scope prevents establishing D, retain a conservative allowance or do not expand.

For illustration only, assume the unrefreshed B=25.28, C=5.176484316, U=1.08099640, M=2, J=10, R=.89, and **P=D=0 only after evidence establishes those facts**:

| Proposed lifetime L | Additional runtime token allowance | Gross requirement including U, J and R | Margin versus 25.28 |
| --- | ---: | ---: | ---: |
| Current 9.99964904 | 4.823164724 | 22.698322248 | 2.581677752 |
| 11 | 5.823515684 | 24.699024168 | 0.580975832 |
| Mathematical edge 11.290487916 | 6.114003600 | 25.280000000 | 0 |
| 16 | 10.823515684 | 34.699024168 | -9.419024168 |
| 17 | 11.823515684 | 36.699024168 | -11.419024168 |

**16 and 17 do not fit this preserved-reserve calculation.** The exact edge is not a recommended allocation. Even 11 is only a conditional arithmetic example, not an enabled profile or approval.

The observed account statement reportedly includes Trial +1.94 and Builder credits +30.25, consumption -6.91, closing 25.28; header 29.69 differs. This review did not inspect or refresh that UI. Establish which balance/period is spendable and whether all components are eligible gifts. The original allocation excluded trial credit; a revised record must explicitly retain that exclusion or substantiate and record any inclusion. Never infer a missing charge or excluded balance component is zero.

## Technical feasibility and minimum safe transition

The code supports a versioned reviewed profile with a higher lifetime limit **without resetting history**:

- LiveProfile validates enabled/confirmed credit and authorized_total <= available_credit, but does not independently reconcile funds (runtime.py:77–107, 132–153).
- The orchestrator always constructs BudgetLedger on PROJECT_ROOT/.cache/budget.db and uses profile.authorized_total_usd (orchestrator.py:435–446).
- The limit is a reviewed instance input, not a stored baseline that resets with a new profile. _committed/open_run/reserve include every existing charge and open-run floor across the same SQLite ledger (budget.py:246–289, 315–350).
- Unknown/pending states and halts remain blocking, with only documented settled verified bounds/reviewed retentions permitted. Actual-usage history permanently requires provider-bound admission; closing a run does not re-enable estimates (budget.py:209–231).
- The current MVP driver intentionally pins the old profile SHA and 9.99964904 pool. It must not be silently repointed or edited during execution.

A future transition must occur at an idle boundary after fresh gift-balance and price/bound review. Preserve immutable old profile/allocation/receipts and record new profile SHA, predecessor SHA, human authorization source, timestamped UI/account scope, reconciled C/U/P/D, unchanged J/R, funding arithmetic, and before/after canonical ledger projections. Explicitly retire or reduce unused external-probe allocation so no later process can reuse it. Keep the same ledger path and every attempt/retention row; do not overwrite historical results.

Create a separate profile/version and newly prepared driver only after that record is reviewed. Keep the existing daily cap unless separately justified; in all cases combined same-day runtime plus external commitments must remain within its reviewed ceiling. A larger lifetime allocation is not permission to enlarge per-run actual-cost thresholds, per-request token bounds, retry counts, or any acceptance gate. No new configuration or model call was made by this review.

## Read-only source hashes

- docs/PLAN.md: e3afb65480c42066e919e0959ec8df9e03952e113fd2cf456d377056c6b61d56
- docs/LIVE_EXECUTION_PLAN.md: 02e7ffc06790f7731247dd03fe3451dad29e49bbaca93df02c95f7de4de19e96
- reports/live-campaign-20261025/authorization.json: 748a58b81c1cdbcae684df6d457681cfead987440cc7431e409bcdb9d0d8ef28
- reports/live-campaign-20261025/allocation.json: 3db9675ddc542bb2ba42f9929748deea64d3810e913f13c303615e78f88203c0
- reports/live-campaign-20261025/funding-review.json: a7e96360f9cf305ba04c705836371bc0d28526b11693cf6395876e07116becee
- reports/live-campaign-20261025/unused-probe-allocation-option.json: 94364afb791ff81282f75be9811f27cb2c89ea7a9d3b17919ed0a7452197dc0d
- reports/live-campaign-20261025/mvp-v7-finance-review.json: 97ae2ce4d5a19e706107fd4423cb4c680cd2a80279fffdc013b29e6f9a49c423
- reports/acceptance-v2-20261025/cap-review.json: 3f77202a6ca2bd896ba46c1a7ce38efe09e7c9bf088c22d64384051b7bcf5184
- headroom/budget.py: 55df4929cc5e1798e16b90e4fae0b0bb82cb231224fc2e17092c4c0d39bc306d
- headroom/runtime.py: 87b0ef04a62a7d6ef8eb3bb91dec09728c4ba5f8b6fe13d776fdca3c4b777c10
- headroom/orchestrator.py: 586abf889ddb4d3d5e479a4cc8a52a05f4c6bba6a73b234ec3a7765583d3d0a3
- reports/acceptance-v2-20261025/run_mvp_v2.py: 0cd1a0564149b3f0845fec837e8fe405460939a219a6e06647075140459b8fe2
