# R15 reviewer — prepared before the campaign

Run after the campaign terminates:

    .venv/bin/python reports/r15-20261030-terminal-review/review.py.txt

Default input is runs/repair-followup/execution-r15-20261030/campaign.json. The preparation path, ledger path and service name can be supplied explicitly with --preparation, --ledger and --service if the controller uses a different identity.

An absent campaign returns not_started without creating a terminal review. A running campaign returns pending. Terminal output preserves the original rows and exact saved diagnoses, patches, rounds, verification, source pins/revision, readonly Store/ledger costs and cleanup observations. Unrun cases remain unknown under the unchanged denominator nine and target six. A complete nine-case claim requires nine terminal rows plus their saved case reports; a mere controller completion is separate.

The reviewer never instantiates/migrates a BudgetLedger or dispatches any model, GPU, retry or deployment. GPU cleanup is checked only from saved Lab gpu_after artifacts. Current worker PID presence is read from /proc and is not treated as authenticated process identity. It uses readonly SQLite connections and writes only a fresh report JSON/Markdown; rerunning retains the old report and writes a timestamped new one.

Preparation verification used only temporary synthetic JSON/SQLite fixtures. Eight checks passed: absent/pending states, partial fixed-nine accounting, unknown unrun results, unavailable/unknown costs, distinct known actual/charged/unknown fees, readonly databases and no overwrite. Ruff and formatting checks passed. No actual R15 campaign or live financial database was read during preparation.
