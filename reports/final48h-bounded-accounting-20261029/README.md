# FINAL48 bounded accounting correction

This is an offline engineering check and a recovery procedure, not a provider invoice or a new paid run. No live budget database, allocation receipt, service setting, model or GPU was modified during this work.

## Cause confirmed read-only

The new-pool ledger for run `12150a5b0cf445378edb784e6cc6c091` already contains a finalized provider tariff bound:

- Attempt `f80519136f3145f8b08e5e3ee2b89c0e`: reservation `0.01644864`, conservative charge `0.00378462`, actual charge `null`.
- `settled=1`, `dispatched=1`, `admission_kind=verified_provider_bound`, `charge_status=upper_bound`, `charge_basis=verified_tariff_missing_cache_count`.
- The run is closed. Its halt is `local_accounting_incomplete`, added by the new F2 allocation bridge after that bridge incorrectly required an exact actual fee.

The existing `headroom.billing_review.prepare_retention/execute_retention` protocol is for a different case: an unknown charge retaining its entire original reservation under `provider_charge_unknown`. It is not eligible for this run and must not be used to relabel it.

## Correction

`allocation._budget_state` now keeps two independent facts: `known` means exact actual fees are known; `resolved` means all attempts are finalized with exact fees, a verified tariff bound, or a full retained reservation with a matching persisted explicit review. Pending, undispatched bounded, local-estimate unknown, unreviewed unknown and invalid-bound attempts remain unresolved. Halts and active unrelated runs still block new admissions.

F2, F3 and F3b/F5 accounting use conservative `charged_usd` for every cap. Exact `actual_usd` and `scope_spent_usd` stay null where unknown. New `cost_resolved`, `scope_charged_usd` and `all_costs_resolved` fields make that distinction explicit. F2 remains at aggregate $0.30; F3 remains at $4; the same approved pool and inherited daily limit are unchanged.

The F3 driver consumer is a separately owned change; its receipt and verification must be reviewed with this correction.

## Explicit F2 recovery, not yet executed

Use the old, currently bound allocation receipt before any unused-task pin amendment. The proposal binds its exact receipt SHA, original blocked claim/settlement, and complete ledger snapshot. The original blocked decision is preserved both in a new ledger audit row and the registry recovery record. Neither attempt amounts nor provider usage/status are rewritten.

First independently verify the original process has ended and its cleanup completed. Save a private JSON review at `.cache/final48-allocation/f2-execution-review.json` containing:

```json
{
  "run_id": "12150a5b0cf445378edb784e6cc6c091",
  "execution_terminal": true,
  "cleanup_verified": true,
  "reviewed_by": "REPLACE_WITH_REVIEWER",
  "evidence": "REPLACE_WITH_EXACT_TERMINAL_AND_CLEANUP_EVIDENCE"
}
```

These booleans are required evidence assertions; this example does not establish them. Do not copy the placeholders as a completed review.

Prepare only, from the remote project directory:

```python
from pathlib import Path
from headroom.acceptance.common import file_record, write_json
from headroom.acceptance.demo_recovery import prepare_demo_recovery

root = Path("/home/xiaodouzi/workspace/headroom")
proposal = prepare_demo_recovery(
    root / ".cache/final48-allocation/receipt.json",
    project_root=root,
    run_id="12150a5b0cf445378edb784e6cc6c091",
    execution_evidence_path=root / ".cache/final48-allocation/f2-execution-review.json",
)
destination = root / ".cache/final48-allocation/f2-bound-recovery.json"
write_json(destination, proposal)
print(file_record(destination, 512 * 1024)["sha256"])
```

Review that exact proposal and its before-state. The explicit execution call, which has **not** been made by this work, is:

```python
from headroom.acceptance.demo_recovery import execute_demo_recovery

execute_demo_recovery(
    "/home/xiaodouzi/workspace/headroom/.cache/final48-allocation/f2-bound-recovery.json",
    expected_sha256="REPLACE_WITH_INDEPENDENTLY_REVIEWED_FILE_SHA256",
)
```

Execution refuses changed evidence, changed claim, changed ledger, a different halt, unknown/unreviewed charge, non-terminal work or unverified cleanup. It appends `budget_accounting_reviews` before clearing only the exact bridge halt. If a crash occurs before registry finalization, the original registry remains blocked; the same proposal can finish without duplicating or erasing the ledger audit.

After execution, verify the original attempt is byte-for-byte unchanged, actual remains null, the original blocked state exists in the audit, and both the remaining F2 scope and all pool caps deduct the conservative amount. An unrelated uncertain cleanup or unresolved charge must remain blocked.

## Offline validation

See [checks](checks.txt), [machine receipt](receipt.json), and [targeted secret scan](gitleaks.json). The three scoped test invocations overlap; their counts must not be added as independent scenarios. The final bounded/recovery file has 18 cases, including exact retained-review evidence, next F3/feature/F2 dispatch, altered evidence refusal and interrupted cross-database recovery. Existing real API/spawn/normal-runtime MockTransport and bounded runtime tests also passed. No paid calls or GPU tests were performed.

Following the root documentation commit `e9aac95`, all five owned source/test hashes still matched the recorded tested files, and `git diff --check` passed. Production recovery and receipt amendments remain separate operational steps.
