# Historical-positive regression and funding review — 2026-10-30

This package is offline. It reuses authentic saved model outputs to check preservation of host diagnosis and static patch application contracts. It makes zero new model calls, zero GPU runs and zero new repair-success claims. No historical source/report/diagnosis/patch, threshold or ledger is modified.

## Reproduce

From the repository root:

    .venv/bin/python reports/repair-positive-regression-20261030/replay-historical.py.txt

The runner verifies the immutable input hashes in historical-inputs.json, reconstructs host execution/reference metadata using the archived request/baseline/source, and runs the current full validator. It applies each authentic normalized Super proposal to a temporary private copy through apply_proposal. Candidate train.py SHA must equal the actual historical retained candidate SHA. Temporary copies are deleted. Network connections and subprocesses other than git, isolated py_compile and isolated Ruff F821 are denied. No target script is imported/executed. Source hashes are checked before/after, including during the replay.

## Results

| Positive case | Authentic source | Host valid/ready now | Static patch now | Candidate bytes equal prior retained output |
| --- | --- | --- | --- | --- |
| s3 | R6, run84f929ba8ace49b3829df6455419641d | yes/yes | passed | yes |
| s4 | R7, rune8213706570e478f9845e49e24c2b54b | yes/yes | passed | yes |
| s8 | R4, rund10adf0ffac74dcf8d874a460a2a3628 | yes/yes | passed | yes |

The exact full paths/hashes are in replay-result.json. These tests retain the historical scientific limits: s3 had20 paired identical scalar samples; s4 had an original-workload reference and first5 matching samples; s8 recorded identical scalars but full workload pairing was not established. This replay does not rerun or strengthen those measurements.

The newly bounded2k wire schema is a separate check. Authentic original long diagnoses have count/length failures there; no compatibility is inferred from host-validator success. This intentional narrowing affects NEW model generation and must be validated live. Nothing here truncates or edits old diagnoses to force wire acceptance.

## Earliest zero and mechanism

R7 had one target (s4); R8 was the first of the latest completed zero-target rounds. Between source6c7cde2(R7) and a148dfb(R8-stage), git diff for main diagnose.py, solver_context.py and diagnosis_schema.py is empty; diagnose.md changed29lines (13 additions/16 removals). That does not establish causality: requests/model generations were not controlled repeated pairs.

R7s4 proposed the retained-graph fix and an explanatory zero-saving no-op; it was ready and executed. R8s4 proposed the same retained-graph fix PLUS microbatch accumulation, then asked for optimizer input shape, effective batch and loss reduction axes specifically for the added accumulation step. The global needs_more_info stopped both steps. R10 repeats this type of blocking. This is evidence for a planning/dependency-selection failure, not proof that the original valid patch became statically inadmissible. R8s1/s8 had other problems (capture finalization and later response failure), so zero targets cannot all be assigned to one cause.

R4s8 used7290 Ultra completion tokens in one successful request; R7s4 succeeded within the later2000/false mode. Merely raising the token cap cannot be assumed necessary or sufficient. Bounded compact complete answers and actual response-failure evidence need independent checks.

## Budget decision

Fresh read-only accounting is in budget-review.json. Oldmain remaining1.082960504 net, FINAL48remaining1.787809228 net, judge remaining20.80543972 net, original F3subscope remaining.740368840. All charges are resolved; old/F48 exact totals remain unknown. These are separate existing commitments. None is treated as freely interchangeable.

For budget alone to accommodate nine cases each at the existing.60 ceiling, a new envelope needs5.40net (21%tax rounded up6.54gross). This cannot guarantee operational execution or success. A possible USER-AUTHORIZED transfer is to freeze the remaining FINAL48spendable1.787809228 and transfer that capacity, plus3.612190772 from judge capacity. Judge effective cap would become17.307809228, leaving17.193248948 after prior.11456028 spent. Keep oldmain1.082960504 unchanged, preserve all past receipts and create explicit transfer/accounting records. Total committed balance does not increase. Do not use the anonymous/demo route or old profile aliases to evade the F3scope.

Using the last private F8provider-balance observation (not refreshed here), current future commitments×1.21+$8reserve+$3.63lagreserve leave only approximately.10gross unassigned. It is unsafe to simply allocate another5.40net on top of all current commitments. A fresh provider observation and explicit user approval are required before any transfer/new pool. This review made neither.
