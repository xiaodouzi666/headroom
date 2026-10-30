# R9 preparation and controller review — 2026-10-30

Reviewed source commit: 5817a723df82bf9596397f9ae95598925088f1e0.

The independent read-only review found no remaining blocker in the prepared R9
proposal. This review did not create claims, run inference or start GPU jobs.
The root agent subsequently started the existing controller; its outcome is
separate from preparation and must be read from the R9 campaign.

## Preparation identity

- Proposal: .cache/f3-retry-20261030/r9-proposal.json
- Canonical proposal digest:
  e6928a3bee5007e60fc73b53fb0dc3a1de9052453cb2124451960ef8ef52521d
- Preparation: runs/final48-repair-preparation-20261030-r9/preparation.json
- Canonical preparation digest:
  ba0ad679dc0c4880f09ccff501102ead9d98eb43be3ec1b7aa332fbe023a0bdc
- Independently rehashed 30 input pins and 170 implementation pins: no mismatch.
- Original controls, cells, input pins, source files, calibration and repository
  identities are unchanged. All nine bound requests retain 20 optimizer steps,
  seed 1337, six rounds, USD 0.60 per-child admission and USD 6.43 F48 daily cap.
  The outer controller deadline remains 480 seconds per cell.
- Current validation-feedback and diagnosis source hashes are pinned.
  No source changes are permitted during the campaign.

These are canonical object digests, not SHA256 of pretty-printed JSON bytes.

## Funding and failure boundaries

The original F3 twelve children and every retry revision cumulatively consume
the original USD 4 F3 cap inside the same F48 receipt and ledger. This does not
create funding, reuse an old cell claim or spend from the separate judge pool.

The root agent's preparation accounting reported F3 remaining USD 1.96011636
and F48 remaining USD 3.087750248, with all costs resolved. These match the
saved R8 terminal accounting; this review did not query the provider balance or
a live ledger independently. Each new claim rechecks both remaining amounts,
requires full USD 0.60 admission, and rechecks source/request/profile/receipt
identity before reservation and dispatch. Unknown actual cost remains null;
resolved conservative bounds may be charged. Unresolved cost, cleanup uncertainty,
pending claims or changed inputs block later admission.

The remaining amount does not guarantee all nine can dispatch. If admission
stops, unexecuted rows remain not_run within denominator nine. The 6/9 threshold
is only the memory-target threshold, not overall acceptance.

## Reviewed commands

Prepare was performed by the root agent after source freeze:

    .venv/bin/python reports/f3-retry-20261030/prepare-fixed9-retry.py.txt --revision r9 --original-preparation runs/final48-repair-preparation-20261029-v4/preparation.json

Reviewed controller invocation:

    .venv/bin/python reports/f3-retry-20261030/execute-fixed9-retry.py.txt --proposal .cache/f3-retry-20261030/r9-proposal.json --expected-sha256 e6928a3bee5007e60fc73b53fb0dc3a1de9052453cb2124451960ef8ef52521d --output runs/final48-f3-retry/execution-r9-20261030 --execute-reviewed

Do not replay this command once its revision has started. The controller uses
the normal CLI/runtime path and requires terminal, cleanup and cost-settlement
evidence; it is not an injected/mock production path.

## Review-only projection

The root-created summarize-r9.py.txt is exactly the R8 script after only r8/R8
label replacements. Independent comparison and AST parse passed; the R8
original remains unchanged. R9 script SHA256:
87e4ad7606b1c1feef7ed440e9da072b9c29deca82911a39b69b56bad2a8744e.

After terminal state, generate into a fresh review directory. Keep raw-category,
valid-and-correct, ready and memory-target counts separate; unknown truth is
never correct. Exact actual cost remains null when incomplete, with known
subtotal and resolved charged bound separate. Staging output is not publication.
