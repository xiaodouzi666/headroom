# Early training-update intent screen — proposal only

R17 s7 exercised the new runtime guard successfully. Both a head-only optimizer and a full optimizer with backbone requires_grad=False completed20 steps, reduced peak17.8198→4.4132GB, and were rejected/reverted: training_coverage_not_reduced=false, parameter_policy=false and numerical_acceptance=false. Parameter count alone stayed unchanged in both, and the scalar max difference was3.3520. These are failed candidates, not target successes.

The proposed early check would reject only a clearly positive freeze/exclude-updated-parameters intent when the already-sent, source/run-bound original observation proves a complete all-registered-parameter update scope and the unchanged policy explicitly forbids a model change. It would raise the existing MODEL_CHANGE_FORBIDDEN output-contract issue so the model can use its already-limited correction request. It would not modify needs_more_info or select a repair for the model.

The first predicate should be deliberately narrow: require actual plan description content, explicit parameter-update reduction, and clause-level negation checks; never reject a title merely containing freeze. Already-frozen or never-updated members, incomplete observations, unregistered eval-only modules, activation lifetime edits and preserving in-backward updates are necessary counterexamples.

proposal.json records the exact conjunction, code anchors, source-bound feedback scope and counterexamples. All existing post-patch/GPU/numerical checks remain final and unchanged. No production/test file or runtime was modified here.
