# Plan changes and clarifications

Canonical plan: `docs/PLAN.md` is immutable and matches the supplied attachment.

## Approved changes

No acceptance or feature-scope changes. On 2026-10-23 Frank explicitly requested retaining the original plan and discussing the proposed corrections individually later. No proposed acceptance correction is approved for implementation.

## Current sequencing instruction

After stopping the competing GPU service, Frank said to continue other work while he registers accounts. API-independent Lab and evidence-pack implementation proceeds under that instruction. T0.1/T0.4/T0.5 remain pending; their live acceptance is not inferred from offline work. This does not authorize paid calls or any pending acceptance correction.

## Explicit v4.2 precedence (already specified in the supplied plan)

- Section 0.6 supersedes the older T1.12 ending and Phase 2 heading: after passing MVP,
  continue to Phase 2 P0 without waiting; if still failing after the allowed three repairs,
  stop for Frank.
- T0.1 explicitly permits work on T0.2, T0.3 and T0.6 while keys are pending.

## Pending decisions

- True peak reconstruction and valid paired numerical comparisons.
- Distinguish cached free memory from demonstrated fragmentation.
- Preserve existing run evidence rather than deleting it.
- Phase 2 maximum six rounds; precision-changing candidates only under an allowing policy.

No pending proposal is treated as an approved change or as a passed acceptance check.

## Implementation versus pending plan changes

T1.2 reconstructs the true peak because existing section C.4 already requires
blocks alive at the peak. Its high cache-gap flag is retained as required, with
a separate limitation explaining that it does not prove harmful fragmentation.
These implementation details do not approve the pending changes to numerical
comparisons, loop acceptance or precision policies. T1.2's s2 >=40% gate remains
unchanged and fails on the measured capture (39.8715009692%).

## 2026-10-24 continuation

Frank asked to defer the Nebius registration/credit issue and start the previously
account-dependent work. T0.4/T1.3 may be prepared and mock-tested; T1.4 schema and
prompt checks may also be prepared. These are intermediate artifacts, not accepted
live gates. The existing T1.2 >=40% failure and other deferred plan corrections
remain unchanged. No alternative model provider or paid account action is implied.

Tavily's authenticated Billing page shows the free Researcher plan, 0/1000 credits
used, pay-as-you-go off, auto-upgrade off, and requests stopping at the plan limit.
The requested four-operation probe can use those free credits once its existing
key is configured on azuki; it must not enable a paid plan or auto-upgrade.

Validation for the 2026-10-24 offline continuation is saved in
reports/api-prep-20261023T222659Z.json (259 tests, Ruff/format, 62-item no-request
dry-run). A corrected test-isolation incident is documented in docs/MODELS.md;
no authenticated model or Tavily call is claimed. Original acceptance gates and
the canonical PLAN.md bytes remain unchanged.
