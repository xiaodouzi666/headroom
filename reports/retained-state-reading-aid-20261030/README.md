# Current source versus historical candidate state

R8 s8 round 2 was reverted after a teacher UnboundLocalError. Its recorded selection stayed on the original baseline. The next diagnosis nevertheless described the rejected guard as already present in the retained source.

The new small reading aid puts the current execution selection beside each earlier candidate identifier. Historical `candidate_selected` and `selected_after_round` are snapshots from those rounds; they do not identify the source retained by a later request. Current edit coordinates still come from current source documents. Missing selection metadata stays unknown and no diagnosis, source, verifier result or policy is rewritten.

`historical-reconstruction.json` reconstructs the new aid from genuine saved round-end metadata. It is an offline counterexample check, not a replay of the original model request and not a new repair success. Focused tests also exercise actual orchestrator transitions through keep, revert, and later repair with both Ultra and Super request builders.
