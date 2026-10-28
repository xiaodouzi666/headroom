# F3 preparation and sequential driver — offline checks

The reviewed pack contains **12 independent cells**: the original fixed nine from `eval/mvp_phase1_v2.yaml`, two additional s2 numerical tiers, and one HF Trainer case. The fixed-nine denominator stays **9** and its threshold stays **6**; the extra cases do not enter that score. No live repair, model, Tavily or GPU call was performed, and no actual allocation was created.

`headroom/acceptance/final48_repair.py` prepares and verifies source, manifest, historical s2 calibration, nanoGPT revision, implementation and request pins. The default command below only reads and reports preparation. An explicit `--output` saved the review pack privately in `runs/final48-repair-preparation-20261029/preparation.json`; `--verify` reconstructed the same pins successfully. The preparation digest is recorded in [receipt.json](receipt.json) and must be refreshed after any pinned code/source change.

```sh
.venv/bin/python scripts/prepare_final48_repair.py
```

The command returned `mode=prepare`, `planned_cells=12`, `executed_cells=0`. It did not read a runtime profile or ledger. `bound_requests` and `cell_request_pins` can build the exact receipt input map once the profile path and approved daily allowance are known; these helpers do not activate an allocation.

The explicit execution path binds the reviewed digest, exact 12-request map, receipt and profile before claiming F3 once. It requires the reviewed `final48-diagnosis-only-2000-v1` profile policy, uses the installed-CLI supervisor, preserves the 0.60 USD per-cell allowance, and maintains one F3 scope capped at 4 USD. The approved daily limit belongs to the entire pool and is inherited from the receipt; it is not silently replaced by the F3 scope cap. Settled actual fees remain authoritative, unknown charges stay unknown, and insufficient funds retain unrun cells. A failed cleanup or uncertified execution stops further dispatch. HF configuration checks and new numerical-tier summaries remain separate from the primary score.

## Validation

- 14 focused tests passed in 3.27 seconds; [test output](focused-tests.txt). These deny network and credential access and never import or execute the sentinel workload sources.
- One test uses the real allocation/ledger APIs in a temporary directory and a fake supervisor: an earlier F1 fixture spends 1.5, then 12 F3 fixtures spend 3.6 total under an approved 6.43 pool/day allowance. The combined 5.1 settles correctly under the parent total ceiling of 5.5; the 4 USD F3 scope is preserved. These are test amounts, not a new user approval or real charge.
- Negative cases cover missing authorization, modified source/preparation, the legacy default profile, repeated parent claims, shortfall, unknown/overrun costs, and incomplete cleanup. Unrun and running intents are not labelled measured; offline successes cannot satisfy the live 6/9 threshold.
- Ruff check/format passed. The redacted publication scan is recorded in the receipt.

## Still unproved

The real 12-cell campaign has not run. This work creates no new pairing proof, independent s2 success, HF candidate, live billing result, or permission to spend. An approved allocation with its exact preparation/request pins remains necessary. The 4 USD scope may end before all cells run; resume/reset of a consumed once-only claim is intentionally unavailable. Historical results are unchanged.
