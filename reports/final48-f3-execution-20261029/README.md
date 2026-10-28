# R7 execution integration — engineering checkpoint

The fixed-nine campaign, two independent s2 tiers and one HF Trainer case now
have a prepared sequential execution path. The primary denominator remains nine
and the threshold remains six. All twelve cells are prepared; zero new live
cells have executed. No new allocation or authorization was created.

## What changed

The installed CLI carries an explicit numerical requirement and the exact child
allocation binding through the supervisor. Each new request rechecks that binding
before the normal budget admission and settlement. All children share one fixed
F3 ceiling, while inheriting the separately approved whole-pool daily limit.
Prior F1 costs do not incorrectly consume the F3-specific scope. Unknown costs,
uncertain cleanup and changed inputs prevent the next dispatch.

The prepared driver pins source, historical calibration, manifests, repository
revision and implementation. Only the primary fixed-nine count is used for the
six-of-nine threshold; the nested generic summary describes the attempted subset.
Additional s2 and HF outcomes stay separate. Unrun rows are not counted as measured.
The actual runtime must select the declared 2000-output-token, reasoning-off
diagnosis policy. The HF checker constrains source edits without claiming that a
configuration is valid or successful on hardware.

## Verification

[Integration receipt](integration.json) binds current source hashes and four
disjoint focused test groups: 91 CLI/worker/orchestrator checks, 29 allocation
checks, 14 prepared-driver checks and 16 HF configuration checks. All 150 passed.
This is not the final full regression. Initial failures and their fixes are
retained in the component reports; they have not been deleted or recast as passes.

- [CLI bridge evidence](../final48h-cli-bridge-20261029/README.md)
- [Prepared campaign and driver](../final48h-repair-20261029/README.md)
- [Allocation test output](allocation-tests.txt)
- [HF checker evidence](hf-configuration-validation.json)
- [F1 request package v7](../final48-f1-preparation-20261029/README.md)
- [Recording toolchain smoke](../final48h-media-toolchain-20261029/README.md)

F1 v7 retains all twenty-seven request-file bytes, input pins and scoring from v6;
only the changed allocation/orchestration implementation bindings were refreshed.
Both old request packs and old receipts remain available.

## Remaining requirements

The actual F1 and R7 campaigns, new numerical-tier records, HF repair, real
snapshot diagnoses, Watch trigger, public example, clean-clone repair and final
video are not verified by these offline checks. The earlier real campaign scores
remain unchanged. New-pool amount approval, then current balance/price checks and
activation, precede any funded execution. Public Verified runs still requires C.
The video smoke is isolated test material and cannot substitute for a real s3 run.

## Published revision and independent checkout

Commit `42c954ebf921122ad228c0a5455202a2edfcf39b` was pushed and matched
GitHub main. Commit hooks passed Ruff, format and Gitleaks. The existing clean
F5 checkout was fetched to that exact revision; its installed Python 3.12.3 CLI
imports its own checkout and exposes both explicit numerical options. Dependency
files were unchanged, so no install or Lab-image rebuild was repeated.
[Post-push receipt](post-push-clean-check.json) also verifies both frozen packs.
No real s3 repair or submission tag was produced, so F5 remains incomplete.
