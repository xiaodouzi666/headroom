# Two stale-test corrections

Only `tests/test_published_evaluations.py` and `tests/test_snapshot_integration.py` changed. No business source, public switch, numerical threshold or ledger changed.

- The exact public-catalog assertion still expected only R6/R5. It now lists the reviewed R7/R6/R5/Watch/browser-demo entries in their actual order. The existing historical fixed-nine, six-target, numerical and privacy assertions are unchanged; independent demos are not combined into a campaign success rate.
- The snapshot launcher test wrote `{}` as its publication fixtures. The current launcher correctly rejects that manifest before reaching the snapshot assertions. Its temporary project now has a valid version-1 manifest and explicitly offline, empty campaign, exercising the real validation and publication-copy path. Snapshot remains disabled despite the environment flag; the existing POST 503 and dispatcher assertions are unchanged.

The original failure-summary misattributed the stale catalog assertion to `test_disabled_submission_cannot_be_bypassed_with_judge_token`. The full log places it in `test_reviewed_public_suites_keep_fixed_denominators_and_private_data_out`. The public-access test actually stopped at the external closing guard's dir_fd path handling and was not edited here.

Validation: the two original tests reproduced their failures (2 failed in 1.13s). After the minimal edits, both pass together with the existing malformed-manifest, symlink and malformed-campaign rejection cases: **5 passed in 1.15s**. Ruff lint/format and diff checks pass. Exact commands, hashes and boundaries are in `receipt.json`; original and final output are in `before.log` and `after.log`.

These are focused offline checks using existing network/provider guards and temporary project fixtures. They are not a new full-suite pass, a model invocation, GPU experiment or production database operation. No commit was made by this subtask.
