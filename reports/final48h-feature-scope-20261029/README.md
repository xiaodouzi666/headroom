# FINAL48 feature inputs and execution handoff

This is a read-only inventory, not an execution receipt. Exact paths, sizes and SHA-256 values are in [preparation-inputs.json](preparation-inputs.json). Inputs came from F1 v7 and its R6 campaign; no broad filesystem search, model call, GPU run, profile or pool creation occurred.

## Current handoff and preserved inventory

The inventory JSON records the earlier preparation state and remains unchanged.
The subsequent [integration receipt](integration.md) and
[clean-checkout check](post-push-clean-check.json) record the completed feature
bridges at commit e97bc42 and the existing clean checkout updated to that commit,
with its own installed CLI importing its own source. The old checkout revision
and missing-helper fields in the inventory are historical, not current blockers.

The current prepared packages are [F1 v8](../final48-f1-preparation-20261029/final-preparation-check.json)
and [F3 v2](f3-preparation-refresh.json); both have zero executed requests/cells.
Their final input and implementation pins have been checked. Actual feature
intents, profile/day limits and registered slot maps still depend on A.

## Existing inputs

| Slot | Input | Boundary |
|---|---|---|
| snapshot-s2 | R6 capture efb0c5d0821540c191068761266618c2; 10,651,527-byte snapshot | Completed 20 optimizer updates. Its traceback is StepLimitReached, not CUDA OOM. Authored category: optimizer state. |
| snapshot-nanogpt | R6 capture a71a8224483b48d2af346130506e4d5f; 590,852-byte snapshot | CUDA OOM before an optimizer update; root-cause truth remains unverified. |
| snapshot-web | The same nanoGPT files in a separate Web slot | Upload/display acceptance, not a third independent scenario. |
| watch-s1 | scenarios/s1_batch_too_big; command python train.py | Use this narrow scenario directory as source root. All files copied by Lab are hashed in the inventory. |
| clean-s3 | /tmp/headroom-f5-20261029-krupo1aa/repo | Inventory recorded 42c954eb without feature helpers; superseded by the e97bc42 own-CLI check linked above. |

All six snapshot/trace/source inputs fit upload limits. nanoGPT's proposed source upload contains only train.py, not model.py or configurator.py; the inventory records model.py separately. The clean s3 source matches the main worktree's SHA.

## Preparation before claims

1. Integration and clean-checkout refresh to e97bc42 are recorded above. Before freezing the actual feature intent, recheck the selected checkout and its own installed CLI/imports; never point PYTHONPATH at the original tree.
2. After A supplies authorization, select the actual allocation profile and receipt-wide daily allowance. Authorization amounts remain null in this inventory.
3. Build intents using the existing pure helpers: snapshot_binding.snapshot_intent(request, daily_budget_usd=...), watch_binding.prepare_watch_intent(command, source_root=..., fix_options=...), and cli_execution.prepare_feature_fix_intent(request, checkout=...). Freeze all eventual CLI controls, profile, input bytes, source hashes and clean-checkout identity.
4. Build each group's fixed slot-to-intent_sha256 map. Derive its preparation digest from canonical JSON containing these real inputs, exact intents, controls and implementation pins. Bind both hashes in task_pins.F3b/F5 before activating the one shared allocation. Do not use placeholder hashes or hash this prose as preparation.
5. Set explicit group and per-slot ceilings in the approved plan. F3b totals at most $1; F5 at most $0.30; each slot at most $0.30. These limits do not grant authorization. Inherit the actual receipt daily allowance.
6. Claim each parent once, then run its slots sequentially. The preserved inventory uses F1 v7 input provenance; the current F1 v8 and F3 v2 preparation receipts bind the completed integration. Any later pinned-source change requires a new reviewed preparation.

## Two snapshot CLI runs

For snapshot-s2 and snapshot-nanogpt, rebuild the intent from the files and call claim_feature_child with a fresh 32-hex run ID. Save the returned binding alone in an owner-private regular JSON file, mode 0600. Set HEADROOM_SNAPSHOT_FEATURE_BINDING to that path only for the installed CLI invocation.

The normal command remains headroom diagnose --snapshot ... --traceback ... --source ... --runtime-profile ... --budget 0.30. Use exactly the frozen files and controls. The CLI passes the assigned ID and retains live_model provenance. It intentionally does not claim or finish automatically.

After process termination, inspect the terminal result and require snapshot_cleanup_verified(run_root, run_id) before calling finish_feature_child. The helper separately requires closed, known-cost budget state. Unknown costs or uncertain cleanup stop continuation. Every snapshot result keeps verification=not_run: a generated patch is not a GPU repair.

## One Web upload

The private create_app(snapshot_allocation_parent=parent) hook is now present. Configure the same runtime profile; preserve normal owner cookies, rate limits and readiness checks. The server manager claims snapshot-web from the actual uploaded hashes, supervises the child and settles after cleanup. Upload the exact recorded nanoGPT files. HTTP cannot select receipt, parent, slot or budget.

The public service remains disabled for new work. A later real check must have one active snapshot dispatcher; an enable flag alone does not prove singleton ownership. Record the real diagnosis card and hardware-not-run label. Snapshot binding integration evidence is maintained separately in ../final48h-snapshot-binding-20261029.

## Watch and clean F5

For Watch, claim watch-s1 and save mode-0600 JSON containing exactly binding and intent. Set HEADROOM_WATCH_FEATURE_CONTEXT only for headroom watch, passing the frozen --runtime-profile, --budget 0.30, full receipt --daily-budget, --source-root scenarios/s1_batch_too_big, and -- python train.py. The helper verifies original command/source against the actual OOM capture before repair. Save terminal output. The controller must verify process completion and all owned Lab cleanups before finishing the child; uncertainty stays unsettled.

For F5, create the fixed s3 FixRequest in the refreshed clean checkout and claim clean-s3. Use the existing supervise_evaluation_run with allocation_child_binding, feature_intent and preparation=None. It launches that checkout's installed CLI and retains the 480-second supervision and normal reporting/closing logic. Provide its required private credentials without putting them in reports. After terminal result, verified CLI receipt and cleanup, finish the child and parent.

No new execution framework is required. Still pending are A, the actual profile/day limit, and feature preparation/slot maps bound to those exact settings and the selected checkout. The completed source-pin refresh and clean-checkout check are recorded above; they do not activate a pool. Three maximum-cost snapshots can leave insufficient room for a $0.30 Watch slot; stop rather than reset or exceed the group cap. Keep two snapshot trials, one authored truth and nanoGPT's unknown truth explicit. Web transport, Watch triggering, snapshot diagnosis and clean-clone GPU repair remain separate observations.
