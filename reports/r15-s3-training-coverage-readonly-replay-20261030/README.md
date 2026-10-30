# R15 s3 read-only training-coverage replay

PASS. Used the existing campaign third row and saved verification baseline/candidate run IDs, read both retained source/train.py files independently, and matched their actual byte SHA256 to the capture source digests. Both actual captures completed twenty logical updates. The new guard finds no reduction; it does not override the existing parameter_policy.

Each logical update covered37,791,744 observed elements on both sides. This is offline replay of saved observations, not a GPU/model rerun or a new accepted target.

Both old captures lack optional group_options. Their complete current optimizer summaries exactly match the pre-group-metadata implementation at964b658: status remains observed, optimizer_group_hyperparameters remains not_captured, and numerical_equivalence_proven remains false. No defaults or new hyperparameters were backfilled.

Campaign, job report, source and capture hashes were checked unchanged before/after. Exact bindings, old/current summaries and guard output are in replay.json. No historical result, count, patch, budget or runtime execution was modified.
