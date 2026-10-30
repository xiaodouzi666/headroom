# Encumbered public availability independent review — 2026-10-30

PASS for the reviewed donor read paths. No source changes were made to allocation.py, demo_binding.py, judge_binding.py or snapshot_public_binding.py by this reviewer.

`allocation._budget_state` sums only actual attempt `charged_usd` into `charged`. Permanent external funding commitments are separately listed and summed into `encumbered`; they do not invent a provider attempt, actual cost or charge.

Demo, judge and public snapshot run admission calculate remaining availability as `effective authorized total − existing charged − external commitments`, and clip the new run limit to that remaining amount. The binding's total limit remains the original authorized total (or valid existing extension total), rather than reducing it by the hold. `BudgetLedger` then includes the hold exactly once when checking that unchanged overall limit. Reducing the binding total as well would double count the commitment; these paths do not do so.

Three guarded temporary-ledger integration tests passed. Each starts with an actual immutable hold leaving exactly$0.10, verifies public availability remains true, confirms the next binding clips to$0.10 while preserving the original total cap, successfully opens the run budget (a double deduction would reject it), settles exactly$0.10 and confirms both hold and charge remain separate while public availability becomes false. The snapshot and ordinary judge paths share the same exhaustion state. These tests use temporary fixtures and synthetic settlement, not provider spend or production account evidence.

Test evidence: focused.xml and focused.log; checks and reviewed revision hashes in verification.json. No provider/network/GPU dispatch, production database mutation, or actual funding transfer was performed.

A separate legacy F3 child planner still computes its displayed remaining amount from charged alone. The underlying donor ledger admission still counts holds and fails closed, so this is not an overspend path. The new isolated repair controller must continue using a separate authorized receipt and ledger; it must not reuse the old F3 allocation alias. Binding/controller review remains a separate required check.

## Final v3 controller read review

The final source-only controller review passed: `reports/repair-followup-20261030/execute-fixed9.py.txt` is pinned by its proposal; the proposal and active receipt bind the profile, new ledger identity and both immutable donor holds. Its repair cap is4.890504400 USD. The F48 hold1.288313628 plus judge hold3.612190772 equals4.900504400; a separate0.01 buffer leaves the repair cap, while exactly0.30 remains in the original F48 pool. This changes no total future commitment from v2 and does not count that retained0.30 again in the new repair pool. The review did not inspect a real account balance or execute these transfers.

The controller sets the new `HEADROOM_BUDGET_DB_PATH` before spawning a child; the installed CLI copies that environment when no legacy allocation child binding is used. Each fixed-nine cell appears once with no top-level retry. Before admission it requires the new ledger to be quiet/resolved and to have a complete0.60 run allowance. It retains fixed9/6, six internal repair rounds,20 updates, seed1337 and480-second supervision. Each recorded target is suppressed unless execution is terminal with closed/resolved cost, no halt, at most0.60 charged, cleanup, wall and CLI receipts; it stops on an unsafe child. Unrun rows preserve null target, cost and run identifiers. All implementation modules are included in rebuilt source pins.

The script uses Python `assert` for controller-level gates, so the reviewed invocation must use standard Python with assertions enabled (no `-O`). Underlying budget admission remains separately enforced. No controller execution or production DB/provider/GPU action occurred during this review. `controller-v3-review.json` records the exact reviewed source hash.

Root subsequently added an explicit `sys.flags.optimize` rejection to both activation and execution scripts; source-only reinspection confirms an exception is raised before optimized execution could bypass assert gates. The final controller and activation hashes are recorded in the JSON receipt. No other execution semantics changed in this final read review.
