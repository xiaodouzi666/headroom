# Retained initial full regression failure

The full guarded run 20261025T091216Z-088540d3 finished with
2717 passed and 30 failed in 725.40 seconds. The 293 source entries, canonical
PLAN and offline isolation guard were unchanged throughout the run.

Every failure was in tests/test_diagnosis_acceptance.py. The prepared-call
adapter in headroom/acceptance/diagnosis.py still required reasoning is False;
the production diagnostic call now deliberately supplies True. The adapter
therefore rejected dispatch with ONLY_ONE_PREPARED_DIAGNOSIS_ALLOWED before any
HTTP transport. Prepared messages and their independently derived schema also
need the exact new availability catalogue.

The failure is retained. The repair must update the prepared request contract
rather than remove its one-call, exact-message/schema, model identity, output
cap or financial checks. New negative tests must retain refusal of drift and
second attempts. No model/GPU acceptance has been run for this repair iteration.
A fresh source-matched full pass is still required before dispatch.
