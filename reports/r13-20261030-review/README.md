# R13 development-repair projector — prepared only

The tool `project-r13.py.txt` accepts only the distinct R13 campaign path and `headroom.development-repair-campaign.v2`, scope DEVELOPMENT_REPAIR_FOLLOWUP, a real 40-character source commit, the original nine ordered cells and minimum six memory targets. It rejects v1/F3 inputs, relabelling another path, missing starting-pool accounting and modified historical scores. R12 campaign/report/controller bytes are untouched.

No real R13 campaign was read or projected during this preparation. No terminal result, acceptance score or publication is asserted. The twenty offline checks use temporary synthetic fixtures that are removed afterward. They exercise the existing API registry reader and product projection without a network request.

## Fees and boundaries

Each R13 attempted row is reconstructed from its saved per-job report, first-round diagnosis, bounded round patch/verification artifacts, usage and settlement. Unrun rows keep null run identity, target and costs. Unknown actual remains null. A retained unresolved reservation is recorded separately from a settled exact/verified charge; it is never called an exact provider expense.

`metrics.cost` covers only R13 attempted rows. `whole_pool_accounting` separately retains the exact starting and latest saved v2 pool snapshots, including the earlier R12 full reservation and unknown actual. Prior attempt identities, charges and unknown actuals may not disappear, change or be relabelled as R13. New pool charges must belong to saved R13 run identities and reconcile to R13 retained-row charges where available. Unknown whole-pool actuals are never subtracted to manufacture a campaign actual total. The saved model ledger USD is not an invoice or tax estimate.

If terminal pool accounting is unavailable, the projection preserves explicit nulls and the read failure. A last-known snapshot is not promoted to current truth. The tool does not read or update a live ledger, account balance, provider invoice, service, credential or controller. Saved source artifacts are opened read-only, hashed, and rechecked for changes before the review receipt is written.

## Root-controlled execution after terminal review

Only after independently confirming R13 is terminal, run from the azuki repository with a new output directory and identifier:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python reports/r13-20261030-review/project-r13.py.txt --campaign runs/repair-followup/execution-r13-20261030/campaign.json --output reports/r13-20261030-review/terminal-review-UNIQUE --id r13-terminal-UNIQUE --terminal-reviewed
```

Choose lowercase letters/digits/hyphens in the identifier. Without `--terminal-reviewed`, output is explicitly provisional and memory_threshold_met stays null. The flag records the caller's independent confirmation; it does not inspect process state. Running rows or a running controller are refused. The fixed nine denominator and six-target requirement never change; memory threshold is not overall acceptance.

Outputs are a new `summary.json`, a proposed single-entry staging registry and campaign readable by the existing API/product projector, and a source/output hash receipt. This is review staging only: it never merges or replaces the live registry or publishes a result. Existing output directories are refused.

## Offline evidence

`offline-verification-formatted.json`: 20 checks pass, including fixed schema/scope/sha/thresholds, preservation of prior R12 retention, campaign-versus-pool cost reconciliation, unavailable-accounting unknowns, all nine null unrun rows, API/product reading, source-path identity and overwrite refusal. Syntax, formatting and Ruff pass (the inherited ValueError refusal interface retains a TRY004 exemption); git diff --check passes. The first fixture attempt lacked explicit condition metadata and was corrected; its log is retained. No provider, GPU or worker subprocess is available to the verification helper.
