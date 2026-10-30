# Nano annotation request identity constraints — 2026-10-30

Status: source and offline validation complete; no new live inference, GPU work,
claim, deployment or historical score change.

## Confirmed R7 evidence

Eight fixed synthetic cases from
`runs/final48-f3/execution-20261029-v1/campaign.json` were read.
Five annotation sets are complete: s1/s3/s4/s7/s8.
Their heuristic agreements are respectively 37.5%, 15.3846%, 20%, 0%, 27.2727%;
none reaches the original 80% criterion. The other three (s2/s5/s6) failed the
strict identity-set check. Their annotation artifacts retain zero output rows
after rejection, so the combined reason cannot identify whether each individual
response had missing, duplicate or foreign IDs. Raw rejected responses were not
reviewed, and no different cause is inferred.

All eight saved transport receipts state that the selected frame content was
complete. The actual requested ID counts were 10/14/18/15/17/15/16/14. This does
not establish that stack-only evidence is sufficient for semantic classification.
Per-source paths and SHA256s: r7-readonly-summary.json. All were rechecked unchanged.

## Minimal change

headroom/annotate.py creates a fresh schema from the unchanged StackLabels model.
The stack_id enum is exactly the IDs already present in the current transported
request. The annotation array's minItems and maxItems both equal that ID count.
Only neutral identities/count are added; no heuristic labels, categories, bytes,
or historical answers enter the model schema/messages.

The existing strict uniqueness/complete-set check remains. Exact array length
and an ID enum do not prove uniqueness by themselves: a response containing two
different labels for the same ID is still rejected by the host. Categories,
fingerprint binding, heuristic comparator and original eight-case/80% criteria
are unchanged. Output remains at most 3,000 tokens with reasoning disabled.
There is still one request, no automatic paid retry or fabricated missing label.

This closes a request-contract omission; it does not establish higher model
accuracy or turn R7 into 8/8. The five complete but low-agreement cases still
require genuine classification improvement and a future authorized live result.

## Verification

Unchanged v4 offline guard passed parent and spawn negative probes.
**45 passed in 1.46s**, exit 0: new schema tests plus existing annotate, call-view
and frame-transport tests. Actual SDK + MockTransport exercised native JSON Schema
and JSON-object fallback, exact on-wire enum/count, no oracle leakage, unchanged
output/reasoning limits, rejected missing/extra/foreign IDs, host duplicate
rejection and no cross-capture schema reuse. Ruff/format/diff checks passed.

Evidence: focused-initial.log/json and final-checks.json. This suite is synthetic
engineering evidence, not a new classification score. No API key, live database,
ledger or private runtime configuration was read.

## Funding boundary

The existing feature_allocation GROUPS['F3b'] is a $1 shared cap for exactly the
snapshot-s2, snapshot-nanogpt, snapshot-web and watch-s1 slots. It has no standalone
annotation slot. Existing R7 annotation calls were inside F3 repair runs; a future
R8 annotation is therefore part of that same F3 retry run allowance, with the
existing runtime Nano sub-budget of $0.02. No F3b annotation claim or new funding
route was created, and this audit did not query a live remaining balance.

Frozen source hashes:

- headroom/annotate.py: b0f2bf8981bf1db716cf956c147b2a8eae4aa5b1b113120ed5ac06bd3376449b
- tests/test_annotation_schema.py: 676c1e081280306b04dda0636e6e35eee08abeb9cfaeef072d66d11809f5c711
