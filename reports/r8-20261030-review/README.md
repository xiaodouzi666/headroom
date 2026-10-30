# R8 fixed-nine review — 2026-10-30

**R8 finished all nine scenarios: 0/9 memory targets, below the unchanged 6/9 requirement.**
Saved first-round categories match 7/9; 5/9 are also valid and correct, and only
2/9 are valid, correct and ready for patching. s5 and nanoGPT truth remain
unverified and are not counted correct or incorrect. The denominator stays nine.

Source: runs/final48-f3-retry/execution-r8-20261030/campaign.json,
SHA256 3b2c2119b4d2d3aedbb8cfda95247d2d0bfca713aa2a52dfcc2456b1f2c01a50.
The read-only projection was generated before subsequent diagnosis-feedback
source changes. The nine controller rows have certified execution; this does not
make their repair results successful.

| Scenario | Final status | First-round valid / ready | Target |
| --- | --- | --- | --- |
| s1 | needs_human | yes / yes | no |
| s2 | needs_human | no / no | no |
| s3 | needs_human | no / no | no |
| s4 | needs_human | yes / no | no |
| s5 | needs_human | no / no | no |
| s6 | needs_human | yes / no | no |
| s7 | needs_human | yes / no | no |
| s8 | failed | yes / yes | no |
| nanoGPT | needs_human | no / no | no |

s1 stopped after a round-02 dependency declaration error. s2/s3/s5 and nanoGPT
retained invalid evidence-request declarations. s4/s6/s7 retained genuine
needs_more_info. s8 reached several valid-ready diagnoses but ended with a
ResponseValidationError; no successful final configuration is inferred.

## Costs

This revision's actual total is **null**: all nine runs retain some unknown actual
cost. Known actual subtotal is **$1.00007874** and the resolved conservative charged
amount is **$1.02829080**. No unknown charge becomes zero. This is stored accounting
evidence, not a provider invoice re-audit.

R8's saved terminal accounting reports original F3 plus all retries charged
$2.03988364 of the same $4 scope, leaving $1.96011636. The saved global F48 remaining
amount is $3.087750248. These are the terminal snapshot, not a later live balance.

## Nano annotation

All eight synthetic cases now contain a complete exact ID set; all eight source
fingerprints match their saved evidence. R7's separate 5/8 complete result remains
unchanged. None of the eight meets the 80% heuristic-agreement requirement:
62.5%, 18.18%, 7.69%, 40%, 18.18%, 50%, 0%, 0%, respectively.
This is improved observed coverage, not passing classification or controlled
proof that the schema change alone caused it. Repository nanoGPT is recorded
separately (complete, 38.89% agreement) and does not enlarge the eight-case metric.

## Outputs and publication boundary

summary.json contains the nine rows, source pointers/hashes and separate
raw/valid/readiness/target counts. nano-review.json contains per-case saved-ID and
fingerprint checks. projection-receipt.json rechecks every input and hashes the
generated output and reused helper source.

staging/ is a proposal validated by the existing API and product projection.
It has no overall-acceptance banner and was **not published**. Its single-entry
registry must be reviewed and merged, never used to replace the live registry.
R7 and all original run artifacts were preserved. The review performed no model
call, GPU job, production mutation or rerun.
