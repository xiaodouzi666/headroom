# Judge expiry compatibility — candidate, not deployed

2026-10-30. Parent authorized a narrow update for the revised official judging period. This extends access time only; no additional amount, credential, allocation, model capability or safety relaxation is introduced.

## Official evidence

Both [rules section 1](https://nebiusglobalaihackathon.devpost.com/rules) and [dates](https://nebiusglobalaihackathon.devpost.com/details/dates), read in this review, now end judging at December 23, 2026 12:00 PST = 2026-12-23T20:00:00Z = December 24 04:00 Beijing. The related requirements review records the Manager's conditional access clarification. No organizer message was sent.

## Implementation and compatibility

Only headroom/acceptance/judge_binding.py changes product behavior. The original EXPIRES_AT (December 15) remains the historical receipt/plan/credit serialization anchor. judge_credit.py is unchanged, so recomputing existing immutable credit documents does not change their hash. Receipt, profile, database identities, existing rows, funding caps and credentials need no migration or overwrite.

A fixed source-reviewed JUDGING_PERIOD_POLICY and EFFECTIVE_EXPIRES_AT introduce the new date. New claims use run.v3 with the explicit policy and expiry. The funding check continues to select the same original cap or authenticated credit-extension hash; it never treats the period change as fresh funds. Source, request, profile, claim, ledger identity, run/day/total limits and strict budget mode checks remain in the normal factory path.

Legacy v1/v2 claims retain their original dispatch deadline. New reserve and mark_dispatched check the binding-specific deadline, including the exact boundary; honest settlement remains possible after either deadline. The public controller's effective_expires_at property distinguishes the reviewed access deadline from the immutable historical receipt. Queue worker selection uses trusted funding_kind, not a hard-coded v1/v2 schema string, so no queue change is needed.

## Focused verification

Executed remotely with synthetic temporary pools. Existing autouse guard blocks socket/DNS/provider/GPU subprocesses and production .cache/runs databases and credential files.

Command:
    .venv/bin/pytest -q tests/test_judge_period.py tests/test_judge_binding.py tests/test_judge_credit.py

Observed stdout: 86 passed in 6.20s. This is one combined run, not an additional 86 beyond its constituent tests. Ruff format/check passed for all four files. The new nine cases cover new-period dispatch with and without a credit extension, unchanged immutable files/DB identities/caps, legacy v1/v2 dispatch rejection and late settlement, rehashed policy/date/schema tampering, and the exact new deadline. Existing 77 cases retain funding/unknown-cost/cleanup/SDK MockTransport guards. No production data, provider calls, GPU work or service changes occurred.

Source hashes:

- headroom/acceptance/judge_binding.py: 2987663bf82926bda5745bfc2866155deec62f59ad0e8bee5f168bba7c2fb0e9
- tests/test_judge_period.py: 489a07d7cd6ff80a5595c95d5e622a33221086e74be2e634e160e91f7b988fb7
- tests/test_judge_binding.py: 1d03a43825a250850694aeedea186c70f3377995e31f8653d97895eab16a883b
- tests/test_judge_credit.py: 7f2b278ff35c0abec014d2b3dd866d254c38bfd7003af9fa4dedfb869a0fc463

## Operator deployment, no funding activation

1. Obtain the independent source review, confirm queue idle and no active unsettled worker.
2. Deploy the reviewed code and restart the existing public service using its unchanged trusted configuration. Do not edit receipt.json, runtime-profile.json, credit-extension.json, databases, token or amount settings; do not call any activation/bootstrap function.
3. Inspect effective_expires_at through the existing controller and verify ordinary health/config and current availability without starting a task. Confirm original private file digests and logical history are unchanged. Update the private testing instructions to cover December 23; avoid publishing credentials.
4. Record deployment separately. These instructions and the unit tests are not a deployment receipt.

Rollback must wait for every v3 claim to settle and clean up: older source cannot recover/settle an active v3 claim. A source rollback restores the older December 15 access behavior and does not justify editing historical rows or pretending the extended date remains deployed.
