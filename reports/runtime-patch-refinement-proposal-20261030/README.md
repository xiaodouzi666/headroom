# Proposal: continue implementation repair without re-diagnosing an unchanged program

Recommendation: yes, add a narrowly gated patch-refinement path within the existing six rounds. This is a new Super invocation using an earlier real, host-revalidated ready diagnosis from the same run. It is not a replayed patch, a new Ultra diagnosis, or an accepted repair.

## Actual counterexample

R15 s4 round 1's ready diagnosis correctly requested removal of retain_graph and scalar metric accumulation. Super changed total_loss += loss.item() but left the subsequent total_loss.item() consumer. The candidate completed only one GPU update and raised AttributeError at train.py:114. The runtime capture/trace, original source, policy and goal remained available; target/container/artifact cleanup was verified. Instead of repairing that implementation, round 2 invoked Ultra again, which requested unrelated optimizer/update certainty and terminated needs_more_info.

r15-s4-readonly-gate-replay.json binds this to the unchanged actual saved report, ready diagnosis, failed patch and source traceback. The draft predicate admits this failure and a complete bounded retained-copy fingerprint can be computed. No model, patch or GPU work was replayed by this audit; the historical result remains false.

## Proposed mechanism

1. After a reverted candidate, create one pending refinement ticket only for a finalized, clean, observed Python implementation failure. First-version exception classes are AttributeError, NameError, TypeError, UnboundLocalError, IndexError and KeyError. The candidate must have passed static patch policy, preserve CLI/environment, have unchanged measured parameter count and permitted numerics, and have verified capture/export/container/artifact cleanup.
2. At the next ordinary loop iteration, consume the ticket once. Recompute a hash over the complete selected original Lab source copy and its manifest, raw retained JSON/Markdown evidence, selected run, argv, policy, target/reference configuration, seed, optimizer-update count and runtime settings. Changed, missing, unsafe or incomplete context invalidates reuse.
3. Re-run the existing host diagnosis validator on the prior real payload. Only a still-ready result may be reused. Otherwise use the normal fresh diagnosis route.
4. Invoke the existing Super patch engine on the retained original source, with the entire bounded failed diff and exact source-bound exception frames. Request a fresh complete implementation including affected consumers. The failed candidate is never used as the next baseline.
5. Keep every existing source/static policy check, candidate reference preflight, model reservation, GPU/sandbox verification, numerical comparison, target/speed rule and keep/revert decision. A successful candidate still needs all original gates. Every refinement consumes a normal round; the six-round bound is unchanged.

A distinct diagnose.reused_for_patch_refinement event and model_response_reused_from metadata identify the original real diagnosis path/round/hash. No fresh Ultra event or fee is invented. Another eligible implementation failure may produce the next ticket, still inside the same finite loop. Static rejection, changed loss, precision/parameter-policy failure, OOM, timeout, CUDA RuntimeError, transport/preparation failure, unknown cleanup, incomplete traceback and changed state do not use this path.

## Conservative first-version scope

The complete original selected Lab source copy must match its manifest, contain at most 64 files / 4 MiB total and no unsafe paths or unlisted additions. Kept patch trees do not use the shortcut in this first version. They fall back to the existing fresh diagnosis flow. Tracebacks expose only exact /source frames, source SHA, exception class and bounded/redacted message; no arbitrary host path or log is sent. The complete failed diff and refinement context must fit 8 KiB, included in the existing shared 64 KiB solver bound.

This strict scope addresses the observed consumer bug without guessing optimizer hyperparameters, deleting true prerequisites, changing goals, recognizing benchmark names or inserting a handwritten target fix. It will not by itself solve all other R15 planning failures or prove six of nine.

## Reviewable artifacts and validation

proposal.diff contains a new runtime_refinement helper plus proposed orchestrator/solver-context/patch-engine wiring. All files are under proposed/; production headroom, tests, prompts and controllers were not edited.

The draft helper has 26 v5-guarded offline tests covering the actual saved R15 failure, numerical/policy and cleanup exclusions, source/evidence/configuration changes, unlisted/symlink sources, complete failed diff and byte bounds. Draft files compile, Ruff and formatting checks pass. Production base hashes remain unchanged.

The full proposed orchestrator has not yet been imported/executed as a live or mocked integration. Before applying/promoting it, add explicit MockTransport integration tests proving one initial Ultra plus two fresh Super requests, original-source rollback, no reuse after policy/source/semantic changes, unchanged six-round and per-run model budgets, and preserved numerical rejection. Then run a fresh separately recorded campaign within the already authorized remaining pool. No historical result or fixed-nine denominator/gate should be changed.
