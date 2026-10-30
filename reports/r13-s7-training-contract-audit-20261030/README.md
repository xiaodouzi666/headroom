# R13 s7: executed training contract versus intended label

The saved final diagnosis proposes freezing the backbone and removing it from AdamW while claiming that this preserves head-only training. It also estimates about 30B backbone parameters. The actual program has 1,075,970,304 total parameters and updates all of them. Its name and intended_trainable=head label do not describe its executed optimization problem.

Both real Ultra requests contained the complete source, including backbone.eval(), the comment that requires_grad was never disabled, and AdamW(model.parameters(), foreach=False). They also contained the owned optimizer catalog. Neither request included the already captured runtime parameter/update observations: its runtime_input_observations field instead said unsupported because the separate named-input pairing adapter does not recognize this source.

The saved host instrumentation is stronger than that unsupported input status: 34 observed Parameter tensors sum exactly to the complete registered model count; every one had requires_grad=true, and all 20 optimizer steps recorded complete updates covering every one of those 34 IDs. Optimizer class was torch.optim.adamw.AdamW. These are observed update-set facts, not a proof of numerical/objective equivalence.

A read-only recheck of the old real model-generated head-only candidate against today's static check_source_changes still returns allowed=true, issues=[] and requires_runtime_verification=true. Existing static policy checks model shape/constructor sizes, training limits and precision, but do not establish unchanged trainability or optimizer parameter membership. The unchanged total parameter-count gate also cannot detect freezing parameters that still exist. Historical full loss comparison rejected such a candidate.

## Minimum general mechanisms

1. Forward a small, source/run-bound summary of the existing optimizer_update_observation and step_records independently of named-input pairing support. Require complete capture/parameter coverage, unique valid IDs/counts and matching source identity. State precisely whether the observed catalog covers the complete registered count. Missing facts remain unknown; this summary must not certify objective equivalence, absent clipping, helper applicability or arbitrary external targets.
2. Give executed source/update facts priority over names, comments and intended labels. A plan must preserve the baseline's actually updated parameter set, original hyperparameters and update boundary. The owned operator is optional and cannot turn a false full-to-head-only claim into an equivalent plan.
3. For a further guard, detect known new requires_grad=False changes and optimizer parameter-expression narrowing before execution when the existing policy forbids changing model/training mathematics. Preserve unknown cases and do not whitelist an arbitrary helper or claim semantic proof from a matching count. The generic same-parameter AdamW-in-backward API can remain an independently chosen candidate under its real prerequisites.

No hidden research patch, changed scene source, lowered threshold or new model/GPU call is required for this evidence handoff. A later genuine model choice and complete hardware validation are still necessary. The first Ultra answer is not retained, so only the final diagnosis's failure is characterized.
