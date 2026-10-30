# R8 summary and review-only projection

Prepared 2026-10-30. This is an offline projection tool, not an R8 result or publication.
R8 has not been prepared/executed by this agent. The script does not open any ledger,
credentials, model client, GPU workload, HTTP endpoint or production registry.

## After the reviewed R8 controller finishes or stops partially

From the repository root, substitute the actual controller output directory below:

```sh
.venv/bin/python reports/f3-retry-20261030/summarize-r8.py.txt \
  --campaign runs/REPLACE_WITH_R8_OUTPUT/campaign.json \
  --output reports/r8-20261030-review \
  --id r8-20261030
```

The input must be a new retry campaign with revision r8, the original ordered nine
cells, fixed denominator 9, memory target minimum 6, and memory-only threshold scope.
Old R7 input, a running row, reordered/missing cells, conflicting report run identity,
uncertified target claims and contradictory cost metadata are rejected.
The output directory must not exist. The CLI only reads under runs/ and creates a
new directory under reports/. Symlink inputs are rejected; artifact reads are bounded.

Outputs:

- summary.json: nine rows, saved round-01 category/valid/readiness and issue codes,
  source hashes, fixed-nine metric counts and accounting evidence.
- staging/public-evaluations.json and staging/published-evaluations/r8-20261030.json:
  an allowlisted single-entry proposal validated by the existing API and product
  projection. This manifest must be reviewed and merged, never used to overwrite
  the live registry. No acceptance banner is emitted.
- projection-receipt.json: successful source recheck, source/helper/script hashes,
  output hashes and metrics. Absence of this receipt means any review output is
  incomplete and must not be published.

The helpers evaluation_outcomes, summarize, _public_row, _registry, _campaign and
product_evaluation are reused; no alternate scoring framework or serving path is added.
Helper/script source and every read artifact are rechecked before a success receipt.

## Evidence boundaries

- Every headline stays /9, including not_run. The public format marks not_run
  provenance unknown so the existing API does not count it as an executed live run;
  its explicit status and the private summary preserve the unrun state.
- Unknown/unverified scenario truth is not counted as correct or incorrect.
  Raw category match, valid correct first cause, valid ready diagnosis and
  ready-valid-correct first cause are separate counts.
- The saved round-01 diagnosis may already include same-round bounded supplements.
  It is not necessarily the first raw model response. Final/later diagnoses are not
  substituted for the saved first round.
- Memory target threshold is only the memory target threshold. Overall acceptance
  remains not_assessed. A target is copied only with matching report and execution
  certification; no hidden assumption about full quality, first cause or cleanup is
  introduced by projection.
- Unknown actual fees stay null. Known actual subtotal, resolved conservative charged
  amount and unresolved charge counts are separate. Only this revision's attempted
  rows are totaled; this tool does not re-audit the global/F3 ledger or provider bill.
- Unselected or uncompleted candidate captures are not reported as a successful
  after measurement. Original controller/run artifacts are never changed.

## Offline verification

Unchanged v4 isolation guard (parent and spawned negative probes) passed.
Final synthetic suite: **14 passed in 1.73s**, exit 0. Initial 14-pass receipt is also
retained; the final rerun adds the summary script itself to the before/after helper
hash set. These are two overlapping runs, not 28 distinct tests.

Cases cover partial nine-row execution, unknown truth, raw/valid/ready distinctions,
unknown actual versus charged bound, all nine not_run, immutable historical input,
invalid fixed-suite identity/scope, conflicting report/charge, changed/symlink
sources, refusal to overwrite existing publication, and no success receipt after
helper changes. Fixtures use a temporary directory; no production run is read.

Final script SHA256:
`06528558a057194746e6fbb82998381224d7c60efd45325545afb7d39946c2e3`.
Full command, source hashes and elapsed time: r8-projection-focused-final.json.
Test source is preserved as test-r8-projection.py.txt; no test is added to production.
